"""Frozen ``ImportManifest`` contract and canonical ``manifest.json`` persistence.

The frozen in-process object is Phase 3's API; ``manifest.json`` makes
"immutable" provable and gives the operator something durable to review and
diff between runs (D-29). ``manifest.json`` holds full detail -- complete
paths, real layer names, full field lists -- and is git-ignored (D-31);
operator-facing output stays redacted via ``evidence.py``'s ``SuccessEvent``
machinery, never this module's payload directly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from vicmap_acquire.discovery import FieldProfile, LayerProfile


MANIFEST_SCHEMA_VERSION = 1


class ManifestFailure(RuntimeError):
    """A closed manifest failure carrying no filesystem-controlled text."""

    code = "manifest_write_failed"

    def __init__(self) -> None:
        super().__init__(self.code)


class ManifestWriteFailed(ManifestFailure):
    code = "manifest_write_failed"


@dataclass(frozen=True)
class CompanionFile:
    relative_path: str
    byte_count: int
    sha256: str


@dataclass(frozen=True)
class ManifestLayer:
    profile: LayerProfile
    target_table: str


@dataclass(frozen=True)
class ImportManifest:
    schema_version: int
    order_id: str
    run_timestamp: str
    run_directory: str
    artifact_sha256: str
    artifact_byte_count: int
    message_fingerprint: str
    layers: tuple[ManifestLayer, ...]
    companions: tuple[CompanionFile, ...]


def build_manifest(
    *,
    order_id: str,
    run_timestamp: str,
    run_directory: Path,
    artifact_sha256: str,
    artifact_byte_count: int,
    message_fingerprint: str,
    layers: tuple[ManifestLayer, ...],
    companions: tuple[CompanionFile, ...],
) -> ImportManifest:
    """Build the frozen in-process manifest object -- the Phase 3 API."""

    return ImportManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        order_id=order_id,
        run_timestamp=run_timestamp,
        run_directory=str(run_directory),
        artifact_sha256=artifact_sha256,
        artifact_byte_count=artifact_byte_count,
        message_fingerprint=message_fingerprint,
        layers=layers,
        companions=companions,
    )


def _field_payload(field: FieldProfile) -> dict:
    return {
        "name": field.name,
        "ogr_type": field.ogr_type,
        "width": field.width,
        "precision": field.precision,
        "nullable": field.nullable,
    }


def _layer_payload(manifest_layer: ManifestLayer) -> dict:
    profile = manifest_layer.profile
    return {
        "target_table": manifest_layer.target_table,
        "dataset_relative_path": profile.dataset_relative_path,
        "dataset_stem": profile.dataset_stem,
        "layer_name": profile.layer_name,
        "driver": profile.driver,
        "spatial": profile.spatial,
        "geometry_type": profile.geometry_type,
        "geometry_column": profile.geometry_column,
        "fid_column": profile.fid_column,
        "feature_count": profile.feature_count,
        "source_wkt": profile.source_wkt,
        "epsg": profile.epsg,
        "extent": list(profile.extent) if profile.extent is not None else None,
        "fields": [_field_payload(field) for field in profile.fields],
    }


def _companion_payload(companion: CompanionFile) -> dict:
    return {
        "relative_path": companion.relative_path,
        "byte_count": companion.byte_count,
        "sha256": companion.sha256,
    }


def manifest_payload(manifest: ImportManifest) -> dict:
    """Return the complete, full-detail JSON-serializable manifest payload."""

    return {
        "schema_version": manifest.schema_version,
        "order_id": manifest.order_id,
        "run_timestamp": manifest.run_timestamp,
        "run_directory": manifest.run_directory,
        "artifact_sha256": manifest.artifact_sha256,
        "artifact_byte_count": manifest.artifact_byte_count,
        "message_fingerprint": manifest.message_fingerprint,
        "layers": [_layer_payload(layer) for layer in manifest.layers],
        "companions": [_companion_payload(companion) for companion in manifest.companions],
    }


def write_manifest(manifest: ImportManifest, run_directory: Path) -> str:
    """Write ``manifest.json`` + ``manifest.json.sha256`` into ``run_directory``.

    Reuses the repository's one existing deterministic-JSON idiom
    (``evidence.py``'s ``json.dumps(..., sort_keys=True, separators=(",", ":"))``).
    A file cannot embed its own hash, so the digest lives in the sidecar,
    computed over the canonical bytes without the trailing newline. Returns
    the digest.
    """

    try:
        payload = manifest_payload(manifest)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        manifest_path = run_directory / "manifest.json"
        sidecar_path = run_directory / "manifest.json.sha256"
        manifest_path.write_text(canonical + "\n", encoding="utf-8")
        sidecar_path.write_text(digest + "\n", encoding="utf-8")
        return digest
    except OSError:
        raise ManifestWriteFailed() from None
