"""GEO-04/GEO-05 pure-function regressions for target table naming (D-21..D-24).

These are pure unit tests needing no fixtures, in ``tests/test_origin.py``'s
style. ``NormalizeTargetTableNameTest`` and ``PostgresKeywordSnapshotTest``
cover D-21/D-22 normalization; ``AssignTargetTableNamesTest`` covers D-23/D-24
collision detection using lightweight profile stand-ins so no geodatabase is
needed. ``NamingModulePurityTest`` inspects the module's own source with
``ast`` to prove it stays leaf-ward (no import of ``discovery``,
``manifest``, ``extraction``, or ``read_mailbox``) and structurally incapable
of contacting a database (no database driver or ``socket`` import).

``PostgresKeywordOracleTest`` (IN-01) is the one exception to "no database
driver": every other test above checks ``_RESERVED_KEYWORDS`` against
*itself* -- ``PostgresKeywordSnapshotTest``'s trap words were chosen by
reading the same hand-transcribed frozenset the code under test uses, so a
transcription error in that frozenset (a missing or extra keyword) would
never be caught by any test that was written against the same list. The
oracle test instead asks a *running PostgreSQL server* -- via
``pg_get_keywords()``, which the server derives at build time from its own
grammar tables (``src/include/parser/kwlist.h``), not from anyone re-reading
the Appendix C documentation page a second time -- and diffs its answer
against ``_RESERVED_KEYWORDS``. This is optional and skips cleanly (never
fails) when no PostgreSQL driver is importable or no server is reachable,
since neither this module nor its test suite may require a live database
(D-23) or network access to pass.
"""

from __future__ import annotations

import ast
import os
import unittest
from dataclasses import dataclass
from pathlib import Path

from vicmap_acquire.naming import (
    POSTGRES_KEYWORD_SNAPSHOT,
    NamingFailure,
    TableNameCollision,
    TableNameInvalid,
    assign_target_table_names,
    normalize_target_table_name,
)

import vicmap_acquire.naming as naming_module


class NormalizeTargetTableNameTest(unittest.TestCase):
    def test_happy_case_vmadd_address(self):
        self.assertEqual(normalize_target_table_name("VMADD", "ADDRESS"), "vmadd_address")

    def test_hyphen_separator_collapses(self):
        self.assertEqual(normalize_target_table_name("VM-ADD", "ADDRESS"), "vm_add_address")

    def test_underscore_run_collapses(self):
        self.assertEqual(normalize_target_table_name("VM__ADD", "ADDRESS"), "vm_add_address")

    def test_space_separator_collapses(self):
        self.assertEqual(normalize_target_table_name("VM ADD", "ADDRESS"), "vm_add_address")

    def test_period_separator_collapses(self):
        self.assertEqual(normalize_target_table_name("VM.ADD", "ADDRESS"), "vm_add_address")

    def test_mixed_separator_run_collapses(self):
        self.assertEqual(normalize_target_table_name("VM -_. ADD", "ADDRESS"), "vm_add_address")

    def test_leading_and_trailing_separators_stripped(self):
        self.assertEqual(normalize_target_table_name("-VMADD-", "-ADDRESS-"), "vmadd_address")

    def test_invalid_charset_character_raises(self):
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name("VMADD!", "ADDRESS")

    def test_accented_character_raises_on_charset(self):
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name("VMÁDD", "ADDRESS")

    def test_fullwidth_digit_raises_on_charset(self):
        # U+FF10 FULLWIDTH DIGIT ZERO -- not in [a-z0-9_], proving no
        # Unicode normalization path folds it down to ASCII "0".
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name("VMADD０", "ADDRESS")

    def test_leading_digit_raises(self):
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name("1VMADD", "ADDRESS")

    def test_reserved_keyword_category_raises(self):
        # "select" -- plain "reserved" category.
        with self.assertRaises(TableNameInvalid):
            _normalize_whole("select")

    def test_reserved_can_be_function_or_type_keyword_binary_raises(self):
        # "binary" -- "reserved (can be function or type)" category, one of
        # the words a hand-typed "common reserved words" shortlist misses.
        with self.assertRaises(TableNameInvalid):
            _normalize_whole("binary")

    def test_reserved_can_be_function_or_type_keyword_concurrently_raises(self):
        with self.assertRaises(TableNameInvalid):
            _normalize_whole("concurrently")

    def test_reserved_can_be_function_or_type_keyword_current_schema_raises(self):
        with self.assertRaises(TableNameInvalid):
            _normalize_whole("current_schema")

    def test_63_byte_name_accepted(self):
        # dataset_stem "a"*61 + "_" + layer_name "b" composes to exactly 63
        # bytes (61 + 1 joiner underscore + 1 = 63).
        name = normalize_target_table_name("a" * 61, "b")
        self.assertEqual(len(name.encode("utf-8")), 63)

    def test_64_byte_name_raises(self):
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name("a" * 62, "b")

    def test_empty_dataset_stem_raises(self):
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name("", "ADDRESS")

    def test_empty_layer_name_raises(self):
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name("VMADD", "")

    def test_whitespace_only_dataset_stem_raises(self):
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name("   ", "ADDRESS")

    def test_whitespace_only_layer_name_raises(self):
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name("VMADD", "   ")

    def test_separators_only_composition_raises(self):
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name("---", "___")

    def test_non_string_dataset_stem_raises_table_name_invalid_not_type_error(self):
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name(12345, "ADDRESS")  # type: ignore[arg-type]

    def test_non_string_layer_name_raises_table_name_invalid_not_type_error(self):
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name("VMADD", None)  # type: ignore[arg-type]

    def test_none_dataset_stem_raises(self):
        with self.assertRaises(TableNameInvalid):
            normalize_target_table_name(None, "ADDRESS")  # type: ignore[arg-type]

    def test_every_invalid_case_raises_table_name_invalid_never_bare_builtin(self):
        invalid_inputs = [
            ("", "ADDRESS"),
            ("VMADD", ""),
            ("VMADD!", "ADDRESS"),
            ("1VMADD", "ADDRESS"),
            ("a" * 62, "b"),
            (12345, "ADDRESS"),
            ("VMADD", None),
            ("---", "___"),
        ]
        for dataset_stem, layer_name in invalid_inputs:
            with self.subTest(dataset_stem=dataset_stem, layer_name=layer_name):
                try:
                    normalize_target_table_name(dataset_stem, layer_name)  # type: ignore[arg-type]
                except TableNameInvalid:
                    pass
                except Exception as exc:  # pragma: no cover -- assertion path
                    self.fail(f"expected TableNameInvalid, got {type(exc).__name__}: {exc}")
                else:
                    self.fail("expected TableNameInvalid, no exception raised")


def _normalize_whole(word: str) -> str:
    """Drive ``word`` through the public API as the sole surviving token.

    ``normalize_target_table_name`` always joins ``dataset_stem`` and
    ``layer_name`` with an underscore, and an empty component is itself a
    typed failure, so a bare reserved word cannot be composed by leaving a
    side empty. Instead, pair it with a lone separator character (``"-"``)
    as the other component: the joiner underscore and the lone hyphen sit
    adjacent and collapse into one separator run, which the trailing-strip
    rule then removes entirely, leaving ``word`` as the exact composed
    result -- exercising the reserved-word rule against a real single word
    rather than a synthetic ``"prefix_word"`` composite.
    """

    return normalize_target_table_name(word, "-")


class PostgresKeywordSnapshotTest(unittest.TestCase):
    def test_snapshot_is_nonempty_string_naming_version_and_appendix(self):
        self.assertIsInstance(POSTGRES_KEYWORD_SNAPSHOT, str)
        self.assertTrue(POSTGRES_KEYWORD_SNAPSHOT.strip())
        lowered = POSTGRES_KEYWORD_SNAPSHOT.lower()
        self.assertIn("postgresql", lowered)
        self.assertIn("appendix", lowered)

    def test_reserved_keyword_frozenset_contains_shortlist_trap_words(self):
        trap_words = {
            "binary",
            "concurrently",
            "cross",
            "current_schema",
            "freeze",
            "ilike",
            "isnull",
            "natural",
            "notnull",
            "outer",
            "overlaps",
            "similar",
            "verbose",
        }
        for word in trap_words:
            with self.subTest(word=word):
                with self.assertRaises(TableNameInvalid):
                    _normalize_whole(word)


class PostgresKeywordOracleTest(unittest.TestCase):
    """IN-01 differential oracle: cross-check ``_RESERVED_KEYWORDS`` against
    a live PostgreSQL server's own ``pg_get_keywords()`` instead of another
    hand-written assertion against the same transcribed list.

    Skipped, never failed, when no PostgreSQL driver (``psycopg`` or
    ``psycopg2``) is installed, or when no server is reachable within a
    short local timeout -- this suite has no required network or live
    database dependency. Set ``VICMAP_TEST_POSTGRES_DSN`` to point this
    test at a specific server; otherwise it tries a local default
    connection (``dbname=postgres``) and skips on any connection failure.
    """

    _DSN_ENV_VAR = "VICMAP_TEST_POSTGRES_DSN"
    _CONNECT_TIMEOUT_SECONDS = 2

    def _connect(self):
        try:
            import psycopg as _driver  # psycopg3, preferred if present
        except ImportError:
            try:
                import psycopg2 as _driver  # type: ignore[no-redef]
            except ImportError:
                self.skipTest(
                    "no PostgreSQL driver (psycopg or psycopg2) installed -- "
                    "IN-01 oracle check skipped, not failed"
                )

        dsn = os.environ.get(self._DSN_ENV_VAR)
        try:
            if dsn:
                connection = _driver.connect(
                    dsn, connect_timeout=self._CONNECT_TIMEOUT_SECONDS
                )
            else:
                connection = _driver.connect(
                    dbname="postgres",
                    connect_timeout=self._CONNECT_TIMEOUT_SECONDS,
                )
        except Exception as exc:  # noqa: BLE001 -- any connect failure just skips
            self.skipTest(
                f"no reachable PostgreSQL server for IN-01 oracle check: {exc}"
            )
        return connection

    def test_reserved_keywords_match_live_server_pg_get_keywords(self):
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT word, catcode FROM pg_get_keywords()")
                rows = cursor.fetchall()
        finally:
            connection.close()

        # catcode 'R' = RESERVED_KEYWORD ("reserved" in Appendix C);
        # catcode 'T' = TYPE_FUNC_NAME_KEYWORD ("reserved (can be function
        # or type)" in Appendix C). These are the server's own category
        # codes, generated from its grammar tables -- not re-typed from the
        # documentation page naming.py's own comment cites.
        server_blocking_keywords = {
            word for word, catcode in rows if catcode in ("R", "T")
        }
        self.assertEqual(
            naming_module._RESERVED_KEYWORDS,
            server_blocking_keywords,
            "naming.py's hand-transcribed _RESERVED_KEYWORDS has drifted "
            "from this live server's pg_get_keywords() reserved categories "
            "('R' and 'T') -- see IN-01",
        )


@dataclass(frozen=True)
class _ProfileStub:
    """Lightweight profile stand-in carrying only what naming.py reads."""

    dataset_relative_path: str
    dataset_stem: str
    layer_name: str


class AssignTargetTableNamesTest(unittest.TestCase):
    def test_two_crs_folder_variants_collide(self):
        gda94 = _ProfileStub(
            dataset_relative_path="gda94_vicgrid/filegdb/whole_of_dataset/victoria/VMADD.gdb",
            dataset_stem="VMADD",
            layer_name="ADDRESS",
        )
        gda2020 = _ProfileStub(
            dataset_relative_path="gda2020_vicgrid/filegdb/whole_of_dataset/victoria/VMADD.gdb",
            dataset_stem="VMADD",
            layer_name="ADDRESS",
        )
        with self.assertRaises(TableNameCollision):
            assign_target_table_names((gda94, gda2020))

    def test_two_format_folder_variants_collide(self):
        filegdb = _ProfileStub(
            dataset_relative_path="gda2020_vicgrid/filegdb/whole_of_dataset/victoria/VMADD.gdb",
            dataset_stem="VMADD",
            layer_name="ADDRESS",
        )
        shp = _ProfileStub(
            dataset_relative_path="gda2020_vicgrid/shp/whole_of_dataset/victoria/VMADD.gdb",
            dataset_stem="VMADD",
            layer_name="ADDRESS",
        )
        with self.assertRaises(TableNameCollision):
            assign_target_table_names((filegdb, shp))

    def test_case_only_difference_in_layer_name_collides(self):
        upper = _ProfileStub(
            dataset_relative_path="a/VMADD.gdb", dataset_stem="VMADD", layer_name="ADDRESS"
        )
        lower = _ProfileStub(
            dataset_relative_path="b/VMADD.gdb", dataset_stem="VMADD", layer_name="address"
        )
        with self.assertRaises(TableNameCollision):
            assign_target_table_names((upper, lower))

    def test_invalid_profile_raises_invalid_not_collision_when_invalid_is_first(self):
        invalid = _ProfileStub(dataset_relative_path="a", dataset_stem="", layer_name="ADDRESS")
        valid = _ProfileStub(dataset_relative_path="b", dataset_stem="VMADD", layer_name="ADDRESS")
        with self.assertRaises(TableNameInvalid):
            assign_target_table_names((invalid, valid))

    def test_invalid_profile_raises_invalid_not_collision_when_invalid_is_second(self):
        valid = _ProfileStub(dataset_relative_path="b", dataset_stem="VMADD", layer_name="ADDRESS")
        invalid = _ProfileStub(dataset_relative_path="a", dataset_stem="", layer_name="ADDRESS")
        with self.assertRaises(TableNameInvalid):
            assign_target_table_names((valid, invalid))

    def test_empty_profile_sequence_returns_empty_tuple(self):
        self.assertEqual(assign_target_table_names(()), ())

    def test_same_single_profile_across_two_separate_calls_both_succeed(self):
        profile = _ProfileStub(
            dataset_relative_path="a/VMADD.gdb", dataset_stem="VMADD", layer_name="ADDRESS"
        )
        first = assign_target_table_names((profile,))
        second = assign_target_table_names((profile,))
        self.assertEqual(first, ((profile, "vmadd_address"),))
        self.assertEqual(second, ((profile, "vmadd_address"),))

    def test_malformed_profile_object_raises_table_name_invalid(self):
        class _Malformed:
            pass

        with self.assertRaises(TableNameInvalid):
            assign_target_table_names((_Malformed(),))

    def test_returns_pairs_in_same_order_as_input(self):
        first = _ProfileStub(dataset_relative_path="a", dataset_stem="VMADD", layer_name="ADDRESS")
        second = _ProfileStub(dataset_relative_path="b", dataset_stem="VMROAD", layer_name="ROAD")
        result = assign_target_table_names((first, second))
        self.assertEqual(
            result, ((first, "vmadd_address"), (second, "vmroad_road"))
        )

    def test_distinct_layers_do_not_collide(self):
        first = _ProfileStub(dataset_relative_path="a", dataset_stem="VMADD", layer_name="ADDRESS")
        second = _ProfileStub(dataset_relative_path="b", dataset_stem="VMROAD", layer_name="ROAD")
        result = assign_target_table_names((first, second))
        self.assertEqual(len(result), 2)


class NamingModulePurityTest(unittest.TestCase):
    """Structural proof that naming.py stays leaf-ward and DB-free (T-02-30)."""

    def _module_tree(self) -> ast.AST:
        source = Path(naming_module.__file__).read_text(encoding="utf-8")
        return ast.parse(source, filename=naming_module.__file__)

    def _imported_module_names(self) -> set[str]:
        tree = self._module_tree()
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    names.add(node.module)
        return names

    def test_no_import_of_sibling_pipeline_modules(self):
        forbidden = {
            "discovery",
            "manifest",
            "extraction",
            "read_mailbox",
            "vicmap_acquire.discovery",
            "vicmap_acquire.manifest",
            "vicmap_acquire.extraction",
            "vicmap_acquire.read_mailbox",
        }
        imported = self._imported_module_names()
        offending = imported & forbidden
        self.assertFalse(
            offending,
            f"vicmap_acquire/naming.py must not import {sorted(offending)} -- "
            "dependency direction must stay leaf-ward (D-23).",
        )

    def test_no_database_driver_or_socket_import(self):
        forbidden = {
            "socket",
            "psycopg2",
            "psycopg",
            "psycopg2.extensions",
            "asyncpg",
            "sqlite3",
            "sqlalchemy",
        }
        imported = self._imported_module_names()
        offending = imported & forbidden
        self.assertFalse(
            offending,
            f"vicmap_acquire/naming.py must not import {sorted(offending)} -- "
            "the module must be structurally incapable of contacting a "
            "database (D-23, T-02-30).",
        )


if __name__ == "__main__":
    unittest.main()
