---
phase: "02"
slug: "safe-geospatial-discovery"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-14"
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
| **Estimated runtime** | ~30 seconds |

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
| {N}-01-01 | 01 | 1 | REQ-{XX} | T-{N}-01 / — | {expected secure behavior or "N/A"} | unit | `{command}` | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `flake.nix` — add `pyogrio`, `pyproj`, and `pkgs.gdal` to the devShell (hard blocker: no Phase 2 code runs inside `nix develop` without them)
- [ ] `tests/fixtures/` — pre-generated tiny synthetic OpenFileGDB fixtures (point layer, geometry-less table, 3D-point layer), built via `ogr2ogr` and checked in as small binary blobs
- [ ] `tests/test_extraction.py` — GEO-01 stubs, synthetic in-memory zip fixtures
- [ ] `tests/test_discovery.py` — GEO-02 / GEO-03 stubs
- [ ] `tests/test_discovery_differential.py` — GEO-03 independent-oracle test against `ogrinfo -json` (must not import implementation parsing helpers)
- [ ] `tests/test_naming.py` — GEO-04 stubs against a version-pinned PostgreSQL reserved-word snapshot
- [ ] `tests/test_manifest.py` — GEO-05 hard-stop-before-write stubs plus `manifest.json` sidecar-hash round-trip
- [ ] Framework install: none — `unittest` is stdlib

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| {behavior} | REQ-{XX} | {reason} | {steps} |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < {N}s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** {pending / approved YYYY-MM-DD}
