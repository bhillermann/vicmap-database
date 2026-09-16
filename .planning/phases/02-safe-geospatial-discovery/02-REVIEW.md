---
phase: 02-safe-geospatial-discovery
reviewed: 2026-09-16T10:57:58Z
depth: standard
files_reviewed: 23
files_reviewed_list:
  - discover_order.py
  - flake.nix
  - .gitignore
  - read_mailbox.py
  - vicmap.toml
  - vicmap_acquire/discovery.py
  - vicmap_acquire/download.py
  - vicmap_acquire/evidence.py
  - vicmap_acquire/extraction.py
  - vicmap_acquire/manifest.py
  - vicmap_acquire/naming.py
  - tests/fixtures/build_fixtures.py
  - tests/test_discovery.py
  - tests/test_discovery_config.py
  - tests/test_discovery_differential.py
  - tests/test_discovery_tracer.py
  - tests/test_download.py
  - tests/test_evidence.py
  - tests/test_extraction.py
  - tests/test_graph.py
  - tests/test_manifest.py
  - tests/test_naming.py
  - tests/test_provenance.py
  - tests/test_repository_policy.py
findings:
  critical: 2
  warning: 2
  info: 1
  total: 5
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-09-16T10:57:58Z
**Depth:** standard
**Files Reviewed:** 23
**Status:** issues_found

## Summary

This phase's implementation is unusually disciplined for a fail-closed archive/discovery pipeline: guard ordering is validate-before-write throughout, closed typed-exception hierarchies never leak driver/subprocess text, evidence redaction is enforced structurally (regex-checked scalars, `_EmitOnce` sink isolation), and the test suite includes a genuinely independent `ogrinfo`-based differential oracle for discovery (`tests/test_discovery_differential.py`) that avoids sharing the implementation's own parsing blind spot.

Two BLOCKER-level defects were found, both squarely inside the areas the phase context flagged as highest-severity: an archive-extraction guard that can be silently bypassed via path-alias duplicate members, and a two-file manifest publish that is not atomic, so a failure partway through can leave a manifest.json on disk in exactly the "hard stop that should have prevented a manifest" scenario the phase is designed to avoid. Neither is exercised by the existing test suite, which strengthens rather than weakens the finding — the current duplicate-name test (`test_duplicate_member_name_rejected`) only covers byte-identical literal filenames, and the current manifest OSError test (`test_oserror_translates_to_manifest_write_failed`) patches `os.open` globally, so both file creates fail identically and the "manifest committed, sidecar failed" path is never reached.

A known issue is already recorded and is intentionally not repeated here: `vicmap.toml`'s `max_compression_ratio = 20` will hard-stop on the real OpenFileGDB delivery.

## Critical Issues

### CR-01: Archive duplicate-member guard compares raw filenames, not resolved destinations — path-alias members silently overwrite each other post-hash

**Verified:** CONFIRMED by live reproduction (orchestrator, at HEAD). A zip with members `d/f.txt` and `d//f.txt` extracts with no guard trip. `ExtractionResult.members` records two entries — `d//f.txt` sha `93f75c82…` (11 bytes) and `d/f.txt` sha `a8ddaa6b…` (10 bytes) — while exactly one file exists on disk: `d/f.txt`, sha `93f75c82…`, 11 bytes. The manifest entry for `d/f.txt` names a digest that no file on disk has.

**File:** `vicmap_acquire/extraction.py:238-248` (`_validate_members`), guard logic in `vicmap_acquire/extraction.py:181-218` (`_reject_unsafe_member`)

**Issue:**

`_validate_members` builds its D-26 "hardlink-style aliasing" duplicate check from the raw `info.filename` string:

```python
seen_names: set[str] = set()
validated: list[tuple[zipfile.ZipInfo, Path]] = []
for info in infolist:
    if info.filename in seen_names:
        raise ArchiveUnsafeMemberRejected()
    destination = _reject_unsafe_member(info, destination_root)
    seen_names.add(info.filename)
    validated.append((info, destination))
```

`_reject_unsafe_member` independently computes each member's **resolved destination path** via `(destination_root / normalized).resolve()` (extraction.py:215), and pathlib collapses redundant separators and `.` segments during that resolution. Two members with *different* literal `ZipInfo.filename` strings — e.g. `"a/b"` and `"a//b"`, or `"a/b"` and `"a/./b"` — pass the `".."`/`":"` component checks (neither contains a `..` or `:` part) and both resolve to the **identical on-disk destination path**, yet `seen_names` never flags them as duplicates because it compares the unresolved strings, not the resolved paths.

At write time (extraction.py:313-366), the second member's `open(destination, "wb")` silently truncates and overwrites the first member's already-written, already-hashed bytes. The `members` list ends up with two `ExtractedMember` entries for what is now one file on disk: the first entry's `sha256`/`byte_count` no longer match the bytes that actually exist at that path once extraction completes. This is a genuine bypass of the guard the module's own docstring promises ("Duplicate-name detection (D-26's hardlink-style aliasing guard) is the caller's responsibility"), and it is directly constructible with the existing test harness's own `_member()`/`_build_archive()` helpers (`tests/test_extraction.py`) — no adversarial zip crafting beyond what the suite already builds for other cases.

This is worse on the two Darwin targets `flake.nix` builds for (`aarch64-darwin`, `x86_64-darwin`): the default case-insensitive-but-case-preserving APFS makes `"a/b"` vs `"a/B"` alias on disk too, and neither the resolved-path check nor the current string-based `seen_names` check catches case-only aliasing at all.

The existing regression (`tests/test_extraction.py::MemberGuardRejectionTest::test_duplicate_member_name_rejected`) only proves the guard catches *exact* literal duplicate filenames; it does not exercise this path-alias case, so the gap is untested as well as unguarded.

**Fix:**

Detect aliasing by destination identity, not by the raw archive-supplied name — and prefer a filesystem-truth check over a pure-Python set, so it also catches case-only aliasing on case-insensitive filesystems:

```python
def _validate_members(
    infolist: list[zipfile.ZipInfo], destination_root: Path, policy: ExtractionPolicy
) -> list[tuple[zipfile.ZipInfo, Path]]:
    if len(infolist) > policy.max_member_count:
        raise ArchiveCeilingExceeded()

    seen_destinations: set[Path] = set()
    validated: list[tuple[zipfile.ZipInfo, Path]] = []
    for info in infolist:
        destination = _reject_unsafe_member(info, destination_root)
        # Alias by resolved destination, not by the archive-supplied literal
        # name -- "a/b" and "a//b" (or "a/./b") resolve to the same path and
        # must be treated as the same D-26 aliasing violation the exact
        # duplicate-name case already covers. destination_root is guaranteed
        # fresh at this point, so a pre-existing entry can only mean an
        # earlier member in this same archive already claimed it -- this
        # also catches case-only aliasing on case-insensitive filesystems
        # (the default on the aarch64-darwin/x86_64-darwin flake targets),
        # which a pure Python set of resolved Path objects would miss.
        if destination in seen_destinations or destination.exists():
            raise ArchiveUnsafeMemberRejected()
        seen_destinations.add(destination)
        validated.append((info, destination))
    return validated
```

Add a regression alongside `test_duplicate_member_name_rejected` using two members with different literal names that resolve to the same path (e.g. `_member("a/b", b"one"), _member("a//b", b"two")`).

### CR-02: `write_manifest` publishes `manifest.json` and its `.sha256` sidecar as two independent, non-atomic commits — a failure between them leaves a half-published, unverifiable manifest that can never be completed by a retry

**Verified:** CONFIRMED by live reproduction (orchestrator, at HEAD). With only `manifest.json.sha256` pre-existing in the run directory, `write_manifest` raises `ManifestWriteFailed` — the reported hard stop — yet leaves a complete 290-byte `manifest.json` on disk. A second `write_manifest` into the same directory also raises `ManifestWriteFailed`: the run is permanently unable to publish.

**File:** `vicmap_acquire/manifest.py:171-197` (`write_manifest`)

**Issue:**

```python
manifest_path = run_directory / "manifest.json"
sidecar_path = run_directory / "manifest.json.sha256"

_write_new_file_fsync(manifest_path, canonical + "\n")
_write_new_file_fsync(sidecar_path, digest + "\n")
return digest
```

Each `_write_new_file_fsync` call is individually durable (`O_EXCL`, `fsync`, `fdopen`), but the two calls are not committed together. If the first call succeeds and the second raises `OSError` (disk full, permission change, a crash between the two calls), `write_manifest` raises `ManifestWriteFailed` — the caller (`discover_order.run_discovery`) treats this as a hard stop and emits exactly one redacted `SafeFailure` — but `manifest.json` is now **durably on disk** in `run_directory` with no matching `.sha256` sidecar. This directly contradicts the module's own stated guarantee ("gives the operator something durable to review... 'immutable', provable") and is exactly the failure mode the phase context calls out: a manifest exists on disk after a run that was reported to the operator as a hard stop.

Worse, this state is not automatically recoverable: because `manifest.json` was created with `O_EXCL`, any retry into the *same* `run_directory` (same `order_id`/`run_timestamp`) fails immediately with `FileExistsError` on the very first `_write_new_file_fsync(manifest_path, ...)` call, before ever reaching the sidecar write — so the run directory is permanently stuck with an unverifiable manifest until an operator manually intervenes.

The existing regression (`tests/test_manifest.py::ManifestRoundTripTest::test_oserror_translates_to_manifest_write_failed`) patches `os.open` globally, so both file-creates fail identically and this specific "first file committed, second file fails" ordering is never exercised.

**Fix:**

Roll back the just-published `manifest.json` if the sidecar write fails, so a failed call always leaves the run directory in the same state as before the call (and a retry can succeed):

```python
manifest_path = run_directory / "manifest.json"
sidecar_path = run_directory / "manifest.json.sha256"

_write_new_file_fsync(manifest_path, canonical + "\n")
try:
    _write_new_file_fsync(sidecar_path, digest + "\n")
except OSError:
    # A partially published manifest (present without its verifying
    # sidecar) must never survive a reported failure -- and leaving it
    # would also permanently block every retry via O_EXCL. Roll back the
    # just-committed manifest.json so this call's failure leaves no trace,
    # exactly as every other guard in this phase does.
    try:
        manifest_path.unlink()
    except OSError:
        pass
    raise
return digest
```

(The outer `except OSError: raise ManifestWriteFailed() from None` already wraps this correctly once the inner `raise` re-propagates.) Add a regression that fails only the *second* `os.open`/`_write_new_file_fsync` call and asserts `manifest.json` does not exist afterward.

## Warnings

### WR-01: `find_datasets` matches archive suffixes case-sensitively, so an uppercase-extension delivery silently fails to discover its own dataset

**File:** `vicmap_acquire/discovery.py:35-43` (`_EXTENSION_DRIVERS`), `vicmap_acquire/discovery.py:168` (`find_datasets`)

**Issue:** `_EXTENSION_DRIVERS.get(path.suffix)` is a case-sensitive dict lookup against `Path.suffix`, which preserves the on-disk case exactly. A delivery whose dataset is named `VMADD.GDB` (or any other non-lowercase extension) is invisible to `find_datasets` — it is neither recognized as a candidate nor descended into — and, if nothing else in the archive matches, the run ends in `DeliveryEmpty`. This still fails closed (no silent success with the wrong data), but it fails with a generic "delivery is empty" reason rather than anything that points an operator at the real cause, for a variation (extension casing) that is plausible across different delivery tooling versions.

**Fix:** Normalize the comparison, not the admitted set: `_EXTENSION_DRIVERS.get(path.suffix.casefold())` with the dict's keys already lowercase (as they are today), or `next((driver for suffix, driver in _EXTENSION_DRIVERS.items() if path.suffix.casefold() == suffix), None)`.

### WR-02: `manifest.json`'s and its sidecar's directory entries are never fsynced after creation

**File:** `vicmap_acquire/manifest.py:171-197` (`write_manifest`), contrast with `vicmap_acquire/extraction.py:157-179`/`vicmap_acquire/download.py:289-311` (`_fsync_directory`)

**Issue:** Both `extraction.py` and `download.py` fsync the parent directory after their atomic publish step, specifically because a new directory entry (as opposed to the file's own data) is not guaranteed durable across a crash without it. `manifest.py`'s `write_manifest` fsyncs each file's own file descriptor but never calls the sibling `_fsync_directory` pattern on `run_directory` after either `manifest.json` or `manifest.json.sha256` is created. On a crash shortly after a successful `write_manifest` return, the manifest's directory entry (its filename) is not guaranteed to survive even though its content was fsynced — a smaller instance of the same durability gap as CR-02.

**Fix:** After both files are written (and as part of the CR-02 fix, only once both are known-good), call the same `_fsync_directory(run_directory)` idiom `extraction.py`/`download.py` already use.

## Info

### IN-01: `_RESERVED_KEYWORDS` in naming.py is a hand-transcribed constant with no independent oracle verifying it against real PostgreSQL

**File:** `vicmap_acquire/naming.py:33-65`

**Issue:** `POSTGRES_KEYWORD_SNAPSHOT`'s docstring states the set was "transcribed" from the PostgreSQL 18 documentation appendix by hand, not generated from a machine-readable source. `tests/test_naming.py::PostgresKeywordSnapshotTest` checks that a fixed shortlist of "trap words" (the words a naive shortlist commonly misses) is present, but nothing in the test suite cross-checks the full set against an independent oracle (e.g. `SELECT word FROM pg_get_keywords() WHERE catcode IN ('R','T')` against a real PostgreSQL instance, mirroring the differential-oracle discipline `tests/test_discovery_differential.py` already applies to `ogrinfo`). A transcription gap here is asymmetric-risk: a keyword missing from the set produces a table name that later fails at CREATE TABLE time in Phase 3 (safe, just confusing); an *extra*, incorrectly-included word only over-rejects (also safe). Both directions fail closed today, so this is not a bug, but it is the one closed-set in this phase whose correctness rests entirely on manual transcription rather than either generation or an independent check.

**Fix:** If a PostgreSQL instance is available in CI, add a differential test that fetches the live reserved-keyword set and asserts equality (or a documented, reviewed subset relationship) with `_RESERVED_KEYWORDS`, rather than relying solely on the hand-picked trap-word regression.

---

_Reviewed: 2026-09-16T10:57:58Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
