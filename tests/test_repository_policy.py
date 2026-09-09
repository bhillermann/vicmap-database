"""Regressions proving every policy-permitted output root is git-ignored.

These tests exercise the WR-05 ignore-coverage requirement directly against
the real ``.gitignore`` via ``git check-ignore`` -- not by reading the ignore
file's patterns -- so a change to ``.gitignore`` that stops covering a
permitted output root fails this test immediately. Nothing here skips: if
git is unavailable, ``subprocess.run`` raises and the test errors rather than
silently passing.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _check_ignore(relative_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "check-ignore", "-q", "--", str(relative_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


class RepositoryIgnoreCoverageTest(unittest.TestCase):
    def _assert_ignored(self, relative_path: Path, description: str) -> None:
        result = _check_ignore(relative_path)
        self.assertEqual(
            0,
            result.returncode,
            f"{description} must be git-ignored; stderr={result.stderr!r}",
        )

    def test_root_level_output_root_is_ignored(self):
        output_root = REPO_ROOT / "artifacts"
        created = not output_root.exists()
        output_root.mkdir(exist_ok=True)
        try:
            artifact = output_root / f"probe-{uuid.uuid4().hex}.zip"
            artifact.write_bytes(b"probe")
            try:
                self._assert_ignored(
                    artifact.relative_to(REPO_ROOT),
                    "a finalized artifact under the root-level permitted output directory",
                )
            finally:
                artifact.unlink()
        finally:
            if created:
                shutil.rmtree(output_root)

    def test_nested_output_root_is_ignored(self):
        output_root = REPO_ROOT / f"nested-probe-{uuid.uuid4().hex}" / "artifacts"
        output_root.mkdir(parents=True)
        try:
            artifact = output_root / "Order_OK0VUZ.zip"
            artifact.write_bytes(b"probe")
            self._assert_ignored(
                artifact.relative_to(REPO_ROOT),
                "a finalized artifact under a nested permitted output directory",
            )
        finally:
            shutil.rmtree(output_root.parent)

    def test_private_partial_download_is_ignored(self):
        output_root = REPO_ROOT / f"partial-probe-{uuid.uuid4().hex}" / "artifacts"
        output_root.mkdir(parents=True)
        try:
            partial = output_root / ".vicmap-download-abc123.part"
            partial.write_bytes(b"probe")
            self._assert_ignored(
                partial.relative_to(REPO_ROOT),
                "a private partial download file",
            )
        finally:
            shutil.rmtree(output_root.parent)


if __name__ == "__main__":
    unittest.main()
