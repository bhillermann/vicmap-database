# Vicmap Database

## What This Is

Vicmap Database is an automated delivery pipeline for spatial datasets used by Vegetation Link's GIS work. It monitors `automations@vegetationlink.com.au` for recurring Vicmap order updates, downloads ready geodatabase packages, discovers their spatial layers, and safely refreshes corresponding PostGIS tables. v0.1 proved this end to end for one operator-run delivery; unattended daily systemd operation is the next step.

## Core Value

Vicmap updates must reach the correct PostGIS layers automatically without exposing users to partial, invalid, or duplicate data loads.

## Current State

**Shipped:** v0.1 End-to-End Vicmap Import Proof (2026-09-30) — see [MILESTONES.md](MILESTONES.md).

One real ready-order email (order `OK0VUZ`) was processed through four operator-run CLIs (acquire → `discover_order.py` → `stage_order.py` → `publish_order.py`) into `vicmap.vmadd_address` (4,222,035 rows), with reader access proven and a redacted EVID-01 `summary.json`. A publish that fails after its promotion commits can now be resumed (Phase 05.1).

## Next Milestone Goals

Not yet defined — start with `/gsd-new-milestone`. The natural candidates are the v0.1 Future Requirements:

- Operational hardening: durable audit records (OPS-01), idempotent/overlap-safe reprocessing (OPS-02), retry/resume beyond publish (OPS-03), source drift detection (OPS-04), daily systemd run with failure notification (OPS-05)
- Backlog 999.1 (ICSM grid selection) and 999.2 (provisioning creates/checks the `vicmap` database)

## Requirements

### Validated

- ✓ A reproducible Nix development environment supplies Python and the O365 SDK — existing
- ✓ Microsoft application credentials are injected from 1Password through opnix — existing
- ✓ Authenticate with Microsoft Graph and read messages from the automation mailbox (memory-only auth, bounded metadata paging) — v0.1
- ✓ Identify a real Vicmap ready-order email from an authenticated trusted sender, download its order archive through authorized bounded hops, and unpack it safely — v0.1
- ✓ Discover and read the delivered geospatial files into an immutable, collision-free layer manifest — v0.1
- ✓ Connect to the existing local PostGIS instance on port 5432 with a proven-capable least-privilege loader — v0.1
- ✓ Load delivered layers into validated staging and publish them atomically into a dedicated `vicmap` schema — v0.1
- ✓ Make the resulting production tables queryable by database users (reader role; writes denied) — v0.1
- ✓ Inventory abandoned WFS-attempt tables and remove only tables explicitly approved for deletion — v0.1 (satisfied by manual cleanup; no WFS tables remained)
- ✓ Re-running publication after a post-commit failure resumes the committed promotion instead of re-promoting, and any unprovable live state fails closed with no DDL — v0.1 (Phase 05.1, publish slice of OPS-03)

### Active

(None — define with `/gsd-new-milestone`. See Next Milestone Goals.)

### Out of Scope

- Manual order-to-dataset-to-table mappings — layer targets are discovered and normalized from geodatabase layer names (proven in v0.1)
- Incremental feature upserts or append-only loading — each delivered layer is a complete snapshot replaced atomically
- Mailbox folders as authoritative workflow state — Postgres audit records govern idempotency and processing history
- Processing messages from unconfigured senders — sender allowlisting bound to DKIM/DMARC is the selected trust boundary
- Success notification emails — normal operation is visible through structured journal logs; email is reserved for failures
- General-purpose geospatial ETL framework or management UI — prove further Vicmap operations before adding abstractions

## Context

Shipped v0.1 with ~27,300 lines of Python/SQL (~18,300 of them tests; 704 tests passing, 0 skipped with live DSNs). Tech stack: Python in a Nix flake, O365/Microsoft Graph, html5lib, GDAL/pyogrio/ogr2ogr with a vendored ICSM grid, psycopg 3, PostgreSQL 17/18 + PostGIS, opnix-injected secrets. Evidence is emitted as closed-vocabulary, redacted JSON Lines events.

Vicmap sends two messages for an update to an existing order: an initial confirmation followed later by a ready notification whose download link is then live. An order number remains stable across updates and may deliver multiple spatial files.

Known issues and debt: GDA94↔GDA2020 transforms use Helmert rather than the ICSM grid (~2 mm, backlog 999.1); the `vicmap` database must be created manually before provisioning (backlog 999.2); `vicmap.vmadd_address` predates the publication marker, so a re-run of that order fails closed as UNPROVEN; no reusable WFS cleanup tooling exists (EXT-03). The pre-v0.1 note that runtime credential material sat inside the checkout was not re-checked at this milestone close — confirm before a production deployment baseline.

## Constraints

- **Runtime**: Python in a Nix-managed environment — extend the existing reproducible flake rather than relying on ambient dependencies
- **Mailbox identity**: Monitor `automations@vegetationlink.com.au` using Microsoft application credentials — this is the dedicated delivery mailbox
- **Trust boundary**: Validate configured Vicmap senders (with a passing DKIM/DMARC/compauth verdict) before following links — mailbox receipt alone is insufficient authorization
- **Target database**: PostgreSQL with PostGIS — audit state and published spatial layers share the operational database platform
- **Layer naming**: Normalize discovered source layer names to lowercase `snake_case` in a configured schema — target selection must be deterministic and safe for PostgreSQL identifiers
- **Availability**: Publish through staging and atomic replacement — readers must never observe partially loaded data
- **Idempotency**: Persist message, order, artifact, checksum, and load outcomes in Postgres — daily retries must not duplicate completed work
- **Operations**: Run daily under systemd with journal logging and failure email — unattended operation must remain diagnosable

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Discover layers automatically from downloaded geodatabases | Each recurring order may contain multiple spatial files and maintaining a manual mapping would be brittle | ✓ Good — v0.1 Phase 2; profiling confirmed against an independent ogrinfo oracle |
| Normalize discovered layer names to lowercase `snake_case` tables | Provides deterministic, PostgreSQL-safe target names | ✓ Good — v0.1 Phase 2; `ADDRESS` → `vicmap.vmadd_address`, collisions hard-stop |
| Replace complete layers through validated staging and atomic swap | Prevents partial data visibility and retains the prior version on failure | ✓ Good — v0.1 Phase 4; single-transaction promotion, shared `xmin` and rollback proven live |
| Prove reader write-denial with a real zero-row INSERT probe, never grant-metadata | A DEFAULT VALUES probe could not reach the not-denied branch on this schema (gid has no default) | ✓ Good — v0.1 Phase 4 (CR-01/bf6c624); broken-grant trip proven live |
| Store delivery and load audit state in Postgres | Provides durable idempotency and a queryable operational history | ⚠️ Partial — `vicmap_audit.staging_validation` gate and `publication` marker exist; full message/order/artifact history is OPS-01 |
| Trust configured sender addresses or domains | Establishes a practical boundary before accepting emailed download links | ✓ Good — v0.1 Phase 1; strengthened by binding to a passing DKIM/DMARC/compauth verdict |
| Report through journald and failure-only email | Keeps routine operation observable without creating success-notification noise | — Pending (OPS-05) |
| Close legacy cleanup (Phase 5) as satisfied by manual action | Operator removed abandoned WFS tables manually; live 2026-09-28 catalog check found none, so building approval-gated deletion tooling had no targets | ✓ Good — CLN-01–CLN-05 satisfied; deletion tool deferred (EXT-03) |
| Prove publication provenance with a durable per-layer marker row (`vicmap_audit.publication`) plus a matching live pg_class OID, never by table name or staging absence | A crash after COMMIT left published tables that a re-run could neither safely re-promote nor distinguish from foreign ones (WINDOWS #16) | ✓ Good — v0.1 Phase 05.1; resume proven live; concurrent-run locking deferred to OPS-05 |
| Accept PROJ's Helmert selection over the vendored ICSM grid for GDA94↔GDA2020 | PROJ rates Helmert more accurate; real-point difference ~2 mm | ⚠️ Revisit — backlog 999.1, pending whether consumers need grid-accurate coordinates |
| Use independent differential oracles for parsing/visibility logic | Hand-written tests shared the implementation's blind spots (24/2000 leaks found only by fuzz) | ✓ Good — v0.1 Phase 1 (html5lib + fuzz), Phase 2 (ogrinfo, pg_get_keywords) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `$gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `$gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-30 after v0.1 milestone*
