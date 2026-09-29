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

import ast
import contextlib
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import publish_order
from vicmap_acquire import discovery, download, publish, staging
from vicmap_acquire import manifest as manifest_module


REPO_ROOT = Path(__file__).resolve().parent.parent


_RUN_TS = "20260918t041500z"
_STAGING_TABLE = "vmadd_address_20260918t041500z"

# D-82: a fixed UTC published_at for offline marker/resume fixtures -- never
# wall-clock time, so a resumed PromotionResult's timestamp is deterministic.
_FIXED_PUBLISHED_AT = datetime(2026, 9, 24, 7, 9, 27, 495000, tzinfo=timezone.utc)


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
    catalog-discovery/``version()``/marker reads from a fixed fixture, so a
    full ``promote_order``/``promote_or_resume`` runs with no server. Raises
    when a configured substring appears in a statement, to exercise the
    rollback path.

    Dispatch order matters (D-79/D-86): the marker INSERT check must come
    before the generic ``"publication"`` classification-SELECT check, since
    the marker INSERT's own text also selects from ``pg_class``/mentions
    ``publication``.
    """

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
        self._connection.executed_params.append(params)
        if self._connection.fail_on and self._connection.fail_on in text:
            raise RuntimeError("induced driver failure")
        if "staging_validation" in text and self._connection.audit_error is not None:
            raise self._connection.audit_error
        if "version()" in text:
            self._rows = [("PostgreSQL 18.6 (fake build)",)]
        elif "INSERT INTO" in text and "publication" in text:
            self._rows = list(self._connection.marker_rows)
        elif "staging_validation" in text:
            self._rows = list(self._connection.audit_rows)
        elif "publication" in text:
            self._rows = list(self._connection.publication_rows)
        elif "pg_constraint" in text:
            self._rows = list(self._connection.constraint_rows)
        elif "pg_indexes" in text:
            self._rows = list(self._connection.index_rows)
        elif "SELECT t.oid FROM pg_class" in text:
            key = tuple(params) if params else None
            row = self._connection.relation_oids.get(key)
            self._rows = [row] if row is not None else []
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
        publication_rows=(),
        relation_oids=None,
        marker_rows=None,
        fail_on=None,
        audit_error=None,
    ):
        self.executed: list[str] = []
        self.executed_params: list = []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False
        self.constraint_rows = constraint_rows
        self.index_rows = index_rows
        self.audit_rows = audit_rows
        self.publication_rows = publication_rows
        self.relation_oids = relation_oids if relation_oids is not None else {}
        self.marker_rows = (
            marker_rows if marker_rows is not None else [(_FIXED_PUBLISHED_AT,)]
        )
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
        self.assertEqual(publish.PROMOTION_PERFORMED, result.promotion)
        self.assertEqual(_FIXED_PUBLISHED_AT, result.published_at)

    def test_publication_marker_insert_follows_the_grant_with_no_conflict_clause(self):
        # D-79/D-81/D-82: the marker commits atomically with the rename/grant,
        # names pg_class as its OID source, and never soft-swallows a
        # duplicate key (RESEARCH.md anti-pattern -- unlike staging's
        # ON CONFLICT DO NOTHING insert, a repeat here is a classifier bug).
        connection = self._connection()
        self._promote(connection)
        marker_statements = [
            s
            for s in connection.executed
            if "INSERT INTO" in s and '"publication"' in s
        ]
        self.assertEqual(1, len(marker_statements))
        statement = marker_statements[0]
        self.assertIn("FROM pg_class", statement)
        self.assertIn("RETURNING published_at", statement)
        self.assertNotIn("ON CONFLICT", statement)
        grant_index = next(
            i for i, s in enumerate(connection.executed) if s.startswith("GRANT")
        )
        marker_index = connection.executed.index(statement)
        self.assertLess(grant_index, marker_index)

    def test_publication_marker_insert_binds_the_expected_parameters(self):
        connection = self._connection()
        self._promote(connection)
        for statement, params in zip(connection.executed, connection.executed_params):
            if "INSERT INTO" in statement and '"publication"' in statement:
                self.assertEqual(
                    (
                        _RUN_TS,
                        "a" * 64,
                        "vmadd_address",
                        "PostgreSQL 18.6 (fake build)",
                        "vicmap",
                        "vmadd_address",
                    ),
                    tuple(params),
                )
                break
        else:
            self.fail("no publication marker insert was executed")


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

    def test_publication_marker_insert_failure_rolls_back(self):
        gate_conn = _FakeConnection(audit_rows=(("vmadd_address", "pass"),))
        connection = _FakeConnection(
            constraint_rows=(_PK_ROW, _NOT_NULL_ROW),
            index_rows=(_GEOM_INDEX_ROW,),
            fail_on="INSERT INTO",
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
        self.assertEqual(1, connection.commit_count)

    def test_publication_marker_insert_returning_no_row_rolls_back(self):
        # D-82: a marker INSERT ... RETURNING published_at that returns no
        # row is a promotion failure, never a silently-accepted marker.
        gate_conn = _FakeConnection(audit_rows=(("vmadd_address", "pass"),))
        connection = _FakeConnection(
            constraint_rows=(_PK_ROW, _NOT_NULL_ROW),
            index_rows=(_GEOM_INDEX_ROW,),
            marker_rows=[],
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
        self.assertEqual(1, connection.commit_count)


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

    def test_audit_read_failed_code(self):
        self.assertEqual("db_audit_read_failed", publish.AuditReadFailed.code)

    def test_publication_ambiguous_code(self):
        self.assertEqual(
            "pub_generation_ambiguous", publish.PublicationAmbiguous.code
        )

    def test_publication_superseded_code(self):
        self.assertEqual(
            "pub_generation_superseded", publish.PublicationSuperseded.code
        )

    def test_publication_summary_failed_code(self):
        self.assertEqual("pub_summary_failed", publish.PublicationSummaryFailed.code)

    def _all_publish_failure_subclasses(self, base=None):
        base = base if base is not None else publish.PublishFailure
        for subclass in base.__subclasses__():
            yield subclass
            yield from self._all_publish_failure_subclasses(subclass)

    def test_every_publish_failure_code_is_a_registered_reason_code(self):
        reason_values = {reason.value for reason in publish.evidence.ReasonCode}
        subclasses = list(self._all_publish_failure_subclasses())
        self.assertGreater(len(subclasses), 0)
        for failure in subclasses:
            with self.subTest(failure=failure.__name__):
                self.assertIn(failure.code, reason_values)


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


class PromoteOrResumeTest(unittest.TestCase):
    """No database. Covers the D-86 classify-then-branch composition:
    PROMOTE (fresh staging, no marker), RESUME (staging absent, marker
    present, live OID matches -- no promotion connection ever opens),
    PublicationValidationMissing (D-89's gate-first ordering), and
    PublicationAmbiguous/AuditReadFailed for the two read-only failure
    boundaries -- neither of which is ever misreported as
    ``PromotionFailed``."""

    _TARGET = "vmadd_address"
    _DIGEST = "a" * 64

    def _staging_table(self, target=_TARGET):
        return staging.staging_table_name(target, _RUN_TS)

    def _gate_connection(self, target=_TARGET):
        return _FakeConnection(audit_rows=((target, "pass"),))

    def test_freshly_staged_order_promotes(self):
        gate_conn = self._gate_connection()
        classify_conn = _FakeConnection(
            relation_oids={("vicmap_staging", self._staging_table()): (111,)}
        )
        promote_conn = _FakeConnection(
            constraint_rows=(_PK_ROW, _NOT_NULL_ROW), index_rows=(_GEOM_INDEX_ROW,)
        )
        with patch.object(
            publish.psycopg,
            "connect",
            side_effect=[gate_conn, classify_conn, promote_conn],
        ):
            result = publish.promote_or_resume(
                _one_layer_manifest(self._TARGET),
                _publish_policy(),
                "sentinel-secret",
                _RUN_TS,
                self._DIGEST,
            )
        self.assertEqual(publish.PROMOTION_PERFORMED, result.promotion)
        self.assertEqual((self._TARGET,), result.published_tables)
        for statement in classify_conn.executed:
            self.assertNotIn("DROP TABLE", statement)
            self.assertNotIn("ALTER TABLE", statement)
            self.assertNotIn("GRANT", statement)
            self.assertNotIn("INSERT INTO", statement)

    def test_committed_order_resumes_without_a_promotion_connection(self):
        marker_row = (
            self._TARGET,
            222,
            "PostgreSQL 18.6 (fake build)",
            _FIXED_PUBLISHED_AT,
        )
        gate_conn = self._gate_connection()
        classify_conn = _FakeConnection(
            publication_rows=(marker_row,),
            relation_oids={("vicmap", self._TARGET): (222,)},
        )

        def _third_call_fails(*args, **kwargs):
            self.fail("resume must not open a promotion connection")

        with patch.object(
            publish.psycopg,
            "connect",
            side_effect=[gate_conn, classify_conn, _third_call_fails],
        ):
            result = publish.promote_or_resume(
                _one_layer_manifest(self._TARGET),
                _publish_policy(),
                "sentinel-secret",
                _RUN_TS,
                self._DIGEST,
            )
        self.assertEqual(publish.PROMOTION_RESUMED, result.promotion)
        self.assertEqual((self._TARGET,), result.published_tables)
        self.assertEqual("PostgreSQL 18.6 (fake build)", result.server_version)
        self.assertEqual(_FIXED_PUBLISHED_AT, result.published_at)
        for statement in gate_conn.executed + classify_conn.executed:
            self.assertNotIn("DROP TABLE", statement)
            self.assertNotIn("ALTER TABLE", statement)
            self.assertNotIn("GRANT", statement)
            self.assertNotIn("INSERT INTO", statement)

    def test_no_pass_row_raises_before_classification_connects(self):
        gate_conn = _FakeConnection(audit_rows=())
        created: list[int] = []

        def _factory(*args, **kwargs):
            created.append(1)
            return gate_conn

        with patch.object(publish.psycopg, "connect", side_effect=_factory):
            with self.assertRaises(publish.PublicationValidationMissing):
                publish.promote_or_resume(
                    _one_layer_manifest(self._TARGET),
                    _publish_policy(),
                    "sentinel-secret",
                    _RUN_TS,
                    self._DIGEST,
                )
        self.assertEqual(1, len(created))

    def test_staging_absent_with_no_marker_raises_publication_ambiguous(self):
        gate_conn = self._gate_connection()
        classify_conn = _FakeConnection(publication_rows=())
        with patch.object(
            publish.psycopg, "connect", side_effect=[gate_conn, classify_conn]
        ):
            with self.assertRaises(publish.PublicationAmbiguous):
                publish.promote_or_resume(
                    _one_layer_manifest(self._TARGET),
                    _publish_policy(),
                    "sentinel-secret",
                    _RUN_TS,
                    self._DIGEST,
                )
        for statement in classify_conn.executed:
            self.assertNotIn("DROP TABLE", statement)
            self.assertNotIn("ALTER TABLE", statement)

    def test_classification_connect_failure_raises_audit_read_failed_never_promotion_failed(
        self,
    ):
        gate_conn = self._gate_connection()
        with patch.object(
            publish.psycopg,
            "connect",
            side_effect=[gate_conn, publish.psycopg.OperationalError("boom")],
        ):
            with self.assertRaises(publish.AuditReadFailed):
                publish.promote_or_resume(
                    _one_layer_manifest(self._TARGET),
                    _publish_policy(),
                    "sentinel-secret",
                    _RUN_TS,
                    self._DIGEST,
                )

    def test_classification_session_sets_read_only_before_its_reads(self):
        gate_conn = self._gate_connection()
        classify_conn = _FakeConnection(
            relation_oids={("vicmap_staging", self._staging_table()): (111,)}
        )
        promote_conn = _FakeConnection(
            constraint_rows=(_PK_ROW, _NOT_NULL_ROW), index_rows=(_GEOM_INDEX_ROW,)
        )
        with patch.object(
            publish.psycopg,
            "connect",
            side_effect=[gate_conn, classify_conn, promote_conn],
        ):
            publish.promote_or_resume(
                _one_layer_manifest(self._TARGET),
                _publish_policy(),
                "sentinel-secret",
                _RUN_TS,
                self._DIGEST,
            )
        read_only_index = next(
            i
            for i, s in enumerate(classify_conn.executed)
            if "default_transaction_read_only" in s
        )
        first_read_index = next(
            i
            for i, s in enumerate(classify_conn.executed)
            if "SELECT" in s.upper() and "default_transaction" not in s
        )
        self.assertLess(read_only_index, first_read_index)


class SupersededClassificationTest(unittest.TestCase):
    """No database. Covers order_verdict's SUPERSEDED rule and
    classify_publication_state's PublicationSuperseded raise (D-86/D-87),
    proven before any DDL runs."""

    _TARGET = "vmadd_address"
    _TARGET_2 = "vmroad_road"
    _DIGEST = "b" * 64

    def test_order_verdict_superseded_rules(self):
        C = publish.LayerCase
        V = publish.PublicationVerdict
        self.assertIs(V.SUPERSEDED, publish.order_verdict((C.RESUMABLE, C.SUPERSEDED)))
        self.assertIs(V.SUPERSEDED, publish.order_verdict((C.SUPERSEDED,)))

    def _gate_connection(self, targets):
        return _FakeConnection(audit_rows=tuple((t, "pass") for t in targets))

    def _no_third_connection(self):
        def _fail(*args, **kwargs):
            self.fail("a superseded verdict must not open a promotion connection")

        return _fail

    def _assert_no_ddl(self, connection):
        for statement in connection.executed:
            upper = statement.upper()
            self.assertNotIn("DROP", upper)
            self.assertNotIn("ALTER", upper)
            self.assertNotIn("GRANT", upper)
            self.assertNotIn("INSERT", upper)

    def test_two_layer_order_with_one_replaced_oid_raises_superseded(self):
        target_a, target_b = self._TARGET, self._TARGET_2
        marker_rows = (
            (target_a, 111, "PostgreSQL 18.6 (fake build)", _FIXED_PUBLISHED_AT),
            (target_b, 222, "PostgreSQL 18.6 (fake build)", _FIXED_PUBLISHED_AT),
        )
        gate_conn = self._gate_connection((target_a, target_b))
        classify_conn = _FakeConnection(
            publication_rows=marker_rows,
            relation_oids={
                ("vicmap", target_a): (111,),  # unchanged -- resumable
                ("vicmap", target_b): (999,),  # replaced -- oid differs
            },
        )
        manifest = types.SimpleNamespace(
            layers=(
                types.SimpleNamespace(target_table=target_a),
                types.SimpleNamespace(target_table=target_b),
            )
        )
        with patch.object(
            publish.psycopg,
            "connect",
            side_effect=[gate_conn, classify_conn, self._no_third_connection()],
        ):
            with self.assertRaises(publish.PublicationSuperseded):
                publish.promote_or_resume(
                    manifest,
                    _publish_policy(),
                    "sentinel-secret",
                    _RUN_TS,
                    self._DIGEST,
                )
        self._assert_no_ddl(classify_conn)

    def test_one_layer_order_with_missing_live_table_raises_superseded(self):
        target = self._TARGET
        marker_row = (target, 333, "PostgreSQL 18.6 (fake build)", _FIXED_PUBLISHED_AT)
        gate_conn = self._gate_connection((target,))
        classify_conn = _FakeConnection(
            publication_rows=(marker_row,),
            relation_oids={},  # the live table is gone entirely
        )
        with patch.object(
            publish.psycopg,
            "connect",
            side_effect=[gate_conn, classify_conn, self._no_third_connection()],
        ):
            with self.assertRaises(publish.PublicationSuperseded):
                publish.promote_or_resume(
                    _one_layer_manifest(target),
                    _publish_policy(),
                    "sentinel-secret",
                    _RUN_TS,
                    self._DIGEST,
                )
        self._assert_no_ddl(classify_conn)


class LayerClassificationTableTest(unittest.TestCase):
    """No database. Exhaustive ``classify_layer`` table (D-86), including the
    exact-int OID boundary at ``uint32`` max (D-81/D-82; must-have precision
    edge): a recorded OID of 4294967295 matches a live 4294967295 and not
    4294967294."""

    _MAX_UINT32 = 4294967295

    def _record(
        self,
        table_oid,
        *,
        server_version="PostgreSQL 18.6",
        published_at=_FIXED_PUBLISHED_AT,
    ):
        return publish.PublicationRecord(
            target_table="vmadd_address",
            table_oid=table_oid,
            server_version=server_version,
            published_at=published_at,
        )

    def test_classification_table(self):
        C = publish.LayerCase
        cases = (
            ("staging present, no record", 111, None, None, C.STAGED),
            ("staging present, record", 111, self._record(222), None, C.CONFLICTED),
            ("absent, no record", None, None, None, C.UNPROVEN),
            (
                "absent, matching max-uint32 oid",
                None,
                self._record(self._MAX_UINT32),
                self._MAX_UINT32,
                C.RESUMABLE,
            ),
            (
                "absent, off-by-one max-uint32 oid",
                None,
                self._record(self._MAX_UINT32),
                self._MAX_UINT32 - 1,
                C.SUPERSEDED,
            ),
            (
                "absent, record, live missing",
                None,
                self._record(222),
                None,
                C.SUPERSEDED,
            ),
        )
        for label, staging_oid, record, live_oid, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(
                    expected,
                    publish.classify_layer(
                        staging_oid=staging_oid, record=record, live_oid=live_oid
                    ),
                )


class OrderVerdictTableTest(unittest.TestCase):
    """No database. Exhaustive ``order_verdict`` table (D-86/D-87) -- the
    fixed precedence: ``PROMOTE`` only all-``STAGED``, ``RESUME`` only
    all-``RESUMABLE``, ``SUPERSEDED`` only non-empty
    resumable-or-superseded-with-at-least-one-superseded, ``AMBIGUOUS``
    otherwise."""

    def test_verdict_table(self):
        C = publish.LayerCase
        V = publish.PublicationVerdict
        cases = (
            ((), V.AMBIGUOUS),
            ((C.STAGED,), V.PROMOTE),
            ((C.STAGED,) * 3, V.PROMOTE),
            ((C.RESUMABLE,), V.RESUME),
            ((C.RESUMABLE,) * 3, V.RESUME),
            ((C.RESUMABLE, C.RESUMABLE, C.STAGED), V.AMBIGUOUS),
            ((C.STAGED, C.UNPROVEN), V.AMBIGUOUS),
            ((C.SUPERSEDED, C.UNPROVEN), V.AMBIGUOUS),
            ((C.SUPERSEDED, C.STAGED), V.AMBIGUOUS),
            ((C.UNPROVEN,), V.AMBIGUOUS),
            ((C.CONFLICTED,), V.AMBIGUOUS),
            ((C.RESUMABLE, C.CONFLICTED), V.AMBIGUOUS),
            ((C.RESUMABLE, C.RESUMABLE, C.SUPERSEDED), V.SUPERSEDED),
        )
        for cases_tuple, expected in cases:
            with self.subTest(cases=cases_tuple):
                self.assertEqual(expected, publish.order_verdict(cases_tuple))


class ResumeReconstructionTest(unittest.TestCase):
    """No database. ``promotion_result_from_records``' single-promotion
    consistency check (D-81/D-82) and the D-80 subset rule -- rows for a
    target outside ``target_tables`` are ignored, every named target must
    have exactly one row, and every row must agree on ``server_version`` and
    ``published_at`` to the microsecond."""

    _TARGET_A = "vmadd_address"
    _TARGET_B = "vmroad_road"

    def _record(
        self,
        target,
        oid,
        *,
        server_version="PostgreSQL 18.6",
        published_at=_FIXED_PUBLISHED_AT,
    ):
        return publish.PublicationRecord(
            target_table=target,
            table_oid=oid,
            server_version=server_version,
            published_at=published_at,
        )

    def test_consistent_rows_reconstruct_in_target_table_order(self):
        records = (
            self._record(self._TARGET_B, 222),
            self._record(self._TARGET_A, 111),
        )
        result = publish.promotion_result_from_records(
            records, (self._TARGET_A, self._TARGET_B)
        )
        self.assertEqual((self._TARGET_A, self._TARGET_B), result.published_tables)
        self.assertEqual("PostgreSQL 18.6", result.server_version)
        self.assertEqual(_FIXED_PUBLISHED_AT, result.published_at)
        self.assertEqual(publish.PROMOTION_RESUMED, result.promotion)

    def test_differing_server_version_raises_ambiguous(self):
        records = (
            self._record(self._TARGET_A, 111, server_version="PostgreSQL 18.6"),
            self._record(self._TARGET_B, 222, server_version="PostgreSQL 18.5"),
        )
        with self.assertRaises(publish.PublicationAmbiguous):
            publish.promotion_result_from_records(
                records, (self._TARGET_A, self._TARGET_B)
            )

    def test_published_at_disagreeing_by_one_microsecond_raises_ambiguous(self):
        from datetime import timedelta

        other = _FIXED_PUBLISHED_AT + timedelta(microseconds=1)
        records = (
            self._record(self._TARGET_A, 111, published_at=_FIXED_PUBLISHED_AT),
            self._record(self._TARGET_B, 222, published_at=other),
        )
        with self.assertRaises(publish.PublicationAmbiguous):
            publish.promotion_result_from_records(
                records, (self._TARGET_A, self._TARGET_B)
            )

    def test_row_for_target_outside_target_tables_is_ignored(self):
        extraneous = self._record("vmroad_extra", 999, server_version="wrong-version")
        records = (self._record(self._TARGET_A, 111), extraneous)
        result = publish.promotion_result_from_records(records, (self._TARGET_A,))
        self.assertEqual((self._TARGET_A,), result.published_tables)
        self.assertEqual("PostgreSQL 18.6", result.server_version)

    def test_missing_row_for_a_target_raises_ambiguous(self):
        records = (self._record(self._TARGET_A, 111),)
        with self.assertRaises(publish.PublicationAmbiguous):
            publish.promotion_result_from_records(
                records, (self._TARGET_A, self._TARGET_B)
            )


class FailClosedNoDdlTest(unittest.TestCase):
    """No database. Every AMBIGUOUS classification path through
    ``promote_or_resume`` -- unproven, conflicted, mixed staged-and-resumable,
    and an empty target set -- opens exactly the gate and classification
    connections, the classification session sets read-only before its reads,
    and neither connection ever issues DROP/ALTER/GRANT/CREATE/INSERT/
    UPDATE/DELETE."""

    _TARGET = "vmadd_address"
    _TARGET_2 = "vmroad_road"
    _DIGEST = "c" * 64

    _FORBIDDEN = ("DROP", "ALTER", "GRANT", "CREATE", "INSERT", "UPDATE", "DELETE")

    def _run(self, manifest, gate_conn, classify_conn):
        connect_calls: list = []
        connections = [gate_conn, classify_conn]

        def _factory(*args, **kwargs):
            connect_calls.append(1)
            if len(connect_calls) <= len(connections):
                return connections[len(connect_calls) - 1]
            self.fail("must not open a third connection")

        with patch.object(publish.psycopg, "connect", side_effect=_factory):
            with self.assertRaises(publish.PublicationAmbiguous):
                publish.promote_or_resume(
                    manifest,
                    _publish_policy(),
                    "sentinel-secret",
                    _RUN_TS,
                    self._DIGEST,
                )
        self.assertEqual(2, len(connect_calls))

        for connection in connections:
            for statement in connection.executed:
                upper = statement.upper()
                for keyword in self._FORBIDDEN:
                    self.assertNotIn(keyword, upper)
        self.assertTrue(
            any(
                "default_transaction_read_only" in statement
                for statement in classify_conn.executed
            )
        )

    def test_unproven_fails_closed(self):
        gate_conn = _FakeConnection(audit_rows=((self._TARGET, "pass"),))
        classify_conn = _FakeConnection(publication_rows=(), relation_oids={})
        self._run(_one_layer_manifest(self._TARGET), gate_conn, classify_conn)

    def test_conflicted_fails_closed(self):
        staging_table = staging.staging_table_name(self._TARGET, _RUN_TS)
        marker_row = (
            self._TARGET,
            111,
            "PostgreSQL 18.6 (fake build)",
            _FIXED_PUBLISHED_AT,
        )
        gate_conn = _FakeConnection(audit_rows=((self._TARGET, "pass"),))
        classify_conn = _FakeConnection(
            publication_rows=(marker_row,),
            relation_oids={("vicmap_staging", staging_table): (999,)},
        )
        self._run(_one_layer_manifest(self._TARGET), gate_conn, classify_conn)

    def test_mixed_staged_and_resumable_fails_closed(self):
        target_a, target_b = self._TARGET, self._TARGET_2
        staging_table_a = staging.staging_table_name(target_a, _RUN_TS)
        marker_row_b = (
            target_b,
            222,
            "PostgreSQL 18.6 (fake build)",
            _FIXED_PUBLISHED_AT,
        )
        gate_conn = _FakeConnection(
            audit_rows=((target_a, "pass"), (target_b, "pass"))
        )
        classify_conn = _FakeConnection(
            publication_rows=(marker_row_b,),
            relation_oids={
                ("vicmap_staging", staging_table_a): (111,),
                ("vicmap", target_b): (222,),
            },
        )
        manifest = types.SimpleNamespace(
            layers=(
                types.SimpleNamespace(target_table=target_a),
                types.SimpleNamespace(target_table=target_b),
            )
        )
        self._run(manifest, gate_conn, classify_conn)

    def test_empty_target_set_fails_closed(self):
        gate_conn = _FakeConnection()
        classify_conn = _FakeConnection()
        manifest = types.SimpleNamespace(layers=())
        self._run(manifest, gate_conn, classify_conn)


class PublicationMarkerProvenanceTest(unittest.TestCase):
    """No database. Mechanical proof of D-88's "no backfill" rule: parses
    ``publish.py`` with ``ast`` and shows ``_record_publication`` is called
    only from ``_promote_in_transaction``, and that among functions
    referencing ``PUBLICATION_TABLE``, only ``_record_publication`` contains
    an ``INSERT`` string constant -- the pipeline can write a publication
    marker only inside the promotion transaction."""

    def _module_tree(self) -> ast.AST:
        source = Path(publish.__file__).read_text(encoding="utf-8")
        return ast.parse(source, filename=publish.__file__)

    def _function_defs(self, tree: ast.AST) -> list[ast.FunctionDef]:
        return [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]

    def test_record_publication_is_called_only_inside_promote_in_transaction(self):
        tree = self._module_tree()
        callers = []
        for func in self._function_defs(tree):
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "_record_publication"
                ):
                    callers.append(func.name)
        self.assertEqual(["_promote_in_transaction"], callers)

    def test_only_record_publication_contains_insert_among_publication_table_referrers(
        self,
    ):
        tree = self._module_tree()
        referrers_with_insert = []
        for func in self._function_defs(tree):
            references_table = False
            has_insert_constant = False
            for node in ast.walk(func):
                if isinstance(node, ast.Name) and node.id == "PUBLICATION_TABLE":
                    references_table = True
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and "INSERT" in node.value.upper()
                ):
                    has_insert_constant = True
            if references_table and has_insert_constant:
                referrers_with_insert.append(func.name)
        self.assertEqual(["_record_publication"], referrers_with_insert)


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


_PUBLICATION_DDL_PATTERN = re.compile(
    r"CREATE TABLE IF NOT EXISTS vicmap_audit\.publication \(.*?\);", re.DOTALL
)


def _provisioned_publication_ddl() -> str:
    """Read the exact ``CREATE TABLE ... vicmap_audit.publication (...);``
    statement out of the provisioning script, so the live fixture's own DDL
    can never drift from what an operator actually runs by hand (D-78)."""

    text = (REPO_ROOT / "db" / "provision_vicmap_loader.sql").read_text(
        encoding="utf-8"
    )
    match = _PUBLICATION_DDL_PATTERN.search(text)
    if match is None:
        raise AssertionError(
            "db/provision_vicmap_loader.sql has no vicmap_audit.publication "
            "CREATE TABLE statement matching the expected shape"
        )
    return match.group(0)


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
            published_at=_FIXED_PUBLISHED_AT,
            promotion=publish.PROMOTION_PERFORMED,
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

    def test_promotion_field_round_trips_performed_and_resumed(self):
        # D-84: summary.json's new field records whether this run performed
        # or resumed the promotion -- both closed values must round-trip.
        with tempfile.TemporaryDirectory() as tmp_dir:
            performed = self._assemble(
                tmp_dir,
                publication_result=self._publication_result(
                    promotion=publish.PROMOTION_PERFORMED
                ),
            )
        self.assertEqual("performed", performed["promotion"])
        with tempfile.TemporaryDirectory() as tmp_dir:
            resumed = self._assemble(
                tmp_dir,
                publication_result=self._publication_result(
                    promotion=publish.PROMOTION_RESUMED
                ),
            )
        self.assertEqual("resumed", resumed["promotion"])

    def test_invalid_promotion_value_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            publish.PromotionResult(
                server_version="PostgreSQL 18.6 (fake build)",
                published_tables=("vmadd_address",),
                published_at=_FIXED_PUBLISHED_AT,
                promotion="bogus",
            )


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
        """Create ``vicmap_audit.staging_validation`` and
        ``vicmap_audit.publication`` only if absent, recording what was
        created so cleanup drops only that. Mirrors
        ``AuditValidationRecordTest``'s provision-if-missing shape. The
        ``publication`` DDL is read from the provisioning script itself
        (``_provisioned_publication_ddl``) so this fixture can never drift
        from what an operator actually runs by hand (D-78)."""

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
        cursor.execute("SELECT to_regclass('vicmap_audit.publication')")
        (publication_oid,) = cursor.fetchone()
        if publication_oid is None:
            cursor.execute(_provisioned_publication_ddl())
            created["publication_table"] = True

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
                cur.execute("SELECT to_regclass('vicmap_audit.publication')")
                (publication_oid,) = cur.fetchone()
                if publication_oid is not None:
                    for run_ts, digest in audit_keys:
                        cur.execute(
                            "DELETE FROM vicmap_audit.publication "
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
                if created.get("publication_table"):
                    cur.execute("DROP TABLE IF EXISTS vicmap_audit.publication")
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

        created = {"audit_schema": False, "audit_table": False, "publication_table": False}

        def _cleanup():
            with connection.cursor() as cur:
                cur.execute("SELECT to_regclass('vicmap_audit.staging_validation')")
                (audit_oid,) = cur.fetchone()
                if audit_oid is not None:
                    cur.execute(
                        "DELETE FROM vicmap_audit.staging_validation WHERE run_ts = %s",
                        (self._RUN_TS,),
                    )
                cur.execute("SELECT to_regclass('vicmap_audit.publication')")
                (publication_oid,) = cur.fetchone()
                if publication_oid is not None:
                    cur.execute(
                        "DELETE FROM vicmap_audit.publication WHERE run_ts = %s",
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
                if created["publication_table"]:
                    cur.execute("DROP TABLE IF EXISTS vicmap_audit.publication")
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
            cursor.execute(
                "SELECT count(*) FROM vicmap_audit.publication WHERE run_ts = %s",
                (self._RUN_TS,),
            )
            (publication_row_count,) = cursor.fetchone()

        # Prior published table and its exact marker row are untouched...
        self.assertEqual(1, marker_count)
        # ...no layer was partially published...
        self.assertIsNone(promoted_b)
        # ...and layer A's staging table rolled back to the staging schema.
        self.assertIsNotNone(staging_a_regclass)
        # D-79: a rolled-back promotion leaves no publication marker row.
        self.assertEqual(0, publication_row_count)


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


class _LivePublishOrderMixin(_LivePublishMixin):
    """Shared fixture machinery for driving a full ``publish_order.main`` run
    entirely through the real CLI entry point (never through ``publish``'s
    functions directly): the repository's own ``vicmap.toml`` re-pointed at
    throwaway schemas/roles, a real artifact + provenance sidecar, a real
    ``manifest.json``, a staged table owned by a genuine non-superuser
    loader login, a PASS audit row (D-70), a reader login holding only
    baseline schema ``USAGE`` (D-72), and the D-78 ``vicmap_audit.publication``
    grant. Parameterised by ``tag`` (a short per-test label, so sibling live
    classes sharing a pid never collide on schema/role/order names) and
    ``run_dir_name`` (so a full run and a resume re-run each get their own
    run directory)."""

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

    def _write_run_artifacts(
        self, config_root: Path, *, order_id, target, run_dir_name
    ) -> tuple:
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

        run_directory = config_root / "runs" / order_id / run_dir_name
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
            run_timestamp=run_dir_name,
            run_directory=run_directory,
            artifact_sha256=artifact_sha256,
            artifact_byte_count=len(artifact_bytes),
            message_fingerprint=self._FINGERPRINT,
            layers=(manifest_module.ManifestLayer(profile=profile, target_table=target),),
            companions=(),
        )
        digest = manifest_module.write_manifest(manifest, run_directory)
        return run_directory, artifact_sha256, digest

    def _provision_order_fixture(
        self, *, tag: str, run_dir_name: str, staged: bool = True
    ):
        """Provision one throwaway but complete order -- schemas, a genuine
        non-superuser loader + reader login, a staged fixture table, the
        D-70/D-78 audit grants, and the PASS row -- and return everything a
        caller needs to drive ``publish_order.main`` and inspect the result.
        Registers its own cleanup; the superuser connection's close is
        registered here too, so callers never need their own ``addCleanup``.

        ``staged=False`` skips creating the staging table (and its owner
        transfer) while keeping everything else, including the PASS row --
        the fixture-scale shape of D-88's unmarked ``vicmap.vmadd_address``:
        a live published table this run never staged and has no marker for.
        """

        connection = self._open_superuser()
        self.addCleanup(connection.close)
        sql = publish.sql

        pid = os.getpid()
        order_id = f"LIVETEST{tag.upper()}{pid}"
        pub_schema = f"livetest_{tag}pub_{pid}"
        stg_schema = f"livetest_{tag}stg_{pid}"
        # A genuine non-superuser loader login, so the CLI's whole path runs
        # with exactly the privileges D-70/D-72/D-78 provisioning grants.
        loader_role = f"livetest_{tag}ld_{pid}"
        reader_role = f"livetest_{tag}rd_{pid}"
        target = f"livetest_{tag}_{pid}"
        loader_password = secrets.token_hex(16)
        reader_password = secrets.token_hex(16)

        config_root = Path(tempfile.mkdtemp(prefix=f"livetest-publish-order-{tag}-"))
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
            config_root, order_id=order_id, target=target, run_dir_name=run_dir_name
        )

        created = {
            "audit_schema": False,
            "audit_table": False,
            "publication_table": False,
        }
        self._register_fixture_cleanup(
            connection,
            schemas=(pub_schema, stg_schema),
            roles=(loader_role, reader_role),
            audit_keys=((run_dir_name, digest),),
            created=created,
        )

        staging_table = staging.staging_table_name(target, run_dir_name)
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
            if staged:
                self._create_point_table(
                    cursor,
                    stg_schema,
                    staging_table,
                    gist_index=f"livetest_{tag}_gix_{pid}",
                    points=self._VICTORIA_POINTS,
                )
                cursor.execute(
                    sql.SQL("ALTER TABLE {} OWNER TO {}").format(
                        sql.Identifier(stg_schema, staging_table),
                        sql.Identifier(loader_role),
                    )
                )
            # D-70/D-78: the loader reads (and in production appends to) both
            # audit tables; this test only needs the gate's, classifier's,
            # and summary's reads plus the marker write a promotion makes.
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
            cursor.execute(
                sql.SQL(
                    "GRANT SELECT, INSERT ON vicmap_audit.publication TO {}"
                ).format(sql.Identifier(loader_role))
            )
            self._insert_pass_row(
                cursor,
                run_ts=run_dir_name,
                digest=digest,
                target=target,
                row_count=len(self._VICTORIA_POINTS),
            )

        return types.SimpleNamespace(
            connection=connection,
            config_path=config_path,
            run_directory=run_directory,
            digest=digest,
            artifact_sha256=artifact_sha256,
            order_id=order_id,
            loader_password=loader_password,
            reader_password=reader_password,
            pub_schema=pub_schema,
            stg_schema=stg_schema,
            target=target,
            staging_table=staging_table,
        )


class LivePublishOrderFullRunTest(_LivePublishOrderMixin, unittest.TestCase):
    """Skips without live DSNs. ``publish_order.py``'s full ordered
    composition (load-config -> gate -> classify -> promote -> reader-verify
    -> summary, D-77/D-83) exits 0 and writes ``summary.json`` into the run
    directory against a real server. Asserts the summary's every EVID-01
    link fact, the new ``promotion`` field is "performed", the single
    rendered success event, and that no secret or local path leaks."""

    _RUN_DIR_NAME = "20260928T000004Z"

    def test_full_run_exits_zero_and_writes_summary_json(self):
        self._require_live()
        fixture = self._provision_order_fixture(tag="fr", run_dir_name=self._RUN_DIR_NAME)
        sql = publish.sql

        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(
            os.environ,
            {
                staging.PASSWORD_ENV_VAR: fixture.loader_password,
                publish.READER_PASSWORD_ENV_VAR: fixture.reader_password,
            },
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = publish_order.main(["--config", str(fixture.config_path)])

        output = stdout.getvalue() + stderr.getvalue()
        self.assertEqual(0, exit_code, output)

        summary_path = fixture.run_directory / "summary.json"
        summary_text = summary_path.read_text(encoding="utf-8")
        summary = json.loads(summary_text)
        self.assertEqual(fixture.order_id, summary["order_id"])
        self.assertEqual(self._FINGERPRINT, summary["message_fingerprint"])
        self.assertEqual(fixture.artifact_sha256, summary["artifact_sha256"])
        self.assertEqual(fixture.digest, summary["manifest_sha256"])
        self.assertEqual(1, summary["layer_count"])
        self.assertEqual([fixture.target], summary["published_tables"])
        self.assertEqual("performed", summary["promotion"])
        self.assertEqual(
            [
                {
                    "target_table": fixture.target,
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
                "tables_discovered": [fixture.target],
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
            self.assertNotIn(fixture.loader_password, text)
            self.assertNotIn(fixture.reader_password, text)
            self.assertNotIn(str(fixture.config_path.parent), text)

        # The promotion really committed under the throwaway loader.
        self.assertEqual(
            len(self._VICTORIA_POINTS),
            self._scalar(
                fixture.connection,
                sql.SQL("SELECT count(*) FROM {}").format(
                    sql.Identifier(fixture.pub_schema, fixture.target)
                ),
            ),
        )


class LivePublishOrderResumeTest(_LivePublishOrderMixin, unittest.TestCase):
    """Skips without live DSNs. Reproduces the 2026-09-24 WINDOWS.md #16
    incident end to end (D-93): run 1 publishes with
    ``VICMAP_READER_PASSWORD`` unset -- the promotion commits durably, then
    the post-commit reader proof fails closed, and the staging table is
    already consumed. Run 2, with the password now set, must resume from the
    durable ``vicmap_audit.publication`` marker instead of re-entering
    promotion (which would hit ``UndefinedTable`` on the already-consumed
    staging table): it patches ``publish._promote_in_transaction`` to explode
    if reached, and asserts exit 0, ``summary.json`` recording promotion
    "resumed", the marker's own ``server_version``, and the published
    table's ``(oid, xmin)`` unchanged -- proving no promotion DDL ran."""

    _RUN_DIR_NAME = "20260929T000005Z"

    def test_rerun_after_post_commit_reader_failure_resumes(self):
        self._require_live()
        fixture = self._provision_order_fixture(tag="rs", run_dir_name=self._RUN_DIR_NAME)

        # Run 1: reader password unset -- promotion commits, then the reader
        # proof fails closed (the exact 2026-09-24 incident shape).
        stdout1, stderr1 = io.StringIO(), io.StringIO()
        with patch.dict(
            os.environ, {staging.PASSWORD_ENV_VAR: fixture.loader_password}
        ):
            os.environ.pop(publish.READER_PASSWORD_ENV_VAR, None)
            with contextlib.redirect_stdout(stdout1), contextlib.redirect_stderr(
                stderr1
            ):
                exit_code_1 = publish_order.main(["--config", str(fixture.config_path)])

        output_1 = stdout1.getvalue() + stderr1.getvalue()
        self.assertEqual(1, exit_code_1, output_1)
        failure_lines = [line for line in stderr1.getvalue().splitlines() if line]
        self.assertEqual(1, len(failure_lines))
        failure = json.loads(failure_lines[0])
        self.assertEqual("db_reader_verify", failure["stage"])
        self.assertEqual("reader_role_unavailable", failure["reason"])

        summary_path = fixture.run_directory / "summary.json"
        self.assertFalse(summary_path.exists())

        # The staging table is gone -- consumed by the committed promotion.
        self.assertIsNone(
            self._scalar(
                fixture.connection,
                "SELECT to_regclass(%s)",
                (f"{fixture.stg_schema}.{fixture.staging_table}",),
            )
        )

        published_oid = self._scalar(
            fixture.connection,
            "SELECT to_regclass(%s)::oid",
            (f"{fixture.pub_schema}.{fixture.target}",),
        )
        published_xmin = self._scalar(
            fixture.connection,
            "SELECT xmin::text FROM pg_class WHERE oid = to_regclass(%s)",
            (f"{fixture.pub_schema}.{fixture.target}",),
        )
        self.assertEqual(
            1,
            self._scalar(
                fixture.connection,
                "SELECT count(*) FROM vicmap_audit.publication "
                "WHERE run_ts = %s AND manifest_digest = %s",
                (self._RUN_DIR_NAME, fixture.digest),
            ),
        )
        marker_oid = self._scalar(
            fixture.connection,
            "SELECT table_oid FROM vicmap_audit.publication "
            "WHERE run_ts = %s AND manifest_digest = %s",
            (self._RUN_DIR_NAME, fixture.digest),
        )
        self.assertEqual(published_oid, marker_oid)
        marker_server_version = self._scalar(
            fixture.connection,
            "SELECT server_version FROM vicmap_audit.publication "
            "WHERE run_ts = %s AND manifest_digest = %s",
            (self._RUN_DIR_NAME, fixture.digest),
        )

        # Run 2: both passwords set. _promote_in_transaction is patched to
        # explode if reached -- proving resume never re-enters promotion.
        stdout2, stderr2 = io.StringIO(), io.StringIO()
        with patch.dict(
            os.environ,
            {
                staging.PASSWORD_ENV_VAR: fixture.loader_password,
                publish.READER_PASSWORD_ENV_VAR: fixture.reader_password,
            },
        ), patch.object(
            publish,
            "_promote_in_transaction",
            side_effect=AssertionError("resume must not re-enter promotion"),
        ), contextlib.redirect_stdout(stdout2), contextlib.redirect_stderr(stderr2):
            exit_code_2 = publish_order.main(["--config", str(fixture.config_path)])

        output_2 = stdout2.getvalue() + stderr2.getvalue()
        self.assertEqual(0, exit_code_2, output_2)

        summary_text = summary_path.read_text(encoding="utf-8")
        summary = json.loads(summary_text)
        self.assertEqual("resumed", summary["promotion"])
        self.assertEqual(marker_server_version, summary["server_version"])
        self.assertEqual([fixture.target], summary["published_tables"])

        self.assertEqual(
            published_oid,
            self._scalar(
                fixture.connection,
                "SELECT to_regclass(%s)::oid",
                (f"{fixture.pub_schema}.{fixture.target}",),
            ),
        )
        self.assertEqual(
            published_xmin,
            self._scalar(
                fixture.connection,
                "SELECT xmin::text FROM pg_class WHERE oid = to_regclass(%s)",
                (f"{fixture.pub_schema}.{fixture.target}",),
            ),
        )
        self.assertEqual(
            1,
            self._scalar(
                fixture.connection,
                "SELECT count(*) FROM vicmap_audit.publication "
                "WHERE run_ts = %s AND manifest_digest = %s",
                (self._RUN_DIR_NAME, fixture.digest),
            ),
        )

        for text in (summary_text, output_1, output_2):
            self.assertNotIn(fixture.loader_password, text)
            self.assertNotIn(fixture.reader_password, text)
            self.assertNotIn(str(fixture.config_path.parent), text)

    _SUPERSEDED_RUN_DIR_NAME = "20260929T000006Z"

    def test_superseded_generation_fails_closed_without_ddl(self):
        """A generation this run itself published, later replaced out of
        band (a rename plus a fresh table under the same name), is
        pub_generation_superseded -- proven live with no DDL against the
        replacement and no publication_summary event (D-86/D-87)."""

        self._require_live()
        fixture = self._provision_order_fixture(
            tag="sp", run_dir_name=self._SUPERSEDED_RUN_DIR_NAME
        )
        sql = publish.sql

        # Run 1: a normal full run -- both passwords set.
        stdout1, stderr1 = io.StringIO(), io.StringIO()
        with patch.dict(
            os.environ,
            {
                staging.PASSWORD_ENV_VAR: fixture.loader_password,
                publish.READER_PASSWORD_ENV_VAR: fixture.reader_password,
            },
        ), contextlib.redirect_stdout(stdout1), contextlib.redirect_stderr(stderr1):
            exit_code_1 = publish_order.main(["--config", str(fixture.config_path)])
        output_1 = stdout1.getvalue() + stderr1.getvalue()
        self.assertEqual(0, exit_code_1, output_1)

        summary_path = fixture.run_directory / "summary.json"
        summary_bytes_1 = summary_path.read_bytes()

        # Replace the published generation out of band: rename the table
        # this run published, then create a fresh one under the same name.
        old_name = f"{fixture.target}_old"
        with fixture.connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER TABLE {} RENAME TO {}").format(
                    sql.Identifier(fixture.pub_schema, fixture.target),
                    sql.Identifier(old_name),
                )
            )
            self._create_point_table(
                cursor,
                fixture.pub_schema,
                fixture.target,
                gist_index=f"livetest_sp_replacement_gix_{os.getpid()}",
                points=self._VICTORIA_POINTS,
            )
        replacement_oid = self._scalar(
            fixture.connection,
            "SELECT to_regclass(%s)::oid",
            (f"{fixture.pub_schema}.{fixture.target}",),
        )
        replacement_xmin = self._scalar(
            fixture.connection,
            "SELECT xmin::text FROM pg_class WHERE oid = to_regclass(%s)",
            (f"{fixture.pub_schema}.{fixture.target}",),
        )

        # Run 2: re-run against the replaced generation.
        stdout2, stderr2 = io.StringIO(), io.StringIO()
        with patch.dict(
            os.environ,
            {
                staging.PASSWORD_ENV_VAR: fixture.loader_password,
                publish.READER_PASSWORD_ENV_VAR: fixture.reader_password,
            },
        ), contextlib.redirect_stdout(stdout2), contextlib.redirect_stderr(stderr2):
            exit_code_2 = publish_order.main(["--config", str(fixture.config_path)])
        output_2 = stdout2.getvalue() + stderr2.getvalue()
        self.assertEqual(1, exit_code_2, output_2)

        failure_lines = [line for line in stderr2.getvalue().splitlines() if line]
        self.assertEqual(1, len(failure_lines))
        failure = json.loads(failure_lines[0])
        self.assertEqual("db_publish", failure["stage"])
        self.assertEqual("pub_generation_superseded", failure["reason"])

        events = [json.loads(line) for line in stdout2.getvalue().splitlines() if line]
        self.assertNotIn("publication_summary", [e.get("event") for e in events])

        self.assertEqual(
            replacement_oid,
            self._scalar(
                fixture.connection,
                "SELECT to_regclass(%s)::oid",
                (f"{fixture.pub_schema}.{fixture.target}",),
            ),
        )
        self.assertEqual(
            replacement_xmin,
            self._scalar(
                fixture.connection,
                "SELECT xmin::text FROM pg_class WHERE oid = to_regclass(%s)",
                (f"{fixture.pub_schema}.{fixture.target}",),
            ),
        )
        self.assertIsNotNone(
            self._scalar(
                fixture.connection,
                "SELECT to_regclass(%s)",
                (f"{fixture.pub_schema}.{old_name}",),
            )
        )
        self.assertEqual(
            1,
            self._scalar(
                fixture.connection,
                "SELECT count(*) FROM vicmap_audit.publication "
                "WHERE run_ts = %s AND manifest_digest = %s",
                (self._SUPERSEDED_RUN_DIR_NAME, fixture.digest),
            ),
        )
        self.assertEqual(summary_bytes_1, summary_path.read_bytes())

        for text in (output_1, output_2):
            self.assertNotIn(fixture.loader_password, text)
            self.assertNotIn(fixture.reader_password, text)
            self.assertNotIn(str(fixture.config_path.parent), text)

    _UNMARKED_RUN_DIR_NAME = "20260929T000007Z"

    def test_unmarked_live_table_fails_closed_as_ambiguous(self):
        """The fixture-scale shape of D-88: a live published table this run
        never staged (``staged=False``) and holds no publication marker for
        makes ``publish_order.main`` exit 1 with ``pub_generation_ambiguous``,
        leaving the table's ``(oid, xmin)`` unchanged and writing neither a
        publication row nor ``summary.json``. The real ``vicmap.vmadd_address``
        is probed read-only in Plan 05.1-05."""

        self._require_live()
        fixture = self._provision_order_fixture(
            tag="um", run_dir_name=self._UNMARKED_RUN_DIR_NAME, staged=False
        )

        with fixture.connection.cursor() as cursor:
            self._create_point_table(
                cursor,
                fixture.pub_schema,
                fixture.target,
                gist_index=f"livetest_um_gix_{os.getpid()}",
                points=self._VICTORIA_POINTS,
            )
        live_oid = self._scalar(
            fixture.connection,
            "SELECT to_regclass(%s)::oid",
            (f"{fixture.pub_schema}.{fixture.target}",),
        )
        live_xmin = self._scalar(
            fixture.connection,
            "SELECT xmin::text FROM pg_class WHERE oid = to_regclass(%s)",
            (f"{fixture.pub_schema}.{fixture.target}",),
        )

        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(
            os.environ,
            {
                staging.PASSWORD_ENV_VAR: fixture.loader_password,
                publish.READER_PASSWORD_ENV_VAR: fixture.reader_password,
            },
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = publish_order.main(["--config", str(fixture.config_path)])
        output = stdout.getvalue() + stderr.getvalue()
        self.assertEqual(1, exit_code, output)

        failure_lines = [line for line in stderr.getvalue().splitlines() if line]
        self.assertEqual(1, len(failure_lines))
        failure = json.loads(failure_lines[0])
        self.assertEqual("db_publish", failure["stage"])
        self.assertEqual("pub_generation_ambiguous", failure["reason"])

        self.assertEqual(
            live_oid,
            self._scalar(
                fixture.connection,
                "SELECT to_regclass(%s)::oid",
                (f"{fixture.pub_schema}.{fixture.target}",),
            ),
        )
        self.assertEqual(
            live_xmin,
            self._scalar(
                fixture.connection,
                "SELECT xmin::text FROM pg_class WHERE oid = to_regclass(%s)",
                (f"{fixture.pub_schema}.{fixture.target}",),
            ),
        )
        self.assertEqual(
            0,
            self._scalar(
                fixture.connection,
                "SELECT count(*) FROM vicmap_audit.publication "
                "WHERE run_ts = %s AND manifest_digest = %s",
                (self._UNMARKED_RUN_DIR_NAME, fixture.digest),
            ),
        )
        self.assertFalse((fixture.run_directory / "summary.json").exists())

        self.assertNotIn(fixture.loader_password, output)
        self.assertNotIn(fixture.reader_password, output)
        self.assertNotIn(str(fixture.config_path.parent), output)


if __name__ == "__main__":
    unittest.main()
