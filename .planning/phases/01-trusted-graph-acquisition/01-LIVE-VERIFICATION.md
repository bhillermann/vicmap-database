# Phase 1 Controlled Live Acquisition Verification

Status: PASS

**Controlled acquisition:** The prior Plan 01-05 executor reported that one qualifying current message was selected, one bounded download completed, and the final safe event's byte count and SHA-256 matched an independent on-disk calculation. The quota interruption occurred during documentation, after the artifact had been finalized.

## Automated checks

### Redacted correlation recovery

The original safe correlation output was not retained. On 2026-09-09, after explicit operator approval, one bounded read-only recovery scan used the production Graph adapter, the configured 15-day Inbox window, selective MIME retrieval, candidate policy, and local URL validation. It stopped before artifact transport: the artifact host was not contacted and the artifact was not downloaded or overwritten.

- Mailbox: `a*********s@vegetationlink.com.au`
- Order ID: `OK0VUZ`
- Received at: `2026-09-02T23:35:20+00:00`
- Sender: `n*****y@datashare.maps.vic.gov.au`
- Message fingerprint: `326d1fab5ee70066`
- Approved hostname: `s3.ap-southeast-2.amazonaws.com`
- Path fingerprint: `15d51b9d8bf3b985`
- Recovery result: PASS

The correlation recovery emitted no subject, message body, complete Graph message ID, complete source URL, URL query, credential, bearer token, cookie, or raw exception.

### Final artifact

- Final path: `artifacts/Order_OK0VUZ.zip`
- Artifact files at the configured destination: 1
- Partial artifact files: 0
- Artifact bytes: 233089097
- Artifact SHA-256: 6a7868094ccab5b01fed11aec34587bd7e92bacdc35935b3c2835df21665411b
- File type: regular file
- File mode: `0600`
- ZIP integrity: PASS

Both `sha256sum` and an independent Python streaming calculation reproduced the exact byte count and checksum above. The values match the successful controlled-run result reported by the prior executor.

### Deterministic and runtime-state checks

- Full deterministic suite: PASS (81 tests, 0 failures, 0 skips)
- User-level Vicmap/Vegetation Link scheduled units: absent
- System-level Vicmap/Vegetation Link scheduled units: absent
- Artifact ignore policy: PASS (`artifacts/` is ignored)
- Tracked artifact/token runtime paths: absent
- Redaction review: PASS

The deterministic suite completed without live network access and verifies the read-only Graph scan surface, full pagination, exact candidate policy, one-call/no-fallback orchestration, approved-host download boundary, atomic finalization, closed reason vocabulary, and seeded sensitive-value exclusion.

## Operator attestations

These are operator-provided facts, not conclusions derived by the automated checks above.

- Tenant scope: PASS — the operator attests that the Microsoft application has read-only `Mail.Read` application permission and is resource-scoped to `automations@vegetationlink.com.au`.
- Legacy checkout token: PASS — the operator attests that the legacy checkout token was revoked and quarantined or removed under operator control.

## Disclosure boundary

This record intentionally contains only the configured mailbox in masked form, canonical order ID, aware received timestamp, masked sender, shortened message and path fingerprints, approved hostname, local final path, exact byte count, complete artifact SHA-256, and PASS/absence attestations. It does not retain source message content, complete opaque identifiers, complete source URLs or queries, credentials, token values, provider response bodies, or raw exception text.
