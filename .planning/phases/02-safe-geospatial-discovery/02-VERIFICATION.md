---
phase: 02-safe-geospatial-discovery
verified: 2026-09-16T21:30:00Z
status: gaps_found
score: 3/6 must-haves verified
covered_files:
  - ".gitignore"
  - ".planning/REQUIREMENTS.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-01-PLAN.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-01-SUMMARY.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-02-PLAN.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-02-SUMMARY.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-03-PLAN.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-03-SUMMARY.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-04-PLAN.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-04-SUMMARY.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-05-PLAN.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-05-SUMMARY.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-06-PLAN.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-06-SUMMARY.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-REVIEW.md"
  - "discover_order.py"
  - "flake.nix"
  - "read_mailbox.py"
  - "vicmap.toml"
  - "vicmap_acquire/discovery.py"
  - "vicmap_acquire/download.py"
  - "vicmap_acquire/evidence.py"
  - "vicmap_acquire/extraction.py"
  - "vicmap_acquire/manifest.py"
  - "vicmap_acquire/naming.py"
covered_digest: "v1:sha256:2d7e28dccf695afdaca17a399066abf7a4b8ad9ab5a67a0cf1d3cda9827f0b34"
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "The archive is extracted into an isolated run directory, and traversal paths, unsafe links, or any attempted write outside that directory are rejected (SC1 / GEO-01)."
    status: failed
    reason: "The D-26 duplicate-member ('hardlink-style aliasing') guard in extraction.py compares raw ZipInfo.filename strings, not resolved destination paths. Independently reproduced: a zip with members `d/f.txt` and `d//f.txt` extracts with no guard trip. Exactly one file exists on disk (`d/f.txt`, 12 bytes, sha256 fbb06514d3ee...), but ExtractionResult.members records two entries, including one for `d/f.txt` with byte_count=10 and sha256=11fd6e99ed51... that matches no file on disk. The run reports success while the extraction result -- and therefore the manifest -- silently records incorrect provenance for an archive member. This is a direct violation of 02-03-PLAN.md's own must-have: 'Every member of the archive is accounted for in the extraction result with its relative path, byte count, and SHA-256.'"
    artifacts:
      - path: "vicmap_acquire/extraction.py"
        issue: "_validate_members (lines 238-248) builds seen_names from info.filename (the raw archive-supplied string) instead of the resolved destination path _reject_unsafe_member already computes at line 215. 'a/b' and 'a//b' (or 'a/./b') resolve to the same on-disk path but are never flagged as duplicates."
    missing:
      - "Detect aliasing by resolved destination path (and, ideally, filesystem existence) rather than by raw archive-supplied name, so path-alias and case-only (APFS) aliasing are both caught before any output handle is opened."
      - "A regression using two members with different literal names that resolve to the same destination path."
  - truth: "The manifest is immutable: a hard stop never leaves a manifest.json / sidecar behind, and a retry into the same run directory can proceed (goal statement 'immutable import manifest'; D-29; explicit must-have in 02-06-PLAN.md: 'Every GEO-05 hard stop ... leaves no manifest.json and no manifest sidecar anywhere under the run root')."
    status: failed
    reason: "write_manifest publishes manifest.json and manifest.json.sha256 as two independent O_EXCL creates with no rollback between them. Independently reproduced: with only manifest.json.sha256 pre-existing in the run directory, write_manifest raises ManifestWriteFailed (the reported hard stop) but leaves a complete, valid manifest.json on disk. A second write_manifest call into the same run directory also raises ManifestWriteFailed -- via O_EXCL against the now-pre-existing manifest.json -- so the run directory is permanently stuck; no retry can ever complete. This directly falsifies 02-06-PLAN.md's own stated must-have."
    artifacts:
      - path: "vicmap_acquire/manifest.py"
        issue: "write_manifest (lines 171-197) calls _write_new_file_fsync(manifest_path, ...) then _write_new_file_fsync(sidecar_path, ...) with no try/rollback around the second call. A failure on the second call leaves the first file committed."
    missing:
      - "Roll back (unlink) the just-published manifest.json if the sidecar write fails, so a failed write_manifest call always leaves the run directory in the same state as before the call."
      - "A regression that fails only the second create and asserts manifest.json does not exist afterward."
  - truth: "The pipeline can process the real production order end-to-end using the shipped vicmap.toml configuration (implied by the phase goal and by 02-CONTEXT.md's grounding in the real Order_OK0VUZ.zip delivery)."
    status: failed
    reason: "vicmap.toml ships [extraction].max_compression_ratio = 20 (confirmed at HEAD). The real OpenFileGDB delivery's small index members (e.g. a00000006.gdbtablx) compress up to ~139x, per 02-06-SUMMARY.md's own live-test finding, which worked around this by hardcoding a test-local ratio of 200 rather than fixing vicmap.toml. A real `python discover_order.py` invocation against the actual downloaded artifact will hard-stop with archive_ceiling_exceeded before any layer is discovered. This was explicitly flagged by the executor as an unresolved action item, not fixed by any of the 6 plans."
    artifacts:
      - path: "vicmap.toml"
        issue: "[extraction].max_compression_ratio = 20 is miscalibrated against the real delivery's actual compression ratios; 02-01's tracer fixture and 02-06's live regression both needed a local override to 200 to proceed."
    missing:
      - "Raise vicmap.toml's [extraction].max_compression_ratio to a value that accommodates real OpenFileGDB index-file compression ratios (200+, matching both test-local overrides already used), or otherwise recalibrate D-26's ceiling defaults against the real delivery."
requirements_status:
  - id: GEO-01
    status: blocked
    reason: "CR-01: duplicate/aliased member guard is bypassable, corrupting recorded extraction provenance."
  - id: GEO-02
    status: satisfied
  - id: GEO-03
    status: satisfied
  - id: GEO-04
    status: satisfied
  - id: GEO-05
    status: blocked
    reason: "CR-02: a reported hard stop (ManifestWriteFailed) does not guarantee no manifest.json survives, contradicting the phase's own explicit must-have and permanently blocking retry into the same run directory."
---

# Phase 2: Safe Geospatial Discovery Verification Report

**Phase Goal:** The operator can turn the downloaded order into a complete, immutable import manifest before any database mutation.
**Verified:** 2026-09-16T21:30:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 (GEO-01): Archive extracted into isolated run directory; traversal, unsafe links, writes outside directory rejected | ✗ FAILED | Independently reproduced CR-01: a zip with members `d/f.txt` and `d//f.txt` extracts with no guard trip. `ExtractionResult.members` records two entries (one with a sha256/byte_count matching no file on disk) while exactly one file exists on disk. See `vicmap_acquire/extraction.py:238-248`. |
| 2 | SC2 (GEO-02/GEO-03): Operator sees every supported dataset and layer, with fields, feature count, geometry type, source CRS | ✓ VERIFIED | `tests/test_discovery_differential.py` (independent `ogrinfo` oracle, 4/4 pass, spot-checked live); `tests/test_manifest.py::LiveDeliveryRegressionTest` pins the real delivery: `ADDRESS` layer, feature_count 4222035, EPSG 7899, 61 real fields, `OBJECTID`/`SHAPE` FID/geometry columns. |
| 3 | SC3 (GEO-04): Every source layer has a deterministic target table name visible before loading | ✓ VERIFIED | `vicmap_acquire/naming.py` implements D-21 through D-24 exactly (composition, casefold, separator collapse, charset/leading-digit/reserved-word/byte-length checks, exact-equality collision detection, no DB contact). Live regression confirms `VMADD.gdb`/`ADDRESS` → `vmadd_address`. `tests/test_naming.py` full run: OK. |
| 4a | SC4 (GEO-05), literal: No database object is ever changed by Phase 2 | ✓ VERIFIED | `tests/test_manifest.py::NoSocketNoDatabaseTest` proves no DB driver import and no live socket use anywhere in a successful run (instrumented, not inspection-only). `discover_order.py` imports no DB library. |
| 4b | Phase goal / D-29: manifest is immutable — a reported hard stop leaves no `manifest.json`/sidecar, so a retry can proceed | ✗ FAILED | Independently reproduced CR-02: with only `manifest.json.sha256` pre-existing, `write_manifest` raises `ManifestWriteFailed` (the reported hard stop) yet leaves a complete `manifest.json` on disk. A second call into the same directory also raises `ManifestWriteFailed` — permanently stuck. Directly contradicts 02-06-PLAN.md's own must-have: "Every GEO-05 hard stop ... leaves no `manifest.json` and no manifest sidecar anywhere under the run root." |
| 5 | The pipeline can process the real production order end-to-end under the shipped `vicmap.toml` | ✗ FAILED | `vicmap.toml`'s `[extraction].max_compression_ratio = 20` (confirmed at HEAD via `grep`) is below the real delivery's measured ~139x on small index members. 02-06-SUMMARY.md's own live test needed a test-local override of 200 to pass; production config was never changed. A real CLI run today hard-stops with `archive_ceiling_exceeded` before discovering any layer. |

**Score:** 3/6 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `vicmap_acquire/extraction.py` | Fail-closed archive extraction, ExtractionPolicy contract | ⚠️ WIRED but defective | Present, substantive, wired into `discover_order.run_discovery`. CR-01 defect confirmed live (see gap 1). |
| `vicmap_acquire/discovery.py` | pyogrio + ogrinfo layer profiling | ✓ VERIFIED | Present, substantive, wired; differential-oracle tests pass; live-regression pins real delivery values. |
| `vicmap_acquire/naming.py` | D-21–D-24 normalization and collision detection | ✓ VERIFIED | Present, substantive, wired; pure-function module with no DB import (checked). |
| `vicmap_acquire/manifest.py` | Frozen ImportManifest contract + manifest.json persistence | ⚠️ WIRED but defective | Present, substantive, wired into `discover_order.run_discovery`. CR-02 defect confirmed live (see gap 2). |
| `discover_order.py` | Guarded CLI + `run_discovery` orchestration | ✓ VERIFIED | Ordered verify→extract→discover→name→build→write→render pipeline confirmed by reading source; `_EmitOnce` guard reused correctly; no DB/network import. |
| `flake.nix` | pyogrio/pyproj/ogrinfo in dev shell | ✓ VERIFIED | Tests requiring these tools run and pass under `nix develop path:.`. |
| `.gitignore` | Unanchored `runs/` exclusion matching `artifacts/` | ✓ VERIFIED | `grep` confirms `runs/` (line 25) and `artifacts/` (line 24) both unanchored. |
| `vicmap.toml` `[extraction]`/`[discovery]` | Reviewable non-secret policy | ⚠️ PRESENT but miscalibrated | Sections exist with the documented shape, but `max_compression_ratio = 20` blocks the real delivery (see gap 3). |
| `.planning/phases/02-safe-geospatial-discovery/COVERAGE.md` | Reasoned no-external-API declaration | ✓ VERIFIED | Present, contains "No external API integration:" and a reasoned boundary table. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `discover_order.py` | `vicmap_acquire/extraction.py` | `verify_artifact` then `extract_artifact` before any discovery call | ✓ WIRED | Confirmed by reading `run_discovery` (lines 126-144). |
| `discover_order.py` | `vicmap_acquire/discovery.py` | `discover_layers` on the published run directory | ✓ WIRED | Confirmed (line 158). |
| `discover_order.py` | `vicmap_acquire/naming.py` | `assign_target_table_names` on every discovered profile | ✓ WIRED | Confirmed (line 159); automatic, unconditional (D-30). |
| `discover_order.py` | `vicmap_acquire/manifest.py` | `build_manifest` then `write_manifest`, only after naming succeeds | ✓ WIRED | Confirmed (lines 174-184). |
| `vicmap_acquire/manifest.py` | `vicmap_acquire/evidence.py` | redacted operator output via `fingerprint()`/`SuccessEvent` | ✓ WIRED | Confirmed via `discover_order.py`'s `SuccessEvent.manifest_completed(...)` call; manifest payload itself never rendered directly. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| CR-01 (duplicate-member aliasing bypass) | Standalone script constructing a zip with `d/f.txt`/`d//f.txt` and calling `extract_artifact` | No exception raised; `ExtractionResult.members` records a checksum matching no file on disk | ✗ FAIL (confirms review finding) |
| CR-02 (non-atomic manifest publish) | Standalone script pre-creating only `manifest.json.sha256`, then calling `write_manifest` twice | First call raises `ManifestWriteFailed` but leaves `manifest.json` on disk; second call (retry) also raises `ManifestWriteFailed` | ✗ FAIL (confirms review finding) |
| Discovery/oracle agreement | `nix develop path:. -c python -m unittest tests.test_discovery_differential -v` | 4/4 tests OK | ✓ PASS |
| Naming/extraction/manifest regressions | `nix develop path:. -c python -m unittest tests.test_naming tests.test_extraction tests.test_manifest -v` | 100/100 tests OK | ✓ PASS (note: these tests do not exercise the CR-01/CR-02 paths — confirmed by independent reproduction above) |
| Debt-marker scan | `grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` over all phase-modified files | No matches | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|-----------------|--------------|--------|----------|
| GEO-01 | 02-01, 02-02, 02-03 | Unpack order archive into isolated run directory without permitting traversal, unsafe links, writes outside directory | ✗ BLOCKED | CR-01: duplicate/path-alias member guard bypassable — see gap 1. |
| GEO-02 | 02-01, 02-02, 02-04, 02-06 | See every supported dataset and layer discovered | ✓ SATISFIED | Live regression + differential oracle. |
| GEO-03 | 02-01, 02-04, 02-06 | See each layer's fields, feature count, geometry type, source CRS | ✓ SATISFIED | Live regression + differential oracle. |
| GEO-04 | 02-01, 02-05, 02-06 | See deterministic source-layer-to-table-name mapping before DB mutation | ✓ SATISFIED | `naming.py` + live regression. |
| GEO-05 | 02-01, 02-04, 02-05, 02-06 | Stop before DB mutation if datasets unreadable or names collide | ✗ BLOCKED | CR-02: a reported hard stop does not guarantee no manifest artifact survives, contradicting the phase's own explicit must-have and blocking retry. DB itself is never touched (verified), but the "hard stop leaves a clean, retryable state" contract this requirement's phase-level design depends on is broken. |

No orphaned requirements found — GEO-01 through GEO-05 all appear in at least one plan's `requirements` frontmatter, matching REQUIREMENTS.md's traceability table.

**Note:** `.planning/REQUIREMENTS.md` currently marks GEO-01 through GEO-05 as `[x]` complete. This verification found GEO-01 and GEO-05 to be BLOCKED by live-reproduced defects; that checklist should be revisited once the gaps below are closed.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `vicmap_acquire/extraction.py` | 238-248 | Duplicate-member guard uses unresolved string identity instead of resolved-path/filesystem identity | 🛑 Blocker | Silent corruption of extraction result / manifest provenance (CR-01). |
| `vicmap_acquire/manifest.py` | 171-197 | Two-file publish (`manifest.json` + sidecar) has no rollback on partial failure | 🛑 Blocker | Non-atomic "immutable" manifest; permanently blocks retry on partial failure (CR-02). |
| `vicmap_acquire/discovery.py` | 35-43, 168 | `_EXTENSION_DRIVERS.get(path.suffix)` is case-sensitive | ⚠️ Warning | An uppercase-extension delivery (e.g. `VMADD.GDB`) is invisible to discovery and fails with a generic `DeliveryEmpty` rather than a pointed diagnosis. Does not affect the current real delivery (observed lowercase `.gdb`). Not independently re-verified beyond reading the review's code citation — treated as WARNING per the review's own classification. |
| `vicmap_acquire/manifest.py` | 171-197 | Directory entries for `manifest.json`/sidecar never fsynced (only file contents are) | ⚠️ Warning | Smaller instance of CR-02's durability gap — a crash shortly after a successful `write_manifest` return could lose the directory entry. Not independently re-verified with a crash-injection test; accepted from the code review's citation. |
| `vicmap_acquire/naming.py` | 33-65 | Hand-transcribed PostgreSQL reserved-keyword snapshot, no independent oracle check | ℹ️ Info | Fails closed in both directions (missing keyword → later CREATE TABLE failure in Phase 3, safe; extra keyword → over-rejection, safe). Not a correctness bug today. |
| `vicmap.toml` | 26 | `max_compression_ratio = 20` miscalibrated against real delivery (up to ~139x on small index members) | 🛑 Blocker | Real `discover_order.py` run against `Order_OK0VUZ.zip` hard-stops before discovering any layer — see gap 3. |

### Human Verification Required

None. All findings above were independently reproduced with deterministic scripts against the actual codebase at HEAD (not inferred from SUMMARY.md or the code review alone).

### Gaps Summary

Three gaps block the phase goal, all with independently reproduced evidence (not merely re-stated review findings):

1. **CR-01 — extraction duplicate-member guard is bypassable by path aliasing.** `vicmap_acquire/extraction.py`'s `_validate_members` compares raw `ZipInfo.filename` strings, not resolved destination paths. Two members that resolve to the same on-disk path (e.g. `d/f.txt` and `d//f.txt`) both pass the guard; the second silently overwrites the first on disk, but `ExtractionResult.members` still carries an entry for the first member whose recorded SHA-256 and byte count match nothing on disk. This directly falsifies the phase's own accuracy guarantee for extraction ("every member... accounted for... with its... byte count, and SHA-256") and, by extension, the "complete" half of the phase goal, since the manifest inherits this false data. The run does **not** stop — it reports success with corrupted data, which is a more severe failure mode than a hard stop.

2. **CR-02 — manifest publish is not atomic.** `vicmap_acquire/manifest.py`'s `write_manifest` writes `manifest.json` then its `.sha256` sidecar as two independent `O_EXCL` creates with no rollback. A failure between the two (confirmed with only the sidecar pre-existing) leaves `manifest.json` durably on disk even though the caller is told the run hard-stopped, and because the file was created with `O_EXCL`, no retry into the same run directory can ever succeed afterward. This directly falsifies 02-06-PLAN.md's explicit must-have that every GEO-05 hard stop "leaves no `manifest.json` and no manifest sidecar anywhere under the run root," and breaks the "immutable" half of the phase goal.

3. **Production `vicmap.toml` cannot process the real delivery.** `[extraction].max_compression_ratio = 20` is below the real order's measured compression ratios (up to ~139x on small OpenFileGDB index files). 02-01's tracer test and 02-06's live-delivery regression both worked around this with test-local overrides (`200`) rather than updating the shipped config. As shipped, a real `python discover_order.py` invocation against the actual downloaded artifact hard-stops with `archive_ceiling_exceeded` before discovering any layer — the phase's central deliverable does not work end-to-end against the real data it was built for, without a manual config edit first.

Everything else checked — dataset/layer discovery (GEO-02/GEO-03), deterministic naming (GEO-04), the "no database contact" guarantee, redaction discipline, `.gitignore` treatment, ordered pipeline composition, and absence of debt markers — is solid and independently confirmed against the real delivery via the live regression test and the `ogrinfo` differential oracle.

None of the three gaps are deferred to a later phase: all sit squarely inside Phase 2's own boundary (extraction safety, manifest immutability, and enabling a real run), not inside Phase 3/4/5 scope.

---

_Verified: 2026-09-16T21:30:00Z_
_Verifier: Claude (gsd-verifier)_
