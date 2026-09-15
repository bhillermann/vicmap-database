"""Phase 2 [extraction]/[discovery] configuration regressions.

Covers ``read_mailbox.load_discovery_config`` and
``read_mailbox.validate_discovery_policy`` -- the single reviewable,
fail-closed contract for Phase 2's ceilings, run root, and format allowlist.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


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
"""

TWO_SECTION_TOML = """\
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
"""


def _write(directory: str, text: str = VALID_TOML) -> Path:
    path = Path(directory) / "vicmap.toml"
    path.write_text(text, encoding="utf-8")
    return path


class LoadDiscoveryConfigValidTest(unittest.TestCase):
    def test_valid_policy_loads_the_complete_reviewable_phase_2_contract(self):
        import read_mailbox

        with tempfile.TemporaryDirectory() as directory:
            config = read_mailbox.load_discovery_config(_write(directory))

        self.assertEqual(("OpenFileGDB",), config.supported_formats)
        self.assertEqual(4096, config.max_member_count)
        self.assertEqual(10737418240, config.max_total_bytes)
        self.assertEqual(4294967296, config.max_member_bytes)
        self.assertEqual(20, config.max_compression_ratio)
        self.assertEqual(60, config.ogrinfo_timeout_seconds)
        self.assertEqual("runs", config.run_root.name)
        self.assertEqual(("OK0VUZ",), config.allowed_order_ids)
        self.assertEqual(16, config.fingerprint_hex_chars)
        self.assertTrue(config.artifacts_dir.is_absolute())
        self.assertEqual("artifacts", config.artifacts_dir.name)

    def test_real_repository_vicmap_toml_loads_the_settled_phase_2_defaults(self):
        import read_mailbox

        repo_root = Path(__file__).resolve().parent.parent
        config = read_mailbox.load_discovery_config(repo_root / "vicmap.toml")
        self.assertEqual(("OpenFileGDB",), config.supported_formats)
        self.assertEqual(4096, config.max_member_count)
        self.assertEqual("runs", config.run_root.name)

    def test_load_config_also_accepts_the_complete_four_section_document(self):
        import read_mailbox

        with tempfile.TemporaryDirectory() as directory:
            config = read_mailbox.load_config(_write(directory))
        self.assertEqual("automations@vegetationlink.com.au", config.mailbox)


class LoadConfigRequiresFourSectionsTest(unittest.TestCase):
    def test_load_config_rejects_a_toml_document_holding_only_mailbox_and_download(self):
        import read_mailbox

        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, TWO_SECTION_TOML)
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.load_config(path)
            self.assertEqual("config_invalid", caught.exception.code)

    def test_load_discovery_config_rejects_the_same_two_section_document(self):
        import read_mailbox

        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, TWO_SECTION_TOML)
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.load_discovery_config(path)
            self.assertEqual("config_invalid", caught.exception.code)


class DiscoveryConfigRejectionTest(unittest.TestCase):
    """Every rejection case must raise ``config_invalid`` before any archive
    is opened or any subprocess spawned -- proven by patching both to raise
    if invoked, so a bug here surfaces as a test failure, not a silent pass.
    """

    def _load(self, directory: str, text: str):
        import read_mailbox

        path = _write(directory, text)
        return read_mailbox.load_discovery_config(path)

    def _assert_rejected(self, text: str):
        import read_mailbox

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(
                    zipfile,
                    "ZipFile",
                    side_effect=AssertionError("must not open any archive"),
                ),
                patch.object(
                    subprocess,
                    "run",
                    side_effect=AssertionError("must not spawn any subprocess"),
                ),
            ):
                with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                    self._load(directory, text)
        self.assertEqual("config_invalid", caught.exception.code)

    def test_missing_extraction_section(self):
        text = VALID_TOML.replace(
            "[extraction]\n"
            "run_dir = \"runs\"\n"
            "max_total_bytes = 10737418240\n"
            "max_member_bytes = 4294967296\n"
            "max_member_count = 4096\n"
            "max_compression_ratio = 20\n\n",
            "",
        )
        self._assert_rejected(text)

    def test_missing_discovery_section(self):
        text = VALID_TOML.replace(
            "[discovery]\n"
            "supported_formats = [\"OpenFileGDB\"]\n"
            "ogrinfo_timeout_seconds = 60\n",
            "",
        )
        self._assert_rejected(text)

    def test_unknown_key_in_extraction_section(self):
        text = VALID_TOML.replace(
            "max_compression_ratio = 20\n", "max_compression_ratio = 20\nextra = 1\n"
        )
        self._assert_rejected(text)

    def test_unknown_key_in_discovery_section(self):
        text = VALID_TOML.replace(
            "ogrinfo_timeout_seconds = 60\n",
            "ogrinfo_timeout_seconds = 60\nextra = true\n",
        )
        self._assert_rejected(text)

    def test_missing_key_in_extraction_section(self):
        text = VALID_TOML.replace("max_compression_ratio = 20\n", "")
        self._assert_rejected(text)

    def test_boolean_supplied_where_integer_required(self):
        for field in (
            "max_total_bytes = 10737418240",
            "max_member_bytes = 4294967296",
            "max_member_count = 4096",
            "max_compression_ratio = 20",
        ):
            name = field.split(" = ")[0]
            with self.subTest(field=name):
                text = VALID_TOML.replace(field, f"{name} = true")
                self._assert_rejected(text)
        with self.subTest(field="ogrinfo_timeout_seconds"):
            text = VALID_TOML.replace(
                "ogrinfo_timeout_seconds = 60", "ogrinfo_timeout_seconds = true"
            )
            self._assert_rejected(text)

    def test_non_positive_ceilings(self):
        for field in (
            "max_total_bytes = 10737418240",
            "max_member_bytes = 4294967296",
            "max_member_count = 4096",
            "max_compression_ratio = 20",
        ):
            name = field.split(" = ")[0]
            for bad_value in (0, -1):
                with self.subTest(field=name, value=bad_value):
                    text = VALID_TOML.replace(field, f"{name} = {bad_value}")
                    self._assert_rejected(text)

    def test_member_bytes_exceeding_total_bytes(self):
        text = VALID_TOML.replace(
            "max_total_bytes = 10737418240", "max_total_bytes = 1000"
        ).replace("max_member_bytes = 4294967296", "max_member_bytes = 2000")
        self._assert_rejected(text)

    def test_empty_supported_formats(self):
        text = VALID_TOML.replace(
            'supported_formats = ["OpenFileGDB"]', "supported_formats = []"
        )
        self._assert_rejected(text)

    def test_duplicated_format_entry(self):
        text = VALID_TOML.replace(
            'supported_formats = ["OpenFileGDB"]',
            'supported_formats = ["OpenFileGDB", "OpenFileGDB"]',
        )
        self._assert_rejected(text)

    def test_format_outside_the_recognized_driver_set(self):
        text = VALID_TOML.replace(
            'supported_formats = ["OpenFileGDB"]', 'supported_formats = ["ESRI Shapefile"]'
        )
        self._assert_rejected(text)

    def test_ogrinfo_timeout_non_positive(self):
        for bad_value in (0, -1):
            with self.subTest(value=bad_value):
                text = VALID_TOML.replace(
                    "ogrinfo_timeout_seconds = 60",
                    f"ogrinfo_timeout_seconds = {bad_value}",
                )
                self._assert_rejected(text)

    def test_run_dir_absolute_path(self):
        text = VALID_TOML.replace('run_dir = "runs"', 'run_dir = "/etc/runs"')
        self._assert_rejected(text)

    def test_run_dir_contains_dot_dot(self):
        text = VALID_TOML.replace('run_dir = "runs"', 'run_dir = "../runs"')
        self._assert_rejected(text)

    def test_run_dir_not_the_recognized_runs_name(self):
        text = VALID_TOML.replace('run_dir = "runs"', 'run_dir = "other"')
        self._assert_rejected(text)

    def test_run_dir_blank(self):
        text = VALID_TOML.replace('run_dir = "runs"', 'run_dir = "   "')
        self._assert_rejected(text)


class DirectlyConstructedDiscoveryRunConfigTest(unittest.TestCase):
    """``validate_discovery_policy`` is the single contract -- both entry
    points (TOML loader and a hand-built config) must reject identically.
    """

    def _valid_kwargs(self, directory: Path) -> dict:
        return dict(
            artifacts_dir=directory / "artifacts",
            run_root=directory / "runs",
            fingerprint_hex_chars=16,
            allowed_order_ids=("OK0VUZ",),
            max_total_bytes=10737418240,
            max_member_bytes=4294967296,
            max_member_count=4096,
            max_compression_ratio=20,
            supported_formats=("OpenFileGDB",),
            ogrinfo_timeout_seconds=60,
        )

    def test_valid_hand_built_config_passes(self):
        import read_mailbox

        with tempfile.TemporaryDirectory() as directory:
            config = read_mailbox.DiscoveryRunConfig(**self._valid_kwargs(Path(directory)))
            read_mailbox.validate_discovery_policy(config)  # must not raise

    def test_relative_run_root_is_rejected(self):
        import read_mailbox

        with tempfile.TemporaryDirectory() as directory:
            kwargs = self._valid_kwargs(Path(directory))
            kwargs["run_root"] = Path("relative/runs")
            config = read_mailbox.DiscoveryRunConfig(**kwargs)
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.validate_discovery_policy(config)
            self.assertEqual("config_invalid", caught.exception.code)

    def test_empty_allowed_order_ids_is_rejected(self):
        import read_mailbox

        with tempfile.TemporaryDirectory() as directory:
            kwargs = self._valid_kwargs(Path(directory))
            kwargs["allowed_order_ids"] = ()
            config = read_mailbox.DiscoveryRunConfig(**kwargs)
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.validate_discovery_policy(config)
            self.assertEqual("config_invalid", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
