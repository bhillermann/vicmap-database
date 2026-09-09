# Phase 1 Controlled Live Acquisition Verification

Status: PASS

**Controlled acquisition:** One connected, uninterrupted invocation of `read_mailbox.py` against the operator-confirmed real trust policy (`vicmap.toml`) authenticated the configured mailbox, selected exactly one candidate message, downloaded its artifact through the approved host, and finalized it — with the candidate-selection, download-target, and artifact-finalization events all captured together from that single run.

## Automated checks

### Connected transaction proof

On 2026-09-09, one invocation of `nix develop --impure --no-write-lock-file path:. --command python read_mailbox.py --config vicmap.toml` ran end to end with no interruption and no retry, producing exactly one `candidate_selected`, one `download_target`, and one `artifact_finalized` event in that order from combined stdout/stderr of that single process. All of the values below come from that one invocation; none is composed from a separate or earlier run.

- Order ID: `OK0VUZ`
- Received at (aware UTC): `2026-09-02T23:35:20+00:00`
- Sender: `n*****y@datashare.maps.vic.gov.au`
- Message fingerprint: `326d1fab5ee70066`
- Approved hostname: `s3.ap-southeast-2.amazonaws.com`
- Path fingerprint: `15d51b9d8bf3b985`
- Artifact bytes: `233089097`
- Artifact SHA-256: `6a7868094ccab5b01fed11aec34587bd7e92bacdc35935b3c2835df21665411b`

The invocation emitted no subject, message body, complete Graph message ID, complete source URL, URL query, credential, bearer token, cookie, or raw exception text.

**Historical note:** This section supersedes the prior composite record, which combined a Plan 01-05 executor's narration of an earlier download with a later mailbox-only recovery scan that stopped before artifact transport. That composite record's message fingerprint, order ID, path fingerprint, and final-artifact byte count/SHA-256 all agree with the connected proof above (same underlying message and artifact), but the message-to-transport correlation itself was not retained from one run until now.

### Authenticated origin

The genuine message's `Authentication-Results` headers carried `dkim=pass`, `dmarc=pass`, and `compauth=pass`. All three verdicts satisfy the configured `required_authentication_results = ["dkim", "dmarc", "compauth"]` in `vicmap.toml`; the connected invocation above would have failed closed as `origin_unauthenticated` before any download contact had any of them not been present and passing. Verdict names only are recorded here — no header text.

### Final artifact

- Final path: `artifacts/Order_OK0VUZ.zip`
- Artifact files at the configured destination: 1
- Partial artifact files: 0
- Artifact bytes: 233089097
- Artifact SHA-256: 6a7868094ccab5b01fed11aec34587bd7e92bacdc35935b3c2835df21665411b
- File type: regular file
- File mode: `0600`
- ZIP integrity: PASS

Both `sha256sum` and an independent Python streaming calculation reproduced the exact byte count and checksum above, matching the `artifact_finalized` event from the same connected invocation.

### Deterministic and runtime-state checks

- Full deterministic suite: PASS (171 tests, 0 failures, 0 skips)
- User-level Vicmap/Vegetation Link scheduled units: absent
- System-level Vicmap/Vegetation Link scheduled units: absent
- Artifact ignore policy: PASS (`artifacts/` is ignored; the finalized artifact does not appear in `git status`)
- Tracked artifact/token runtime paths: absent
- Redaction review: PASS (this file was grepped for message subject/body text, complete Graph message IDs, complete URLs/queries, credentials, tokens, cookies, and raw exception text before commit; none present)

The deterministic suite completed without live network access and verifies the read-only Graph scan surface, full pagination, exact candidate policy (including the void-element suppression fix in Plan 01-12), one-call/no-fallback orchestration, approved-host and bucket/path-prefix download boundary, atomic finalization, closed reason vocabulary, and seeded sensitive-value exclusion.

### Two invocations across this plan's life

Plan 01-11 Task 2 required two live invocations of `read_mailbox.py` across the life of this plan, not one:

1. **First invocation** (against the real trust policy committed in Task 1) closed with `{"event":"failure","hint":"review_ready_message_against_policy","reason":"candidate_ambiguous","stage":"candidate"}`. No artifact host was contacted and no artifact was written. Root cause, diagnosed read-only against the live message: Plan 01-07 placed the void HTML elements `meta` and `link` into `_AnchorCollector`'s non-rendered suppression set. Void elements never emit an end tag, so each bare `<meta>`/`<link>` in the message's `<head>` raised the suppression counter with nothing to lower it, leaving it at a nonzero depth for the rest of the document and suppressing every anchor and visible-text URL in the body — zero archive links were found. This was a parser defect, not a policy rejection, and it did not involve a duplicated archive link. It was fixed in gap-closure Plan 01-12 (`05cfc9b`, `ca014ba`, `da633a8`, `b437c9d`), which added `_VOID_ELEMENTS` and excludes void elements from the suppression counter in `handle_starttag`/`handle_endtag`/`handle_startendtag`, while leaving container suppression, the exactly-one-link rule, and the deliberate non-deduplication of repeated identical URLs unchanged. No allowlist or policy value was relaxed to close this defect; PROHIB-05 was not engaged.
2. **Second invocation** (after Plan 01-12 landed, same unmodified `vicmap.toml`) is the connected transaction proof recorded above: it succeeded, selecting the same message and producing the same artifact identity as the pre-defect recovery evidence.

Per Task 2's own instruction, the first invocation's failure was recorded and not retried with any relaxed policy; the underlying defect was instead fixed in its own auditable plan before the second, successful invocation was made.

## Operator attestations

These are operator-provided facts, not conclusions derived by the automated checks above.

- Tenant scope: PASS — the operator attests that the Microsoft application has read-only `Mail.Read` application permission and is resource-scoped to `automations@vegetationlink.com.au`.
- Legacy checkout token: PASS — the operator attests that the legacy checkout token was revoked and quarantined or removed under operator control.
- Trusted bucket/path prefix: PASS — the operator read the current ready notification and confirmed `https://s3.ap-southeast-2.amazonaws.com/cl-isd-prd-datashare-s3-delivery/` as the exact trusted authority now committed in `vicmap.toml`.

## Disclosure boundary

This record intentionally contains only the configured mailbox in masked form, canonical order ID, aware received timestamp, masked sender, shortened message and path fingerprints, approved hostname, local final path, exact byte count, complete artifact SHA-256, authentication verdict names, and PASS/absence attestations. It does not retain source message content, complete opaque identifiers, complete source URLs or queries, credentials, token values, provider response bodies, or raw exception text.
