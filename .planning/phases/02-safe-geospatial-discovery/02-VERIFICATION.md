---
phase: 02-safe-geospatial-discovery
verified: 2026-09-17T00:00:00Z
status: passed
score: 6/6 must-haves verified
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
  - ".planning/phases/02-safe-geospatial-discovery/02-07-PLAN.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-07-SUMMARY.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-08-PLAN.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-08-SUMMARY.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-09-PLAN.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-09-SUMMARY.md"
  - ".planning/phases/02-safe-geospatial-discovery/02-REVIEW.md"
  - "discover_order.py"
  - "flake.nix"
  - "read_mailbox.py"
  - "tests/test_discovery.py"
  - "tests/test_discovery_config.py"
  - "tests/test_extraction.py"
  - "tests/test_manifest.py"
  - "vicmap.toml"
  - "vicmap_acquire/discovery.py"
  - "vicmap_acquire/download.py"
  - "vicmap_acquire/evidence.py"
  - "vicmap_acquire/extraction.py"
  - "vicmap_acquire/manifest.py"
  - "vicmap_acquire/naming.py"
covered_digest: "v1:sha256:8daa0716588bb6dc4a0801ca5c54c662482ad833aeee6506ca21dbb41aa261af"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/6
  gaps_closed:
    - "GEO-01: extraction duplicate-member aliasing guard bypassable by path/case aliasing (CR-01) — fixed in 02-08."
    - "GEO-05 / phase goal: manifest publication non-atomic, a reported hard stop could leave manifest.json behind and permanently block retry (CR-02) — fixed in 02-09."
    - "Pipeline cannot process the real production order under the shipped vicmap.toml (max_compression_ratio=20 too low) — fixed in 02-07."
  gaps_remaining: []
  regressions: []
advisory:
  - finding: "WR-03 (raised in 02-REVIEW.md, committed 679b07c): the 02-08 write-time exclusive-create guard in vicmap_acquire/extraction.py leaks the raw os.open() file descriptor and leaves an orphaned 0-byte file in the .tmp- directory when zip_file.open() raises on a malformed member (e.g. an unsupported/mismatched compression method)."
    category: other
    reason: "Live-reproduced independently this session (see Behavioral Spot-Checks) — confirmed real, not speculative. Does not corrupt provenance, does not cause a false success report, and does not survive process exit (discover_order.py is a per-invocation CLI). The correct typed failure (ArchiveUnreadable) is still raised and no run directory is published. It does not violate any must-have this phase declares. Recommend fixing by reordering the compound `with` statement (destination fd first) as the review suggests, as a fast follow-up, not a phase-blocking gap."
    evidence_status: "live-reproduced independently (fd count 4→5, non-decreasing; 0-byte orphan file confirmed on disk)"
human_verification: []
---

# Phase 2: Safe Geospatial Discovery Verification Report

**Phase Goal:** The operator can turn the downloaded order into a complete, immutable import manifest before any database mutation.
**Verified:** 2026-09-17T00:00:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (plans 02-07, 02-08, 02-09)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 (GEO-01): Archive extracted into isolated run directory; traversal, unsafe links, writes outside directory, and hardlink-style aliasing are all rejected | ✓ VERIFIED | CR-01 independently re-reproduced against HEAD with a standalone script (`d/f.txt` + `d//f.txt`): now raises `ArchiveUnsafeMemberRejected`, no run directory published. Also ran the exact regressions `test_double_slash_path_alias_rejected`, `test_dot_segment_path_alias_rejected`, `test_case_alias_rejected`, `test_aliased_pair_rejected_when_colliding_name_appears_{first,second}` — 5/5 pass. Independent provenance-integrity oracle (`ProvenanceIntegrityTest`, recomputes byte count + SHA-256 from disk, never from `ExtractionResult`'s own bookkeeping) run live against the tracer fixture and the real 46-member `artifacts/Order_OK0VUZ.zip` — 2/2 pass. |
| 2 | SC2 (GEO-02/GEO-03): Operator sees every supported dataset and layer, with fields, feature count, geometry type, source CRS | ✓ VERIFIED | Unchanged from prior verification plus 02-07's WR-01 hardening: `tests/test_discovery_differential.py` (independent `ogrinfo` oracle) and `FindDatasetsTest` (11/11, including new uppercase-extension regressions) run live — all pass. `LiveDeliveryRegressionTest` (see truth 5) pins `feature_count=4222035`, `epsg=7899` against the real delivery. |
| 3 | SC3 (GEO-04): Every source layer has a deterministic target table name visible before loading | ✓ VERIFIED | Unchanged, untouched by gap-closure plans. `vicmap_acquire/naming.py` unmodified; live regression confirms `vmadd_address`. |
| 4a | SC4 (GEO-05), literal: No database object is ever changed by Phase 2 | ✓ VERIFIED | `tests/test_manifest.py::NoSocketNoDatabaseTest` run live (2/2 pass) — no DB driver import, no live socket use in a successful run. |
| 4b | Phase goal / D-29: manifest is immutable — a reported hard stop leaves no `manifest.json`/sidecar, and a retry into the same run directory can proceed | ✓ VERIFIED | CR-02 independently re-reproduced against HEAD with two standalone scripts: (a) sidecar pre-existing → `write_manifest` raises `ManifestWriteFailed`, directory listing identical before/after, `manifest.json` absent; (b) a transient `os.open` failure on the sidecar create (mocked exactly once, mirroring `test_failed_sidecar_create_then_retry_succeeds_into_same_directory`) → first call fails and leaves no `manifest.json`, the **immediate retry into the same directory succeeds** and returns a digest. Also ran the full `ManifestRoundTripTest` class live — 19/19 pass, including `test_rollback_does_not_fire_on_pre_existing_complete_manifest`, `test_rollback_unlink_failure_still_raises_manifest_write_failed`, `test_successful_write_fsyncs_run_directory_exactly_once`, and `test_non_ascii_manifest_digest_is_byte_identity_not_code_point_count`. |
| 5 | The pipeline can process the real production order end-to-end under the shipped `vicmap.toml`, with no test-local ceiling override anywhere in the call path | ✓ VERIFIED | `vicmap.toml`'s `[extraction].max_compression_ratio` is now `200` (confirmed via `grep`); `git diff` shape confirms only this one value changed from the prior-verified `20`, all other ceilings byte-for-byte identical (`max_total_bytes=10737418240`, `max_member_bytes=4294967296`, `max_member_count=4096`). Read `tests/test_manifest.py::LiveDeliveryRegressionTest` source directly: it sources every ceiling from `read_mailbox.load_discovery_config(REPO_ROOT / "vicmap.toml")`, not a hardcoded policy. Ran it live — reported `ok`, not skipped (`artifacts/Order_OK0VUZ.zip` present), completing in 3.4s and publishing a manifest naming target table `vmadd_address` with `feature_count=4222035`, `epsg=7899`. Also ran `tests/test_discovery_config.py::ShippedCeilingCalibrationTest` live (2/2 pass) — independently derives the worst-case ratio from both archives via a bare `zipfile` walk and asserts the shipped ceiling strictly exceeds it. |

**Score:** 6/6 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `vicmap_acquire/extraction.py` | Fail-closed archive extraction, ExtractionPolicy contract, destination-identity aliasing guard | ✓ VERIFIED | Present, substantive, wired. `_validate_members` (lines 221-267) now keys aliasing on `_reject_unsafe_member`'s resolved destination `Path` plus a `normcase`/`casefold` key. Read directly and confirmed against the CR-01 defect description — matches exactly. Independently re-run and re-reproduced (see truth 1). |
| `vicmap_acquire/manifest.py` | Frozen ImportManifest contract + atomic manifest.json persistence with rollback | ✓ VERIFIED | Present, substantive, wired. `write_manifest` (lines 201-256) wraps the sidecar create in `try/except OSError`, unlinking `manifest_path` (provably the one this call created, since it's reached only after the manifest's own `O_EXCL` create succeeded) before re-raising. Directory fsync added at line 253. Independently re-reproduced (see truth 4b). |
| `vicmap_acquire/discovery.py` | pyogrio + ogrinfo layer profiling, case-insensitive extension recognition | ✓ VERIFIED | `find_datasets` now does `_EXTENSION_DRIVERS.get(path.suffix.casefold())`; table keys unchanged (`.gdb`, `.shp`, `.gpkg`, `.tab`, `.dxf`, all lowercase, confirmed by reading the module). Downstream driver re-check against `supported_formats` still runs unconditionally. |
| `vicmap.toml` `[extraction]`/`[discovery]` | Reviewable non-secret policy, calibrated to the real delivery | ✓ VERIFIED | `max_compression_ratio=200` confirmed live to clear the real delivery's measured worst case (~139.24x, ~1.44x headroom) — pinned by `ShippedCeilingCalibrationTest`, run live, pass. |
| `tests/test_extraction.py` | GEO-01 adversarial regressions, path/case-alias regressions, provenance-integrity oracle | ✓ VERIFIED | New classes/methods read directly; ran live (`MemberGuardRejectionTest` aliasing subset, `ProvenanceIntegrityTest`) — all pass. |
| `tests/test_manifest.py` | Manifest round-trip, hard-stop, rollback, live-delivery regressions | ✓ VERIFIED | `ManifestRoundTripTest` (19/19) and `LiveDeliveryRegressionTest` (1/1, not skipped) run live — all pass. |
| `discover_order.py` | Guarded CLI + `run_discovery` orchestration | ✓ VERIFIED | Unchanged by gap-closure plans; end-to-end path re-proven live against the real delivery. |
| `.planning/REQUIREMENTS.md` | GEO-01..GEO-05 traceability | ⚠️ STALE (documentation only) | See note below — checkbox/status columns are stale relative to this verification's findings; not a codebase defect. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `vicmap.toml` | `discover_order.py` | `read_mailbox.load_discovery_config` supplies `max_compression_ratio` into `ExtractionPolicy` | ✓ WIRED | Confirmed by reading `read_mailbox.py` and by the live-delivery test passing under the shipped value. |
| `tests/test_manifest.py` | `vicmap.toml` | Live regression reads shipped config instead of hardcoding ceilings | ✓ WIRED | Confirmed by reading `LiveDeliveryRegressionTest` source — no hardcoded ceiling literal remains except `run_root`. |
| `_validate_members` | `_reject_unsafe_member` | Resolved destination path becomes the whole-archive aliasing key | ✓ WIRED | Confirmed by reading `extraction.py:221-267` and by the CR-01 reproduction now raising as expected. |
| `vicmap_acquire/extraction.py` | `vicmap_acquire/manifest.py` | `ExtractionResult.members` supplies companion byte counts/digests the manifest records | ✓ WIRED | Unchanged; confirmed by reading `discover_order.py`'s `run_discovery`. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite regression | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py'` | `Ran 399 tests in 14.676s` / `OK` | ✓ PASS |
| CR-01 fix (aliasing guard) | Standalone script: zip with `d/f.txt` + `d//f.txt`, `extraction.extract_artifact(...)` | `Raised ArchiveUnsafeMemberRejected as expected`; final run directory absent | ✓ PASS |
| CR-01 regressions | `unittest tests.test_extraction.MemberGuardRejectionTest.test_double_slash_path_alias_rejected .test_dot_segment_path_alias_rejected .test_case_alias_rejected .test_aliased_pair_rejected_when_colliding_name_appears_first .test_aliased_pair_rejected_when_colliding_name_appears_second` | `Ran 5 tests ... OK` | ✓ PASS |
| Provenance-integrity oracle (independent of guard mechanism) | `unittest tests.test_extraction.ProvenanceIntegrityTest -v` | `Ran 2 tests ... OK` (tracer fixture + real 46-member delivery) | ✓ PASS |
| CR-02 fix (sidecar pre-existing) | Standalone script: pre-create `manifest.json.sha256`, call `write_manifest` | `ManifestWriteFailed` raised; directory listing before == after; `manifest.json` absent | ✓ PASS |
| CR-02 fix (retry succeeds) | Standalone script: mock one transient `os.open` failure on sidecar create, then call `write_manifest` again | First call fails, no `manifest.json` left; **second call (retry) succeeds and returns a digest**; both files present afterward | ✓ PASS |
| CR-02 regressions | `unittest tests.test_manifest.ManifestRoundTripTest -v` | `Ran 19 tests ... OK` | ✓ PASS |
| WR-01 fix (case-insensitive extensions) | `unittest tests.test_discovery.FindDatasetsTest -v` | `Ran 11 tests ... OK` (includes `test_uppercase_geodatabase_extension_is_recognized`, `test_uppercase_unsupported_extension_raises_unsupported_format`) | ✓ PASS |
| Calibration regression | `unittest tests.test_discovery_config -v` | `Ran 28 tests ... OK` (includes `ShippedCeilingCalibrationTest` x2) | ✓ PASS |
| Live production run under shipped config | `unittest tests.test_manifest.LiveDeliveryRegressionTest -v` | `ok` (not skipped), `[live-delivery] run_discovery elapsed: 3.4s` | ✓ PASS |
| No DB/socket contact | `unittest tests.test_manifest.NoSocketNoDatabaseTest -v` | `Ran 2 tests ... OK` | ✓ PASS |
| WR-03 reproduction (open finding, follow-up) | Standalone script: zip with one member whose local+central-directory compression-method fields are patched to an unsupported value (99), then `extract_artifact(...)` | `ArchiveUnreadable` raised (correct typed failure) but process fd count rose 4→5 and did not return to 4; a 0-byte orphan file was left at `.tmp-.../a.bin` | ⚠️ CONFIRMED LIVE, UNFIXED (see Advisory — not a phase-blocking defect) |
| Debt-marker scan | `grep -n -E "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` over all phase-modified files | Only match is `\\uXXXX` inside a docstring describing Unicode escape notation (`manifest.py:207`) — not a debt marker | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|-----------------|--------------|--------|----------|
| GEO-01 | 02-01, 02-02, 02-03, 02-08 | Unpack order archive into isolated run directory without permitting traversal, unsafe links, writes outside directory, or hardlink-style aliasing | ✓ SATISFIED | CR-01 fixed and independently re-reproduced; provenance-integrity oracle passes live against the real delivery. |
| GEO-02 | 02-01, 02-02, 02-04, 02-06, 02-07 | See every supported dataset and layer discovered | ✓ SATISFIED | Differential `ogrinfo` oracle + live regression + WR-01 case-insensitivity fix, all run live. |
| GEO-03 | 02-01, 02-04, 02-06 | See each layer's fields, feature count, geometry type, source CRS | ✓ SATISFIED | Live regression pins exact real-delivery values. |
| GEO-04 | 02-01, 02-05, 02-06 | See deterministic source-layer-to-table-name mapping before DB mutation | ✓ SATISFIED | `naming.py` unchanged and previously verified; live regression confirms `vmadd_address`. |
| GEO-05 | 02-01, 02-04, 02-05, 02-06, 02-07, 02-09 | Stop before DB mutation if datasets unreadable or names collide; a reported hard stop leaves no manifest artifact and permits retry | ✓ SATISFIED | CR-02 fixed and independently re-reproduced (rollback + retry-succeeds); `NoSocketNoDatabaseTest` re-run live; real delivery now processes end-to-end under the shipped config. |

No orphaned requirements found — GEO-01 through GEO-05 all appear in at least one plan's `requirements` frontmatter, matching REQUIREMENTS.md's traceability table.

**Note on `.planning/REQUIREMENTS.md` staleness:** The traceability table and checklist currently read GEO-01 `[x]` Complete, GEO-02/03/04 `[ ]` Gaps Found, GEO-05 `[x]` Complete. This is stale in **both directions** relative to the actual history: the prior `02-VERIFICATION.md` (2026-09-16) found the opposite pattern true at that time (GEO-01 and GEO-05 blocked; GEO-02/03/04 satisfied), and this re-verification now finds all five satisfied. This is a documentation bookkeeping gap, not a codebase defect — recommend updating `.planning/REQUIREMENTS.md`'s checkboxes and traceability table to mark all of GEO-01 through GEO-05 `[x]` Complete now that this VERIFICATION.md supersedes the prior one.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `vicmap_acquire/extraction.py` | 358-365 | Write-time exclusive-create guard (`os.open()` then a compound `with zip_file.open(...) as source, os.fdopen(descriptor, "wb") as target:`) leaks the raw destination file descriptor and orphans a 0-byte file if `zip_file.open()` raises on a malformed member | ⚠️ Warning | Live-reproduced (WR-03, raised in `02-REVIEW.md`, still open). Per-process resource leak on an adversarial/corrupt member; does not corrupt provenance, does not cause a false success report, does not survive process exit. Does not violate any must-have this phase declares. Recommended fix: swap the `with` ordering so the destination fd's context manager enters first (see `02-REVIEW.md` for the exact patch and regression). Follow-up, not phase-blocking. |
| `vicmap_acquire/naming.py` | 33-65 | Hand-transcribed PostgreSQL reserved-keyword snapshot, no independent oracle check (IN-01, carried forward unchanged since the original review) | ℹ️ Info | Fails closed in both directions; not a correctness bug today. Unchanged by this round's gap-closure plans. |
| `vicmap.toml` | 26 | `max_compression_ratio = 200` clears the real delivery's worst-case ratio (~139.24x) by only ~1.44x headroom (IN-02, `02-REVIEW.md`) | ℹ️ Info | Guarded live by `ShippedCeilingCalibrationTest`, which fails the moment a future delivery's worst case regresses past the shipped value. Not a security gap — `max_member_bytes`/`max_total_bytes` remain the binding resource bound. Noted for awareness only. |

### Human Verification Required

None. Every truth above was independently re-verified this session with a real command whose output is quoted above (a live behavioral reproduction, a live named-test run, or a `grep`/direct source read for static facts) — not inferred from SUMMARY.md, `02-REVIEW.md`, or the prior `02-VERIFICATION.md` alone.

### Gaps Summary

No gaps remain. All three gaps recorded in the prior `02-VERIFICATION.md` (2026-09-16, `gaps_found`, 3/6) are independently confirmed closed at HEAD:

1. **CR-01 (extraction aliasing bypass) — CLOSED.** Re-reproduced the exact prior defect (`d/f.txt` + `d//f.txt`) against HEAD: it now raises `ArchiveUnsafeMemberRejected` and publishes no run directory. The fix is keyed on `_reject_unsafe_member`'s resolved destination path plus a case-folded key, not on the raw archive-supplied name — closing both the path-alias and case-alias axes the original defect described. A new independent provenance-integrity oracle (recomputing every recorded member's byte count and SHA-256 from disk, never from the extraction result's own bookkeeping) now runs live against both the tracer fixture and the real 46-member delivery and passes, making this class of defect durably detectable regardless of how the guard is implemented in the future.

2. **CR-02 (non-atomic manifest publish) — CLOSED.** Re-reproduced the exact prior defect (sidecar pre-existing before `write_manifest`): the failed call now leaves the run directory byte-for-byte unchanged (`manifest.json` absent), where before it left a durable, unremovable `manifest.json` behind. Additionally verified the specific must-have the prior gap named as broken — "a second `write_manifest` call into the same run directory succeeds" — by reproducing a transient sidecar-write failure and confirming the very next call into the same directory succeeds and returns a digest. Ran the full `ManifestRoundTripTest` class (19 tests) live, including the rollback-scope guard (never unlinks a manifest it didn't just create) and the rollback-failure-still-raises-closed-exception guard.

3. **Shipped `vicmap.toml` cannot process the real delivery — CLOSED.** `max_compression_ratio` is now `200` in the shipped file (was `20`); confirmed the only other four ceiling/section values are unchanged. Ran `LiveDeliveryRegressionTest` live and confirmed it is not skipped and sources every ceiling from the shipped `vicmap.toml` via `read_mailbox.load_discovery_config` (no hardcoded test-local override remains in the call path) — it completed against the real 233 MB delivery in 3.4s and published a manifest naming `vmadd_address`. `ShippedCeilingCalibrationTest` independently derives the worst-case ratio from both archives with a bare `zipfile` walk and asserts the shipped ceiling clears it, so a future regression below the real delivery's worst case fails in CI.

One new, non-blocking finding from the incremental code review (`02-REVIEW.md`, WR-03) remains open and is independently confirmed live in this session: a file-descriptor leak and an orphaned 0-byte temp file when a malformed archive member's compression method makes `zip_file.open()` raise after the destination's exclusive-create `os.open()` has already succeeded. This does not corrupt recorded provenance, does not cause a false success report, and does not survive process exit — it is recorded as an advisory follow-up (see `advisory:` frontmatter and Anti-Patterns table above), not a gap. It does not block the phase goal: the operator can still turn a valid downloaded order into a complete, immutable import manifest before any database mutation, and a malformed/adversarial member is still correctly rejected with a typed closed failure rather than silently corrupting the manifest.

All five requirements (GEO-01 through GEO-05) are now satisfied, and the phase's stated goal — "The operator can turn the downloaded order into a complete, immutable import manifest before any database mutation" — holds against the real production delivery under the shipped, unmodified configuration.

---

_Verified: 2026-09-17T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
