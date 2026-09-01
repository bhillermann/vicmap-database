# Architecture Research

**Domain:** Email-triggered geospatial ETL into PostGIS
**Researched:** 2026-09-01
**Confidence:** HIGH for component boundaries and build order; MEDIUM for the exact Vicmap email/download contract until a real ready email and archive are inspected

## Standard Architecture

### System Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Thin command / orchestration                                        │
│  import-one-order → explicit stages → clear terminal result          │
└───────────┬──────────────────────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────────────┐
│ Application and domain                                              │
│  Ready-email selector → order/link parser → layer-name normalizer    │
│  Import manifest → validation policy → publication plan              │
└──────┬──────────────────┬─────────────────────┬──────────────────────┘
       │                  │                     │
┌──────▼─────────┐ ┌──────▼──────────┐ ┌────────▼─────────────────────┐
│ Graph adapter  │ │ Artifact adapter│ │ PostGIS adapter              │
│ auth/read mail │ │ download/unpack │ │ connect/load/validate/swap  │
│ body metadata  │ │ GDAL discovery  │ │ roles/inventory/cleanup plan│
└──────┬─────────┘ └──────┬──────────┘ └────────┬─────────────────────┘
       │                  │                     │
┌──────▼─────────┐ ┌──────▼──────────┐ ┌────────▼─────────────────────┐
│ Microsoft Graph│ │ bounded work dir│ │ local PostgreSQL/PostGIS     │
│ automation box │ │ archive + files │ │ vicmap_staging → vicmap     │
└────────────────┘ └─────────────────┘ └──────────────────────────────┘
```

This should remain a synchronous, single-process pipeline for v0.1. The milestone proves one order; a queue, scheduler, long-lived service, event bus, and durable processing ledger would add failure modes without helping that proof. The important architectural move is not distribution but separation: keep Microsoft Graph objects, filesystem paths/GDAL datasets, and database connections behind adapters, and pass small repository-owned records between stages.

### Component Responsibilities

| Component | Responsibility | Recommended implementation |
|-----------|----------------|----------------------------|
| CLI/orchestrator | Run exactly one import, select or identify the ready email, create a work directory, sequence stages, and return a non-zero exit on failure | `argparse` command calling application services; no domain parsing or SQL embedded here |
| Configuration | Validate mailbox, sender allowlist, workspace, download limits, and database connection inputs before external calls | Immutable dataclass populated from environment/CLI; passwords remain outside config files and logs |
| Graph mailbox adapter | Reuse application authentication, read the configured mailbox/folder, page messages, and return selected fields/body | Refactor the working `O365.Account` code from `read_mailbox.py`; expose repository-owned `MailMessage` values rather than O365 objects |
| Ready-email policy | Decide whether a message is a trusted ready notification and extract order identity plus candidate download URL | Pure functions over sender, subject, received time, and HTML body; exact patterns learned from a real message and captured in fixtures |
| Artifact downloader | Follow only the accepted HTTPS URL, stream to disk, enforce timeout/redirect/size rules, and preserve the original archive | `requests.Session` or the HTTP client already used transitively, with explicit response checks and a caller-owned work directory |
| Safe unpacker | Inspect archive members, reject path traversal/special entries and excessive expansion, then extract | Standard-library `zipfile` initially; isolated function so other archive formats can be added only if the real delivery requires them |
| Geospatial discovery | Find dataset roots, enumerate layers, and record source name, driver, geometry type, CRS, feature count, and fields | GDAL/OGR read-only APIs or `ogrinfo -json`; build GDAL with OpenFileGDB and PostgreSQL drivers in the Nix shell |
| Naming policy | Convert source layer names to deterministic PostgreSQL-safe names and reject collisions after normalization | Pure function producing lowercase `snake_case`, bounded identifiers, and an explicit source-to-target manifest |
| PostGIS loader | Verify connectivity/PostGIS, create staging namespace, bulk-copy each discovered layer, and collect load facts | GDAL PostgreSQL driver/`ogr2ogr` for geospatial transfer; a PostgreSQL client for DDL, validation, grants, and transactions |
| Validator | Compare source and staging facts before publication | At minimum: layer exists, nonzero/expected feature count, geometry column/type, SRID/CRS, and readable sample; fail the whole order on any invalid layer |
| Publisher | Replace all tables for the order in one short database transaction after slow loading/validation completes | Load into uniquely named `vicmap_staging` tables first; transactionally move/rename validated tables into `vicmap`, apply ownership/grants, and retire prior targets |
| Access provisioner | Make production tables queryable without granting write access | Dedicated read role with `USAGE ON SCHEMA vicmap` and `SELECT` on published tables; verify with `SET ROLE` or a read-only connection |
| Legacy inventory/cleanup | List likely abandoned WFS tables separately from legitimate GIS objects and generate an approval manifest | Read-only catalog query first; a separate cleanup command accepts exact schema-qualified names and requires an explicit approval artifact/flag |

## Recommended Project Structure

```text
vicmap-database/
├── src/vicmap_database/
│   ├── cli.py                 # import, inventory, and approved-cleanup commands
│   ├── config.py              # environment/CLI validation
│   ├── models.py              # MailMessage, OrderArtifact, LayerInfo, ImportManifest
│   ├── pipeline.py            # one-order application orchestration
│   ├── mail/
│   │   ├── graph.py           # O365/Graph adapter
│   │   └── ready_order.py     # trusted ready-message parsing policy
│   ├── artifacts/
│   │   ├── download.py        # bounded HTTPS download
│   │   ├── archive.py         # safe extraction
│   │   └── geospatial.py      # GDAL dataset/layer discovery
│   └── database/
│       ├── connection.py      # PostgreSQL connectivity and PostGIS preflight
│       ├── load.py            # GDAL-to-staging load
│       ├── publish.py         # validation, transactional promotion, grants
│       └── legacy.py          # inventory and exact-name cleanup
├── tests/
│   ├── fixtures/              # sanitized email HTML and tiny geodata/archive fixtures
│   ├── test_ready_order.py
│   ├── test_archive.py
│   ├── test_geospatial.py
│   ├── test_publish.py
│   └── test_legacy.py
├── migrations/
│   └── 001_vicmap_schemas.sql # schema and role bootstrap if kept as SQL
├── read_mailbox.py            # temporary compatibility wrapper, then remove
├── flake.nix                  # O365 + GDAL + PostgreSQL client/runtime dependencies
└── .planning/                 # workflow artifacts only
```

### Structure Rationale

- **`pipeline.py`:** makes stage order and failure boundaries visible while keeping third-party APIs out of orchestration.
- **`mail/`, `artifacts/`, `database/`:** follow the three external failure domains. Each can be tested with a fake or fixture without live Graph, download hosting, or PostGIS.
- **`models.py`:** prevents O365 message instances, raw HTML, GDAL handles, and database cursors from leaking across boundaries.
- **`migrations/`:** owns stable database prerequisites; temporary staging table names and per-run swaps remain runtime behavior.
- **Three CLI operations:** `import` may create/replace only `vicmap` objects; `inventory` is read-only; `cleanup` is deliberately separate and exact-targeted. This keeps abandoned-WFS cleanup out of the importer's blast radius.

## Architectural Patterns

### Pattern 1: Functional Core, Imperative Adapters

**What:** Put ready-email matching, URL selection, layer-name normalization, manifest construction, and validation decisions in pure functions. Keep Graph, HTTP, GDAL, filesystem, and SQL effects in narrow adapters.

**When to use:** Throughout v0.1, because real external systems are required but most decision logic can be fixture-tested.

**Trade-offs:** Adds small repository-owned records and mapping code, but prevents a hard-to-test script where live credentials and database state are required for every check.

**Example:**

```python
message = graph.get_message(message_id)
order = parse_ready_order(message, allowed_senders=config.allowed_senders)
archive = downloader.fetch(order.download_url, workspace)
layers = geodata.discover(unpacker.extract(archive, workspace))
manifest = build_manifest(order, layers, target_schema="vicmap")
pipeline.load_validate_publish(manifest)
```

### Pattern 2: Manifest Before Mutation

**What:** Resolve the complete mapping from message → order → archive → dataset → source layer → normalized target table before creating production objects. Detect duplicate normalized names, unsupported datasets, missing CRS, and unexpected empty layers at this boundary.

**When to use:** Before any staging load and again before publication.

**Trade-offs:** Requires an explicit discovery pass, but produces a reviewable proof and prevents one source layer silently overwriting another.

The v0.1 manifest can be an in-memory dataclass rendered as JSON to the per-run work directory. It is evidence, not yet the durable audit ledger deferred to a later milestone.

### Pattern 3: Load Outside, Publish Inside a Transaction

**What:** Perform slow GDAL loads into uniquely named tables in `vicmap_staging`. Validate them there. Only then begin a short PostgreSQL transaction that locks conflicting production targets, moves existing targets aside, moves/renames all new tables into `vicmap`, applies ownership/grants, and drops or retains old tables according to one explicit policy. Roll back the entire publication if any DDL fails.

**When to use:** For every complete-snapshot delivery, including the one-order proof.

**Trade-offs:** Requires unique staging names and careful identifier quoting. Table replacement changes object identity, so dependent views/foreign keys and table-specific grants need an explicit policy. For v0.1, preflight should fail if a target already has unsupported dependencies, and grants should be reapplied and verified. Do not hold a transaction open during archive reading or bulk load.

```sql
BEGIN;
LOCK TABLE vicmap.target IN ACCESS EXCLUSIVE MODE; -- only when it exists
ALTER TABLE vicmap.target SET SCHEMA vicmap_staging;
ALTER TABLE vicmap_staging.target RENAME TO target__old_run_id;
ALTER TABLE vicmap_staging.target__new_run_id SET SCHEMA vicmap;
ALTER TABLE vicmap.target__new_run_id RENAME TO target;
GRANT SELECT ON TABLE vicmap.target TO vicmap_reader;
COMMIT;
```

The generated SQL must use database-driver identifier composition, not string interpolation. Multiple target tables from one order belong in the same publication transaction.

### Pattern 4: Approval as Data for Destructive Cleanup

**What:** Inventory legacy candidates into a report containing exact schema, table, owner, estimated rows/size, geometry metadata, dependencies, and the evidence used to classify each candidate. Cleanup consumes only an explicit approved list and re-checks that every object still matches the inventory before dropping it.

**When to use:** After the new `vicmap` pipeline succeeds and independently of normal imports.

**Trade-offs:** Makes cleanup a two-step operation, which is intentional. Classification cannot safely be inferred from “spatial table” or location in `public`, because legitimate tables share that schema.

## Data Flow

### One-Order Import Flow

```text
CLI selects message (explicit ID or constrained newest-ready search)
    ↓
Graph adapter authenticates and reads selected metadata + HTML body
    ↓
Ready-order policy checks sender and extracts order ID + HTTPS URL
    ↓
Downloader streams archive into a fresh bounded workspace
    ↓
Safe unpacker inspects members and extracts below that workspace only
    ↓
GDAL discovery enumerates datasets/layers and builds import manifest
    ↓
PostGIS preflight verifies host:5432, database, PostGIS, schemas, privileges
    ↓
GDAL loads uniquely named tables into vicmap_staging
    ↓
Validator compares source and staging facts
    ↓
Publisher promotes every validated table in one transaction to vicmap
    ↓
Access check queries published tables as the reader role
    ↓
CLI emits concise manifest/result; workspace remains for proof/debugging
```

### State Management

There is no durable workflow state in v0.1. State should be explicit and run-scoped:

```text
RunContext
├── selected Graph message ID and received timestamp
├── trusted sender, order ID, accepted download URL
├── workspace and archive checksum
├── discovered source-layer metadata
├── source → staging → production manifest
└── per-stage result and final verification query
```

Use a unique `run_id` in workspace and staging table names so a failed proof does not collide with another attempt. Startup may report stale staging objects but must not delete them implicitly. Later automation can persist this same model as the deferred Postgres audit ledger.

### Key Data Flows

1. **Message discovery:** Query a bounded recent window and select only needed fields. Graph message listing is paged, message bodies are HTML, and large broad result sets can time out; the adapter must honor the SDK's pagination rather than assuming one call returns the Inbox.
2. **Download:** Treat the email body as untrusted input even after sender matching. Parse HTML, select an allowed HTTPS URL, constrain redirects/host policy after observing the real Vicmap link flow, and never log query tokens.
3. **Geospatial discovery:** Inspect every extracted candidate in read-only mode. Let GDAL identify supported formats and enumerate layers; do not infer layer identity solely from filenames because a File Geodatabase is a directory dataset containing multiple layers.
4. **Publication:** GDAL handles bulk spatial type conversion and COPY-based loading; repository-owned SQL handles schema qualification, validation, transactional DDL, roles, and access verification.
5. **Legacy cleanup:** Catalog → human approval → guarded exact-name drops. It does not share a code path with `publish` and never scans/drops all spatial tables in `public`.

## Scaling Considerations

| Scale | Architecture adjustments |
|-------|--------------------------|
| One order / v0.1 | One synchronous process, local workspace, sequential layer loads, unique staging names, one publication transaction |
| Daily recurring orders | Add Postgres audit/idempotency records, checksum-based deduplication, retryable stages, bounded retention, systemd execution, and failure notification without changing adapter boundaries |
| Multiple large orders or concurrent runs | Add a database advisory lock per order/target set, resource limits, controlled layer parallelism, and resumable artifact storage before considering a queue |

### Scaling Priorities

1. **First bottleneck — bulk geospatial load:** Dataset size and conversion dominate runtime. Use GDAL's PostgreSQL driver and COPY behavior, validate GDAL build capabilities, keep indexes/constraints out of the initial bulk copy where appropriate, and create/analyze them before publication.
2. **Second bottleneck — operational recovery:** Once unattended, repeated messages and half-finished staging loads matter more than CPU. Add the deferred database ledger and deterministic checksums before introducing concurrency.

## Anti-Patterns

### Anti-Pattern 1: Growing `read_mailbox.py` into the Pipeline

**What people do:** Add HTML parsing, downloading, extraction, GDAL calls, and SQL below the existing message loop.

**Why it's wrong:** Importing the file already performs live authentication; exceptions have no stage context; O365 objects leak everywhere; and tests require secrets.

**Do this instead:** Move current authentication/mailbox behavior into `mail/graph.py`, add a guarded thin command, and pass repository-owned values between stages.

### Anti-Pattern 2: Download or Extract Directly into a Shared Directory

**What people do:** Trust the emailed filename, call `extractall`, and scan a persistent directory recursively.

**Why it's wrong:** Filenames can collide, stale files can be mistaken for the current order, and archive members can attempt path traversal or cause excessive expansion.

**Do this instead:** Use a fresh run directory, generated local archive name, inspected members, containment checks, size/count limits, and a manifest of extracted paths.

### Anti-Pattern 3: `ogr2ogr -overwrite` Against Production

**What people do:** Point GDAL directly at `vicmap.target` and overwrite it during conversion.

**Why it's wrong:** Readers can observe missing/partial data and one failed layer can leave a multi-layer order inconsistently published.

**Do this instead:** Load unique staging tables, validate, then promote all order tables in a short database transaction.

### Anti-Pattern 4: Using `search_path` for Write Targeting

**What people do:** Set `search_path` and use unqualified table names for convenience.

**Why it's wrong:** PostgreSQL resolves and creates unqualified objects through the search path; writable schemas in that path are also a trust concern. This risks touching legitimate `public` objects.

**Do this instead:** Schema-qualify every runtime object, constrain identifiers through a naming policy, and use driver-supported identifier composition.

### Anti-Pattern 5: Inferring Abandoned Tables and Dropping Them Inline

**What people do:** Delete tables based on spatial type, a broad name pattern, or presence in `public` before loading the new data.

**Why it's wrong:** Legitimate GIS tables are actively used in the same schema, and catalog heuristics cannot prove abandonment.

**Do this instead:** Complete the isolated `vicmap` proof first; produce a dependency-aware inventory; require approval of exact schema-qualified targets; revalidate immediately before deletion.

## Integration Points

### External Services

| Service | Integration pattern | Notes |
|---------|---------------------|-------|
| Microsoft Graph | Existing O365 client-credentials account scoped to `automations@vegetationlink.com.au` | Keep application auth; request/select only needed mail fields, honor paging, parse HTML body, and validate actual sender before accepting a URL. `Mail.Read` is needed when reading bodies/attachments rather than only basic metadata. |
| Vicmap order download host | Bounded HTTPS streaming client | The exact URL shape, redirects, expiry, cookies, filename, and archive format are discovery items from the first real email; isolate these assumptions in the downloader. |
| GDAL/OGR | Read-only dataset discovery plus PostgreSQL writer | Pin through Nix and verify at startup that the delivered format driver (likely OpenFileGDB, but do not assume) and PostgreSQL/PostGIS driver are present. `ogrinfo -json` is a useful inspectable boundary for the proof. |
| Local OCI PostGIS | PostgreSQL connection at configured host and port 5432 | Port alone is insufficient: database, user, password/service, TLS/local policy, installed PostGIS version, and target reader role must be configuration/preflight inputs. Never rely on container name from application code. |
| Database users | PostgreSQL role grants | Prefer a non-login `vicmap_reader` group role; grant schema usage and table select, then test an actual query under that role. Whether existing users inherit this role is an operator-approved database action. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| CLI ↔ pipeline | Typed config + selected message ID/options | Default search may be added, but an explicit message ID makes the initial proof reproducible |
| Graph adapter ↔ ready policy | `MailMessage` record | Include immutable Graph ID, sender, subject, received time, HTML body; exclude the live SDK object |
| Ready policy ↔ downloader | `ReadyOrder` record | Only a policy-approved URL crosses the boundary |
| Unpacker ↔ geospatial discovery | Root path + extracted member manifest | Discovery sees only this run's files |
| Discovery ↔ loader | `ImportManifest` | Manifest freezes normalization and catches collisions before mutation |
| Loader ↔ publisher | Staging table facts | Publisher never accepts an unvalidated or non-run-owned staging name |
| Import ↔ legacy cleanup | No runtime coupling | Only shared connection/config helpers; cleanup is a separate command and approval gate |

## Dependency-Aware Build Order

1. **Refactor without behavior change:** Create package/CLI/config, move Graph account and mailbox listing behind `GraphMailbox`, add `main()` guard, and preserve the known successful login/read path.
2. **Capture the real contract:** Select one real ready email, record sanitized sender/subject/body fixture, implement sender validation and ready-order/link parsing, then download one archive into a unique workspace.
3. **Establish safe artifact handling:** Add archive inspection/extraction limits and create a real archive manifest. Do not design geodata loading until the actual delivered archive format and layout are known.
4. **Add GDAL discovery:** Extend `flake.nix`, verify required drivers, enumerate all dataset layers and metadata, normalize names, and fail on target collisions. This produces the complete import manifest.
5. **Add database preflight and bootstrap:** Connect to the local OCI-published port, verify `PostGIS_Full_Version()`, create/verify `vicmap_staging` and `vicmap`, establish owner/reader roles, and confirm no code path writes unqualified names or mutates `public`.
6. **Load staging:** Transfer each manifest layer to a unique staging table, then validate counts, geometry, CRS/SRID, fields, and readability. Keep production unchanged on failure.
7. **Publish and prove access:** Implement multi-table transactional promotion, grants, dependency checks for replacements, and an explicit reader-role query. Preserve the run manifest and evidence.
8. **Inventory and gated cleanup:** Only after the new path works, inventory abandoned WFS candidates, obtain exact approval, revalidate targets/dependencies, then execute cleanup separately. Never make cleanup a prerequisite for the proof unless a confirmed name/space conflict exists.

## Sources

- [Microsoft Graph: List messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0) — paging, field selection, HTML message bodies, and mailbox access patterns.
- [Microsoft Graph: Get attachment](https://learn.microsoft.com/en-us/graph/api/attachment-get?view=graph-rest-1.0) — attachment types, raw-content endpoint, and permissions if the real delivery uses an attachment rather than a body link.
- [python-o365 source: message and attachment implementation](https://github.com/O365/python-o365/blob/master/O365/message.py) — behavior of the existing SDK boundary used by this repository.
- [GDAL `ogrinfo`](https://gdal.org/en/stable/programs/ogrinfo.html) — read-only datasource inspection, layer enumeration, JSON summaries, and error status.
- [GDAL `ogr2ogr`](https://gdal.org/en/latest/programs/ogr2ogr.html) — vector conversion/loading and transaction-related options.
- [GDAL PostgreSQL/PostGIS driver](https://gdal.org/en/stable/drivers/vector/pg.html) — connection forms, layer creation, PostGIS behavior, transactions, and COPY-based insertion.
- [GDAL vector drivers](https://gdal.org/en/stable/drivers/vector/index.html) — supported dataset drivers including OpenFileGDB and PostgreSQL.
- [Python `zipfile`](https://docs.python.org/3/library/zipfile.html) — archive extraction APIs and explicit warning to inspect untrusted archives before extraction.
- [PostgreSQL schemas](https://www.postgresql.org/docs/current/ddl-schemas.html) — qualified names, schema creation, `search_path`, and schema trust implications.
- [PostgreSQL transaction control](https://www.postgresql.org/docs/current/sql-begin.html) — transaction boundaries used for short publication DDL.
- [PostgreSQL privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — ownership and `USAGE`/`SELECT` privilege model for user access.

---
*Architecture research for: v0.1 End-to-End Vicmap Import Proof*
*Researched: 2026-09-01*
