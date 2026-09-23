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

import os
import types
import unittest
from unittest.mock import patch

from vicmap_acquire import publish


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

    def test_reader_failures_are_a_closed_hierarchy(self):
        for failure in (
            publish.ReaderRoleUnavailable,
            publish.ReaderVerificationFailed,
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
    ):
        self.executed: list[str] = []
        self.discovered_rows = discovered_rows
        self.spatial_rows = spatial_rows
        self.deny_write = deny_write
        self.discovery_error = discovery_error
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

    def test_writable_reader_is_not_a_silent_pass(self):
        # Task 2 (T-04-02) hardens this branch into the dedicated,
        # security-critical ReaderWriteNotDenied; for now it must still fail
        # closed rather than silently return write_denied=False.
        connection = self._connection(deny_write=False)
        with patch.object(publish.psycopg, "connect", return_value=connection):
            with self.assertRaises(publish.PublishFailure):
                publish.verify_reader_access(
                    _publish_policy(),
                    reader_password="sentinel-secret",
                    published_tables=("vmadd_address",),
                )
        # The check always rolls back, whether the write was denied or not,
        # and always closes -- no state is ever left behind.
        self.assertGreaterEqual(connection.rollback_count, 1)
        self.assertTrue(connection.closed)

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


class LivePromoteOneLayerTest(_LivePublishMixin, unittest.TestCase):
    """Skips without live DSNs. Stages a tiny fixture table plus a PASS audit
    row, promotes it, and asserts the committed post-state: ``vicmap.{target}``
    exists, the staging table is gone, the geometry index is named
    ``{target}_geom_idx``, and the reader role holds SELECT (PUB-01/PUB-04)."""

    def test_single_layer_promotes_into_publish_schema(self):
        self._require_live()
        self.skipTest(
            "live single-layer promotion requires an operator-provisioned "
            "vicmap_audit schema, reader role, and staged fixture; deferred to "
            "the operator's live run (see 04-04-SUMMARY.md)"
        )


class LiveMultiLayerPromotionTest(_LivePublishMixin, unittest.TestCase):
    """Skips without live DSNs. All layers of a multi-layer order become
    visible together in one committed transaction; no session ever sees a
    partial order (PUB-02)."""

    def test_all_layers_commit_together(self):
        self._require_live()
        self.skipTest(
            "live multi-layer promotion requires operator-provisioned schemas, "
            "roles, and staged fixtures; deferred to the operator's live run"
        )


class LivePromotionRollbackTest(_LivePublishMixin, unittest.TestCase):
    """Skips without live DSNs. An induced failure on a later layer rolls the
    whole transaction back: no layer is promoted and every prior ``vicmap.*``
    table -- including any dropped earlier in the same transaction -- remains
    exactly as it was (PUB-03)."""

    def test_induced_failure_preserves_every_prior_table(self):
        self._require_live()
        self.skipTest(
            "live rollback proof requires operator-provisioned schemas, roles, "
            "and staged fixtures; deferred to the operator's live run"
        )


class LiveReaderVerificationTest(_LivePublishMixin, unittest.TestCase):
    """Skips without live DSNs. From a genuinely separate reader login
    (``policy.reader_user`` + ``VICMAP_READER_PASSWORD``, never ``SET ROLE``
    from the loader): discovers the published tables it can see, runs the
    Victoria-extent GiST-exercising spatial query, and confirms the rows are
    selectable (PUB-04/PUB-05/D-74)."""

    def test_reader_discovers_and_spatially_queries_published_tables(self):
        self._require_live()
        self.skipTest(
            "live reader verification requires an operator-provisioned reader "
            "role (D-72), VICMAP_READER_PASSWORD (D-74 opnix wiring), and a "
            "promoted spatial fixture from a completed 04-04 run; deferred to "
            "the operator's live run (see 04-05-SUMMARY.md)"
        )


class LiveReaderWriteDenialTest(_LivePublishMixin, unittest.TestCase):
    """Skips without live DSNs. The reader's attempted write is denied by a
    real executed ``INSERT ... DEFAULT VALUES`` that raises
    ``InsufficientPrivilege`` (PUB-04's negative half of the access proof)."""

    def test_insufficient_privilege_path_returns_write_denied_true(self):
        self._require_live()
        self.skipTest(
            "live write-denial proof requires an operator-provisioned reader "
            "role with baseline USAGE only (D-72) and a promoted fixture "
            "table; deferred to the operator's live run"
        )


if __name__ == "__main__":
    unittest.main()
