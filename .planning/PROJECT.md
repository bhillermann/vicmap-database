# Vicmap Database

## What This Is

Vicmap Database is an automated delivery pipeline for spatial datasets used by Vegetation Link's GIS work. It monitors `automations@vegetationlink.com.au` for recurring Vicmap order updates, downloads ready geodatabase packages, discovers their spatial layers, and safely refreshes corresponding PostGIS tables on a daily systemd schedule.

## Core Value

Vicmap updates must reach the correct PostGIS layers automatically without exposing users to partial, invalid, or duplicate data loads.

## Current Milestone: v0.1 End-to-End Vicmap Import Proof

**Goal:** Prove that one real Vicmap ready-order email can be processed end to end into queryable PostGIS production tables.

**Target features:**
- Authenticate with Microsoft Graph, locate a ready-order email, and download its order archive
- Unpack and read the delivered geospatial files
- Load data through staging into queryable production tables in a dedicated `vicmap` schema
- Inventory abandoned WFS-attempt tables and remove only an explicitly approved list

## Requirements

### Validated

- ✓ A reproducible Nix development environment supplies Python and the O365 SDK — existing
- ✓ Microsoft application credentials are injected from 1Password through opnix — existing
- ✓ The application can authenticate with Microsoft Graph and access the `automations@vegetationlink.com.au` Inbox — existing
- ✓ Load delivered layers into staging and migrate them into production tables in a dedicated `vicmap` schema — Phase 4
- ✓ Make the resulting production tables queryable by database users — Phase 4

### Active

- [ ] Authenticate with Microsoft Graph and read messages from the automation mailbox
- [ ] Identify a real Vicmap ready-order email, download its order archive, and unpack it
- [ ] Discover and read the delivered geospatial files
- [ ] Connect to the existing local PostGIS instance on port 5432
- [ ] Inventory abandoned WFS-attempt tables and remove only tables explicitly approved for deletion

### Out of Scope

- Manual order-to-dataset-to-table mappings — layer targets will be discovered and normalized from geodatabase layer names
- Incremental feature upserts or append-only loading — each delivered layer is a complete snapshot replaced atomically
- Mailbox folders as authoritative workflow state — Postgres audit records govern idempotency and processing history
- Processing messages from unconfigured senders — sender allowlisting is the selected trust boundary
- Success notification emails — normal operation is visible through structured journal logs; email is reserved for failures
- Daily scheduling, failure notifications, durable audit history, and comprehensive idempotency — deferred until after the v0.1 end-to-end proof

## Context

Vicmap sends two messages for an update to an existing order: an initial confirmation followed later by a ready notification whose download link is then live. An order number remains stable across updates and may deliver multiple spatial files. The present repository is a prototype: `read_mailbox.py` authenticates with application credentials, opens the target Inbox, and prints messages, while `flake.nix` supplies the O365 dependency and opnix-backed secrets.

No message interpretation, delivery ledger, download client, geodatabase inspection, PostGIS loader, transactional swap, notification mechanism, tests, or production service currently exists. Runtime credential material is also present inside the checkout and must be moved out of the repository and protected before establishing a production deployment baseline.

## Constraints

- **Runtime**: Python in a Nix-managed environment — extend the existing reproducible flake rather than relying on ambient dependencies
- **Mailbox identity**: Monitor `automations@vegetationlink.com.au` using Microsoft application credentials — this is the dedicated delivery mailbox
- **Trust boundary**: Validate configured Vicmap senders before following links — mailbox receipt alone is insufficient authorization
- **Target database**: PostgreSQL with PostGIS — audit state and published spatial layers share the operational database platform
- **Layer naming**: Normalize discovered source layer names to lowercase `snake_case` in a configured schema — target selection must be deterministic and safe for PostgreSQL identifiers
- **Availability**: Publish through staging and atomic replacement — readers must never observe partially loaded data
- **Idempotency**: Persist message, order, artifact, checksum, and load outcomes in Postgres — daily retries must not duplicate completed work
- **Operations**: Run daily under systemd with journal logging and failure email — unattended operation must remain diagnosable

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Discover layers automatically from downloaded geodatabases | Each recurring order may contain multiple spatial files and maintaining a manual mapping would be brittle | — Pending |
| Normalize discovered layer names to lowercase `snake_case` tables | Provides deterministic, PostgreSQL-safe target names | — Pending |
| Replace complete layers through validated staging and atomic swap | Prevents partial data visibility and retains the prior version on failure | ✓ Phase 4 — single-transaction promote_order; rollback-preserves-prior-tables proven live (LivePromotionRollbackTest) |
| Prove reader write-denial with a real zero-row INSERT probe, never grant-metadata | A DEFAULT VALUES probe could not reach the not-denied branch on this schema (gid has no default) | ✓ Phase 4 (CR-01/bf6c624) — broken-grant trip proven live (LiveReaderWriteNotDeniedTest) |
| Store delivery and load audit state in Postgres | Provides durable idempotency and a queryable operational history | — Pending |
| Trust configured sender addresses or domains | Establishes a practical boundary before accepting emailed download links | — Pending |
| Report through journald and failure-only email | Keeps routine operation observable without creating success-notification noise | — Pending |

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
*Last updated: 2026-09-25 after Phase 4*
