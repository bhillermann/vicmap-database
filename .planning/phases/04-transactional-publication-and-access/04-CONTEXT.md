# Phase 4: Transactional Publication and Access - Context

**Gathered:** 2026-09-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Promote the complete validated order from `vicmap_staging` into the published `vicmap` schema as one short transaction — all layers becoming visible together, never partially — and preserve the last usable production tables if promotion fails. Grant a configured reader role read-only access, and prove as that non-owner reader that the published tables can be discovered, selected, and spatially queried but not written. Finally, emit a redacted end-to-end run summary linking the selected message, artifact checksum, discovered layers, staging validation, published tables, and reader verification.

Covers PUB-01, PUB-02, PUB-03, PUB-04, PUB-05, EVID-01, EVID-02.

Not in scope: mailbox access, download, extraction, discovery, and the manifest (Phases 1–2); the staging load and D-56 validation themselves (Phase 3, though Phase 4 requires a small back-fill so Phase 3 persists its validation verdict durably — see D-68/D-70); legacy `public` WFS-table cleanup (Phase 5). Unattended daily orchestration, idempotency/replay protection, and the full durable audit subsystem remain deferred (OPS-01/02/05).

</domain>

<decisions>
## Implementation Decisions

Decision numbering continues the project sequence (Phase 1 D-01–D-20, Phase 2 D-21–D-40, Phase 3 D-41–D-65).

### Promotion Mechanism (PUB-01, PUB-02)

- **D-66:** Promotion is a **metadata move**, not a row copy. For each layer, `ALTER TABLE vicmap_staging.{table}_{run_ts} SET SCHEMA vicmap` then `ALTER TABLE vicmap.{table}_{run_ts} RENAME TO {table}`, with every layer's move inside **one transaction** so PUB-02's "all layers visible together in one short transaction" holds. No rows are recopied; D-63's PK on `gid`, typed `geometry(Point,7899)` column, GiST index, and `NOT NULL` are dependent objects that travel with the table. `CREATE TABLE AS SELECT` was rejected: it re-materializes 4.2M rows, transiently doubles storage (~975 MB), and rebuilds the constraints/indexes Phase 3 already built — the same no-row-recopy reasoning as D-41. — **Reversibility:** one-way — `vicmap.{table}` and its column contract are what every downstream QGIS project and saved query bind to.
- **D-67:** Index and constraint names are **renamed to canonical** (`{table}_pkey`, `{table}_geom_idx`, and so on) as part of the publish transaction, so the live table carries predictable names rather than the run-timestamped names minted in staging (e.g. `vmadd_address_20260918t..._geom_idx`). Consistent with D-45/D-46 treating the live table as the published contract. **Planner note:** index/constraint names are schema-scoped unique, so the outgoing table and its indexes must be dropped (D-71) *before* the new canonical names are minted, or the rename collides.

### Publication Gate (PUB-01)

- **D-68:** Only staging tables with a durable **PASS validation record** may be promoted. Phase 3 emits `LayerValidation` only as ephemeral JSON Lines events today — the only file it writes to the run directory is the `ogr2ogr` stderr on failure — so this record does **not exist yet**. This is a genuine cross-phase handoff gap, the same shape D-32 solved for provenance. Phase 4 reads the record and refuses to promote unless every manifest layer for the run is PASS. Re-running validation in Phase 4 was rejected (repeats the full 4.2M-row scan); trusting mere table presence + manifest digest was rejected (an implicit "it exists so it passed").
- **D-69:** The validation record is a **durable Postgres row**, not a filesystem sidecar. Its scope is deliberately **minimal — a publication gate, not OPS-01's audit subsystem**: per staging run, the `run_ts`, the frozen manifest digest, and a per-layer verdict plus the D-56 metrics (row count, SRID, geometry type, repaired count). Nothing about mailbox state, idempotency, or history. This pulls a thin slice of durable audit ahead of OPS-01 by explicit operator choice. — **Reversibility:** costly — it is a real table that both the publish gate and the EVID-01 summary read; the minimal shape is chosen precisely so OPS-01 stays deferred and the table can grow later without rework here.
- **D-70:** The record lives in a **dedicated `vicmap_audit` schema**, created once by hand via the D-60 superuser provisioning script — never in `vicmap` (it would clutter the reader-facing contract) and never in `vicmap_staging` (whose tables are per-run ephemeral). `vicmap_loader` is granted write on it. The DB-02-style preflight is extended to verify the schema exists and the loader holds the required privilege, failing closed and naming what is missing. Requires a **Phase 3 back-fill**: `stage_order.py` writes the validation row after `validate_layer`/`apply_post_validation_ddl`.

### Previous-Version Handling (PUB-03)

- **D-71:** On a **successful** publish, the outgoing `vicmap.{table}` (the prior order's live table) is **dropped inside the same publish transaction** — a single live generation, no `_previous` copy and no timestamped history, so storage does not grow per run and no retention policy is needed. PUB-03's failure case is satisfied *structurally*: the whole swap is one transaction, so a failed promotion rolls back and leaves the prior tables untouched. Keeping one `_previous` generation (post-commit manual rollback) and keeping timestamped history were both considered and rejected for v0.1 as extra storage plus deferred-hardening retention scope. — **Reversibility:** reversible — a retention scheme can be added later without changing the swap mechanism.

### Reader Role and Access (PUB-04, PUB-05)

- **D-72:** The reader role is **provisioned once by hand** via the D-60 superuser script — created with `LOGIN` and granted `USAGE ON SCHEMA vicmap` — not by the pipeline. The loader never needs `CREATEROLE`: it owns the published tables (D-59) and can therefore `GRANT SELECT` on them to an already-existing reader. The DB-02-style preflight verifies the reader role exists with baseline `USAGE`. Consistent with D-59/D-60's operator-provisioned, least-privilege posture.
- **D-73:** `GRANT SELECT` to the reader on each promoted table is applied **inside the publish transaction**. Each publish creates a new table identity (OID), so name-based grants never carry over and must be re-applied every publish; doing it in-transaction means a reader never observes a window where the table exists in `vicmap` but is not yet selectable.
- **D-74:** PUB-05 is proven with a **real reader login**. The reader role has its own password from opnix (`VICMAP_READER_PASSWORD`, exactly as `VICMAP_DB_PASSWORD` per D-58). Verification opens a *fresh connection as the reader* and (a) discovers the published tables, (b) runs a representative spatial query, and (c) attempts a write that must be denied. This is also the realistic identity that GIS/QGIS consumers connect as. `SET ROLE` from the loader connection was rejected — it proves role privileges rather than a real login, and would make the loader a member of the reader role. — **Reversibility:** costly — introduces a new secret plus 1Password/flake wiring; changing how PUB-05 is proven later means reworking the verification path and provisioning.

### Evidence and Summary (EVID-01, EVID-02)

- **D-75:** EVID-01 is emitted **two ways**: a durable, redacted `summary.json` written to the run directory (the milestone's proof artifact) **and** a final summary event on the existing JSON Lines stream through `_EmitOnce` (operator visibility, house style). The file is the deliverable; the event fits the everything-is-an-event pattern.
- **D-76:** Phase 4 **assembles the summary by re-reading the durable per-phase artifacts** — Phase 1's provenance sidecar (D-32), Phase 2's `manifest.json`, and Phase 3's new `vicmap_audit` validation record — then adds its own publish and reader-verification facts. This mirrors how Phase 2 reads the provenance sidecar and Phase 3 reads the manifest; no growing record is threaded between phase invocations.
- **D-77:** Phase 4 adds a new **`publish_order.py`** entry point (promote + grant + verify + summary), preserving the one-CLI-per-phase architecture (`read_mailbox.py` → `discover_order.py` → `stage_order.py` → `publish_order.py`). The operator runs the four CLIs in sequence (or a thin wrapper); no top-level end-to-end orchestrator is built — that is OPS-05 deferred scope. EVID-02's exit-code contract follows Phases 1–3: any stage failure returns non-zero, names the failed boundary via `Stage`/`ReasonCode`, and exposes no secrets.

### Claude's Discretion

- The exact **representative spatial query** for PUB-05 — planning toward a GiST-index-exercising `ST_Intersects`/`&&` predicate against a Victoria bounding box, plus table discovery via the catalog and a row/SELECT check.
- New `Stage` and `ReasonCode` members in `vicmap_acquire/evidence.py` for publication, grant, reader-verification, and validation-record-missing/failed boundaries.
- The exact schema and columns of the `vicmap_audit` validation-record table, provided it carries `run_ts`, the manifest digest, and the per-layer D-56 verdict + metrics.
- Whether the reader-role name is a new key in `vicmap.toml`'s `[database]` section or its own section; the exact 1Password item path for `VICMAP_READER_PASSWORD`.
- Module layout for the publish / grant / reader-verification code — in `vicmap_acquire/` alongside `staging.py`, or a sibling module.
- The exact filename and format of the durable `summary.json` and the field shape of the final summary event.
- Whether the write-denial check uses an `INSERT` or `UPDATE`, and how the expected permission-denied result is mapped to a pass verdict.
- The `-gt`/transaction shape of the promotion DDL and whether grants and drops are issued per-layer or batched, provided the whole promotion remains one transaction.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope and Requirements
- `.planning/PROJECT.md` — Binds this phase: publish through staging and atomic replacement so readers never see partial data; a dedicated `vicmap` schema; failure-only reporting; and the out-of-scope entries (manual mappings, incremental upserts, unattended daily execution) that keep OPS-01/02/05 deferred.
- `.planning/REQUIREMENTS.md` — Defines `PUB-01`–`PUB-05`, `EVID-01`, `EVID-02`, and the deferred `OPS-01` (durable audit), `OPS-02` (idempotency), `OPS-05` (daily systemd run) that bound what D-69/D-71/D-77 deliberately leave out.
- `.planning/ROADMAP.md` — Fixed Phase 4 boundary and its five success criteria (no `Canonical refs:` line is set for this phase).

### Prior Phase Decisions (binding)
- `.planning/phases/03-validated-postgis-staging/03-CONTEXT.md` — Phase 3's `D-41`–`D-65`. Directly binding: D-47 (`vicmap_staging` separate from `vicmap`), D-48 (`vmadd_address_{run_ts}` staging names — the promotion source), D-56 (the three blocking checks whose verdict D-68 gates on), D-57 (spatial vs non-spatial profiles the record must carry), D-58 (non-secret fields in `vicmap.toml`, password via opnix — extended by D-74), D-59 (`vicmap_loader` owns both schemas), D-60 (by-hand provisioning + preflight — extended by D-70/D-72), D-61 (DB-01 identity print), D-63 (PK/typed-geom/GiST/NOT NULL that D-66 carries across), and D-65 (drop-on-promotion, now largely subsumed by D-66's move; the failed-staging age sweep stays deferred).
- `.planning/phases/02-safe-geospatial-discovery/02-CONTEXT.md` — Phase 2's manifest contract and redaction rule; `manifest.json` and its digest are inputs to D-76. D-32's provenance sidecar is the model D-68 follows and a D-76 input.
- `.planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md` — Phase 1's redacted-evidence and safe-failure posture (D-17–D-20) that EVID-01/EVID-02 and D-75 inherit; the message fingerprint D-76 links.

### Source Files (read these, not the maps)
- `vicmap_acquire/staging.py` — `StagingPolicy`, `DatabaseIdentity`, `LayerValidation`, `_connect`, `read_database_identity`, `preflight_staging_privileges`, `staging_table_name`, `run_staging`, `apply_post_validation_ddl`, and the `StagingFailure` hierarchy. Phase 4's publish/grant/verify code extends this module's connection and typed-failure patterns; the preflight grows to cover `vicmap_audit` and the reader role.
- `stage_order.py` — Phase 3 entry point; the model for `publish_order.py` and the site of the D-70 validation-record back-fill (it emits `LayerValidation` today but persists no durable record).
- `vicmap_acquire/manifest.py` — `read_manifest` and the digest; a D-76 input.
- `vicmap_acquire/download.py` — `read_provenance_sidecar`; a D-76 input for the message fingerprint and artifact checksum.
- `vicmap_acquire/evidence.py` — `Stage`, `ReasonCode`, `fingerprint()`, `SuccessEvent`/`ProgressEvent`/`SafeFailure`, `_EmitOnce`. D-75's summary event and all new publication reason codes extend this closed vocabulary.
- `vicmap_acquire/naming.py` — D-22 normalization; still authoritative for the target `{table}` name D-66 renames to.
- `read_mailbox.py` — `load_config` / `validate_*` pattern; the reader-role name and any new `[database]` keys follow the complete-key-set, fail-closed shape.
- `vicmap.toml` — existing `[database]` section from Phase 3; extended with the reader-role name (non-secret).
- `db/provision_vicmap_loader.sql` — the D-60 by-hand provisioning script; extended by D-70 (`vicmap_audit` schema + loader write) and D-72 (reader `LOGIN` role + `USAGE ON SCHEMA vicmap`).
- `flake.nix` / `.envrc` — opnix wiring that injects `VICMAP_DB_PASSWORD`; extended for `VICMAP_READER_PASSWORD` (D-74).

### External Documentation
- PostgreSQL docs — `ALTER TABLE ... SET SCHEMA` / `RENAME`, `GRANT`, and role/privilege semantics (grants keyed to table OID, not name; DDL transactionality) that underpin D-66/D-71/D-73. Verify against the live PostgreSQL 18.x server used in Phase 3.
- PostGIS docs — spatial predicate + GiST index behaviour for the D-74 representative query.

### Codebase Maps (treat as stale where they concern this phase)
- `.planning/codebase/ARCHITECTURE.md` and `.planning/codebase/INTEGRATIONS.md` — accurate for Phases 1–3; both predate the `vicmap_audit` schema, the reader role/secret, and `publish_order.py` introduced here.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `vicmap_acquire/staging.py`: `_connect` + `StagingPolicy` are the connection and frozen-policy pattern the publish path reuses; `preflight_staging_privileges` is the model (and the site) for the D-70/D-72 preflight additions; `staging_table_name` produces the exact `{table}_{run_ts}` names D-66 moves. `LayerValidation` is the in-memory verdict D-70 persists.
- `vicmap_acquire/evidence.py` (545+ lines): 13 stages / 34 reason codes with `_EmitOnce` and `fingerprint_hex_chars` threading. Phase 4 extends the enums for publication/grant/verification and adds D-75's summary event — no second output mechanism.
- `vicmap_acquire/download.py`: `read_provenance_sidecar` gives D-76 the Phase 1 message fingerprint and artifact checksum without re-opening the mailbox.
- `vicmap_acquire/manifest.py`: `read_manifest` + digest give D-76 the discovered-layer facts and the digest D-68 checks.
- `tests/test_naming.py`'s `PostgresKeywordOracleTest` and Phase 3's live-DB tests: the guarded, `VICMAP_TEST_POSTGRES_DSN`-driven, skip-not-fail pattern the reader-login and publish tests reuse.

### Established Patterns
- Every boundary is a frozen, up-front-validated policy dataclass; one validator is the single configuration contract.
- Failures are typed closed failures mapped to a fixed `ReasonCode`; unexpected exceptions map to one fixed internal failure with no interpolation; travelling output is redacted (D-43 scoping applies).
- Only `vicmap_acquire/staging.py` imports the PostgreSQL driver (D-41 driver isolation); Phase 4's DB code lives with or beside it, not scattered.
- Allowlists / config keys start minimal and widen by config change (`allowed_senders`, `index_columns`); the reader-role name follows this shape.
- Independent-oracle testing where hand-written assertions would share the code's blind spot (`ogrinfo`, `pg_get_keywords()`), per [[differential-oracle-testing]].
- One durable file per fact on the filesystem (provenance sidecar, `manifest.json`); D-69 chose a Postgres row *instead* for the validation record, so this is the first fact that lives in the database rather than the run directory.

### Integration Points
- `publish_order.py` reads: the run directory's `manifest.json` + provenance sidecar, and the `vicmap_audit` validation record. It writes: the promoted `vicmap.*` tables, reader grants, the `vicmap_audit` gate read, and `summary.json`.
- The D-70 back-fill touches `stage_order.py` / `staging.py` — "complete" Phase 3 code — to persist the validation row. Keep it minimal and additive; re-running Phase 3 staging is required to populate the record for the proof delivery.
- `tests/test_manifest.py` enforces a forbidden-driver-import list for the manifest module — do not broaden it blindly; the driver still belongs only in the staging/publish DB module.
- opnix injects secrets at shell startup; `VICMAP_READER_PASSWORD` joins `VICMAP_DB_PASSWORD` (new 1Password item/field; update `.envrc`/`flake.nix` and the USER-SETUP notes).
- `.gitignore` already covers `runs/`, so D-75's `summary.json` in the run directory is ignored.

</code_context>

<specifics>
## Specific Ideas

Ground truth carried from Phase 3, to treat as verified, not assumed:

- **Proof delivery path:** `vicmap_staging.vmadd_address_{run_ts}` — 4,222,035 Point features, `geom geometry(Point, 7899) NOT NULL`, `gid` primary key, GiST index built after validation — is promoted by D-66 to `vicmap.vmadd_address` (its canonical index/constraint names per D-67), with the reader granted `SELECT` in the same transaction (D-73).
- **One-layer order:** the proof delivery is a single layer, but the promotion transaction and the summary must be written for N layers (all-or-nothing per PUB-02).
- **Reader verification (D-74):** connect as the reader with `VICMAP_READER_PASSWORD`, list `vicmap` tables, run a spatial predicate over `vmadd_address.geom` (exercising the GiST index), and attempt a write that must fail with permission denied.
- **PostgreSQL server:** the live PostGIS server from Phase 3 (port 5432); `ogrinfo` from the pinned GDAL 3.13.2 remains available as an independent oracle for cross-checking published counts/geometry/CRS in the summary.

</specifics>

<deferred>
## Deferred Ideas

- **Full OPS-01 durable audit subsystem.** `vicmap_audit` (D-69/D-70) is a minimal publication-gate slice only — messages, orders, artifacts, and load-outcome history with idempotency remain out of scope for v0.1.
- **Idempotency / replay protection for a re-run publish (OPS-02).** Phase 4 assumes a clean prior state or fails closed; overlapping or repeated publishes are not made safe here.
- **Top-level end-to-end orchestrator / daily systemd run (OPS-05).** D-77 keeps the one-CLI-per-phase shape; a single command that runs Phases 1→4 is deferred.
- **Retaining previous published generations.** A `_previous` generation or timestamped published history plus its retention policy — considered in D-71, rejected for v0.1.
- **Failed-staging age-based sweep (D-65 second half).** Still deferred, unchanged from Phase 3; Phase 4 only removes staging tables by moving successfully promoted ones out (D-66).
- **Extent sanity envelope.** Carried unchanged from Phase 3 — a Victoria-shaped bounding box a published extent must fall inside; not blocking.
- **Auto-pruning old run directories.** Carried unchanged from Phase 2/3 — ~975 MB per run, pruned manually.
- **Widening the format allowlist.** Carried unchanged — shapefile/GeoPackage/MapInfo/DXF remain unsupported until a real delivery needs them.

None — discussion stayed within phase scope (the deferred items above were surfaced as boundaries of the decisions taken, not as scope-creep requests).

</deferred>

---

*Phase: 04-transactional-publication-and-access*
*Context gathered: 2026-09-22*
