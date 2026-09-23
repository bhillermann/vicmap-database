---
phase: 01-trusted-graph-acquisition
verified: 2026-09-23T00:00:00Z
status: passed
score: 21/21 must-haves verified
covered_files:
  - .gitignore
  - .planning/REQUIREMENTS.md
  - .planning/ROADMAP.md
  - .planning/phases/01-trusted-graph-acquisition/01-01-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-01-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-02-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-02-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-03-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-03-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-04-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-04-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-05-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-05-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-06-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-06-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-07-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-07-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-08-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-08-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-09-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-09-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-10-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-10-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-11-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-11-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-12-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-12-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-13-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-13-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-14-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-14-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md
  - .planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md
  - .planning/phases/01-trusted-graph-acquisition/01-REVIEW-GAP-CLOSURE.md
  - .planning/phases/01-trusted-graph-acquisition/01-REVIEW.md
  - .planning/phases/01-trusted-graph-acquisition/01-SECURITY.md
  - .planning/phases/01-trusted-graph-acquisition/01-VALIDATION.md
  - read_mailbox.py
  - tests/__init__.py
  - tests/test_candidates.py
  - tests/test_download.py
  - tests/test_evidence.py
  - tests/test_graph.py
  - tests/test_html_visibility_differential.py
  - tests/test_origin.py
  - tests/test_provenance.py
  - tests/test_repository_policy.py
  - vicmap.toml
  - vicmap_acquire/__init__.py
  - vicmap_acquire/candidates.py
  - vicmap_acquire/download.py
  - vicmap_acquire/evidence.py
  - vicmap_acquire/graph.py
  - vicmap_acquire/origin.py
covered_digest: "v1:sha256:98b948daf4e9f9be4fcc82787e1838db6735b8cb0ed66090b72b5861e99de7aa"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 21/21
  gaps_closed: []
  gaps_remaining: []
  regressions: []
gaps: []
---

# Phase 1: Trusted Graph Acquisition Verification Report (Re-verification — covered files changed after prior round)

**Phase Goal:** The operator can obtain exactly one authentic Vicmap order artifact from the automation mailbox without leaking sensitive content or trusting an unsafe download path.

**Verified:** 2026-09-23T00:00:00Z

**Status:** passed

**Re-verification:** Yes — superseding the 2026-09-14T13:10:00Z verification (`passed`, 21/21). That round is stale: Phase 2 (`02-02`) and Phase 3 (`03`, WR-06) plans subsequently modified four of the phase's own covered files (`read_mailbox.py`, `vicmap_acquire/download.py`, `vicmap_acquire/evidence.py`, `vicmap.toml`) and their regression tests (`tests/test_graph.py`, `tests/test_evidence.py`, `tests/test_download.py`) to add cross-cutting policy/evidence vocabulary and a durable provenance sidecar, plus a wholly new phase-1-relevant test file (`tests/test_provenance.py`). This round independently re-derives whether that touch broke any Phase 1 truth, rather than trusting the prior report's "unchanged" claims for those files.

## Goal Achievement

**What changed since the prior round, verified by direct diff, not by SUMMARY narrative.** `git diff 7dc124e..HEAD` (the last Phase 1 commit through the current tip) confirms the touch is entirely additive to the trust-critical path:

- `vicmap_acquire/origin.py`, `vicmap_acquire/candidates.py`, `vicmap_acquire/graph.py` — **zero diff**. The authenticated-origin binding, HTML-visibility recognition, and Graph read-only boundary are byte-for-byte unchanged since the 01-14 verification.
- `vicmap_acquire/download.py` (+149 lines) — purely additive: a new `ArtifactProvenance` dataclass and `write_provenance_sidecar`/`read_provenance_sidecar` functions that durably persist the message fingerprint, SHA-256, and byte count already computed by the unmodified download path, using the exact same atomic `os.link`-as-commit-point idiom as `_publish_artifact`. No existing function's body changed.
- `vicmap_acquire/evidence.py` (+497 lines) — additive `Stage`/`ReasonCode` vocabulary for Phases 2/3, plus one tightening fix (WR-06): `_HOST` widened from a loose pattern with no length bound to the same DNS-structured, 253-byte-bounded pattern already used by `read_mailbox._HOSTNAME`/`staging._HOSTNAME`. This is strictly more restrictive, not more permissive, and still matches the real approved hostname (`s3.ap-southeast-2.amazonaws.com`).
- `read_mailbox.py` (+470 lines) — additive: `run_provenance()` (a new entry point that backfills a sidecar for an artifact already on disk, without downloading) and a `--provenance-only` CLI flag; `load_config` now requires the complete five-section `vicmap.toml` (`mailbox`, `download`, `extraction`, `discovery`, `database`) instead of two, still validated pre-auth, still with no credential key in any section (confirmed: `VICMAP_DB_PASSWORD` stays environment-only, matching the pre-existing Phase 1 credential-handling guarantee). `run_acquisition`'s existing body is unchanged except for two additive lines that call the new sidecar writer and emit one new `artifact_verified` evidence event after the pre-existing `artifact_finalized` event — the original event is still emitted with the same fields.
- `vicmap.toml` — three new sections appended (`[extraction]`, `[discovery]`, `[database]`); the `[mailbox]`/`[download]` sections are untouched.

**Independently confirmed, not just read.** The full regression suite for every Phase 1 test module — including the new `tests/test_provenance.py` — was re-run directly in this pass and is 228/228 green (see Behavioral Spot-Checks). The on-disk live artifact and its provenance sidecar were independently re-hashed and cross-checked against both the sidecar JSON and `01-LIVE-VERIFICATION.md`'s recorded digest.

**One out-of-band artifact confirmed genuine, not merely present.** `artifacts/Order_OK0VUZ.provenance.json` (dated 16 Sep, after the 14 Sep verification and after the artifact's original 9 Sep download) was independently re-derived: `sha256sum artifacts/Order_OK0VUZ.zip` reproduces `6a7868...411b` exactly, matching both the sidecar's `sha256` field and `01-LIVE-VERIFICATION.md`'s recorded digest, and the sidecar's `byte_count` (233089097) matches the file's actual size. This is real evidence the Phase 2 provenance backfill (`run_provenance`, run once against the real artifact) executed correctly against Phase 1's real live proof artifact — reinforcing MAIL-05, not just failing to break it.

### Observable Truths

| # | Source | Truth | Status | Evidence |
|---|---|---|---|---|
| 1 | Roadmap SC1 | Authenticate, confirm the configured mailbox, and inspect a bounded Inbox result without credential/body output | ✓ VERIFIED | `vicmap_acquire/graph.py` unchanged (zero diff since 01-14); full suite regression-checked (228/228 pass, including all of `tests/test_graph.py`). |
| 2 | Roadmap SC2 | Configured markers identify candidates and exactly one is selected with redacted identity | ✓ VERIFIED | `vicmap_acquire/candidates.py` unchanged (zero diff since 01-14, confirmed by `git diff --stat`); `tests/test_candidates.py` (58 tests) and `tests/test_html_visibility_differential.py` (2000-doc fuzz, 0 leaks) both re-run directly and pass. |
| 3 | Roadmap SC3 | Selected message yields one artifact through the approved HTTPS host with redirect/timeout/size limits, bound to an authenticated origin | ✓ VERIFIED | `vicmap_acquire/origin.py` unchanged (zero diff); `download.py`'s pre-existing `download_artifact`/`_publish_artifact`/redirect-authorization logic unchanged — only new, additive functions were appended. `tests/test_download.py` (including the new `ProvenanceSidecarPostCommitTest`, which independently proves a post-commit sidecar failure never re-decides the already-published artifact) re-run directly and passes. |
| 4 | Roadmap SC4 | Completed download reports exact byte count and checksum | ✓ VERIFIED, reinforced | The original `artifact_finalized` event is still emitted unchanged; a new `artifact_verified` event (additive, same byte_count/sha256 fields, independently validated as a complete lowercase SHA-256 by `_HEX_64.fullmatch`) now also confirms it via the durable provenance sidecar. Independently re-hashed on disk: `sha256sum artifacts/Order_OK0VUZ.zip` reproduces the sidecar's and `01-LIVE-VERIFICATION.md`'s recorded digest exactly. |
| 5 | Plan 01 | Importing the CLI/package causes no auth, network, directory, or artifact side effect | ✓ VERIFIED | Unchanged; `tests/test_graph.py::ConfigurationTest::test_import_constructs_no_clients_and_creates_no_output` re-run, passes. |
| 6 | Plan 01 | Policy is fully validated pre-auth; credentials remain environment-only; tokens remain memory-only | ✓ VERIFIED | `load_config` now requires five sections instead of two but retains the identical pre-auth-validation, environment-only-credential, memory-only-token contract; no new section (`[extraction]`/`[discovery]`/`[database]`) carries a secret field (`vicmap.toml`'s own D-58 comment states this by design and `VICMAP_DB_PASSWORD` is read separately from the environment). `tests/test_graph.py::ConfigurationTest` (5 tests) re-run, passes. |
| 7 | Plan 01 | Tracer output contains only redacted identity/download evidence | ✓ VERIFIED | Unchanged; full suite regression-checked. |
| 8 | Plan 02 | App-only memory auth confirms exact mailbox without body/raw-provider output | ✓ VERIFIED | `graph.py` unchanged (zero diff); `GraphAuthenticationBoundaryTest` (5 tests) re-run, passes. |
| 9 | Plan 02 | One inclusive cutoff and four-field metadata query exhaust all pages without a count cap | ✓ VERIFIED | Unchanged; `GraphMetadataBoundaryTest` re-run, passes. |
| 10 | Plan 02 | Only header-qualified messages trigger MIME retrieval; scanning stays read-only, one connection-level GET per MIME fetch | ✓ VERIFIED | Unchanged; `GraphReadOnlyEnforcementTest` (4 tests) re-run, passes. |
| 11 | Plan 03 | Only exact sender/order/subject/MIME/link-cardinality matches become candidates | ✓ VERIFIED | `candidates.py` unchanged (zero diff); 58-test `CandidateRecognitionTest` suite re-run, passes. |
| 12 | Plan 03 | Complete-scan selection deterministically chooses one newest candidate and displays only a fingerprint | ✓ VERIFIED | Unchanged; `CandidateSelectionTest` (13 tests) re-run, passes. |
| 13 | Plan 03 | Empty/ambiguous/malformed/mismatched candidates fail closed | ✓ VERIFIED | Unchanged; re-run, passes. |
| 14 | Plan 04 | Every initial/redirect target is exact-host HTTPS and exact bucket/path prefix, validated before request | ✓ VERIFIED | Pre-existing `download_artifact`/redirect logic byte-for-byte unchanged (only new functions appended to the module); re-run, passes. |
| 15 | Plan 04 | Connect/read timeouts remain independent with no total-transfer deadline | ✓ VERIFIED | Unchanged; re-run, passes. |
| 16 | Plan 04 | Exact inclusive ceiling, persisted-byte count/hash, and atomic no-overwrite publication | ✓ VERIFIED, reinforced | `_publish_artifact` byte-for-byte unchanged; the new `write_provenance_sidecar` reuses its exact atomic-commit idiom and its own dedicated test (`ProvenanceSidecarPostCommitTest`) proves a sidecar-write failure never re-decides the already-committed artifact. `DownloadCommitPointTest` and the new test both re-run, pass. |
| 17 | Plan 04 | Every handled failure removes private partial state and returns one coherent closed result | ✓ VERIFIED | Unchanged; re-run, passes. |
| 18 | Plan 05 | CLI renders only one closed machine-readable success/progress/failure vocabulary | ✓ VERIFIED | The vocabulary was extended (new `Stage`/`ReasonCode` members for Phases 2/3, one new `artifact_verified` success kind) but remains closed — every new member is enumerated in `_FAILURE_POLICY`/the `SuccessEvent` classmethods, and `Phase3VocabularyTest::test_phase_3_reason_codes_extend_the_closed_vocabulary` (re-run, passes) pins that extension is deliberate and complete, not an open escape hatch. |
| 19 | Plan 05 | Exactly one selected candidate enters the downloader and no fallback occurs | ✓ VERIFIED | Unchanged; re-run, passes. |
| 20 | Plan 05 | A controlled live run proves one redacted authentic message-to-artifact transaction | ✓ VERIFIED | `01-LIVE-VERIFICATION.md` untouched since the 01-11 commit; independently re-verified in this pass by re-hashing the on-disk artifact and cross-checking against both the record and the (separately, Phase-2-authored) provenance sidecar — all three agree exactly. |
| 21 | Plan 05 | Live record safely records scope/runtime/disclosure attestations without prohibited source values | ✓ VERIFIED | Unchanged; not touched since 01-11. |

**Score:** 21/21 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `vicmap_acquire/candidates.py`, `vicmap_acquire/origin.py`, `vicmap_acquire/graph.py` | Pure recognition, authenticated-origin binding, read-only mailbox adapter | ✓ VERIFIED, unchanged | `git diff --stat 7dc124e HEAD` confirms zero lines changed in any of the three. |
| `vicmap_acquire/download.py` | Bounded, checksummed, atomically published artifact download | ✓ VERIFIED, extended additively | Pre-existing functions unchanged; new `ArtifactProvenance`/`write_provenance_sidecar`/`read_provenance_sidecar` reuse the same atomic-commit idiom and are covered by new, passing tests. |
| `vicmap_acquire/evidence.py` | Closed redacted event vocabulary | ✓ VERIFIED, extended additively with one tightening fix | New Phase 2/3 `Stage`/`ReasonCode` members are additive and enumerated; `_HOST` was tightened (WR-06), not loosened, and still accepts the real approved hostname. |
| `read_mailbox.py` | CLI orchestration, policy validation, closed acquisition contract | ✓ VERIFIED, extended additively | `run_acquisition`'s body is unchanged except two additive lines; new `run_provenance`/`--provenance-only` path is a separate, opt-in entry point that never calls `download_artifact` (proven by `test_provenance_only_writes_sidecar_and_never_calls_download_artifact`). |
| `tests/test_provenance.py` (new) | Regression coverage for the new provenance sidecar path | ✓ VERIFIED | 16 tests, all passing; covers round-trip fidelity, malformed-sidecar rejection, post-commit failure isolation, and the `--provenance-only` CLI routing. |
| `01-LIVE-VERIFICATION.md`, `artifacts/Order_OK0VUZ.zip`, `artifacts/Order_OK0VUZ.provenance.json` | Safe live proof of one authentic acquisition | ✓ VERIFIED | Independently re-hashed; artifact digest, sidecar digest, and the live-verification record's recorded digest agree exactly (`6a7868...411b`, 233089097 bytes). |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `read_mailbox.py::run_acquisition` | `vicmap_acquire/download.py::write_provenance_sidecar` | Called immediately after the pre-existing successful download, before the pre-existing `artifact_finalized` emit | ✓ WIRED | Confirmed by direct read of `read_mailbox.py` lines ~585-600; does not alter the download or finalization path it follows. |
| `read_mailbox.py::run_provenance` | `vicmap_acquire/candidates.py::recognize_candidate`/`select_candidate` | Identical selection path to `run_acquisition`, but never constructs a `DownloadPolicy` or calls `download_artifact` | ✓ WIRED, isolation proven | `tests/test_provenance.py::ProvenanceOnlyCliTest::test_provenance_only_writes_sidecar_and_never_calls_download_artifact` asserts this directly. |
| `vicmap_acquire/evidence.py::_HOST` | `SuccessEvent.download_target`, `_require_url_prefix`-adjacent validators | Tightened DNS-structured pattern still accepts the real approved hostname | ✓ WIRED | Confirmed by direct read; `s3.ap-southeast-2.amazonaws.com` matches the tightened pattern, and the full suite (which exercises `download_target` rendering against the real configured host) passes. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `download.py::write_provenance_sidecar` | `ArtifactProvenance` fields | Real streamed SHA-256/byte count from the completed download (`run_acquisition`) or a fresh streaming re-hash of the existing artifact (`run_provenance`) | Yes | ✓ FLOWING |
| `artifacts/Order_OK0VUZ.provenance.json` | `sha256`, `byte_count` | Independently re-derived via `sha256sum` against the real on-disk artifact in this verification pass | Yes — matches exactly | ✓ FLOWING / TRUSTED |
| (all other Phase 1 artifacts) | — | — | Unchanged from prior round | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full Phase 1 test-module suite (including the new provenance module) | `OPNIX_ENV_DISABLE=1 nix develop --impure --no-write-lock-file path:. --command python -m unittest tests.test_candidates tests.test_download tests.test_evidence tests.test_graph tests.test_origin tests.test_html_visibility_differential tests.test_repository_policy tests.test_provenance -v` | 228 tests, 0 failures, 0 skips | ✓ PASS |
| Scope of change since the prior verification's commit point | `git diff --stat 7dc124e HEAD -- vicmap_acquire/ read_mailbox.py tests/ vicmap.toml` | `origin.py`/`candidates.py`/`graph.py`: zero diff. `download.py`/`evidence.py`/`read_mailbox.py`/`vicmap.toml`/`test_graph.py`/`test_evidence.py`/`test_download.py`: additive only (confirmed by reading each diff in full). | ✓ PASS |
| Live artifact digest independently reproduced | `sha256sum artifacts/Order_OK0VUZ.zip` | `6a7868094ccab5b01fed11aec34587bd7e92bacdc35935b3c2835df21665411b` — matches sidecar and `01-LIVE-VERIFICATION.md` exactly | ✓ PASS |
| Provenance sidecar well-formed and consistent | `cat artifacts/Order_OK0VUZ.provenance.json` | `order_id=OK0VUZ`, `byte_count=233089097` (matches real file size), `sha256` matches the independently reproduced digest | ✓ PASS |
| No debt markers in the changed Phase 1 files | `grep -n -E "TBD\|FIXME\|XXX" read_mailbox.py vicmap_acquire/download.py vicmap_acquire/evidence.py vicmap.toml` | No matches | ✓ PASS |
| `artifacts/` (including the new `.provenance.json` sidecar) stays outside version control | `git status --ignored -- artifacts/` | Listed under "Ignored files"; working tree clean | ✓ PASS |

### Probe Execution

No probes declared for this phase; none found under `scripts/*/tests/probe-*.sh`. Skipped.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| MAIL-01 | 01-01, 01-02, 01-05, 01-09, 01-10, 01-11 | Authenticate/confirm configured mailbox without credential/body disclosure | ✓ SATISFIED | `graph.py` unchanged; full suite green; `REQUIREMENTS.md` marks `[x]` Complete. |
| MAIL-02 | 01-01–01-14 | Bounded Inbox scan and configured candidate recognition | ✓ SATISFIED | `candidates.py` unchanged since the 01-14 tree-based rewrite; `REQUIREMENTS.md` marks `[x]` Complete. |
| MAIL-03 | 01-01, 01-03, 01-05, 01-09, 01-11 | Deterministically select exactly one and show redacted identity | ✓ SATISFIED | Unchanged; `REQUIREMENTS.md` marks `[x]` Complete. |
| MAIL-04 | 01-01, 01-04, 01-05, 01-08 | Download one artifact only through approved bounded HTTPS | ✓ SATISFIED | Core download path unchanged; `REQUIREMENTS.md` marks `[x]` Complete. |
| MAIL-05 | 01-01, 01-04, 01-05, 01-09 | Show exact artifact byte count and checksum | ✓ SATISFIED, reinforced | Original `artifact_finalized` event unchanged; a durable provenance sidecar (Phase 2's D-32/D-28 work) now independently persists and reconfirms the same digest, verified against the real on-disk artifact in this pass. `REQUIREMENTS.md` marks `[x]` Complete. |

No orphaned requirements: `.planning/REQUIREMENTS.md`'s Traceability table maps all five MAIL-* IDs to Phase 1 with status `Complete`, and all five appear in at least one plan's `requirements` frontmatter.

## Prohibition Gate

| Prohibition | Automated evidence | Disposition |
|---|---|---|
| PROHIB-01 — no mailbox mutation | 4 named tests in `tests/test_graph.py::GraphReadOnlyEnforcementTest`, re-run in this pass | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward, regression-confirmed 2026-09-23) |
| PROHIB-02 — no Graph/ambient authority at artifact host | 2 named tests in `tests/test_download.py`, re-run | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward, regression-confirmed) |
| PROHIB-03 — no incomplete/failed/over-limit final publication | 8 named tests in `tests/test_download.py` plus the new `ProvenanceSidecarPostCommitTest`, re-run | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward, and newly reinforced by the post-commit-sidecar-failure isolation test) |
| PROHIB-04 — no substitution of an older/different order's artifact after failure | 1 named test in `tests/test_evidence.py`, re-run | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward, regression-confirmed) |
| PROHIB-05 — no automatic widening of the trust policy from a received message | 4 named tests plus `test_origin.py`'s unauthenticated-origin rejections, re-run | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward, regression-confirmed) |

## Anti-Patterns and Review Findings

| Finding | Status | Verdict |
|---|---|---|
| Prior round's RED-evidence quantitative discrepancy (370 vs. 24 leak-direction disagreements) | ✅ Recorded, non-blocking | Carried forward from the 2026-09-14 round; not touched by this round's file changes. |
| WR-02 (MSO conditional comments unconditionally suppressed) | ⚠ OPEN — not blocking | Unchanged, still explicitly deferred (availability-only, fail-closed). `candidates.py` had zero diff this round. |
| WR-03 (SafeFailure events never carry `order_id`/fingerprints) | ⚠ OPEN — not blocking | Unchanged, still explicitly deferred. |
| IN-01, IN-02 (informational) | ℹ OPEN | Unchanged. |

No unreferenced `TBD`, `FIXME`, or `XXX` debt markers were found in any file touched since the last Phase 1 commit.

## Disconfirmation Pass

- **The "unchanged" claims from the prior round were re-derived, not re-quoted.** `git diff --stat 7dc124e HEAD` was run directly against the four covered files that later phases' commits did touch (`read_mailbox.py`, `download.py`, `evidence.py`, `vicmap.toml`) and the three that stayed untouched (`origin.py`, `candidates.py`, `graph.py`), rather than trusting the prior VERIFICATION.md's regression-only framing for files that have since changed.
- **The additive framing was checked for hidden behavioral changes, not assumed from diff size alone.** Every diff hunk in `read_mailbox.py`, `download.py`, and `evidence.py` was read in full; the only semantic change to pre-existing logic found was the WR-06 `_HOST` tightening, which was checked against the real approved hostname to confirm it still matches.
- **The live artifact's continued integrity was independently re-measured, not read off the record.** `sha256sum artifacts/Order_OK0VUZ.zip` was run fresh in this session and cross-checked against both the 2026-09-09 `01-LIVE-VERIFICATION.md` record and the 2026-09-16 provenance sidecar — three independent sources agreeing exactly is stronger evidence than any one of them alone.
- **`git status --ignored` was checked directly**, not assumed, to confirm the new provenance sidecar (unlike the plan/summary/test files) never entered version control.

## Decision Coverage

Not independently re-derived line-by-line in this pass (non-blocking gate, consistent with prior rounds). Nothing found in this re-verification contradicts any tracked Phase 1 decision; the later-phase touch to Phase 1 files was itself decision-driven (D-32/D-28 provenance persistence, D-58 no-credential-in-config, WR-06 host-pattern alignment) and is documented in Phase 2/3's own review and summary artifacts, outside this phase's scope to re-audit.

## Human Verification Required

None. The live mailbox was not re-contacted in this verification pass (consistent with the prior round's posture); its continued validity is corroborated independently and strongly: the live artifact's digest was freshly recomputed from the file on disk and agrees exactly with both the 2026-09-09 live-run record and the independently-authored 2026-09-16 provenance sidecar.

## Gaps Summary

None. This re-verification was triggered by covered-file churn (four Phase 1 files were subsequently touched by Phase 2/Phase 3 plans), not by a reported defect. Direct diffing confirms the touch is additive to the trust-critical path (one new durable-provenance feature, one config-schema extension, one evidence-vocabulary extension, and one hostname-pattern tightening), the three most security-critical modules (`origin.py`, `candidates.py`, `graph.py`) have zero diff since the last Phase 1 commit, and the full 228-test regression suite for every Phase 1 test module — including the new provenance tests — passes. The phase goal remains achieved.

---

_Verified: 2026-09-23T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
