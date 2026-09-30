# Milestones

## v0.1 End-to-End Vicmap Import Proof (Shipped: 2026-09-30)

**Delivered:** One real Vicmap ready-order email (order `OK0VUZ`) processed end to end — mailbox → checksummed artifact → immutable manifest → validated PostGIS staging → atomic publication of `vicmap.vmadd_address` (4,222,035 rows) with reader access proven and a redacted EVID-01 summary.

**Phases completed:** 6 phases (1–5, plus inserted 05.1), 40 plans, 97 tasks

**Key accomplishments:**

1. **Trusted acquisition (Phase 1)** — Memory-only Graph auth, DKIM/DMARC/compauth-bound sender trust, html5lib visibility-aware link recognition (2000-document differential fuzz, 0 leaks), and a per-hop authorized, byte-bounded, SHA-256-verified download of the real 233,089,097-byte order archive.
2. **Safe discovery (Phase 2)** — Fail-closed extraction guard chain, pyogrio profiling confirmed against an independent `ogrinfo` oracle, deterministic PostgreSQL-safe target naming with collision hard stops, and an atomic, digest-pinned `manifest.json`.
3. **Validated staging (Phase 3)** — Privilege preflight that proves capability, isolated `vicmap_staging` loads with a fail-closed transform guard, blocking DB-04 validation (counts, SRID, geometry type, counted repair, extent), and post-validation PK/GiST indexing — `public` provably untouched.
4. **Atomic publication (Phase 4)** — A D-68 PASS gate and single-transaction multi-layer promotion (shared `xmin` proven live), rollback preserving prior tables, a real reader login proving discovery/spatial query/write denial, and the EVID-02 non-zero exit-code contract.
5. **Resumable publish (Phase 05.1)** — A durable `vicmap_audit.publication` marker written inside the promotion transaction lets a re-run resume a committed promotion (WINDOWS #16 fixed) and fail closed with no DDL on every ambiguous state.
6. **Legacy cleanup closed (Phase 5)** — Live catalog inspection confirmed no abandoned WFS tables remain after operator manual cleanup; deletion tooling deferred to EXT-03.

**Stats:**

- 296 commits, 2026-08-31 → 2026-09-30 (31 days); 209 files changed, +59,973 / −407
- ~27,300 lines Python/SQL (of which ~18,300 tests); 704 tests passing, 0 skipped (live DSNs set)
- Requirements: 27/27 satisfied (MAIL, GEO, DB, PUB, EVID, CLN)
- Git range: `75cf5b2` (docs: map existing codebase) → `v0.1`

**Closeout:** override_closeout — all 6 phases verified `passed` (Phases 01–04 re-verified 2026-09-30 after later phases staled their digests; no regressions).
Known verification overrides: 1 newly acknowledged, 0 carried forward from a prior close (see STATE.md Deferred Items) — `uat_gaps` 03/03-UAT.md, a scanner false positive (`status: passed`, 0 pending).
Phase 03 verification carries one PROHIB-09 override citing the 2026-09-21 grid-vs-Helmert decision (backlog 999.1).

**Tech debt carried forward:**

- WINDOWS #2/#7 — GDA94↔GDA2020 transform selects Helmert over the ICSM grid (~2 mm) → backlog 999.1
- WINDOWS #4 — `vicmap` database must be created manually before provisioning → backlog 999.2
- `vicmap.vmadd_address` predates the publication marker, so a re-run of `OK0VUZ` classifies UNPROVEN and fails closed (by design)
- IN-01 keyword oracle opt-in; IN-02 compression-ratio headroom ~1.44×; WR-02/WR-03 (Phase 1) deferred
- No reusable WFS inventory/approval/drop tooling (EXT-03)

**Archives:** [roadmap](milestones/v0.1-ROADMAP.md) · [requirements](milestones/v0.1-REQUIREMENTS.md) · [audit](milestones/v0.1-MILESTONE-AUDIT.md) · [phases](milestones/v0.1-phases/)

---
