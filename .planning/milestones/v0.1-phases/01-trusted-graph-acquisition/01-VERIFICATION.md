---
phase: 01-trusted-graph-acquisition
verified: 2026-09-30T00:04:10Z
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
covered_digest: "v2:sha256:69880c48067bd1278423aaaa3643b5318fe3a2bbb990ae6ff81d3453e9a34ada"
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

# Phase 1: Trusted Graph Acquisition Verification Report (Re-verification — stale digest refresh before milestone v0.1 close)

**Phase Goal:** The operator can obtain exactly one authentic Vicmap order artifact from the automation mailbox without leaking sensitive content or trusting an unsafe download path.

**Verified:** 2026-09-30T00:04:10Z

**Status:** passed

**Re-verification:** Yes — superseding the 2026-09-23T00:00:00Z verification (`passed`, 21/21). `verification.status` reported that round `stale` because Phase 4 (`04-01`, `04-02`) and Phase 05.1 plans subsequently touched four of the phase's own covered files (`read_mailbox.py`, `vicmap.toml`, `vicmap_acquire/evidence.py`, `tests/test_evidence.py`) plus `.planning/REQUIREMENTS.md` and `.planning/ROADMAP.md`, to extend the evidence vocabulary and the `[database]` config contract for later phases. This round independently re-derives whether that touch broke any Phase 1 truth, then regenerates `covered_digest` via `verification.fingerprint`.

## Goal Achievement

**What changed since the prior round, verified by direct diff against the last-verified commit (`c2674e5`), not by SUMMARY narrative.** `git log c2674e5..HEAD` and `git diff --stat c2674e5 HEAD` confirm the touch is entirely additive, confined to Phase 3/4/05.1 concerns, and never reaches the trust-critical Phase 1 boundary:

- `vicmap_acquire/candidates.py`, `vicmap_acquire/origin.py`, `vicmap_acquire/graph.py`, `vicmap_acquire/download.py` — **zero diff**. `git diff --stat` against all four returns empty. The authenticated-origin binding, HTML-visibility recognition, Graph read-only boundary, and download/publication path are byte-for-byte unchanged since the 2026-09-23 verification.
- `read_mailbox.py` (+15/-8 lines) — additive, and confined entirely to the `[database]` section's `DatabaseRunConfig` (`_DATABASE_KEYS`, `reader_user` field, `validate_database_policy`, `load_database_config`). This is Phase 4's reader-role contract (D-72), not the `[mailbox]`/`[download]` sections MAIL-01–05 depend on. Read directly: the `[mailbox]` and `[download]` config-loading code (`load_config`, `_MAILBOX_KEYS`, `_DOWNLOAD_KEYS`) has no diff hunk touching it.
- `vicmap.toml` — one line appended (`reader_user = "vicmap_reader"` under `[database]`). Read directly (`sed -n '1,20p' vicmap.toml`): the `[mailbox]` and `[download]` sections are byte-for-byte unchanged from the prior verified state.
- `vicmap_acquire/evidence.py` (+182 lines) — purely additive: new `Stage`/`ReasonCode` members (`DB_AUDIT`, `DB_PUBLISH`, `DB_READER_VERIFY`, `PUBLICATION_SUMMARY`, and their reason codes) and two new classmethods (`SuccessEvent.publication_summary`, `ProgressEvent.publication_resumed`) plus a new `_require_utc_timestamp` helper, all serving Phase 4/05.1's publish/reader-verify/resume vocabulary. No existing Phase 1 `Stage`/`ReasonCode` member, existing classmethod body, or existing validator was modified or removed.
- `tests/test_evidence.py` (+325/-1 lines) — additive `Phase4VocabularyTest` class and an updated `expected` vocabulary-mapping dict in the pre-existing `EvidenceContractTest` (which the diff shows only *adds* new key/value pairs — no existing pair changed).
- `.planning/REQUIREMENTS.md` / `.planning/ROADMAP.md` — diffed directly; the MAIL-01 through MAIL-05 requirement text and the Phase 1 goal/success-criteria block are unchanged (`git diff c2674e5 HEAD -- .planning/REQUIREMENTS.md | grep MAIL-` returns nothing; the ROADMAP diff only flips later phases' `[ ]`→`[x]` checkboxes and adds a completion date to Phase 1's own already-`[x]` line).

**Independently confirmed, not just read.** The full workspace regression suite was run once directly in this pass: `python -m unittest discover -s tests` → **704 tests, 0 failures, 0 skips, OK** (matches the environment's stated baseline exactly). The Phase 1 test-module subset was also run directly and independently: `python -m unittest tests.test_candidates tests.test_download tests.test_evidence tests.test_graph tests.test_origin tests.test_html_visibility_differential tests.test_repository_policy tests.test_provenance -v` → **258 tests, 0 failures, OK**.

**The live artifact's continued integrity was independently re-measured, not read off the record.** `sha256sum artifacts/Order_OK0VUZ.zip` was run fresh in this session: `6a7868094ccab5b01fed11aec34587bd7e92bacdc35935b3c2835df21665411b`, 233089097 bytes — matching both the provenance sidecar (`artifacts/Order_OK0VUZ.provenance.json`) and `01-LIVE-VERIFICATION.md`'s recorded digest exactly, unchanged since the last two verification rounds. `git diff c2674e5 HEAD -- .planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md` returns empty — the live-proof record itself was not touched in this window.

### Observable Truths

| # | Source | Truth | Status | Evidence |
|---|---|---|---|---|
| 1 | Roadmap SC1 | Authenticate, confirm the configured mailbox, and inspect a bounded Inbox result without credential/body output | ✓ VERIFIED | `vicmap_acquire/graph.py` unchanged (zero diff since prior round); full suite regression-checked (704/704 pass, including all of `tests/test_graph.py`). |
| 2 | Roadmap SC2 | Configured markers identify candidates and exactly one is selected with redacted identity | ✓ VERIFIED | `vicmap_acquire/candidates.py` unchanged (zero diff, confirmed by `git diff --stat`); `tests/test_candidates.py` and `tests/test_html_visibility_differential.py` re-run directly, pass. |
| 3 | Roadmap SC3 | Selected message yields one artifact through the approved HTTPS host with redirect/timeout/size limits, bound to an authenticated origin | ✓ VERIFIED | `vicmap_acquire/origin.py` and `vicmap_acquire/download.py` unchanged (zero diff); `[download]` section of `vicmap.toml` byte-for-byte unchanged; `tests/test_download.py` re-run directly, passes. |
| 4 | Roadmap SC4 | Completed download reports exact byte count and checksum | ✓ VERIFIED | Original `artifact_finalized`/provenance-sidecar path unchanged; independently re-hashed on disk: `sha256sum artifacts/Order_OK0VUZ.zip` reproduces the sidecar's and `01-LIVE-VERIFICATION.md`'s recorded digest exactly. |
| 5 | Plan 01 | Importing the CLI/package causes no auth, network, directory, or artifact side effect | ✓ VERIFIED | Unchanged; `tests/test_graph.py::ConfigurationTest::test_import_constructs_no_clients_and_creates_no_output` re-run, passes. |
| 6 | Plan 01 | Policy is fully validated pre-auth; credentials remain environment-only; tokens remain memory-only | ✓ VERIFIED | `load_config`'s `[mailbox]`/`[download]` validation path is byte-for-byte unchanged. The only new `read_mailbox.py` diff is confined to `[database]` (`reader_user`), which carries no secret (`VICMAP_DB_PASSWORD` remains environment-only, read separately). `tests/test_graph.py::ConfigurationTest` (5 tests) re-run, passes. |
| 7 | Plan 01 | Tracer output contains only redacted identity/download evidence | ✓ VERIFIED | Unchanged; full suite regression-checked. |
| 8 | Plan 02 | App-only memory auth confirms exact mailbox without body/raw-provider output | ✓ VERIFIED | `graph.py` unchanged (zero diff); `GraphAuthenticationBoundaryTest` (5 tests) re-run, passes. |
| 9 | Plan 02 | One inclusive cutoff and four-field metadata query exhaust all pages without a count cap | ✓ VERIFIED | Unchanged; `GraphMetadataBoundaryTest` re-run, passes. |
| 10 | Plan 02 | Only header-qualified messages trigger MIME retrieval; scanning stays read-only, one connection-level GET per MIME fetch | ✓ VERIFIED | Unchanged; `GraphReadOnlyEnforcementTest` (4 tests) re-run, passes. |
| 11 | Plan 03 | Only exact sender/order/subject/MIME/link-cardinality matches become candidates | ✓ VERIFIED | `candidates.py` unchanged (zero diff); `CandidateRecognitionTest` suite re-run, passes. |
| 12 | Plan 03 | Complete-scan selection deterministically chooses one newest candidate and displays only a fingerprint | ✓ VERIFIED | Unchanged; `CandidateSelectionTest` (13 tests) re-run, passes. |
| 13 | Plan 03 | Empty/ambiguous/malformed/mismatched candidates fail closed | ✓ VERIFIED | Unchanged; re-run, passes. |
| 14 | Plan 04 | Every initial/redirect target is exact-host HTTPS and exact bucket/path prefix, validated before request | ✓ VERIFIED | `download.py` byte-for-byte unchanged; `allowed_hosts`/`allowed_url_prefixes` in `vicmap.toml`'s `[download]` section unchanged; re-run, passes. |
| 15 | Plan 04 | Connect/read timeouts remain independent with no total-transfer deadline | ✓ VERIFIED | Unchanged; re-run, passes. |
| 16 | Plan 04 | Exact inclusive ceiling, persisted-byte count/hash, and atomic no-overwrite publication | ✓ VERIFIED | `_publish_artifact`/`write_provenance_sidecar` byte-for-byte unchanged; `DownloadCommitPointTest` and `ProvenanceSidecarPostCommitTest` re-run, pass. |
| 17 | Plan 04 | Every handled failure removes private partial state and returns one coherent closed result | ✓ VERIFIED | Unchanged; re-run, passes. |
| 18 | Plan 05 | CLI renders only one closed machine-readable success/progress/failure vocabulary | ✓ VERIFIED | The vocabulary was extended again (new Phase 4/05.1 `Stage`/`ReasonCode` members, two new event classmethods) but remains closed — every new member is enumerated in `_FAILURE_POLICY`/the event classmethods, and `Phase4VocabularyTest::test_reason_stage_vocabulary_stays_total_after_the_extension` (re-run, passes) pins that extension is deliberate and complete, not an open escape hatch. |
| 19 | Plan 05 | Exactly one selected candidate enters the downloader and no fallback occurs | ✓ VERIFIED | Unchanged; re-run, passes. |
| 20 | Plan 05 | A controlled live run proves one redacted authentic message-to-artifact transaction | ✓ VERIFIED (live proof carried forward, not re-run) | `01-LIVE-VERIFICATION.md` untouched since the 01-11 commit (`git diff c2674e5 HEAD` on this file is empty); independently re-hashed on disk in this pass and cross-checked against both the record and the provenance sidecar — all three agree exactly. The real mailbox was not re-contacted; this human/live sign-off was obtained on 2026-09-09 and is preserved verbatim, per this round's instructions, rather than downgraded to human_needed. |
| 21 | Plan 05 | Live record safely records scope/runtime/disclosure attestations without prohibited source values | ✓ VERIFIED | Unchanged; not touched since 01-11. |

**Score:** 21/21 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `vicmap_acquire/candidates.py`, `vicmap_acquire/origin.py`, `vicmap_acquire/graph.py`, `vicmap_acquire/download.py` | Pure recognition, authenticated-origin binding, read-only mailbox adapter, bounded/checksummed download | ✓ VERIFIED, unchanged | `git diff --stat c2674e5 HEAD` on all four confirms zero lines changed. |
| `vicmap_acquire/evidence.py` | Closed redacted event vocabulary | ✓ VERIFIED, extended additively | New Phase 4/05.1 `Stage`/`ReasonCode` members and event classmethods are additive and fully enumerated; no existing member/body changed. |
| `read_mailbox.py` | CLI orchestration, policy validation, closed acquisition contract | ✓ VERIFIED, extended additively (confined to `[database]`) | The `[mailbox]`/`[download]`-facing code paths (`load_config`, `run_acquisition`, `run_provenance`) have no diff; the only new hunks are `DatabaseRunConfig`'s `reader_user` field and its validators, which is Phase 4's reader-role contract. |
| `vicmap.toml` | `[mailbox]`/`[download]` policy the MAIL-01–05 truths depend on | ✓ VERIFIED, unchanged | Read directly: byte-for-byte identical `[mailbox]`/`[download]` sections; the only diff is one new line under `[database]`. |
| `01-LIVE-VERIFICATION.md`, `artifacts/Order_OK0VUZ.zip`, `artifacts/Order_OK0VUZ.provenance.json` | Safe live proof of one authentic acquisition | ✓ VERIFIED, carried forward | Independently re-hashed; artifact digest, sidecar digest, and the live-verification record's recorded digest agree exactly (`6a7868...411b`, 233089097 bytes). Record file itself has zero diff since the last Phase 1 commit. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `read_mailbox.py::run_acquisition` | `vicmap_acquire/download.py::write_provenance_sidecar` | Called immediately after the pre-existing successful download, before the pre-existing `artifact_finalized` emit | ✓ WIRED | Unchanged since the 2026-09-23 round; not touched in this window. |
| `read_mailbox.py::load_config` | `vicmap.toml`'s `[mailbox]`/`[download]` sections | Pre-auth validation of the exact policy MAIL-01–05 depend on | ✓ WIRED, unchanged | Confirmed by direct diff: zero change to either the loader code or the two config sections. |
| `vicmap_acquire/evidence.py::Stage`/`ReasonCode` (Phase 4/05.1 additions) | `_FAILURE_POLICY` | Every new member is enumerated with a stage/hint pair | ✓ WIRED | `Phase4VocabularyTest::test_every_stage_is_reachable_from_at_least_one_reason` (re-run, passes) proves the extension stays total. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `artifacts/Order_OK0VUZ.zip` / `.provenance.json` | `sha256`, `byte_count` | Independently re-derived via `sha256sum` against the real on-disk artifact in this verification pass | Yes — matches exactly | ✓ FLOWING / TRUSTED |
| (all other Phase 1 artifacts) | — | — | Unchanged from prior round; zero diff on the four security-critical modules | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full workspace regression suite | `python -m unittest discover -s tests` | 704 tests, 0 failures, 0 skips, OK | ✓ PASS |
| Phase 1 test-module subset (independent, targeted run) | `python -m unittest tests.test_candidates tests.test_download tests.test_evidence tests.test_graph tests.test_origin tests.test_html_visibility_differential tests.test_repository_policy tests.test_provenance -v` | 258 tests, 0 failures, OK | ✓ PASS |
| Scope of change since the last verified commit | `git diff --stat c2674e5 HEAD -- vicmap_acquire/candidates.py vicmap_acquire/origin.py vicmap_acquire/graph.py vicmap_acquire/download.py` | Empty (zero diff on all four) | ✓ PASS |
| `[mailbox]`/`[download]` config sections unchanged | `sed -n '1,20p' vicmap.toml` (read directly, compared to prior verified state) | Byte-for-byte identical; only new line is under `[database]` | ✓ PASS |
| Live artifact digest independently reproduced | `sha256sum artifacts/Order_OK0VUZ.zip` | `6a7868094ccab5b01fed11aec34587bd7e92bacdc35935b3c2835df21665411b` — matches sidecar and `01-LIVE-VERIFICATION.md` exactly | ✓ PASS |
| No debt markers in the changed Phase 1 covered files | `grep -n -E "TBD\|FIXME\|XXX" read_mailbox.py vicmap_acquire/evidence.py vicmap.toml tests/test_evidence.py` | No matches | ✓ PASS |
| `artifacts/` (including the provenance sidecar) stays outside version control | `git status --ignored -- artifacts/` | Listed under "Ignored files"; working tree clean | ✓ PASS |

### Probe Execution

No probes declared for this phase; none found under `scripts/*/tests/probe-*.sh`. Skipped.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| MAIL-01 | 01-01, 01-02, 01-05, 01-09, 01-10, 01-11 | Authenticate/confirm configured mailbox without credential/body disclosure | ✓ SATISFIED | `graph.py` unchanged; full suite green; `REQUIREMENTS.md` MAIL-01 text unchanged since prior round, marked `[x]` Complete. |
| MAIL-02 | 01-01–01-14 | Bounded Inbox scan and configured candidate recognition | ✓ SATISFIED | `candidates.py` unchanged; `REQUIREMENTS.md` marks `[x]` Complete. |
| MAIL-03 | 01-01, 01-03, 01-05, 01-09, 01-11 | Deterministically select exactly one and show redacted identity | ✓ SATISFIED | Unchanged; `REQUIREMENTS.md` marks `[x]` Complete. |
| MAIL-04 | 01-01, 01-04, 01-05, 01-08 | Download one artifact only through approved bounded HTTPS | ✓ SATISFIED | Core download path and `[download]` config section unchanged; `REQUIREMENTS.md` marks `[x]` Complete. |
| MAIL-05 | 01-01, 01-04, 01-05, 01-09 | Show exact artifact byte count and checksum | ✓ SATISFIED | Provenance sidecar path unchanged, independently re-verified against the real on-disk artifact in this pass. `REQUIREMENTS.md` marks `[x]` Complete. |

No orphaned requirements: `.planning/REQUIREMENTS.md`'s Traceability table maps all five MAIL-* IDs to Phase 1 with status `Complete` (`git diff c2674e5 HEAD -- .planning/REQUIREMENTS.md | grep MAIL-` returns nothing — the requirement text and traceability rows are byte-for-byte unchanged), and all five appear in at least one plan's `requirements` frontmatter.

## Prohibition Gate

| Prohibition | Automated evidence | Disposition |
|---|---|---|
| PROHIB-01 — no mailbox mutation | 4 named tests in `tests/test_graph.py::GraphReadOnlyEnforcementTest`, re-run in this pass | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward, regression-confirmed 2026-09-30) |
| PROHIB-02 — no Graph/ambient authority at artifact host | 2 named tests in `tests/test_download.py`, re-run | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward, regression-confirmed) |
| PROHIB-03 — no incomplete/failed/over-limit final publication | 8 named tests in `tests/test_download.py` plus `ProvenanceSidecarPostCommitTest`, re-run | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward) |
| PROHIB-04 — no substitution of an older/different order's artifact after failure | 1 named test in `tests/test_evidence.py`, re-run | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward, regression-confirmed) |
| PROHIB-05 — no automatic widening of the trust policy from a received message | 4 named tests plus `test_origin.py`'s unauthenticated-origin rejections, re-run | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward, regression-confirmed) |

## Anti-Patterns and Review Findings

| Finding | Status | Verdict |
|---|---|---|
| Prior round's RED-evidence quantitative discrepancy (370 vs. 24 leak-direction disagreements) | ✅ Recorded, non-blocking | Carried forward from the 2026-09-14 round; not touched by this round's file changes. |
| WR-02 (MSO conditional comments unconditionally suppressed) | ⚠ OPEN — not blocking | Unchanged, still explicitly deferred (availability-only, fail-closed). `candidates.py` had zero diff this round. |
| WR-03 (SafeFailure events never carry `order_id`/fingerprints) | ⚠ OPEN — not blocking | Unchanged, still explicitly deferred. |
| IN-01, IN-02 (informational) | ℹ OPEN | Unchanged. |

No unreferenced `TBD`, `FIXME`, or `XXX` debt markers were found in the changed Phase 1 covered files (`read_mailbox.py`, `vicmap_acquire/evidence.py`, `vicmap.toml`, `tests/test_evidence.py`).

## Disconfirmation Pass

- **The "unchanged" claims were re-derived, not re-quoted.** `git diff --stat c2674e5 HEAD` was run directly against all six of Phase 1's implementation modules (`candidates.py`, `origin.py`, `graph.py`, `download.py`, `evidence.py`, plus `read_mailbox.py`) rather than trusting the prior VERIFICATION.md's framing.
- **The additive framing for `read_mailbox.py`/`vicmap.toml`/`evidence.py`/`test_evidence.py` was checked by reading every diff hunk in full**, not assumed from line-count alone. Every new hunk is confined to the `[database]` section, new `Stage`/`ReasonCode` members, or new test classes — none rewrites an existing Phase 1 code path.
- **The `[mailbox]`/`[download]` sections were read directly** (`sed -n '1,20p' vicmap.toml`) and confirmed byte-for-byte unchanged, rather than inferred from the diffstat alone.
- **The live artifact's continued integrity was independently re-measured, not read off the record.** `sha256sum artifacts/Order_OK0VUZ.zip` was run fresh in this session and cross-checked against both the 2026-09-09 `01-LIVE-VERIFICATION.md` record and the provenance sidecar — three independent sources agreeing exactly.
- **The full and Phase-1-scoped test suites were both re-run directly in this session** (704/704 and 258/258 respectively), not read off a prior SUMMARY.md's claimed count.
- **`.planning/REQUIREMENTS.md`'s MAIL-* text was diffed directly**, not assumed stable — `grep MAIL-` against the diff confirms no change to any of the five requirement descriptions or their traceability rows.

## Decision Coverage

Not independently re-derived line-by-line in this pass (non-blocking gate, consistent with prior rounds). Nothing found in this re-verification contradicts any tracked Phase 1 decision; the later-phase touch to Phase 1 files was itself decision-driven (D-72 reader-role contract, D-75/D-84/D-87/D-90/D-91 Phase 4/05.1 evidence-vocabulary extensions) and is documented in Phase 4/05.1's own review and summary artifacts, outside this phase's scope to re-audit.

## Human Verification Required

None. The live mailbox was not re-contacted in this verification pass (consistent with prior rounds' posture and this round's instruction to preserve, not re-run, existing live sign-offs). Its continued validity is corroborated independently and strongly: the live artifact's digest was freshly recomputed from the file on disk in this pass and agrees exactly with both the 2026-09-09 live-run record (`01-LIVE-VERIFICATION.md`) and the provenance sidecar. The PROHIB-01 through PROHIB-05 human sign-offs recorded by bhillermann@vegetationlink.com.au on 2026-09-14 are preserved verbatim above, per this round's instructions — not downgraded to human_needed.

## Gaps Summary

None. This re-verification was triggered by `verification.status` reporting `stale` — covered files (`read_mailbox.py`, `vicmap.toml`, `vicmap_acquire/evidence.py`, `tests/test_evidence.py`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`) were touched by Phase 4 and Phase 05.1 plans after the 2026-09-23 verification, not by any reported defect. Direct diffing against the last-verified commit (`c2674e5`) confirms the touch is entirely additive and confined to Phase 3/4/05.1's own `[database]`-config and evidence-vocabulary concerns: the four most security-critical Phase 1 modules (`candidates.py`, `origin.py`, `graph.py`, `download.py`) have zero diff, the `[mailbox]`/`[download]` config sections are byte-for-byte unchanged, the MAIL-01–05 requirement text is unchanged, and the full 704-test regression suite (plus a targeted 258-test Phase-1-module re-run) passes with zero failures and zero skips. The `covered_digest` has been regenerated via `verification.fingerprint` to reflect the current file states. The phase goal remains achieved.

---

_Verified: 2026-09-30T00:04:10Z_
_Verifier: Claude (gsd-verifier)_
