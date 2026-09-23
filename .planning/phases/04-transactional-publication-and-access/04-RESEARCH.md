# Phase 4: Transactional Publication and Access - Research

**Researched:** 2026-09-23
**Domain:** PostgreSQL/PostGIS transactional DDL, role-based read-only access, closed-vocabulary evidence
**Confidence:** MEDIUM-HIGH (backend-only phase over a codebase whose every convention is already established in Phases 1-3; the two open items are the live server's exact major version and this session's inability to run a live query against it)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

Decision numbering continues the project sequence (Phase 1 D-01-D-20, Phase 2 D-21-D-40, Phase 3 D-41-D-65).

**Promotion Mechanism (PUB-01, PUB-02)**

- **D-66:** Promotion is a **metadata move**, not a row copy. For each layer, `ALTER TABLE vicmap_staging.{table}_{run_ts} SET SCHEMA vicmap` then `ALTER TABLE vicmap.{table}_{run_ts} RENAME TO {table}`, with every layer's move inside **one transaction** so PUB-02's "all layers visible together in one short transaction" holds. No rows are recopied; D-63's PK on `gid`, typed `geometry(Point,7899)` column, GiST index, and `NOT NULL` are dependent objects that travel with the table. `CREATE TABLE AS SELECT` was rejected: it re-materializes 4.2M rows, transiently doubles storage (~975 MB), and rebuilds the constraints/indexes Phase 3 already built -- the same no-row-recopy reasoning as D-41. -- **Reversibility:** one-way -- `vicmap.{table}` and its column contract are what every downstream QGIS project and saved query bind to.
- **D-67:** Index and constraint names are **renamed to canonical** (`{table}_pkey`, `{table}_geom_idx`, and so on) as part of the publish transaction, so the live table carries predictable names rather than the run-timestamped names minted in staging (e.g. `vmadd_address_20260918t..._geom_idx`). Consistent with D-45/D-46 treating the live table as the published contract. **Planner note:** index/constraint names are schema-scoped unique, so the outgoing table and its indexes must be dropped (D-71) *before* the new canonical names are minted, or the rename collides.

**Publication Gate (PUB-01)**

- **D-68:** Only staging tables with a durable **PASS validation record** may be promoted. Phase 3 emits `LayerValidation` only as ephemeral JSON Lines events today -- the only file it writes to the run directory is the `ogr2ogr` stderr on failure -- so this record does **not exist yet**. This is a genuine cross-phase handoff gap, the same shape D-32 solved for provenance. Phase 4 reads the record and refuses to promote unless every manifest layer for the run is PASS. Re-running validation in Phase 4 was rejected (repeats the full 4.2M-row scan); trusting mere table presence + manifest digest was rejected (an implicit "it exists so it passed").
- **D-69:** The validation record is a **durable Postgres row**, not a filesystem sidecar. Its scope is deliberately **minimal -- a publication gate, not OPS-01's audit subsystem**: per staging run, the `run_ts`, the frozen manifest digest, and a per-layer verdict plus the D-56 metrics (row count, SRID, geometry type, repaired count). Nothing about mailbox state, idempotency, or history. This pulls a thin slice of durable audit ahead of OPS-01 by explicit operator choice. -- **Reversibility:** costly -- it is a real table that both the publish gate and the EVID-01 summary read; the minimal shape is chosen precisely so OPS-01 stays deferred and the table can grow later without rework here.
- **D-70:** The record lives in a **dedicated `vicmap_audit` schema**, created once by hand via the D-60 superuser provisioning script -- never in `vicmap` (it would clutter the reader-facing contract) and never in `vicmap_staging` (whose tables are per-run ephemeral). `vicmap_loader` is granted write on it. The DB-02-style preflight is extended to verify the schema exists and the loader holds the required privilege, failing closed and naming what is missing. Requires a **Phase 3 back-fill**: `stage_order.py` writes the validation row after `validate_layer`/`apply_post_validation_ddl`.

**Previous-Version Handling (PUB-03)**

- **D-71:** On a **successful** publish, the outgoing `vicmap.{table}` (the prior order's live table) is **dropped inside the same publish transaction** -- a single live generation, no `_previous` copy and no timestamped history, so storage does not grow per run and no retention policy is needed. PUB-03's failure case is satisfied *structurally*: the whole swap is one transaction, so a failed promotion rolls back and leaves the prior tables untouched. Keeping one `_previous` generation (post-commit manual rollback) and keeping timestamped history were both considered and rejected for v0.1 as extra storage plus deferred-hardening retention scope. -- **Reversibility:** reversible -- a retention scheme can be added later without changing the swap mechanism.

**Reader Role and Access (PUB-04, PUB-05)**

- **D-72:** The reader role is **provisioned once by hand** via the D-60 superuser script -- created with `LOGIN` and granted `USAGE ON SCHEMA vicmap` -- not by the pipeline. The loader never needs `CREATEROLE`: it owns the published tables (D-59) and can therefore `GRANT SELECT` on them to an already-existing reader. The DB-02-style preflight verifies the reader role exists with baseline `USAGE`. Consistent with D-59/D-60's operator-provisioned, least-privilege posture.
- **D-73:** `GRANT SELECT` to the reader on each promoted table is applied **inside the publish transaction**. Each publish creates a new table identity (OID), so name-based grants never carry over and must be re-applied every publish; doing it in-transaction means a reader never observes a window where the table exists in `vicmap` but is not yet selectable.
- **D-74:** PUB-05 is proven with a **real reader login**. The reader role has its own password from opnix (`VICMAP_READER_PASSWORD`, exactly as `VICMAP_DB_PASSWORD` per D-58). Verification opens a *fresh connection as the reader* and (a) discovers the published tables, (b) runs a representative spatial query, and (c) attempts a write that must be denied. This is also the realistic identity that GIS/QGIS consumers connect as. `SET ROLE` from the loader connection was rejected -- it proves role privileges rather than a real login, and would make the loader a member of the reader role. -- **Reversibility:** costly -- introduces a new secret plus 1Password/flake wiring; changing how PUB-05 is proven later means reworking the verification path and provisioning.

**Evidence and Summary (EVID-01, EVID-02)**

- **D-75:** EVID-01 is emitted **two ways**: a durable, redacted `summary.json` written to the run directory (the milestone's proof artifact) **and** a final summary event on the existing JSON Lines stream through `_EmitOnce` (operator visibility, house style). The file is the deliverable; the event fits the everything-is-an-event pattern.
- **D-76:** Phase 4 **assembles the summary by re-reading the durable per-phase artifacts** -- Phase 1's provenance sidecar (D-32), Phase 2's `manifest.json`, and Phase 3's new `vicmap_audit` validation record -- then adds its own publish and reader-verification facts. This mirrors how Phase 2 reads the provenance sidecar and Phase 3 reads the manifest; no growing record is threaded between phase invocations.
- **D-77:** Phase 4 adds a new **`publish_order.py`** entry point (promote + grant + verify + summary), preserving the one-CLI-per-phase architecture (`read_mailbox.py` -> `discover_order.py` -> `stage_order.py` -> `publish_order.py`). The operator runs the four CLIs in sequence (or a thin wrapper); no top-level end-to-end orchestrator is built -- that is OPS-05 deferred scope. EVID-02's exit-code contract follows Phases 1-3: any stage failure returns non-zero, names the failed boundary via `Stage`/`ReasonCode`, and exposes no secrets.

### Claude's Discretion

- The exact **representative spatial query** for PUB-05 -- planning toward a GiST-index-exercising `ST_Intersects`/`&&` predicate against a Victoria bounding box, plus table discovery via the catalog and a row/SELECT check.
- New `Stage` and `ReasonCode` members in `vicmap_acquire/evidence.py` for publication, grant, reader-verification, and validation-record-missing/failed boundaries.
- The exact schema and columns of the `vicmap_audit` validation-record table, provided it carries `run_ts`, the manifest digest, and the per-layer D-56 verdict + metrics.
- Whether the reader-role name is a new key in `vicmap.toml`'s `[database]` section or its own section; the exact 1Password item path for `VICMAP_READER_PASSWORD`.
- Module layout for the publish / grant / reader-verification code -- in `vicmap_acquire/` alongside `staging.py`, or a sibling module.
- The exact filename and format of the durable `summary.json` and the field shape of the final summary event.
- Whether the write-denial check uses an `INSERT` or `UPDATE`, and how the expected permission-denied result is mapped to a pass verdict.
- The `-gt`/transaction shape of the promotion DDL and whether grants and drops are issued per-layer or batched, provided the whole promotion remains one transaction.

### Deferred Ideas (OUT OF SCOPE)

- **Full OPS-01 durable audit subsystem.** `vicmap_audit` (D-69/D-70) is a minimal publication-gate slice only -- messages, orders, artifacts, and load-outcome history with idempotency remain out of scope for v0.1.
- **Idempotency / replay protection for a re-run publish (OPS-02).** Phase 4 assumes a clean prior state or fails closed; overlapping or repeated publishes are not made safe here.
- **Top-level end-to-end orchestrator / daily systemd run (OPS-05).** D-77 keeps the one-CLI-per-phase shape; a single command that runs Phases 1-4 is deferred.
- **Retaining previous published generations.** A `_previous` generation or timestamped published history plus its retention policy -- considered in D-71, rejected for v0.1.
- **Failed-staging age-based sweep (D-65 second half).** Still deferred, unchanged from Phase 3; Phase 4 only removes staging tables by moving successfully promoted ones out (D-66).
- **Extent sanity envelope.** Carried unchanged from Phase 3 -- a Victoria-shaped bounding box a published extent must fall inside; not blocking.
- **Auto-pruning old run directories.** Carried unchanged from Phase 2/3 -- ~975 MB per run, pruned manually.
- **Widening the format allowlist.** Carried unchanged -- shapefile/GeoPackage/MapInfo/DXF remain unsupported until a real delivery needs them.

None -- discussion stayed within phase scope (the deferred items above were surfaced as boundaries of the decisions taken, not as scope-creep requests).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PUB-01 | Operator can publish only fully validated staging tables into the dedicated `vicmap` schema | Pattern 1 (catalog-driven promotion) + "The gate read (D-68)" code example + `vicmap_audit` schema recommendation (Open Question 2) |
| PUB-02 | All layers from the selected order become visible together through a short transactional publication step, with no partial order publication | Pattern 2 (single-connection, single-transaction promotion) + system architecture diagram + Anti-Pattern on combining `SET SCHEMA`/`RENAME` |
| PUB-03 | Publication preserves the previous usable production tables if promotion fails | Pattern 2 (rollback-on-exception) + Don't Hand-Roll row on previous-version safety net + Pitfall 4 (scoped `DROP TABLE` vs PROHIB-10) |
| PUB-04 | A configured reader role receives schema `USAGE` and table `SELECT` privileges without receiving write privileges | Alternatives Considered (in-transaction `GRANT` vs `ALTER DEFAULT PRIVILEGES`) + Security Domain (V4 Access Control) |
| PUB-05 | Operator can verify table discovery, row access, and a representative spatial query while acting as the non-owner reader role | Pattern 3 (second independently-authenticated connection) + Pattern 4 (representative spatial query) + Pitfall 3 (EPSG:7899 extent) + Code Examples (reader-side table discovery) |
| EVID-01 | Operator receives a redacted summary connecting the selected message, artifact checksum, discovered layers, staging validation, published tables, and reader query | System architecture diagram (summary.json assembly step) + Sources this phase's `manifest.py`/`download.py` reads reuse |
| EVID-02 | Any failed stage returns a non-zero result and clearly identifies the failed boundary without exposing secrets | Evidence Vocabulary Extension (new `Stage`/`ReasonCode` members) + Validation Architecture EVID-02 test row |
</phase_requirements>

## Summary

Phase 4 is a pure extension of the pattern already proven in `vicmap_acquire/staging.py`: one policy dataclass, one driver-isolated module, typed closed failures, `sql.Composed`/`Identifier`/`Literal` everywhere, and per-function connections that commit once or roll back completely. Nothing here calls for a new library, a new framework, or a new architectural idea — the work is composing PostgreSQL's own transactional DDL (`ALTER TABLE ... SET SCHEMA`, `RENAME TO`, `RENAME CONSTRAINT`, `DROP TABLE`, `GRANT`) into one connection, one uncommitted transaction, one `commit()`, exactly as `apply_post_validation_ddl` already does for the DDL it applies today.

The one load-bearing technical risk this research resolves is name provenance: D-67 requires renaming the staging-time constraint/index names (which may be truncated-and-hashed by `_bounded_composed_identifier`, D-63) to canonical published names, but the *actual* current names must never be re-derived by string formatting — they must be read from `pg_constraint`/`pg_indexes` at promotion time, the same "read the catalog, never assume" discipline `apply_post_validation_ddl` already uses for Open Question 1 (geometry column typing). This matters more than it looks: PostgreSQL 18 changed `NOT NULL` from an untracked `pg_attribute` flag into a named `pg_constraint` row (release notes, confirmed below), so the exact set of objects D-67 must rename is version-dependent and must be discovered at runtime, not hardcoded from Phase 3's `apply_post_validation_ddl` source.

**Primary recommendation:** Build one new sibling module (`vicmap_acquire/publish.py`, driver-isolated exactly like `staging.py`) that (1) reads Phase 3's `vicmap_audit` PASS records for every manifest layer as a hard gate, (2) runs the entire promote-drop-rename-grant sequence for every layer inside one connection's one transaction, discovering constraint/index names from the catalog rather than assuming them, (3) opens a second, genuinely separate connection as the reader role to prove PUB-05, and (4) assembles `summary.json` by re-reading the durable artifacts of every prior phase, never threading a growing in-memory record between phases.

## Architectural Responsibility Map

This phase has no browser, SSR, or CDN tier — it is a backend batch CLI operating directly against PostgreSQL, identical in shape to Phases 1-3.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Publication gate (PASS record check) | Database / Storage | API / Backend | The gate's truth lives in a Postgres row (`vicmap_audit`); the CLI only reads and decides |
| Atomic multi-table promotion | Database / Storage | — | DDL transactionality is a database engine guarantee, not something the application layer can simulate |
| Reader grant issuance | Database / Storage | API / Backend | ACLs are database-native objects; the CLI only issues the `GRANT` statements inside the same transaction |
| Reader access verification | API / Backend | Database / Storage | The verifying "client" is this CLI opening a second connection under the reader's own credentials — there is no separate consumer tier in v0.1 |
| Redacted evidence assembly | API / Backend | — | Pure composition over already-durable artifacts (provenance sidecar, `manifest.json`, `vicmap_audit` rows); no new tier |
| CLI orchestration (`publish_order.py`) | API / Backend | — | Mirrors `stage_order.py`'s thin-entry-point shape |

## Standard Stack

### Core

No new runtime dependency is required. `psycopg` 3.3.4 is already the pinned, dev-shell-provided driver [VERIFIED: `python3 -c "import psycopg; print(psycopg.__version__)"` this session, matches Phase 3's operator-approved pin per STATE.md Phase 03 decisions log]. `ogrinfo`/GDAL 3.13.2 remains available as an independent oracle for cross-checking published row counts against the live table [VERIFIED: `ogrinfo --version` this session].

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | 3.3.4 | The only driver Phase 4's new module may import (D-41 extended) | Already the project's proven, operator-approved PostgreSQL driver — no reason to introduce a second one |

### Supporting

None — Phase 4 introduces no new third-party package. It extends `vicmap.toml`'s `[database]` section (reader-role name — Claude's discretion, see below) and adds one new environment variable (`VICMAP_READER_PASSWORD`, D-74) and one new 1Password item, following exactly `VICMAP_DB_PASSWORD`'s existing opnix wiring [VERIFIED: `flake.nix:20-32`, quoted: `{ name = "VICMAP_DB_PASSWORD"; reference = "op://nixos-services/vicmap_loader_credentials/password"; }`].

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Schema-move + rename (D-66) | `CREATE TABLE AS SELECT` re-materialization | Already rejected in CONTEXT.md D-66: doubles storage transiently (~975 MB) and rebuilds constraints/indexes Phase 3 already built |
| Postgres row for the validation gate (D-69) | Filesystem sidecar (Phase 1/2's pattern) | Already rejected in CONTEXT.md D-69: the gate and EVID-01 both need it queryable by `run_ts`/digest, and a sidecar can't be joined against inside the same transaction that reads it |
| In-transaction `GRANT` per publish (D-73) | `ALTER DEFAULT PRIVILEGES` set up once | Considered here: default privileges would auto-grant SELECT to every future table the loader creates in `vicmap`, removing the need to re-grant per publish. Rejected for this phase: D-73 already locked in-transaction grants specifically so a reader never observes a window where a table exists but is not yet selectable — `ALTER DEFAULT PRIVILEGES` grants at object-creation time, which is exactly what an in-transaction `GRANT` already achieves with narrower, more auditable scope (one statement per promoted table, visible in the same DDL block as the rename) |
| `SET ROLE` reader proof (D-74) | Real reader login with its own password | Already rejected in CONTEXT.md D-74: `SET ROLE` proves privilege bits, not a real, independently-authenticated connection, and would make the loader a member of the reader role |

**Installation:** None required — no `npm install`/`pip install` equivalent for this phase.

**Version verification:** `psycopg 3.3.4` confirmed present via `python3 -c "import psycopg; print(psycopg.__version__)"` this session, matching the project's existing pin (`flake.nix`, Phase 3 Task 1 checkpoint). No other package needs registry verification.

## Package Legitimacy Audit

Not applicable — this phase installs no new external package. `psycopg` is already vetted and pinned from Phase 3 (operator checkpoint approval recorded in STATE.md's Phase 03 decisions log). No `npm view`/`pip index versions` check is needed because nothing new is added to the dependency surface.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 manifest.json + Order_{id}.provenance.json      vicmap_audit.staging_validation
 (Phase 2/1 durable artifacts, run directory)     (Phase 3 backfill, durable Postgres row)
              |                                              |
              v                                              v
     +-----------------------------+          +--------------------------------+
     | publish_order.py            |--------->| Publication gate                |
     | (thin CLI, mirrors          |  reads    | every manifest layer must have  |
     | stage_order.py)             |  digest   | a PASS row for this run_ts +    |
     +-----------------------------+  match    | manifest digest, else hard stop |
              |                                 +--------------------------------+
              | on gate pass, one connection, one transaction
              v
     +--------------------------------------------------------------------+
     | Promotion transaction (per layer, all layers, one commit)          |
     |  1. discover current constraint/index names via pg_constraint/     |
     |     pg_indexes (never re-derive by string formatting)              |
     |  2. DROP TABLE vicmap.{table}          -- prior generation, if any |
     |  3. ALTER TABLE vicmap_staging.{staging_table} SET SCHEMA vicmap   |
     |  4. ALTER TABLE vicmap.{staging_table} RENAME TO {table}           |
     |  5. ALTER TABLE ... RENAME CONSTRAINT ... TO {table}_pkey (etc.)   |
     |  6. ALTER INDEX ... RENAME TO {table}_geom_idx (etc.)              |
     |  7. GRANT SELECT ON vicmap.{table} TO vicmap_reader                |
     +--------------------------------------------------------------------+
              |                                        | (any step fails)
     commit()  \                                        \ rollback() -- prior
              v                                           v  tables untouched (PUB-03)
     +--------------------------------------------------------------------+
     | Reader verification (D-74) -- a SECOND, genuinely separate         |
     | connection authenticated as vicmap_reader, own password             |
     |  a. discover tables (information_schema.tables, schema=vicmap)      |
     |  b. representative spatial query (&&/ST_Intersects, GiST-exercising)|
     |  c. attempted write -> must raise InsufficientPrivilege (42501)     |
     +--------------------------------------------------------------------+
              |
              v
     +--------------------------------------------------------------------+
     | summary.json (EVID-01) -- assembled by RE-READING durable artifacts:|
     | provenance sidecar + manifest.json + vicmap_audit rows + this run's |
     | own publish/grant/reader facts. Never threads a growing in-process  |
     | record between phase invocations (D-76).                            |
     +--------------------------------------------------------------------+
```

### Recommended Project Structure

```
vicmap_acquire/
├── staging.py          # unchanged Phase 3 boundary; gains ONE new function (record_validation)
├── publish.py           # NEW — sibling driver-isolated module (D-41 pattern extended)
│                         #   PublishPolicy, ReaderVerification, promotion, grant, reader-proof
├── evidence.py          # extended: 3 new Stage members, ~7 new ReasonCode members, PublicationSummary event
└── manifest.py          # unchanged — read_manifest/read_provenance_sidecar are D-76 inputs

publish_order.py          # NEW top-level CLI, mirrors stage_order.py's shape exactly

db/
└── provision_vicmap_loader.sql   # extended: vicmap_audit schema + table + grants, reader LOGIN role + USAGE

tests/
└── test_publish.py       # NEW, mirrors test_staging.py's _LivePostgresMixin pattern
```

**Module-layout decision needed (Claude's discretion per CONTEXT.md):** whichever choice is made, `tests/test_staging.py::DriverImportPolicyTest.test_staging_is_the_only_module_referencing_a_database_driver` **must** be touched. It currently hard-codes the single exemption `path.name == "staging.py"` [VERIFIED: `tests/test_staging.py:544-549`, quoted: `if path.name == "staging.py": continue` / `forbidden_tokens = ("psycopg", "psycopg2", "sqlalchemy", "asyncpg", "pg8000")`]. Two options, both viable:
- **(A) Same file:** add the publish/grant/verify functions directly to `staging.py`. No test change needed, but the file grows past its current 1,241 lines.
- **(B) Sibling module (recommended):** add `publish.py`, and widen the test's exemption to a small closed set, e.g. `{"staging.py", "publish.py"}`. This keeps Phase 3 and Phase 4 concerns separated (different lifecycle stage, different failure surface) while the structural "driver isolation" guarantee (WR/D-41's intent — a small, closed, reviewable set of driver-touching files, not scattered) still holds and is still tested.

Either way, this is a concrete, easy-to-miss task the plan must include explicitly — a naive "just add a new file that imports psycopg" will silently break an existing, currently-passing structural test.

### Pattern 1: Catalog-driven object renaming (never string-derive a DDL identifier that PostgreSQL itself may have already truncated or auto-named)

**What:** Before renaming any constraint or index, `SELECT` its current name from `pg_constraint`/`pg_indexes` keyed by the staging table's OID, exactly as `apply_post_validation_ddl` already reads `geometry_columns` rather than assuming GDAL created a typed column (Open Question 1, `vicmap_acquire/staging.py:974-985`).

**When to use:** Every promotion. Two reasons this is not optional:
1. `_bounded_composed_identifier` (`vicmap_acquire/staging.py:70-91`) truncates-and-hashes any staging-time identifier over 63 bytes, so the literal name in the database can differ from what a naive `f"{staging_table}_pkey"` reconstruction would produce for a long table/run-timestamp combination.
2. **PostgreSQL 18 stores `NOT NULL` as a named `pg_constraint` row** (`contype = 'n'`), unlike prior versions where it was only a `pg_attribute.attnotnull` flag with no catalog name to discover. Official release notes, quoted below. This means the *set* of objects D-67 must rename is version-dependent, not a fixed list of three names (PK, GiST index, secondary indexes) — it may also include an auto-named `NOT NULL` constraint on PostgreSQL 18+.

**Example (recommended shape, not existing code):**
```python
# Discover, never assume -- mirrors apply_post_validation_ddl's Open
# Question 1 resolution (staging.py:974-985).
cursor.execute(
    "SELECT conname, contype FROM pg_constraint "
    "WHERE conrelid = %s::regclass",
    (f"{staging_schema}.{staging_table}",),
)
constraints = cursor.fetchall()  # includes 'p' (primary key) and,
                                   # on PG18+, 'n' (NOT NULL) rows
cursor.execute(
    "SELECT indexname FROM pg_indexes "
    "WHERE schemaname = %s AND tablename = %s",
    (staging_schema, staging_table),
)
indexes = cursor.fetchall()
```

### Pattern 2: Single-connection, single-transaction promotion (mirrors `apply_post_validation_ddl`'s own shape)

**What:** One `psycopg.connect()` (no `autocommit=True`, matching `staging._connect`'s existing default), every DDL/DML statement for every layer executed in sequence, one `connection.commit()` at the very end, `connection.rollback()` on any exception.

**When to use:** The entire promote step (PUB-02's "one short transaction"). This is exactly `apply_post_validation_ddl`'s existing shape (`vicmap_acquire/staging.py:949-1125`), already proven in this codebase and already tested (`PostValidationDdlTest`).

### Pattern 3: A second, independently-authenticated connection for the reader proof

**What:** After the promotion transaction commits, open a *new* `psycopg.connect()` using `policy.reader_user`/`VICMAP_READER_PASSWORD` — not `SET ROLE` from the loader's connection (D-74 explicitly rejected `SET ROLE` because it proves privilege bits, not a real login, and would require the loader to hold membership in the reader role).

**Example — the write-denial check (recommended shape):**
```python
# INSERT DEFAULT VALUES is chosen over UPDATE: it needs no prior SELECT
# to find an existing row and is deterministic regardless of table
# contents. PostgreSQL's ACL check for a relation runs at executor
# startup (ExecCheckRTPerms, called from standard_ExecutorStart,
# before the plan tree is initialized) -- i.e. before any constraint,
# including NOT NULL, is ever evaluated -- so this reliably raises
# InsufficientPrivilege regardless of the target table's columns.
try:
    with reader_connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("INSERT INTO {table} DEFAULT VALUES").format(
                table=sql.Identifier(publish_schema, table_name)
            )
        )
except psycopg.errors.InsufficientPrivilege:
    reader_connection.rollback()
    write_denied = True
else:
    reader_connection.rollback()
    raise ReaderWriteNotDenied()  # security-critical: must hard-stop
```

### Pattern 4: Representative spatial query exercising the GiST index

**What:** A bounding-box predicate against Victoria's real extent, computed via `ST_Transform` from a WGS84 envelope rather than a hand-typed projected-meters literal (EPSG:7899's own advertised "projected bounds" are the CRS's full mathematical domain, not Victoria's actual extent — see Common Pitfall 3).

**Example:**
```python
cursor.execute(
    sql.SQL(
        "SELECT gid FROM {table} WHERE geom && "
        "ST_Transform(ST_MakeEnvelope(140.96, -39.2, 150.04, -33.98, 4326), %s) "
        "LIMIT 10"
    ).format(table=sql.Identifier(publish_schema, table_name)),
    (target_srid,),
)
```
Victoria's real WGS84 extent (140.96, -39.2, 150.04, -33.98) is [CITED: spatialreference.org/ref/epsg/7899/] — the same source's *other* rendering of "projected bounds" (easting -3,564,812 to 5,948,947 m) is the Lambert Conformal Conic's full valid mathematical domain, not Victoria's real footprint, and must not be used as the query envelope (see Pitfall 3).

### Anti-Patterns to Avoid

- **Combining `SET SCHEMA`/`RENAME` with other clauses in one `ALTER TABLE` statement:** PostgreSQL's own docs are explicit that `RENAME`, `SET SCHEMA`, `ATTACH PARTITION`, and `DETACH PARTITION` are the four forms that **cannot** be combined with other alterations in the same `ALTER TABLE` command [CITED: postgresql.org/docs/current/sql-altertable.html, quoted: "All the forms of `ALTER TABLE` that act on a single table, except `RENAME`, `SET SCHEMA`, `ATTACH PARTITION`, and `DETACH PARTITION` can be combined into a list of multiple alterations to be applied together."]. D-66 already anticipates this correctly (two separate statements) — the plan must not "optimize" this into one statement.
- **Re-deriving a DDL name by string formatting instead of reading the catalog** — see Pattern 1.
- **Granting via `ALTER DEFAULT PRIVILEGES` instead of in-transaction `GRANT`** — already rejected by D-73; see Alternatives Considered.
- **Using `has_table_privilege` to prove the write-denial check "the cheap way"** — this proves the ACL *bit*, not that a real query against a real table is actually rejected end-to-end. PUB-05 requires the real, executed proof (D-74's whole point).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic multi-table visibility | A custom "staging flag" column + application-level filtering | PostgreSQL's native transactional DDL (`BEGIN` ... `ALTER TABLE`/`GRANT` ... `COMMIT`) | The database already guarantees this; a hand-rolled visibility flag reintroduces exactly the partial-visibility window PUB-02 exists to prevent |
| Previous-version safety net | A custom `_previous` table-copy-and-swap scheme | The rollback-on-failure guarantee of the single transaction itself (D-71) | Already decided in CONTEXT.md: PUB-03 is satisfied structurally by the transaction boundary, not by extra copying |
| Reader access proof | Reading `pg_catalog`/`information_schema` grant metadata only | A real second connection, real login, real query, real attempted write (D-74) | Metadata-only checks (like `has_table_privilege`) prove the ACL bit is set, not that the whole access path actually works for a genuinely separate credential |
| Durable audit trail | A hand-rolled append-only JSON log for every publish | The `vicmap_audit` Postgres table (D-69/D-70) | A JSON log can't be queried transactionally as a promotion gate; the deliberately minimal Postgres row already solves exactly this and nothing more (explicitly not OPS-01's full audit subsystem) |

**Key insight:** Every "hand-roll" temptation in this phase is a worse reimplementation of something PostgreSQL's transaction/ACL model already provides for free. The engineering work is entirely in *composing* those primitives correctly (statement ordering, name discovery, connection separation) — not in building new abstractions.

## Runtime State Inventory

Not applicable — this is not a rename/refactor/migration phase. Phase 4 introduces new state (the `vicmap_audit` schema/table, the reader role) but does not rename or relocate any existing named entity; D-77 explicitly keeps the existing `stage_order.py`/`discover_order.py`/etc. naming scheme unchanged and only adds `publish_order.py` alongside it.

## Common Pitfalls

### Pitfall 1: Assuming the staging-time constraint/index names without reading the catalog

**What goes wrong:** A promotion that string-formats `f"{staging_table}_pkey"` etc. silently renames the wrong (non-existent) object, or fails outright, whenever `_bounded_composed_identifier` truncated the staging-time name (any staging table name + suffix combination over 63 bytes).
**Why it happens:** The staging-time code (`apply_post_validation_ddl`) already handles this correctly for its own purposes but only *returns* the names for evidence/reporting (`ddl_objects_created`) — that tuple is not documented or tested as an authoritative object inventory for a later renamer to consume.
**How to avoid:** Query `pg_constraint`/`pg_indexes` directly at promotion time (Pattern 1).
**Warning signs:** A promotion that works in tests against short fixture table names but fails against the real 4.2M-row `vmadd_address` delivery, whose staging table name (`vmadd_address_{run_ts}`) is close to the 63-byte edge once a longer `target_table` is involved.

### Pitfall 2: PostgreSQL 18's named `NOT NULL` constraints changing what D-67 must rename

**What goes wrong:** A promotion plan written against pre-18 assumptions (only PK + GiST + secondary indexes need renaming) silently leaves an auto-named `NOT NULL` constraint (e.g. a system-generated name like `{table}_geom_not_null`) uncanonicalized on PostgreSQL 18+, or — worse — a plan written *for* PG18 hard-codes a specific auto-generated name pattern that doesn't match what the server actually chose.
**Why it happens:** This is a genuinely new PostgreSQL 18 behavior. Release notes, quoted: "Store column `NOT NULL` specifications in `pg_constraint`" ... "This allows names to be specified for `NOT NULL` constraint" [CITED: postgresql.org/docs/18/release-18.html]. Prior to PG18, `ALTER TABLE ... ALTER COLUMN ... SET NOT NULL` created no catalog-visible named object at all.
**How to avoid:** Discover the actual constraint set from `pg_constraint` at promotion time (`contype IN ('p', 'n')`) rather than assuming a fixed three-object list; rename whatever is actually found.
**Warning signs:** This will not show up as a hard failure on a server where it doesn't apply (PG < 18 simply returns no `'n'`-type row, and the discovery loop naturally does nothing extra) — it will only surface as a genuinely uncanonicalized constraint name on a PG18+ server, which is easy to miss without an explicit assertion. **Version caveat (must be reconfirmed live, not assumed):** Phase 3's own live verification recorded the actual dev server as PostgreSQL 17.5/PostGIS 3.5.2 [VERIFIED: `vicmap_acquire/evidence.py:38-42`, quoted: "a real `PostGIS_Full_Version()` string on a live PostgreSQL 17.5/PostGIS 3.5.2 server observed during 03-04's live verification is 345 characters"], which would **not** exhibit this behavior. However, this session's own devshell ships `psql` client 18.6 [VERIFIED: `psql --version` this session, output `psql (PostgreSQL) 18.6`], and this research session's Bash tool was denied permission to materialize `VICMAP_DB_PASSWORD` to query the live server directly (sandbox "Credential Materialization" classifier), so the *current* server-side major version at execution time is **not independently confirmed by this research** and must be the first thing the executing plan checks (`SELECT version()`, which `read_database_identity` already surfaces for free at connection time).

### Pitfall 3: EPSG:7899's advertised "projected bounds" are not Victoria's extent

**What goes wrong:** Using the CRS's own advertised easting/northing bounds (roughly -3.56M to 5.95M easting, -1.03M to 5.79M northing) [CITED: epsg.io/7899] as the representative-query envelope produces a query that is technically valid but not "representative" of any real Victorian address — that range is the Lambert Conformal Conic projection's full mathematically valid domain (which the tool itself describes as extending toward "Victoria, New South Wales, Tasmania, and South Australia as a unified region"), not Victoria's actual footprint.
**Why it happens:** EPSG.io renders both a WGS84 bounding box and a much larger "projected bounds" figure for the same CRS entry, and the latter is easy to mistake for "the extent of the data" rather than "the mathematical domain of the projection."
**How to avoid:** Build the envelope from Victoria's real WGS84 extent (140.96, -39.2, 150.04, -33.98) [CITED: spatialreference.org/ref/epsg/7899/] and `ST_Transform` it into the target SRID at query time (Pattern 4), rather than hand-typing a projected-meters literal.
**Warning signs:** A spatial predicate that returns rows even against wildly wrong test data, or a `LIMIT 10` query that returns zero rows against the real ~4.2M-row ADDRESS table despite its rows genuinely covering Victoria.

### Pitfall 4: Treating "no destructive SQL" (PROHIB-10) as forbidding D-71's `DROP TABLE`

**What goes wrong:** A planner or reviewer over-reads PROHIB-10 and either omits D-71's required drop of the outgoing table, or flags it as a violation, stalling the plan.
**Why it happens:** PROHIB-10 (carried from Phases 1-3's "no destructive SQL" discipline) is about *unscoped* destructive operations — wildcards, `CASCADE`, operating on names not explicitly and individually approved. D-71's drop is the opposite: one exact, schema-qualified, single-target `DROP TABLE vicmap.{table}` inside the same transaction as its replacement, with no `CASCADE` and no pattern matching — structurally identical in discipline to Phase 5's CLN-04 ("no wildcards, no CASCADE").
**How to avoid:** State explicitly in the plan that this is the one deliberately-authorized destructive statement in Phase 4, scoped to exactly the single outgoing table name the promotion is about to replace, and that it must never accept a computed/wildcarded target.
**Warning signs:** A code review that either (a) removes the drop entirely, silently leaving stale generations accumulating (violating D-71's "single live generation" design) or (b) generalizes it into a loop over "all tables not in this run's set," which would be exactly the un-scoped destructive pattern Phase 5 exists to gate behind explicit approval.

### Pitfall 5: Forgetting the structural driver-isolation test when adding a new DB-touching module

**What goes wrong:** A new `publish.py` (or any new module) that `import psycopg` breaks `tests/test_staging.py::DriverImportPolicyTest` immediately and confusingly, because that test currently hard-codes `staging.py` as the *only* permitted exception.
**Why it happens:** See Recommended Project Structure above — the test was written before Phase 4 existed and has no reason to already know about a future module.
**How to avoid:** Decide up front (module-layout discretion item) and update the test's exemption set in the same commit that introduces the new import, never as an afterthought.
**Warning signs:** A confusing, unrelated-looking test failure (`DriverImportPolicyTest.test_staging_is_the_only_module_referencing_a_database_driver`) on a change that "should" only touch a new file.

## Code Examples

### The gate read (D-68) — recommended shape

```python
# One row per (run_ts, target_table) is expected; absence is a hard stop,
# never inferred as "not yet staged" vs "failed" -- both cases fail closed
# identically (D-68 explicitly rejected trusting table presence alone).
cursor.execute(
    "SELECT target_table, verdict FROM vicmap_audit.staging_validation "
    "WHERE run_ts = %s AND manifest_digest = %s",
    (manifest.run_timestamp, manifest_digest),
)
passed = {row[0] for row in cursor.fetchall() if row[1] == "pass"}
required = {layer.target_table for layer in manifest.layers}
if not required.issubset(passed):
    raise PublicationValidationMissing()
```

### Reader-side table discovery (PUB-05 part a)

```python
with reader_connection.cursor() as cursor:
    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s ORDER BY table_name",
        (publish_schema,),
    )
    discovered = [row[0] for row in cursor.fetchall()]
```
`information_schema.tables` only lists objects the connected role has at least one privilege on [CITED: postgresql.org/docs/current/ddl-priv.html — no privilege is granted to `PUBLIC` by default on tables, so an un-granted table is invisible to this query for the reader role], which makes this query itself a meaningful part of the PUB-05 proof, not just a listing convenience.

## State of the Art

| Old Approach (pre-Phase 4 thinking) | Current Approach (this research) | When Changed | Impact |
|--------------------------------------|-----------------------------------|---------------|--------|
| Assume `NOT NULL` is an untracked attribute flag with nothing to rename | Discover `pg_constraint` rows with `contype = 'n'` at promotion time | PostgreSQL 18 (2026 release) | D-67's rename set must be computed, not hard-coded, or a PG18+ server silently ends up with a non-canonical constraint name |

**Deprecated/outdated:** None specific to this phase's stack beyond the PG18 `NOT NULL` catalog change above.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The live dev PostgreSQL server's *current* major version (this session could not connect: Bash credential materialization was denied) | Common Pitfall 2, Environment Availability | If actually PG18+, the promotion code must rename an extra `NOT NULL` constraint object; if it assumes PG17-only, it silently leaves that object with a non-canonical name on a PG18+ server. Mitigated by design: Pattern 1's catalog-discovery approach is correct regardless of which version turns out to be true, provided the plan does not hardcode either assumption. |
| A2 | Recommended `vicmap_audit.staging_validation` table schema (columns beyond the D-69-required `run_ts`, manifest digest, per-layer verdict, D-56 metrics) | Don't Hand-Roll / architecture | Low — CONTEXT.md explicitly delegates the exact schema to Claude's discretion; any reasonable superset of the required fields satisfies D-69 |
| A3 | `INSERT INTO {table} DEFAULT VALUES` reliably raises `InsufficientPrivilege` before any `NOT NULL` constraint is evaluated, based on `ExecCheckRTPerms` running during executor startup before the plan tree is initialized | Pattern 3 | Sourced from PostgreSQL source-tree documentation/commit messages (execMain.c), not the user-facing SQL reference docs directly — high confidence but not a docs-page citation. Low risk: D-74 already requires a *live* proof of the write-denial as part of PUB-05's actual verification, so any discrepancy self-corrects at execution time rather than silently shipping wrong |
| A4 | Reader-role provisioning grants `USAGE ON SCHEMA vicmap` only, not `CREATE` (D-72 already states this) — carried forward without independent re-verification here | Standard Stack / Architecture | Already a locked CONTEXT.md decision (D-72), not newly assumed by this research |
| A5 | Recommended new `Stage`/`ReasonCode` enum member names (`DB_AUDIT`, `DB_PUBLISH`, `DB_READER_VERIFY`, `PUB_VALIDATION_MISSING`, `PUB_PROMOTION_FAILED`, `READER_ROLE_UNAVAILABLE`, `READER_VERIFICATION_FAILED`, `READER_WRITE_NOT_DENIED`, `DB_AUDIT_PRIVILEGE_DENIED`, `DB_AUDIT_RECORD_FAILED`) | Evidence Vocabulary Extension (below) | CONTEXT.md explicitly delegates exact naming to Claude's discretion; low risk, purely a naming/taxonomy choice the planner can freely adjust |

## Open Questions

1. **Does the live dev server's current PostgreSQL major version support named `NOT NULL` constraints (PG18+), or is it still the PG17.5 Phase 3 last verified?**
   - What we know: Phase 3's live verification (03-04) recorded PostgreSQL 17.5/PostGIS 3.5.2 [VERIFIED: `vicmap_acquire/evidence.py:38-42`]. This session's devshell ships a newer `psql` client (18.6) [VERIFIED this session].
   - What's unclear: Whether the actual running server (a Docker container observed reachable at `127.0.0.1:5432` this session, image `postgis/postgis:latest`, up ~27h) is the same instance Phase 3 verified, or has since been recreated/upgraded — this session's Bash tool was denied permission to read `VICMAP_DB_PASSWORD` to check directly.
   - Recommendation: Make `SELECT version()` (already surfaced by `read_database_identity`) the first live action of the executing plan, and make the promotion code's object-discovery (Pattern 1) version-agnostic so the answer doesn't need to be known in advance.

2. **Exact `vicmap_audit.staging_validation` schema and whether `vicmap_loader` should own the table (broader `CREATE`) or only hold `SELECT`+`INSERT` on a superuser-created table.**
   - What we know: D-70 requires the schema created by hand by a superuser and `vicmap_loader` "granted write on it." D-59's existing pattern for `vicmap_staging`/`vicmap` is full schema ownership.
   - What's unclear: Whether audit should follow the same ownership model or the tighter least-privilege model (table pre-created by the provisioning script, loader granted only `SELECT`+`INSERT` on that one table, no `CREATE` on the schema).
   - Recommendation: The tighter model — it is more consistent with D-72's stated "operator-provisioned, least-privilege posture" for the reader role, and the audit table's structure should not change without an operator decision anyway (unlike per-run staging tables, which the loader legitimately creates dynamically).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL server | Everything in this phase | Yes (reachable) | Unconfirmed this session — client is `psql 18.6`; last live-verified server was `17.5`/PostGIS `3.5.2` (Phase 3) | The executing plan's first live task must run `SELECT version(), PostGIS_Full_Version()` |
| PostGIS extension | Spatial validation/query | Presumed present (loaded in every prior phase) | 3.5.2 last verified (Phase 3) | — |
| psycopg | All new DB code | Yes | 3.3.4 [VERIFIED this session] | — |
| ogrinfo / GDAL | Independent oracle for cross-checking published data | Yes | 3.13.2 [VERIFIED this session] | — |
| `VICMAP_DB_PASSWORD` (opnix/1Password) | Loader connection | Present in `.envrc`/`flake.nix` wiring, but **this research session's Bash tool was denied permission to materialize it** (sandbox "Credential Materialization" classifier) | — | Not a phase blocker — this is a research-session sandbox restriction, not a missing project dependency; the executing environment (`/gsd-execute-phase`) is expected to have normal opnix access, as Phase 3 already proved live |
| `VICMAP_READER_PASSWORD` (new, D-74) | Reader-role live proof | Does not exist yet | — | Must be created (1Password item + `flake.nix`/`.envrc` wiring + `db/provision_vicmap_loader.sql` reader role) as part of this phase's user-setup, mirroring `VICMAP_DB_PASSWORD` exactly |
| `VICMAP_TEST_POSTGRES_SUPERUSER_DSN` | Test-only superuser fixture setup (e.g. creating `vicmap_audit`/reader role for tests) | Established during Phase 3 (WINDOWS.md #6, now `fixed`) — a real superuser test credential exists on the dev server | — | Reuse directly; do not re-provision |

**Missing dependencies with no fallback:** None that block *planning* — the one genuinely new thing (`VICMAP_READER_PASSWORD`) is expected new user-setup work, already anticipated by D-74/D-72.

**Missing dependencies with fallback:** Server version confirmation (fallback: confirm live as the first task, design code version-agnostically).

## Evidence Vocabulary Extension (Claude's Discretion)

CONTEXT.md explicitly delegates new `Stage`/`ReasonCode` members to this research. Recommended additions to `vicmap_acquire/evidence.py`, appended after the existing `DB_STAGING_DDL`/`DB_STAGING_DDL_FAILED` pair in pipeline order [existing enum VERIFIED: `vicmap_acquire/evidence.py:67-134`]:

**New `Stage` members:**
- `DB_AUDIT = "db_audit"` — covers both the Phase 3 backfill write and the Phase 4 gate read against `vicmap_audit`
- `DB_PUBLISH = "db_publish"` — the single promote-drop-rename-grant transaction
- `DB_READER_VERIFY = "db_reader_verify"` — the post-commit reader-role proof

**New `ReasonCode` members** (each needs a `(Stage, hint)` entry in `_FAILURE_POLICY`, mirroring the existing table's shape exactly):

| ReasonCode | Stage | Meaning |
|---|---|---|
| `DB_AUDIT_PRIVILEGE_DENIED` | `DB_AUDIT` | Preflight: `vicmap_audit` schema/table missing, or loader lacks required privilege on it |
| `DB_AUDIT_RECORD_FAILED` | `DB_AUDIT` | The Phase 3 backfill write itself failed (unrelated to validation correctness) |
| `PUB_VALIDATION_MISSING` | `DB_AUDIT` | Gate failure: at least one manifest layer has no matching PASS row for this `run_ts`/digest |
| `PUB_PROMOTION_FAILED` | `DB_PUBLISH` | Any failure inside the one promote/drop/rename/grant transaction (DDL error, name-discovery mismatch, grant failure) |
| `READER_ROLE_UNAVAILABLE` | `DB_READER_VERIFY` | Preflight: reader role missing, lacks baseline `USAGE`, or `VICMAP_READER_PASSWORD` unset |
| `READER_VERIFICATION_FAILED` | `DB_READER_VERIFY` | The discovery or spatial-query leg of PUB-05 itself failed |
| `READER_WRITE_NOT_DENIED` | `DB_READER_VERIFY` | **Security-critical**: the reader's attempted write was *not* rejected — the grant model is broken; this must hard-stop with the most urgent remediation hint in the table, not a routine retry hint |

This widens the vocabulary from 13 stages / 34 reason codes to 16 stages / 41 reason codes — consistent scale with Phases 1-3's own growth per phase.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `unittest` (Python standard library) [VERIFIED: `.planning/codebase/TESTING.md:5-11`, and confirmed live — no `pytest` installed in this devshell: `python3 -m pytest --version` → `No module named pytest`] |
| Config file | none — discovery-based, `tests/test_*.py` |
| Quick run command | `python -m unittest tests.test_publish -v` |
| Full suite command | `python -m unittest discover -s tests -p 'test_*.py' -v` |

Live-database tests must follow the existing `_LivePostgresMixin` pattern (`tests/test_staging.py:759-813`): skip (never fail) when `VICMAP_TEST_POSTGRES_DSN` is unset, and use the already-established `VICMAP_TEST_POSTGRES_SUPERUSER_DSN` (WINDOWS.md #6, `fixed`) for any test-only setup that needs superuser rights (creating a throwaway `vicmap_audit` table or reader role for the test run).

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PUB-01 | Only PASS-recorded staging tables promote; non-PASS/missing layer hard-stops | unit + live | `python -m unittest tests.test_publish.PublicationGateTest -v` | ❌ Wave 0 |
| PUB-02 | All layers visible together in one transaction; induced failure exposes no partial order | live (real multi-layer or forced-failure fixture) | `python -m unittest tests.test_publish.PromotionTransactionTest -v` | ❌ Wave 0 |
| PUB-03 | Previous usable tables preserved on promotion failure | live | `python -m unittest tests.test_publish.PromotionRollbackTest -v` | ❌ Wave 0 |
| PUB-04 | Reader gets schema `USAGE` + table `SELECT`, no write privileges | live | `python -m unittest tests.test_publish.ReaderGrantTest -v` | ❌ Wave 0 |
| PUB-05 | Reader can discover tables, `SELECT` rows, run a spatial query, and is denied a write | live, real second connection as reader | `python -m unittest tests.test_publish.ReaderVerificationTest -v` | ❌ Wave 0 |
| EVID-01 | Redacted summary links message -> checksum -> layers -> validation -> published tables -> reader verification | unit (pure assembly function, fixture inputs) | `python -m unittest tests.test_publish.SummaryAssemblyTest -v` | ❌ Wave 0 |
| EVID-02 | Any stage failure returns non-zero, names the failed boundary, exposes no secret | unit (CLI exit-code contract, mirrors `stage_order.py`'s existing exception-to-exit-code tests) | `python -m unittest tests.test_publish_order -v` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `python -m unittest tests.test_publish -v` (and `tests.test_publish_order`, `tests.test_evidence` for the vocabulary extension)
- **Per wave merge:** `python -m unittest discover -s tests -p 'test_*.py' -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`, plus the live D-74 reader proof run against the real delivery (mirrors Phase 3's `--preflight-only` live check pattern in `stage_order.py`)

### Wave 0 Gaps

- [ ] `tests/test_publish.py` — new file, covers PUB-01..05 (driver-isolation-respecting: only imports `vicmap_acquire.publish`, never `psycopg` directly at module scope in a non-`publish.py`/`staging.py` file)
- [ ] `tests/test_publish_order.py` — new file, covers EVID-02's CLI exit-code contract (mirrors `stage_order.py`'s own tested shape)
- [ ] `tests/test_staging.py::DriverImportPolicyTest` — must be updated in the same commit that introduces any new driver-importing module (see Pitfall 5)
- [ ] `tests/test_evidence.py` — extend for the 3 new `Stage` and ~7 new `ReasonCode` members plus the new summary event, mirroring the existing per-event test classes' shape
- [ ] No new test framework install needed — `unittest` is stdlib

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes (reader role) | A real, independently-authenticated connection with its own password (D-74) — no shared credential, no `SET ROLE` |
| V3 Session Management | No | No web session in this phase; each verification is a fresh, short-lived DB connection |
| V4 Access Control | Yes | PostgreSQL GRANT/schema-USAGE model (D-72/D-73/D-74) — least-privilege, no superuser, no blanket schema `CREATE` for the reader |
| V5 Input Validation | Yes | Every identifier composed via `psycopg.sql.Identifier`/`sql.Literal`, never raw string interpolation (established pattern, extended unchanged) |
| V6 Cryptography | No new surface | Credentials remain env-var-only, opnix/1Password-sourced (D-58/D-74 pattern) — never a config file, never argv |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via a composed identifier | Tampering | `sql.Identifier`/`sql.Literal` exclusively (already the codebase-wide pattern; no new risk introduced) |
| Reader role silently gaining write access via a grant-model regression | Elevation of Privilege | PUB-05's *live, executed* write-denial proof (Pattern 3) — a metadata-only check would not catch this class of regression; the new `READER_WRITE_NOT_DENIED` reason code exists specifically to hard-stop rather than warn |
| Partial-order visibility during promotion (a reader querying mid-promotion sees some but not all new layers) | Tampering / Information Disclosure | Single transaction, single commit (PUB-02); PostgreSQL's MVCC guarantees no other session sees any change until commit |
| Credential leakage into evidence output | Information Disclosure | Unchanged pattern: `VICMAP_READER_PASSWORD` reaches the process only via env var, never logged, never in `vicmap.toml`; `summary.json`/evidence events reuse the existing `_require_*` safe-scalar validators |

## Sources

### Primary (HIGH confidence)
- `vicmap_acquire/staging.py` (this session, full read) — the exact pattern (connection lifecycle, `sql.Composed`, closed failures, `apply_post_validation_ddl`'s catalog-discovery precedent) Phase 4 extends
- `vicmap_acquire/evidence.py` (this session, full read) — existing closed `Stage`/`ReasonCode` vocabulary and every safe-scalar validator this phase's new events must reuse
- `stage_order.py`, `vicmap_acquire/manifest.py`, `db/provision_vicmap_loader.sql`, `read_mailbox.py` (relevant sections), `flake.nix`, `vicmap.toml`, `tests/test_staging.py` (relevant sections) — all read this session
- postgresql.org/docs/current/sql-altertable.html — verified via `WebFetch` this session: the exact "cannot be combined" wording for `RENAME`/`SET SCHEMA`
- postgresql.org/docs/18/release-18.html — verified via `WebFetch` this session: exact quote on `NOT NULL` constraints now stored in `pg_constraint`
- postgresql.org/docs/current/ddl-priv.html — verified via `WebFetch` this session: default-privilege scope, `information_schema.tables` visibility behavior

### Secondary (MEDIUM confidence)
- spatialreference.org/ref/epsg/7899 and epsg.io/7899 — WebSearch-derived Victoria WGS84 extent and EPSG:7899 CRS metadata
- PostgreSQL source-tree documentation (execMain.c / `ExecCheckRTPerms`) — WebSearch-derived, confirms ACL checks run at executor startup before constraint evaluation; not a user-facing docs page

### Tertiary (LOW confidence)
- None retained as authoritative — the one WebSearch result that misleadingly implied `RENAME`/`SET SCHEMA` are excluded from *transactional* rollback (conflating it with "cannot be combined in one statement") was corrected against the actual docs page via `WebFetch` before being included above.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependency, everything reuses Phase 3's already-approved driver and patterns
- Architecture: HIGH — direct extension of `apply_post_validation_ddl`'s proven shape; the one genuinely new risk (PG18 `NOT NULL` naming) is resolved by a runtime-discovery pattern that is correct regardless of server version
- Pitfalls: MEDIUM-HIGH — Pitfalls 1, 3, 4, 5 are grounded in this session's direct reads of the actual source files and tests; Pitfall 2 (PG18 `NOT NULL`) is grounded in official release notes but the *actual* live server version could not be independently confirmed this session (sandbox credential restriction) — flagged explicitly as Open Question 1 / Assumption A1, not silently assumed either way

**Research date:** 2026-09-23
**Valid until:** 30 days (stable PostgreSQL/PostGIS semantics; the one fast-moving element — confirming the live server's actual major version — should be re-checked at execution time regardless of this file's age, since it was never confirmed live in this session)
