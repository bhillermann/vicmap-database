# Phase 1: Trusted Graph Acquisition - Context

**Gathered:** 2026-09-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Authenticate to the configured automation mailbox, inspect a bounded Inbox window, select exactly one trusted Vicmap ready-order message, and download its artifact through a constrained HTTPS path. Report redacted provenance, byte count, and checksum. Archive extraction, geospatial inspection, database loading, durable scan state, and batch acquisition remain outside this phase.

</domain>

<decisions>
## Implementation Decisions

### Candidate Recognition
- **D-01:** Qualifying senders must appear on an exact email-address allowlist. The Phase 1 allowlist initially contains only `noreply@datashare.maps.vic.gov.au`.
- **D-02:** Qualifying order IDs must appear on a configured allowlist. Phase 1 initially contains only proof order `OK0VUZ`.
- **D-03:** Match the exact ready subject template `Your DataShare Order {ORDER_ID} is ready to download` case-insensitively. A corresponding confirmation email is not required.
- **D-04:** Inspect the plain-text body first and fall back to HTML when plain text is unavailable or contains no candidate link.
- **D-05:** Require exactly one archive link whose filename matches `Order_{ORDER_ID}.zip`. Missing, duplicate, or ambiguous matches block acquisition.
- **D-06:** Reject and safely log a mismatch between subject order ID and archive filename order ID. A deliberate configuration override may permit it; there is no ad-hoc interactive bypass.

### Deterministic Selection
- **D-07:** Scan a configurable received-time lookback with a default of 15 days. Phase 1 does not persist a last-scan watermark.
- **D-08:** Paginate through every Inbox message in the lookback window; do not impose a secondary message-count cap.
- **D-09:** Select the newest valid candidate by Graph `receivedDateTime` across the entire configured order-ID allowlist.
- **D-10:** Break equal-timestamp ties using stable Graph message-ID ordering. Never display the full opaque message ID.
- **D-11:** Begin the bounded download automatically after successful selection; do not require a second confirmation.
- **D-12:** If the selected newest candidate cannot be downloaded or has expired, stop with an error. Do not fall back silently to an older candidate.

### Download Trust Boundary
- **D-13:** Require HTTPS and an exact hostname allowlist, initially containing only `s3.ap-southeast-2.amazonaws.com`.
- **D-14:** Permit redirects only when every hop uses HTTPS and the destination hostname remains allowlisted.
- **D-15:** Enforce a configurable artifact-size limit with a default of 10 GiB.
- **D-16:** Use separate configurable connection and stalled-read timeouts. Do not impose a fixed total duration while bytes continue arriving.

### Redacted Operator Evidence
- **D-17:** Identify the selected message using its order ID, received timestamp, masked sender, and shortened message-ID fingerprint. Do not print its subject or body.
- **D-18:** Represent the download target using the approved hostname and a fingerprint of the redacted path. Never print the complete URL.
- **D-19:** Report periodic bytes and percentage when total size is known, followed by final byte count and SHA-256 checksum.
- **D-20:** On failure, report the failed stage, a safe reason code, redacted identifiers, and a remediation hint. Do not emit raw exception text.

### the agent's Discretion
- Exact CLI/configuration structure and safe default values for connection timeout, stalled-read timeout, and progress-reporting interval.
- The fingerprint algorithm and display length, provided identifiers remain useful for correlation without exposing their full values.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope and Requirements
- `.planning/PROJECT.md` — Defines the milestone goal, trust boundary, constraints, and deferred operational hardening.
- `.planning/REQUIREMENTS.md` — Defines Phase 1 requirements `MAIL-01` through `MAIL-05` and explicit out-of-scope behavior.
- `.planning/ROADMAP.md` — Defines the fixed Phase 1 boundary and success criteria.

No external specifications or ADRs were referenced during discussion.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `read_mailbox.py`: Existing O365 client-credentials authentication, token backend, mailbox selection, and Inbox access provide the starting integration.
- `flake.nix`: Existing pinned Python/O365 environment and opnix-backed credential injection should be extended rather than replaced with ambient dependencies.

### Established Patterns
- Microsoft Graph access uses `O365.Account` with application credentials and the `.default` scope.
- Configuration currently comes from environment variables, while mailbox address, Inbox name, token path, and query behavior are hard-coded.
- Current message enumeration is not actually bounded: a limited result is assigned and discarded before an unbounded second call.

### Integration Points
- Refactor `read_mailbox.py` behind a guarded entry point so Graph access does not run on import.
- Replace raw message printing with project-owned candidate recognition, deterministic selection, redaction, and download boundaries.
- Preserve `automations@vegetationlink.com.au` as the configured mailbox identity and extend the Nix environment for any new runtime or test dependencies.

</code_context>

<specifics>
## Specific Ideas

- Confirmation subjects use `Your DataShare Order OK0VUZ is confirmed`; the stable order ID maps to a package set, but confirmation lookup is not required in Phase 1.
- Ready subjects use `Your DataShare Order OK0VUZ is ready to download`.
- The ready body states that the order is ready, includes an `Order_OK0VUZ.zip` link, and says the link expires after 15 days.
- An expired delivery may return “Could not find the file to download”; surface this through a safe failure code and remediation hint.

</specifics>

<deferred>
## Deferred Ideas

- Controlled acquisition and later import of the expiring backlog archives. Manually preserved archives should remain immutable source artifacts with order ID, original filename, download timestamp, source host, byte size, and SHA-256 recorded. This is separate from Phase 1's one-artifact proof.
- Durable “all messages since last scan” state belongs with the future Postgres audit/idempotency work, not this phase.

</deferred>

---

*Phase: 01-trusted-graph-acquisition*
*Context gathered: 2026-09-02*
