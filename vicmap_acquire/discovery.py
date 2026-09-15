"""pyogrio + ogrinfo layer discovery and profiling (D-33..D-40).

``pyogrio.read_info()`` supplies the bulk metadata (feature count, geometry
type, CRS, FID/geometry column names) without materializing features. It
does not expose field width/precision/nullability, so a single
``ogrinfo -json -al -so`` subprocess call per dataset supplies exactly that
gap (verified in 02-RESEARCH.md's Pattern 3). Every public entry point is
total with respect to its inputs: an unexpected exception collapses to one
typed closed failure, never raw driver or subprocess text.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pyogrio
import pyproj


class DiscoveryFailure(RuntimeError):
    """A closed discovery failure carrying no driver- or subprocess-controlled text."""

    code = "layer_unreadable"

    def __init__(self) -> None:
        super().__init__(self.code)


class UnsupportedFormat(DiscoveryFailure):
    code = "unsupported_format"


class DeliveryEmpty(DiscoveryFailure):
    code = "delivery_empty"


class LayerUnreadable(DiscoveryFailure):
    code = "layer_unreadable"


class LayerEmpty(DiscoveryFailure):
    code = "layer_empty"


class GeometryTypeUnresolved(DiscoveryFailure):
    code = "geometry_type_unresolved"


class CrsUnresolved(DiscoveryFailure):
    code = "crs_unresolved"


class LayerSchemaIncomplete(DiscoveryFailure):
    code = "layer_schema_incomplete"


def _positive_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("discovery policy values must be positive integers")
    return value


@dataclass(frozen=True)
class DiscoveryPolicy:
    """Complete non-secret policy for one discovery pass (D-34)."""

    supported_formats: tuple[str, ...]
    ogrinfo_timeout_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.supported_formats, tuple) or not self.supported_formats:
            raise ValueError("supported_formats must be a non-empty tuple")
        for fmt in self.supported_formats:
            if not isinstance(fmt, str) or not fmt:
                raise ValueError("supported_formats entries must be non-empty strings")
        _positive_integer(self.ogrinfo_timeout_seconds)


@dataclass(frozen=True)
class FieldProfile:
    name: str
    ogr_type: str
    width: int | None
    precision: int | None
    nullable: bool


@dataclass(frozen=True)
class LayerProfile:
    dataset_relative_path: str
    dataset_stem: str
    layer_name: str
    driver: str
    spatial: bool
    geometry_type: str | None
    geometry_column: str | None
    fid_column: str
    feature_count: int
    source_wkt: str | None
    epsg: int | None
    extent: tuple[float, float, float, float] | None
    fields: tuple[FieldProfile, ...]


def find_datasets(run_directory: Path) -> tuple[Path, ...]:
    """Return every ``.gdb`` dataset directory beneath ``run_directory``, sorted."""

    return tuple(sorted(path for path in run_directory.rglob("*.gdb") if path.is_dir()))


def read_field_schema(
    dataset_path: Path, policy: DiscoveryPolicy
) -> dict[str, tuple[FieldProfile, ...]]:
    """Return ``{layer_name: (FieldProfile, ...)}`` via one ``ogrinfo -json`` call.

    ``-so`` (summary-only) avoids a full geometry scan; ``-al`` enumerates
    every layer's fields in the one subprocess invocation, so this runs
    once per dataset, not once per layer.
    """

    try:
        result = subprocess.run(
            ["ogrinfo", "-json", "-al", "-so", str(dataset_path)],
            capture_output=True,
            text=True,
            timeout=policy.ogrinfo_timeout_seconds,
            check=True,
        )
        payload = json.loads(result.stdout)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        OSError,
    ):
        raise LayerUnreadable() from None

    schema: dict[str, tuple[FieldProfile, ...]] = {}
    try:
        for layer in payload["layers"]:
            fields = []
            for field in layer.get("fields", []):
                fields.append(
                    FieldProfile(
                        name=field["name"],
                        ogr_type=field["type"],
                        width=field.get("width"),
                        precision=field.get("precision"),
                        nullable=bool(field.get("nullable", True)),
                    )
                )
            schema[layer["name"]] = tuple(fields)
    except (KeyError, TypeError):
        raise LayerUnreadable() from None
    return schema


def _resolve_epsg(crs_field: str | None) -> int:
    """Resolve a CRS string/WKT to an EPSG code, hard-stopping if unresolved (D-39)."""

    if crs_field is None:
        raise CrsUnresolved()
    try:
        epsg = pyproj.CRS.from_user_input(crs_field).to_epsg()
    except Exception:
        raise CrsUnresolved() from None
    if epsg is None:
        raise CrsUnresolved()
    return epsg


def profile_layer(
    dataset_path: Path,
    layer_name: str,
    *,
    dataset_relative_path: str,
    field_schema: tuple[FieldProfile, ...],
    policy: DiscoveryPolicy,
) -> LayerProfile:
    """Profile one layer via ``pyogrio.read_info()``, total w.r.t. its inputs.

    ``geometry_type is None`` is D-35's legitimate non-spatial layer, never
    conflated with the exact string ``"Unknown"`` (D-38's hard stop) -- two
    genuinely distinct pyogrio return values.
    """

    try:
        info = pyogrio.read_info(str(dataset_path), layer=layer_name)

        driver = info.get("driver")
        if driver not in policy.supported_formats:
            raise UnsupportedFormat()

        geometry_type = info.get("geometry_type")
        spatial = geometry_type is not None
        if spatial and geometry_type == "Unknown":
            raise GeometryTypeUnresolved()

        feature_count = info.get("features")
        if not isinstance(feature_count, int) or feature_count < 0:
            raise LayerUnreadable()
        if feature_count == 0:
            raise LayerEmpty()

        fid_column = info.get("fid_column")
        geometry_column = info.get("geometry_name") if spatial else None
        if not fid_column:
            raise LayerSchemaIncomplete()
        if spatial and not geometry_column:
            raise LayerSchemaIncomplete()
        if not field_schema:
            raise LayerSchemaIncomplete()

        epsg = _resolve_epsg(info.get("crs")) if spatial else None

        total_bounds = info.get("total_bounds")
        extent = (
            tuple(float(value) for value in total_bounds)
            if total_bounds is not None
            else None
        )

        return LayerProfile(
            dataset_relative_path=dataset_relative_path,
            dataset_stem=Path(dataset_path).stem,
            layer_name=layer_name,
            driver=driver,
            spatial=spatial,
            geometry_type=geometry_type,
            geometry_column=geometry_column,
            fid_column=fid_column,
            feature_count=feature_count,
            source_wkt=info.get("crs") if spatial else None,
            epsg=epsg,
            extent=extent,
            fields=field_schema,
        )
    except DiscoveryFailure:
        raise
    except Exception:
        raise LayerUnreadable() from None


def discover_layers(run_directory: Path, policy: DiscoveryPolicy) -> tuple[LayerProfile, ...]:
    """Discover and profile every layer across every supported dataset.

    Total with respect to its inputs: any stray exception collapses to
    ``LayerUnreadable`` rather than leaking driver or subprocess text.
    """

    try:
        datasets = find_datasets(run_directory)
        if not datasets:
            raise DeliveryEmpty()

        profiles: list[LayerProfile] = []
        for dataset_path in datasets:
            try:
                layer_rows = pyogrio.list_layers(str(dataset_path))
            except Exception:
                raise LayerUnreadable() from None

            field_schema_by_layer = read_field_schema(dataset_path, policy)
            dataset_relative_path = dataset_path.relative_to(run_directory).as_posix()

            for row in layer_rows:
                layer_name = str(row[0])
                field_schema = field_schema_by_layer.get(layer_name)
                if field_schema is None:
                    raise LayerSchemaIncomplete()
                profiles.append(
                    profile_layer(
                        dataset_path,
                        layer_name,
                        dataset_relative_path=dataset_relative_path,
                        field_schema=field_schema,
                        policy=policy,
                    )
                )

        if not profiles:
            raise DeliveryEmpty()

        return tuple(profiles)
    except DiscoveryFailure:
        raise
    except Exception:
        raise LayerUnreadable() from None
