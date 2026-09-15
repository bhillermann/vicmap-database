"""GEO-02/GEO-03 regressions for the manifest contract (02-06 Task 1).

``ManifestRoundTripTest`` proves ``manifest.py``'s canonical, hashable
persistence shape in isolation, using lightweight ``LayerProfile``/
``FieldProfile`` stand-ins so no geodatabase is needed (mirrors
``tests/test_naming.py``'s pure-unit style): payload shape, spatial and
non-spatial layer serialization, field-order preservation, byte-stability
across two calls, sidecar digest equality, the existing-manifest guard, and
the ``OSError`` translation.

The composition suite proving the ordered ``discover_order.run_discovery``
pipeline and every GEO-05 hard stop is added in a later commit (Task 2).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vicmap_acquire import discovery, manifest as manifest_module


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


def _field(name: str, ogr_type: str, *, width=None, precision=None, nullable=True):
    return discovery.FieldProfile(
        name=name, ogr_type=ogr_type, width=width, precision=precision, nullable=nullable
    )


_DEFAULT_FIELDS = (
    _field("UFI", "Integer"),
    _field("PFI", "String", width=10),
    _field("EZI_ADDRESS", "String", width=80),
)


def _layer_profile(**overrides) -> discovery.LayerProfile:
    defaults = dict(
        dataset_relative_path="gda2020_vicgrid/filegdb/whole_of_dataset/victoria/VMADD.gdb",
        dataset_stem="VMADD",
        layer_name="ADDRESS",
        driver="OpenFileGDB",
        spatial=True,
        geometry_type="Point",
        geometry_column="SHAPE",
        fid_column="OBJECTID",
        feature_count=4222035,
        source_wkt='PROJCRS["GDA2020 / Vicgrid"]',
        epsg=7899,
        extent=(2126780.196697, 2259755.350635, 2934322.982015, 2826389.754039),
        fields=_DEFAULT_FIELDS,
    )
    defaults.update(overrides)
    return discovery.LayerProfile(**defaults)


def _manifest(**overrides) -> manifest_module.ImportManifest:
    profile = overrides.pop("profile", None) or _layer_profile()
    target_table = overrides.pop("target_table", "vmadd_address")
    layers = overrides.pop(
        "layers",
        (manifest_module.ManifestLayer(profile=profile, target_table=target_table),),
    )
    companions = overrides.pop(
        "companions",
        (
            manifest_module.CompanionFile(
                relative_path="Creative Commons Licence.html",
                byte_count=123,
                sha256="a" * 64,
            ),
        ),
    )
    defaults = dict(
        order_id="OK0VUZ",
        run_timestamp="20260915T000000Z",
        run_directory=Path("/tmp/runs/OK0VUZ/20260915T000000Z"),
        artifact_sha256="b" * 64,
        artifact_byte_count=233089097,
        message_fingerprint="0123456789abcdef",
        layers=layers,
        companions=companions,
    )
    defaults.update(overrides)
    return manifest_module.build_manifest(**defaults)


class _TempDirMixin:
    def make_temp_dir(self, prefix: str) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        return temp_dir


class ManifestRoundTripTest(_TempDirMixin, unittest.TestCase):
    def test_payload_survives_json_dumps_with_no_custom_encoder(self):
        payload = manifest_module.manifest_payload(_manifest())
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.assertIsInstance(canonical, str)

        def _assert_plain(value, path):
            self.assertNotIsInstance(value, Path, path)
            self.assertNotIsInstance(value, tuple, path)
            if isinstance(value, dict):
                for key, item in value.items():
                    _assert_plain(item, f"{path}.{key}")
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    _assert_plain(item, f"{path}[{index}]")

        _assert_plain(payload, "payload")

    def test_provenance_nested_under_its_own_key(self):
        manifest = _manifest()
        payload = manifest_module.manifest_payload(manifest)
        self.assertEqual(
            {"schema_version", "provenance", "layers", "companions"}, set(payload)
        )
        provenance = payload["provenance"]
        self.assertEqual(
            {
                "order_id",
                "run_timestamp",
                "run_directory",
                "artifact_sha256",
                "artifact_byte_count",
                "message_fingerprint",
            },
            set(provenance),
        )
        self.assertEqual(manifest.message_fingerprint, provenance["message_fingerprint"])
        self.assertEqual(manifest.order_id, provenance["order_id"])

    def test_field_order_preserved_not_alphabetized(self):
        fields = (
            _field("UFI", "Integer"),
            _field("PFI", "String", width=10),
            _field("EZI_ADDRESS", "String", width=80),
        )
        profile = _layer_profile(fields=fields)
        manifest = _manifest(profile=profile)
        payload = manifest_module.manifest_payload(manifest)
        field_names = [f["name"] for f in payload["layers"][0]["fields"]]
        self.assertEqual(["UFI", "PFI", "EZI_ADDRESS"], field_names)

    def test_non_spatial_layer_serializes_with_null_geometry_fields(self):
        profile = _layer_profile(
            spatial=False,
            geometry_type=None,
            geometry_column=None,
            source_wkt=None,
            epsg=None,
            extent=None,
            fields=(_field("CODE", "String", width=3), _field("LABEL", "String", width=40)),
        )
        manifest = _manifest(profile=profile, target_table="lookup_lookup")
        payload = manifest_module.manifest_payload(manifest)
        layer = payload["layers"][0]
        self.assertFalse(layer["spatial"])
        self.assertIsNone(layer["geometry_type"])
        self.assertIsNone(layer["geometry_column"])
        self.assertIsNone(layer["source_wkt"])
        self.assertIsNone(layer["epsg"])
        self.assertIsNone(layer["extent"])

    def test_spatial_layer_extent_is_a_plain_list(self):
        payload = manifest_module.manifest_payload(_manifest())
        extent = payload["layers"][0]["extent"]
        self.assertIsInstance(extent, list)
        self.assertEqual(4, len(extent))

    def test_two_write_manifest_calls_produce_byte_identical_manifest(self):
        manifest = _manifest()
        dir_a = self.make_temp_dir("manifest-a-")
        dir_b = self.make_temp_dir("manifest-b-")
        digest_a = manifest_module.write_manifest(manifest, dir_a)
        digest_b = manifest_module.write_manifest(manifest, dir_b)
        self.assertEqual(digest_a, digest_b)
        self.assertEqual(
            (dir_a / "manifest.json").read_bytes(), (dir_b / "manifest.json").read_bytes()
        )

    def test_sidecar_digest_matches_manifest_bytes_without_trailing_newline(self):
        manifest = _manifest()
        run_dir = self.make_temp_dir("manifest-sidecar-")
        returned_digest = manifest_module.write_manifest(manifest, run_dir)

        manifest_bytes = (run_dir / "manifest.json").read_bytes()
        self.assertTrue(manifest_bytes.endswith(b"\n"))
        expected_digest = hashlib.sha256(manifest_bytes[:-1]).hexdigest()

        sidecar_text = (run_dir / "manifest.json.sha256").read_text(encoding="utf-8").strip()
        self.assertEqual(expected_digest, sidecar_text)
        self.assertEqual(expected_digest, returned_digest)

    def test_existing_manifest_raises_and_leaves_file_untouched(self):
        manifest = _manifest()
        run_dir = self.make_temp_dir("manifest-existing-")
        manifest_module.write_manifest(manifest, run_dir)
        original_bytes = (run_dir / "manifest.json").read_bytes()

        with self.assertRaises(manifest_module.ManifestWriteFailed):
            manifest_module.write_manifest(manifest, run_dir)

        self.assertEqual(original_bytes, (run_dir / "manifest.json").read_bytes())

    def test_oserror_translates_to_manifest_write_failed(self):
        manifest = _manifest()
        run_dir = self.make_temp_dir("manifest-oserror-")
        with patch("os.open", side_effect=OSError("disk full")):
            with self.assertRaises(manifest_module.ManifestWriteFailed):
                manifest_module.write_manifest(manifest, run_dir)
        self.assertFalse((run_dir / "manifest.json").exists())

    def test_provenance_message_fingerprint_matches_phase_one_sidecar(self):
        # Independent of any live sidecar on disk: build an ArtifactProvenance
        # the way read_provenance_sidecar would return one, and prove the
        # manifest payload carries it through unchanged.
        from vicmap_acquire.download import ArtifactProvenance

        provenance = ArtifactProvenance(
            order_id="OK0VUZ",
            message_fingerprint="deadbeefcafef00d",
            sha256="c" * 64,
            byte_count=233089097,
        )
        manifest = _manifest(
            order_id=provenance.order_id,
            message_fingerprint=provenance.message_fingerprint,
            artifact_sha256=provenance.sha256,
            artifact_byte_count=provenance.byte_count,
        )
        payload = manifest_module.manifest_payload(manifest)
        self.assertEqual(
            provenance.message_fingerprint, payload["provenance"]["message_fingerprint"]
        )


if __name__ == "__main__":
    unittest.main()
