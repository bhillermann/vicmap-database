"""Differential test: discovery vs an independently authored ``ogrinfo`` oracle.

CRITICAL PROPERTY OF THIS FILE (state it here so a future refactor does not
casually undo it, following the discipline established by
``tests/test_html_visibility_differential.py``): the oracle functions below
(``_run_ogrinfo_json``, ``_oracle_layer``, ``_oracle_geometry_normalized``,
``_oracle_epsg``, ``_oracle_facts``) MUST stay independent of
``vicmap_acquire.discovery``'s implementation. They invoke ``ogrinfo -json``
themselves via their own ``subprocess.run`` call and parse the resulting
JSON themselves. This module imports exactly two names from
``vicmap_acquire.discovery``: ``discover_layers`` (the single public entry
point under test -- the complete pipeline this file cross-checks) and
``DiscoveryPolicy`` (the frozen config dataclass ``discover_layers``
requires as an argument -- a data container, not parsing/computation logic).
It must never import ``read_field_schema``, ``profile_layer``,
``_EXTENSION_DRIVERS``, or any geometry-type normalization helper from
``vicmap_acquire.discovery`` -- even for convenience or deduplication. A
hand-picked test case that shares the implementation's own parsing already
shares its blind spot; that is precisely how a flat suppression counter
survived four review passes in Phase 1 (see
``test_html_visibility_differential.py``'s docstring for that history). The
``ImportIndependenceTest`` below enforces this via ``ast`` inspection of
this module's own source, so the constraint cannot silently erode.

Geometry-type vocabulary genuinely differs between the two tools for the
same underlying geometry (``pyogrio.read_info()`` reports ``'Point Z'``,
``ogrinfo -json`` reports ``'PointZ'`` -- verified in 02-RESEARCH.md's
Pitfall 3). Both sides are normalized independently -- a base type plus
separate ``has_z``/``has_m`` booleans, derived from each tool's own spelling
convention -- rather than string-matching one tool's spelling against the
other's.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from vicmap_acquire.discovery import DiscoveryPolicy, discover_layers

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
ORDER_TRACER1 = FIXTURES_DIR / "Order_TRACER1.zip"
GEOMETRYLESS_GDB = FIXTURES_DIR / "geometryless_gdb.zip"
POINT_Z_GDB = FIXTURES_DIR / "point_z_gdb.zip"

# The only names this module is permitted to import from
# vicmap_acquire.discovery -- see the module docstring and
# ImportIndependenceTest below.
_ALLOWED_DISCOVERY_IMPORTS = frozenset({"discover_layers", "DiscoveryPolicy"})


# ---------------------------------------------------------------------------
# Independent ogrinfo oracle. Never calls into vicmap_acquire.discovery.
# ---------------------------------------------------------------------------


def _run_ogrinfo_json(dataset_path: Path) -> dict:
    """Invoke ``ogrinfo -json -al -so`` directly and parse its own JSON."""

    result = subprocess.run(
        ["ogrinfo", "-json", "-al", "-so", str(dataset_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def _oracle_layer(payload: dict, layer_name: str) -> dict:
    for layer in payload["layers"]:
        if layer["name"] == layer_name:
            return layer
    raise AssertionError(f"layer {layer_name!r} not present in ogrinfo output")


def _oracle_geometry_normalized(layer: dict) -> tuple[str, bool, bool] | None:
    """Independently normalize ogrinfo's own geometry spelling.

    ``ogrinfo -json`` spells a 3D point ``'PointZ'`` (no space) -- a base
    type with an appended ``Z``/``M``/``ZM`` suffix, not a separate token.
    An empty ``geometryFields`` list means the layer has no geometry field
    at all (the oracle's own non-spatial signal), which normalizes to
    ``None``.
    """

    geometry_fields = layer.get("geometryFields") or []
    if not geometry_fields:
        return None
    text = geometry_fields[0]["type"]
    has_z = text.endswith("ZM") or text.endswith("Z")
    has_m = text.endswith("ZM") or text.endswith("M")
    base = text
    for suffix in ("ZM", "Z", "M"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return (base.casefold(), has_z, has_m)


def _oracle_epsg(layer: dict) -> int | None:
    """Independently resolve EPSG from ogrinfo's own ``projjson`` block.

    Never touches ``pyproj`` -- reads the top-level ``id`` node of the
    geometry field's ``coordinateSystem.projjson``, which is GDAL's own
    resolved authority/code for the layer's CRS as a whole (not a nested
    datum/conversion ``id``, which sits deeper in the same document under
    ``base_crs``/``conversion``).
    """

    geometry_fields = layer.get("geometryFields") or []
    if not geometry_fields:
        return None
    coordinate_system = geometry_fields[0].get("coordinateSystem")
    if not coordinate_system:
        return None
    projjson = coordinate_system.get("projjson")
    if not projjson:
        return None
    identifier = projjson.get("id")
    if not identifier or identifier.get("authority") != "EPSG":
        return None
    return int(identifier["code"])


def _oracle_facts(dataset_path: Path, layer_name: str) -> dict:
    payload = _run_ogrinfo_json(dataset_path)
    layer = _oracle_layer(payload, layer_name)
    return {
        "feature_count": layer["featureCount"],
        "field_names": [field["name"] for field in layer["fields"]],
        "field_types": [field["type"] for field in layer["fields"]],
        "geometry_normalized": _oracle_geometry_normalized(layer),
        "epsg": _oracle_epsg(layer),
    }


# ---------------------------------------------------------------------------
# Independent normalization of the *implementation's* (pyogrio) spelling.
# Deliberately a separate function with its own tokenization rule, derived
# from pyogrio's own vocabulary ("Point Z", space-separated), not shared
# with the oracle's suffix-stripping logic above.
# ---------------------------------------------------------------------------


def _implementation_geometry_normalized(
    geometry_type: str | None,
) -> tuple[str, bool, bool] | None:
    if geometry_type is None:
        return None
    tokens = geometry_type.split()
    base = tokens[0] if tokens else geometry_type
    suffix = tokens[1] if len(tokens) > 1 else ""
    has_z = "Z" in suffix
    has_m = "M" in suffix
    return (base.casefold(), has_z, has_m)


class DiscoveryOracleAgreementTest(unittest.TestCase):
    def setUp(self):
        self.run_dir = Path(tempfile.mkdtemp(prefix="discovery-oracle-"))
        self.addCleanup(shutil.rmtree, self.run_dir, ignore_errors=True)
        self.policy = DiscoveryPolicy(
            supported_formats=("OpenFileGDB",), ogrinfo_timeout_seconds=60
        )

    def _profile_and_oracle(self, archive: Path, layer_name: str):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(self.run_dir)
        profiles = discover_layers(self.run_dir, self.policy)
        profile = next(p for p in profiles if p.layer_name == layer_name)
        dataset_path = self.run_dir / profile.dataset_relative_path
        oracle = _oracle_facts(dataset_path, layer_name)
        return profile, oracle

    def test_order_tracer1_address_layer_agrees_with_oracle(self):
        profile, oracle = self._profile_and_oracle(ORDER_TRACER1, "ADDRESS")

        self.assertEqual(oracle["feature_count"], profile.feature_count)
        self.assertEqual(oracle["field_names"], [field.name for field in profile.fields])
        self.assertEqual(
            oracle["field_types"], [field.ogr_type for field in profile.fields]
        )
        self.assertEqual(
            oracle["geometry_normalized"],
            _implementation_geometry_normalized(profile.geometry_type),
        )
        self.assertEqual(oracle["epsg"], profile.epsg)

    def test_geometryless_gdb_both_sides_agree_there_is_no_crs(self):
        profile, oracle = self._profile_and_oracle(GEOMETRYLESS_GDB, "LOOKUP")

        self.assertIsNone(oracle["epsg"])
        self.assertIsNone(profile.epsg)
        self.assertIsNone(oracle["geometry_normalized"])
        self.assertIsNone(_implementation_geometry_normalized(profile.geometry_type))
        self.assertEqual(oracle["feature_count"], profile.feature_count)
        self.assertEqual(oracle["field_names"], [field.name for field in profile.fields])
        self.assertEqual(
            oracle["field_types"], [field.ogr_type for field in profile.fields]
        )

    def test_point_z_gdb_agrees_after_vocabulary_normalization(self):
        profile, oracle = self._profile_and_oracle(POINT_Z_GDB, "POINTZ")

        # Prove the normalization is real, not a coincidental string match:
        # the implementation side sees pyogrio's spelling ("Point Z", with a
        # space) and the oracle side independently sees ogrinfo's different
        # spelling ("PointZ", no space) for the exact same geometry.
        dataset_path = self.run_dir / profile.dataset_relative_path
        raw_oracle_type = _oracle_layer(_run_ogrinfo_json(dataset_path), "POINTZ")[
            "geometryFields"
        ][0]["type"]
        self.assertEqual("Point Z", profile.geometry_type)
        self.assertEqual("PointZ", raw_oracle_type)
        self.assertNotEqual(raw_oracle_type, profile.geometry_type)

        normalized_implementation = _implementation_geometry_normalized(
            profile.geometry_type
        )
        self.assertEqual(("point", True, False), normalized_implementation)
        self.assertEqual(oracle["geometry_normalized"], normalized_implementation)
        self.assertEqual(oracle["feature_count"], profile.feature_count)
        self.assertEqual(oracle["epsg"], profile.epsg)


class ImportIndependenceTest(unittest.TestCase):
    def test_only_the_allowed_names_are_imported_from_discovery(self):
        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(Path(__file__)))

        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "vicmap_acquire.discovery":
                for alias in node.names:
                    imported_names.add(alias.name)

        self.assertEqual(
            _ALLOWED_DISCOVERY_IMPORTS,
            imported_names,
            "test_discovery_differential.py must import exactly "
            f"{sorted(_ALLOWED_DISCOVERY_IMPORTS)} from vicmap_acquire.discovery -- "
            f"found {sorted(imported_names)}. Importing any parsing/computation "
            "helper (read_field_schema, profile_layer, _EXTENSION_DRIVERS, or a "
            "geometry-type normalization helper) defeats the independence this "
            "oracle exists to provide.",
        )


if __name__ == "__main__":
    unittest.main()
