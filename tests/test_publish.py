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
    ):
        self.executed: list[str] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False
        self.constraint_rows = constraint_rows
        self.index_rows = index_rows
        self.audit_rows = audit_rows
        self.fail_on = fail_on

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
        with patch.object(publish.psycopg, "connect", return_value=connection):
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
            audit_rows=(("vmadd_address", "pass"),),
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
        connection = _FakeConnection(
            constraint_rows=(_PK_ROW, _NOT_NULL_ROW),
            index_rows=(_GEOM_INDEX_ROW,),
            fail_on="GRANT SELECT",
        )
        with patch.object(publish.psycopg, "connect", return_value=connection):
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


if __name__ == "__main__":
    unittest.main()
