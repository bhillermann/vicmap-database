"""Tests for ``vicmap_acquire.publish`` -- the transactional publication boundary.

Two tiers, exactly as ``test_staging.py`` established (research Validation
Architecture): pure/offline tests that compose and inspect the promotion SQL
against a recording fake cursor (no server, always run) and live tests that
skip -- never fail -- without both ``VICMAP_TEST_POSTGRES_DSN`` and
``VICMAP_TEST_POSTGRES_SUPERUSER_DSN`` (the superuser DSN is needed only to
build the throwaway audit/reader fixtures a real promotion reads).

The offline tests never ``import psycopg`` directly: they reach the driver and
its ``sql``/``errors`` modules through ``publish``'s own re-exports, mirroring
how ``test_staging.py`` uses ``staging.psycopg``/``staging.sql`` so the
driver-isolation posture is respected in the tests too.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import secrets
import shutil
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import publish_order
from vicmap_acquire import discovery, download, publish, staging
from vicmap_acquire import manifest as manifest_module


REPO_ROOT = Path(__file__).resolve().parent.parent


_RUN_TS = "20260918t041500z"
_STAGING_TABLE = "vmadd_address_20260918t041500z"


def _publish_policy(**overrides) -> publish.PublishPolicy:
    kwargs = dict(
        host="127.0.0.1",
        port=5432,
        dbname="vicmap",
        user="vicmap_loader",
        staging_schema="vicmap_staging",
        publish_schema="vicmap",
        target_srid=7899,
        reader_user="vicmap_reader",
        connect_timeout_seconds=5,
        statement_timeout_seconds=3600,
        lock_timeout_seconds=30,
    )
    kwargs.update(overrides)
    return publish.PublishPolicy(**kwargs)


def _one_layer_manifest(target_table: str = "vmadd_address"):
    """A stand-in manifest carrying only what ``promote_order`` reads --
    ``.layers`` and each layer's ``.target_table``. A real ``ImportManifest``
    would work identically; this keeps the offline test independent of the
    (heavier) discovery/profile machinery ``promote_order`` never touches."""

    return types.SimpleNamespace(
        layers=(types.SimpleNamespace(target_table=target_table),)
    )


class _FakeCursor:
    """Records every executed statement as rendered SQL text and answers the
    catalog-discovery/``version()`` reads from a fixed fixture, so a full
    ``promote_order`` runs with no server. Raises when a configured substring
    appears in a statement, to exercise the rollback path."""

    def __init__(self, connection):
        self._connection = connection
        self._rows: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, query, params=None):
        text = query if isinstance(query, str) else query.as_string(None)
        self._connection.executed.append(text)
        if self._connection.fail_on and self._connection.fail_on in text:
            raise RuntimeError("induced driver failure")
        if "staging_validation" in text and self._connection.audit_error is not None:
            raise self._connection.audit_error
        if "version()" in text:
            self._rows = [("PostgreSQL 18.6 (fake build)",)]
        elif "staging_validation" in text:
            self._rows = list(self._connection.audit_rows)
        elif "pg_constraint" in text:
            self._rows = list(self._connection.constraint_rows)
        elif "pg_indexes" in text:
            self._rows = list(self._connection.index_rows)
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeConnection:
    def __init__(
        self,
        *,
        constraint_rows=(),
        index_rows=(),
        audit_rows=(),
        fail_on=None,
        audit_error=None,
    ):
        self.executed: list[str] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False
        self.constraint_rows = constraint_rows
        self.index_rows = index_rows
        self.audit_rows = audit_rows
        self.fail_on = fail_on
        self.audit_error = audit_error

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True

    def ddl_statements(self) -> list[str]:
        """Only the statements ``promote_order`` itself issued -- the two
        ``SET`` timeout statements ``_connect`` runs are dropped so assertions
        read cleanly."""

        return [s for s in self.executed if "timeout" not in s.lower()]


# The canonical single-layer promotion fixture: a PG18-shaped catalog with a
# primary key, a named NOT NULL constraint on geom, and the GiST geometry
# index -- the exact object set a real ADDRESS staging table carries.
_PK_ROW = (f"{_STAGING_TABLE}_pkey", "p", None)
_NOT_NULL_ROW = (f"{_STAGING_TABLE}_geom_nn", "n", "geom")
_GEOM_INDEX_ROW = (f"{_STAGING_TABLE}_geom_gist", "geom")


class PublishPolicyValidationTest(unittest.TestCase):
    """No database. Mirrors ``StagingPolicy``'s up-front validation contract."""

    def test_valid_policy_constructs(self):
        policy = _publish_policy()
        self.assertEqual("vicmap", policy.publish_schema)
        self.assertEqual("vicmap_reader", policy.reader_user)

    def test_public_publish_schema_is_rejected(self):
        with self.assertRaises(ValueError):
            _publish_policy(publish_schema="public")

    def test_staging_equal_to_publish_schema_is_rejected(self):
        with self.assertRaises(ValueError):
            _publish_policy(staging_schema="vicmap", publish_schema="vicmap")

    def test_reader_equal_to_loader_is_rejected(self):
        with self.assertRaises(ValueError):
            _publish_policy(reader_user="vicmap_loader")

    def test_out_of_range_srid_is_rejected(self):
        with self.assertRaises(ValueError):
            _publish_policy(target_srid=999)

    def test_lock_timeout_exceeding_statement_timeout_is_rejected(self):
        with self.assertRaises(ValueError):
            _publish_policy(statement_timeout_seconds=10, lock_timeout_seconds=11)

    def test_non_identifier_reader_is_rejected(self):
        with self.assertRaises(ValueError):
            _publish_policy(reader_user="Robert'); DROP TABLE x;--")


class PromotionCompositionTest(unittest.TestCase):
    """No database. Proves the composed promotion SQL for one layer: version()
    first, a single scoped drop, the two-statement metadata move, canonical
    catalog-driven renames, and the in-transaction reader grant."""

    def _promote(self, connection):
        # promote_order opens two connections: the D-68 gate's read-only
        # connection first (answers the audit query with an all-PASS row) then
        # the promotion transaction's connection (``connection``, the one under
        # assertion). side_effect hands them out in that order.
        gate_conn = _FakeConnection(audit_rows=(("vmadd_address", "pass"),))
        with patch.object(
            publish.psycopg, "connect", side_effect=[gate_conn, connection]
        ):
            return publish.promote_order(
                _one_layer_manifest(),
                _publish_policy(),
                "sentinel-secret",
                _RUN_TS,
                "a" * 64,
            )

    def _connection(self, **overrides):
        params = dict(
            constraint_rows=(_PK_ROW, _NOT_NULL_ROW),
            index_rows=(_GEOM_INDEX_ROW,),
        )
        params.update(overrides)
        return _FakeConnection(**params)

    def test_version_is_the_first_promotion_action(self):
        connection = self._connection()
        self._promote(connection)
        ddl = connection.ddl_statements()
        version_index = next(i for i, s in enumerate(ddl) if "version()" in s)
        first_ddl_index = next(
            i
            for i, s in enumerate(ddl)
            if "DROP TABLE" in s or "ALTER TABLE" in s or "ALTER INDEX" in s
        )
        self.assertLess(version_index, first_ddl_index)

    def test_prior_table_drop_is_a_single_scoped_target_without_cascade(self):
        connection = self._connection()
        self._promote(connection)
        drops = [s for s in connection.executed if "DROP TABLE" in s]
        self.assertEqual(1, len(drops), connection.executed)
        drop = drops[0]
        self.assertIn("DROP TABLE IF EXISTS", drop)
        self.assertIn('"vicmap"."vmadd_address"', drop)
        self.assertNotIn("CASCADE", drop.upper())
        self.assertNotIn("*", drop)

    def test_set_schema_and_rename_are_separate_statements(self):
        connection = self._connection()
        self._promote(connection)
        set_schema = [s for s in connection.executed if "SET SCHEMA" in s]
        rename_table = [
            s for s in connection.executed if "RENAME TO" in s and "INDEX" not in s
        ]
        self.assertEqual(1, len(set_schema))
        self.assertEqual(1, len(rename_table))
        # The two forms are never combined into one ALTER TABLE.
        self.assertNotIn("RENAME", set_schema[0])
        self.assertNotIn("SET SCHEMA", rename_table[0])
        self.assertIn(
            '"vicmap_staging"."vmadd_address_20260918t041500z"', set_schema[0]
        )
        self.assertIn('SET SCHEMA "vicmap"', set_schema[0])
        self.assertIn('RENAME TO "vmadd_address"', rename_table[0])

    def test_primary_key_is_renamed_to_the_canonical_name(self):
        connection = self._connection()
        self._promote(connection)
        renames = [s for s in connection.executed if "RENAME CONSTRAINT" in s]
        self.assertTrue(
            any(
                f'RENAME CONSTRAINT "{_STAGING_TABLE}_pkey" TO "vmadd_address_pkey"'
                in s
                for s in renames
            ),
            renames,
        )

    def test_not_null_constraint_is_renamed_using_the_catalog_column(self):
        connection = self._connection()
        self._promote(connection)
        renames = [s for s in connection.executed if "RENAME CONSTRAINT" in s]
        self.assertTrue(
            any('TO "vmadd_address_geom_not_null"' in s for s in renames), renames
        )

    def test_geometry_index_is_renamed_to_canonical_geom_idx(self):
        connection = self._connection()
        self._promote(connection)
        index_renames = [s for s in connection.executed if "ALTER INDEX" in s]
        self.assertEqual(1, len(index_renames))
        self.assertIn(
            '"vicmap"."vmadd_address_20260918t041500z_geom_gist"', index_renames[0]
        )
        self.assertIn('RENAME TO "vmadd_address_geom_idx"', index_renames[0])

    def test_reader_is_granted_select_in_the_same_transaction(self):
        connection = self._connection()
        self._promote(connection)
        grants = [s for s in connection.executed if s.startswith("GRANT")]
        self.assertEqual(1, len(grants))
        self.assertIn('GRANT SELECT ON "vicmap"."vmadd_address"', grants[0])
        self.assertIn('TO "vicmap_reader"', grants[0])

    def test_successful_promotion_commits_and_never_rolls_back(self):
        connection = self._connection()
        result = self._promote(connection)
        # One commit in _connect's timeout setup, one final commit after DDL.
        self.assertEqual(2, connection.commit_count)
        self.assertEqual(0, connection.rollback_count)
        self.assertEqual(("vmadd_address",), result.published_tables)
        self.assertIn("PostgreSQL", result.server_version)


class PromotionRollbackCompositionTest(unittest.TestCase):
    """No database. An induced failure mid-promotion rolls the transaction back
    and re-raises the closed ``PromotionFailed`` -- the final commit never
    runs, so a real prior table would be left untouched (PUB-03)."""

    def test_failure_rolls_back_and_raises_promotion_failed(self):
        gate_conn = _FakeConnection(audit_rows=(("vmadd_address", "pass"),))
        connection = _FakeConnection(
            constraint_rows=(_PK_ROW, _NOT_NULL_ROW),
            index_rows=(_GEOM_INDEX_ROW,),
            fail_on="GRANT SELECT",
        )
        with patch.object(
            publish.psycopg, "connect", side_effect=[gate_conn, connection]
        ):
            with self.assertRaises(publish.PromotionFailed):
                publish.promote_order(
                    _one_layer_manifest(),
                    _publish_policy(),
                    "sentinel-secret",
                    _RUN_TS,
                    "a" * 64,
                )
        self.assertEqual(1, connection.rollback_count)
        # Only _connect's setup commit ran; the final promotion commit did not.
        self.assertEqual(1, connection.commit_count)

    def test_promotion_failed_carries_only_its_code(self):
        self.assertEqual("pub_promotion_failed", publish.PromotionFailed.code)
        self.assertEqual("pub_promotion_failed", str(publish.PromotionFailed()))


class ClosedFailureVocabularyTest(unittest.TestCase):
    """No database. The closed failure codes equal their ``evidence.ReasonCode``
    counterparts (checked in ``test_evidence``); here we pin the codes this
    module owns so a rename cannot silently drift."""

    def test_publication_validation_missing_code(self):
        self.assertEqual(
            "pub_validation_missing", publish.PublicationValidationMissing.code
        )

    def test_publish_failures_are_a_closed_hierarchy(self):
        for failure in (publish.PromotionFailed, publish.PublicationValidationMissing):
            self.assertTrue(issubclass(failure, publish.PublishFailure))

    def test_reader_role_unavailable_code(self):
        self.assertEqual("reader_role_unavailable", publish.ReaderRoleUnavailable.code)

    def test_reader_verification_failed_code(self):
        self.assertEqual(
            "reader_verification_failed", publish.ReaderVerificationFailed.code
        )

    def test_reader_write_not_denied_code(self):
        self.assertEqual("reader_write_not_denied", publish.ReaderWriteNotDenied.code)

    def test_reader_failures_are_a_closed_hierarchy(self):
        for failure in (
            publish.ReaderRoleUnavailable,
            publish.ReaderVerificationFailed,
            publish.ReaderWriteNotDenied,
        ):
            self.assertTrue(issubclass(failure, publish.PublishFailure))


def _two_layer_target_tables():
    return ("vmadd_address", "vmadd_road")


class PublicationGateTest(unittest.TestCase):
    """No database. The D-68 gate hard-stops before any DDL: every required
    target must have a PASS row for the run, else PublicationValidationMissing;
    an unreadable audit table is AuditPrivilegeDenied. This unit test runs
    offline (it must, per the plan) by patching the driver connection."""

    def _run_gate(self, connection, target_tables):
        with patch.object(publish.psycopg, "connect", return_value=connection):
            publish.assert_all_layers_validated(
                _publish_policy(),
                "sentinel-secret",
                run_timestamp=_RUN_TS,
                manifest_digest="a" * 64,
                target_tables=target_tables,
            )

    def test_all_layers_pass_is_accepted(self):
        connection = _FakeConnection(
            audit_rows=(("vmadd_address", "pass"), ("vmadd_road", "pass"))
        )
        self._run_gate(connection, _two_layer_target_tables())  # no raise
        # A gate is read-only: it executes no DDL.
        for statement in connection.executed:
            self.assertNotIn("DROP TABLE", statement)
            self.assertNotIn("ALTER TABLE", statement)
            self.assertNotIn("GRANT", statement)

    def test_a_missing_layer_raises_publication_validation_missing(self):
        connection = _FakeConnection(audit_rows=(("vmadd_address", "pass"),))
        with self.assertRaises(publish.PublicationValidationMissing):
            self._run_gate(connection, _two_layer_target_tables())

    def test_a_non_pass_verdict_raises_publication_validation_missing(self):
        connection = _FakeConnection(
            audit_rows=(("vmadd_address", "pass"), ("vmadd_road", "fail"))
        )
        with self.assertRaises(publish.PublicationValidationMissing):
            self._run_gate(connection, _two_layer_target_tables())

    def test_no_ddl_runs_when_the_gate_fails(self):
        connection = _FakeConnection(audit_rows=())
        with self.assertRaises(publish.PublicationValidationMissing):
            self._run_gate(connection, ("vmadd_address",))
        self.assertFalse(
            any("DROP TABLE" in s or "ALTER TABLE" in s for s in connection.executed)
        )

    def test_unreadable_audit_table_raises_audit_privilege_denied(self):
        connection = _FakeConnection(
            audit_error=publish.pg_errors.InsufficientPrivilege("denied")
        )
        with patch.object(publish.psycopg, "connect", return_value=connection):
            with self.assertRaises(publish.AuditPrivilegeDenied):
                publish.assert_all_layers_validated(
                    _publish_policy(),
                    "sentinel-secret",
                    run_timestamp=_RUN_TS,
                    manifest_digest="a" * 64,
                    target_tables=("vmadd_address",),
                )

    def test_promote_order_hard_stops_before_any_ddl_when_the_gate_fails(self):
        # The gate connection returns no PASS rows; promote_order must raise
        # before it ever opens the promotion transaction, so only ONE
        # connection is created and it issues no DDL (PUB-01/T-04-06).
        gate_conn = _FakeConnection(audit_rows=())
        created: list[_FakeConnection] = []

        def _factory(*args, **kwargs):
            created.append(gate_conn)
            return gate_conn

        with patch.object(publish.psycopg, "connect", side_effect=_factory):
            with self.assertRaises(publish.PublicationValidationMissing):
                publish.promote_order(
                    _one_layer_manifest(),
                    _publish_policy(),
                    "sentinel-secret",
                    _RUN_TS,
                    "a" * 64,
                )
        self.assertEqual(1, len(created))
        self.assertFalse(any("DROP TABLE" in s for s in gate_conn.executed))


class _FakeReaderCursor:
    """Records every executed statement and answers discovery/spatial-query
    reads from the owning connection's fixed fixture rows. The write attempt
    either raises ``InsufficientPrivilege`` (denied, the pass case) or
    succeeds silently (not denied, the security-critical hard-stop case),
    controlled by the owning connection's ``deny_write`` flag -- exactly the
    two branches ``verify_reader_access`` must distinguish."""

    def __init__(self, connection):
        self._connection = connection
        self._rows: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, query, params=None):
        text = query if isinstance(query, str) else query.as_string(None)
        self._connection.executed.append(text)
        if "SET statement_timeout" in text or "SET lock_timeout" in text:
            return
        if "INSERT INTO" in text:
            if self._connection.deny_write:
                raise publish.pg_errors.InsufficientPrivilege("denied")
            # A writable role passes the ACL check; the real server may then
            # raise a row-level constraint error (CR-01: DEFAULT VALUES tripped
            # gid's NOT NULL). Model that when write_error is set; otherwise a
            # zero-row probe succeeds silently.
            if self._connection.write_error is not None:
                raise self._connection.write_error
            return
        if "information_schema.tables" in text:
            if self._connection.discovery_error is not None:
                raise self._connection.discovery_error
            self._rows = list(self._connection.discovered_rows)
        elif "ST_Transform" in text:
            self._rows = list(self._connection.spatial_rows)
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)


class _FakeReaderConnection:
    """A recording fake standing in for the second, independently-
    authenticated reader connection ``verify_reader_access`` opens -- never
    the same connection/fixture ``_FakeConnection`` above uses for the
    promotion transaction, keeping the two proofs' fixtures independent."""

    def __init__(
        self,
        *,
        discovered_rows=(),
        spatial_rows=(),
        deny_write=True,
        discovery_error=None,
        write_error=None,
    ):
        self.executed: list[str] = []
        self.discovered_rows = discovered_rows
        self.spatial_rows = spatial_rows
        self.deny_write = deny_write
        self.discovery_error = discovery_error
        self.write_error = write_error
        self.rollback_count = 0
        self.commit_count = 0
        self.closed = False

    def cursor(self):
        return _FakeReaderCursor(self)

    def rollback(self):
        self.rollback_count += 1

    def commit(self):
        self.commit_count += 1

    def close(self):
        self.closed = True


class ReaderVerificationTest(unittest.TestCase):
    """No database. Proves ``verify_reader_access``'s whole PUB-04/PUB-05
    contract against a recording fake reader connection: table discovery,
    the Victoria-extent GiST-exercising spatial query, the real executed
    write-denial proof, and the security-critical not-denied hard-stop
    (T-04-02) -- with no metadata-only shortcut."""

    def _connection(self, **overrides):
        params = dict(
            discovered_rows=[("vmadd_address",)],
            spatial_rows=[(1,), (2,)],
            deny_write=True,
        )
        params.update(overrides)
        return _FakeReaderConnection(**params)

    def test_missing_reader_password_fails_closed_before_any_connection(self):
        with patch.object(publish.psycopg, "connect") as connect:
            with self.assertRaises(publish.ReaderRoleUnavailable):
                publish.verify_reader_access(
                    _publish_policy(),
                    reader_password="",
                    published_tables=("vmadd_address",),
                )
        connect.assert_not_called()

    def test_empty_published_tables_fails_closed_before_any_connection(self):
        with patch.object(publish.psycopg, "connect") as connect:
            with self.assertRaises(publish.ReaderVerificationFailed):
                publish.verify_reader_access(
                    _publish_policy(), reader_password="sentinel-secret", published_tables=()
                )
        connect.assert_not_called()

    def test_reader_connect_failure_is_reader_role_unavailable(self):
        with patch.object(
            publish.psycopg, "connect", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(publish.ReaderRoleUnavailable):
                publish.verify_reader_access(
                    _publish_policy(),
                    reader_password="sentinel-secret",
                    published_tables=("vmadd_address",),
                )

    def test_discovery_spatial_query_and_write_denial_proof(self):
        connection = self._connection()
        with patch.object(publish.psycopg, "connect", return_value=connection):
            result = publish.verify_reader_access(
                _publish_policy(),
                reader_password="sentinel-secret",
                published_tables=("vmadd_address",),
            )
        self.assertEqual(("vmadd_address",), result.tables_discovered)
        self.assertEqual(2, result.spatial_query_row_count)
        self.assertTrue(result.write_denied)
        self.assertTrue(connection.closed)
        self.assertGreaterEqual(connection.rollback_count, 1)

    def test_discovery_query_is_scoped_to_the_publish_schema(self):
        connection = self._connection()
        with patch.object(publish.psycopg, "connect", return_value=connection):
            publish.verify_reader_access(
                _publish_policy(),
                reader_password="sentinel-secret",
                published_tables=("vmadd_address",),
            )
        discovery = [s for s in connection.executed if "information_schema.tables" in s]
        self.assertEqual(1, len(discovery))

    def test_spatial_query_uses_victoria_wgs84_extent_and_target_srid(self):
        connection = self._connection()
        with patch.object(publish.psycopg, "connect", return_value=connection):
            publish.verify_reader_access(
                _publish_policy(),
                reader_password="sentinel-secret",
                published_tables=("vmadd_address",),
            )
        spatial = [s for s in connection.executed if "ST_Transform" in s]
        self.assertEqual(1, len(spatial))
        self.assertIn("140.96", spatial[0])
        self.assertIn("-39.2", spatial[0])
        self.assertIn('"vicmap"."vmadd_address"', spatial[0])

    def test_writable_reader_raises_reader_write_not_denied(self):
        # T-04-02, security-critical: a writable reader is caught, never a
        # silent pass -- the negative proof that the check actually detects
        # a broken grant, not just the happy path.
        connection = self._connection(deny_write=False)
        with patch.object(publish.psycopg, "connect", return_value=connection):
            with self.assertRaises(publish.ReaderWriteNotDenied):
                publish.verify_reader_access(
                    _publish_policy(),
                    reader_password="sentinel-secret",
                    published_tables=("vmadd_address",),
                )
        # The check always rolls back, whether the write was denied or not,
        # and always closes -- no state is ever left behind.
        self.assertGreaterEqual(connection.rollback_count, 1)
        self.assertTrue(connection.closed)

    def test_writable_reader_hitting_not_null_still_raises_not_denied(self):
        # CR-01: the exact broken-grant failure mode. A reader mistakenly
        # granted INSERT passes the ACL check, so on this schema the write
        # would trip gid's NOT NULL/PK constraint (NotNullViolation) rather
        # than succeed. That is still a WRITABLE reader -- it must raise the
        # security-critical ReaderWriteNotDenied, never fall through as an
        # uncaught IntegrityError misreported as an internal failure.
        connection = self._connection(
            deny_write=False,
            write_error=publish.pg_errors.NotNullViolation("null value in gid"),
        )
        with patch.object(publish.psycopg, "connect", return_value=connection):
            with self.assertRaises(publish.ReaderWriteNotDenied):
                publish.verify_reader_access(
                    _publish_policy(),
                    reader_password="sentinel-secret",
                    published_tables=("vmadd_address",),
                )
        self.assertGreaterEqual(connection.rollback_count, 1)
        self.assertTrue(connection.closed)

    def test_write_probe_is_zero_row_insert_never_default_values(self):
        # CR-01 regression guard: the write probe must be a zero-row
        # INSERT ... SELECT ... WHERE false (ACL-checked but constraint-free),
        # never DEFAULT VALUES (which trips gid NOT NULL before the ACL result
        # can be observed on a writable reader).
        connection = self._connection()
        with patch.object(publish.psycopg, "connect", return_value=connection):
            publish.verify_reader_access(
                _publish_policy(),
                reader_password="sentinel-secret",
                published_tables=("vmadd_address",),
            )
        inserts = [s for s in connection.executed if "INSERT INTO" in s]
        self.assertEqual(1, len(inserts))
        self.assertIn("WHERE false", inserts[0])
        self.assertNotIn("DEFAULT VALUES", inserts[0])

    def test_discovery_failure_is_reader_verification_failed(self):
        connection = self._connection(discovery_error=RuntimeError("driver exploded"))
        with patch.object(publish.psycopg, "connect", return_value=connection):
            with self.assertRaises(publish.ReaderVerificationFailed):
                publish.verify_reader_access(
                    _publish_policy(),
                    reader_password="sentinel-secret",
                    published_tables=("vmadd_address",),
                )
        self.assertTrue(connection.closed)


class ReadLayerValidationsTest(unittest.TestCase):
    """No database. ``read_layer_validations`` re-reads the full D-56 metrics
    (not just the pass/fail the gate checks) for every manifest layer, in
    the caller's own ``target_tables`` order, and maps the same failure
    modes as the gate."""

    _AUDIT_ROW = (
        "vmadd_address",
        "pass",
        True,
        4222035,
        7899,
        "POINT",
        12,
    )
    _NON_SPATIAL_ROW = (
        "vmadd_lookup",
        "pass",
        False,
        100,
        None,
        None,
        None,
    )

    def test_returns_one_record_per_target_table_in_caller_order(self):
        connection = _FakeConnection(
            audit_rows=(self._NON_SPATIAL_ROW, self._AUDIT_ROW)
        )
        with patch.object(publish.psycopg, "connect", return_value=connection):
            records = publish.read_layer_validations(
                _publish_policy(),
                "sentinel-secret",
                run_timestamp=_RUN_TS,
                manifest_digest="a" * 64,
                target_tables=("vmadd_address", "vmadd_lookup"),
            )
        self.assertEqual(2, len(records))
        self.assertEqual("vmadd_address", records[0].target_table)
        self.assertTrue(records[0].spatial)
        self.assertEqual(4222035, records[0].row_count)
        self.assertEqual(7899, records[0].srid)
        self.assertEqual("vmadd_lookup", records[1].target_table)
        self.assertFalse(records[1].spatial)
        self.assertIsNone(records[1].srid)
        self.assertIsNone(records[1].geometry_type)
        self.assertIsNone(records[1].repaired_count)
        # A read-only re-read: no DDL, no write.
        for statement in connection.executed:
            self.assertNotIn("DROP TABLE", statement)
            self.assertNotIn("ALTER TABLE", statement)
            self.assertNotIn("GRANT", statement)
            self.assertNotIn("INSERT", statement)

    def test_a_table_with_no_row_is_simply_omitted(self):
        connection = _FakeConnection(audit_rows=(self._AUDIT_ROW,))
        with patch.object(publish.psycopg, "connect", return_value=connection):
            records = publish.read_layer_validations(
                _publish_policy(),
                "sentinel-secret",
                run_timestamp=_RUN_TS,
                manifest_digest="a" * 64,
                target_tables=("vmadd_address", "vmadd_road"),
            )
        self.assertEqual(("vmadd_address",), tuple(r.target_table for r in records))

    def test_unreadable_audit_table_raises_audit_privilege_denied(self):
        connection = _FakeConnection(
            audit_error=publish.pg_errors.InsufficientPrivilege("denied")
        )
        with patch.object(publish.psycopg, "connect", return_value=connection):
            with self.assertRaises(publish.AuditPrivilegeDenied):
                publish.read_layer_validations(
                    _publish_policy(),
                    "sentinel-secret",
                    run_timestamp=_RUN_TS,
                    manifest_digest="a" * 64,
                    target_tables=("vmadd_address",),
                )


def _provenance_fixture(directory: Path, *, order_id: str, message_fingerprint: str, sha256: str):
    """Write a real D-32 provenance sidecar into ``directory`` -- the exact
    on-disk artifact ``assemble_summary`` re-reads -- so the offline
    ``SummaryAssemblyTest`` exercises the real ``read_provenance_sidecar``
    path, never a mocked stand-in (differential-oracle-testing: a hand-rolled
    fixture that never touches the real reader would share any blind spot
    the reader itself has)."""

    artifact_path = directory / f"Order_{order_id}.zip"
    artifact_path.write_bytes(b"not a real archive -- only the sidecar is read")
    download.write_provenance_sidecar(
        artifact_path,
        order_id=order_id,
        message_fingerprint=message_fingerprint,
        sha256=sha256,
        byte_count=1234,
    )
    return artifact_path


class SummaryAssemblyTest(unittest.TestCase):
    """No database. ``assemble_summary`` links all six EVID-01 facts from
    fixture inputs -- a real provenance sidecar on disk, a stand-in manifest,
    fixture ``LayerValidationRecord`` rows, and fixture publish/reader
    results -- and rejects a malformed input before returning anything."""

    _ORDER_ID = "ORD123"
    _MESSAGE_FINGERPRINT = "a" * 16
    _ARTIFACT_SHA256 = "b" * 64
    _MANIFEST_DIGEST = "c" * 64

    def _validation_record(self, **overrides) -> publish.LayerValidationRecord:
        kwargs = dict(
            target_table="vmadd_address",
            verdict="pass",
            spatial=True,
            row_count=4222035,
            srid=7899,
            geometry_type="POINT",
            repaired_count=12,
        )
        kwargs.update(overrides)
        return publish.LayerValidationRecord(**kwargs)

    def _publication_result(self, **overrides) -> publish.PromotionResult:
        kwargs = dict(
            server_version="PostgreSQL 18.6 (fake build)",
            published_tables=("vmadd_address",),
        )
        kwargs.update(overrides)
        return publish.PromotionResult(**kwargs)

    def _reader_verification(self, **overrides) -> publish.ReaderVerification:
        kwargs = dict(
            tables_discovered=("vmadd_address",),
            spatial_query_row_count=2,
            write_denied=True,
        )
        kwargs.update(overrides)
        return publish.ReaderVerification(**kwargs)

    def _assemble(self, tmp_dir: str, **overrides):
        artifact_path = _provenance_fixture(
            Path(tmp_dir),
            order_id=self._ORDER_ID,
            message_fingerprint=self._MESSAGE_FINGERPRINT,
            sha256=self._ARTIFACT_SHA256,
        )
        kwargs = dict(
            order_id=self._ORDER_ID,
            artifact_path=artifact_path,
            manifest=_one_layer_manifest(),
            manifest_digest=self._MANIFEST_DIGEST,
            validation_rows=(self._validation_record(),),
            publication_result=self._publication_result(),
            reader_verification=self._reader_verification(),
        )
        kwargs.update(overrides)
        return publish.assemble_summary(**kwargs)

    def test_links_all_six_evid_01_facts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            summary = self._assemble(tmp_dir)
        self.assertEqual(self._ORDER_ID, summary["order_id"])
        self.assertEqual(self._MESSAGE_FINGERPRINT, summary["message_fingerprint"])
        self.assertEqual(self._ARTIFACT_SHA256, summary["artifact_sha256"])
        self.assertEqual(self._MANIFEST_DIGEST, summary["manifest_sha256"])
        self.assertEqual(1, summary["layer_count"])
        self.assertEqual(["vmadd_address"], summary["published_tables"])
        self.assertEqual(1, len(summary["staging_validation"]))
        self.assertEqual("vmadd_address", summary["staging_validation"][0]["target_table"])
        self.assertEqual(4222035, summary["staging_validation"][0]["row_count"])
        self.assertEqual(["vmadd_address"], summary["reader"]["tables_discovered"])
        self.assertEqual(2, summary["reader"]["spatial_query_row_count"])
        self.assertTrue(summary["reader"]["write_denied"])

    def test_non_spatial_layer_reports_not_applicable_geometry_fields(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            summary = self._assemble(
                tmp_dir,
                manifest=_one_layer_manifest("vmadd_lookup"),
                validation_rows=(
                    self._validation_record(
                        target_table="vmadd_lookup",
                        spatial=False,
                        srid=None,
                        geometry_type=None,
                        repaired_count=None,
                    ),
                ),
                publication_result=self._publication_result(
                    published_tables=("vmadd_lookup",)
                ),
                reader_verification=self._reader_verification(
                    tables_discovered=("vmadd_lookup",)
                ),
            )
        record = summary["staging_validation"][0]
        self.assertFalse(record["spatial"])
        self.assertEqual(publish.evidence.NOT_APPLICABLE, record["srid"])
        self.assertEqual(publish.evidence.NOT_APPLICABLE, record["geometry_type"])
        self.assertEqual(publish.evidence.NOT_APPLICABLE, record["repaired_count"])

    def test_no_raw_message_id_path_dsn_or_password_in_summary(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            summary = self._assemble(tmp_dir)
        rendered = json.dumps(summary)
        for forbidden in (
            "sentinel-secret",
            str(Path(tmp_dir)),
            "graph_message_id",
            "password",
            "dsn",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_missing_validation_row_for_a_manifest_layer_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError):
                self._assemble(tmp_dir, validation_rows=())

    def test_non_pass_verdict_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError):
                self._assemble(
                    tmp_dir,
                    validation_rows=(self._validation_record(verdict="fail"),),
                )

    def test_unsafe_target_table_in_published_tables_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError):
                self._assemble(
                    tmp_dir,
                    publication_result=self._publication_result(
                        published_tables=("Robert'); DROP TABLE x;--",)
                    ),
                )

    def test_summary_is_the_publication_event_source_of_truth(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            summary = self._assemble(tmp_dir)
        event = publish.summary_to_publication_event(summary)
        self.assertEqual("publication_summary", event["event"])
        self.assertEqual(summary["order_id"], event["order_id"])
        self.assertEqual(summary["message_fingerprint"], event["message_fingerprint"])
        self.assertEqual(summary["published_tables"], event["published_tables"])


class WriteSummaryTest(unittest.TestCase):
    """No database. ``write_summary`` writes canonical, sorted-key UTF-8 JSON
    into the run directory."""

    def test_writes_canonical_json_into_the_run_directory(self):
        summary = {"b": 1, "a": 2}
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = publish.write_summary(Path(tmp_dir), summary)
            self.assertEqual(Path(tmp_dir) / "summary.json", path)
            text = path.read_text(encoding="utf-8")
        self.assertEqual('{"a":2,"b":1}\n', text)


class _LivePublishMixin:
    """Skips -- never fails -- unless both a live loader DSN and a superuser
    DSN are present and reachable. Real promotion fixtures (a throwaway audit
    row, a reader grant target, a staged fixture table) need superuser rights
    to set up, so a missing superuser DSN skips exactly as a missing loader DSN
    does. No test using this mixin may require a reachable server to pass."""

    _DSN_ENV_VAR = "VICMAP_TEST_POSTGRES_DSN"
    _SUPERUSER_DSN_ENV_VAR = "VICMAP_TEST_POSTGRES_SUPERUSER_DSN"
    _CONNECT_TIMEOUT_SECONDS = 2

    def _require_live(self):
        try:
            import psycopg  # noqa: F401 -- presence probe only
        except ImportError:
            self.skipTest("no psycopg installed -- live publish check skipped")
        if not os.environ.get(self._DSN_ENV_VAR):
            self.skipTest(
                f"{self._DSN_ENV_VAR} unset -- live publish check skipped, not failed"
            )
        if not os.environ.get(self._SUPERUSER_DSN_ENV_VAR):
            self.skipTest(
                f"{self._SUPERUSER_DSN_ENV_VAR} unset -- live publish fixture "
                "setup needs superuser rights; skipped, not failed"
            )

    def _policy_from_dsn(self) -> publish.PublishPolicy:
        from psycopg.conninfo import conninfo_to_dict

        parsed = conninfo_to_dict(os.environ[self._DSN_ENV_VAR])
        return _publish_policy(
            host=str(parsed.get("host") or "127.0.0.1"),
            port=int(parsed.get("port") or 5432),
            dbname=str(parsed.get("dbname") or "vicmap"),
            user=str(parsed.get("user") or "vicmap_loader"),
            connect_timeout_seconds=self._CONNECT_TIMEOUT_SECONDS,
        )

    def _superuser_params(self) -> dict:
        """host/port/dbname/user/password parsed from the superuser DSN. The
        live promotion and reader connections both target this exact database,
        so the throwaway fixtures created on the superuser connection are the
        ones the code under test actually operates on. Only ever called after
        ``_require_live`` has proven both DSNs are set."""

        from psycopg.conninfo import conninfo_to_dict

        parsed = conninfo_to_dict(os.environ[self._SUPERUSER_DSN_ENV_VAR])
        return {
            "host": str(parsed.get("host") or "127.0.0.1"),
            "port": int(parsed.get("port") or 5432),
            "dbname": str(parsed.get("dbname") or "vicmap"),
            "user": str(parsed.get("user") or "postgres"),
            "password": str(parsed.get("password") or ""),
        }

    def _open_superuser(self):
        """Open an autocommit superuser connection for fixture setup, or skip
        (never fail) if it is unreachable. Mirrors ``AuditValidationRecordTest``
        in ``tests/test_staging.py``."""

        import psycopg

        try:
            connection = psycopg.connect(
                os.environ[self._SUPERUSER_DSN_ENV_VAR],
                connect_timeout=self._CONNECT_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 -- any connect failure just skips
            self.skipTest(
                "no reachable PostgreSQL superuser connection for live publish "
                f"fixture: {exc}"
            )
        connection.autocommit = True
        return connection

    # Three points inside Victoria's WGS84 extent (the envelope
    # verify_reader_access queries) and one far outside it (Perth), so the
    # spatial query's row count proves the envelope actually filters.
    _VICTORIA_POINTS = ((145.0, -37.0), (144.96, -37.81), (147.0, -36.5))
    _OUTSIDE_POINT = (115.86, -31.95)

    def _ensure_audit_table(self, cursor, created):
        """Create ``vicmap_audit.staging_validation`` only if it is absent,
        recording what was created so cleanup drops only that. Mirrors
        ``AuditValidationRecordTest``'s provision-if-missing shape."""

        cursor.execute("SELECT to_regnamespace('vicmap_audit')")
        (schema_oid,) = cursor.fetchone()
        if schema_oid is None:
            cursor.execute("CREATE SCHEMA vicmap_audit")
            created["audit_schema"] = True
        cursor.execute("SELECT to_regclass('vicmap_audit.staging_validation')")
        (table_oid,) = cursor.fetchone()
        if table_oid is None:
            cursor.execute(
                "CREATE TABLE vicmap_audit.staging_validation ("
                "run_ts text NOT NULL, manifest_digest text NOT NULL, "
                "target_table text NOT NULL, staging_table text NOT NULL, "
                "verdict text NOT NULL, spatial boolean NOT NULL, "
                "row_count bigint NOT NULL, srid integer, geometry_type text, "
                "repaired_count bigint, "
                "recorded_at timestamptz NOT NULL DEFAULT now(), "
                "PRIMARY KEY (run_ts, manifest_digest, target_table))"
            )
            created["audit_table"] = True

    def _register_fixture_cleanup(
        self, connection, *, schemas=(), roles=(), audit_keys=(), created=None
    ):
        """Drop exactly the throwaway objects a live test made: its audit rows
        (by ``(run_ts, manifest_digest)`` only, never a real run's), its
        schemas, and its roles -- ``DROP OWNED BY`` first so a role's grants on
        the shared ``vicmap_audit`` table never block ``DROP ROLE`` -- then the
        audit table/schema only if this test created them. Also run once
        immediately, so leftovers from a crashed earlier run with the same pid
        never make fixture setup fail."""

        sql = publish.sql
        created = created if created is not None else {}

        def _cleanup():
            with connection.cursor() as cur:
                cur.execute("SELECT to_regclass('vicmap_audit.staging_validation')")
                (audit_oid,) = cur.fetchone()
                if audit_oid is not None:
                    for run_ts, digest in audit_keys:
                        cur.execute(
                            "DELETE FROM vicmap_audit.staging_validation "
                            "WHERE run_ts = %s AND manifest_digest = %s",
                            (run_ts, digest),
                        )
                for schema in schemas:
                    cur.execute(
                        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                            sql.Identifier(schema)
                        )
                    )
                for role in roles:
                    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
                    if cur.fetchone() is not None:
                        cur.execute(
                            sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role))
                        )
                        cur.execute(
                            sql.SQL("DROP ROLE {}").format(sql.Identifier(role))
                        )
                if created.get("audit_table"):
                    cur.execute("DROP TABLE IF EXISTS vicmap_audit.staging_validation")
                if created.get("audit_schema"):
                    cur.execute("DROP SCHEMA IF EXISTS vicmap_audit")

        _cleanup()
        self.addCleanup(_cleanup)

    def _create_point_table(self, cursor, schema, table, *, gist_index, points):
        """A ``(gid bigint PRIMARY KEY, geom geometry(Point, 7899))`` table
        with a GiST index -- the shape staging produces and
        ``_promote_layer``'s catalog-driven renames and ``verify_reader_access``'s
        ``gid``/``geom`` queries expect -- holding one row per WGS84 point."""

        sql = publish.sql
        cursor.execute(
            sql.SQL(
                "CREATE TABLE {} (gid bigint PRIMARY KEY, geom geometry(Point, 7899))"
            ).format(sql.Identifier(schema, table))
        )
        cursor.execute(
            sql.SQL("CREATE INDEX {} ON {} USING gist (geom)").format(
                sql.Identifier(gist_index), sql.Identifier(schema, table)
            )
        )
        for gid, (lon, lat) in enumerate(points, start=1):
            cursor.execute(
                sql.SQL(
                    "INSERT INTO {} (gid, geom) VALUES (%s, "
                    "ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 7899))"
                ).format(sql.Identifier(schema, table)),
                (gid, lon, lat),
            )

    def _insert_pass_row(self, cursor, *, run_ts, digest, target, row_count):
        """One D-68 PASS gate row carrying the spatial facts
        ``assemble_summary`` requires of a spatial layer."""

        cursor.execute(
            "INSERT INTO vicmap_audit.staging_validation "
            "(run_ts, manifest_digest, target_table, staging_table, verdict, "
            "spatial, row_count, srid, geometry_type, repaired_count) "
            "VALUES (%s, %s, %s, %s, 'pass', true, %s, 7899, 'POINT', 0)",
            (
                run_ts,
                digest,
                target,
                staging.staging_table_name(target, run_ts),
                row_count,
            ),
        )

    def _superuser_loader_policy(self, *, stg_schema, pub_schema, reader_role):
        """A policy whose loader is the superuser itself -- as
        ``LivePromotionRollbackTest`` does -- so fixtures need no ownership
        transfers. The reader is always a distinct throwaway role."""

        su = self._superuser_params()
        return _publish_policy(
            host=su["host"],
            port=su["port"],
            dbname=su["dbname"],
            user=su["user"],
            staging_schema=stg_schema,
            publish_schema=pub_schema,
            reader_user=reader_role,
            target_srid=7899,
            connect_timeout_seconds=self._CONNECT_TIMEOUT_SECONDS,
        )

    def _scalar(self, connection, query, params=()):
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            (value,) = cursor.fetchone()
        return value


class LivePromoteOneLayerTest(_LivePublishMixin, unittest.TestCase):
    """Skips without live DSNs. Stages a tiny fixture table plus a PASS audit
    row over an existing published table, promotes it, and asserts the
    committed post-state: ``{publish}.{target}`` is the staged table (the
    prior one replaced), the staging table is gone, the PK and geometry index
    carry canonical names, and the reader role holds SELECT but not INSERT
    (PUB-01/PUB-04/D-67/D-71/D-73)."""

    _RUN_TS = "20260928t000001z"
    _DIGEST = "e" * 64

    def test_single_layer_promotes_into_publish_schema(self):
        self._require_live()
        connection = self._open_superuser()
        self.addCleanup(connection.close)
        sql = publish.sql

        pid = os.getpid()
        pub_schema = f"livetest_p1pub_{pid}"
        stg_schema = f"livetest_p1stg_{pid}"
        reader_role = f"livetest_p1rdr_{pid}"
        target = f"livetest_p1_{pid}"
        staging_table = staging.staging_table_name(target, self._RUN_TS)

        created = {"audit_schema": False, "audit_table": False}
        self._register_fixture_cleanup(
            connection,
            schemas=(pub_schema, stg_schema),
            roles=(reader_role,),
            audit_keys=((self._RUN_TS, self._DIGEST),),
            created=created,
        )

        with connection.cursor() as cursor:
            for schema in (pub_schema, stg_schema):
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema)
                    )
                )
                cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cursor.execute(
                sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(reader_role))
            )
            # The prior published table the promotion must replace (D-71).
            cursor.execute(
                sql.SQL("CREATE TABLE {} (gid bigint, note text)").format(
                    sql.Identifier(pub_schema, target)
                )
            )
            cursor.execute(
                sql.SQL("INSERT INTO {} VALUES (999, 'prior-marker')").format(
                    sql.Identifier(pub_schema, target)
                )
            )
            self._create_point_table(
                cursor,
                stg_schema,
                staging_table,
                gist_index=f"livetest_p1_gix_{pid}",
                points=self._VICTORIA_POINTS,
            )
            self._ensure_audit_table(cursor, created)
            self._insert_pass_row(
                cursor,
                run_ts=self._RUN_TS,
                digest=self._DIGEST,
                target=target,
                row_count=len(self._VICTORIA_POINTS),
            )

        policy = self._superuser_loader_policy(
            stg_schema=stg_schema, pub_schema=pub_schema, reader_role=reader_role
        )
        result = publish.promote_order(
            _one_layer_manifest(target),
            policy,
            self._superuser_params()["password"],
            run_timestamp=self._RUN_TS,
            manifest_digest=self._DIGEST,
        )

        self.assertEqual((target,), result.published_tables)
        self.assertTrue(result.server_version.startswith("PostgreSQL"))

        qualified = f"{pub_schema}.{target}"
        # The staged rows replaced the prior table: no marker row survives.
        self.assertEqual(
            len(self._VICTORIA_POINTS),
            self._scalar(
                connection,
                sql.SQL("SELECT count(*) FROM {}").format(
                    sql.Identifier(pub_schema, target)
                ),
            ),
        )
        self.assertEqual(
            0,
            self._scalar(
                connection,
                sql.SQL("SELECT count(*) FROM {} WHERE gid = 999").format(
                    sql.Identifier(pub_schema, target)
                ),
            ),
        )
        # The staging table moved; nothing is left behind in staging.
        self.assertIsNone(
            self._scalar(
                connection, "SELECT to_regclass(%s)", (f"{stg_schema}.{staging_table}",)
            )
        )
        # D-67 canonical names, read back from the catalog after commit.
        self.assertEqual(
            1,
            self._scalar(
                connection,
                "SELECT count(*) FROM pg_indexes "
                "WHERE schemaname = %s AND tablename = %s AND indexname = %s",
                (pub_schema, target, f"{target}_geom_idx"),
            ),
        )
        self.assertEqual(
            1,
            self._scalar(
                connection,
                "SELECT count(*) FROM pg_constraint "
                "WHERE conrelid = to_regclass(%s) AND contype = 'p' AND conname = %s",
                (qualified, f"{target}_pkey"),
            ),
        )
        # D-73: SELECT granted in the same transaction; no write privilege.
        self.assertTrue(
            self._scalar(
                connection,
                "SELECT has_table_privilege(%s, %s, 'SELECT')",
                (reader_role, qualified),
            )
        )
        self.assertFalse(
            self._scalar(
                connection,
                "SELECT has_table_privilege(%s, %s, 'INSERT')",
                (reader_role, qualified),
            )
        )


class LiveMultiLayerPromotionTest(_LivePublishMixin, unittest.TestCase):
    """Skips without live DSNs. All layers of a multi-layer order become
    visible together in one committed transaction; no session ever sees a
    partial order (PUB-02). The single-transaction proof is read from the
    catalog itself: every promoted table's ``pg_class`` row was last written
    by the same transaction id (``xmin``)."""

    _RUN_TS = "20260928t000002z"
    _DIGEST = "f" * 64

    def test_all_layers_commit_together(self):
        self._require_live()
        connection = self._open_superuser()
        self.addCleanup(connection.close)
        sql = publish.sql

        pid = os.getpid()
        pub_schema = f"livetest_mlpub_{pid}"
        stg_schema = f"livetest_mlstg_{pid}"
        reader_role = f"livetest_mlrdr_{pid}"
        targets = tuple(f"livetest_ml{i}_{pid}" for i in range(3))

        created = {"audit_schema": False, "audit_table": False}
        self._register_fixture_cleanup(
            connection,
            schemas=(pub_schema, stg_schema),
            roles=(reader_role,),
            audit_keys=((self._RUN_TS, self._DIGEST),),
            created=created,
        )

        with connection.cursor() as cursor:
            for schema in (pub_schema, stg_schema):
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema)
                    )
                )
                cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cursor.execute(
                sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(reader_role))
            )
            self._ensure_audit_table(cursor, created)
            for i, target in enumerate(targets):
                self._create_point_table(
                    cursor,
                    stg_schema,
                    staging.staging_table_name(target, self._RUN_TS),
                    gist_index=f"livetest_ml{i}_gix_{pid}",
                    points=self._VICTORIA_POINTS[: i + 1],
                )
                self._insert_pass_row(
                    cursor,
                    run_ts=self._RUN_TS,
                    digest=self._DIGEST,
                    target=target,
                    row_count=i + 1,
                )

        manifest = types.SimpleNamespace(
            layers=tuple(types.SimpleNamespace(target_table=t) for t in targets)
        )
        policy = self._superuser_loader_policy(
            stg_schema=stg_schema, pub_schema=pub_schema, reader_role=reader_role
        )
        result = publish.promote_order(
            manifest,
            policy,
            self._superuser_params()["password"],
            run_timestamp=self._RUN_TS,
            manifest_digest=self._DIGEST,
        )

        self.assertEqual(targets, result.published_tables)
        xmins = set()
        for i, target in enumerate(targets):
            self.assertEqual(
                i + 1,
                self._scalar(
                    connection,
                    sql.SQL("SELECT count(*) FROM {}").format(
                        sql.Identifier(pub_schema, target)
                    ),
                ),
            )
            self.assertIsNone(
                self._scalar(
                    connection,
                    "SELECT to_regclass(%s)",
                    (f"{stg_schema}.{staging.staging_table_name(target, self._RUN_TS)}",),
                )
            )
            xmins.add(
                self._scalar(
                    connection,
                    "SELECT xmin::text FROM pg_class WHERE oid = to_regclass(%s)",
                    (f"{pub_schema}.{target}",),
                )
            )
        # PUB-02: one transaction made every layer visible at once.
        self.assertEqual(1, len(xmins), xmins)


class LivePromotionRollbackTest(_LivePublishMixin, unittest.TestCase):
    """Skips without live DSNs. An induced failure on a later layer rolls the
    whole transaction back: no layer is promoted and every prior ``vicmap.*``
    table -- including any dropped earlier in the same transaction -- remains
    exactly as it was (PUB-03)."""

    _READER_ROLE_PREFIX = "livetest_rbrdr_"
    _RUN_TS = "20260925t000000z"
    _DIGEST = "d" * 64

    def test_induced_failure_preserves_every_prior_table(self):
        self._require_live()
        connection = self._open_superuser()
        self.addCleanup(connection.close)
        su = self._superuser_params()
        sql = publish.sql

        pid = os.getpid()
        pub_schema = f"livetest_rbpub_{pid}"
        stg_schema = f"livetest_rbstg_{pid}"
        reader_role = f"{self._READER_ROLE_PREFIX}{pid}"
        target_a = f"livetest_a_{pid}"
        target_b = f"livetest_b_{pid}"
        staging_a = staging.staging_table_name(target_a, self._RUN_TS)
        gist_index = f"livetest_a_geom_gix_{pid}"
        # staging_b is deliberately never created: its absence is the induced
        # mid-transaction failure on the second layer (PUB-03).

        created = {"audit_schema": False, "audit_table": False}

        def _cleanup():
            with connection.cursor() as cur:
                cur.execute("SELECT to_regclass('vicmap_audit.staging_validation')")
                (audit_oid,) = cur.fetchone()
                if audit_oid is not None:
                    cur.execute(
                        "DELETE FROM vicmap_audit.staging_validation WHERE run_ts = %s",
                        (self._RUN_TS,),
                    )
                for schema in (pub_schema, stg_schema):
                    cur.execute(
                        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                            sql.Identifier(schema)
                        )
                    )
                cur.execute(
                    sql.SQL("DROP ROLE IF EXISTS {}").format(
                        sql.Identifier(reader_role)
                    )
                )
                if created["audit_table"]:
                    cur.execute("DROP TABLE IF EXISTS vicmap_audit.staging_validation")
                if created["audit_schema"]:
                    cur.execute("DROP SCHEMA IF EXISTS vicmap_audit")

        self.addCleanup(_cleanup)

        with connection.cursor() as cursor:
            # Fresh throwaway schemas + the reader role _promote_layer grants to.
            for schema in (pub_schema, stg_schema):
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema)
                    )
                )
                cursor.execute(
                    sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
                )
            cursor.execute(
                sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(reader_role))
            )
            cursor.execute(
                sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(reader_role))
            )

            # Prior published table for layer A, with a marker row that must
            # survive the rollback exactly as it was (PUB-03).
            cursor.execute(
                sql.SQL("CREATE TABLE {} (gid bigint, note text)").format(
                    sql.Identifier(pub_schema, target_a)
                )
            )
            cursor.execute(
                sql.SQL("INSERT INTO {} (gid, note) VALUES (999, 'prior-marker')").format(
                    sql.Identifier(pub_schema, target_a)
                )
            )

            # Staging table for layer A: a PK and a GiST geometry index for
            # _promote_layer's catalog-driven canonical renames to find.
            cursor.execute(
                sql.SQL(
                    "CREATE TABLE {} (gid bigint PRIMARY KEY, "
                    "geom geometry(Point, 7899))"
                ).format(sql.Identifier(stg_schema, staging_a))
            )
            cursor.execute(
                sql.SQL("CREATE INDEX {} ON {} USING gist (geom)").format(
                    sql.Identifier(gist_index),
                    sql.Identifier(stg_schema, staging_a),
                )
            )
            cursor.execute(
                sql.SQL(
                    "INSERT INTO {} (gid, geom) VALUES (1, "
                    "ST_Transform(ST_SetSRID(ST_MakePoint(145.0, -37.0), 4326), 7899))"
                ).format(sql.Identifier(stg_schema, staging_a))
            )

            # D-68 gate rows: both layers PASS, so promotion is gated in and the
            # failure is the induced DDL error on layer B, not a missing PASS row.
            self._ensure_audit_table(cursor, created)
            for target in (target_a, target_b):
                cursor.execute(
                    "INSERT INTO vicmap_audit.staging_validation "
                    "(run_ts, manifest_digest, target_table, staging_table, "
                    "verdict, spatial, row_count) "
                    "VALUES (%s, %s, %s, %s, 'pass', true, 1)",
                    (
                        self._RUN_TS,
                        self._DIGEST,
                        target,
                        staging.staging_table_name(target, self._RUN_TS),
                    ),
                )

        manifest = types.SimpleNamespace(
            layers=(
                types.SimpleNamespace(target_table=target_a),
                types.SimpleNamespace(target_table=target_b),
            )
        )
        policy = _publish_policy(
            host=su["host"],
            port=su["port"],
            dbname=su["dbname"],
            user=su["user"],
            staging_schema=stg_schema,
            publish_schema=pub_schema,
            reader_user=reader_role,
            target_srid=7899,
            connect_timeout_seconds=self._CONNECT_TIMEOUT_SECONDS,
        )

        with self.assertRaises(publish.PromotionFailed):
            publish.promote_order(
                manifest,
                policy,
                su["password"],
                run_timestamp=self._RUN_TS,
                manifest_digest=self._DIGEST,
            )

        # PUB-03 invariant: the whole transaction rolled back.
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT count(*) FROM {} WHERE gid = 999").format(
                    sql.Identifier(pub_schema, target_a)
                )
            )
            (marker_count,) = cursor.fetchone()
            cursor.execute("SELECT to_regclass(%s)", (f"{pub_schema}.{target_b}",))
            (promoted_b,) = cursor.fetchone()
            cursor.execute("SELECT to_regclass(%s)", (f"{stg_schema}.{staging_a}",))
            (staging_a_regclass,) = cursor.fetchone()

        # Prior published table and its exact marker row are untouched...
        self.assertEqual(1, marker_count)
        # ...no layer was partially published...
        self.assertIsNone(promoted_b)
        # ...and layer A's staging table rolled back to the staging schema.
        self.assertIsNotNone(staging_a_regclass)


class LiveReaderVerificationTest(_LivePublishMixin, unittest.TestCase):
    """Skips without live DSNs. From a genuinely separate reader login
    (``policy.reader_user`` + ``VICMAP_READER_PASSWORD``, never ``SET ROLE``
    from the loader): discovers the published tables it can see, runs the
    Victoria-extent GiST-exercising spatial query, and confirms the rows are
    selectable (PUB-04/PUB-05/D-74)."""

    _READER_PASSWORD = "livetest-reader-pw-3a91"

    def test_reader_discovers_and_spatially_queries_published_tables(self):
        self._require_live()
        connection = self._open_superuser()
        self.addCleanup(connection.close)
        sql = publish.sql

        pid = os.getpid()
        pub_schema = f"livetest_rvpub_{pid}"
        # Never created -- PublishPolicy only needs a valid, distinct name.
        stg_schema = f"livetest_rvstg_{pid}"
        reader_role = f"livetest_rvrdr_{pid}"
        target = f"livetest_rv_{pid}"
        hidden = f"livetest_rvhidden_{pid}"

        self._register_fixture_cleanup(
            connection, schemas=(pub_schema,), roles=(reader_role,)
        )

        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(pub_schema)
                )
            )
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(pub_schema)))
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(reader_role), sql.Literal(self._READER_PASSWORD)
                )
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(pub_schema), sql.Identifier(reader_role)
                )
            )
            self._create_point_table(
                cursor,
                pub_schema,
                target,
                gist_index=f"livetest_rv_gix_{pid}",
                points=self._VICTORIA_POINTS + (self._OUTSIDE_POINT,),
            )
            cursor.execute(
                sql.SQL("GRANT SELECT ON {} TO {}").format(
                    sql.Identifier(pub_schema, target), sql.Identifier(reader_role)
                )
            )
            # A sibling table the reader holds no privilege on: discovery via
            # information_schema must not list it (PUB-05's discovery proof is
            # privilege-filtered, not a bare catalog listing).
            cursor.execute(
                sql.SQL("CREATE TABLE {} (gid bigint)").format(
                    sql.Identifier(pub_schema, hidden)
                )
            )

        policy = self._superuser_loader_policy(
            stg_schema=stg_schema, pub_schema=pub_schema, reader_role=reader_role
        )
        verification = publish.verify_reader_access(
            policy,
            reader_password=self._READER_PASSWORD,
            published_tables=(target,),
        )

        self.assertEqual((target,), verification.tables_discovered)
        # Only the in-Victoria rows fall inside the transformed envelope.
        self.assertEqual(len(self._VICTORIA_POINTS), verification.spatial_query_row_count)
        self.assertIs(True, verification.write_denied)


class LiveReaderWriteDenialTest(_LivePublishMixin, unittest.TestCase):
    """Skips without live DSNs. The reader's attempted write is denied by a
    real executed zero-row ``INSERT ... SELECT ... WHERE false`` that raises
    ``InsufficientPrivilege`` (PUB-04's negative half of the access proof).
    The reader holds only the D-72 baseline schema ``USAGE``; its table
    privilege comes solely from ``promote_order``'s own D-73 grant, so this
    proves the grant the promotion actually issues is read-only."""

    _READER_PASSWORD = "livetest-reader-pw-5d0e"
    _RUN_TS = "20260928t000003z"
    _DIGEST = "0" * 64

    def test_insufficient_privilege_path_returns_write_denied_true(self):
        self._require_live()
        connection = self._open_superuser()
        self.addCleanup(connection.close)
        sql = publish.sql

        pid = os.getpid()
        pub_schema = f"livetest_wdpub_{pid}"
        stg_schema = f"livetest_wdstg_{pid}"
        reader_role = f"livetest_wdrdr_{pid}"
        target = f"livetest_wd_{pid}"

        created = {"audit_schema": False, "audit_table": False}
        self._register_fixture_cleanup(
            connection,
            schemas=(pub_schema, stg_schema),
            roles=(reader_role,),
            audit_keys=((self._RUN_TS, self._DIGEST),),
            created=created,
        )

        with connection.cursor() as cursor:
            for schema in (pub_schema, stg_schema):
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema)
                    )
                )
                cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(reader_role), sql.Literal(self._READER_PASSWORD)
                )
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(pub_schema), sql.Identifier(reader_role)
                )
            )
            self._create_point_table(
                cursor,
                stg_schema,
                staging.staging_table_name(target, self._RUN_TS),
                gist_index=f"livetest_wd_gix_{pid}",
                points=self._VICTORIA_POINTS,
            )
            self._ensure_audit_table(cursor, created)
            self._insert_pass_row(
                cursor,
                run_ts=self._RUN_TS,
                digest=self._DIGEST,
                target=target,
                row_count=len(self._VICTORIA_POINTS),
            )

        policy = self._superuser_loader_policy(
            stg_schema=stg_schema, pub_schema=pub_schema, reader_role=reader_role
        )
        result = publish.promote_order(
            _one_layer_manifest(target),
            policy,
            self._superuser_params()["password"],
            run_timestamp=self._RUN_TS,
            manifest_digest=self._DIGEST,
        )
        verification = publish.verify_reader_access(
            policy,
            reader_password=self._READER_PASSWORD,
            published_tables=result.published_tables,
        )

        self.assertIs(True, verification.write_denied)
        self.assertEqual((target,), verification.tables_discovered)
        # The denied probe left the published rows exactly as promoted.
        self.assertEqual(
            len(self._VICTORIA_POINTS),
            self._scalar(
                connection,
                sql.SQL("SELECT count(*) FROM {}").format(
                    sql.Identifier(pub_schema, target)
                ),
            ),
        )


class LiveReaderWriteNotDeniedTest(_LivePublishMixin, unittest.TestCase):
    """Skips without live DSNs. A reader-equivalent role deliberately granted
    INSERT on the fixture table must trip ``ReaderWriteNotDenied`` -- proving
    the check actually detects a broken grant, not just the happy path
    (T-04-02, security-critical)."""

    _READER_PASSWORD = "livetest-reader-pw-7c2f"

    def test_writable_reader_trips_reader_write_not_denied(self):
        self._require_live()
        connection = self._open_superuser()
        self.addCleanup(connection.close)
        su = self._superuser_params()
        sql = publish.sql

        pid = os.getpid()
        pub_schema = f"livetest_wpub_{pid}"
        # Never created -- PublishPolicy only needs a valid, distinct name.
        stg_schema = f"livetest_wstg_{pid}"
        reader_role = f"livetest_wrdr_{pid}"
        target = f"livetest_wr_{pid}"

        def _cleanup():
            with connection.cursor() as cur:
                cur.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(pub_schema)
                    )
                )
                cur.execute(
                    sql.SQL("DROP ROLE IF EXISTS {}").format(
                        sql.Identifier(reader_role)
                    )
                )

        self.addCleanup(_cleanup)

        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(pub_schema)
                )
            )
            cursor.execute(
                sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(reader_role))
            )
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(pub_schema)))
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(reader_role), sql.Literal(self._READER_PASSWORD)
                )
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(pub_schema), sql.Identifier(reader_role)
                )
            )
            cursor.execute(
                sql.SQL(
                    "CREATE TABLE {} (gid bigint PRIMARY KEY, "
                    "geom geometry(Point, 7899))"
                ).format(sql.Identifier(pub_schema, target))
            )
            cursor.execute(
                sql.SQL(
                    "INSERT INTO {} (gid, geom) VALUES (1, "
                    "ST_Transform(ST_SetSRID(ST_MakePoint(145.0, -37.0), 4326), 7899))"
                ).format(sql.Identifier(pub_schema, target))
            )
            # The broken grant: the reader is deliberately given INSERT as well
            # as the baseline USAGE/SELECT. verify_reader_access must detect it.
            cursor.execute(
                sql.SQL("GRANT SELECT, INSERT ON {} TO {}").format(
                    sql.Identifier(pub_schema, target), sql.Identifier(reader_role)
                )
            )

        policy = _publish_policy(
            host=su["host"],
            port=su["port"],
            dbname=su["dbname"],
            user=su["user"],
            staging_schema=stg_schema,
            publish_schema=pub_schema,
            reader_user=reader_role,
            target_srid=7899,
            connect_timeout_seconds=self._CONNECT_TIMEOUT_SECONDS,
        )

        # The zero-row INSERT probe's ACL check passes for this writable role,
        # so the not-denied branch fires: security-critical trip (T-04-02/CR-01).
        with self.assertRaises(publish.ReaderWriteNotDenied):
            publish.verify_reader_access(
                policy,
                reader_password=self._READER_PASSWORD,
                published_tables=(target,),
            )


class LivePublishOrderFullRunTest(_LivePublishMixin, unittest.TestCase):
    """Skips without live DSNs. ``publish_order.py``'s full ordered
    composition (load-config -> gate -> promote -> reader-verify -> summary,
    D-77) exits 0 and writes ``summary.json`` into the run directory against
    a real server. The fixture is a throwaway but complete order: the
    repository's own ``vicmap.toml`` re-pointed at throwaway schemas/roles, a
    real artifact + provenance sidecar, a real ``manifest.json``, a staged
    table owned by a genuine non-superuser loader login, a PASS audit row
    (D-70), and a reader login holding only baseline schema ``USAGE`` (D-72),
    both passwords supplied through the environment exactly as in production
    (D-58/D-74). Asserts the summary's every EVID-01 link fact, the single
    rendered success event, and that no secret or local path leaks."""

    _RUN_DIR_NAME = "20260928T000004Z"
    _FINGERPRINT = "0123456789abcdef"

    def _write_config(self, config_root: Path, *, order_id, loader_role, reader_role,
                      stg_schema, pub_schema) -> Path:
        """The repository's own ``vicmap.toml`` with only the order, database
        identity, and schema/role names swapped for this test's throwaway
        ones -- so the config loaders' full five-section contract is exercised
        exactly as in production. Each substitution must match exactly once,
        so a drifted ``vicmap.toml`` fails loudly instead of silently testing
        the wrong database."""

        su = self._superuser_params()
        host = "127.0.0.1" if su["host"] == "localhost" else su["host"]
        text = (REPO_ROOT / "vicmap.toml").read_text(encoding="utf-8")
        for old, new in (
            ('allowed_order_ids = ["OK0VUZ"]', f'allowed_order_ids = ["{order_id}"]'),
            ('host = "127.0.0.1"', f'host = "{host}"'),
            ("port = 5432", f"port = {su['port']}"),
            ('dbname = "vicmap"', f'dbname = "{su["dbname"]}"'),
            ('user = "vicmap_loader"', f'user = "{loader_role}"'),
            ('staging_schema = "vicmap_staging"', f'staging_schema = "{stg_schema}"'),
            ('publish_schema = "vicmap"', f'publish_schema = "{pub_schema}"'),
            ('reader_user = "vicmap_reader"', f'reader_user = "{reader_role}"'),
        ):
            self.assertEqual(1, text.count(old), f"vicmap.toml drifted: {old!r}")
            text = text.replace(old, new)
        config_path = config_root / "vicmap.toml"
        config_path.write_text(text, encoding="utf-8")
        return config_path

    def _write_run_artifacts(self, config_root: Path, *, order_id, target) -> tuple:
        """A real Phase 1 artifact + provenance sidecar and a real Phase 2
        ``manifest.json`` (+ digest sidecar) under ``config_root``, laid out
        exactly where ``publish_order`` looks for them. Returns
        ``(run_directory, artifact_sha256, manifest_digest)``."""

        artifacts_dir = config_root / "artifacts"
        artifacts_dir.mkdir()
        artifact_path = artifacts_dir / f"Order_{order_id}.zip"
        artifact_bytes = b"livetest artifact bytes\n"
        artifact_path.write_bytes(artifact_bytes)
        artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
        download.write_provenance_sidecar(
            artifact_path,
            order_id=order_id,
            message_fingerprint=self._FINGERPRINT,
            sha256=artifact_sha256,
            byte_count=len(artifact_bytes),
        )

        run_directory = config_root / "runs" / order_id / self._RUN_DIR_NAME
        run_directory.mkdir(parents=True)
        profile = discovery.LayerProfile(
            dataset_relative_path="livetest/LIVETEST.gdb",
            dataset_stem="LIVETEST",
            layer_name="POINTS",
            driver="OpenFileGDB",
            spatial=True,
            geometry_type="Point",
            geometry_column="SHAPE",
            fid_column="OBJECTID",
            feature_count=len(self._VICTORIA_POINTS),
            source_wkt='PROJCRS["GDA2020 / Vicgrid"]',
            epsg=7899,
            extent=(2126780.0, 2259755.0, 2934322.0, 2826389.0),
            fields=(
                discovery.FieldProfile(
                    name="UFI", ogr_type="Integer", width=None, precision=None,
                    nullable=True,
                ),
            ),
        )
        manifest = manifest_module.build_manifest(
            order_id=order_id,
            run_timestamp=self._RUN_DIR_NAME,
            run_directory=run_directory,
            artifact_sha256=artifact_sha256,
            artifact_byte_count=len(artifact_bytes),
            message_fingerprint=self._FINGERPRINT,
            layers=(manifest_module.ManifestLayer(profile=profile, target_table=target),),
            companions=(),
        )
        digest = manifest_module.write_manifest(manifest, run_directory)
        return run_directory, artifact_sha256, digest

    def test_full_run_exits_zero_and_writes_summary_json(self):
        self._require_live()
        connection = self._open_superuser()
        self.addCleanup(connection.close)
        sql = publish.sql

        pid = os.getpid()
        order_id = f"LIVETEST{pid}"
        pub_schema = f"livetest_frpub_{pid}"
        stg_schema = f"livetest_frstg_{pid}"
        # A genuine non-superuser loader login, so the CLI's whole path runs
        # with exactly the privileges D-70/D-72 provisioning grants.
        loader_role = f"livetest_frld_{pid}"
        reader_role = f"livetest_frrd_{pid}"
        target = f"livetest_fr_{pid}"
        loader_password = secrets.token_hex(16)
        reader_password = secrets.token_hex(16)

        config_root = Path(tempfile.mkdtemp(prefix="livetest-publish-order-"))
        self.addCleanup(shutil.rmtree, config_root, ignore_errors=True)
        config_path = self._write_config(
            config_root,
            order_id=order_id,
            loader_role=loader_role,
            reader_role=reader_role,
            stg_schema=stg_schema,
            pub_schema=pub_schema,
        )
        run_directory, artifact_sha256, digest = self._write_run_artifacts(
            config_root, order_id=order_id, target=target
        )

        created = {"audit_schema": False, "audit_table": False}
        self._register_fixture_cleanup(
            connection,
            schemas=(pub_schema, stg_schema),
            roles=(loader_role, reader_role),
            audit_keys=((self._RUN_DIR_NAME, digest),),
            created=created,
        )

        staging_table = staging.staging_table_name(target, self._RUN_DIR_NAME)
        with connection.cursor() as cursor:
            for role, password in (
                (loader_role, loader_password),
                (reader_role, reader_password),
            ):
                cursor.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(password)
                    )
                )
            for schema in (pub_schema, stg_schema):
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema)
                    )
                )
                cursor.execute(
                    sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                        sql.Identifier(schema), sql.Identifier(loader_role)
                    )
                )
            # D-72 baseline: the reader holds schema USAGE only; its table
            # SELECT must come from the promotion's own D-73 grant.
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(pub_schema), sql.Identifier(reader_role)
                )
            )
            self._create_point_table(
                cursor,
                stg_schema,
                staging_table,
                gist_index=f"livetest_fr_gix_{pid}",
                points=self._VICTORIA_POINTS,
            )
            cursor.execute(
                sql.SQL("ALTER TABLE {} OWNER TO {}").format(
                    sql.Identifier(stg_schema, staging_table),
                    sql.Identifier(loader_role),
                )
            )
            # D-70: the loader reads (and in production appends to) the audit
            # table; this test only needs the gate's and summary's reads.
            self._ensure_audit_table(cursor, created)
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA vicmap_audit TO {}").format(
                    sql.Identifier(loader_role)
                )
            )
            cursor.execute(
                sql.SQL("GRANT SELECT ON vicmap_audit.staging_validation TO {}").format(
                    sql.Identifier(loader_role)
                )
            )
            self._insert_pass_row(
                cursor,
                run_ts=self._RUN_DIR_NAME,
                digest=digest,
                target=target,
                row_count=len(self._VICTORIA_POINTS),
            )

        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(
            os.environ,
            {
                staging.PASSWORD_ENV_VAR: loader_password,
                publish.READER_PASSWORD_ENV_VAR: reader_password,
            },
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = publish_order.main(["--config", str(config_path)])

        output = stdout.getvalue() + stderr.getvalue()
        self.assertEqual(0, exit_code, output)

        summary_path = run_directory / "summary.json"
        summary_text = summary_path.read_text(encoding="utf-8")
        summary = json.loads(summary_text)
        self.assertEqual(order_id, summary["order_id"])
        self.assertEqual(self._FINGERPRINT, summary["message_fingerprint"])
        self.assertEqual(artifact_sha256, summary["artifact_sha256"])
        self.assertEqual(digest, summary["manifest_sha256"])
        self.assertEqual(1, summary["layer_count"])
        self.assertEqual([target], summary["published_tables"])
        self.assertEqual(
            [
                {
                    "target_table": target,
                    "spatial": True,
                    "row_count": len(self._VICTORIA_POINTS),
                    "srid": 7899,
                    "geometry_type": "POINT",
                    "repaired_count": 0,
                }
            ],
            summary["staging_validation"],
        )
        self.assertEqual(
            {
                "tables_discovered": [target],
                "tables_discovered_count": 1,
                "spatial_query_row_count": len(self._VICTORIA_POINTS),
                "write_denied": True,
            },
            summary["reader"],
        )

        # Exactly one rendered event: the publication_summary mirror.
        events = [json.loads(line) for line in stdout.getvalue().splitlines() if line]
        self.assertEqual(["publication_summary"], [e.get("event") for e in events])

        # EVID-01 redaction: no secret or local path reaches either output.
        for text in (summary_text, output):
            self.assertNotIn(loader_password, text)
            self.assertNotIn(reader_password, text)
            self.assertNotIn(str(config_root), text)

        # The promotion really committed under the throwaway loader.
        self.assertEqual(
            len(self._VICTORIA_POINTS),
            self._scalar(
                connection,
                sql.SQL("SELECT count(*) FROM {}").format(
                    sql.Identifier(pub_schema, target)
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
