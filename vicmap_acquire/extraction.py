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
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


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
    (``ArtifactChecksumMismatch``), which also covers an absent artifact
    file -- a missing file cannot match a supplied digest either. Streams
    the artifact in 1 MiB chunks; never trusts that nothing touched
    ``artifacts/`` since Phase 1 ran. Never constructs ``zipfile.ZipFile``.
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
        raise ArtifactChecksumMismatch() from None

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


def _reject_unsafe_member(info: zipfile.ZipInfo, destination_root: Path) -> Path:
    """Validate one member fully, returning its resolved destination path.

    Runs before any output handle is opened for the member (reject-before-
    write, Pattern 1): absolute paths, ``..`` traversal, drive-letter roots,
    symlinks (only meaningful when ``create_system == 3``), non-regular
    members, encrypted members, and any resolved path escaping
    ``destination_root``. Duplicate-name detection (D-26's hardlink-style
    aliasing guard) is the caller's responsibility -- see
    ``_validate_members`` -- because it is a whole-archive property, not a
    single-member one.
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

    resolved = (destination_root / normalized).resolve()
    if resolved != destination_root and destination_root not in resolved.parents:
        raise ArchiveTraversalRejected()
    return resolved


def _validate_members(
    infolist: list[zipfile.ZipInfo], destination_root: Path, policy: ExtractionPolicy
) -> list[tuple[zipfile.ZipInfo, Path]]:
    """Validate the complete member list before any output handle is opened.

    Mirrors ``download.py``'s validate-before-connect ordering
    (``validate_https_target`` runs completely before ``session.get`` is
    ever called): this pass runs to completion -- the member-count ceiling,
    then every member's path/mode/encryption/aliasing guards -- and raises
    on the first violation, before the write phase in ``extract_artifact``
    ever begins. A valid member appearing before an invalid one is
    therefore never written to disk.

    D-26's hardlink-style aliasing guard is keyed on each member's
    *resolved destination*, not on the archive-supplied ``ZipInfo.filename``
    string: ``_reject_unsafe_member`` is called first to obtain that
    resolved ``Path``, then two keys derived from it are tested for a
    collision -- the resolved ``Path`` itself (catches redundant separators
    and ``.`` segments, e.g. ``d/f.txt`` vs ``d//f.txt`` or ``a/b`` vs
    ``a/./b``) and ``os.path.normcase(str(destination)).casefold()``
    (catches members whose names differ only by letter case, which alias on
    a case-insensitive filesystem such as the default APFS on the
    ``aarch64-darwin``/``x86_64-darwin`` targets ``flake.nix`` builds for).
    Whole-archive duplicate detection remains the caller's responsibility,
    as before.
    """

    if len(infolist) > policy.max_member_count:
        raise ArchiveCeilingExceeded()

    seen_destinations: set[Path] = set()
    seen_case_folded: set[str] = set()
    validated: list[tuple[zipfile.ZipInfo, Path]] = []
    for info in infolist:
        destination = _reject_unsafe_member(info, destination_root)
        case_folded = os.path.normcase(str(destination)).casefold()
        if destination in seen_destinations or case_folded in seen_case_folded:
            # Two members naming one destination -- whatever strings the
            # archive spelled their names with -- is D-26's hardlink-style
            # aliasing: the second occurrence could silently overwrite or
            # alias the first once written, so no destination may be
            # claimed twice.
            raise ArchiveUnsafeMemberRejected()
        seen_destinations.add(destination)
        seen_case_folded.add(case_folded)
        validated.append((info, destination))
    return validated


def extract_artifact(
    artifact_path: Path, *, order_id: str, run_timestamp: str, policy: ExtractionPolicy
) -> ExtractionResult:
    """Extract ``artifact_path`` into ``{run_root}/{order_id}/{run_timestamp}/``.

    Every member is validated against the complete guard list (Pattern 1)
    before any output handle is opened for it -- see ``_validate_members``.
    Streaming enforces per-member and cumulative byte ceilings against
    actual decompressed bytes, never just declared metadata (Pattern 2).
    ``os.rename`` from a private sibling ``.tmp-`` directory into the
    published run directory is the sole commit point, mirroring
    ``download.py``'s ``_publish_artifact``. A previously published run
    directory of the same name is never overwritten (PROHIB-06); a guard
    trip anywhere in this function leaves the ``.tmp-`` directory behind
    for inspection rather than deleting it (D-25).

    Wrapped exactly as ``download_artifact`` is wrapped: this function's own
    typed failures pass straight through, any other ``OSError`` (a local
    filesystem problem -- ``mkdir``, a short write, ``rename``) becomes
    ``RunDirectoryWriteFailed``, and any other unexpected exception (for
    example a ``zipfile.BadZipFile`` raised somewhere this function does not
    narrowly catch it itself, such as a corrupt central directory surfacing
    from ``infolist()``) becomes ``ArchiveUnreadable`` -- no raw ``zipfile``
    exception text ever reaches a caller.
    """

    if not isinstance(order_id, str) or _ORDER_ID.fullmatch(order_id) is None:
        raise ArchiveTraversalRejected()
    if not isinstance(run_timestamp, str) or not run_timestamp:
        raise ArchiveTraversalRejected()

    order_root = policy.run_root / order_id
    temp_dir = order_root / f".tmp-{run_timestamp}"
    final_dir = order_root / run_timestamp

    members: list[ExtractedMember] = []
    total_received = 0

    try:
        if final_dir.exists():
            raise RunDirectoryWriteFailed()

        order_root.mkdir(parents=True, exist_ok=True)
        if temp_dir.exists():
            raise RunDirectoryWriteFailed()
        temp_dir.mkdir(parents=True)
        temp_dir_resolved = temp_dir.resolve()

        try:
            zip_file = zipfile.ZipFile(artifact_path)
        except (OSError, zipfile.BadZipFile):
            raise ArchiveUnreadable() from None

        with zip_file:
            try:
                infolist = zip_file.infolist()
            except (OSError, zipfile.BadZipFile):
                raise ArchiveUnreadable() from None

            validated = _validate_members(infolist, temp_dir_resolved, policy)

            for info, destination in validated:
                relative = info.filename.replace("\\", "/")
                is_directory_entry = relative.endswith("/")

                if is_directory_entry:
                    destination.mkdir(parents=True, exist_ok=True)
                    # D-27: every member is accounted for, including
                    # directory entries -- they carry no bytes of their own.
                    members.append(
                        ExtractedMember(
                            relative_path=relative,
                            byte_count=0,
                            sha256=_EMPTY_SHA256,
                        )
                    )
                    continue

                destination.parent.mkdir(parents=True, exist_ok=True)

                member_received = 0
                digest = hashlib.sha256()
                # Exclusive create (mirrors manifest.py's
                # _write_new_file_fsync idiom): the filesystem is the last
                # oracle on "is this destination already claimed?" -- an
                # alias the pre-pass guard somehow missed fails its own
                # create here instead of silently truncating an already-
                # written, already-hashed file. FileExistsError is an
                # OSError, so it maps to RunDirectoryWriteFailed below with
                # no raw text reaching a caller.
                descriptor = os.open(
                    destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
                )
                # WR-03: os.fdopen(descriptor, ...) must be entered *before*
                # zip_file.open(info, "r") in this compound ``with``. Python
                # constructs/enters context managers left-to-right; if the
                # raw descriptor's wrapper were entered second and
                # zip_file.open() raised first (a corrupt/adversarial member
                # header), the descriptor from os.open() above would never
                # be handed to anything that closes it -- it would leak for
                # the remaining life of the process. Entering os.fdopen()
                # first means the ``with`` statement's own partial-entry
                # cleanup closes it if the sibling construction then fails.
                with os.fdopen(descriptor, "wb") as target, zip_file.open(
                    info, "r"
                ) as source:
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
                        written = target.write(chunk)
                        if written != len(chunk):
                            raise RunDirectoryWriteFailed()
                        digest.update(chunk)
                    target.flush()
                    os.fsync(target.fileno())

                if (
                    info.compress_size
                    and member_received / info.compress_size > policy.max_compression_ratio
                ):
                    raise ArchiveCeilingExceeded()

                members.append(
                    ExtractedMember(
                        relative_path=relative,
                        byte_count=member_received,
                        sha256=digest.hexdigest(),
                    )
                )

        if final_dir.exists():
            raise RunDirectoryWriteFailed()
        os.rename(temp_dir, final_dir)
        _fsync_directory(final_dir.parent)
    except ArchiveFailure:
        raise
    except OSError:
        raise RunDirectoryWriteFailed() from None
    except Exception:
        raise ArchiveUnreadable() from None
    finally:
        # D-25: a guard trip leaves the private .tmp-{run_timestamp}
        # directory on disk for inspection -- never delete it here. Every
        # other resource this function opens (the zip archive, each output
        # file) is already scoped to a ``with`` block above and closes
        # itself; this clause exists only to make that guarantee explicit
        # and to mirror download_artifact's wrap-with-finally shape. It can
        # never re-decide an outcome this function already committed to,
        # because os.rename above is the sole commit point and nothing
        # after it can raise (_fsync_directory swallows its own OSErrors).
        pass

    members.sort(key=lambda member: member.relative_path)
    return ExtractionResult(
        run_directory=final_dir,
        order_id=order_id,
        run_timestamp=run_timestamp,
        members=tuple(members),
        total_byte_count=total_received,
    )
