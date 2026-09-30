# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v0.1 — End-to-End Vicmap Import Proof

**Shipped:** 2026-09-30
**Phases:** 6 (1–5 + inserted 05.1) | **Plans:** 40 | **Tasks:** 97 | **Active days:** 17 of 31 (2026-08-31 → 2026-09-30)

### What Was Built

- Trusted Graph acquisition: DKIM/DMARC-bound sender trust, html5lib visibility-aware link recognition, per-hop authorized, bounded, SHA-256-verified download of the real order `OK0VUZ`
- Safe discovery: fail-closed extraction, oracle-confirmed layer profiling, deterministic naming, and an immutable digest-pinned manifest
- Validated PostGIS staging with capability-proving privilege preflight and blocking validation
- Single-transaction multi-layer publication into `vicmap`, reader access with write denial proven, a redacted EVID-01 summary, and the EVID-02 exit-code contract
- A resumable publish path via a durable in-transaction publication marker (05.1)

### What Worked

- **Independent oracles over hand-written tests.** The html5lib + 2000-document differential fuzz found 24 leaks the unit tests missed; `ogrinfo` and `pg_get_keywords()` played the same role in Phase 2.
- **Live verification as a gate.** Live runs caught real defects offline tests could not: three bugs in 03-04, including a transform guard GDAL silently ignored; tests green only because they never executed (03-05); and the WINDOWS #16 stranding.
- **Closed evidence vocabulary.** Every failure maps to a named stage and reason code, which made EVID-02 and the 05.1 boundary corrections tractable.
- **A WINDOWS.md ledger with evidence-backed closure.** Open debt stayed visible (13 → 4 → 3 open) instead of being implied resolved.

### What Was Inefficient

- **Phase 1 needed 9 gap-closure plans on top of 5 planned** (14 total). Several were self-inflicted regressions (01-07 introduced the void-element suppression bug that 01-12 fixed, and 01-13 fixed its CR-01/CR-02) before the counter approach was replaced outright in 01-14.
- **Phase 2 needed 3 gap-closure plans**, including `max_compression_ratio` being too tight for the real delivery. That should have been calibrated against the real artifact first.
- **Phase 4 shipped code-only**, with the one-way-door live promotion deferred to the operator. The post-commit failure mode (#16) surfaced live and needed an inserted phase.
- **Fingerprinted VERIFICATION.md digests go stale** whenever a later phase touches shared modules (`evidence.py`, `read_mailbox.py`, `vicmap.toml`). All four earlier phases had to be re-verified at milestone close.

### Patterns Established

- One CLI per phase boundary (acquire → `discover_order` → `stage_order` → `publish_order`), each composing fail-closed steps and emitting closed-vocabulary redacted events
- Durable handoff records between phases: provenance sidecar → manifest digest → `staging_validation` PASS row → `publication` marker
- Classify-before-DDL, and fail closed with no DDL on any state that cannot be proven
- Opt-in `Live*` test classes gated on DSN env vars, with the full suite run live before sign-off

### Key Lessons

1. Calibrate thresholds and parsers against the real delivery before hardening them, not after gap closure finds the mismatch.
2. When a hand-written fix keeps regressing (for example, the suppression counter), replace the approach with a real parser plus an independent oracle rather than patching further.
3. Don't mark a one-way-door phase complete code-only. Schedule the live run, and probe its post-commit failure modes, inside the phase.
4. Expect shared-module edits to stale earlier verification digests, and budget a re-verification pass at milestone close (or keep shared vocabulary out of per-phase `covered_files`).

### Cost Observations

- Model mix: not recorded (balanced profile; verifiers ran on sonnet)
- Sessions: not recorded
- Notable: the four close-out re-verifications ran in parallel in about 10 minutes and found no regressions

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Active days | Phases | Key Change |
|-----------|-------------|--------|------------|
| v0.1 | 17 | 6 | Live verification and differential oracles became the acceptance bar; WINDOWS.md ledger for deviations |

### Cumulative Quality

| Milestone | Tests | Skipped (live DSNs set) | Test LOC |
|-----------|-------|-------------------------|----------|
| v0.1 | 704 | 0 | ~18,300 |

### Top Lessons (Verified Across Milestones)

1. (Needs a second milestone to cross-validate.)
