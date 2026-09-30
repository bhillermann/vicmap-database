---
phase: 03
phase_name: "Validated PostGIS Staging"
project: "Vicmap Database"
generated: "2026-09-22"
counts:
  decisions: 7
  lessons: 8
  patterns: 6
  surprises: 5
missing_artifacts: []
---

# Phase 3 Learnings: Validated PostGIS Staging

The organising fact of this phase: **five defects shipped past a fully green test
suite, and every one surfaced only when something ran against the real server.**
Read the Lessons and Surprises together — they are one story told twice.

## Decisions

### Vendor the ICSM NTv2 grid by pinned hash rather than enable PROJ_NETWORK
D-50 named a `proj-data` package that does not exist at the pinned nixpkgs
revision, and PROJ 9.8.1 ships zero grid files. The operator chose
`vendor-fetchurl`: fetch the one ICSM GDA94→GDA2020 grid via `pkgs.fetchurl`
with a live-verified SHA-256.

**Rationale:** Offline after first `nix develop`, matches the existing
`python-o365` vendoring pattern, and adds no new runtime outbound host. The
rejected `proj-network` option would have made every load depend on reaching
`cdn.proj.org`, contradicting the project's pinned/offline posture.
**Source:** 03-01-SUMMARY.md (Task 2 checkpoint)

---

### Merge PROJ_DATA into one directory instead of colon-joining two
**Rationale:** With `PROJ_DATA="${proj}/share/proj:${gridDir}"` — two valid
directories — `pyproj.datadir.get_data_dir()` confirmed only the *first* was ever
consulted. A `pkgs.runCommand` step (`projDataDir`) now symlinks `proj`'s own
`share/proj` contents and the vendored grid under their real basenames into a
single directory.
**Source:** 03-01-SUMMARY.md (Deviation 2, Rule 3)

---

### Accept the published staging contract as already locked
`geom`/`gid` column names and a single `target_srid=7899`, baked into
`build_ogr2ogr_command`.

**Rationale:** 03-CONTEXT.md already recorded D-45/D-46/D-49 as decided by the
operator in discuss-phase. The executor proceeded on that basis and the operator
confirmed it retrospectively. Worth noting the process cost: this was a
`gate="blocking"` checkpoint that should have halted, and the confirmation was
sought *after* the code was written, not before.
**Source:** 03-04-SUMMARY.md (Task 1); operator confirmation during execution

---

### Grant the loader nothing; give it ownership instead
`vicmap_loader` owns `vicmap_staging` and `vicmap`. There is no `GRANT`
statement on either, and deliberately none on `public`.

**Rationale:** D-59/DB-05. Ownership is what confers `USAGE`/`CREATE`, so there
is nothing further to grant — and nothing to accidentally over-grant.
`preflight_staging_privileges` proves the weakness at runtime rather than
trusting the provisioning file to have been read.
**Source:** db/provision_vicmap_loader.sql; 03-04-SUMMARY.md (Task 3)

---

### Keep the test-only superuser DSN out of the shared devshell
`VICMAP_TEST_POSTGRES_SUPERUSER_DSN` is supplied per-shell by the operator via
`op read` references, and is deliberately **not** added to `flake.nix`'s
`opnixEnvConfig`.

**Rationale:** That config feeds every `nix develop`. A superuser entry there
would hand superuser access to every process in the devshell — directly
contradicting D-59/DB-05, the invariant this phase exists to establish. The
elevated credential lives only as long as the one shell that runs the test.
**Source:** 03-UAT.md (Option A)

---

### Record the provisioning gap rather than silently patch the script
`db/provision_vicmap_loader.sql` assumes the target database already exists.

**Rationale:** Adding `CREATE DATABASE` changes what the script assumes about
who runs it and in what order — an operator-facing provisioning-story decision,
not an in-scope auto-fix for a plan whose authorised scope was exactly the five
items D-59/DB-02 need.
**Source:** 03-04-SUMMARY.md ("Provisioning gap found, not fixed"); WINDOWS.md #4

---

### Do not force grid selection; leave it as an architectural decision
Neither `staging.py` nor `vicmap.toml` was changed to override PROJ's operation
choice, even after the behaviour was decisively confirmed.

**Rationale:** Forcing selection needs an explicit `-ct` pipeline override or a
stricter operation filter — a Rule 4 architectural decision, not an auto-fix.
Whether ~2 mm at one Melbourne point generalises across Victoria is a
spatial-data-quality judgment a human should weigh. Recorded as
`human_judgment: true`.
**Source:** 03-06-SUMMARY.md ("Grid Question — Settled, Not Left Open")

---

## Lessons

### `--config OGR_CT_ONLY_BEST` is not a real GDAL option
D-51's fail-closed transform posture was a **silent no-op** from the moment it
was written. `CPL_DEBUG=ON` printed `Warning 1: Unknown configuration option
'OGR_CT_ONLY_BEST'` and GDAL proceeded with its default selection. `strings` on
`libgdal.so.39` lists `ONLY_BEST`/`ALLOW_BALLPARK` only as sub-options of
`-ct_opt <NAME>=<VALUE>`, never as `--config` names.

**Context:** PROHIB-09's transparency requirement was never enforced by any load
this phase or 03-01's testing performed. Found only by running `ogr2ogr`
directly with debug output while investigating an unrelated question.
**Source:** 03-04-SUMMARY.md (Deviation 3, security-relevant)

---

### PostgreSQL rejects bind parameters in utility statements — learned twice
`SET statement_timeout = %s` and `CREATE ROLE ... LOGIN PASSWORD %s` both fail
with `syntax error at or near "$1"`. Utility statements are not DML. Both must
be composed with `psycopg.sql.Literal`.

**Context:** Fixed once in `staging._connect` (`616d50a`), then reintroduced in
`PrivilegePreflightTest.setUp` and fixed again (`ba3ef2b`). The codebase already
carried an assertion pinning this exact bug class for the implementation — and
the fixture reproduced it anyway, because the fixture had executed zero times.
**Source:** 03-04-SUMMARY.md (Deviation 1); commit ba3ef2b

---

### PostGIS `GeometryType()` does not append a `Z` suffix — only `M`
`GeometryType(ST_GeomFromText('POINT Z (1 1 1)'))` returns bare `'POINT'`. A
genuine XYZM point also returns `'POINT'`. Only the historically ambiguous XYM
case yields `'POINTM'`.

**Context:** This plan's own `<interfaces>` block asserted the opposite. A
literal implementation would have raised `GeometryTypeMismatch` on every
Z-dimensioned point layer — the exact common case the check exists to pass.
`ST_Zmflag` is the authoritative dimensionality signal, never the type name.
**Source:** 03-05-SUMMARY.md (Deviation 1)

---

### A test that passes by skipping is not coverage
Before 03-05, **zero** live-database tests had ever executed. They gated on
`VICMAP_TEST_POSTGRES_DSN`; unset, they fell back to a Unix socket that does not
exist on this host and skipped — while a correctly provisioned server was
reachable over TCP the entire time.

**Context:** Pointed at the real server, `LoadIntegrationTest` did not pass — it
*errored* with `permission denied for database vicmap`. It had never been
capable of passing against a correctly provisioned database.
**Source:** Orchestrator reproduction, recorded in 03-05-SUMMARY.md
("Live-Database Test Execution"); WINDOWS.md #5

---

### `pyproj.datadir` checks a build-time internal path before `PROJ_DATA`
The default `TransformerGroup` call always misreports a vendored grid as
unavailable, regardless of environment. `pyproj.datadir.set_data_dir()`, called
explicitly, bypasses the precedence bug.

**Context:** This invalidated 03-01's own verification method and made 03-04's
grid investigation inconclusive. The tool used to check the fact was broken in
the same direction as the fact being checked.
**Source:** 03-06-SUMMARY.md; WINDOWS.md #3 (now fixed)

---

### Real-world banner strings blow optimistic length bounds
`_SERVER_VERSION_TEXT` capped server version text at 200 characters. The real
`PostGIS_Full_Version()` output on this server is **345** — it enumerates
GEOS/PROJ/LIBXML/LIBJSON/LIBPROTOBUF/WAGYU versions plus PROJ's writable-directory
and database paths.

**Context:** The regex had never been checked against a real PostGIS server.
Widened to 1024 — still a finite cap satisfying D-61's anti-smuggling intent.
**Source:** 03-04-SUMMARY.md (Deviation 2)

---

### Treat a plan's `<interfaces>` block as a hypothesis, not a fact
Three separate plan-asserted API behaviours proved false against real tools: the
GDAL config-option syntax, the `GeometryType()` Z suffix, and the assumption
that fixing `PROJ_DATA` resolution would fix operation selection.

**Context:** Each was written confidently in a plan and each survived review.
Only execution against the real binary caught them.
**Source:** 03-04-SUMMARY.md; 03-05-SUMMARY.md; 03-06-SUMMARY.md

---

### The honest first step of provisioning was undocumented
The operator's first attempt failed with `FATAL: database "vicmap" does not
exist`. The script's usage comment says `-d <dbname>` and its first statement is
`CREATE ROLE`.

**Context:** A provisioning script that cannot run as documented is a
documentation defect even when every statement in it is correct.
**Source:** 03-04-SUMMARY.md; WINDOWS.md #4

---

## Patterns

### Differential oracle against the real binary
Pull the exact arguments the production code emits, run them through the real
installed tool, and assert on what the tool actually says.
`Ogr2ogrFlagOracleTest` runs `build_ogr2ogr_command`'s `-ct_opt` pair through
the real `ogr2ogr` with `CPL_DEBUG=ON` and asserts no "Unknown configuration
option" warning. `ValidationOgrinfoOracleTest` checks `validate_layer` against
`ogrinfo`.

**When to use:** Any time code encodes assumptions about an external tool's CLI
surface or output format. A hand-written test shares the code's blind spot; an
independent oracle does not.
**Source:** 03-04-SUMMARY.md; 03-05-SUMMARY.md

---

### Throwaway table in an owned schema, not a throwaway schema
`ValidationTest`, `ValidationOgrinfoOracleTest`, and `LoadIntegrationTest` all
create a uniquely-named table inside `vicmap_staging`, which `vicmap_loader`
already owns, instead of creating a schema — which would need privilege the
role deliberately lacks.

**When to use:** Whenever a test fixture reaches for elevated privilege. Ask
first whether the same isolation is achievable inside something the test subject
already owns. Weakening the privilege model to make a test pass inverts what the
test is for.
**Source:** 03-05-SUMMARY.md (Deviations 2 and 3)

---

### Pin the real observed value, not the value you expected
After the 345-character version string broke a 200-character bound, a test was
added pinning that exact observed string, and the old boundary test was updated
to assert against the new limit rather than silently continuing to test an
abandoned one.

**When to use:** After any real-world encounter invalidates an assumed bound.
Capture the specimen.
**Source:** 03-04-SUMMARY.md (Deviation 2)

---

### Credential by reference, scoped to one shell
No literal secret in anything typed. `op://` references resolve at point of use,
so the history file records paths, not values. `export` itself is not the
exposure — an env var is readable via `/proc/<pid>/environ` only by the same
user. The channels that leak are **argv** (`ps` reads it) and **the history
file** on disk.

**When to use:** Any elevated credential needed for a single operation. Prefer
it over adding the credential to shared environment config, which widens the
blast radius to every process in that environment.
**Source:** 03-UAT.md (credential handling)

---

### Broken-windows ledger separating "confirmed" from "remediated"
`WINDOWS.md` tracks each finding with an explicit status. #3 moved to `fixed`
when a working verification method was found; #2 stayed `open` and gained a new
evidenced entry (#7), because the behaviour was now *confirmed and root-caused*
but still not *changed*.

**When to use:** Whenever investigation resolves a question without resolving
the underlying issue. Collapsing those two states loses the distinction that
matters to whoever picks it up next.
**Source:** 03-06-SUMMARY.md; WINDOWS.md

---

### Assert the absence of the placeholder in composed SQL
`ConnectionSetupTest` mocks `psycopg.connect` and asserts the composed `SET`
statements carry no `%s`/`$1`. No database required.

**When to use:** For any SQL built by string composition where a bind parameter
would be silently wrong. Cheap, fast, and catches the whole bug class — though
note it only protects the code paths it is pointed at. It did not cover the test
fixture that later reproduced the same bug.
**Source:** 03-04-SUMMARY.md (Deviation 1)

---

## Surprises

### The grid was vendored, resolvable, and never used
The whole point of vendoring the ICSM grid was to make cross-datum transforms
grid-accurate. PROJ ranks the generic Helmert transform (**declared** 0.01 m)
above the actual measured ICSM distortion grid (**declared** 0.05 m) for this
CRS pair. `ONLY_BEST` picks by declared accuracy, not real-world fidelity.

**Impact:** 03-04's working hypothesis — that fixing the `PROJ_DATA` resolution
bug would fix selection — does not hold. The two are independent. Confirmed by
transforming a real ADDRESS coordinate through the exact flags the code emits
and matching `pyproj`'s Helmert result to four decimal places.
**Source:** 03-06-SUMMARY.md; WINDOWS.md #7

---

### The real-world cost of that was ~2 mm, not 0.5–1.5 m
03-01's research measured a `+0.52 m, +1.46 m` ballpark-fallback shift and
flagged it as the problem the grid would solve. The confirmed Helmert-vs-grid
difference at a real ADDRESS point is **~2 mm**.

**Impact:** Turns an apparent correctness emergency into a judgment call about
whether ~2 mm at one Melbourne point generalises across Victoria. The phase
deliberately did not survey that.
**Source:** 03-06-SUMMARY.md

---

### The privilege fixture had never run, and was broken
`PrivilegePreflightTest` — DB-02/DB-05's entire automated privilege proof — was
broken for as long as it existed. Its first ever execution produced five errors.

**Impact:** The verifier's refusal to round 4/5 up to 5/5 is what forced this
out. Had it accepted "the code exists and is correctly wired", the four
fail-closed branches would have shipped unexecuted.
**Source:** 03-VERIFICATION.md (first pass, `human_needed`); commit ba3ef2b

---

### A plan-specified class name would have silently deleted 26 tests
The plan named two new test classes `ManifestRoundTripTest`/`ManifestDigestTest`.
A class of the first name already existed with 26 methods. Python binds class
names in module-execution order, so the second definition would have rebound the
name and dropped all 26 from discovery — **with no error**.

**Impact:** A regression in `write_manifest` could have shipped undetected. The
failure mode is invisible: the suite still passes, it just tests less.
**Source:** 03-03-SUMMARY.md (Deviation 1)

---

### Five defects, one common property
A non-existent GDAL option; a bind parameter in a utility statement, twice; a
false `GeometryType()` assumption; live tests passing by skipping; a fixture
broken since birth. **Not one was visible to a passing test suite.**

**Impact:** The phase's real output is not just the staging boundary — it is the
demonstrated inadequacy of unit tests for anything that talks to an external
system. Every defect was found by running against the real server, and most were
found while investigating something else.
**Source:** 03-01 through 03-06 SUMMARY.md; 03-VERIFICATION.md
