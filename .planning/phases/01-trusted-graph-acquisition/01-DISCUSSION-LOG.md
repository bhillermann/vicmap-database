# Phase 1: Trusted Graph Acquisition - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-02
**Phase:** 1-trusted-graph-acquisition
**Areas discussed:** Candidate recognition, Deterministic selection, Download trust boundary, Redacted operator evidence

---

## Candidate Recognition

| Decision | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Sender trust | Exact addresses; domains; addresses plus domains | Exact address allowlist |
| Ready marker | Subject only; subject plus matching link; flexible subject/body markers | Exact ready subject plus exactly one matching archive link |
| Confirmation dependency | Required; optional context; unnecessary | Ready email is sufficient |
| Order scope | One configured ID; any ID; configured ID allowlist | Configured allowlist, initially `OK0VUZ` |
| Subject tolerance | Exact case-sensitive; exact case-insensitive; flexible markers | Exact case-insensitive template |
| Body format | Plain only; HTML only; plain then HTML; require agreement | Plain text, then HTML fallback |
| ID mismatch | Reject; ignore filename; interactive override; configured override | Reject and log, with deliberate config override available |

**User's choice:** Exact allowlists and strict correlation among sender, subject order ID, and archive filename.
**Notes:** The only current sender is `noreply@datashare.maps.vic.gov.au`; `OK0VUZ` is the Phase 1 proof order and maps consistently to its package set.

---

## Deterministic Selection

| Decision | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Duplicate candidates | Newest; oldest; reject duplicates | Newest by Graph receive time |
| Timestamp tie | Message ID; URL ordering; reject | Stable message-ID ordering |
| Post-selection action | Confirm; automatic download; dry-run default | Automatic download |
| Inbox bound | Count; time; both; persisted last-scan state | Configurable time window |
| Default window | 30 days; 15 days; 7 days | 15 days |
| Several allowed orders | Explicit target; newest globally; one per order | Newest globally |
| Failed newest link | Stop; same-order fallback; any fallback | Stop without fallback |
| Secondary cap | Failing cap; silent cap; full window pagination | No count cap |

**User's choice:** Select one globally newest valid candidate from a fully paginated 15-day window and download it automatically.
**Notes:** A persisted scan watermark was considered and deferred because Phase 1 has no durable audit state.

---

## Download Trust Boundary

| Decision | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Host policy | Exact host; host plus path prefix; broad AWS domain | Exact hostname allowlist |
| Redirects | Allowlisted HTTPS hops; none; arbitrary HTTPS | Allowlisted HTTPS hops only |
| Size limit | 10 GiB; 5 GiB; 1 GiB | Configurable 10 GiB default |
| Timeouts | Connect plus stalled-read; overall; connect only | Connect plus stalled-read |

**User's choice:** Strict host and redirect validation with bounded size and stalled-transfer detection.
**Notes:** Initial allowed host is `s3.ap-southeast-2.amazonaws.com`; progressing downloads have no fixed overall timeout.

---

## Redacted Operator Evidence

| Decision | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Message identity | Recommended redacted fields; minimal fields; redacted subject | Order ID, time, masked sender, ID fingerprint |
| URL identity | Host plus path fingerprint; host only; partial/full URL; none | Host plus redacted path fingerprint |
| Progress | Periodic percentage; final only; byte count only | Periodic progress plus final evidence |
| Failures | Safe structured detail; generic detail; raw exception | Safe structured detail and remediation |

**User's choice:** Provide reproducible, actionable evidence while never printing message content, complete URLs, opaque IDs, or raw exceptions.
**Notes:** Successful download evidence ends with byte count and SHA-256.

---

## the agent's Discretion

- CLI/configuration shape, concrete timeout defaults, progress interval, and identifier fingerprint presentation.

## Deferred Ideas

- Controlled acquisition and later import of the expiring backlog order archives.
- Durable last-scan tracking through the future Postgres audit/idempotency model.
