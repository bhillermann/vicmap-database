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

import tempfile
import tomllib
import unittest
from pathlib import Path

import read_mailbox


REPO_ROOT = Path(__file__).resolve().parent.parent

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
