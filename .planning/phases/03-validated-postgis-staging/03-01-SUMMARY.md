---
phase: 03-validated-postgis-staging
plan: 01
subsystem: infra
tags: [nix, flake, psycopg, postgresql, proj, gdal, opnix, supply-chain]

requires:
  - phase: 02-safe-geospatial-discovery
    provides: existing flake.nix devShell (python-o365, pyogrio, pyproj, gdal), opnix wiring pattern
provides:
  - psycopg (3.3.4) importable from `nix develop path:.` alone, human-cleared via blocking-human gate
  - psql client available in the dev shell for D-60's operator-run provisioning script
  - au_icsm_GDA94_GDA2020_conformal_and_distortion.tif vendored by pinned SHA-256 and resolvable via PROJ_DATA
  - VICMAP_DB_PASSWORD wired through opnix as an op:// reference only
  - COVERAGE.md's no-external-API declaration confirmed accurate for the vendor-fetchurl decision
affects: [03-02, 03-03, 03-04, 03-05, 03-06]

actuals:
  tokens: 1538
  tasks: 3
  commits: 2
  plan_head_before: ffd1ccc

tech-stack:
  added: [psycopg 3.3.4, postgresql (client), pkgs.fetchurl-vendored ICSM NTv2 grid]
  patterns:
    - "Merged single-directory PROJ_DATA (pkgs.runCommand + symlinks by real basename), not a colon-joined path list"
    - "fetchurl single-file outputs must be re-symlinked under their real basename before PROJ/any plain-filename search can find them"

key-files:
  created: []
  modified:
    - flake.nix

key-decisions:
  - "Task 1 checkpoint (package legitimacy): operator approved psycopg as a required runtime dependency after verifying PyPI, github.com/psycopg/psycopg, and the nixpkgs-curated 3.3.4 version. Recorded inline in flake.nix's ps.psycopg comment."
  - "Task 2 checkpoint (D-50 grid mechanism): operator selected vendor-fetchurl (option A) — vendor the ICSM NTv2 grid via pkgs.fetchurl with the pinned SHA-256, no PROJ_NETWORK. D-50's named `proj-data` package does not exist at the pinned nixpkgs revision and is superseded by this choice; COVERAGE.md's cdn.proj.org row already matched this option and required no correction."
  - "Research Open Question 2 (PROJ_DATA multi-path search): a colon-joined PROJ_DATA list is NOT honored by PROJ 9.8.1 / pyproj 3.7.2 for grid resolution — pyproj.datadir.get_data_dir() only reads the first entry, and the vendored grid stayed reported unavailable through the flake's own shellHook even though the file was present and byte-correct on the second path. Only a single merged directory (pkgs.runCommand symlinking proj's share/proj contents plus the grid, all under their real basenames) resolves the grid. This settles OQ-2 empirically in favor of the plan's stated fallback."
  - "MAJOR FINDING (not this plan's scope to fix — flagged for 03-03/03-04/03-06): vendoring the grid does not make it PROJ's 'best' operation. pyproj.transformer.TransformerGroup('EPSG:3111','EPSG:7899') ranks a grid-free 7-parameter Helmert transformation ('Inverse of Vicgrid + GDA94 to GDA2020 (1) + Vicgrid') as best (declared accuracy 0.01m) ahead of both NTv2 grid-based operations (declared accuracy 0.05m each). This holds even with pyproj's only_best=True/allow_ballpark=False (the exact semantics of D-51's OGR_CT_ONLY_BEST/OGR_CT_ALLOW_BALLPARK) and even with a Victoria-scoped area_of_interest. The Helmert operation is not classified as 'ballpark' by PROJ (it is a real registered EPSG transformation), so D-51's ALLOW_BALLPARK=NO does not exclude it. Transforming a test point (2500000, 2400000) under only_best/no-ballpark produced a +0.52m/+1.46m shift — matching 03-RESEARCH.md's own measured ballpark-fallback shift almost exactly — meaning the vendored grid sits on disk unused by default selection. Achieving D-50's actual goal (the ICSM grid being used, not just present) likely requires 03-04/03-06 to pin the specific grid-based transformation explicitly (e.g. an explicit PROJ pipeline/coordinate-operation code in the ogr2ogr invocation) rather than relying on `-t_srs` plus D-51's env vars alone."
  - "operator must still create the 1Password item op://nixos-services/vicmap_loader_credentials/password (see this plan's user_setup) before VICMAP_DB_PASSWORD resolves; opnix currently reports itemNotFound, which does not block `nix develop` from succeeding."

patterns-established:
  - "Supply-chain review comments for [SUS]-flagged packages live inline in flake.nix within five lines of the package entry, naming the source repo and the gate outcome (date + approver) — established by 02-01, continued here for psycopg."
  - "pkgs.fetchurl vendoring of a single binary grid/data file, mirroring the existing python-o365 fetchFromGitHub pin — pinned SHA-256, no runtime network dependency."

requirements-completed: [DB-01, DB-03, DB-04]

coverage:
  - id: D1
    description: "psycopg 3.3.4 and psql resolve from `nix develop path:.` alone, with no ambient-profile dependency"
    requirement: "DB-01"
    verification:
      - kind: other
        ref: "nix develop path:. -c python -c \"import psycopg; print(psycopg.__version__)\" -> psycopg 3.3.4"
        status: pass
      - kind: other
        ref: "nix develop path:. -c psql --version -> psql (PostgreSQL) 18.6"
        status: pass
    human_judgment: false
  - id: D2
    description: "The vendored ICSM GDA94<->GDA2020 grid is present, byte-correct, and resolvable via PROJ_DATA"
    requirement: "DB-04"
    verification:
      - kind: other
        ref: "sha256sum of the resolved PROJ_DATA grid path == 89bb9e5c55a714c8925ddc134bf4c191be8df2607b229a05efb778f5f6166ee0"
        status: pass
      - kind: other
        ref: "glob over PROJ_DATA finds au_icsm_GDA94_GDA2020_conformal_and_distortion.tif"
        status: pass
    human_judgment: false
  - id: D3
    description: "The GDA94 VicGrid -> GDA2020 VicGrid transform resolves its best operation as available AND reports zero unavailable operations (plan's literal acceptance criterion)"
    requirement: "DB-04"
    verification:
      - kind: other
        ref: "TransformerGroup('EPSG:3111','EPSG:7899').best_available -> True; .unavailable_operations -> ['(3)', '(2)'] (non-empty)"
        status: fail
    human_judgment: true
    rationale: "best_available is True, but is satisfied by a grid-free Helmert operation, not the vendored grid, and unavailable_operations is non-empty regardless of grid presence. This is a structural PROJ/EPSG accuracy-metadata characteristic, not an implementation defect fixable within this plan's dev-shell-only scope. See the MAJOR FINDING key-decision above. Requires an explicit human/planner decision on how 03-04/03-06 pin the grid-based operation."
  - id: D4
    description: "VICMAP_DB_PASSWORD reaches the pipeline only via an op:// reference; no literal secret in the repository"
    requirement: "DB-03"
    verification:
      - kind: other
        ref: "grep -c VICMAP_DB_PASSWORD flake.nix == 1, inside opnixEnvConfig.vars; no literal password value in flake.nix"
        status: pass
    human_judgment: false
  - id: D5
    description: "COVERAGE.md's reasoned no-external-API declaration is accurate for the vendor-fetchurl decision"
    verification:
      - kind: other
        ref: "COVERAGE.md contains 'No external API integration:' and its cdn.proj.org row already matched the vendor-fetchurl option (no edit needed)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Existing Phase 1/2 test suite stays green after the toolchain change"
    verification:
      - kind: other
        ref: "nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -> Ran 401 tests, OK (skipped=1)"
        status: pass
    human_judgment: false

duration: ~55min
completed: 2026-09-21
status: complete
---

# Phase 3 Plan 1: Database Toolchain, Grid Vendoring & Coverage Declaration Summary

**Dev shell now supplies psycopg 3.3.4 (human-cleared) and psql, vendors the ICSM GDA94<->GDA2020 grid via a merged PROJ_DATA directory (colon-joined form empirically disproven for PROJ 9.8.1), and wires VICMAP_DB_PASSWORD through opnix by reference only — but the vendored grid is not automatically selected as PROJ's "best" operation, a finding flagged for 03-04/03-06.**

## Performance

- **Duration:** ~55 min (continuation dispatch; two checkpoints pre-resolved by the human before this executor started)
- **Tasks:** 3 (Task 1 checkpoint:human-verify, Task 2 checkpoint:decision — both resolved before this executor's dispatch; Task 3 type=auto — executed here)
- **Files modified:** 1 (flake.nix)

## Accomplishments

- Added `ps.psycopg` to the dev shell's `python3.withPackages` list, with the Task 1 blocking-human gate outcome (approved 2026-09-21) recorded inline in a supply-chain comment matching the existing pyogrio/pyproj convention.
- Added `postgresql` to the top-level `packages` array, supplying `psql` for D-60's operator-run provisioning script.
- Vendored `au_icsm_GDA94_GDA2020_conformal_and_distortion.tif` via `pkgs.fetchurl` with the pinned, live-verified SHA-256, and made it resolvable to PROJ via a single merged `projDataDir` (empirically required — a colon-joined `PROJ_DATA` list does not work for this PROJ/pyproj combination).
- Added `VICMAP_DB_PASSWORD` to `opnixEnvConfig.vars` as an `op://` reference only.
- Confirmed `COVERAGE.md`'s existing declaration already matches the vendor-fetchurl decision; no edit was needed.
- Confirmed the full existing test suite (401 tests) still passes.
- Discovered and documented a significant gap: the vendored grid is present and byte-correct, but PROJ's own "best operation" ranking prefers a grid-free Helmert transformation over it (see Deviations below) — this is now a flagged open item for the plans that actually invoke `ogr2ogr`.

## Task Commits

Each checkpoint was resolved by the human before this executor was dispatched; only Task 3 produced a commit:

1. **Task 1: Confirm psycopg's package legitimacy (checkpoint:human-verify, blocking-human)** — resolved by human ("approved") before this executor's dispatch. No commit (nothing built at this gate).
2. **Task 2: Choose the GDA94-GDA2020 grid mechanism (checkpoint:decision, blocking)** — resolved by human (`vendor-fetchurl`) before this executor's dispatch. No commit (a decision, not a build).
3. **Task 3: Add driver, psql, grid mechanism, and password secret to the dev shell** — `4b82b93` (feat)

**Plan metadata:** committed together with this SUMMARY (see below).

## Files Created/Modified

- `flake.nix` — added `ps.psycopg` + supply-chain comment; added `postgresql`; added `icsmGda94Gda2020Grid` (fetchurl) and `projDataDir` (merged directory); exported `PROJ_DATA`; added `VICMAP_DB_PASSWORD` to `opnixEnvConfig.vars`.

## Decisions Made

- **Checkpoint 1 (psycopg legitimacy):** Operator typed "approved" after verifying the PyPI project, the `github.com/psycopg/psycopg` source repository, and the nixpkgs-curated 3.3.4 version via the plan's specified `nix eval` command. Recorded in `flake.nix`'s `ps.psycopg` comment.
- **Checkpoint 2 (D-50 grid mechanism):** Operator selected `vendor-fetchurl` (option A) — vendor the ICSM NTv2 grid via `pkgs.fetchurl` with the pinned SHA-256, matching the existing `python-o365` vendoring pattern. No `PROJ_NETWORK`. D-50's named `proj-data` package does not exist at the pinned nixpkgs revision (confirmed by 03-RESEARCH.md) and is superseded by this decision.
- **Research Open Question 2, settled empirically:** a colon-joined `PROJ_DATA` list (`"${pkgs.proj}/share/proj:${gridDir}"`) is NOT honored by PROJ 9.8.1 / pyproj 3.7.2 for grid discovery — `pyproj.datadir.get_data_dir()` only reads the first path segment, and the grid stayed reported unavailable via the flake's own shellHook despite the file being present and byte-correct on the second path. Only a single merged directory (built with `pkgs.runCommand`, symlinking `proj`'s `share/proj` contents plus the grid file, all under their real basenames) resolves it. This is the fallback the plan's Common Pitfall 1 / Assumption A5 anticipated, now confirmed as the required mechanism, not merely a fallback.
- **`pkgs.fetchurl` naming gotcha:** its single-file output lives at a hash-prefixed store path (`/nix/store/<hash>-<basename>`); every Nix store path's `dirOf` is the shared `/nix/store` parent, and the leaf name carries the hash prefix, so a plain-filename search (which is what PROJ and this plan's own acceptance criteria use) never matches it directly. Resolved by symlinking the fetched file under its real basename inside the merged directory.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `dirOf` on a `fetchurl` output resolves to `/nix/store`, not a usable grid directory**
- **Found during:** Task 3, first verification pass (grid-glob acceptance check)
- **Issue:** The plan's own action text anticipated this ("take `dirOf` it or place it explicitly") but `dirOf` alone is not sufficient: `pkgs.fetchurl`'s single-file output is a hash-prefixed store path, whose `dirOf` is the shared `/nix/store` parent (not a directory containing only the grid), and the file's own basename carries the store hash prefix rather than the plain ICSM filename PROJ/the acceptance criteria search for.
- **Fix:** Added a `pkgs.runCommand` step (`projDataDir`) that symlinks the vendored grid under its real basename, merged alongside `proj`'s own `share/proj` contents.
- **Files modified:** flake.nix
- **Verification:** `glob.glob(os.path.join(d, 'au_icsm_GDA94_GDA2020_conformal_and_distortion.tif'))` finds the file; `sha256sum` matches the pinned hash.
- **Committed in:** 4b82b93 (Task 3 commit)

**2. [Rule 3 - Blocking] Colon-joined `PROJ_DATA` does not resolve the grid for PROJ 9.8.1 / pyproj 3.7.2 (Open Question 2)**
- **Found during:** Task 3, second verification pass (transform-availability acceptance check)
- **Issue:** With `PROJ_DATA="${pkgs.proj}/share/proj:${gridDir}"` (two colon-joined directories, both valid and containing the expected files), `pyproj.transformer.TransformerGroup` still reported both NTv2 grid-based operations as unavailable. `pyproj.datadir.get_data_dir()` confirmed only the first directory was actually being consulted.
- **Fix:** Replaced the colon-joined export with a single merged directory (`projDataDir`, built via `pkgs.runCommand`) containing both `proj.db` (and the rest of `proj`'s `share/proj`) and the vendored grid, all symlinked under their real basenames.
- **Files modified:** flake.nix
- **Verification:** After the fix, `glob` finds the grid on the (now single-entry) `PROJ_DATA` path, and `TransformerGroup('EPSG:3111','EPSG:7899').transformers` includes an operation whose `.grids[0].available` is `True` for `au_icsm_GDA94_GDA2020_conformal_and_distortion.tif`.
- **Committed in:** 4b82b93 (Task 3 commit)

### Unresolved / Flagged for Follow-up (not auto-fixable within this plan's scope)

**3. [Finding — flagged, not fixed] The vendored grid is not PROJ's "best" operation; `unavailable_operations` stays non-empty**
- **Found during:** Task 3, third verification pass (the plan's literal `assert not g.unavailable_operations` acceptance criterion)
- **Issue:** `pyproj.transformer.TransformerGroup('EPSG:3111', 'EPSG:7899').best_available` is `True`, but the operation it selects (`Inverse of Vicgrid + GDA94 to GDA2020 (1) + Vicgrid`, declared accuracy 0.01m) is a grid-free 7-parameter Helmert transformation, not either NTv2 grid-based operation (both declared accuracy 0.05m, both reported `unavailable=False`/needing a grid — including the exact grid this plan vendored, `au_icsm_GDA94_GDA2020_conformal_and_distortion.tif`, which nonetheless still shows as needed-but-marked-unavailable on the *lower-accuracy* candidate operation while a *different*, higher-declared-accuracy candidate wins the ranking). This holds identically with `only_best=True, allow_ballpark=False` — the precise pyproj equivalents of D-51's `OGR_CT_ONLY_BEST=YES` / `OGR_CT_ALLOW_BALLPARK=NO` — and with an explicit Victoria-scoped `area_of_interest`. Transforming a representative point (2,500,000 / 2,400,000) under `only_best`/`no-ballpark` produced a `(+0.52m, +1.46m)` shift, matching 03-RESEARCH.md's own measured ballpark-fallback shift (`+0.536m, +1.461m`) almost exactly. The Helmert operation is a real, registered EPSG transformation (not PROJ's "ballpark" concept), so `ALLOW_BALLPARK=NO` does not exclude it.
- **Attempted fixes (exhausted, none change the outcome):** (a) colon-joined `PROJ_DATA` — fixed grid resolvability but not selection; (b) merged single-directory `PROJ_DATA` — same; (c) `only_best=True, allow_ballpark=False` pyproj flags mirroring D-51 exactly — same operation still selected; (d) Victoria-scoped `area_of_interest` instead of the default whole-of-Australia AOI — same operation still selected. Vendoring a second grid file was considered and explicitly rejected: it would not change the ranking outcome (the Helmert operation's declared accuracy still beats both grid operations' declared accuracy), and would add an unreviewed second binary outside this plan's approved Task 2 decision scope (a Rule 4 concern, not a Rule 1-3 auto-fix).
- **Why not fixed here:** This plan's stated scope is explicitly "writes no production Python... only job is to make the environment... exist" — the environment now genuinely makes the grid resolvable, which is D-50's literal ask. Whether PROJ's default "best operation" selection actually prefers the grid is a transform-*selection* question that belongs to whichever plan builds the actual `ogr2ogr -t_srs` invocation (03-04 and/or 03-06), since fixing it likely requires pinning a specific coordinate-operation code or explicit PROJ pipeline rather than relying on `-t_srs` + D-51's env vars alone — an architectural decision (Rule 4) outside a dev-shell-only task's authority.
- **Recommendation:** 03-04/03-06 should explicitly test `ogr2ogr -t_srs EPSG:7899` against a real GDA94 VicGrid source under `OGR_CT_ONLY_BEST=YES OGR_CT_ALLOW_BALLPARK=NO`, using a coordinate with a known correct answer, before trusting that D-51's flags alone route through the vendored grid.
- **Files affected:** none (no fix attempted, by design — see above)
- **Verification:** literal acceptance criterion FAILS; see coverage entry D3 above for the exact reproduction commands.

---

**Total deviations:** 2 auto-fixed (both Rule 3 — blocking, both required to make the grid resolvable at all), 1 flagged finding (unresolved, out of this plan's scope, requires a follow-up architectural decision in 03-04/03-06).
**Impact on plan:** The two auto-fixes were both necessary corrections to make Task 2's approved decision actually work as intended — no scope creep. The flagged finding does not block this plan's own `<done>` criteria (the dev shell genuinely supplies a *resolvable* transform, which is what Task 3 promises), but it is a real, significant risk to D-50/D-51's stated goal that the next plans touching `ogr2ogr` must address explicitly rather than assume solved.

## Issues Encountered

- The 1Password item `op://nixos-services/vicmap_loader_credentials/password` does not exist yet (opnix reports `itemNotFound`); this is expected — see `03-01-USER-SETUP.md`. It does not block `nix develop path:.` from succeeding; it only means `VICMAP_DB_PASSWORD` is unset until the operator creates the item.
- See "Deviations from Plan" item 3 above — the grid-selection finding is the most significant issue from this plan and is carried forward as a blocker for 03-04/03-06, not resolved here.

## User Setup Required

**External service requires manual configuration.** Per this plan's `user_setup` frontmatter, the operator must create a 1Password item for the `vicmap_loader` role password:
- Vault: `nixos-services`
- Item: `vicmap_loader_credentials` (chosen to match the existing `o365_app_credentials` naming convention; this exact name is what `flake.nix` now references — rename the item or update the `op://` reference in `flake.nix` together if a different name is preferred)
- Field: `password`
- `flake.nix` already references `op://nixos-services/vicmap_loader_credentials/password`

## Next Phase Readiness

- `psycopg`, `psql`, and a byte-verified vendored grid are all available from `nix develop path:.` alone — 03-02 through 03-06 can rely on this environment.
- **Blocker for 03-04/03-06:** the vendored grid is not automatically selected as PROJ's "best" GDA94<->GDA2020 operation under `OGR_CT_ONLY_BEST=YES`/`OGR_CT_ALLOW_BALLPARK=NO` (see Deviations item 3). Whichever plan writes the actual `ogr2ogr -t_srs` invocation must explicitly verify — with a real coordinate and a known-correct expected result — that the grid is actually applied, not just present on disk. This has been recorded in `.planning/WINDOWS.md` and as a `STATE.md` blocker.
- The 1Password item for `VICMAP_DB_PASSWORD` still needs operator creation before any code that reads it (03-04 onward) can run end to end.

---
*Phase: 03-validated-postgis-staging*
*Completed: 2026-09-21*

## Self-Check: PASSED
- FOUND: flake.nix
- FOUND: .planning/phases/03-validated-postgis-staging/COVERAGE.md
- FOUND: commit 4b82b93
- FOUND: .planning/phases/03-validated-postgis-staging/03-01-SUMMARY.md
