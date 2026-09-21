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
import os
import re
from dataclasses import dataclass
from pathlib import Path

from vicmap_acquire.discovery import FieldProfile, LayerProfile


MANIFEST_SCHEMA_VERSION = 1

_SIDECAR_DIGEST = re.compile(r"[0-9a-f]{64}")


class ManifestFailure(RuntimeError):
    """A closed manifest failure carrying no filesystem-controlled text."""

    code = "manifest_write_failed"

    def __init__(self) -> None:
        super().__init__(self.code)


class ManifestWriteFailed(ManifestFailure):
    code = "manifest_write_failed"


class ManifestUnreadable(ManifestFailure):
    code = "manifest_unreadable"


class ManifestDigestMismatch(ManifestFailure):
    code = "manifest_digest_mismatch"


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
    """Return the complete, full-detail JSON-serializable manifest payload.

    ``provenance`` nests every run-identity field (D-32) in one object --
    settled Task 1 contract -- distinct from the ``layers``/``companions``
    arrays, which never sort their own element order (only JSON object keys
    are canonically sorted by ``write_manifest``'s ``sort_keys=True``).
    """

    return {
        "schema_version": manifest.schema_version,
        "provenance": {
            "order_id": manifest.order_id,
            "run_timestamp": manifest.run_timestamp,
            "run_directory": manifest.run_directory,
            "artifact_sha256": manifest.artifact_sha256,
            "artifact_byte_count": manifest.artifact_byte_count,
            "message_fingerprint": manifest.message_fingerprint,
        },
        "layers": [_layer_payload(layer) for layer in manifest.layers],
        "companions": [_companion_payload(companion) for companion in manifest.companions],
    }


def _write_new_file_fsync(path: Path, content: str) -> None:
    """Write ``content`` to a brand-new file only, fsyncing before close.

    ``O_EXCL`` makes "does this file already exist" and "create it" one
    atomic kernel operation -- no separate existence check that a second
    concurrent run could race between checking and creating. A
    ``FileExistsError`` (an ``OSError`` subclass) and any other ``OSError``
    both propagate to the caller, which maps every one of them to
    ``ManifestWriteFailed``; the existing file is never opened, truncated,
    or otherwise touched.
    """

    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(directory: Path) -> None:
    """Fsync a directory entry so a completed publish is durably recorded.

    Mirrors ``extraction.py``'s and ``download.py``'s ``_fsync_directory``
    exactly: any ``OSError`` from opening, syncing, or closing the directory
    descriptor is swallowed, because the publish itself has already
    committed and this call only strengthens durability, never correctness.
    Kept as a private per-module copy rather than imported from either --
    each of those two modules already carries its own private copy, so a
    third follows the established convention, and ``manifest.py`` otherwise
    depends only on ``discovery``; importing from ``extraction`` here would
    couple the manifest contract to the extraction module for no contract
    reason.
    """

    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def write_manifest(manifest: ImportManifest, run_directory: Path) -> str:
    """Write ``manifest.json`` + ``manifest.json.sha256`` into ``run_directory``.

    Reuses the repository's one existing deterministic-JSON idiom
    (``evidence.py``'s ``json.dumps(..., sort_keys=True, separators=(",", ":"))``),
    except ``ensure_ascii=False``: the digest and the file must be over the
    manifest's actual UTF-8 bytes, not an ASCII-escaped ``\\uXXXX``
    representation of non-ASCII layer/dataset names, so byte identity holds
    for every delivery regardless of naming. A file cannot embed its own
    hash, so the digest lives in the sidecar, computed over the canonical
    bytes without the trailing newline. Both files are created exclusively
    (never overwritten) and fsynced before close.

    Publication is atomic: if the sidecar write fails after ``manifest.json``
    was already created, that ``manifest.json`` is rolled back (best-effort
    unlink) before the failure is reported, so a failed call always leaves
    ``run_directory`` exactly as it found it and is always retryable into
    the same directory. A run directory that already holds a complete
    ``manifest.json`` is still never overwritten or unlinked -- the first
    create raises before the sidecar write, or any rollback, is ever
    attempted. Once both files exist, ``run_directory``'s own entry is
    fsynced exactly once so the publication survives a crash; a call that
    rolls back never reaches this step, since it has nothing durable to
    record. Returns the digest.
    """

    try:
        payload = manifest_payload(manifest)
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        manifest_path = run_directory / "manifest.json"
        sidecar_path = run_directory / "manifest.json.sha256"

        _write_new_file_fsync(manifest_path, canonical + "\n")
        try:
            _write_new_file_fsync(sidecar_path, digest + "\n")
        except OSError:
            # manifest_path's create returned above without raising, so
            # this call is provably its creator (the create is O_EXCL) --
            # unlinking it here can never remove a pre-existing manifest,
            # only the one this call just made. Best-effort: a failure of
            # the unlink itself must still surface as the closed
            # ManifestWriteFailed below, never as a raw OSError.
            try:
                manifest_path.unlink()
            except OSError:
                pass
            raise

        _fsync_directory(run_directory)
        return digest
    except OSError:
        raise ManifestWriteFailed() from None


def _extent_from_payload(value: list | None) -> tuple[float, ...] | None:
    if value is None:
        return None
    return tuple(float(item) for item in value)


def _field_profile_from_payload(payload: dict) -> FieldProfile:
    return FieldProfile(
        name=payload["name"],
        ogr_type=payload["ogr_type"],
        width=payload["width"],
        precision=payload["precision"],
        nullable=payload["nullable"],
    )


def _layer_profile_from_payload(payload: dict) -> LayerProfile:
    fields_payload = payload["fields"]
    if not isinstance(fields_payload, list):
        raise TypeError("layer fields must be a list")
    return LayerProfile(
        dataset_relative_path=payload["dataset_relative_path"],
        dataset_stem=payload["dataset_stem"],
        layer_name=payload["layer_name"],
        driver=payload["driver"],
        spatial=payload["spatial"],
        geometry_type=payload["geometry_type"],
        geometry_column=payload["geometry_column"],
        fid_column=payload["fid_column"],
        feature_count=payload["feature_count"],
        source_wkt=payload["source_wkt"],
        epsg=payload["epsg"],
        extent=_extent_from_payload(payload["extent"]),
        fields=tuple(_field_profile_from_payload(field) for field in fields_payload),
    )


def _manifest_layer_from_payload(payload: dict) -> ManifestLayer:
    return ManifestLayer(
        profile=_layer_profile_from_payload(payload), target_table=payload["target_table"]
    )


def _companion_from_payload(payload: dict) -> CompanionFile:
    return CompanionFile(
        relative_path=payload["relative_path"],
        byte_count=payload["byte_count"],
        sha256=payload["sha256"],
    )


def read_manifest(run_directory: Path) -> ImportManifest:
    """Read ``manifest.json`` back, verifying its digest before trusting a field.

    The exact inverse of ``write_manifest``: recomputes the SHA-256 over the
    canonical bytes (one trailing newline stripped, same as the sidecar's own
    trailing newline) and compares it to the sidecar *before* the JSON is
    even parsed, so a tampered file is rejected on identity, never on shape
    (T-03-11). Every collection comes back as a ``tuple``, in the exact order
    the file lists it, so the returned object is as frozen as the one
    ``build_manifest`` produced and ``layers``/``companions`` load in D-42's
    file order. Neither closed failure below carries file text, JSON text, or
    a path -- mirrors ``discovery.read_field_schema``'s total-collapse
    pattern: a specific failure is never masked by the catch-all.
    """

    try:
        try:
            manifest_text = (run_directory / "manifest.json").read_text(encoding="utf-8")
            sidecar_text = (run_directory / "manifest.json.sha256").read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeError):
            raise ManifestUnreadable() from None

        canonical = manifest_text[:-1] if manifest_text.endswith("\n") else manifest_text
        actual_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        sidecar_digest = sidecar_text[:-1] if sidecar_text.endswith("\n") else sidecar_text

        if _SIDECAR_DIGEST.fullmatch(sidecar_digest) is None:
            raise ManifestDigestMismatch()
        if sidecar_digest != actual_digest:
            raise ManifestDigestMismatch()

        payload = json.loads(canonical)
        if not isinstance(payload, dict):
            raise TypeError("manifest payload must be an object")
        if payload["schema_version"] != MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported manifest schema_version")

        provenance = payload["provenance"]
        layers_payload = payload["layers"]
        companions_payload = payload["companions"]
        if not isinstance(layers_payload, list) or not isinstance(companions_payload, list):
            raise TypeError("layers and companions must be lists")

        return ImportManifest(
            schema_version=payload["schema_version"],
            order_id=provenance["order_id"],
            run_timestamp=provenance["run_timestamp"],
            run_directory=provenance["run_directory"],
            artifact_sha256=provenance["artifact_sha256"],
            artifact_byte_count=provenance["artifact_byte_count"],
            message_fingerprint=provenance["message_fingerprint"],
            layers=tuple(_manifest_layer_from_payload(layer) for layer in layers_payload),
            companions=tuple(
                _companion_from_payload(companion) for companion in companions_payload
            ),
        )
    except ManifestFailure:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise ManifestUnreadable() from None
