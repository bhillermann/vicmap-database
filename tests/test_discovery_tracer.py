"""Wave 0 end-to-end artifact-to-manifest tracer regression (02-01 Task 3).

Builds a temp copy of ``tests/fixtures/Order_TRACER1.zip``, records its real
SHA-256/byte count directly (never reusing production code to derive the
expected values -- an independent computation, not the code's own answer
about itself), and asserts the whole ``discover_order.run_discovery`` path
produces one manifest naming target table ``vmadd_address`` with the exact
GEO-03 profile values. Also proves the D-28 checksum boundary, the D-31
redaction boundary, and import safety for every new module.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ARCHIVE = REPO_ROOT / "tests" / "fixtures" / "Order_TRACER1.zip"


def _sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


class OrderManifestTracerTest(unittest.TestCase):
    def setUp(self):
        self.scratch_dir = Path(tempfile.mkdtemp(prefix="tracer-"))
        self.addCleanup(shutil.rmtree, self.scratch_dir, ignore_errors=True)

        self.artifact_path = self.scratch_dir / "Order_TRACER1.zip"
        shutil.copyfile(FIXTURE_ARCHIVE, self.artifact_path)
        self.sha256, self.byte_count = _sha256_and_size(self.artifact_path)

        self.run_root = self.scratch_dir / "runs"

    def _config(
        self,
        discover_order,
        extraction,
        discovery,
        *,
        expected_sha256: str | None = None,
        expected_byte_count: int | None = None,
    ):
        return discover_order.DiscoveryConfig(
            artifact_path=self.artifact_path,
            order_id="TRACER1",
            run_timestamp="20260914T000000Z",
            expected_sha256=self.sha256 if expected_sha256 is None else expected_sha256,
            expected_byte_count=(
                self.byte_count if expected_byte_count is None else expected_byte_count
            ),
            message_fingerprint="0123456789abcdef",
            extraction_policy=extraction.ExtractionPolicy(
                run_root=self.run_root,
                max_total_bytes=5 * 1024 * 1024,
                max_member_bytes=2 * 1024 * 1024,
                max_member_count=64,
                max_compression_ratio=100,
            ),
            discovery_policy=discovery.DiscoveryPolicy(
                supported_formats=("OpenFileGDB",),
                ogrinfo_timeout_seconds=60,
            ),
        )

    def test_verified_artifact_becomes_one_manifest_end_to_end(self):
        import discover_order
        from vicmap_acquire import discovery, extraction

        events = []
        config = self._config(discover_order, extraction, discovery)
        manifest = discover_order.run_discovery(config, event_sink=events.append)

        self.assertEqual(1, len(manifest.layers))
        layer = manifest.layers[0]
        self.assertEqual("vmadd_address", layer.target_table)

        profile = layer.profile
        self.assertEqual(2, profile.feature_count)
        self.assertEqual(7899, profile.epsg)
        self.assertEqual("Point", profile.geometry_type)
        self.assertEqual("OBJECTID", profile.fid_column)
        self.assertEqual("SHAPE", profile.geometry_column)

        fields_by_name = {field.name: field for field in profile.fields}
        self.assertIn("EZI_ADDRESS", fields_by_name)
        self.assertEqual(80, fields_by_name["EZI_ADDRESS"].width)

        self.assertEqual(2, len(manifest.companions))
        companion_names = {companion.relative_path for companion in manifest.companions}
        self.assertIn("Creative Commons Licence.html", companion_names)

        run_directory = Path(manifest.run_directory)
        manifest_path = run_directory / "manifest.json"
        sidecar_path = run_directory / "manifest.json.sha256"
        self.assertTrue(manifest_path.exists())
        self.assertTrue(sidecar_path.exists())

        canonical_bytes = manifest_path.read_bytes()
        self.assertTrue(canonical_bytes.endswith(b"\n"))
        expected_digest = hashlib.sha256(canonical_bytes[:-1]).hexdigest()
        self.assertEqual(expected_digest, sidecar_path.read_text(encoding="utf-8").strip())

        # Redaction boundary (D-31): rendered evidence carries only safe
        # scalars -- never the run directory's absolute path or a raw
        # companion filename.
        rendered = json.dumps([dict(event) for event in events])
        self.assertIn("TRACER1", rendered)
        self.assertIn("vmadd_address", rendered)
        self.assertIn(expected_digest, rendered)
        self.assertNotIn(str(run_directory), rendered)
        self.assertNotIn(str(self.run_root), rendered)
        self.assertNotIn("Creative Commons Licence.html", rendered)

    def test_checksum_mismatch_stops_before_any_extraction(self):
        import discover_order
        from vicmap_acquire import discovery, extraction

        config = self._config(
            discover_order, extraction, discovery, expected_sha256="0" * 64
        )
        with self.assertRaises(extraction.ArtifactChecksumMismatch):
            discover_order.run_discovery(config, event_sink=lambda event: None)
        self.assertFalse(self.run_root.exists())

    def test_correct_hash_with_wrong_byte_count_also_rejected(self):
        import discover_order
        from vicmap_acquire import discovery, extraction

        config = self._config(
            discover_order,
            extraction,
            discovery,
            expected_byte_count=self.byte_count + 1,
        )
        with self.assertRaises(extraction.ArtifactChecksumMismatch):
            discover_order.run_discovery(config, event_sink=lambda event: None)
        self.assertFalse(self.run_root.exists())

    def test_importing_every_new_module_creates_no_directory(self):
        empty_cwd = Path(tempfile.mkdtemp(prefix="import-safety-"))
        self.addCleanup(shutil.rmtree, empty_cwd, ignore_errors=True)

        script = (
            "import discover_order\n"
            "import vicmap_acquire.extraction\n"
            "import vicmap_acquire.discovery\n"
            "import vicmap_acquire.naming\n"
            "import vicmap_acquire.manifest\n"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=empty_cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], list(empty_cwd.iterdir()))


if __name__ == "__main__":
    unittest.main()
