# Phase 4: Transactional Publication and Access - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-22
**Phase:** 4-Transactional Publication and Access
**Areas discussed:** Promotion mechanism, Previous-version handling, Reader role & verification, Run summary & evidence

---

## Promotion mechanism

### How a validated staging table becomes the live vicmap.* table

| Option | Description | Selected |
|--------|-------------|----------|
| Metadata move (SET SCHEMA + RENAME) | Catalog-only move; PK/typed-geom/GiST/NOT NULL travel with the table; whole swap is DDL in one short transaction | ✓ |
| Copy (CREATE TABLE AS SELECT) | Re-materialize 4.2M rows, rebuild indexes/constraints, transiently double storage | |

**User's choice:** Metadata move (SET SCHEMA + RENAME) → D-66.

### PUB-01 gate — how Phase 4 establishes staging tables passed validation

| Option | Description | Selected |
|--------|-------------|----------|
| Persisted validation record | Phase 3 marks each layer PASS durably; Phase 4 requires PASS before promoting | ✓ |
| Re-run validation in Phase 4 | Re-execute D-56 checks against staging; repeats a full 4.2M-row scan | |
| Trust presence + manifest digest | Treat a matching staging table as validated; verify manifest digest only | |

**User's choice:** Persisted validation record → D-68.

### Index/constraint names after the move

| Option | Description | Selected |
|--------|-------------|----------|
| Rename to canonical | Live table gets {table}_pkey / {table}_geom_idx etc.; predictable published contract | ✓ |
| Accept timestamped names | Keep staging-minted names; cosmetic, nothing binds to them | |
| You decide | Claude discretion | |

**User's choice:** Rename to canonical → D-67.

### Where the durable validation record comes from (follow-up to the PUB-01 gate)

| Option | Description | Selected |
|--------|-------------|----------|
| Filesystem sidecar (back-fill Phase 3) | validation.json in run dir, analog of D-32 provenance sidecar | |
| Durable Postgres audit row | Phase 3 writes validation outcomes to an audit table | ✓ |
| Capture the event stream | Phase 4 reads a JSONL file the operator captured from stdout | |

**User's choice:** Durable Postgres audit row → D-69/D-70.
**Notes:** Claude flagged this pulls a slice of OPS-01 (deferred) forward; scope was then bounded in the two follow-ups below.

### Validation-record scope

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal publication-gate record | run_ts, manifest digest, per-layer verdict + D-56 metrics only | ✓ |
| Broader audit foundation | First slice of the full OPS-01 audit schema | |

**User's choice:** Minimal publication-gate record → D-69.

### Validation-record home

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated audit schema (operator-provisioned) | New vicmap_audit schema via the D-60 script; loader granted write; verified by preflight | ✓ |
| Control table in vicmap_staging | Persistent control table inside the ephemeral-table staging schema | |
| You decide | Claude discretion (not vicmap; provisioned by D-60 script) | |

**User's choice:** Dedicated audit schema → D-70.

---

## Previous-version handling

### What happens to the outgoing vicmap.* table on a successful publish

| Option | Description | Selected |
|--------|-------------|----------|
| Drop it in the same transaction | Single live generation; failure covered by rollback; no storage growth | ✓ |
| Keep one _previous generation | Manual post-commit rollback; ~one extra order's storage | |
| Keep timestamped history | Full history; grows every run; needs retention policy | |

**User's choice:** Drop it in the same transaction → D-71.
**Notes:** PUB-03's failure case is satisfied structurally by the single-transaction rollback, independent of retention.

---

## Reader role & verification

### Reader role provisioning

| Option | Description | Selected |
|--------|-------------|----------|
| Operator by-hand (D-60 pattern) | Reader created once by the superuser script, granted USAGE; verified by preflight | ✓ |
| Pipeline creates it | Loader creates role/grants; requires CREATEROLE, widening loader privilege | |

**User's choice:** Operator by-hand → D-72.

### How PUB-05 non-owner access is proven

| Option | Description | Selected |
|--------|-------------|----------|
| Real reader login (own credential) | Reader has LOGIN + VICMAP_READER_PASSWORD via opnix; fresh connection runs discovery + spatial query + denied write | ✓ |
| SET ROLE from loader connection | Loader (a member of the reader role) does SET ROLE; no new secret, but not a real login | |

**User's choice:** Real reader login → D-74.

### When the reader's per-table SELECT grant is applied

| Option | Description | Selected |
|--------|-------------|----------|
| Inside the publish transaction | Tables become visible and readable atomically; no ungranted window | ✓ |
| Separate post-commit step | Simpler per-statement, but a brief window without reader access | |
| You decide | Claude discretion | |

**User's choice:** Inside the publish transaction → D-73.

---

## Run summary & evidence

### How EVID-01 is emitted

| Option | Description | Selected |
|--------|-------------|----------|
| Both: durable file + stream event | Redacted summary.json in run dir + final summary event on the JSONL stream | ✓ |
| Final summary event only | One SummaryEvent on the stream; no durable file | |
| Standalone summary.json only | Durable file, no dedicated event | |

**User's choice:** Both → D-75.

### How cross-phase facts are gathered

| Option | Description | Selected |
|--------|-------------|----------|
| Re-read the durable per-phase artifacts | Read provenance sidecar + manifest.json + vicmap_audit record, add Phase 4 facts | ✓ |
| Thread a growing record through the phases | Each phase appends its slice to one evolving object | |

**User's choice:** Re-read the durable per-phase artifacts → D-76.

### What owns producing EVID-01

| Option | Description | Selected |
|--------|-------------|----------|
| New publish_order.py assembles it | Phase 4 CLI does promote + grant + verify + summary; one CLI per phase | ✓ |
| New end-to-end orchestrator CLI | Top-level command runs Phases 1→4 (OPS-05 deferred scope) | |
| You decide | Claude discretion | |

**User's choice:** New publish_order.py → D-77.

---

## Claude's Discretion

- Exact representative spatial query for PUB-05 (toward a GiST-exercising ST_Intersects/&& predicate against a Victoria bbox + catalog discovery + write-denial).
- New Stage/ReasonCode members in evidence.py for publication/grant/verification/validation-record boundaries.
- Exact schema/columns of the vicmap_audit validation-record table.
- Reader-role name placement in vicmap.toml and the 1Password item path for VICMAP_READER_PASSWORD.
- Module layout for the publish/reader/verification code.
- Filename/format of summary.json and the shape of the final summary event.
- Whether the write-denial check uses INSERT or UPDATE.
- Per-layer vs batched DDL within the single promotion transaction.

## Deferred Ideas

- Full OPS-01 durable audit subsystem (vicmap_audit is a minimal slice only).
- Idempotency/replay protection for a re-run publish (OPS-02).
- Top-level end-to-end orchestrator / daily systemd run (OPS-05).
- Retaining previous published generations (_previous or timestamped history + retention).
- Failed-staging age-based sweep (D-65 second half).
- Extent sanity envelope (carried from Phase 3).
- Auto-pruning old run directories (carried from Phase 2/3).
- Widening the format allowlist (carried).
