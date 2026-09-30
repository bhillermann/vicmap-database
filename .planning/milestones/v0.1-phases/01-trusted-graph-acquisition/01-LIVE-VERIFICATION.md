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
- Legacy checkout token: VERIFIED (not an attestation) — the current code uses `MemoryTokenBackend` (`vicmap_acquire/graph.py:12` import, `:119` use), so no OAuth token is ever written to disk. The `token/` directory does not exist in the working tree, and `/token/` is gitignored (`.gitignore:3`), so the pre-phase-01 on-disk token cache (`token/my_token.txt`) cannot be reintroduced by this code path.
- Redaction review: PASS (this file was grepped for message subject/body text, complete Graph message IDs, complete URLs/queries, credentials, tokens, cookies, and raw exception text before commit; none present)

The deterministic suite completed without live network access and verifies the read-only Graph scan surface, full pagination, exact candidate policy (including the void-element suppression fix in Plan 01-12), one-call/no-fallback orchestration, approved-host and bucket/path-prefix download boundary, atomic finalization, closed reason vocabulary, and seeded sensitive-value exclusion.

### Two invocations across this plan's life

Plan 01-11 Task 2 required two live invocations of `read_mailbox.py` across the life of this plan, not one:

1. **First invocation** (against the real trust policy committed in Task 1) closed with `{"event":"failure","hint":"review_ready_message_against_policy","reason":"candidate_ambiguous","stage":"candidate"}`. No artifact host was contacted and no artifact was written. Root cause, diagnosed read-only against the live message: Plan 01-07 placed the void HTML elements `meta` and `link` into `_AnchorCollector`'s non-rendered suppression set. Void elements never emit an end tag, so each bare `<meta>`/`<link>` in the message's `<head>` raised the suppression counter with nothing to lower it, leaving it at a nonzero depth for the rest of the document and suppressing every anchor and visible-text URL in the body — zero archive links were found. This was a parser defect, not a policy rejection, and it did not involve a duplicated archive link. It was fixed in gap-closure Plan 01-12 (`05cfc9b`, `ca014ba`, `da633a8`, `b437c9d`), which added `_VOID_ELEMENTS` and excludes void elements from the suppression counter in `handle_starttag`/`handle_endtag`/`handle_startendtag`, while leaving container suppression, the exactly-one-link rule, and the deliberate non-deduplication of repeated identical URLs unchanged. No allowlist or policy value was relaxed to close this defect; PROHIB-05 was not engaged.
2. **Second invocation** (after Plan 01-12 landed, same unmodified `vicmap.toml`) is the connected transaction proof recorded above: it succeeded, selecting the same message and producing the same artifact identity as the pre-defect recovery evidence.

Per Task 2's own instruction, the first invocation's failure was recorded and not retried with any relaxed policy; the underlying defect was instead fixed in its own auditable plan before the second, successful invocation was made.

## Operator attestations

These are operator-provided facts, not conclusions derived by the automated checks above, except where a sub-bullet below is explicitly marked as code-verified.

- **Tenant scope: MIXED (attested condition, verified code boundary, accepted residual risk).**
  - Attested by operator: the application holds read-only `Mail.Read` application permission, but it is **tenant-wide, not scoped to** `automations@vegetationlink.com.au`. Per-mailbox scoping was attempted and is not available in this tenant/app configuration. The same credentials can also reach the MFA inbox and the receipt-tracking user inbox.
  - Verified in code (not an attestation): the mailbox is pinned from `vicmap.toml` and never discovered at runtime (`vicmap_acquire/graph.py:146`, `self._account.mailbox(resource=self._mailbox_address)`), and any folder other than `Inbox` is rejected before any request is issued (`tests/test_graph.py::GraphReadOnlyEnforcementTest::test_prohib_01_non_inbox_folder_rejected_before_any_request`). This code path reads exactly one mailbox.
  - Residual risk, recorded openly and accepted: the credential itself is broader than the code's use of it. Anyone holding it can read every mailbox in the tenant, read-only. This is a known and accepted condition, not an unresolved gap.
- Trusted bucket/path prefix: PASS — the operator read the current ready notification and confirmed `https://s3.ap-southeast-2.amazonaws.com/cl-isd-prd-datashare-s3-delivery/` as the exact trusted authority now committed in `vicmap.toml`.

## Prohibition Disposition

Nothing below was inferred from a passing test. Each disposition is a statement the operator made explicitly, reviewing the statement, the requirement it protects, the named enforcement tests, and the stated residual risk.

| Identifier | Statement | Enforcement evidence | Disposition | Accepted-by-and-date |
|---|---|---|---|---|
| PROHIB-01 | No mailbox mutation while scanning | `tests/test_graph.py::GraphReadOnlyEnforcementTest::test_prohib_01_complete_scan_and_mime_use_only_read_requests`, `::test_prohib_01_no_recorded_request_touches_a_mutation_endpoint`, `::test_prohib_01_public_surface_exposes_no_mutation_named_callable`, `::test_prohib_01_non_inbox_folder_rejected_before_any_request` | accepted | bhillermann@vegetationlink.com.au, 2026-09-14 |
| PROHIB-02 | No Graph bearer, cookie, or ambient netrc authority reaching the artifact host | `tests/test_download.py::test_prohib_02_no_ambient_or_graph_authority_reaches_artifact_host`, `::test_clean_session_uses_manual_redirects_tls_and_timeout_tuple` | accepted | bhillermann@vegetationlink.com.au, 2026-09-14 |
| PROHIB-03 | No publication or overwrite from an incomplete, failed, or over-limit stream | `tests/test_download.py::test_two_concurrent_finalizers_have_exactly_one_complete_winner`, `::test_post_link_cleanup_failure_still_reports_a_committed_success`, `::test_pre_commit_timeout_family_leaves_no_final_path`, `::test_pre_commit_over_limit_family_leaves_no_final_path`, `::test_pre_commit_short_write_family_leaves_no_final_path`, `::test_pre_commit_declared_length_mismatch_family_leaves_no_final_path`, `::test_pre_commit_existing_final_path_family_is_left_untouched`, `::test_keyboard_interrupt_cleans_private_state_and_reraises` | accepted | bhillermann@vegetationlink.com.au, 2026-09-14 |
| PROHIB-04 | No substitution of an older or different order's artifact after the selected candidate fails | `tests/test_evidence.py::test_expired_newest_download_stops_after_one_attempt_without_fallback` | accepted | bhillermann@vegetationlink.com.au, 2026-09-14 |
| PROHIB-05 | No automatic widening of the trust policy from a received message | `tests/test_download.py::test_prefix_authority_narrows_the_allowed_host`, `::test_redirect_leaving_the_configured_prefix_is_rejected_after_one_contact`, `::test_relative_redirect_leaving_the_configured_prefix_is_rejected_before_recontact`, `::test_allowed_url_prefixes_rejects_seven_invalid_shapes`; `tests/test_origin.py` unauthenticated-origin rejections; the operator-only prefix change made in Task 1 | accepted | bhillermann@vegetationlink.com.au, 2026-09-14 |

Residual risk, recorded as known and accepted rather than unresolved, for each accepted row:

- **PROHIB-01:** Concurrent server-side mutation by another principal is not audited by these tests.
- **PROHIB-02:** A future change reusing the Graph connection would not necessarily be caught by these tests.
- **PROHIB-03:** The link-to-fsync crash window is unsimulated.
- **PROHIB-04:** None identified.
- **PROHIB-05:** Operator broadening of the allowlist is a policy decision, not a code path, and is therefore outside what any test can enforce. This plan's own history provides live evidence of the boundary holding: when the ready message failed recognition (the first invocation recorded above), the defect was repaired under Plan 01-12 and no trust value — no allowlist, prefix, or authentication-verdict requirement — was relaxed to force the acquisition to pass.

## Disclosure boundary

This record intentionally contains only the configured mailbox in masked form, canonical order ID, aware received timestamp, masked sender, shortened message and path fingerprints, approved hostname, local final path, exact byte count, complete artifact SHA-256, authentication verdict names, and PASS/absence attestations. It does not retain source message content, complete opaque identifiers, complete source URLs or queries, credentials, token values, provider response bodies, or raw exception text.
