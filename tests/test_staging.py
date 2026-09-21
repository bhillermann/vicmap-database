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
from vicmap_acquire.evidence import SuccessEvent


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
            "OGR_CT_ONLY_BEST",
            "OGR_CT_ALLOW_BALLPARK",
            "20000",
        ]
        for token in needed:
            with self.subTest(token=token):
                self.assertIn(token, command)

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
    """Skips without a server. DB-03/D-45/D-46/D-49, and production isolation."""

    def setUp(self):
        self.scratch_dir = Path(tempfile.mkdtemp(prefix="staging-load-"))
        self.addCleanup(shutil.rmtree, self.scratch_dir, ignore_errors=True)
        with zipfile.ZipFile(FIXTURE_ARCHIVE) as archive:
            archive.extractall(self.scratch_dir)
        candidates = list(self.scratch_dir.rglob("*.gdb"))
        self.assertEqual(1, len(candidates))
        self.dataset_path = candidates[0]

    def _drop_schema(self, connection, schema_name: str) -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
            connection.commit()
        finally:
            connection.close()

    def test_load_creates_table_with_expected_rows_columns_and_no_public_leak(self):
        connection = self._connect()
        params = self._connection_params()

        schema_name = f"staging_load_test_{os.getpid()}"
        with connection.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
            cursor.execute(f"CREATE SCHEMA {schema_name}")
        connection.commit()
        self.addCleanup(self._drop_schema, connection, schema_name)

        policy = _staging_policy(
            host=params["host"],
            port=params["port"],
            dbname=params["dbname"],
            user=params["user"],
            staging_schema=schema_name,
            connect_timeout_seconds=self._CONNECT_TIMEOUT_SECONDS,
        )

        staging.load_layer(
            dataset_path=self.dataset_path,
            layer_name="ADDRESS",
            staging_table="vmadd_address_test",
            policy=policy,
            password=params["password"],
            diagnostics_dir=self.scratch_dir,
        )

        with connection.cursor() as verify_cursor:
            verify_cursor.execute(
                f"SELECT COUNT(*) FROM {schema_name}.vmadd_address_test"
            )
            (row_count,) = verify_cursor.fetchone()
            verify_cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                (schema_name, "vmadd_address_test"),
            )
            columns = {row[0] for row in verify_cursor.fetchall()}
            verify_cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename = 'vmadd_address_test'"
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


if __name__ == "__main__":
    unittest.main()
