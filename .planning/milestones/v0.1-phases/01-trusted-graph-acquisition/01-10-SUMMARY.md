---
phase: 01-trusted-graph-acquisition
plan: 10
subsystem: acquisition
tags: [python, o365, graph-api, mailbox, testing]

requires:
  - phase: 01-06
    provides: The GraphMailbox adapter, MessageMetadata, and the closed GraphFailure hierarchy this plan's connection-level MIME rewrite builds on
provides:
  - "get_message_mime issues exactly one connection-level GET to the Graph MIME value endpoint (/messages/{id}/$value), replacing the two-request path that first fetched an ordinary message representation"
  - "Connection-level request-counting regressions (_RecordingConnection) that assert the metadata-first boundary against recorded (method, url) requests instead of an in-memory SDK object, closing review warning WR-03 / verification warning W-01"
  - "Runtime enforcement evidence for PROHIB-01 (MAIL-02): GET-only method set across a complete scan plus one MIME retrieval, no mutation-path-segment requests, no mutation-named public callables, and non-Inbox folder rejection before any request"
affects: [01-11, trusted-graph-acquisition]

actuals:
  tokens: 4818
  tasks: 2
  commits: 2
commits: 2
plan_head_before: 51ef1fadfc4ce493d9c5300dfe96d2ca73e186ec

tech-stack:
  added: []
  patterns:
    - "Connection-level request-double testing: a _RecordingConnection wired as a fake folder's `con` attribute records (method, url) tuples, proving production request shape rather than in-memory call order"
    - "MIME retrieval builds its URL through the confirmed folder's own build_url (ApiComponent.build_url in the installed O365 2.1.0 SDK), keeping the mailbox resource segment exactly the users/{address} scope authenticate_and_confirm already established"

key-files:
  created: []
  modified:
    - vicmap_acquire/graph.py
    - tests/test_graph.py

key-decisions:
  - "Read the installed O365 2.1.0 SDK source directly (message.py's own get_mime_content, mailbox.py's Folder._endpoints) to confirm the exact MIME endpoint shape (/messages/{id}/$value) and that Folder exposes build_url via ApiComponent, rather than assuming the shape."
  - "get_message_mime calls _confirmed_folder() to a local variable before evaluating self._mime_url(...), rather than the plan text's literal `self._folder.con.get(self._mime_url(...))` — Python evaluates `self._folder` before evaluating the argument expression, so on the first call (self._folder is still None) the literal form would raise AttributeError before _mime_url's internal _confirmed_folder() call could set it."
  - "Bundled Task 1 and Task 2 into one RED commit and one GREEN commit: Task 2 adds no production code (its PROHIB-01 assertions run against the connection-level double introduced for Task 1), so its tests only pass once Task 1's implementation lands — the same dependency a separate RED/GREEN pair for Task 2 would still express, just without an intervening commit."
  - "Removed _MetadataFolder.get_message and get_message_calls (unused once get_message_mime no longer calls folder.get_message) rather than leaving them as dead fake surface."

patterns-established:
  - "Fake folder/connection doubles that route both metadata pagination and MIME retrieval through a single shared con object, so request-count assertions ('N pages plus one MIME retrieval') are connection-observable rather than inferred from call-order on unrelated fakes."

requirements-completed:
  - MAIL-01
  - MAIL-02

coverage:
  - id: D1
    description: "get_message_mime issues exactly one connection-level GET request to the MIME value endpoint for a valid complete Graph ID, using the confirmed folder's own connection and build_url."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_graph.py#GraphMetadataBoundaryTest.test_selective_mime_fetches_by_complete_id_only_on_explicit_call"
        status: pass
      - kind: unit
        ref: "tests/test_graph.py#GraphMetadataBoundaryTest.test_scan_plus_one_mime_retrieval_issues_one_request_per_page_plus_one"
        status: pass
    human_judgment: false
  - id: D2
    description: "A message ID containing reserved URL characters is percent-encoded with an empty safe set, producing one well-formed request rather than a malformed or split one."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_graph.py#GraphMetadataBoundaryTest.test_mime_url_percent_encodes_reserved_characters_into_one_request"
        status: pass
    human_judgment: false
  - id: D3
    description: "A non-200 response, non-bytes content, a blank message ID, and a connection exception each raise GraphScanFailed without leaking response text, headers, or exception text into the failure's string form or repr."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_graph.py#GraphMetadataBoundaryTest.test_mime_retrieval_failure_cases_raise_graphscanfailed_without_leaking"
        status: pass
      - kind: unit
        ref: "tests/test_graph.py#GraphMetadataBoundaryTest.test_paging_and_mime_provider_errors_do_not_escape"
        status: pass
    human_judgment: false
  - id: D4
    description: "Runtime enforcement evidence for PROHIB-01: across a complete multi-page scan plus one MIME retrieval every recorded connection request method is GET, no recorded URL touches a mutation-implying path segment, no public GraphMailbox callable has a mutation-implying name, and a non-Inbox folder name is rejected before any connection request."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_graph.py#GraphReadOnlyEnforcementTest.test_prohib_01_complete_scan_and_mime_use_only_read_requests"
        status: pass
      - kind: unit
        ref: "tests/test_graph.py#GraphReadOnlyEnforcementTest.test_prohib_01_no_recorded_request_touches_a_mutation_endpoint"
        status: pass
      - kind: unit
        ref: "tests/test_graph.py#GraphReadOnlyEnforcementTest.test_prohib_01_public_surface_exposes_no_mutation_named_callable"
        status: pass
      - kind: unit
        ref: "tests/test_graph.py#GraphReadOnlyEnforcementTest.test_prohib_01_non_inbox_folder_rejected_before_any_request"
        status: pass
    human_judgment: false

duration: 11min
completed: 2026-09-09
status: complete
---

# Phase 01 Plan 10: Connection-Level MIME Boundary and PROHIB-01 Evidence Summary

**`get_message_mime` now issues one connection-level GET to `/messages/{id}/$value` (verified against a request-recording double), and PROHIB-01 has runtime, request-level enforcement evidence instead of source-text inspection.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-09-09T05:41:04Z
- **Completed:** 2026-09-09T05:51:45Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Replaced the two-request MIME path (`Folder.get_message(...)` then `message.get_mime_content()`) with a single `folder.con.get(self._mime_url(graph_message_id))` call, closing review warning WR-03 / verification warning W-01: with the installed O365 2.1.0 SDK, the old path issued a GET for the ordinary message representation before a second GET for MIME.
- Added `_MIME_VALUE_SUFFIX = "/$value"` and `GraphMailbox._mime_url`, which percent-encodes the complete opaque Graph ID (`urllib.parse.quote(..., safe="")`) and builds the URL through the confirmed folder's own `build_url`, so the mailbox resource segment stays exactly the `users/{address}` scope `authenticate_and_confirm` established — verified against the installed O365 2.1.0 source (`ApiComponent.build_url`, `Folder._endpoints["get_folder"... ]`/message endpoints, `Message.get_mime_content`'s own `/messages/{id}/$value` endpoint).
- Added a `_RecordingConnection` test double that records real `(method, url)` requests, wired as the `con` attribute of the fake folder doubles; rewrote the MIME test to assert on recorded requests rather than in-memory call order, and added reserved-character-encoding, non-200, non-bytes-content, blank-ID, and connection-exception regressions, each asserting `GraphScanFailed` and that no seeded private response text reaches the raised failure's string form or repr.
- Added a connection-routed `_PagingRecordingFolder` double proving that a complete multi-page metadata scan followed by one MIME retrieval issues exactly one more connection request than the number of pages.
- Added `GraphReadOnlyEnforcementTest` with four PROHIB-01 regressions: the recorded method set across a complete scan plus one MIME retrieval is exactly `{GET}`; no recorded URL contains any of nine mutation-implying path segments; no public `GraphMailbox` callable name starts with any of seven mutation-implying prefixes; and constructing `GraphMailbox` with a non-`Inbox` folder name raises `GraphAuthenticationFailed` with zero recorded requests.
- Full deterministic suite: 165 tests, 0 failures, 0 skips (up from 158; `tests.test_graph` alone: 25 tests, all passing, exceeding both plan verify thresholds of 18 and 22).

## Task Commits

Both tasks followed one TDD RED/GREEN pair (see Deviations for why Task 2 has no separate GREEN commit):

1. **Task 1 + Task 2 tests (RED):** `ea2c286` (test) — fails against the pre-change two-request `get_message_mime`: `ImportError` for `_MIME_VALUE_SUFFIX`, and `GraphScanFailed` from the removed `folder.get_message` on the new connection-routed fakes.
2. **Task 1 implementation (GREEN):** `3e37a5b` (feat) — `_mime_url` and the rewritten `get_message_mime`; all 25 `tests.test_graph` tests pass, including the four Task 2 `GraphReadOnlyEnforcementTest` regressions committed alongside Task 1's tests.

**Plan metadata:** committed separately (see final commit below).

## Files Created/Modified

- `vicmap_acquire/graph.py` — `_MIME_VALUE_SUFFIX`, `GraphMailbox._mime_url`, rewritten `get_message_mime` (one connection-level GET; `get_mime_content` alias unchanged)
- `tests/test_graph.py` — `_RecordingConnection`, `_PagingRecordingFolder`, `_adapter_for`; rewrote MIME tests against recorded requests; added `GraphReadOnlyEnforcementTest`

## Decisions Made

See `key-decisions` in frontmatter. In short: verified the exact MIME endpoint shape and `build_url` availability against the installed O365 2.1.0 source rather than assuming it; fetched the confirmed folder into a local variable before evaluating `_mime_url` to avoid an argument-evaluation-order bug the plan's literal suggested call would have hit on the first invocation (`self._folder` is read before `_mime_url()`'s internal `_confirmed_folder()` call can set it); bundled both tasks' tests into one RED/GREEN pair since Task 2 adds no production code of its own; removed the now-unused `_MetadataFolder.get_message`/`get_message_calls` fake surface.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed an argument-evaluation-order bug in the plan's suggested call shape**
- **Found during:** Task 1 implementation
- **Issue:** The plan's action text suggests `self._folder.con.get(self._mime_url(graph_message_id))`. Python evaluates the `self._folder` attribute access before evaluating the argument expression `self._mime_url(...)`. On the first call (`self._folder` is `None` until `_confirmed_folder()` runs), this literal form raises `AttributeError: 'NoneType' object has no attribute 'con'` before `_mime_url`'s own `_confirmed_folder()` call has a chance to populate `self._folder`.
- **Fix:** `get_message_mime` calls `folder = self._confirmed_folder()` first, then computes `url = self._mime_url(graph_message_id)` (whose internal `_confirmed_folder()` call is now a cheap no-op returning the cached folder), then calls `folder.con.get(url)` — same connection object, same one-request behavior, no ordering hazard.
- **Files modified:** `vicmap_acquire/graph.py`
- **Verification:** `test_selective_mime_fetches_by_complete_id_only_on_explicit_call` and all other MIME tests pass on first call with no prior `authenticate_and_confirm()`.
- **Committed in:** `3e37a5b` (Task 1 GREEN commit)

**2. [Rule 3 - Blocking] Removed unused `_MetadataFolder.get_message`/`get_message_calls`**
- **Found during:** Task 1 RED phase (rewriting the MIME test)
- **Issue:** Once `get_message_mime` no longer calls `folder.get_message(...)`, the fake's `get_message` method and `get_message_calls` list became dead test-fixture surface that no test exercised.
- **Fix:** Removed both from `_MetadataFolder`; added `con` and `build_url` instead, which the new connection-level assertions require.
- **Files modified:** `tests/test_graph.py`
- **Verification:** Full suite green; no test referenced the removed names.
- **Committed in:** `ea2c286` (Task 1/2 RED commit)

---

**Total deviations:** 2 auto-fixed (1 bug fix in the implementation, 1 blocking cleanup of now-dead test fixture surface).
**Impact on plan:** Both are necessary for correctness. No scope creep — both changes stay inside the plan's declared `vicmap_acquire/graph.py` / `tests/test_graph.py` files.

## Issues Encountered

None beyond the auto-fixed deviations above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Review warning WR-03 and verification warning W-01 are closed with a production-shaped, connection-level assertion (`_RecordingConnection`).
- MAIL-02's extra-ordinary-message-GET blocker is removed: `get_message_mime` now issues exactly one GET, to the MIME value endpoint.
- PROHIB-01 has runtime enforcement evidence (`GraphReadOnlyEnforcementTest`, 4 regressions) ready to be presented at the blocking prohibition-disposition checkpoint in 01-11.
- Sibling plan 01-11 (remaining prohibition dispositions and the operator's `vicmap.toml` prefix confirmation) is unblocked; it does not depend on this plan's internals beyond the `GraphMailbox` public surface, which is unchanged from the caller's view.

---
*Phase: 01-trusted-graph-acquisition*
*Completed: 2026-09-09*

## Self-Check: PASSED

- FOUND: vicmap_acquire/graph.py
- FOUND: tests/test_graph.py
- FOUND commit: ea2c286 (test, RED, Tasks 1+2)
- FOUND commit: 3e37a5b (feat, GREEN, Task 1)
- `nix develop path:. -c python -m unittest tests.test_graph -v` → 25 tests, OK (exceeds both 18 and 22 thresholds)
- `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` → 165 tests, OK, no failures, no skips
- Re-ran all task-level acceptance criteria (grep + behavioral) from the plan: all pass
