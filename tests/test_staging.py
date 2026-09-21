"""Phase 3 [database] configuration contract regressions (DB-01 through DB-05).

Covers ``read_mailbox.load_database_config`` and
``read_mailbox.validate_database_policy`` -- the single reviewable,
fail-closed contract for Phase 3's connection target, schema names, target
SRID, secondary-index allowlist, and loader timing budget.

``DatabaseConfigTest`` is this module's first test class; it touches no
database and must never skip. 03-04, 03-05, and 03-06 add the live-database
classes to this same module (connection identity, privilege preflight, load
command construction/integration, post-load validation, production
isolation). No test in this module, now or later, may require a reachable
PostgreSQL server or an installed ``psycopg`` in order to pass --
live-database checks skip, never fail.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import read_mailbox
from vicmap_acquire import staging
from vicmap_acquire.discovery import FieldProfile, LayerProfile
from vicmap_acquire.evidence import ProgressEvent, ReasonCode, SafeFailure, SuccessEvent
from vicmap_acquire.manifest import ImportManifest, ManifestLayer


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ARCHIVE = REPO_ROOT / "tests" / "fixtures" / "Order_TRACER1.zip"

VALID_TOML = """\
[mailbox]
address = "automations@vegetationlink.com.au"
folder = "Inbox"
allowed_senders = ["noreply@datashare.maps.vic.gov.au"]
allowed_order_ids = ["OK0VUZ"]
lookback_days = 15
allow_order_id_mismatch = false
required_authentication_results = ["dkim", "dmarc", "compauth"]

[download]
allowed_hosts = ["s3.ap-southeast-2.amazonaws.com"]
max_bytes = 10737418240
connect_timeout_seconds = 10
read_timeout_seconds = 60
progress_interval_seconds = 5
max_redirects = 5
fingerprint_hex_chars = 16
output_dir = "artifacts"
allowed_url_prefixes = ["https://s3.ap-southeast-2.amazonaws.com/private/"]

[extraction]
run_dir = "runs"
max_total_bytes = 10737418240
max_member_bytes = 4294967296
max_member_count = 4096
max_compression_ratio = 20

[discovery]
supported_formats = ["OpenFileGDB"]
ogrinfo_timeout_seconds = 60

[database]
host = "127.0.0.1"
port = 5432
dbname = "vicmap"
user = "vicmap_loader"
staging_schema = "vicmap_staging"
publish_schema = "vicmap"
target_srid = 7899
index_columns = ["pfi"]
gt = 20000
connect_timeout_seconds = 10
statement_timeout_seconds = 3600
lock_timeout_seconds = 30
"""

_DATABASE_SECTION = """\
[database]
host = "127.0.0.1"
port = 5432
dbname = "vicmap"
user = "vicmap_loader"
staging_schema = "vicmap_staging"
publish_schema = "vicmap"
target_srid = 7899
index_columns = ["pfi"]
gt = 20000
connect_timeout_seconds = 10
statement_timeout_seconds = 3600
lock_timeout_seconds = 30
"""

_DATABASE_KEY_NAMES = (
    "host",
    "port",
    "dbname",
    "user",
    "staging_schema",
    "publish_schema",
    "target_srid",
    "index_columns",
    "gt",
    "connect_timeout_seconds",
    "statement_timeout_seconds",
    "lock_timeout_seconds",
)


def _write_policy(directory: str, text: str = VALID_TOML) -> Path:
    path = Path(directory) / "vicmap.toml"
    path.write_text(text, encoding="utf-8")
    return path


class DatabaseConfigTest(unittest.TestCase):
    """The [database] contract fails closed on every rule.

    No test method here may require a reachable PostgreSQL server or an
    installed driver -- it parses TOML and validates a dataclass only.
    """

    def _assert_rejected(self, text: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _write_policy(directory, text)
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.load_database_config(path)
        self.assertEqual("config_invalid", caught.exception.code)

    def _valid_kwargs(self, directory: Path) -> dict:
        return dict(
            run_root=directory / "runs",
            fingerprint_hex_chars=16,
            allowed_order_ids=("OK0VUZ",),
            host="127.0.0.1",
            port=5432,
            dbname="vicmap",
            user="vicmap_loader",
            staging_schema="vicmap_staging",
            publish_schema="vicmap",
            target_srid=7899,
            index_columns=("pfi",),
            gt=20000,
            connect_timeout_seconds=10,
            statement_timeout_seconds=3600,
            lock_timeout_seconds=30,
        )

    def test_happy_path_loads_every_field(self):
        with tempfile.TemporaryDirectory() as directory:
            config = read_mailbox.load_database_config(_write_policy(directory))
        self.assertEqual("127.0.0.1", config.host)
        self.assertEqual(5432, config.port)
        self.assertEqual("vicmap", config.dbname)
        self.assertEqual("vicmap_loader", config.user)
        self.assertEqual("vicmap_staging", config.staging_schema)
        self.assertEqual("vicmap", config.publish_schema)
        self.assertEqual(7899, config.target_srid)
        self.assertEqual(("pfi",), config.index_columns)
        self.assertEqual(20000, config.gt)
        self.assertEqual(10, config.connect_timeout_seconds)
        self.assertEqual(3600, config.statement_timeout_seconds)
        self.assertEqual(30, config.lock_timeout_seconds)

    def test_missing_database_section_entirely(self):
        text = VALID_TOML.replace("\n" + _DATABASE_SECTION, "\n")
        self._assert_rejected(text)

    def test_missing_each_database_key_in_turn(self):
        for key in _DATABASE_KEY_NAMES:
            with self.subTest(key=key):
                lines = _DATABASE_SECTION.splitlines(keepends=True)
                remaining = [line for line in lines if not line.startswith(f"{key} ")]
                text = VALID_TOML.replace(_DATABASE_SECTION, "".join(remaining))
                self._assert_rejected(text)

    def test_extra_key_in_database_section(self):
        text = VALID_TOML.replace(
            "lock_timeout_seconds = 30\n", "lock_timeout_seconds = 30\nextra = 1\n"
        )
        self._assert_rejected(text)

    def test_staging_schema_equals_publish_schema(self):
        text = VALID_TOML.replace(
            'staging_schema = "vicmap_staging"', 'staging_schema = "vicmap"'
        )
        self._assert_rejected(text)

    def test_staging_schema_is_public(self):
        text = VALID_TOML.replace(
            'staging_schema = "vicmap_staging"', 'staging_schema = "public"'
        )
        self._assert_rejected(text)

    def test_publish_schema_is_public(self):
        text = VALID_TOML.replace('publish_schema = "vicmap"', 'publish_schema = "public"')
        self._assert_rejected(text)

    def test_port_zero_and_out_of_range(self):
        for bad_value in (0, 65536):
            with self.subTest(value=bad_value):
                text = VALID_TOML.replace("port = 5432", f"port = {bad_value}")
                self._assert_rejected(text)

    def test_target_srid_below_epsg_range(self):
        text = VALID_TOML.replace("target_srid = 7899", "target_srid = 1023")
        self._assert_rejected(text)

    def test_empty_index_columns(self):
        text = VALID_TOML.replace('index_columns = ["pfi"]', "index_columns = []")
        self._assert_rejected(text)

    def test_duplicate_index_columns(self):
        text = VALID_TOML.replace(
            'index_columns = ["pfi"]', 'index_columns = ["pfi", "pfi"]'
        )
        self._assert_rejected(text)

    def test_index_column_outside_identifier_pattern(self):
        text = VALID_TOML.replace('index_columns = ["pfi"]', 'index_columns = ["PFI"]')
        self._assert_rejected(text)

    def test_lock_timeout_exceeds_statement_timeout(self):
        text = VALID_TOML.replace(
            "lock_timeout_seconds = 30", "lock_timeout_seconds = 9999"
        )
        self._assert_rejected(text)

    def test_non_integer_port(self):
        text = VALID_TOML.replace("port = 5432", 'port = "5432"')
        self._assert_rejected(text)

    def test_boolean_port_is_rejected(self):
        text = VALID_TOML.replace("port = 5432", "port = true")
        self._assert_rejected(text)

    def test_directly_constructed_config_public_schema_bypasses_loader_not_validator(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs = self._valid_kwargs(Path(directory))
            kwargs["staging_schema"] = "public"
            config = read_mailbox.DatabaseRunConfig(**kwargs)
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.validate_database_policy(config)
            self.assertEqual("config_invalid", caught.exception.code)

    def test_directly_constructed_config_rejects_out_of_range_port(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs = self._valid_kwargs(Path(directory))
            kwargs["port"] = 70000
            config = read_mailbox.DatabaseRunConfig(**kwargs)
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.validate_database_policy(config)
            self.assertEqual("config_invalid", caught.exception.code)

    def test_no_credential_shaped_key_in_the_shipped_database_table(self):
        raw = tomllib.loads((REPO_ROOT / "vicmap.toml").read_text(encoding="utf-8"))
        database = raw["database"]
        for key in database:
            lowered = key.lower()
            for forbidden in ("passw", "secret", "token"):
                self.assertNotIn(forbidden, lowered, f"{key!r} looks credential-shaped")


def _staging_policy(**overrides) -> staging.StagingPolicy:
    kwargs = dict(
        host="127.0.0.1",
        port=5432,
        dbname="vicmap",
        user="vicmap_loader",
        staging_schema="vicmap_staging",
        publish_schema="vicmap",
        target_srid=7899,
        index_columns=("pfi",),
        gt=20000,
        connect_timeout_seconds=10,
        statement_timeout_seconds=3600,
        lock_timeout_seconds=30,
    )
    kwargs.update(overrides)
    return staging.StagingPolicy(**kwargs)


class StagingTableNameTest(unittest.TestCase):
    """No database. D-48's naming, and its two structural limits."""

    def test_happy_path_composes_and_casefolds(self):
        self.assertEqual(
            staging.staging_table_name("vmadd_address", "20260918T041500Z"),
            "vmadd_address_20260918t041500z",
        )

    def test_two_different_run_timestamps_produce_two_different_names(self):
        first = staging.staging_table_name("vmadd_address", "20260918T041500Z")
        second = staging.staging_table_name("vmadd_address", "20260919T041500Z")
        self.assertNotEqual(first, second)

    def test_over_length_result_raises_closed_failure(self):
        with self.assertRaises(staging.StagingFailure):
            staging.staging_table_name("a" * 60, "20260918T041500Z")

    def test_uppercase_charset_violation_raises_closed_failure(self):
        with self.assertRaises(staging.StagingFailure):
            staging.staging_table_name("VMADD", "20260918T041500Z")

    def test_hyphen_charset_violation_raises_closed_failure(self):
        with self.assertRaises(staging.StagingFailure):
            staging.staging_table_name("vm-add", "20260918T041500Z")


class LoadCommandConstructionTest(unittest.TestCase):
    """No database, no subprocess. Pure argv construction (D-41..D-52)."""

    def test_command_contains_every_required_flag_and_value(self):
        policy = _staging_policy()
        command = staging.build_ogr2ogr_command(
            dataset_path="/tmp/VMADD.gdb",
            layer_name="ADDRESS",
            staging_table="vmadd_address_20260918t041500z",
            policy=policy,
        )
        needed = [
            "SCHEMA=vicmap_staging",
            "GEOMETRY_NAME=geom",
            "FID=gid",
            "SPATIAL_INDEX=NONE",
            "LAUNDER=YES",
            "PRECISION=YES",
            "EPSG:7899",
            "PG_USE_COPY",
            "ONLY_BEST=YES",
            "ALLOW_BALLPARK=NO",
            "20000",
        ]
        for token in needed:
            with self.subTest(token=token):
                self.assertIn(token, command)

    def test_fail_closed_flags_use_the_ct_opt_form_gdal_actually_accepts(self):
        # 03-04's live verification found that --config OGR_CT_ONLY_BEST YES /
        # --config OGR_CT_ALLOW_BALLPARK NO are not real GDAL config options
        # (CPL_DEBUG=ON showed "Unknown configuration option" for both) --
        # PROHIB-09's fail-closed transform posture was silently a no-op.
        # The real GDAL 3.9+ syntax is -ct_opt NAME=VALUE. This pins that the
        # two ONLY_BEST/ALLOW_BALLPARK flags are passed through -ct_opt, not
        # a bare --config pair, and that neither the old option names nor a
        # bare "--config" precede them.
        policy = _staging_policy()
        command = staging.build_ogr2ogr_command(
            dataset_path="/tmp/VMADD.gdb",
            layer_name="ADDRESS",
            staging_table="vmadd_address_20260918t041500z",
            policy=policy,
        )
        for value in ("ONLY_BEST=YES", "ALLOW_BALLPARK=NO"):
            index = command.index(value)
            self.assertEqual(
                "-ct_opt",
                command[index - 1],
                f"{value} must be preceded by -ct_opt, not --config",
            )
        self.assertNotIn("OGR_CT_ONLY_BEST", command)
        self.assertNotIn("OGR_CT_ALLOW_BALLPARK", command)

    def test_nln_element_carries_the_bare_table_name_with_no_schema_dot(self):
        policy = _staging_policy()
        command = staging.build_ogr2ogr_command(
            dataset_path="/tmp/VMADD.gdb",
            layer_name="ADDRESS",
            staging_table="vmadd_address_20260918t041500z",
            policy=policy,
        )
        self.assertNotIn(".", command[command.index("-nln") + 1])

    def test_no_credential_in_the_returned_argv(self):
        sentinel = "sentinel-secret-9f3a"
        policy = _staging_policy()
        command = staging.build_ogr2ogr_command(
            dataset_path="/tmp/VMADD.gdb",
            layer_name="ADDRESS",
            staging_table="vmadd_address_20260918t041500z",
            policy=policy,
        )
        for element in command:
            self.assertNotIn(sentinel, element)

    def test_load_layer_passes_password_only_via_env_never_argv(self):
        sentinel = "sentinel-secret-9f3a"
        policy = _staging_policy()
        captured: dict[str, object] = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["env"] = kwargs.get("env")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as diagnostics_dir:
            with patch.object(staging.subprocess, "run", side_effect=fake_run):
                staging.load_layer(
                    dataset_path="/tmp/VMADD.gdb",
                    layer_name="ADDRESS",
                    staging_table="vmadd_address_20260918t041500z",
                    policy=policy,
                    password=sentinel,
                    diagnostics_dir=diagnostics_dir,
                )

        self.assertEqual(sentinel, captured["env"]["PGPASSWORD"])
        for element in captured["command"]:
            self.assertNotIn(sentinel, element)


class ConnectionSetupTest(unittest.TestCase):
    """No database. Regression guard for a bug 03-04's live verification
    found: PostgreSQL's ``SET`` is a utility statement, not DML, and rejects
    a bind parameter outright (``syntax error at or near "$1"``) -- there is
    no parameterized form of ``SET statement_timeout = %s``. Every real
    connection attempt failed with ``DatabaseConnectionFailed`` until this
    was fixed to compose the already-validated positive integer as an
    ``sql.Literal`` instead."""

    def test_set_statements_carry_no_bind_placeholder(self):
        policy = _staging_policy(
            statement_timeout_seconds=3600, lock_timeout_seconds=30
        )
        executed: list[str] = []

        class _FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def execute(self, query, params=None):
                # Mirrors psycopg.sql.Composed.as_string()'s job of turning
                # a composed SET statement into literal SQL text with no
                # driver-side parameter binding -- exactly what a real
                # connection's wire protocol requires for a SET statement.
                executed.append(query.as_string(None))
                self.params = params

        class _FakeConnection:
            def cursor(self):
                return _FakeCursor()

            def commit(self):
                pass

            def close(self):
                pass

        with patch.object(
            staging.psycopg, "connect", return_value=_FakeConnection()
        ):
            staging._connect(policy, "sentinel-secret-9f3a")

        self.assertEqual(2, len(executed))
        for statement in executed:
            self.assertNotIn("%s", statement)
            self.assertNotIn("$1", statement)
        self.assertIn("3600000", executed[0])
        self.assertIn("30000", executed[1])


class Ogr2ogrFlagOracleTest(unittest.TestCase):
    """No database. Differential oracle (D-51/PROHIB-09 regression guard):
    exercises the real installed ``ogr2ogr`` binary -- not another
    hand-written assertion sharing ``build_ogr2ogr_command``'s own
    reasoning -- to prove its ``-ct_opt`` flags are ones GDAL actually
    recognizes. 03-04's live verification found ``--config OGR_CT_ONLY_BEST
    YES`` / ``--config OGR_CT_ALLOW_BALLPARK NO`` are not real GDAL options:
    GDAL silently warned "Unknown configuration option" for both and
    proceeded with default (non-fail-closed) behavior, so PROHIB-09's
    fail-closed transform posture was never actually enforced. Skips
    cleanly, never fails, if ``ogr2ogr`` is not on ``PATH``."""

    def test_only_best_and_allow_ballpark_flags_are_recognized_by_the_real_binary(
        self,
    ):
        if shutil.which("ogr2ogr") is None:
            self.skipTest(
                "ogr2ogr not on PATH -- flag oracle check skipped, not failed"
            )

        policy = _staging_policy()
        full_command = staging.build_ogr2ogr_command(
            dataset_path="/tmp/VMADD.gdb",
            layer_name="ADDRESS",
            staging_table="vmadd_address_flag_oracle",
            policy=policy,
        )
        # Pull the exact -ct_opt pairs staging.py actually emits, rather
        # than re-typing them, so a future edit to build_ogr2ogr_command
        # cannot silently drift from what this oracle exercises.
        ct_opt_args: list[str] = []
        for index, element in enumerate(full_command):
            if element == "-ct_opt":
                ct_opt_args.extend((full_command[index], full_command[index + 1]))
        self.assertEqual(4, len(ct_opt_args), full_command)

        scratch_dir = Path(tempfile.mkdtemp(prefix="ogr2ogr-flag-oracle-"))
        self.addCleanup(shutil.rmtree, scratch_dir, ignore_errors=True)
        with zipfile.ZipFile(FIXTURE_ARCHIVE) as archive:
            archive.extractall(scratch_dir)
        candidates = list(scratch_dir.rglob("*.gdb"))
        self.assertEqual(1, len(candidates))
        dataset_path = candidates[0]
        output_path = scratch_dir / "flag_oracle_output.geojson"

        minimal_command = (
            ["ogr2ogr", "-f", "GeoJSON", str(output_path), str(dataset_path), "ADDRESS"]
            + ["-t_srs", f"EPSG:{policy.target_srid}"]
            + ct_opt_args
        )
        result = subprocess.run(
            minimal_command,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "CPL_DEBUG": "ON"},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("Unknown configuration option", result.stderr, result.stderr)


class DriverImportPolicyTest(unittest.TestCase):
    """No database. T-03 structural proof: staging.py alone touches a driver."""

    def test_staging_is_the_only_module_referencing_a_database_driver(self):
        package_dir = REPO_ROOT / "vicmap_acquire"
        forbidden_tokens = ("psycopg", "psycopg2", "sqlalchemy", "asyncpg", "pg8000")
        offending = []
        for path in sorted(package_dir.glob("*.py")):
            if path.name == "staging.py":
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                if token in text:
                    offending.append((path.name, token))
        self.assertEqual([], offending)

    def test_importing_staging_creates_no_runs_directory_and_completes_quickly(self):
        """Importing ``vicmap_acquire.staging`` performs no connection,
        subprocess, or filesystem work: no driver is loaded before the
        import line runs, the driver is present immediately afterward
        (proving the reference is real, not conditionally deferred), no
        ``runs/`` directory is created in a fresh empty cwd, and the whole
        import completes well inside a bounded timeout -- a real network
        connection attempt would not."""

        scratch_dir = Path(tempfile.mkdtemp(prefix="staging-import-"))
        self.addCleanup(shutil.rmtree, scratch_dir, ignore_errors=True)
        script = (
            "import sys\n"
            "assert 'psycopg' not in sys.modules, "
            "'psycopg already imported before the import line'\n"
            "import vicmap_acquire.staging\n"
            "assert 'psycopg' in sys.modules, "
            "'staging.py did not import its own declared driver'\n"
            "print('staging imported cleanly')\n"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=scratch_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("staging imported cleanly", result.stdout)
        self.assertFalse((scratch_dir / "runs").exists())


class GeometryTypeNormalizationTest(unittest.TestCase):
    """No database. Pins every example in this plan's ``<interfaces>`` block
    plus the rejection cases -- must never skip."""

    def test_valid_examples_return_their_exact_pair(self):
        cases = {
            "Point": ("POINT", 0),
            "Point Z": ("POINTZ", 2),
            "Point M": ("POINTM", 1),
            "Point ZM": ("POINTZM", 3),
            "MultiPolygon": ("MULTIPOLYGON", 0),
            "LineString Z": ("LINESTRINGZ", 2),
        }
        for declared, expected in cases.items():
            with self.subTest(declared=declared):
                self.assertEqual(
                    expected, staging.normalize_declared_geometry_type(declared)
                )

    def test_lowercase_input_is_normalized(self):
        self.assertEqual(("POINT", 0), staging.normalize_declared_geometry_type("point"))

    def test_extra_internal_whitespace_is_tolerated(self):
        self.assertEqual(
            ("POINTZ", 2), staging.normalize_declared_geometry_type("Point   Z")
        )

    def test_invalid_examples_each_raise_geometry_type_mismatch(self):
        for declared in ("Unknown", "", None, "Point X", "Curve"):
            with self.subTest(declared=declared):
                with self.assertRaises(staging.GeometryTypeMismatch):
                    staging.normalize_declared_geometry_type(declared)


class ValidationQueryShapeTest(unittest.TestCase):
    """No database. Pins the single-pass D-56/D-57 query shape."""

    def test_spatial_query_contains_every_required_postgis_call(self):
        rendered = staging.build_validation_query(
            staging_schema="vicmap_staging", staging_table="t", spatial=True
        ).as_string(None)
        for token in (
            "ST_IsValid",
            "ST_MakeValid",
            "GeometryType",
            "ST_SRID",
            "ST_Zmflag",
            "ST_Extent",
        ):
            with self.subTest(token=token):
                self.assertIn(token, rendered)

    def test_non_spatial_query_contains_none_of_the_spatial_calls_and_a_row_count(self):
        rendered = staging.build_validation_query(
            staging_schema="vicmap_staging", staging_table="t", spatial=False
        ).as_string(None)
        for token in (
            "ST_IsValid",
            "ST_MakeValid",
            "GeometryType",
            "ST_SRID",
            "ST_Zmflag",
            "ST_Extent",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, rendered)
        self.assertIn("count", rendered.lower())

    def test_both_queries_quote_schema_and_table_as_separate_identifiers(self):
        spatial_rendered = staging.build_validation_query(
            staging_schema="vicmap_staging", staging_table="t", spatial=True
        ).as_string(None)
        flat_rendered = staging.build_validation_query(
            staging_schema="vicmap_staging", staging_table="t", spatial=False
        ).as_string(None)
        for rendered in (spatial_rendered, flat_rendered):
            self.assertIn('"vicmap_staging"."t"', rendered)

    def test_double_quote_in_identifier_is_escaped_not_broken(self):
        rendered = staging.build_validation_query(
            staging_schema="vicmap_staging",
            staging_table='wei"rd',
            spatial=False,
        ).as_string(None)
        self.assertIn('"wei""rd"', rendered)

    def test_repair_statement_is_an_update_restricted_to_invalid_rows(self):
        rendered = staging.build_repair_statement(
            staging_schema="vicmap_staging", staging_table="t"
        ).as_string(None)
        self.assertIn("UPDATE", rendered)
        self.assertIn("ST_MakeValid", rendered)
        self.assertIn("WHERE NOT ST_IsValid", rendered)
        self.assertIn('"vicmap_staging"."t"', rendered)


def _profile_with_fields(**overrides) -> LayerProfile:
    kwargs = dict(
        dataset_relative_path="x.gdb",
        dataset_stem="x",
        layer_name="LAYER",
        driver="OpenFileGDB",
        spatial=True,
        geometry_type="Point",
        geometry_column="geom",
        fid_column="gid",
        feature_count=1,
        source_wkt=None,
        epsg=7899,
        extent=None,
        fields=(),
    )
    kwargs.update(overrides)
    return LayerProfile(**kwargs)


def _field(name: str) -> FieldProfile:
    return FieldProfile(name=name, ogr_type="String", width=10, precision=None, nullable=True)


class SecondaryIndexAllowlistTest(unittest.TestCase):
    """No database. D-64's pure allowlist decision -- must never skip."""

    def test_declared_field_matching_allowlist_yields_the_column(self):
        layer = ManifestLayer(
            profile=_profile_with_fields(fields=(_field("PFI"),)), target_table="x"
        )
        policy = _staging_policy(index_columns=("pfi",))
        self.assertEqual(
            ("pfi",), staging.secondary_index_columns(layer, policy)
        )

    def test_lowercase_declared_field_matches_the_same_way(self):
        layer = ManifestLayer(
            profile=_profile_with_fields(fields=(_field("pfi"),)), target_table="x"
        )
        policy = _staging_policy(index_columns=("pfi",))
        self.assertEqual(
            ("pfi",), staging.secondary_index_columns(layer, policy)
        )

    def test_no_matching_field_yields_empty_tuple_and_raises_nothing(self):
        layer = ManifestLayer(
            profile=_profile_with_fields(fields=(_field("EZI_ADDRESS"),)),
            target_table="x",
        )
        policy = _staging_policy(index_columns=("pfi",))
        self.assertEqual((), staging.secondary_index_columns(layer, policy))

    def test_two_entry_allowlist_with_one_declared_yields_only_that_one(self):
        layer = ManifestLayer(
            profile=_profile_with_fields(fields=(_field("PFI"),)), target_table="x"
        )
        policy = _staging_policy(index_columns=("pfi", "ufi"))
        self.assertEqual(("pfi",), staging.secondary_index_columns(layer, policy))

    def test_non_spatial_layer_is_treated_identically(self):
        layer = ManifestLayer(
            profile=_profile_with_fields(
                spatial=False,
                geometry_type=None,
                geometry_column=None,
                fields=(_field("PFI"),),
            ),
            target_table="x",
        )
        policy = _staging_policy(index_columns=("pfi",))
        self.assertEqual(("pfi",), staging.secondary_index_columns(layer, policy))


class _LivePostgresMixin:
    """Copied from ``tests.test_naming.PostgresKeywordOracleTest._connect`` --
    same ``VICMAP_TEST_POSTGRES_DSN`` env var, same 2-second connect timeout,
    same psycopg-then-psycopg2 import fallback, same ``skipTest`` on both the
    missing-driver and unreachable-server paths. No test using this mixin may
    require a reachable PostgreSQL server or an installed driver to pass."""

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
                    "live staging check skipped, not failed"
                )

        dsn = os.environ.get(self._DSN_ENV_VAR)
        try:
            if dsn:
                connection = _driver.connect(
                    dsn, connect_timeout=self._CONNECT_TIMEOUT_SECONDS
                )
            else:
                connection = _driver.connect(
                    dbname="postgres", connect_timeout=self._CONNECT_TIMEOUT_SECONDS
                )
        except Exception as exc:  # noqa: BLE001 -- any connect failure just skips
            self.skipTest(
                f"no reachable PostgreSQL server for live staging check: {exc}"
            )
        return connection

    def _connection_params(self) -> dict[str, object]:
        """Structured host/port/dbname/user/password for a ``StagingPolicy``,
        parsed from ``VICMAP_TEST_POSTGRES_DSN`` (or this mixin's own
        local-default, mirroring ``_connect``). Only ever called after
        ``_connect`` has already proven the driver is importable."""

        from psycopg.conninfo import conninfo_to_dict

        dsn = os.environ.get(self._DSN_ENV_VAR)
        parsed = conninfo_to_dict(dsn) if dsn else {}
        return {
            "host": str(parsed.get("host") or "127.0.0.1"),
            "port": int(parsed.get("port") or 5432),
            "dbname": str(parsed.get("dbname") or "postgres"),
            "user": str(parsed.get("user") or os.environ.get("USER") or "postgres"),
            "password": str(parsed.get("password") or ""),
        }


class ConnectionIdentityTest(_LivePostgresMixin, unittest.TestCase):
    """Skips without a server. DB-01/D-61."""

    def test_identity_reports_all_six_fields_lowercase_and_no_fingerprint_key(self):
        self._connect().close()
        params = self._connection_params()
        policy = _staging_policy(
            host=params["host"],
            port=params["port"],
            dbname=params["dbname"],
            user=params["user"],
            connect_timeout_seconds=self._CONNECT_TIMEOUT_SECONDS,
        )
        identity = staging.read_database_identity(policy, password=params["password"])

        self.assertTrue(identity.host)
        self.assertTrue(identity.port)
        self.assertTrue(identity.dbname)
        self.assertTrue(identity.role)
        self.assertTrue(identity.server_version)
        self.assertTrue(identity.postgis_version)
        self.assertEqual(identity.dbname, identity.dbname.lower())
        self.assertEqual(identity.role, identity.role.lower())

        event = SuccessEvent.database_identity(
            host=identity.host,
            port=identity.port,
            dbname=identity.dbname,
            role=identity.role,
            server_version=identity.server_version,
            postgis_version=identity.postgis_version,
        )
        rendered = json.dumps(dict(event))
        self.assertNotRegex(rendered, r'"[A-Za-z_]*fingerprint[A-Za-z_]*"')


class LoadIntegrationTest(_LivePostgresMixin, unittest.TestCase):
    """Skips without a server. DB-03/D-45/D-46/D-49, and production isolation.

    Loads into a throwaway TABLE inside ``vicmap_staging`` -- never a new
    schema. ``vicmap_loader`` owns ``vicmap_staging`` (D-59) and already
    holds ``CREATE`` there; a throwaway *schema* needs database-level
    ``CREATE``, which D-59/DB-05 deliberately denies ``vicmap_loader``.
    Pointed at the real role, this test's earlier ``CREATE SCHEMA`` form
    ERRORed with a permission-denied failure rather than skipping cleanly
    (see 03-04-SUMMARY.md and WINDOWS.md's now-resolved entry) -- that was a
    defect in the test's own fixture, not in the provisioning; this table-
    scoped form needs no privilege ``vicmap_loader`` does not already have."""

    def setUp(self):
        self.scratch_dir = Path(tempfile.mkdtemp(prefix="staging-load-"))
        self.addCleanup(shutil.rmtree, self.scratch_dir, ignore_errors=True)
        with zipfile.ZipFile(FIXTURE_ARCHIVE) as archive:
            archive.extractall(self.scratch_dir)
        candidates = list(self.scratch_dir.rglob("*.gdb"))
        self.assertEqual(1, len(candidates))
        self.dataset_path = candidates[0]

    def _drop_table(self, connection, table_name: str) -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    staging.sql.SQL("DROP TABLE IF EXISTS {table}").format(
                        table=staging.sql.Identifier("vicmap_staging", table_name)
                    )
                )
            connection.commit()
        finally:
            connection.close()

    def test_load_creates_table_with_expected_rows_columns_and_no_public_leak(self):
        connection = self._connect()
        params = self._connection_params()

        table_name = f"staging_load_test_{os.getpid()}"
        with connection.cursor() as cursor:
            cursor.execute(
                staging.sql.SQL("DROP TABLE IF EXISTS {table}").format(
                    table=staging.sql.Identifier("vicmap_staging", table_name)
                )
            )
        connection.commit()
        self.addCleanup(self._drop_table, connection, table_name)

        policy = _staging_policy(
            host=params["host"],
            port=params["port"],
            dbname=params["dbname"],
            user=params["user"],
            connect_timeout_seconds=self._CONNECT_TIMEOUT_SECONDS,
        )

        staging.load_layer(
            dataset_path=self.dataset_path,
            layer_name="ADDRESS",
            staging_table=table_name,
            policy=policy,
            password=params["password"],
            diagnostics_dir=self.scratch_dir,
        )

        with connection.cursor() as verify_cursor:
            verify_cursor.execute(
                staging.sql.SQL("SELECT COUNT(*) FROM {table}").format(
                    table=staging.sql.Identifier("vicmap_staging", table_name)
                )
            )
            (row_count,) = verify_cursor.fetchone()
            verify_cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                ("vicmap_staging", table_name),
            )
            columns = {row[0] for row in verify_cursor.fetchall()}
            verify_cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename = %s",
                (table_name,),
            )
            public_hit = verify_cursor.fetchone()

        self.assertEqual(2, row_count)
        self.assertIn("geom", columns)
        self.assertIn("gid", columns)
        self.assertIsNone(public_hit)


class PrivilegePreflightTest(_LivePostgresMixin, unittest.TestCase):
    """Exercises DB-02's full proof -- one pass path, four fail paths --
    against a throwaway role and schema this test itself creates through a
    separate superuser connection, and drops in ``tearDown``. Skips cleanly,
    never fails, without a PostgreSQL driver, without a reachable ordinary
    connection (``VICMAP_TEST_POSTGRES_DSN``), or without
    ``VICMAP_TEST_POSTGRES_SUPERUSER_DSN`` naming a reachable superuser
    connection. Drops no object it did not itself create."""

    _SUPERUSER_DSN_ENV_VAR = "VICMAP_TEST_POSTGRES_SUPERUSER_DSN"

    def setUp(self):
        self._connect().close()  # proves driver + ordinary server, or skips
        params = self._connection_params()
        self.host = params["host"]
        self.port = params["port"]
        self.dbname = params["dbname"]

        superuser_dsn = os.environ.get(self._SUPERUSER_DSN_ENV_VAR)
        if not superuser_dsn:
            self.skipTest(
                f"{self._SUPERUSER_DSN_ENV_VAR} not set -- privilege "
                "preflight check skipped, not failed"
            )

        import psycopg
        from psycopg.conninfo import conninfo_to_dict

        try:
            connection = psycopg.connect(
                superuser_dsn, connect_timeout=self._CONNECT_TIMEOUT_SECONDS
            )
        except Exception as exc:  # noqa: BLE001 -- any connect failure just skips
            self.skipTest(
                f"no reachable PostgreSQL superuser connection for "
                f"privilege preflight check: {exc}"
            )
        connection.autocommit = True
        self.superuser_connection = connection

        parsed = conninfo_to_dict(superuser_dsn)
        self.superuser_password = str(parsed.get("password") or "")

        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            (self.superuser_role,) = cursor.fetchone()

        pid = os.getpid()
        self.role_name = f"staging_preflight_role_{pid}"
        self.schema_name = f"staging_preflight_schema_{pid}"
        self.role_password = "preflight-test-password-9f3a"
        self._granted_public_create = False

        with connection.cursor() as cursor:
            cursor.execute(
                staging.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    staging.sql.Identifier(self.schema_name)
                )
            )
            cursor.execute(
                staging.sql.SQL("DROP ROLE IF EXISTS {}").format(
                    staging.sql.Identifier(self.role_name)
                )
            )
            cursor.execute(
                staging.sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(
                    staging.sql.Identifier(self.role_name)
                ),
                (self.role_password,),
            )
            cursor.execute(
                staging.sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                    staging.sql.Identifier(self.schema_name),
                    staging.sql.Identifier(self.role_name),
                )
            )

    def tearDown(self):
        connection = getattr(self, "superuser_connection", None)
        if connection is None:
            return
        try:
            with connection.cursor() as cursor:
                if self._granted_public_create:
                    cursor.execute(
                        staging.sql.SQL(
                            "REVOKE CREATE ON SCHEMA public FROM {}"
                        ).format(staging.sql.Identifier(self.role_name))
                    )
                cursor.execute(
                    staging.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        staging.sql.Identifier(self.schema_name)
                    )
                )
                cursor.execute(
                    staging.sql.SQL("DROP ROLE IF EXISTS {}").format(
                        staging.sql.Identifier(self.role_name)
                    )
                )
        finally:
            connection.close()

    def _policy(self, **overrides) -> staging.StagingPolicy:
        kwargs = dict(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.role_name,
            staging_schema=self.schema_name,
            publish_schema="vicmap",
            target_srid=7899,
            index_columns=("pfi",),
            gt=20000,
            connect_timeout_seconds=self._CONNECT_TIMEOUT_SECONDS,
            statement_timeout_seconds=3600,
            lock_timeout_seconds=30,
        )
        kwargs.update(overrides)
        return staging.StagingPolicy(**kwargs)

    def test_pass_path_proves_capability_and_leaves_nothing_behind(self):
        staging.preflight_staging_privileges(
            self._policy(), password=self.role_password
        )
        with self.superuser_connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass(%s)",
                (f"{self.schema_name}.{staging.PROBE_TABLE_NAME}",),
            )
            (probe_table,) = cursor.fetchone()
        self.assertIsNone(probe_table)

    def test_fail_path_no_create_on_staging_schema(self):
        with self.superuser_connection.cursor() as cursor:
            cursor.execute(
                staging.sql.SQL("REVOKE CREATE ON SCHEMA {} FROM {}").format(
                    staging.sql.Identifier(self.schema_name),
                    staging.sql.Identifier(self.role_name),
                )
            )
        with self.assertRaises(staging.PrivilegeDenied):
            staging.preflight_staging_privileges(
                self._policy(), password=self.role_password
            )

    def test_fail_path_create_on_public(self):
        with self.superuser_connection.cursor() as cursor:
            cursor.execute(
                staging.sql.SQL("GRANT CREATE ON SCHEMA public TO {}").format(
                    staging.sql.Identifier(self.role_name)
                )
            )
        self._granted_public_create = True
        with self.assertRaises(staging.PrivilegeDenied):
            staging.preflight_staging_privileges(
                self._policy(), password=self.role_password
            )

    def test_fail_path_superuser(self):
        with self.assertRaises(staging.PrivilegeDenied):
            staging.preflight_staging_privileges(
                self._policy(user=self.superuser_role),
                password=self.superuser_password,
            )

    def test_fail_path_unknown_srid(self):
        with self.superuser_connection.cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(srid), 0) FROM spatial_ref_sys")
            (max_srid,) = cursor.fetchone()
        unknown_srid = min(int(max_srid) + 1, 998999)
        with self.assertRaises(staging.TargetSridUnresolved):
            staging.preflight_staging_privileges(
                self._policy(target_srid=unknown_srid), password=self.role_password
            )


class ValidationTest(_LivePostgresMixin, unittest.TestCase):
    """Skips without a server. DB-04: the full ``validate_layer`` contract,
    exercised against real geometry this test writes into a throwaway
    TABLE it creates and drops itself, inside ``vicmap_staging`` -- never a
    new schema. ``validate_layer`` never calls
    ``preflight_staging_privileges``, and ``vicmap_loader`` already holds
    ``CREATE`` on its own staging schema (D-59); creating a table there
    needs no elevated privilege, unlike a throwaway *schema* (see
    ``LoadIntegrationTest``'s docstring and WINDOWS.md's now-resolved entry
    for the identical defect that pattern used to hit). This class
    therefore needs only ``VICMAP_TEST_POSTGRES_DSN``, not a superuser DSN."""

    def setUp(self):
        self._connect().close()  # proves driver + reachable server, or skips
        self.params = self._connection_params()
        self._table_counter = 0
        self._created_tables: list[str] = []
        self.addCleanup(self._drop_created_tables)

    def _drop_created_tables(self) -> None:
        if not self._created_tables:
            return
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                for table_name in self._created_tables:
                    cursor.execute(
                        staging.sql.SQL("DROP TABLE IF EXISTS {table}").format(
                            table=staging.sql.Identifier("vicmap_staging", table_name)
                        )
                    )
            connection.commit()
        finally:
            connection.close()

    def _policy(self, **overrides) -> staging.StagingPolicy:
        kwargs = dict(
            host=self.params["host"],
            port=self.params["port"],
            dbname=self.params["dbname"],
            user=self.params["user"],
            staging_schema="vicmap_staging",
            publish_schema="vicmap",
            target_srid=7899,
            index_columns=("pfi",),
            gt=20000,
            connect_timeout_seconds=self._CONNECT_TIMEOUT_SECONDS,
            statement_timeout_seconds=3600,
            lock_timeout_seconds=30,
        )
        kwargs.update(overrides)
        return staging.StagingPolicy(**kwargs)

    def _manifest_layer(self, **overrides) -> ManifestLayer:
        kwargs = dict(
            dataset_relative_path="x.gdb",
            dataset_stem="x",
            layer_name="LAYER",
            driver="OpenFileGDB",
            spatial=True,
            geometry_type="Point",
            geometry_column="geom",
            fid_column="gid",
            feature_count=1,
            source_wkt=None,
            epsg=7899,
            extent=None,
            fields=(),
        )
        kwargs.update(overrides)
        profile = LayerProfile(**kwargs)
        return ManifestLayer(profile=profile, target_table="x")

    def _new_table_name(self, case: str) -> str:
        self._table_counter += 1
        name = f"claude_validation_test_{os.getpid()}_{self._table_counter}_{case}"
        self._created_tables.append(name)
        return name

    def _create_geometry_table(
        self, table_name: str, rows: list[tuple[str | None, int | None]]
    ) -> None:
        connection = self._connect()
        try:
            table_ref = staging.sql.Identifier("vicmap_staging", table_name)
            with connection.cursor() as cursor:
                cursor.execute(
                    staging.sql.SQL(
                        "CREATE TABLE {table} (gid serial PRIMARY KEY, geom geometry)"
                    ).format(table=table_ref)
                )
                for wkt, srid in rows:
                    if wkt is None:
                        cursor.execute(
                            staging.sql.SQL(
                                "INSERT INTO {table} (geom) VALUES (NULL)"
                            ).format(table=table_ref)
                        )
                    else:
                        cursor.execute(
                            staging.sql.SQL(
                                "INSERT INTO {table} (geom) VALUES (ST_GeomFromText(%s, %s))"
                            ).format(table=table_ref),
                            (wkt, srid),
                        )
            connection.commit()
        finally:
            connection.close()

    def _create_non_spatial_table(self, table_name: str, row_count: int) -> None:
        connection = self._connect()
        try:
            table_ref = staging.sql.Identifier("vicmap_staging", table_name)
            with connection.cursor() as cursor:
                cursor.execute(
                    staging.sql.SQL(
                        "CREATE TABLE {table} (gid serial PRIMARY KEY, name text)"
                    ).format(table=table_ref)
                )
                for index in range(row_count):
                    cursor.execute(
                        staging.sql.SQL(
                            "INSERT INTO {table} (name) VALUES (%s)"
                        ).format(table=table_ref),
                        (f"row{index}",),
                    )
            connection.commit()
        finally:
            connection.close()

    def test_clean_spatial_layer_returns_full_record(self):
        table = self._new_table_name("clean")
        self._create_geometry_table(table, [("POINT(144.9 -37.8)", 7899)] * 3)
        manifest_layer = self._manifest_layer(feature_count=3, geometry_type="Point")
        result = staging.validate_layer(
            manifest_layer=manifest_layer,
            staging_table=table,
            policy=self._policy(),
            password=self.params["password"],
        )
        self.assertEqual(3, result.row_count)
        self.assertEqual("POINT", result.geometry_type)
        self.assertEqual(7899, result.srid)
        self.assertEqual(0, result.repaired_count)
        self.assertEqual(4, len(result.extent))

    def test_row_count_mismatch_raises(self):
        table = self._new_table_name("rowcount")
        self._create_geometry_table(table, [("POINT(1 1)", 7899)] * 2)
        manifest_layer = self._manifest_layer(feature_count=3, geometry_type="Point")
        with self.assertRaises(staging.RowCountMismatch):
            staging.validate_layer(
                manifest_layer=manifest_layer,
                staging_table=table,
                policy=self._policy(),
                password=self.params["password"],
            )

    def test_wrong_srid_raises(self):
        table = self._new_table_name("wrongsrid")
        self._create_geometry_table(table, [("POINT(1 1)", 4326)])
        manifest_layer = self._manifest_layer(feature_count=1, geometry_type="Point")
        with self.assertRaises(staging.SridMismatch):
            staging.validate_layer(
                manifest_layer=manifest_layer,
                staging_table=table,
                policy=self._policy(),
                password=self.params["password"],
            )

    def test_mixed_srid_raises(self):
        table = self._new_table_name("mixedsrid")
        self._create_geometry_table(
            table, [("POINT(1 1)", 7899), ("POINT(1 1)", 4326)]
        )
        manifest_layer = self._manifest_layer(feature_count=2, geometry_type="Point")
        with self.assertRaises(staging.SridMismatch):
            staging.validate_layer(
                manifest_layer=manifest_layer,
                staging_table=table,
                policy=self._policy(),
                password=self.params["password"],
            )

    def test_wrong_geometry_type_raises(self):
        table = self._new_table_name("wrongtype")
        self._create_geometry_table(table, [("POINT(1 1)", 7899)])
        manifest_layer = self._manifest_layer(feature_count=1, geometry_type="Polygon")
        with self.assertRaises(staging.GeometryTypeMismatch):
            staging.validate_layer(
                manifest_layer=manifest_layer,
                staging_table=table,
                policy=self._policy(),
                password=self.params["password"],
            )

    def test_dimensionality_mismatch_raises(self):
        # A POINTZ table declared as plain Point: GeometryType() alone
        # cannot catch this (live verification found it reports bare
        # 'POINT' for both), so this pins that ST_Zmflag is what actually
        # raises the mismatch. See normalize_declared_geometry_type's
        # docstring in staging.py for the full live finding.
        table = self._new_table_name("dimension")
        self._create_geometry_table(table, [("POINT Z (1 1 1)", 7899)])
        manifest_layer = self._manifest_layer(feature_count=1, geometry_type="Point")
        with self.assertRaises(staging.GeometryTypeMismatch):
            staging.validate_layer(
                manifest_layer=manifest_layer,
                staging_table=table,
                policy=self._policy(),
                password=self.params["password"],
            )

    def test_null_geometry_raises(self):
        table = self._new_table_name("nullgeom")
        self._create_geometry_table(table, [("POINT(1 1)", 7899), (None, None)])
        manifest_layer = self._manifest_layer(feature_count=2, geometry_type="Point")
        with self.assertRaises(staging.GeometryTypeMismatch):
            staging.validate_layer(
                manifest_layer=manifest_layer,
                staging_table=table,
                policy=self._policy(),
                password=self.params["password"],
            )

    def test_non_spatial_layer_reports_not_applicable(self):
        table = self._new_table_name("nonspatial")
        self._create_non_spatial_table(table, 2)
        manifest_layer = self._manifest_layer(
            feature_count=2,
            geometry_type=None,
            spatial=False,
            geometry_column=None,
        )
        result = staging.validate_layer(
            manifest_layer=manifest_layer,
            staging_table=table,
            policy=self._policy(),
            password=self.params["password"],
        )
        self.assertEqual(2, result.row_count)
        self.assertEqual(staging.NOT_APPLICABLE, result.geometry_type)
        self.assertEqual(staging.NOT_APPLICABLE, result.srid)
        self.assertEqual(staging.NOT_APPLICABLE, result.repaired_count)
        self.assertEqual(staging.NOT_APPLICABLE, result.extent)

    def _pick_repair_candidates(self) -> tuple[str | None, str | None]:
        """Ask the server itself which known-invalid WKT candidates repair
        type-preserving vs type-changing under ST_MakeValid, rather than
        hard-coding the answer -- this plan's explicit instruction, since
        GEOS's repair behavior for a given invalid shape is version-
        dependent."""

        candidates = [
            "POLYGON((0 0, 0 10, 10 10, 10 0, 0 0),(0 0, 0 10, 10 10, 10 0, 0 0))",
            "POLYGON((0 0, 1 1, 1 0, 0 1, 0 0))",
            "POLYGON((0 0, 4 0, 4 4, 2 0, 0 4, 0 0))",
            "POLYGON((0 0, 1 0, 2 0, 0 0))",
        ]
        preserving = None
        changing = None
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                for wkt in candidates:
                    cursor.execute(
                        "SELECT ST_IsValid(g), "
                        "GeometryType(ST_MakeValid(g)) = GeometryType(g) "
                        "FROM (SELECT ST_GeomFromText(%s, 7899) AS g) AS t",
                        (wkt,),
                    )
                    is_valid, preserves_type = cursor.fetchone()
                    if is_valid:
                        continue
                    if preserves_type and preserving is None:
                        preserving = wkt
                    if not preserves_type and changing is None:
                        changing = wkt
        finally:
            connection.close()
        return preserving, changing

    def test_repair_preserving_type_is_repaired_and_counted(self):
        preserving, _ = self._pick_repair_candidates()
        if preserving is None:
            self.skipTest(
                "no type-preserving invalid geometry candidate found on this server"
            )
        table = self._new_table_name("repairok")
        self._create_geometry_table(table, [(preserving, 7899)])
        manifest_layer = self._manifest_layer(feature_count=1, geometry_type="Polygon")
        result = staging.validate_layer(
            manifest_layer=manifest_layer,
            staging_table=table,
            policy=self._policy(),
            password=self.params["password"],
        )
        self.assertEqual(1, result.repaired_count)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    staging.sql.SQL(
                        "SELECT COUNT(*) FROM {table} WHERE NOT ST_IsValid(geom)"
                    ).format(table=staging.sql.Identifier("vicmap_staging", table))
                )
                (remaining,) = cursor.fetchone()
        finally:
            connection.close()
        self.assertEqual(0, remaining)

    def test_repair_changing_type_raises_and_writes_nothing(self):
        _, changing = self._pick_repair_candidates()
        if changing is None:
            self.skipTest(
                "no type-changing invalid geometry candidate found on this server"
            )
        table = self._new_table_name("repairbad")
        self._create_geometry_table(table, [(changing, 7899)])

        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    staging.sql.SQL("SELECT ST_AsBinary(geom) FROM {table}").format(
                        table=staging.sql.Identifier("vicmap_staging", table)
                    )
                )
                before = cursor.fetchall()
        finally:
            connection.close()

        manifest_layer = self._manifest_layer(feature_count=1, geometry_type="Polygon")
        with self.assertRaises(staging.GeometryRepairChangedType):
            staging.validate_layer(
                manifest_layer=manifest_layer,
                staging_table=table,
                policy=self._policy(),
                password=self.params["password"],
            )

        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    staging.sql.SQL("SELECT ST_AsBinary(geom) FROM {table}").format(
                        table=staging.sql.Identifier("vicmap_staging", table)
                    )
                )
                after = cursor.fetchall()
        finally:
            connection.close()
        self.assertEqual(before, after)


class ValidationOgrinfoOracleTest(_LivePostgresMixin, unittest.TestCase):
    """Skips without a server. The independent oracle CONTEXT.md names as
    this phase's verification aid: after loading the real
    ``Order_TRACER1.zip`` ADDRESS layer into a throwaway table inside
    ``vicmap_staging`` through the real ``load_layer``, runs ``ogrinfo``
    from the same pinned GDAL against the loaded table (via its ``PG:``
    connection string) and asserts its reported feature count, geometry
    type, and CRS agree with what ``validate_layer`` reported. A hand-
    written assertion against ``validate_layer``'s own query set would
    share that query set's blind spot; ``ogrinfo`` reads the table through
    a different code path entirely -- the same differential-oracle
    discipline ``test_discovery_differential.py`` and the live
    ``pg_get_keywords()`` check already apply elsewhere in this repository."""

    def setUp(self):
        self._connect().close()
        self.params = self._connection_params()
        self.scratch_dir = Path(tempfile.mkdtemp(prefix="ogrinfo-oracle-"))
        self.addCleanup(shutil.rmtree, self.scratch_dir, ignore_errors=True)
        with zipfile.ZipFile(FIXTURE_ARCHIVE) as archive:
            archive.extractall(self.scratch_dir)
        candidates = list(self.scratch_dir.rglob("*.gdb"))
        self.assertEqual(1, len(candidates))
        self.dataset_path = candidates[0]
        self.table_name = f"claude_ogrinfo_oracle_{os.getpid()}"
        self.addCleanup(self._drop_table)

    def _drop_table(self) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    staging.sql.SQL("DROP TABLE IF EXISTS {table}").format(
                        table=staging.sql.Identifier("vicmap_staging", self.table_name)
                    )
                )
            connection.commit()
        finally:
            connection.close()

    def test_ogrinfo_agrees_with_validate_layer(self):
        if shutil.which("ogrinfo") is None:
            self.skipTest("ogrinfo not on PATH -- oracle check skipped, not failed")

        policy = staging.StagingPolicy(
            host=self.params["host"],
            port=self.params["port"],
            dbname=self.params["dbname"],
            user=self.params["user"],
            staging_schema="vicmap_staging",
            publish_schema="vicmap",
            target_srid=7899,
            index_columns=("pfi",),
            gt=20000,
            connect_timeout_seconds=self._CONNECT_TIMEOUT_SECONDS,
            statement_timeout_seconds=3600,
            lock_timeout_seconds=30,
        )
        staging.load_layer(
            dataset_path=self.dataset_path,
            layer_name="ADDRESS",
            staging_table=self.table_name,
            policy=policy,
            password=self.params["password"],
            diagnostics_dir=self.scratch_dir,
        )

        manifest_layer = ManifestLayer(
            profile=LayerProfile(
                dataset_relative_path="ADDRESS.gdb",
                dataset_stem="ADDRESS",
                layer_name="ADDRESS",
                driver="OpenFileGDB",
                spatial=True,
                geometry_type="Point",
                geometry_column="geom",
                fid_column="gid",
                feature_count=2,
                source_wkt=None,
                epsg=7899,
                extent=None,
                fields=(),
            ),
            target_table="vmadd_address",
        )
        result = staging.validate_layer(
            manifest_layer=manifest_layer,
            staging_table=self.table_name,
            policy=policy,
            password=self.params["password"],
        )

        connection_string = (
            f"PG:dbname={self.params['dbname']} host={self.params['host']} "
            f"port={self.params['port']} user={self.params['user']} "
            "active_schema=vicmap_staging"
        )
        oracle_command = ["ogrinfo", "-json", "-so", connection_string, self.table_name]
        oracle_result = subprocess.run(
            oracle_command,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "PGPASSWORD": self.params["password"]},
        )
        self.assertEqual(0, oracle_result.returncode, oracle_result.stderr)
        payload = json.loads(oracle_result.stdout)
        layer_payload = payload["layers"][0]

        self.assertEqual(result.row_count, layer_payload["featureCount"])
        self.assertIn("Point", layer_payload["geometryFields"][0]["type"])
        identifier = layer_payload["geometryFields"][0]["coordinateSystem"]["projjson"]["id"]
        self.assertEqual("EPSG", identifier["authority"])
        self.assertEqual(result.srid, int(identifier["code"]))


class PostValidationDdlTest(_LivePostgresMixin, unittest.TestCase):
    """Skips without a server. D-62/D-63/D-64's full contract, exercised
    against a throwaway table this test creates and drops itself, inside
    ``vicmap_staging`` -- never a new schema (same reasoning as
    ``ValidationTest``: ``vicmap_loader`` already holds ``CREATE`` there,
    D-59, so no superuser DSN is needed)."""

    def setUp(self):
        self._connect().close()
        self.params = self._connection_params()
        self._table_counter = 0
        self._created_tables: list[str] = []
        self.addCleanup(self._drop_created_tables)

    def _drop_created_tables(self) -> None:
        if not self._created_tables:
            return
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                for table_name in self._created_tables:
                    cursor.execute(
                        staging.sql.SQL("DROP TABLE IF EXISTS {table}").format(
                            table=staging.sql.Identifier("vicmap_staging", table_name)
                        )
                    )
            connection.commit()
        finally:
            connection.close()

    def _new_table_name(self, case: str) -> str:
        self._table_counter += 1
        name = f"claude_ddl_test_{os.getpid()}_{self._table_counter}_{case}"
        self._created_tables.append(name)
        return name

    def _policy(self, **overrides) -> staging.StagingPolicy:
        kwargs = dict(
            host=self.params["host"],
            port=self.params["port"],
            dbname=self.params["dbname"],
            user=self.params["user"],
            staging_schema="vicmap_staging",
            publish_schema="vicmap",
            target_srid=7899,
            index_columns=("pfi",),
            gt=20000,
            connect_timeout_seconds=self._CONNECT_TIMEOUT_SECONDS,
            statement_timeout_seconds=3600,
            lock_timeout_seconds=30,
        )
        kwargs.update(overrides)
        return staging.StagingPolicy(**kwargs)

    def _manifest_layer(self, **overrides) -> ManifestLayer:
        kwargs = dict(
            dataset_relative_path="x.gdb",
            dataset_stem="x",
            layer_name="LAYER",
            driver="OpenFileGDB",
            spatial=True,
            geometry_type="Point",
            geometry_column="geom",
            fid_column="gid",
            feature_count=1,
            source_wkt=None,
            epsg=7899,
            extent=None,
            fields=(_field("PFI"),),
        )
        kwargs.update(overrides)
        return ManifestLayer(profile=LayerProfile(**kwargs), target_table="x")

    def _create_table(
        self,
        table_name: str,
        *,
        typed_geometry: bool,
        primary_key: bool,
        include_pfi: bool = True,
        spatial: bool = True,
    ) -> None:
        connection = self._connect()
        try:
            table_ref = staging.sql.Identifier("vicmap_staging", table_name)
            gid_sql = "gid integer PRIMARY KEY" if primary_key else "gid integer"
            columns = [gid_sql]
            if spatial:
                columns.append(
                    "geom geometry(Point, 7899)" if typed_geometry else "geom geometry"
                )
            if include_pfi:
                columns.append("pfi text")
            create_sql = "CREATE TABLE {table} (" + ", ".join(columns) + ")"
            insert_columns = ["gid"] + (["geom"] if spatial else []) + (
                ["pfi"] if include_pfi else []
            )
            insert_values = ["1"] + (
                ["ST_SetSRID(ST_MakePoint(144.9, -37.8), 7899)"] if spatial else []
            ) + (["'x'"] if include_pfi else [])
            insert_sql = (
                "INSERT INTO {table} (" + ", ".join(insert_columns) + ") VALUES ("
                + ", ".join(insert_values) + ")"
            )
            with connection.cursor() as cursor:
                cursor.execute(staging.sql.SQL(create_sql).format(table=table_ref))
                cursor.execute(staging.sql.SQL(insert_sql).format(table=table_ref))
            connection.commit()
        finally:
            connection.close()

    def _has_primary_key(self, table_name: str) -> bool:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM information_schema.table_constraints "
                    "WHERE table_schema = %s AND table_name = %s "
                    "AND constraint_type = 'PRIMARY KEY'",
                    ("vicmap_staging", table_name),
                )
                return cursor.fetchone() is not None
        finally:
            connection.close()

    def _index_names(self, table_name: str) -> set[str]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = %s AND tablename = %s",
                    ("vicmap_staging", table_name),
                )
                return {row[0] for row in cursor.fetchall()}
        finally:
            connection.close()

    def _gist_index_count(self, table_name: str) -> int:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM pg_indexes "
                    "WHERE schemaname = %s AND tablename = %s AND indexdef ILIKE %s",
                    ("vicmap_staging", table_name, "%USING gist%"),
                )
                (count,) = cursor.fetchone()
                return count
        finally:
            connection.close()

    def _geometry_column_info(self, table_name: str):
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT type, srid FROM geometry_columns WHERE f_table_schema = %s "
                    "AND f_table_name = %s AND f_geometry_column = 'geom'",
                    ("vicmap_staging", table_name),
                )
                return cursor.fetchone()
        finally:
            connection.close()

    def _geometry_column_not_null(self, table_name: str) -> bool:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s AND column_name = 'geom'",
                    ("vicmap_staging", table_name),
                )
                (is_nullable,) = cursor.fetchone()
                return is_nullable == "NO"
        finally:
            connection.close()

    def _validation(self, table_name: str, *, spatial: bool = True) -> staging.LayerValidation:
        if not spatial:
            return staging.LayerValidation(
                staging_table=table_name,
                spatial=False,
                row_count=1,
                geometry_type=staging.NOT_APPLICABLE,
                srid=staging.NOT_APPLICABLE,
                repaired_count=staging.NOT_APPLICABLE,
                extent=staging.NOT_APPLICABLE,
            )
        return staging.LayerValidation(
            staging_table=table_name,
            spatial=True,
            row_count=1,
            geometry_type="POINT",
            srid=7899,
            repaired_count=0,
            extent=(0.0, 0.0, 0.0, 0.0),
        )

    def test_primary_key_added_when_absent(self):
        table = self._new_table_name("nopk")
        self._create_table(table, typed_geometry=True, primary_key=False)
        created = staging.apply_post_validation_ddl(
            validation=self._validation(table),
            manifest_layer=self._manifest_layer(),
            staging_table=table,
            policy=self._policy(),
            password=self.params["password"],
        )
        self.assertIn(f"{table}_pkey", created)
        self.assertTrue(self._has_primary_key(table))

    def test_rerun_against_an_existing_primary_key_does_not_raise(self):
        table = self._new_table_name("haspk")
        self._create_table(table, typed_geometry=True, primary_key=True)
        created = staging.apply_post_validation_ddl(
            validation=self._validation(table),
            manifest_layer=self._manifest_layer(),
            staging_table=table,
            policy=self._policy(),
            password=self.params["password"],
        )
        self.assertNotIn(f"{table}_pkey", created)
        self.assertTrue(self._has_primary_key(table))

    def test_bare_geometry_column_is_typed_with_declared_type_and_srid(self):
        table = self._new_table_name("bare")
        self._create_table(table, typed_geometry=False, primary_key=False)
        created = staging.apply_post_validation_ddl(
            validation=self._validation(table),
            manifest_layer=self._manifest_layer(),
            staging_table=table,
            policy=self._policy(),
            password=self.params["password"],
        )
        self.assertIn(f"{table}_geom_typed", created)
        observed_type, observed_srid = self._geometry_column_info(table)
        self.assertEqual("POINT", observed_type)
        self.assertEqual(7899, observed_srid)

    def test_already_typed_column_needs_no_alter(self):
        table = self._new_table_name("typed")
        self._create_table(table, typed_geometry=True, primary_key=False)
        created = staging.apply_post_validation_ddl(
            validation=self._validation(table),
            manifest_layer=self._manifest_layer(),
            staging_table=table,
            policy=self._policy(),
            password=self.params["password"],
        )
        self.assertNotIn(f"{table}_geom_typed", created)
        observed_type, observed_srid = self._geometry_column_info(table)
        self.assertEqual("POINT", observed_type)
        self.assertEqual(7899, observed_srid)

    def test_geometry_column_is_not_null_afterwards(self):
        table = self._new_table_name("notnull")
        self._create_table(table, typed_geometry=True, primary_key=False)
        staging.apply_post_validation_ddl(
            validation=self._validation(table),
            manifest_layer=self._manifest_layer(),
            staging_table=table,
            policy=self._policy(),
            password=self.params["password"],
        )
        self.assertTrue(self._geometry_column_not_null(table))

    def test_exactly_one_gist_index_created_after_the_load_not_during(self):
        table = self._new_table_name("gist")
        self._create_table(table, typed_geometry=True, primary_key=False)
        created = staging.apply_post_validation_ddl(
            validation=self._validation(table),
            manifest_layer=self._manifest_layer(),
            staging_table=table,
            policy=self._policy(),
            password=self.params["password"],
        )
        self.assertIn(f"{table}_geom_gist", created)
        self.assertEqual(1, self._gist_index_count(table))
        command = staging.build_ogr2ogr_command(
            dataset_path="/tmp/x.gdb",
            layer_name="LAYER",
            staging_table=table,
            policy=self._policy(),
        )
        self.assertIn("SPATIAL_INDEX=NONE", command)

    def test_allowlisted_column_gets_a_btree_index_and_undeclared_does_not(self):
        table = self._new_table_name("allowlist")
        self._create_table(table, typed_geometry=True, primary_key=False, include_pfi=True)
        created = staging.apply_post_validation_ddl(
            validation=self._validation(table),
            manifest_layer=self._manifest_layer(fields=(_field("PFI"),)),
            staging_table=table,
            policy=self._policy(index_columns=("pfi", "ufi")),
            password=self.params["password"],
        )
        self.assertIn(f"{table}_pfi_idx", created)
        self.assertNotIn(f"{table}_ufi_idx", created)
        self.assertIn(f"{table}_pfi_idx", self._index_names(table))

    def test_no_allowlisted_column_declared_creates_no_secondary_index(self):
        table = self._new_table_name("noallowlist")
        self._create_table(table, typed_geometry=True, primary_key=False, include_pfi=False)
        created = staging.apply_post_validation_ddl(
            validation=self._validation(table),
            manifest_layer=self._manifest_layer(fields=()),
            staging_table=table,
            policy=self._policy(index_columns=("pfi",)),
            password=self.params["password"],
        )
        self.assertNotIn(f"{table}_pfi_idx", created)

    def test_non_spatial_layer_gets_only_primary_key_and_allowlisted_index(self):
        table = self._new_table_name("nonspatial")
        self._create_table(
            table, typed_geometry=False, primary_key=False, include_pfi=True, spatial=False
        )
        created = staging.apply_post_validation_ddl(
            validation=self._validation(table, spatial=False),
            manifest_layer=self._manifest_layer(
                spatial=False,
                geometry_type=None,
                geometry_column=None,
                fields=(_field("PFI"),),
            ),
            staging_table=table,
            policy=self._policy(),
            password=self.params["password"],
        )
        self.assertIn(f"{table}_pkey", created)
        self.assertIn(f"{table}_pfi_idx", created)
        for name in created:
            self.assertNotIn("geom", name)

    def test_induced_failure_leaves_no_constraints_or_indexes(self):
        # The table is already typed as Point, but the manifest declares
        # Polygon -- a genuine disagreement with what validate_layer would
        # already have asserted, so this must hard-stop rather than re-type.
        # No primary key exists yet, so this also proves the whole call is
        # one transaction: the PK step (which would otherwise succeed) is
        # rolled back together with the aborted geometry step.
        table = self._new_table_name("inducedfail")
        self._create_table(table, typed_geometry=True, primary_key=False)
        with self.assertRaises(staging.StagingDdlFailed):
            staging.apply_post_validation_ddl(
                validation=self._validation(table),
                manifest_layer=self._manifest_layer(geometry_type="Polygon"),
                staging_table=table,
                policy=self._policy(),
                password=self.params["password"],
            )
        self.assertFalse(self._has_primary_key(table))
        self.assertEqual(set(), self._index_names(table))

    def test_source_contains_no_concurrently(self):
        import inspect

        source = inspect.getsource(staging.apply_post_validation_ddl)
        self.assertNotIn("CONCURRENTLY", source)


class SequentialOrderTest(unittest.TestCase):
    """No database. Mocks ``load_layer``/``validate_layer``/
    ``apply_post_validation_ddl`` plus the pre-flight identity/privilege
    calls, and pins D-42's sequential, manifest-ordered, stop-at-first-
    failure orchestration. Must never skip."""

    _RUN_TIMESTAMP = "20260918T041500Z"

    @staticmethod
    def _identity() -> staging.DatabaseIdentity:
        return staging.DatabaseIdentity(
            host="127.0.0.1",
            port=5432,
            dbname="vicmap",
            role="vicmap_loader",
            server_version="PostgreSQL",
            postgis_version="POSTGIS",
        )

    @staticmethod
    def _manifest(layer_count: int) -> ImportManifest:
        layers = tuple(
            ManifestLayer(
                profile=_profile_with_fields(
                    dataset_relative_path=f"x{index}.gdb",
                    dataset_stem=f"x{index}",
                    layer_name=f"LAYER{index}",
                    feature_count=1,
                ),
                target_table=f"layer{index}",
            )
            for index in range(layer_count)
        )
        return ImportManifest(
            schema_version=1,
            order_id="OK0VUZ",
            run_timestamp="20260918T030000Z",
            run_directory="/tmp/run",
            artifact_sha256="a" * 64,
            artifact_byte_count=1,
            message_fingerprint="f" * 16,
            layers=layers,
            companions=(),
        )

    @staticmethod
    def _fake_validate(*, staging_table, **kwargs) -> staging.LayerValidation:
        return staging.LayerValidation(
            staging_table=staging_table,
            spatial=True,
            row_count=1,
            geometry_type="POINT",
            srid=7899,
            repaired_count=0,
            extent=(0.0, 0.0, 0.0, 0.0),
        )

    def test_three_layer_manifest_loads_in_manifest_order_with_progress(self):
        manifest = self._manifest(3)
        load_calls: list[str] = []
        events: list[object] = []
        expected = [
            staging.staging_table_name(layer.target_table, self._RUN_TIMESTAMP)
            for layer in manifest.layers
        ]

        with patch.object(
            staging, "read_database_identity", return_value=self._identity()
        ), patch.object(
            staging, "preflight_staging_privileges", return_value=None
        ), patch.object(
            staging,
            "load_layer",
            side_effect=lambda *, staging_table, **kwargs: load_calls.append(
                staging_table
            ),
        ), patch.object(
            staging, "validate_layer", side_effect=self._fake_validate
        ), patch.object(
            staging, "apply_post_validation_ddl", return_value=()
        ):
            result = staging.run_staging(
                manifest,
                _staging_policy(),
                password="x",
                run_timestamp=self._RUN_TIMESTAMP,
                diagnostics_dir="/tmp",
                event_sink=events.append,
            )

        self.assertEqual(expected, load_calls)
        self.assertEqual(3, len(result))
        progress = [
            (event["layer_position"], event["layer_total"])
            for event in events
            if isinstance(event, ProgressEvent)
        ]
        self.assertEqual([(1, 3), (2, 3), (3, 3)], progress)

    def test_load_failed_on_second_layer_stops_after_two_load_calls(self):
        manifest = self._manifest(3)
        load_calls: list[str] = []
        ddl_calls: list[str] = []

        def fake_load(*, staging_table, **kwargs):
            load_calls.append(staging_table)
            if len(load_calls) == 2:
                raise staging.LoadFailed()

        with patch.object(
            staging, "read_database_identity", return_value=self._identity()
        ), patch.object(
            staging, "preflight_staging_privileges", return_value=None
        ), patch.object(
            staging, "load_layer", side_effect=fake_load
        ), patch.object(
            staging, "validate_layer", side_effect=self._fake_validate
        ), patch.object(
            staging,
            "apply_post_validation_ddl",
            side_effect=lambda *, staging_table, **kwargs: ddl_calls.append(
                staging_table
            )
            or (),
        ):
            with self.assertRaises(staging.LoadFailed) as caught:
                staging.run_staging(
                    manifest,
                    _staging_policy(),
                    password="x",
                    run_timestamp=self._RUN_TIMESTAMP,
                    diagnostics_dir="/tmp",
                    event_sink=lambda event: None,
                )

        self.assertEqual(2, len(load_calls))
        self.assertLessEqual(len(ddl_calls), 1)
        expected_second = staging.staging_table_name(
            manifest.layers[1].target_table, self._RUN_TIMESTAMP
        )
        self.assertEqual(expected_second, caught.exception.staging_table)

    def test_one_layer_manifest_produces_exactly_one_load_call(self):
        manifest = self._manifest(1)
        load_calls: list[str] = []

        with patch.object(
            staging, "read_database_identity", return_value=self._identity()
        ), patch.object(
            staging, "preflight_staging_privileges", return_value=None
        ), patch.object(
            staging,
            "load_layer",
            side_effect=lambda *, staging_table, **kwargs: load_calls.append(
                staging_table
            ),
        ), patch.object(
            staging, "validate_layer", side_effect=self._fake_validate
        ), patch.object(
            staging, "apply_post_validation_ddl", return_value=()
        ):
            result = staging.run_staging(
                manifest,
                _staging_policy(),
                password="x",
                run_timestamp=self._RUN_TIMESTAMP,
                diagnostics_dir="/tmp",
                event_sink=lambda event: None,
            )

        self.assertEqual(1, len(load_calls))
        self.assertEqual(1, len(result))

    def test_zero_layer_manifest_produces_zero_calls_and_returns_empty_tuple(self):
        manifest = self._manifest(0)
        load_calls: list[str] = []

        with patch.object(
            staging, "read_database_identity", return_value=self._identity()
        ), patch.object(
            staging, "preflight_staging_privileges", return_value=None
        ), patch.object(
            staging,
            "load_layer",
            side_effect=lambda *, staging_table, **kwargs: load_calls.append(
                staging_table
            ),
        ), patch.object(
            staging, "validate_layer", side_effect=self._fake_validate
        ), patch.object(
            staging, "apply_post_validation_ddl", return_value=()
        ):
            result = staging.run_staging(
                manifest,
                _staging_policy(),
                password="x",
                run_timestamp=self._RUN_TIMESTAMP,
                diagnostics_dir="/tmp",
                event_sink=lambda event: None,
            )

        self.assertEqual((), result)
        self.assertEqual([], load_calls)


class LoadDiagnosticsTest(unittest.TestCase):
    """No database. Mocks ``subprocess.run``. D-43's stderr-to-file
    contract: the file gets everything, the exception and the rendered
    failure event get only the closed code and the file's bare name. Must
    never skip."""

    def test_failed_load_writes_diagnostics_file_and_leaks_nothing(self):
        policy = _staging_policy()
        stderr_text = (
            "ERROR: connection failed\n"
            "PGPASSWORD=sentinel-secret-9f3a\n"
            "detail: credential-shaped-token-abc123\n"
        )

        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, stdout="", stderr=stderr_text)

        with tempfile.TemporaryDirectory() as diagnostics_dir:
            with patch.object(staging.subprocess, "run", side_effect=fake_run):
                with self.assertRaises(staging.LoadFailed) as caught:
                    staging.load_layer(
                        dataset_path="/tmp/VMADD.gdb",
                        layer_name="ADDRESS",
                        staging_table="vmadd_address_20260918t041500z",
                        policy=policy,
                        password="sentinel-secret-9f3a",
                        diagnostics_dir=diagnostics_dir,
                    )
            error = caught.exception
            self.assertEqual("db_load_failed", str(error))
            self.assertNotIn("sentinel-secret-9f3a", str(error))
            self.assertNotIn("credential-shaped-token-abc123", str(error))

            expected_path = staging.diagnostics_path(
                diagnostics_dir, "vmadd_address_20260918t041500z"
            )
            self.assertTrue(expected_path.exists())
            self.assertEqual(stderr_text, expected_path.read_text(encoding="utf-8"))
            self.assertEqual(expected_path.name, error.diagnostics_file)

            failure_event = SafeFailure(
                ReasonCode.DB_LOAD_FAILED, diagnostics_file=error.diagnostics_file
            )
            rendered = json.dumps(dict(failure_event))
            self.assertNotIn("sentinel-secret-9f3a", rendered)
            self.assertNotIn("credential-shaped-token-abc123", rendered)
            self.assertIn(expected_path.name, rendered)


class ProductionIsolationTest(_LivePostgresMixin, unittest.TestCase):
    """Skips without a server. Proves PROHIB-10 empirically: an induced
    ``RowCountMismatch`` and an induced ``LoadFailed`` both leave every
    table outside ``vicmap_staging`` unchanged. This class must not drop
    anything it did not create."""

    def setUp(self):
        self._connect().close()
        self.params = self._connection_params()
        self.scratch_dir = Path(tempfile.mkdtemp(prefix="production-isolation-"))
        self.addCleanup(shutil.rmtree, self.scratch_dir, ignore_errors=True)
        with zipfile.ZipFile(FIXTURE_ARCHIVE) as archive:
            archive.extractall(self.scratch_dir)
        candidates = list(self.scratch_dir.rglob("*.gdb"))
        self.assertEqual(1, len(candidates))
        self.dataset_path = candidates[0]
        self._created_tables: list[str] = []
        self.addCleanup(self._drop_created_tables)

    def _drop_created_tables(self) -> None:
        if not self._created_tables:
            return
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                for table_name in self._created_tables:
                    cursor.execute(
                        staging.sql.SQL("DROP TABLE IF EXISTS {table}").format(
                            table=staging.sql.Identifier("vicmap_staging", table_name)
                        )
                    )
            connection.commit()
        finally:
            connection.close()

    def _catalog_snapshot(self):
        """Full (schema, table) list outside vicmap_staging -- catches a
        stray new table anywhere -- plus row counts scoped to public and
        the publish schema only, so an unrelated pg_catalog/information_
        schema row-count fluctuation (e.g. from this very test creating and
        dropping objects inside vicmap_staging, which pg_class also tracks)
        can never masquerade as a DB-05 violation."""

        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT schemaname, tablename FROM pg_tables "
                    "WHERE schemaname != 'vicmap_staging' ORDER BY schemaname, tablename"
                )
                tables = tuple(cursor.fetchall())
                counts = {}
                for schema, table in tables:
                    if schema not in ("public", "vicmap"):
                        continue
                    cursor.execute(
                        staging.sql.SQL("SELECT COUNT(*) FROM {table}").format(
                            table=staging.sql.Identifier(schema, table)
                        )
                    )
                    (count,) = cursor.fetchone()
                    counts[(schema, table)] = count
        finally:
            connection.close()
        return tables, counts

    def _policy(self) -> staging.StagingPolicy:
        return staging.StagingPolicy(
            host=self.params["host"],
            port=self.params["port"],
            dbname=self.params["dbname"],
            user=self.params["user"],
            staging_schema="vicmap_staging",
            publish_schema="vicmap",
            target_srid=7899,
            index_columns=("pfi",),
            gt=20000,
            connect_timeout_seconds=self._CONNECT_TIMEOUT_SECONDS,
            statement_timeout_seconds=3600,
            lock_timeout_seconds=30,
        )

    def _manifest(self, target_table: str, **layer_overrides) -> ImportManifest:
        kwargs = dict(
            dataset_relative_path=str(self.dataset_path.relative_to(self.scratch_dir)),
            dataset_stem=self.dataset_path.stem,
            layer_name="ADDRESS",
            driver="OpenFileGDB",
            spatial=True,
            geometry_type="Point",
            geometry_column="geom",
            fid_column="gid",
            feature_count=2,
            source_wkt=None,
            epsg=7899,
            extent=None,
            fields=(),
        )
        kwargs.update(layer_overrides)
        layer = ManifestLayer(profile=LayerProfile(**kwargs), target_table=target_table)
        return ImportManifest(
            schema_version=1,
            order_id="OK0VUZ",
            run_timestamp="20260918T041500Z",
            run_directory=str(self.scratch_dir),
            artifact_sha256="a" * 64,
            artifact_byte_count=1,
            message_fingerprint="f" * 16,
            layers=(layer,),
            companions=(),
        )

    def test_induced_row_count_mismatch_leaves_catalog_unchanged(self):
        target_table = f"claude_isolation_rowcount_{os.getpid()}"
        run_timestamp = "20260918T041500Z"
        self._created_tables.append(
            staging.staging_table_name(target_table, run_timestamp)
        )
        before_tables, before_counts = self._catalog_snapshot()

        manifest = self._manifest(target_table, feature_count=999999)
        with self.assertRaises(staging.RowCountMismatch):
            staging.run_staging(
                manifest,
                self._policy(),
                password=self.params["password"],
                run_timestamp=run_timestamp,
                diagnostics_dir=self.scratch_dir,
                event_sink=lambda event: None,
            )

        after_tables, after_counts = self._catalog_snapshot()
        self.assertEqual(before_tables, after_tables)
        self.assertEqual(before_counts, after_counts)

    def test_induced_load_failure_leaves_catalog_unchanged(self):
        target_table = f"claude_isolation_loadfail_{os.getpid()}"
        run_timestamp = "20260918T041500Z"
        self._created_tables.append(
            staging.staging_table_name(target_table, run_timestamp)
        )
        before_tables, before_counts = self._catalog_snapshot()

        manifest = self._manifest(
            target_table,
            dataset_relative_path="does/not/exist.gdb",
            feature_count=2,
        )
        with self.assertRaises(staging.LoadFailed):
            staging.run_staging(
                manifest,
                self._policy(),
                password=self.params["password"],
                run_timestamp=run_timestamp,
                diagnostics_dir=self.scratch_dir,
                event_sink=lambda event: None,
            )

        after_tables, after_counts = self._catalog_snapshot()
        self.assertEqual(before_tables, after_tables)
        self.assertEqual(before_counts, after_counts)


if __name__ == "__main__":
    unittest.main()
