"""Fail-closed archive extraction with atomic run-directory publication.

Mirrors ``download.py``'s shape: a typed closed exception hierarchy, a frozen
``__post_init__``-validated policy dataclass, a streamed chunked loop
enforcing byte ceilings against actual bytes produced (not declared
metadata), and one atomic filesystem operation as the sole commit point.

D-25/D-26: a guard trip during extraction leaves the private ``.tmp-``
directory behind for inspection -- nothing is auto-deleted. Only
``verify_artifact``'s pre-extraction checksum failure touches no directory
at all, because it runs before any run directory is even created.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path


_HEX_64 = re.compile(r"[0-9a-f]{64}")
_ORDER_ID = re.compile(r"[A-Za-z0-9]+")


class ArchiveFailure(RuntimeError):
    """A closed extraction failure carrying no archive-controlled text."""

    code = "archive_unreadable"

    def __init__(self) -> None:
        super().__init__(self.code)


class ArtifactChecksumMismatch(ArchiveFailure):
    code = "artifact_checksum_mismatch"


class ProvenanceUnavailable(ArchiveFailure):
    code = "provenance_unavailable"


class ArchiveTraversalRejected(ArchiveFailure):
    code = "archive_traversal_rejected"


class ArchiveUnsafeMemberRejected(ArchiveFailure):
    code = "archive_unsafe_member_rejected"


class ArchiveCeilingExceeded(ArchiveFailure):
    code = "archive_ceiling_exceeded"


class ArchiveUnreadable(ArchiveFailure):
    code = "archive_unreadable"


class RunDirectoryWriteFailed(ArchiveFailure):
    code = "run_directory_write_failed"


def _positive_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("extraction policy values must be positive integers")
    return value


@dataclass(frozen=True)
class ExtractionPolicy:
    """Complete non-secret policy for one archive extraction (D-25/D-26)."""

    run_root: Path
    max_total_bytes: int
    max_member_bytes: int
    max_member_count: int
    max_compression_ratio: int

    def __post_init__(self) -> None:
        if not isinstance(self.run_root, Path):
            raise ValueError("run_root must be a Path")
        if not self.run_root.is_absolute():
            raise ValueError("run_root must be an absolute Path")

        for value in (
            self.max_total_bytes,
            self.max_member_bytes,
            self.max_member_count,
            self.max_compression_ratio,
        ):
            _positive_integer(value)
        if self.max_member_bytes > self.max_total_bytes:
            raise ValueError("max_member_bytes cannot exceed max_total_bytes")


@dataclass(frozen=True)
class ExtractedMember:
    relative_path: str
    byte_count: int
    sha256: str


@dataclass(frozen=True)
class ExtractionResult:
    run_directory: Path
    order_id: str
    run_timestamp: str
    members: tuple[ExtractedMember, ...]
    total_byte_count: int


def verify_artifact(
    artifact_path: Path, *, expected_sha256: str, expected_byte_count: int
) -> None:
    """Re-verify an existing artifact's SHA-256 and byte count (D-28).

    ``expected_sha256``/``expected_byte_count`` are required input -- Phase
    1's reported provenance. A missing or malformed expected value is a
    distinct closed failure (``ProvenanceUnavailable``) from a well-formed
    expected value the artifact simply fails to match
    (``ArtifactChecksumMismatch``). Streams the artifact in 1 MiB chunks;
    never trusts that nothing touched ``artifacts/`` since Phase 1 ran.
    """

    if (
        not isinstance(expected_sha256, str)
        or _HEX_64.fullmatch(expected_sha256) is None
        or isinstance(expected_byte_count, bool)
        or not isinstance(expected_byte_count, int)
        or expected_byte_count < 0
    ):
        raise ProvenanceUnavailable()

    try:
        digest = hashlib.sha256()
        byte_count = 0
        with open(artifact_path, "rb") as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                byte_count += len(chunk)
    except OSError:
        raise ArchiveUnreadable() from None

    if byte_count != expected_byte_count or digest.hexdigest() != expected_sha256:
        raise ArtifactChecksumMismatch()


def _fsync_directory(directory: Path) -> None:
    """Fsync a directory entry so a completed publish is durably recorded.

    Mirrors ``download.py``'s ``_fsync_directory`` exactly: any ``OSError``
    from opening, syncing, or closing the directory descriptor is swallowed,
    because the publish itself has already committed and this call only
    strengthens durability, never correctness.
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


def _reject_unsafe_member(info: zipfile.ZipInfo, run_dir_resolved: Path) -> Path:
    """Validate one member fully, returning its resolved destination path.

    Runs before any output handle is opened for the member (reject-before-
    write, Pattern 1): absolute paths, ``..`` traversal, drive-letter roots,
    symlinks/hardlinks (only meaningful when ``create_system == 3``),
    non-regular members, encrypted members, and any resolved path escaping
    ``run_dir_resolved``.
    """

    name = info.filename
    if not isinstance(name, str) or not name:
        raise ArchiveTraversalRejected()
    if name.startswith("/") or name.startswith("\\"):
        raise ArchiveTraversalRejected()

    normalized = name.replace("\\", "/")
    parts = normalized.split("/")
    if any(part == ".." for part in parts) or any(":" in part for part in parts):
        raise ArchiveTraversalRejected()

    if info.create_system == 3:
        unix_mode = (info.external_attr >> 16) & 0o170000
        if unix_mode == stat.S_IFLNK:
            raise ArchiveUnsafeMemberRejected()
        if unix_mode not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise ArchiveUnsafeMemberRejected()

    if info.flag_bits & 0x1:
        raise ArchiveUnsafeMemberRejected()

    resolved = (run_dir_resolved / normalized).resolve()
    if resolved != run_dir_resolved and run_dir_resolved not in resolved.parents:
        raise ArchiveTraversalRejected()
    return resolved


def extract_artifact(
    artifact_path: Path, *, order_id: str, run_timestamp: str, policy: ExtractionPolicy
) -> ExtractionResult:
    """Extract ``artifact_path`` into ``{run_root}/{order_id}/{run_timestamp}/``.

    Every member is validated against the complete guard list (Pattern 1)
    before any output handle is opened for it. Streaming enforces
    per-member and cumulative byte ceilings against actual decompressed
    bytes, never just declared metadata (Pattern 2). ``os.rename`` from a
    private sibling ``.tmp-`` directory into the published run directory is
    the sole commit point, mirroring ``download.py``'s ``_publish_artifact``.
    A previously published run directory of the same name is never
    overwritten (PROHIB-06); a guard trip anywhere in this function leaves
    the ``.tmp-`` directory behind for inspection rather than deleting it.
    """

    if not isinstance(order_id, str) or _ORDER_ID.fullmatch(order_id) is None:
        raise ArchiveTraversalRejected()
    if not isinstance(run_timestamp, str) or not run_timestamp:
        raise ArchiveTraversalRejected()

    order_root = policy.run_root / order_id
    temp_dir = order_root / f".tmp-{run_timestamp}"
    final_dir = order_root / run_timestamp

    if final_dir.exists():
        raise RunDirectoryWriteFailed()

    try:
        order_root.mkdir(parents=True, exist_ok=True)
        if temp_dir.exists():
            raise RunDirectoryWriteFailed()
        temp_dir.mkdir(parents=True)
    except OSError:
        raise RunDirectoryWriteFailed() from None

    temp_dir_resolved = temp_dir.resolve()
    members: list[ExtractedMember] = []
    total_received = 0

    try:
        try:
            zip_file = zipfile.ZipFile(artifact_path)
        except (OSError, zipfile.BadZipFile):
            raise ArchiveUnreadable() from None

        with zip_file:
            infolist = zip_file.infolist()
            if len(infolist) > policy.max_member_count:
                raise ArchiveCeilingExceeded()

            validated: list[tuple[zipfile.ZipInfo, Path]] = [
                (info, _reject_unsafe_member(info, temp_dir_resolved))
                for info in infolist
            ]

            for info, destination in validated:
                is_directory_entry = info.filename.replace("\\", "/").endswith("/")
                if is_directory_entry:
                    try:
                        destination.mkdir(parents=True, exist_ok=True)
                    except OSError:
                        raise RunDirectoryWriteFailed() from None
                    continue

                try:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                except OSError:
                    raise RunDirectoryWriteFailed() from None

                member_received = 0
                digest = hashlib.sha256()
                try:
                    with zip_file.open(info, "r") as source, open(
                        destination, "wb"
                    ) as target:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            member_received += len(chunk)
                            if member_received > policy.max_member_bytes:
                                raise ArchiveCeilingExceeded()
                            total_received += len(chunk)
                            if total_received > policy.max_total_bytes:
                                raise ArchiveCeilingExceeded()
                            target.write(chunk)
                            digest.update(chunk)
                except ArchiveFailure:
                    raise
                except (OSError, zipfile.BadZipFile):
                    raise ArchiveUnreadable() from None

                if (
                    info.compress_size
                    and member_received / info.compress_size > policy.max_compression_ratio
                ):
                    raise ArchiveCeilingExceeded()

                relative = destination.relative_to(temp_dir_resolved).as_posix()
                members.append(
                    ExtractedMember(
                        relative_path=relative,
                        byte_count=member_received,
                        sha256=digest.hexdigest(),
                    )
                )
    except ArchiveFailure:
        raise
    except OSError:
        raise ArchiveUnreadable() from None

    try:
        os.rename(temp_dir, final_dir)
        _fsync_directory(final_dir.parent)
    except OSError:
        raise RunDirectoryWriteFailed() from None

    return ExtractionResult(
        run_directory=final_dir,
        order_id=order_id,
        run_timestamp=run_timestamp,
        members=tuple(members),
        total_byte_count=total_received,
    )
