"""GEO-02/GEO-03 regressions for ``vicmap_acquire.discovery`` (02-04 Task 1/2).

Exercises enumeration (``find_datasets``) against the three checked-in
fixtures plus adversarial cases built with tiny synthetic directory trees
and mocked ``pyogrio``/``ogrinfo`` seams, and exercises full-layer profiling
(``read_field_schema``/``profile_layer``/``discover_layers``) against the
real fixture data plus injected ``pyogrio.read_info``/``pyproj`` results for
branches (``Unknown`` geometry, zero features, unresolvable CRS) that cannot
be provoked from GDAL's own behavior without an adversarial fixture GDAL
itself would refuse to write.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from vicmap_acquire import discovery

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
ORDER_TRACER1 = FIXTURES_DIR / "Order_TRACER1.zip"
GEOMETRYLESS_GDB = FIXTURES_DIR / "geometryless_gdb.zip"
POINT_Z_GDB = FIXTURES_DIR / "point_z_gdb.zip"

DEFAULT_POLICY = discovery.DiscoveryPolicy(
    supported_formats=("OpenFileGDB",), ogrinfo_timeout_seconds=60
)


def _extract(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(destination)
    return destination


class _TempDirMixin:
    def make_temp_dir(self, prefix: str) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        return temp_dir


class FindDatasetsTest(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        self.run_dir = self.make_temp_dir("find-datasets-")
        _extract(ORDER_TRACER1, self.run_dir)

    def test_finds_the_single_vmadd_dataset(self):
        datasets = discovery.find_datasets(self.run_dir, DEFAULT_POLICY)
        self.assertEqual(1, len(datasets))
        path, driver = datasets[0]
        self.assertTrue(str(path).endswith("VMADD.gdb"))
        self.assertEqual("OpenFileGDB", driver)

    def test_companion_files_never_appear_in_output(self):
        datasets = discovery.find_datasets(self.run_dir, DEFAULT_POLICY)
        for path, _ in datasets:
            self.assertNotIn("Creative Commons Licence.html", str(path))
            self.assertNotIn(".pdf", str(path))

    def test_unsupported_shp_format_raises(self):
        (self.run_dir / "layer.shp").write_bytes(b"")
        with self.assertRaises(discovery.UnsupportedFormat):
            discovery.find_datasets(self.run_dir, DEFAULT_POLICY)

    def test_empty_run_directory_raises_delivery_empty(self):
        empty_dir = self.make_temp_dir("empty-run-")
        with self.assertRaises(discovery.DeliveryEmpty):
            discovery.find_datasets(empty_dir, DEFAULT_POLICY)

    def test_companion_files_only_raises_delivery_empty(self):
        companions_only = self.make_temp_dir("companions-only-")
        (companions_only / "Creative Commons Licence.html").write_text("x")
        (companions_only / "VICMAP_ADDRESS_fixture.pdf").write_bytes(b"%PDF-1.4\n")
        with self.assertRaises(discovery.DeliveryEmpty):
            discovery.find_datasets(companions_only, DEFAULT_POLICY)

    def test_dataset_with_zero_layers_raises_delivery_empty(self):
        empty_gdb_dir = self.make_temp_dir("zero-layer-")
        (empty_gdb_dir / "EMPTY.gdb").mkdir()
        with patch.object(discovery.pyogrio, "list_layers", return_value=[]):
            with self.assertRaises(discovery.DeliveryEmpty):
                discovery.find_datasets(empty_gdb_dir, DEFAULT_POLICY)

    def test_driver_reported_by_read_info_differs_from_extension_raises(self):
        lying_dir = self.make_temp_dir("lying-driver-")
        (lying_dir / "FAKE.gdb").mkdir()
        with patch.object(
            discovery.pyogrio, "list_layers", return_value=[["LAYER1", "Point"]]
        ), patch.object(
            discovery.pyogrio, "read_info", return_value={"driver": "GPKG"}
        ):
            with self.assertRaises(discovery.UnsupportedFormat):
                discovery.find_datasets(lying_dir, DEFAULT_POLICY)

    def test_injected_list_layers_exception_surfaces_as_layer_unreadable(self):
        lying_dir = self.make_temp_dir("list-layers-raises-")
        (lying_dir / "FAKE.gdb").mkdir()
        with patch.object(
            discovery.pyogrio,
            "list_layers",
            side_effect=RuntimeError("some pyogrio/GDAL diagnostic text"),
        ):
            with self.assertRaises(discovery.LayerUnreadable) as ctx:
                discovery.find_datasets(lying_dir, DEFAULT_POLICY)
        self.assertNotIn("pyogrio", str(ctx.exception))
        self.assertNotIn("GDAL", str(ctx.exception))
        self.assertNotIn("diagnostic", str(ctx.exception))
        self.assertEqual("layer_unreadable", str(ctx.exception))

    def test_uppercase_geodatabase_extension_is_recognized(self):
        # At HEAD (pre-02-07) this ends in DeliveryEmpty: the uppercase
        # directory is never examined because the extension lookup is
        # case-sensitive (WR-01).
        gdb_dir = self.run_dir / (
            "gda2020_vicgrid/filegdb/whole_of_dataset/victoria/VMADD.gdb"
        )
        gdb_dir.rename(gdb_dir.with_name("VMADD.GDB"))
        datasets = discovery.find_datasets(self.run_dir, DEFAULT_POLICY)
        self.assertEqual(1, len(datasets))
        path, driver = datasets[0]
        self.assertTrue(str(path).endswith("VMADD.GDB"))
        self.assertEqual("OpenFileGDB", driver)

    def test_uppercase_unsupported_extension_raises_unsupported_format(self):
        # At HEAD (pre-02-07) this also ends in DeliveryEmpty instead of
        # naming the unsupported format, for the same case-sensitivity
        # reason (WR-01) -- mirrors test_unsupported_shp_format_raises.
        empty_dir = self.make_temp_dir("uppercase-unsupported-")
        (empty_dir / "layer.SHP").write_bytes(b"")
        with self.assertRaises(discovery.UnsupportedFormat):
            discovery.find_datasets(empty_dir, DEFAULT_POLICY)

    def test_does_not_descend_into_a_recognized_dataset_directory(self):
        nested_dir = self.make_temp_dir("nested-")
        gdb_dir = nested_dir / "OUTER.gdb"
        gdb_dir.mkdir()
        (gdb_dir / "inner.shp").write_bytes(b"")
        with patch.object(
            discovery.pyogrio, "list_layers", return_value=[["LAYER1", "Point"]]
        ), patch.object(
            discovery.pyogrio, "read_info", return_value={"driver": "OpenFileGDB"}
        ):
            datasets = discovery.find_datasets(nested_dir, DEFAULT_POLICY)
        self.assertEqual(1, len(datasets))
        self.assertTrue(str(datasets[0][0]).endswith("OUTER.gdb"))


class ReadFieldSchemaTest(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        self.run_dir = self.make_temp_dir("read-field-schema-")
        _extract(ORDER_TRACER1, self.run_dir)
        self.dataset_path = (
            self.run_dir
            / "gda2020_vicgrid"
            / "filegdb"
            / "whole_of_dataset"
            / "victoria"
            / "VMADD.gdb"
        )

    def test_reads_real_address_schema(self):
        schema = discovery.read_field_schema(self.dataset_path, DEFAULT_POLICY)
        fields_by_name = {field.name: field for field in schema["ADDRESS"]}
        self.assertEqual("String", fields_by_name["EZI_ADDRESS"].ogr_type)
        self.assertEqual(80, fields_by_name["EZI_ADDRESS"].width)
        self.assertEqual("Integer", fields_by_name["UFI"].ogr_type)
        self.assertIsNone(fields_by_name["UFI"].width)
        self.assertIsNone(fields_by_name["UFI"].precision)
        self.assertTrue(fields_by_name["UFI"].nullable)

    def _run_with_payload(self, payload: dict):
        completed = MagicMock()
        completed.stdout = json.dumps(payload)
        with patch.object(discovery.subprocess, "run", return_value=completed):
            return discovery.read_field_schema(self.dataset_path, DEFAULT_POLICY)

    def test_field_missing_name_raises_schema_incomplete(self):
        payload = {
            "layers": [
                {"name": "L", "fields": [{"type": "String", "nullable": True}]}
            ]
        }
        with self.assertRaises(discovery.LayerSchemaIncomplete):
            self._run_with_payload(payload)

    def test_field_missing_type_raises_schema_incomplete(self):
        payload = {
            "layers": [{"name": "L", "fields": [{"name": "F", "nullable": True}]}]
        }
        with self.assertRaises(discovery.LayerSchemaIncomplete):
            self._run_with_payload(payload)

    def test_field_missing_nullable_raises_schema_incomplete(self):
        payload = {
            "layers": [{"name": "L", "fields": [{"name": "F", "type": "String"}]}]
        }
        with self.assertRaises(discovery.LayerSchemaIncomplete):
            self._run_with_payload(payload)

    def test_field_with_no_width_or_precision_is_not_a_failure(self):
        payload = {
            "layers": [
                {
                    "name": "L",
                    "fields": [{"name": "F", "type": "Integer", "nullable": True}],
                }
            ]
        }
        schema = self._run_with_payload(payload)
        field = schema["L"][0]
        self.assertIsNone(field.width)
        self.assertIsNone(field.precision)

    def test_empty_field_list_raises_schema_incomplete(self):
        payload = {"layers": [{"name": "L", "fields": []}]}
        with self.assertRaises(discovery.LayerSchemaIncomplete):
            self._run_with_payload(payload)

    def test_called_process_error_raises_layer_unreadable(self):
        with patch.object(
            discovery.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, ["ogrinfo"], stderr="boom"),
        ):
            with self.assertRaises(discovery.LayerUnreadable) as ctx:
                discovery.read_field_schema(self.dataset_path, DEFAULT_POLICY)
        self.assertEqual("layer_unreadable", str(ctx.exception))

    def test_timeout_raises_layer_unreadable(self):
        with patch.object(
            discovery.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["ogrinfo"], 60),
        ):
            with self.assertRaises(discovery.LayerUnreadable):
                discovery.read_field_schema(self.dataset_path, DEFAULT_POLICY)

    def test_invalid_json_raises_layer_unreadable(self):
        completed = MagicMock()
        completed.stdout = "not json{{"
        with patch.object(discovery.subprocess, "run", return_value=completed):
            with self.assertRaises(discovery.LayerUnreadable):
                discovery.read_field_schema(self.dataset_path, DEFAULT_POLICY)


class ProfileLayerTest(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        self.run_dir = self.make_temp_dir("profile-layer-")

    def _address_dataset(self):
        _extract(ORDER_TRACER1, self.run_dir)
        dataset_path = (
            self.run_dir
            / "gda2020_vicgrid"
            / "filegdb"
            / "whole_of_dataset"
            / "victoria"
            / "VMADD.gdb"
        )
        field_schema = discovery.read_field_schema(dataset_path, DEFAULT_POLICY)
        return dataset_path, field_schema

    def test_address_profile_full_fields(self):
        dataset_path, field_schema = self._address_dataset()
        profile = discovery.profile_layer(
            dataset_path,
            "ADDRESS",
            driver="OpenFileGDB",
            dataset_relative_path="gda2020_vicgrid/filegdb/whole_of_dataset/victoria/VMADD.gdb",
            field_schema=field_schema["ADDRESS"],
            policy=DEFAULT_POLICY,
        )
        self.assertEqual(2, profile.feature_count)
        self.assertEqual(7899, profile.epsg)
        self.assertEqual("Point", profile.geometry_type)
        self.assertEqual("OBJECTID", profile.fid_column)
        self.assertEqual("SHAPE", profile.geometry_column)
        self.assertTrue(profile.spatial)

        fields_by_name = {field.name: field for field in profile.fields}
        self.assertEqual(80, fields_by_name["EZI_ADDRESS"].width)
        self.assertIsNone(fields_by_name["UFI"].width)
        self.assertIsNone(fields_by_name["UFI"].precision)

    def test_geometryless_profile_never_invokes_crs_resolver(self):
        _extract(GEOMETRYLESS_GDB, self.run_dir)
        dataset_path = self.run_dir / "LOOKUP.gdb"
        field_schema = discovery.read_field_schema(dataset_path, DEFAULT_POLICY)

        with patch.object(
            discovery.pyproj.CRS,
            "from_user_input",
            side_effect=AssertionError("CRS resolver must never be invoked"),
        ):
            profile = discovery.profile_layer(
                dataset_path,
                "LOOKUP",
                driver="OpenFileGDB",
                dataset_relative_path="LOOKUP.gdb",
                field_schema=field_schema["LOOKUP"],
                policy=DEFAULT_POLICY,
            )

        self.assertFalse(profile.spatial)
        self.assertIsNone(profile.geometry_type)
        self.assertIsNone(profile.geometry_column)
        self.assertIsNone(profile.source_wkt)
        self.assertIsNone(profile.epsg)

    def test_point_z_geometry_type_retains_the_space(self):
        _extract(POINT_Z_GDB, self.run_dir)
        dataset_path = self.run_dir / "POINTZ.gdb"
        field_schema = discovery.read_field_schema(dataset_path, DEFAULT_POLICY)
        profile = discovery.profile_layer(
            dataset_path,
            "POINTZ",
            driver="OpenFileGDB",
            dataset_relative_path="POINTZ.gdb",
            field_schema=field_schema["POINTZ"],
            policy=DEFAULT_POLICY,
        )
        self.assertEqual("Point Z", profile.geometry_type)

    def _address_field_schema(self):
        _, field_schema = self._address_dataset()
        return field_schema["ADDRESS"]

    def test_unknown_geometry_type_raises_geometry_type_unresolved(self):
        field_schema = self._address_field_schema()
        info = {
            "fid_column": "OBJECTID",
            "features": 1,
            "geometry_type": "Unknown",
            "geometry_name": "SHAPE",
            "crs": "EPSG:7899",
            "total_bounds": None,
        }
        with patch.object(discovery.pyogrio, "read_info", return_value=info):
            with self.assertRaises(discovery.GeometryTypeUnresolved):
                discovery.profile_layer(
                    Path("unused.gdb"),
                    "ADDRESS",
                    driver="OpenFileGDB",
                    dataset_relative_path="unused.gdb",
                    field_schema=field_schema,
                    policy=DEFAULT_POLICY,
                )

    def test_zero_features_raises_layer_empty(self):
        field_schema = self._address_field_schema()
        info = {
            "fid_column": "OBJECTID",
            "features": 0,
            "geometry_type": "Point",
            "geometry_name": "SHAPE",
            "crs": "EPSG:7899",
            "total_bounds": None,
        }
        with patch.object(discovery.pyogrio, "read_info", return_value=info):
            with self.assertRaises(discovery.LayerEmpty):
                discovery.profile_layer(
                    Path("unused.gdb"),
                    "ADDRESS",
                    driver="OpenFileGDB",
                    dataset_relative_path="unused.gdb",
                    field_schema=field_schema,
                    policy=DEFAULT_POLICY,
                )

    def test_one_feature_returns_a_profile(self):
        field_schema = self._address_field_schema()
        info = {
            "fid_column": "OBJECTID",
            "features": 1,
            "geometry_type": "Point",
            "geometry_name": "SHAPE",
            "crs": "EPSG:7899",
            "total_bounds": (0.0, 0.0, 1.0, 1.0),
        }
        with patch.object(discovery.pyogrio, "read_info", return_value=info):
            profile = discovery.profile_layer(
                Path("unused.gdb"),
                "ADDRESS",
                driver="OpenFileGDB",
                dataset_relative_path="unused.gdb",
                field_schema=field_schema,
                policy=DEFAULT_POLICY,
            )
        self.assertEqual(1, profile.feature_count)

    def test_unresolvable_crs_raises_and_records_no_substituted_srid(self):
        field_schema = self._address_field_schema()
        info = {
            "fid_column": "OBJECTID",
            "features": 1,
            "geometry_type": "Point",
            "geometry_name": "SHAPE",
            "crs": "LOCAL_CS[\"nonsense\"]",
            "total_bounds": None,
        }
        unresolved_crs = MagicMock()
        unresolved_crs.to_epsg.return_value = None
        with patch.object(discovery.pyogrio, "read_info", return_value=info), patch.object(
            discovery.pyproj.CRS, "from_user_input", return_value=unresolved_crs
        ):
            with self.assertRaises(discovery.CrsUnresolved):
                discovery.profile_layer(
                    Path("unused.gdb"),
                    "ADDRESS",
                    driver="OpenFileGDB",
                    dataset_relative_path="unused.gdb",
                    field_schema=field_schema,
                    policy=DEFAULT_POLICY,
                )

    def test_ogrinfo_style_injected_failures_never_reach_profile_layer_as_raw_text(self):
        # profile_layer itself never calls ogrinfo -- this proves that an
        # empty field_schema (the only ogrinfo-sourced input it receives)
        # is rejected before any pyogrio work happens.
        with self.assertRaises(discovery.LayerSchemaIncomplete):
            discovery.profile_layer(
                Path("unused.gdb"),
                "ADDRESS",
                driver="OpenFileGDB",
                dataset_relative_path="unused.gdb",
                field_schema=(),
                policy=DEFAULT_POLICY,
            )


class DiscoverLayersTest(_TempDirMixin, unittest.TestCase):
    def test_end_to_end_over_order_tracer1(self):
        run_dir = self.make_temp_dir("discover-layers-")
        _extract(ORDER_TRACER1, run_dir)
        profiles = discovery.discover_layers(run_dir, DEFAULT_POLICY)
        self.assertEqual(1, len(profiles))
        self.assertEqual("ADDRESS", profiles[0].layer_name)

    def test_ordering_and_no_dedup_over_two_dataset_tree(self):
        run_dir = self.make_temp_dir("discover-layers-two-")
        source_gdb = (
            self.make_temp_dir("discover-layers-source-")
        )
        _extract(ORDER_TRACER1, source_gdb)
        source_gdb_path = (
            source_gdb
            / "gda2020_vicgrid"
            / "filegdb"
            / "whole_of_dataset"
            / "victoria"
            / "VMADD.gdb"
        )

        dataset_a = run_dir / "dataset_a" / "VMADD.gdb"
        dataset_b = run_dir / "dataset_b" / "VMADD.gdb"
        shutil.copytree(source_gdb_path, dataset_a)
        shutil.copytree(source_gdb_path, dataset_b)

        profiles = discovery.discover_layers(run_dir, DEFAULT_POLICY)

        self.assertEqual(2, len(profiles))
        self.assertEqual("dataset_a/VMADD.gdb", profiles[0].dataset_relative_path)
        self.assertEqual("dataset_b/VMADD.gdb", profiles[1].dataset_relative_path)
        # Byte-identical profiles (aside from their dataset path) remain two
        # distinct entries -- nothing here merges or deduplicates.
        self.assertEqual(profiles[0].layer_name, profiles[1].layer_name)
        self.assertEqual(profiles[0].feature_count, profiles[1].feature_count)
        self.assertEqual(profiles[0].fields, profiles[1].fields)


if __name__ == "__main__":
    unittest.main()
