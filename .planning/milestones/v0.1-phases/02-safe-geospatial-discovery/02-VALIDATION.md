---
phase: "02"
slug: "safe-geospatial-discovery"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-14"
validated: "2026-09-28"
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python stdlib `unittest` |
| **Config file** | none — `unittest discover` with default conventions |
| **Quick run command** | `nix develop path:. -c python -m unittest tests.test_<module> -v` |
| **Full suite command** | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` |
| **Estimated runtime** | ~30 seconds (per-module runs ≤ 7.5s) |

---

## Sampling Rate

- **After every task commit:** Run `nix develop path:. -c python -m unittest tests.test_<touched module> -v`
- **After every plan wave:** Run `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v`
- **Before `/gsd-verify-work`:** Full suite must be green, plus one opt-in live check against the real `artifacts/Order_OK0VUZ.zip`
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | GEO-02, GEO-03 | — | Reproducible GDAL/pyogrio toolchain; fixtures load | smoke | `python -m unittest tests.test_repository_policy -v` + fixture/`ogrinfo --version` probes | ✅ | ✅ green |
| 02-01-02 | 01 | 1 | GEO-04 | — | Naming contract decision (D-21) | checkpoint:decision | n/a — human decision, no code | n/a | ✅ decided |
| 02-01-03 | 01 | 1 | GEO-01..05 | — | One artifact → one immutable manifest end to end | tracer | `python -m unittest tests.test_discovery_tracer tests.test_evidence -v` | ✅ | ✅ green |
| 02-02-01 | 02 | 2 | GEO-01 | — | Durable Phase 1 fingerprint provenance sidecar | unit | `python -m unittest tests.test_provenance -v` | ✅ | ✅ green |
| 02-02-02 | 02 | 2 | GEO-01, GEO-02 | — | Ceilings/format allowlist reviewable and fail closed | unit | `python -m unittest tests.test_discovery_config -v` | ✅ | ✅ green |
| 02-03-01 | 03 | 2 | GEO-01 | — | Unsafe members rejected before any output handle opens | unit | `python -m unittest tests.test_extraction -v` | ✅ | ✅ green |
| 02-03-02 | 03 | 2 | GEO-01 | — | Real-byte ceilings, atomic run-dir publish, every member accounted | unit | `python -m unittest tests.test_extraction tests.test_discovery_tracer -v` | ✅ | ✅ green |
| 02-04-01 | 04 | 2 | GEO-02, GEO-05 | — | Dataset enumeration behind allowlist; empty delivery fails closed | unit | `python -m unittest tests.test_discovery -v` | ✅ | ✅ green |
| 02-04-02 | 04 | 2 | GEO-03, GEO-05 | — | Complete per-layer profile; every GEO-03/05 hard stop | unit | `python -m unittest tests.test_discovery -v` | ✅ | ✅ green |
| 02-04-03 | 04 | 2 | GEO-03 | — | Discovery matches independent `ogrinfo -json` oracle | differential | `python -m unittest tests.test_discovery_differential -v` | ✅ | ✅ green |
| 02-05-01 | 05 | 2 | GEO-04 | — | Strict D-21/D-22 normalization with keyword snapshot | unit | `python -m unittest tests.test_naming -v` | ✅ | ✅ green |
| 02-05-02 | 05 | 2 | GEO-04, GEO-05 | — | Same-delivery collisions detected; published table is not one | unit | `python -m unittest tests.test_naming -v` | ✅ | ✅ green |
| 02-06-01 | 06 | 3 | GEO-02..04 | — | Manifest contract + canonical hashable persistence | unit | `python -m unittest tests.test_manifest -v` | ✅ | ✅ green |
| 02-06-02 | 06 | 3 | GEO-05 | — | Every hard stop lands before anything is written; no DB/socket | unit | `python -m unittest tests.test_manifest -v` | ✅ | ✅ green |
| 02-06-03 | 06 | 3 | GEO-02, GEO-03 | — | Live proof against real Vicmap delivery | live integration | `python -m unittest tests.test_manifest.LiveDeliveryRegressionTest -v` | ✅ | ✅ green |
| 02-07-01 | 07 | 1 (gap) | GEO-05 | — | Real run under shipped config, no test-local ceiling override | tracer | `python -m unittest tests.test_manifest -v` | ✅ | ✅ green |
| 02-07-02 | 07 | 1 (gap) | GEO-05 | — | Calibration and threshold direction pinned | unit | `python -m unittest tests.test_discovery_config tests.test_extraction -v` | ✅ | ✅ green |
| 02-07-03 | 07 | 1 (gap) | GEO-02 | — | Extensions recognized in any letter case (WR-01) | unit + differential | `python -m unittest tests.test_discovery tests.test_discovery_differential -v` | ✅ | ✅ green |
| 02-08-01 | 08 | 1 (gap) | GEO-01 | — | Aliasing guard keyed on destination identity | tracer | `python -m unittest tests.test_extraction -v` | ✅ | ✅ green |
| 02-08-02 | 08 | 1 (gap) | GEO-01 | — | Filesystem as last oracle; provenance proven against disk | unit | `python -m unittest tests.test_extraction tests.test_discovery_tracer tests.test_manifest -v` | ✅ | ✅ green |
| 02-09-01 | 09 | 2 (gap) | GEO-05 | — | Partial manifest rolled back; retry succeeds | tracer | `python -m unittest tests.test_manifest -v` | ✅ | ✅ green |
| 02-09-02 | 09 | 2 (gap) | GEO-05 | — | Durable published dir entry; digest byte identity (WR-02) | unit | `python -m unittest tests.test_manifest -v` | ✅ | ✅ green |

All commands are prefixed with `nix develop path:. -c`.

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Requirement Coverage

| Requirement | Status | Tests |
|-------------|--------|-------|
| GEO-01 | COVERED | `test_extraction` (40), `test_provenance` (19), `test_discovery_config` (28) |
| GEO-02 | COVERED | `test_discovery` (30), `test_discovery_tracer` (4), `LiveDeliveryRegressionTest` |
| GEO-03 | COVERED | `test_discovery` (30), `test_discovery_differential` (4), `LiveDeliveryRegressionTest` |
| GEO-04 | COVERED | `test_naming` (41, 1 opt-in skip) |
| GEO-05 | COVERED | `test_manifest` (57), incl. `NoSocketNoDatabaseTest`, `ManifestRoundTripTest` |

---

## Wave 0 Requirements

- [x] `flake.nix` — `pyogrio`, `pyproj`, and `pkgs.gdal` in the devShell
- [x] `tests/fixtures/` — `Order_TRACER1.zip`, `geometryless_gdb.zip`, `point_z_gdb.zip` + `build_fixtures.py`
- [x] `tests/test_extraction.py` — GEO-01
- [x] `tests/test_discovery.py` — GEO-02 / GEO-03
- [x] `tests/test_discovery_differential.py` — GEO-03 independent oracle (imports only the public `discover_layers` entry point; runs its own `ogrinfo -json` subprocess)
- [x] `tests/test_naming.py` — GEO-04 against a version-pinned PostgreSQL reserved-word snapshot
- [x] `tests/test_manifest.py` — GEO-05 hard-stop-before-write + `manifest.json` sidecar-hash round-trip
- [x] Framework install: none — `unittest` is stdlib

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| IN-01 live keyword oracle: `_RESERVED_KEYWORDS` matches a live server's `pg_get_keywords()` | GEO-04 (advisory hardening) | Opt-in by design (D-23: no required live DB dependency). Needs a DSN with credentials; the loader password reaches processes only via the D-58 secret path, which isn't available to the plain test suite. Structural GEO-04 coverage does not depend on it. | `VICMAP_TEST_POSTGRES_DSN="host=127.0.0.1 port=5432 dbname=vicmap user=vicmap_loader password=…" nix develop path:. -c python -m unittest tests.test_naming.PostgresKeywordOracleTest -v` (expect `ok`, not `skipped`) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-28

---

## Validation Audit 2026-09-28

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

Evidence (live runs this session): full suite `OK (skipped=43)`; per-module `test_repository_policy` 5, `test_discovery_tracer` 4, `test_provenance` 19, `test_discovery_config` 28, `test_extraction` 40, `test_discovery` 30, `test_discovery_differential` 4, `test_naming` 41 (1 skip — IN-01 oracle, see Manual-Only), `test_manifest` 57 — all OK. `LiveDeliveryRegressionTest` not skipped (real delivery present).
