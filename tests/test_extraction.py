"""GEO-01 adversarial archive-extraction regressions.

Every fixture is a synthetic in-memory zip built with explicit
``zipfile.ZipInfo`` objects (``_member``/``_build_archive``) so
``create_system`` and ``external_attr`` are set deliberately rather than
inherited from the test-running platform -- mirroring
``tests/test_download.py``'s fake-transport fixture-builder style for the
archive boundary instead of the HTTP boundary. The one member attribute
that cannot be set this way is ``flag_bits``: ``ZipFile.writestr``
recomputes it unconditionally at write time, so an encrypted-member
fixture patches the raw archive bytes directly after the fact --
see ``_patch_general_purpose_flag_bit``.

Constructing a member whose *declared* ``file_size`` is smaller than what
it actually decompresses to, and proving our code still measures the
per-member ceiling against real streamed bytes, was investigated directly
against CPython 3.14's ``zipfile`` module this session and found to be
unconstructable through the public ``ZipFile.open()``/``.read()`` API:
``ZipExtFile._read1`` unconditionally truncates decompressed output to
``zinfo.file_size`` (``data = data[:self._left]``), so the total bytes a
caller can ever receive for one member is capped at the declared value no
matter how the underlying compressed stream or CRC-32 is crafted. The
tests below instead prove the equivalent, constructible property: a
member whose *on-disk compressed footprint* is tiny but whose real,
accurately-declared decompressed size is large still trips the byte
ceiling from the bytes actually streamed, never from a metadata
short-circuit -- see ``CeilingEnforcementTest``.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import stat
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from vicmap_acquire import extraction


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ARCHIVE = REPO_ROOT / "tests" / "fixtures" / "Order_TRACER1.zip"

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _member(
    name: str,
    data: bytes = b"payload",
    *,
    create_system: int = 3,
    external_attr: int | None = None,
    compress_type: int = zipfile.ZIP_DEFLATED,
) -> tuple[zipfile.ZipInfo, bytes]:
    """Build one ``(ZipInfo, bytes)`` pair with explicit, deliberate metadata.

    ``flag_bits`` is deliberately not a parameter here: ``ZipFile.writestr``
    unconditionally recomputes it at write time (verified this session), so
    an encrypted-member fixture must patch the raw archive bytes directly
    -- see ``_patch_general_purpose_flag_bit``.
    """

    info = zipfile.ZipInfo(name)
    info.create_system = create_system
    info.compress_type = compress_type
    if external_attr is not None:
        info.external_attr = external_attr
    elif create_system == 3:
        mode = stat.S_IFDIR | 0o755 if name.endswith("/") else stat.S_IFREG | 0o644
        info.external_attr = mode << 16
    return info, data


def _build_archive(members: list[tuple[zipfile.ZipInfo, bytes]]) -> bytes:
    """Assemble an in-memory zip archive from explicit ``(ZipInfo, bytes)`` pairs."""

    buffer = io.BytesIO()
    with warnings.catch_warnings():
        # A deliberate duplicate-name fixture triggers zipfile's own
        # "Duplicate name" UserWarning at write time -- that is exactly the
        # adversarial shape being constructed, not a real problem.
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(buffer, "w") as archive:
            for info, data in members:
                archive.writestr(info, data)
    return buffer.getvalue()


def _patch_general_purpose_flag_bit(raw: bytes, bit: int) -> bytes:
    """Set a general-purpose flag bit directly in an archive's raw bytes.

    Verified this session: ``zipfile.ZipFile.writestr()`` and
    ``ZipFile.open(info, "w")`` both unconditionally recompute
    ``flag_bits`` at write time, discarding whatever a test pre-sets on the
    ``ZipInfo`` -- so an "encrypted member" fixture cannot be built through
    any public writer call. Patching the on-disk general-purpose flag field
    directly (local file header offset 6, central directory record offset
    8, both two bytes) is the only way to construct one, and it is exactly
    the bit pattern a genuinely encrypted archive's bytes would carry.
    Assumes exactly one member, as every fixture using this helper does.
    """

    data = bytearray(raw)
    local_offset = data.find(b"PK\x03\x04")
    central_offset = data.find(b"PK\x01\x02")
    assert local_offset != -1 and central_offset != -1
    for header_offset, flag_field_offset in ((local_offset, 6), (central_offset, 8)):
        position = header_offset + flag_field_offset
        value = int.from_bytes(data[position : position + 2], "little")
        value |= bit
        data[position : position + 2] = value.to_bytes(2, "little")
    return bytes(data)


class ExtractionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.run_root = Path(tempfile.mkdtemp(prefix="vicmap-extraction-runs-"))
        self.addCleanup(shutil.rmtree, self.run_root, ignore_errors=True)
        self.artifact_dir = Path(tempfile.mkdtemp(prefix="vicmap-extraction-artifacts-"))
        self.addCleanup(shutil.rmtree, self.artifact_dir, ignore_errors=True)

    def _policy(self, **overrides) -> extraction.ExtractionPolicy:
        defaults = dict(
            run_root=self.run_root,
            max_total_bytes=10_000_000,
            max_member_bytes=5_000_000,
            max_member_count=100,
            max_compression_ratio=2_000,
        )
        defaults.update(overrides)
        return extraction.ExtractionPolicy(**defaults)

    def _write_archive(
        self, members: list[tuple[zipfile.ZipInfo, bytes]], name: str = "artifact.zip"
    ) -> Path:
        path = self.artifact_dir / name
        path.write_bytes(_build_archive(members))
        return path

    def _extract(
        self,
        artifact_path: Path,
        *,
        order_id: str = "ORD1",
        run_timestamp: str = "20260101T000000Z",
        policy: extraction.ExtractionPolicy | None = None,
    ) -> extraction.ExtractionResult:
        return extraction.extract_artifact(
            artifact_path,
            order_id=order_id,
            run_timestamp=run_timestamp,
            policy=policy or self._policy(),
        )

    def _written_files(self, order_id: str = "ORD1") -> list[Path]:
        order_root = self.run_root / order_id
        if not order_root.exists():
            return []
        return [path for path in order_root.rglob("*") if path.is_file()]

    def _assert_nothing_written(self, order_id: str = "ORD1") -> None:
        self.assertEqual(self._written_files(order_id), [])
        final_dir = self.run_root / order_id / "20260101T000000Z"
        self.assertFalse(final_dir.exists())

    def _assert_run_not_published(self, order_id: str = "ORD1") -> None:
        """D-25: a guard trip anywhere leaves ``.tmp-`` behind, never publishes.

        Unlike ``_assert_nothing_written`` (for validation-phase rejections,
        which happen before any output handle opens), a streaming-phase
        ceiling trip can leave a partially written file in the ``.tmp-``
        directory on purpose -- this only asserts the one guarantee that
        always holds: the final run directory never appears.
        """

        final_dir = self.run_root / order_id / "20260101T000000Z"
        temp_dir = self.run_root / order_id / ".tmp-20260101T000000Z"
        self.assertFalse(final_dir.exists())
        self.assertTrue(temp_dir.exists())


class MemberGuardRejectionTest(ExtractionTestCase):
    """Every D-26 reject-before-write guard, each with its own regression."""

    def test_leading_slash_member_rejected(self):
        archive = self._write_archive([_member("/etc/passwd")])
        with self.assertRaises(extraction.ArchiveTraversalRejected):
            self._extract(archive)
        self._assert_nothing_written()

    def test_leading_backslash_member_rejected(self):
        archive = self._write_archive([_member("\\evil.txt")])
        with self.assertRaises(extraction.ArchiveTraversalRejected):
            self._extract(archive)
        self._assert_nothing_written()

    def test_dot_dot_component_rejected(self):
        archive = self._write_archive([_member("../evil.txt")])
        with self.assertRaises(extraction.ArchiveTraversalRejected):
            self._extract(archive)
        self._assert_nothing_written()

    def test_deep_escape_resolves_outside_root_rejected(self):
        archive = self._write_archive(
            [_member("a/b/c/../../../../../../etc/passwd")]
        )
        with self.assertRaises(extraction.ArchiveTraversalRejected):
            self._extract(archive)
        self._assert_nothing_written()

    def test_backslash_separated_traversal_rejected_after_normalization(self):
        archive = self._write_archive([_member("sub\\..\\..\\evil.txt")])
        with self.assertRaises(extraction.ArchiveTraversalRejected):
            self._extract(archive)
        self._assert_nothing_written()

    def test_colon_bearing_component_rejected(self):
        archive = self._write_archive([_member("sub/C:evil.txt")])
        with self.assertRaises(extraction.ArchiveTraversalRejected):
            self._extract(archive)
        self._assert_nothing_written()

    def test_unix_symlink_member_rejected(self):
        archive = self._write_archive(
            [
                _member(
                    "link.txt",
                    b"target",
                    create_system=3,
                    external_attr=(stat.S_IFLNK | 0o777) << 16,
                )
            ]
        )
        with self.assertRaises(extraction.ArchiveUnsafeMemberRejected):
            self._extract(archive)
        self._assert_nothing_written()

    def test_unix_non_regular_member_rejected(self):
        archive = self._write_archive(
            [
                _member(
                    "device",
                    b"",
                    create_system=3,
                    external_attr=(stat.S_IFIFO | 0o644) << 16,
                )
            ]
        )
        with self.assertRaises(extraction.ArchiveUnsafeMemberRejected):
            self._extract(archive)
        self._assert_nothing_written()

    def test_duplicate_member_name_rejected(self):
        archive = self._write_archive(
            [_member("dup.txt", b"one"), _member("dup.txt", b"two")]
        )
        with self.assertRaises(extraction.ArchiveUnsafeMemberRejected):
            self._extract(archive)
        self._assert_nothing_written()

    def test_encrypted_member_rejected(self):
        raw = _patch_general_purpose_flag_bit(
            _build_archive([_member("secret.txt")]), 0x1
        )
        path = self.artifact_dir / "artifact.zip"
        path.write_bytes(raw)
        with self.assertRaises(extraction.ArchiveUnsafeMemberRejected):
            self._extract(path)
        self._assert_nothing_written()

    def test_member_count_ceiling_rejected_before_any_write(self):
        members = [_member(f"file{i}.txt") for i in range(3)]
        archive = self._write_archive(members)
        with self.assertRaises(extraction.ArchiveCeilingExceeded):
            self._extract(archive, policy=self._policy(max_member_count=2))
        self._assert_nothing_written()

    def test_archive_unreadable_for_non_zip_input_carries_no_library_text(self):
        path = self.artifact_dir / "not-a-zip.zip"
        path.write_bytes(b"this is not a zip file, just noise" * 4)
        with self.assertRaises(extraction.ArchiveUnreadable) as caught:
            self._extract(path)
        message = str(caught.exception)
        self.assertNotIn("zip", message.lower())
        self.assertNotIn("File is not a zip", message)

    def test_archive_unreadable_for_truncated_zip_carries_no_library_text(self):
        whole = _build_archive([_member("safe.txt", b"hello world" * 100)])
        path = self.artifact_dir / "truncated.zip"
        path.write_bytes(whole[: len(whole) // 2])
        with self.assertRaises(extraction.ArchiveUnreadable) as caught:
            self._extract(path)
        message = str(caught.exception)
        self.assertNotIn("zip", message.lower())

    def test_valid_member_followed_by_traversal_member_leaves_valid_unwritten(self):
        archive = self._write_archive(
            [_member("safe.txt", b"hello"), _member("../evil.txt")]
        )
        with self.assertRaises(extraction.ArchiveTraversalRejected):
            self._extract(archive)
        self._assert_nothing_written()

    def test_extractall_and_extract_are_never_called(self):
        archive = self._write_archive([_member("safe.txt", b"hello world")])
        with patch.object(
            zipfile.ZipFile, "extractall", side_effect=AssertionError("must not be called")
        ), patch.object(
            zipfile.ZipFile, "extract", side_effect=AssertionError("must not be called")
        ):
            result = self._extract(archive)
        self.assertEqual(len(result.members), 1)
        self.assertEqual(result.members[0].relative_path, "safe.txt")


class MemberAcceptanceTest(ExtractionTestCase):
    def test_non_unix_create_system_with_symlink_bit_pattern_is_accepted_on_path(self):
        # create_system=0 (MS-DOS/FAT) -- the same external_attr bit
        # pattern that means "symlink" under create_system=3 carries no
        # Unix mode meaning here, so this member is judged purely on its
        # (safe) path, proving the mode-bit gate is scoped to create_system
        # == 3 and does not misfire on a Windows-authored archive.
        archive = self._write_archive(
            [
                _member(
                    "ordinary.txt",
                    b"content",
                    create_system=0,
                    external_attr=(stat.S_IFLNK | 0o777) << 16,
                )
            ]
        )
        result = self._extract(archive)
        self.assertEqual(len(result.members), 1)
        self.assertEqual(result.members[0].relative_path, "ordinary.txt")
        self.assertEqual(result.members[0].byte_count, len(b"content"))

    def test_valid_archive_extracts_with_correct_hashes_and_sizes(self):
        archive = self._write_archive(
            [_member("a.txt", b"aaaa"), _member("b.txt", b"bbbbbb")]
        )
        result = self._extract(archive)
        by_name = {member.relative_path: member for member in result.members}
        self.assertEqual(set(by_name), {"a.txt", "b.txt"})
        self.assertEqual(by_name["a.txt"].byte_count, 4)
        self.assertEqual(by_name["a.txt"].sha256, hashlib.sha256(b"aaaa").hexdigest())
        self.assertEqual(by_name["b.txt"].byte_count, 6)
        self.assertEqual(by_name["b.txt"].sha256, hashlib.sha256(b"bbbbbb").hexdigest())
        self.assertEqual(result.total_byte_count, 10)
        self.assertTrue(result.run_directory.exists())
        self.assertEqual((result.run_directory / "a.txt").read_bytes(), b"aaaa")

    def test_members_are_sorted_by_relative_path(self):
        archive = self._write_archive(
            [_member("z.txt", b"z"), _member("a.txt", b"a"), _member("m.txt", b"m")]
        )
        result = self._extract(archive)
        self.assertEqual(
            [member.relative_path for member in result.members],
            ["a.txt", "m.txt", "z.txt"],
        )

    def test_directory_entries_are_recorded_as_zero_byte_members(self):
        archive = self._write_archive(
            [_member("subdir/", b""), _member("subdir/file.txt", b"hi")]
        )
        result = self._extract(archive)
        by_name = {member.relative_path: member for member in result.members}
        self.assertEqual(set(by_name), {"subdir/", "subdir/file.txt"})
        self.assertEqual(by_name["subdir/"].byte_count, 0)
        self.assertEqual(by_name["subdir/"].sha256, _EMPTY_SHA256)
        self.assertTrue((result.run_directory / "subdir").is_dir())


class CeilingEnforcementTest(ExtractionTestCase):
    def test_per_member_ceiling_trips_on_real_streamed_bytes(self):
        # 100,000 real, accurately-declared bytes that compress to ~115 on
        # disk -- proving the ceiling is decided on what actually streams
        # out of the decompressor, not a metadata shortcut against
        # ZipInfo.file_size or compress_size.
        archive = self._write_archive([_member("big.bin", b"A" * 100_000)])
        policy = self._policy(
            max_member_bytes=1_000, max_total_bytes=1_000_000, max_compression_ratio=2_000
        )
        with self.assertRaises(extraction.ArchiveCeilingExceeded):
            self._extract(archive, policy=policy)
        self._assert_run_not_published()

    def test_two_members_individually_pass_but_combined_exceed_total_ceiling(self):
        archive = self._write_archive(
            [
                _member("first.bin", b"X" * 600, compress_type=zipfile.ZIP_STORED),
                _member("second.bin", b"Y" * 600, compress_type=zipfile.ZIP_STORED),
            ]
        )
        policy = self._policy(max_member_bytes=800, max_total_bytes=1_000)
        with self.assertRaises(extraction.ArchiveCeilingExceeded):
            self._extract(archive, policy=policy)
        self._assert_run_not_published()

    def test_compression_ratio_ceiling_trips_after_member_fully_streamed(self):
        archive = self._write_archive([_member("bomb.bin", b"A" * 100_000)])
        policy = self._policy(
            max_member_bytes=1_000_000,
            max_total_bytes=1_000_000,
            max_compression_ratio=100,
        )
        with self.assertRaises(extraction.ArchiveCeilingExceeded):
            self._extract(archive, policy=policy)
        self._assert_run_not_published()

    def test_zero_compress_size_member_extracts_without_dividing_by_zero(self):
        archive = self._write_archive(
            [_member("empty.bin", b"", compress_type=zipfile.ZIP_STORED)]
        )
        result = self._extract(archive, policy=self._policy(max_compression_ratio=1))
        self.assertEqual(len(result.members), 1)
        self.assertEqual(result.members[0].byte_count, 0)


class PublicationTest(ExtractionTestCase):
    def test_existing_final_directory_is_never_overwritten(self):
        order_root = self.run_root / "ORD1"
        final_dir = order_root / "20260101T000000Z"
        final_dir.mkdir(parents=True)
        marker = final_dir / "already-here.txt"
        marker.write_bytes(b"pre-existing content")

        archive = self._write_archive([_member("new.txt", b"new content")])
        with self.assertRaises(extraction.RunDirectoryWriteFailed):
            self._extract(archive)

        self.assertTrue(marker.exists())
        self.assertEqual(marker.read_bytes(), b"pre-existing content")
        self.assertEqual(list(final_dir.iterdir()), [marker])


class VerifyArtifactTest(ExtractionTestCase):
    def _artifact(self, data: bytes = b"payload bytes") -> tuple[Path, str, int]:
        path = self.artifact_dir / "artifact.zip"
        path.write_bytes(data)
        return path, hashlib.sha256(data).hexdigest(), len(data)

    def test_digest_mismatch_raises_checksum_mismatch(self):
        path, digest, byte_count = self._artifact()
        flipped = "0" * 63 + ("1" if digest[-1] != "1" else "2")
        with patch("vicmap_acquire.extraction.zipfile.ZipFile") as zip_ctor:
            with self.assertRaises(extraction.ArtifactChecksumMismatch):
                extraction.verify_artifact(
                    path, expected_sha256=flipped, expected_byte_count=byte_count
                )
            zip_ctor.assert_not_called()

    def test_correct_digest_wrong_byte_count_raises_checksum_mismatch(self):
        path, digest, byte_count = self._artifact()
        with patch("vicmap_acquire.extraction.zipfile.ZipFile") as zip_ctor:
            with self.assertRaises(extraction.ArtifactChecksumMismatch):
                extraction.verify_artifact(
                    path, expected_sha256=digest, expected_byte_count=byte_count + 1
                )
            zip_ctor.assert_not_called()

    def test_absent_artifact_file_raises_checksum_mismatch(self):
        missing_path = self.artifact_dir / "does-not-exist.zip"
        with patch("vicmap_acquire.extraction.zipfile.ZipFile") as zip_ctor:
            with self.assertRaises(extraction.ArtifactChecksumMismatch):
                extraction.verify_artifact(
                    missing_path,
                    expected_sha256="0" * 64,
                    expected_byte_count=1,
                )
            zip_ctor.assert_not_called()

    def test_flipped_byte_raises_checksum_mismatch(self):
        path, digest, byte_count = self._artifact(b"original bytes here")
        path.write_bytes(b"0riginal bytes here")
        with patch("vicmap_acquire.extraction.zipfile.ZipFile") as zip_ctor:
            with self.assertRaises(extraction.ArtifactChecksumMismatch):
                extraction.verify_artifact(
                    path, expected_sha256=digest, expected_byte_count=byte_count
                )
            zip_ctor.assert_not_called()


class RealFixtureAccountingTest(ExtractionTestCase):
    def test_every_member_of_the_real_delivery_is_accounted_for(self):
        with zipfile.ZipFile(FIXTURE_ARCHIVE) as reference:
            expected_count = len(reference.infolist())

        result = self._extract(FIXTURE_ARCHIVE, run_timestamp="20260914T000000Z")

        self.assertEqual(len(result.members), expected_count)
        self.assertEqual(
            result.total_byte_count, sum(member.byte_count for member in result.members)
        )
        names = {member.relative_path for member in result.members}
        self.assertIn("Creative Commons Licence.html", names)
        self.assertIn(
            "VICMAP_ADDRESS_b9e9146d-8378-5c37-b6cd-63e3a8d05d02.pdf", names
        )


if __name__ == "__main__":
    unittest.main()
