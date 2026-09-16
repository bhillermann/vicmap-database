"""GEO-02..GEO-05 regressions for the manifest contract and the ordered
``discover_order.run_discovery`` composition (02-06 Tasks 1/2).

``ManifestRoundTripTest`` proves ``manifest.py``'s canonical, hashable
persistence shape in isolation, using lightweight ``LayerProfile``/
``FieldProfile`` stand-ins so no geodatabase is needed (mirrors
``tests/test_naming.py``'s pure-unit style): payload shape, spatial and
non-spatial layer serialization, field-order preservation, byte-stability
across two calls, sidecar digest equality, the existing-manifest guard, and
the ``OSError`` translation.

The composition suite proves the *ordered* ``discover_order.run_discovery``
pipeline: every GEO-05 hard stop leaves no ``manifest.json`` and no sidecar
anywhere under the run root, stage ordering is real (instrumented call
recording, never a timing assumption), a faulty event sink is isolated by
the ``_EmitOnce`` guard, operator-facing output stays redacted, and the run
opens no socket and imports no database driver. Real end-to-end runs reuse
``tests/fixtures/Order_TRACER1.zip`` (the same fixture
``tests/test_discovery_tracer.py`` uses); conditions the fixture cannot
itself provoke (unsupported format, empty delivery, unreadable/empty layer,
unresolved geometry/CRS, incomplete schema, table-name collision) are
driven by monkeypatching the specific ``discover_order`` stage function to
raise the real typed exception -- composition-level proof, not a re-test of
what ``tests/test_extraction.py``/``test_discovery.py``/``test_naming.py``
already cover at the unit level.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import discover_order
import read_mailbox
from vicmap_acquire import discovery, extraction, manifest as manifest_module, naming


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


# ---------------------------------------------------------------------------
# Task 2: ordered run_discovery composition
# ---------------------------------------------------------------------------


class _DiscoveryConfigMixin(_TempDirMixin):
    def setUp(self):
        super().setUp()
        self.scratch_dir = self.make_temp_dir("run-discovery-")
        self.artifact_path = self.scratch_dir / "Order_TRACER1.zip"
        shutil.copyfile(FIXTURE_ARCHIVE, self.artifact_path)
        self.sha256, self.byte_count = _sha256_and_size(self.artifact_path)
        self.run_root = self.scratch_dir / "runs"

    def _config(self, **overrides):
        defaults = dict(
            artifact_path=self.artifact_path,
            order_id="TRACER1",
            run_timestamp="20260916T000000Z",
            expected_sha256=self.sha256,
            expected_byte_count=self.byte_count,
            message_fingerprint="0123456789abcdef",
            extraction_policy=extraction.ExtractionPolicy(
                run_root=self.run_root,
                max_total_bytes=5 * 1024 * 1024,
                max_member_bytes=2 * 1024 * 1024,
                max_member_count=64,
                max_compression_ratio=200,
            ),
            discovery_policy=discovery.DiscoveryPolicy(
                supported_formats=("OpenFileGDB",),
                ogrinfo_timeout_seconds=60,
            ),
        )
        defaults.update(overrides)
        return discover_order.DiscoveryConfig(**defaults)

    def _no_manifest_anywhere(self) -> bool:
        manifests = list(self.scratch_dir.rglob("manifest.json"))
        sidecars = list(self.scratch_dir.rglob("manifest.json.sha256"))
        return not manifests and not sidecars


class GeoO5HardStopTest(_DiscoveryConfigMixin, unittest.TestCase):
    """Every GEO-05 condition must stop the run before any manifest exists."""

    def _assert_hard_stop(self, config, expected_exception, expected_reason):
        events = []
        with self.assertRaises(expected_exception):
            discover_order.run_discovery(config, event_sink=events.append)
        self.assertTrue(self._no_manifest_anywhere())

        failures = [event for event in events if dict(event).get("event") == "failure"]
        self.assertEqual(1, len(failures))
        self.assertEqual(expected_reason, failures[0]["reason"])

    # -- checksum mismatch (before any run directory exists) --------------

    def test_checksum_mismatch_stops_before_any_manifest(self):
        config = self._config(expected_sha256="0" * 64)
        self._assert_hard_stop(config, extraction.ArtifactChecksumMismatch, "artifact_checksum_mismatch")
        self.assertFalse(self.run_root.exists())

    # -- every archive guard (real extract_artifact, patched to fail) -----

    def test_archive_traversal_rejected_stops_before_any_manifest(self):
        config = self._config()
        with patch.object(
            discover_order, "extract_artifact", side_effect=extraction.ArchiveTraversalRejected()
        ):
            self._assert_hard_stop(
                config, extraction.ArchiveTraversalRejected, "archive_traversal_rejected"
            )

    def test_archive_unsafe_member_rejected_stops_before_any_manifest(self):
        config = self._config()
        with patch.object(
            discover_order,
            "extract_artifact",
            side_effect=extraction.ArchiveUnsafeMemberRejected(),
        ):
            self._assert_hard_stop(
                config,
                extraction.ArchiveUnsafeMemberRejected,
                "archive_unsafe_member_rejected",
            )

    def test_archive_ceiling_exceeded_stops_before_any_manifest(self):
        config = self._config()
        with patch.object(
            discover_order, "extract_artifact", side_effect=extraction.ArchiveCeilingExceeded()
        ):
            self._assert_hard_stop(
                config, extraction.ArchiveCeilingExceeded, "archive_ceiling_exceeded"
            )

    # -- discovery-stage hard stops (patched discover_layers) -------------

    def test_unsupported_format_stops_before_any_manifest(self):
        config = self._config()
        with patch.object(
            discover_order, "discover_layers", side_effect=discovery.UnsupportedFormat()
        ):
            self._assert_hard_stop(config, discovery.UnsupportedFormat, "unsupported_format")

    def test_delivery_empty_stops_before_any_manifest(self):
        config = self._config()
        with patch.object(
            discover_order, "discover_layers", side_effect=discovery.DeliveryEmpty()
        ):
            self._assert_hard_stop(config, discovery.DeliveryEmpty, "delivery_empty")

    def test_layer_unreadable_stops_before_any_manifest(self):
        config = self._config()
        with patch.object(
            discover_order, "discover_layers", side_effect=discovery.LayerUnreadable()
        ):
            self._assert_hard_stop(config, discovery.LayerUnreadable, "layer_unreadable")

    def test_layer_empty_stops_before_any_manifest(self):
        config = self._config()
        with patch.object(
            discover_order, "discover_layers", side_effect=discovery.LayerEmpty()
        ):
            self._assert_hard_stop(config, discovery.LayerEmpty, "layer_empty")

    def test_geometry_type_unresolved_stops_before_any_manifest(self):
        config = self._config()
        with patch.object(
            discover_order,
            "discover_layers",
            side_effect=discovery.GeometryTypeUnresolved(),
        ):
            self._assert_hard_stop(
                config, discovery.GeometryTypeUnresolved, "geometry_type_unresolved"
            )

    def test_crs_unresolved_stops_before_any_manifest(self):
        config = self._config()
        with patch.object(
            discover_order, "discover_layers", side_effect=discovery.CrsUnresolved()
        ):
            self._assert_hard_stop(config, discovery.CrsUnresolved, "crs_unresolved")

    def test_layer_schema_incomplete_stops_before_any_manifest(self):
        config = self._config()
        with patch.object(
            discover_order,
            "discover_layers",
            side_effect=discovery.LayerSchemaIncomplete(),
        ):
            self._assert_hard_stop(
                config, discovery.LayerSchemaIncomplete, "layer_schema_incomplete"
            )

    # -- naming-stage hard stops (real discover_layers, patched naming) ---

    def test_table_name_invalid_stops_before_any_manifest(self):
        config = self._config()
        with patch.object(
            discover_order,
            "assign_target_table_names",
            side_effect=naming.TableNameInvalid(),
        ):
            self._assert_hard_stop(config, naming.TableNameInvalid, "table_name_invalid")

    def test_table_name_collision_stops_before_any_manifest(self):
        config = self._config()
        with patch.object(
            discover_order,
            "assign_target_table_names",
            side_effect=naming.TableNameCollision(),
        ):
            self._assert_hard_stop(
                config, naming.TableNameCollision, "table_name_collision"
            )


class StageOrderingTest(_DiscoveryConfigMixin, unittest.TestCase):
    def test_extraction_never_attempted_before_verify_artifact_returns(self):
        """Instrumented call recording, never a timing assumption (real stages)."""

        call_order: list[str] = []
        original_verify = discover_order.verify_artifact
        original_extract = discover_order.extract_artifact
        original_discover = discover_order.discover_layers
        original_assign = discover_order.assign_target_table_names
        original_build = discover_order.build_manifest
        original_write = discover_order.write_manifest

        def _recording(name, original):
            def _wrapper(*args, **kwargs):
                call_order.append(name)
                return original(*args, **kwargs)

            return _wrapper

        with patch.object(
            discover_order, "verify_artifact", _recording("verify_artifact", original_verify)
        ), patch.object(
            discover_order, "extract_artifact", _recording("extract_artifact", original_extract)
        ), patch.object(
            discover_order, "discover_layers", _recording("discover_layers", original_discover)
        ), patch.object(
            discover_order,
            "assign_target_table_names",
            _recording("assign_target_table_names", original_assign),
        ), patch.object(
            discover_order, "build_manifest", _recording("build_manifest", original_build)
        ), patch.object(
            discover_order, "write_manifest", _recording("write_manifest", original_write)
        ):
            config = self._config()
            discover_order.run_discovery(config, event_sink=lambda event: None)

        self.assertEqual(
            [
                "verify_artifact",
                "extract_artifact",
                "discover_layers",
                "assign_target_table_names",
                "build_manifest",
                "write_manifest",
            ],
            call_order,
        )


class FaultySinkTest(_DiscoveryConfigMixin, unittest.TestCase):
    def test_sink_that_raises_on_first_call_produces_exactly_one_attempt(self):
        calls = []

        def _raising_sink(event):
            calls.append(event)
            raise RuntimeError("sink is broken")

        config = self._config()
        with self.assertRaises(discover_order.RunDiscoveryReportingFailed) as ctx:
            discover_order.run_discovery(config, event_sink=_raising_sink)

        # Never the sink's own exception instance/message escaping
        # run_discovery -- the _EmitOnce guard isolates it, and the
        # pipeline's own internal signal is what propagates instead.
        self.assertNotEqual("sink is broken", str(ctx.exception))
        self.assertIs(discover_order.RunDiscoveryReportingFailed, type(ctx.exception))

        # The sink was invoked exactly once total: the guard marks itself
        # failed on that first attempt and every later emit() -- including
        # the final SafeFailure -- becomes a silent no-op, never retried.
        self.assertEqual(1, len(calls))


class RedactionTest(_DiscoveryConfigMixin, unittest.TestCase):
    def test_successful_run_output_is_redacted(self):
        import io

        from vicmap_acquire.evidence import SafeFailure, SuccessEvent, render_failure, render_success

        events = []
        config = self._config()
        manifest = discover_order.run_discovery(config, event_sink=events.append)

        # Literally captured stdout, via the real rendering functions main()
        # uses -- not a re-derivation of what a renderer might produce.
        stdout_buffer = io.StringIO()
        buffer_lines = []
        for event in events:
            if isinstance(event, SuccessEvent):
                render_success(event, stream=stdout_buffer)
            elif isinstance(event, SafeFailure):
                render_failure(event, stream=stdout_buffer)
        captured_stdout = stdout_buffer.getvalue()
        buffer_lines = [line for line in captured_stdout.splitlines() if line]

        self.assertIn("TRACER1", captured_stdout)
        self.assertIn("vmadd_address", captured_stdout)

        manifest_sha256_entries = [
            dict(event)["manifest_sha256"]
            for event in events
            if isinstance(event, SuccessEvent) and "manifest_sha256" in dict(event)
        ]
        self.assertEqual(1, len(manifest_sha256_entries))
        self.assertIn(manifest_sha256_entries[0], captured_stdout)

        path_fingerprints = [
            dict(event)["run_path_fingerprint"]
            for event in events
            if isinstance(event, SuccessEvent) and "run_path_fingerprint" in dict(event)
        ]
        self.assertTrue(path_fingerprints)
        self.assertIn(path_fingerprints[0], captured_stdout)

        run_directory = Path(manifest.run_directory)
        self.assertNotIn(str(run_directory), captured_stdout)
        self.assertNotIn(str(self.run_root), captured_stdout)
        self.assertNotIn("Creative Commons Licence.html", captured_stdout)

        # No JSON string value may itself start with a filesystem-absolute
        # path -- a stricter, structural version of the substring check
        # above.
        for line in buffer_lines:
            parsed = json.loads(line)
            for value in parsed.values():
                if isinstance(value, str):
                    self.assertFalse(value.startswith("/"), value)
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            self.assertFalse(item.startswith("/"), item)


class NoSocketNoDatabaseTest(_DiscoveryConfigMixin, unittest.TestCase):
    def test_successful_run_completes_with_socket_socket_patched_to_raise(self):
        config = self._config()
        with patch.object(socket, "socket", side_effect=AssertionError("no network allowed")):
            manifest = discover_order.run_discovery(config, event_sink=lambda event: None)
        self.assertEqual(1, len(manifest.layers))

    def test_no_database_driver_module_in_sys_modules_after_successful_run(self):
        script = (
            "import sys\n"
            "import discover_order\n"
            "from vicmap_acquire import discovery, extraction\n"
            f"artifact_path = {str(self.artifact_path)!r}\n"
            f"run_root = {str(self.run_root)!r}\n"
            "config = discover_order.DiscoveryConfig(\n"
            "    artifact_path=__import__('pathlib').Path(artifact_path),\n"
            f"    order_id='TRACER1',\n"
            f"    run_timestamp='20260916T010101Z',\n"
            f"    expected_sha256={self.sha256!r},\n"
            f"    expected_byte_count={self.byte_count!r},\n"
            "    message_fingerprint='0123456789abcdef',\n"
            "    extraction_policy=extraction.ExtractionPolicy(\n"
            "        run_root=__import__('pathlib').Path(run_root),\n"
            "        max_total_bytes=5 * 1024 * 1024,\n"
            "        max_member_bytes=2 * 1024 * 1024,\n"
            "        max_member_count=64,\n"
            "        max_compression_ratio=200,\n"
            "    ),\n"
            "    discovery_policy=discovery.DiscoveryPolicy(\n"
            "        supported_formats=('OpenFileGDB',),\n"
            "        ogrinfo_timeout_seconds=60,\n"
            "    ),\n"
            ")\n"
            "discover_order.run_discovery(config, event_sink=lambda event: None)\n"
            "forbidden = ('psycopg', 'psycopg2', 'sqlalchemy', 'asyncpg', 'pg8000')\n"
            "leaked = [name for name in sys.modules if name.split('.')[0] in forbidden]\n"
            "assert not leaked, leaked\n"
            "print('no database driver imported')\n"
        )
        env = __import__("os").environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("no database driver imported", result.stdout)


class AutomaticSelectionTest(_DiscoveryConfigMixin, unittest.TestCase):
    def test_two_layer_delivery_produces_two_layer_manifest_with_no_filtering(self):
        real_profiles = discovery.discover_layers  # noqa: F841 (documents intent)
        first = _layer_profile(layer_name="ADDRESS", dataset_stem="VMADD")
        second = _layer_profile(
            layer_name="PARCEL",
            dataset_stem="VMADD",
            feature_count=17,
            fields=(_field("PID", "Integer"),),
        )

        config = self._config()
        with patch.object(discover_order, "discover_layers", return_value=(first, second)):
            manifest = discover_order.run_discovery(config, event_sink=lambda event: None)

        self.assertEqual(2, len(manifest.layers))
        target_tables = {layer.target_table for layer in manifest.layers}
        self.assertEqual({"vmadd_address", "vmadd_parcel"}, target_tables)


class MainFaultyRenderTest(_DiscoveryConfigMixin, unittest.TestCase):
    """Drives the faulty-sink property through ``main()``'s real CLI path."""

    def test_render_success_failure_yields_nonzero_exit_no_raw_exception(self):
        from vicmap_acquire.download import write_provenance_sidecar

        artifacts_dir = self.scratch_dir / "artifacts"
        artifacts_dir.mkdir()
        artifact_path = artifacts_dir / "Order_TRACER1.zip"
        shutil.copyfile(FIXTURE_ARCHIVE, artifact_path)
        write_provenance_sidecar(
            artifact_path,
            order_id="TRACER1",
            message_fingerprint="0123456789abcdef",
            sha256=self.sha256,
            byte_count=self.byte_count,
        )

        fake_run_config = read_mailbox.DiscoveryRunConfig(
            artifacts_dir=artifacts_dir,
            run_root=self.run_root,
            fingerprint_hex_chars=16,
            allowed_order_ids=("TRACER1",),
            max_total_bytes=5 * 1024 * 1024,
            max_member_bytes=2 * 1024 * 1024,
            max_member_count=64,
            max_compression_ratio=200,
            supported_formats=("OpenFileGDB",),
            ogrinfo_timeout_seconds=60,
        )

        call_count = {"n": 0}
        original_render_success = discover_order.render_success

        def _raising_render_success(event, **kwargs):
            call_count["n"] += 1
            raise RuntimeError("render is broken")

        with patch.object(
            read_mailbox, "load_discovery_config", return_value=fake_run_config
        ), patch.object(discover_order, "render_success", _raising_render_success):
            exit_code = discover_order.main(["--config", str(self.scratch_dir / "vicmap.toml")])

        self.assertEqual(1, exit_code)
        self.assertGreaterEqual(call_count["n"], 1)


# ---------------------------------------------------------------------------
# Task 3: opt-in live regression against the real Vicmap delivery
# ---------------------------------------------------------------------------

REAL_ORDER_ID = "OK0VUZ"
REAL_ARTIFACT = REPO_ROOT / "artifacts" / f"Order_{REAL_ORDER_ID}.zip"
REAL_PROVENANCE_SIDECAR = REPO_ROOT / "artifacts" / f"Order_{REAL_ORDER_ID}.provenance.json"


class LiveDeliveryRegressionTest(unittest.TestCase):
    """Opt-in regression against the real ``artifacts/Order_OK0VUZ.zip``.

    Skipped unless both the real artifact and its provenance sidecar are
    present on disk (produced by a fresh acquisition run or
    ``python read_mailbox.py --provenance-only``), so the deterministic
    suite stays portable -- mirrors Phase 1's opt-in live-check pattern
    (01-11/01-13/01-14, ``01-LIVE-VERIFICATION.md``). When present, this
    test drives the complete ``run_discovery`` path against the real
    233 MB delivery into a temporary run root outside the repository
    working tree, and asserts the exact values research verified this
    session (``02-RESEARCH.md``) -- doubling as a regression for a future
    ``pyogrio``/GDAL upgrade silently changing an answer.
    """

    @unittest.skipUnless(
        REAL_ARTIFACT.is_file() and REAL_PROVENANCE_SIDECAR.is_file(),
        "requires artifacts/Order_OK0VUZ.zip and its provenance sidecar on disk",
    )
    def test_real_delivery_produces_the_pinned_manifest(self):
        import time
        import zipfile as zipfile_module

        import pyogrio

        from vicmap_acquire.download import read_provenance_sidecar

        # Independent proof the test never mutates the real artifact --
        # measured before and after (see the end of this test).
        sha256_before, byte_count_before = _sha256_and_size(REAL_ARTIFACT)

        provenance = read_provenance_sidecar(REAL_ARTIFACT, order_id=REAL_ORDER_ID)

        # A throwaway system temp directory, entirely outside the
        # repository working tree and never the permitted runs/ root --
        # removed in the finally block below.
        run_root = Path(tempfile.mkdtemp(prefix="live-delivery-run-root-"))
        self.assertFalse(str(run_root).startswith(str(REPO_ROOT)))
        repo_runs_dir = REPO_ROOT / "runs"
        repo_runs_existed_before = repo_runs_dir.exists()

        try:
            config = discover_order.DiscoveryConfig(
                artifact_path=REAL_ARTIFACT,
                order_id=REAL_ORDER_ID,
                run_timestamp="20260916T000000Z",
                expected_sha256=provenance.sha256,
                expected_byte_count=provenance.byte_count,
                message_fingerprint=provenance.message_fingerprint,
                extraction_policy=extraction.ExtractionPolicy(
                    run_root=run_root,
                    max_total_bytes=10_737_418_240,
                    max_member_bytes=4_294_967_296,
                    max_member_count=4096,
                    # NOT vicmap.toml's production default (20): the real
                    # delivery's tiny .gdbtablx/.atx index members compress
                    # up to ~139x (verified this session), the same shape
                    # 02-01's tracer fixture hit and worked around the same
                    # way -- test-local only, see this plan's SUMMARY.
                    max_compression_ratio=200,
                ),
                discovery_policy=discovery.DiscoveryPolicy(
                    supported_formats=("OpenFileGDB",),
                    ogrinfo_timeout_seconds=60,
                ),
            )

            events = []
            started = time.monotonic()
            manifest = discover_order.run_discovery(config, event_sink=events.append)
            elapsed_seconds = time.monotonic() - started
            print(
                f"\n[live-delivery] run_discovery elapsed: {elapsed_seconds:.1f}s",
                flush=True,
            )

            run_directory = Path(manifest.run_directory)

            # -- archive shape: 46 members total (an independent zipfile
            # oracle, never vicmap_acquire.extraction's own accounting);
            # every non-directory member's exact relative path was
            # extracted somewhere under the run directory.
            with zipfile_module.ZipFile(REAL_ARTIFACT) as archive:
                infolist = archive.infolist()
                zip_file_names = {
                    info.filename for info in infolist if not info.filename.endswith("/")
                }
            self.assertEqual(46, len(infolist))

            extracted_file_names = set()
            for path in run_directory.rglob("*"):
                if path.is_dir():
                    continue
                relative = path.relative_to(run_directory).as_posix()
                if relative in ("manifest.json", "manifest.json.sha256"):
                    continue
                extracted_file_names.add(relative)
            self.assertEqual(zip_file_names, extracted_file_names)

            # -- companions: the two non-geospatial files, never datasets --
            companion_paths = {c.relative_path for c in manifest.companions}
            self.assertEqual(
                {
                    "Creative Commons Licence.html",
                    "VICMAP_ADDRESS_b9e9146d-8378-5c37-b6cd-63e3a8d05d02.pdf",
                },
                companion_paths,
            )
            for companion in manifest.companions:
                self.assertNotIn(".gdb/", companion.relative_path)

            # -- exactly one dataset, one layer -----------------------------
            self.assertEqual(1, len(manifest.layers))
            layer = manifest.layers[0]
            profile = layer.profile
            self.assertEqual(
                "gda2020_vicgrid/filegdb/whole_of_dataset/victoria/VMADD.gdb",
                profile.dataset_relative_path,
            )
            self.assertEqual("VMADD", profile.dataset_stem)
            self.assertEqual("ADDRESS", profile.layer_name)
            self.assertEqual("OpenFileGDB", profile.driver)
            self.assertEqual(4222035, profile.feature_count)
            self.assertEqual("Point", profile.geometry_type)
            self.assertTrue(profile.spatial)
            self.assertEqual("OBJECTID", profile.fid_column)
            self.assertEqual("SHAPE", profile.geometry_column)
            self.assertEqual(7899, profile.epsg)
            self.assertEqual("vmadd_address", layer.target_table)

            # -- fields: exact width cases, plus the true field count -------
            # NOTE: 02-RESEARCH.md recorded 40 attribute fields; an
            # independent `ogrinfo -json -al -so` run this session against
            # the same real VMADD.gdb/ADDRESS layer (extracted standalone,
            # outside this test) reports 61 -- confirmed genuine schema
            # fields (BLG_UNIT_*/FLOOR_*/HOUSE_*/DISP_*/ROAD_*/etc.), not a
            # parsing artifact. This assertion pins the live-verified truth
            # per this plan's own purpose (research's number was stale/
            # wrong); see the plan SUMMARY's Deviations section.
            self.assertEqual(61, len(profile.fields))
            fields_by_name = {f.name: f for f in profile.fields}
            self.assertEqual(10, fields_by_name["PFI"].width)
            self.assertEqual(80, fields_by_name["EZI_ADDRESS"].width)
            self.assertIsNone(fields_by_name["UFI"].width)

            # -- extent: the driver's own float tuple, no rounding, checked
            # against pyogrio.read_info() called directly inside this test
            # (the independent oracle) rather than against hard-coded
            # numbers.
            dataset_path = run_directory / profile.dataset_relative_path
            info = pyogrio.read_info(str(dataset_path), layer="ADDRESS")
            oracle_extent = tuple(float(value) for value in info["total_bounds"])
            self.assertEqual(oracle_extent, profile.extent)

            # -- manifest.json + sidecar exist and the digest matches -------
            manifest_path = run_directory / "manifest.json"
            sidecar_path = run_directory / "manifest.json.sha256"
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(sidecar_path.is_file())
            manifest_bytes = manifest_path.read_bytes()
            self.assertTrue(manifest_bytes.endswith(b"\n"))
            expected_digest = hashlib.sha256(manifest_bytes[:-1]).hexdigest()
            self.assertEqual(
                expected_digest, sidecar_path.read_text(encoding="utf-8").strip()
            )

            # -- the repository's own runs/ root was never written into -----
            self.assertEqual(repo_runs_existed_before, repo_runs_dir.exists())
        finally:
            shutil.rmtree(run_root, ignore_errors=True)

        self.assertFalse(run_root.exists())

        # -- the real artifact itself is unchanged before vs after ----------
        sha256_after, byte_count_after = _sha256_and_size(REAL_ARTIFACT)
        self.assertEqual(sha256_before, sha256_after)
        self.assertEqual(byte_count_before, byte_count_after)


if __name__ == "__main__":
    unittest.main()
