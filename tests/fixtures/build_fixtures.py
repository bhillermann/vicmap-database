"""Standalone, re-runnable generator for the Phase 2 OpenFileGDB test fixtures.

Importing this module performs no filesystem, subprocess, or network work --
every side effect lives behind the ``if __name__ == "__main__":`` guard, so
test modules may import path constants from here without triggering a
regeneration.

Run inside the dev shell so ``ogr2ogr`` resolves from the flake, never the
operator's ambient profile::

    nix develop path:. -c python tests/fixtures/build_fixtures.py

Esri's OpenFileGDB writer (as invoked through ``ogr2ogr``) embeds fresh,
per-invocation random content -- UUIDs and creation/modification timestamps
-- into its internal system catalog tables (``a0000000N.gdbtable``) every
time it creates a geodatabase. Verified this session: two geodatabases built
back-to-back from byte-identical CSV/VRT input differ in several small,
consistently-sized byte regions inside those catalog tables, and a masked
copy with those exact regions zeroed still opens correctly under both
``pyogrio`` and ``ogrinfo`` -- same layers, fields, feature count, geometry,
and CRS. There is no known GDAL config option to pin this content, so
``_canonicalize`` builds each fixture geodatabase ``_SAMPLES`` independent
times and zeroes any byte position that is not identical across every
sample. That is what makes two consecutive invocations of this script
produce byte-identical archives despite the writer's embedded randomness.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent

# Independent generations compared per fixture geodatabase before any byte
# position that varies across all of them is zeroed. Each random byte
# coincides across every sample with probability (1/256)**(_SAMPLES - 1);
# at 4 samples that is ~6e-8 per byte, negligible across the handful of
# volatile bytes a small fixture geodatabase carries.
_SAMPLES = 4

# A fixed, arbitrary UTC date_time for every zip member -- never the
# current time -- so the zip's central directory is byte-identical across
# runs regardless of when the generator executes.
_FIXED_ZIP_DATETIME = (2020, 1, 1, 0, 0, 0)

# Regular file, world-readable: (stat.S_IFREG | 0o644) << 16, spelled out
# numerically so this module needs no `stat` import for one constant.
_REGULAR_FILE_EXTERNAL_ATTR = (0o100644) << 16


def _run_ogr2ogr(*args: str) -> None:
    subprocess.run(["ogr2ogr", *args], check=True, capture_output=True, text=True)


def _canonicalize(build_once) -> Path:
    """Build the same fixture directory ``_SAMPLES`` times and zero every
    byte position that varies across samples, returning the canonicalized
    directory. The other samples are removed before returning.
    """

    samples = [build_once() for _ in range(_SAMPLES)]
    canonical = samples[0]
    others = samples[1:]

    canonical_relatives = sorted(
        path.relative_to(canonical) for path in canonical.rglob("*") if path.is_file()
    )
    for other in others:
        other_relatives = sorted(
            path.relative_to(other) for path in other.rglob("*") if path.is_file()
        )
        if other_relatives != canonical_relatives:
            raise RuntimeError(
                "non-deterministic file layout across independent "
                "fixture generations -- cannot canonicalize"
            )

    for rel in canonical_relatives:
        contents = [(canonical / rel).read_bytes()] + [
            (other / rel).read_bytes() for other in others
        ]
        lengths = {len(content) for content in contents}
        if len(lengths) != 1:
            raise RuntimeError(f"non-deterministic file size for {rel!r}")
        canonical_bytes = bytearray(contents[0])
        for index in range(len(canonical_bytes)):
            if len({content[index] for content in contents}) != 1:
                canonical_bytes[index] = 0
        (canonical / rel).write_bytes(bytes(canonical_bytes))

    for other in others:
        shutil.rmtree(other)
    return canonical


def _collect_gdb_members(gdb_dir: Path, archive_prefix: str) -> list[tuple[Path, str]]:
    members = []
    for path in sorted(gdb_dir.rglob("*")):
        if path.is_file():
            relative = path.relative_to(gdb_dir).as_posix()
            members.append((path, f"{archive_prefix}/{relative}"))
    return members


def _write_zip_deterministic(
    members: list[tuple[Path, str]], destination: Path
) -> None:
    """Write ``members`` -- (absolute source path, archive name) pairs --
    in sorted archive-name order with one fixed ``ZipInfo.date_time`` and
    ``ZIP_DEFLATED``, so two calls over byte-identical inputs produce a
    byte-identical zip.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    ordered = sorted(members, key=lambda item: item[1])
    with zipfile.ZipFile(destination, "w") as archive:
        for source_path, archive_name in ordered:
            info = zipfile.ZipInfo(archive_name, date_time=_FIXED_ZIP_DATETIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = _REGULAR_FILE_EXTERNAL_ATTR
            archive.writestr(info, source_path.read_bytes())


def build_order_tracer1(output_zip: Path) -> None:
    """Build ``Order_TRACER1.zip``: delivery-shaped, one ADDRESS point layer
    plus two unclassified (D-27) companion files at the archive root.
    """

    csv_text = (
        "UFI,PFI,EZI_ADDRESS,SOURCE,SOURCE_VERIFIED,WKT\n"
        '1,PFI0000001,1 EXAMPLE STREET MELBOURNE VIC 3000,GEO,'
        '2020-01-01T00:00:00,"POINT (2500000 2400000)"\n'
        '2,PFI0000002,2 EXAMPLE STREET MELBOURNE VIC 3000,GEO,'
        '2020-01-02T00:00:00,"POINT (2500010 2400010)"\n'
    )
    vrt_text = (
        "<OGRVRTDataSource>\n"
        '  <OGRVRTLayer name="ADDRESS">\n'
        '    <SrcDataSource relativeToVRT="1">address.csv</SrcDataSource>\n'
        "    <SrcLayer>address</SrcLayer>\n"
        "    <GeometryType>wkbPoint</GeometryType>\n"
        "    <LayerSRS>EPSG:7899</LayerSRS>\n"
        '    <GeometryField encoding="WKT" field="WKT"/>\n'
        '    <Field name="UFI" type="Integer" src="UFI"/>\n'
        '    <Field name="PFI" type="String" width="10" src="PFI"/>\n'
        '    <Field name="EZI_ADDRESS" type="String" width="80" src="EZI_ADDRESS"/>\n'
        '    <Field name="SOURCE" type="String" width="3" src="SOURCE"/>\n'
        '    <Field name="SOURCE_VERIFIED" type="DateTime" src="SOURCE_VERIFIED"/>\n'
        "  </OGRVRTLayer>\n"
        "</OGRVRTDataSource>\n"
    )

    def build_once() -> Path:
        workdir = Path(tempfile.mkdtemp(prefix="vmadd-"))
        (workdir / "address.csv").write_text(csv_text, encoding="utf-8")
        (workdir / "address.vrt").write_text(vrt_text, encoding="utf-8")
        gdb_path = workdir / "VMADD.gdb"
        _run_ogr2ogr(
            "-f", "OpenFileGDB", str(gdb_path), str(workdir / "address.vrt"),
            "-nln", "ADDRESS", "-a_srs", "EPSG:7899",
        )
        return gdb_path

    canonical_gdb = _canonicalize(build_once)
    scratch_root = canonical_gdb.parent
    prefix = "gda2020_vicgrid/filegdb/whole_of_dataset/victoria/VMADD.gdb"
    members = _collect_gdb_members(canonical_gdb, prefix)

    # D-27 unclassified companion files, extracted and recorded like any
    # other member but never treated as a dataset. Small placeholder bytes
    # -- content is not load-bearing, only the two filenames are.
    licence_path = scratch_root / "Creative Commons Licence.html"
    licence_path.write_bytes(
        b"<html><body>Creative Commons Attribution 4.0 International "
        b"(fixture placeholder content).</body></html>\n"
    )
    pdf_name = "VICMAP_ADDRESS_b9e9146d-8378-5c37-b6cd-63e3a8d05d02.pdf"
    pdf_path = scratch_root / pdf_name
    pdf_path.write_bytes(b"%PDF-1.4\n% fixture placeholder content\n%%EOF\n")

    members.append((licence_path, "Creative Commons Licence.html"))
    members.append((pdf_path, pdf_name))

    _write_zip_deterministic(members, output_zip)
    shutil.rmtree(scratch_root)


def build_geometryless_gdb(output_zip: Path) -> None:
    """Build ``geometryless_gdb.zip``: one OpenFileGDB holding a
    geometry-less table -- D-35's legitimate non-spatial discovery path.
    """

    csv_text = "CODE,LABEL\nGEO,Geodetic\nSUR,Survey\n"

    def build_once() -> Path:
        workdir = Path(tempfile.mkdtemp(prefix="lookup-"))
        (workdir / "lookup.csv").write_text(csv_text, encoding="utf-8")
        gdb_path = workdir / "LOOKUP.gdb"
        _run_ogr2ogr(
            "-f", "OpenFileGDB", str(gdb_path), str(workdir / "lookup.csv"),
            "-nlt", "NONE", "-oo", "GEOM_POSSIBLE_NAMES=DISABLE", "-nln", "LOOKUP",
        )
        return gdb_path

    canonical_gdb = _canonicalize(build_once)
    scratch_root = canonical_gdb.parent
    members = _collect_gdb_members(canonical_gdb, "LOOKUP.gdb")
    _write_zip_deterministic(members, output_zip)
    shutil.rmtree(scratch_root)


def build_point_z_gdb(output_zip: Path) -> None:
    """Build ``point_z_gdb.zip``: one OpenFileGDB holding a 3D point layer,
    for which pyogrio's ``read_info()`` reports geometry type ``'Point Z'``.
    """

    csv_text = (
        "ID,WKT\n"
        '1,"POINT Z (2500000 2400000 10)"\n'
        '2,"POINT Z (2500010 2400010 20)"\n'
    )

    def build_once() -> Path:
        workdir = Path(tempfile.mkdtemp(prefix="pointz-"))
        (workdir / "pointz.csv").write_text(csv_text, encoding="utf-8")
        gdb_path = workdir / "POINTZ.gdb"
        _run_ogr2ogr(
            "-f", "OpenFileGDB", str(gdb_path), str(workdir / "pointz.csv"),
            "-oo", "GEOM_POSSIBLE_NAMES=WKT", "-nlt", "POINT25D",
            "-a_srs", "EPSG:7899", "-nln", "POINTZ",
        )
        return gdb_path

    canonical_gdb = _canonicalize(build_once)
    scratch_root = canonical_gdb.parent
    members = _collect_gdb_members(canonical_gdb, "POINTZ.gdb")
    _write_zip_deterministic(members, output_zip)
    shutil.rmtree(scratch_root)


def main() -> None:
    build_order_tracer1(FIXTURES_DIR / "Order_TRACER1.zip")
    build_geometryless_gdb(FIXTURES_DIR / "geometryless_gdb.zip")
    build_point_z_gdb(FIXTURES_DIR / "point_z_gdb.zip")
    print(f"Fixtures written to {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
