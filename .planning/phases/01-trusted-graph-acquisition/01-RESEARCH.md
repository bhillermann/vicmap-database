# Phase 1: Trusted Graph Acquisition - Research

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

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

### Deferred Ideas (OUT OF SCOPE)
- Controlled acquisition and later import of the expiring backlog archives. Manually preserved archives should remain immutable source artifacts with order ID, original filename, download timestamp, source host, byte size, and SHA-256 recorded. This is separate from Phase 1's one-artifact proof.
- Durable “all messages since last scan” state belongs with the future Postgres audit/idempotency work, not this phase.
</user_constraints>

**Researched:** 2026-09-07
**Domain:** Microsoft Graph mail acquisition, deterministic untrusted-message interpretation, SSRF-resistant streamed download
**Confidence:** MEDIUM — the exact local runtime and SDK APIs were inspected, and the design is supported by official Microsoft, O365, Requests, Python, and OWASP documentation; live Graph and Vicmap download behavior were not exercised.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MAIL-01 | Operator can authenticate with Microsoft Graph and confirm access to the configured automation mailbox without exposing credentials or message bodies. | Use client credentials with the correct O365 2.1.0 keyword, `MemoryTokenBackend`, metadata-only enumeration, library-log suppression, and a safe mailbox-access event. [VERIFIED: .planning/REQUIREMENTS.md:10-10] |
| MAIL-02 | Operator can retrieve a bounded set of Inbox messages and identify ready-order candidates using configured sender and message markers. | Apply an inclusive UTC `receivedDateTime` lower bound, `limit=None`, SDK pagination, exact sender/subject recognition, and body retrieval only after header qualification. [VERIFIED: .planning/REQUIREMENTS.md:11-11] |
| MAIL-03 | Operator can deterministically select exactly one ready-order message and see its redacted identity. | Validate every candidate, then choose by the total key `(receivedDateTime, message_id)` and emit only the allowed redacted fields. [VERIFIED: .planning/REQUIREMENTS.md:12-12] |
| MAIL-04 | Operator can download one artifact only from an approved HTTPS host, with redirect, timeout, and size limits enforced. | Use an unauthenticated Requests session, validate the initial URL and every redirect before sending, stream with connect/read timeouts, and enforce both declared and observed byte ceilings. [VERIFIED: .planning/REQUIREMENTS.md:13-13] |
| MAIL-05 | Operator can see the downloaded artifact's byte count and checksum. | Update byte count and SHA-256 in the same streaming loop and publish final evidence only after successful completion. [VERIFIED: .planning/REQUIREMENTS.md:14-14] |
</phase_requirements>

## Summary

Phase 1 should be planned as three explicit boundaries: a Microsoft Graph adapter that returns minimal message metadata, pure candidate-recognition/selection code that treats all message content as untrusted, and a separate unauthenticated HTTP downloader that revalidates policy before every network hop. This separation is the central security and testability decision: Graph bearer credentials must never enter the artifact-download client, raw message or URL data must never reach logs, and policy decisions must be testable without a live mailbox. [VERIFIED: read_mailbox.py:1-43] [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html]

The existing O365 integration is usable but has three implementation defects the plan must explicitly replace. It performs work on import, uses the wrong `scopes=` keyword for fresh O365 2.1.0 client-credentials authentication, and writes the OAuth token via `FileSystemTokenBackend` under the checkout. The installed SDK instead requires `requested_scopes=` and supplies `MemoryTokenBackend`; its `get_messages()` default is 25, so full bounded-window traversal requires `limit=None` (which activates batches) rather than the current discarded `limit=500` call followed by a default call. [VERIFIED: read_mailbox.py:6-43] [VERIFIED: installed O365 2.1.0 source/runtime probe] [CITED: https://o365.github.io/python-o365/latest/getting_started.html]

The downloader must not rely on Requests' default redirect behavior or on `Content-Length` alone. Disable redirects, validate and follow each redirect manually, stream chunks with a `(connect, read)` timeout tuple, reject an oversized declared length before body reads, and stop before writing any chunk that would cross the observed-byte limit. Hash exactly the bytes written, keep partial output temporary, and only publish the final artifact after success. [CITED: https://requests.readthedocs.io/en/stable/user/advanced/] [CITED: https://requests.readthedocs.io/en/latest/user/quickstart/] [CITED: https://docs.python.org/3/library/hashlib.html]

**Primary recommendation:** Build and test pure policy/data functions first, add a narrow O365 adapter second, then integrate a manually redirected streaming downloader and finish with one redaction-focused live proof.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Client-credentials authentication and Inbox pagination | API adapter | Microsoft Graph | O365 owns OAuth and Graph protocol mechanics; project code owns request shape and safe error translation. [CITED: https://o365.github.io/python-o365/latest/usage/connection.html] |
| Candidate recognition and deterministic choice | Application/domain | — | Sender, subject, order/link consistency, and total ordering are project policy and should be pure code. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:16-30] |
| Redirect and download enforcement | Network adapter | Remote HTTPS/S3 | The application must validate every outbound target before the HTTP client connects. [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html] |
| Artifact bytes and checksum | Filesystem/storage | Network adapter | The storage boundary owns temporary output, finalization, byte count, and the digest of persisted bytes. [CITED: https://docs.python.org/3/library/hashlib.html] |
| Redacted evidence and failure contract | CLI/application | All adapters | Only typed, explicitly safe fields may cross into operator output; raw exceptions and source content stop at their boundary. [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html] |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.14.7 in the current Nix shell | CLI, domain policy, streaming I/O, hashing, tests | It is the verified project runtime; standard-library modules cover configuration, URL decomposition, hashing, temporary files, MIME/HTML parsing, and tests. [VERIFIED: runtime probe through `nix develop path:.`] |
| O365 | 2.1.0, pinned by the existing flake | Client-credentials OAuth, mailbox resource selection, Graph query/pagination, MIME retrieval | Preserve the established integration for this phase; the installed source exposes all required APIs and was inspected directly. [VERIFIED: flake.nix:29-51] [VERIFIED: installed O365 2.1.0 source/runtime probe] |
| Requests | 2.34.2 in the current Nix shell | Dedicated streamed artifact downloader | It is already propagated by the O365 derivation and supports streaming, manual redirect control, TLS verification, and separate connect/read timeouts. [VERIFIED: flake.nix:43-51] [VERIFIED: runtime probe through `nix develop path:.`] [CITED: https://requests.readthedocs.io/en/stable/user/advanced/] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `email` + `html.parser` | Python 3.14.7 stdlib | Prefer the actual `text/plain` MIME part, then extract HTML anchor `href` values only on fallback | Use after sender and subject qualify; never render HTML. [CITED: https://docs.python.org/3/library/email.message.html] [CITED: https://docs.python.org/3/library/html.parser.html] |
| `urllib.parse` | Python 3.14.7 stdlib | Decompose candidate and redirect URLs | Use as a parser followed by explicit validation; Python documents that parsing alone is not validation. [CITED: https://docs.python.org/3/library/urllib.parse.html] |
| `hashlib`, `tempfile`, `pathlib` | Python 3.14.7 stdlib | Incremental SHA-256 and private temporary output | Use in the stream loop and completion boundary. [CITED: https://docs.python.org/3/library/hashlib.html] [CITED: https://docs.python.org/3/library/tempfile.html] |
| `unittest` + `unittest.mock` | Python 3.14.7 stdlib | Fast deterministic unit/adapter tests | Use transport doubles with ordered side effects for pages, redirects, chunks, and exceptions; no new test package is required. [CITED: https://docs.python.org/3.14/library/unittest.mock-examples.html] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| O365 metadata plus selective MIME retrieval | Include bodies in the list-messages query | Listing bodies increases sensitive data returned for every Inbox item, and Microsoft warns that large pages with full payloads can time out; select only metadata and fetch bodies only for header-qualified candidates. [CITED: https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0] |
| Manual redirect loop with Requests | Requests automatic redirects | Automatic following connects before project policy can approve the next hop; OWASP explicitly warns redirects can bypass SSRF validation. [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html] |
| Standard-library `unittest` | Add pytest | The repository has no tests or test dependencies, while `unittest` covers the required pure and mocked-adapter cases without expanding the package surface. [VERIFIED: repository file inventory on 2026-09-07] |

**Installation:** No new package installation is recommended. Continue using `nix develop path:.`; do not add ambient `pip` dependencies. [VERIFIED: flake.nix:58-63]

**Version verification:** The Nix shell imported O365 2.1.0 and Requests 2.34.2 on Python 3.14.7. PyPI currently lists O365 2.1.9 (published 2026-01-30) and Requests 2.34.2 (published 2026-05-14); defer the O365 upgrade because Phase 1 does not require it and all recommended calls were checked against installed 2.1.0. [VERIFIED: runtime probe through `nix develop path:.`] [CITED: https://pypi.org/project/o365/] [CITED: https://pypi.org/project/requests/]

## Package Legitimacy Audit

No new external package is required, so the package-install legitimacy gate does not apply to the proposed phase work. The existing O365 source is pinned to the official `O365/python-o365` repository in `flake.nix`, and Requests is already a propagated input. [VERIFIED: flake.nix:29-51]

## Architecture Patterns

### System Architecture Diagram

```text
opnix-injected credential env + non-secret config + output directory
                              |
                              v
                     guarded CLI entry point
                              |
                  validate config; silence raw library logs
                              |
                              v
              O365 client-credentials + MemoryTokenBackend
                              |
                              v
       Graph Inbox metadata query: receivedDateTime >= UTC cutoff
       select id / receivedDateTime / sender / subject; exhaust pages
                              |
              +---------------+----------------+
              | header rejected               | header qualifies
              v                               v
         safe skip/count              fetch MIME for this message
                                              |
                             text/plain link scan first
                                              |
                          +-------------------+-------------------+
                          | exactly one       | none found
                          v                   v
                    validate candidate    HTML href fallback
                          |                   |
                          +---------+---------+
                                    |
                       mismatch / 0 / >1 links -> safe failure
                                    |
                                    v
                   retain newest valid `(received, message_id)`
                                    |
                             no candidate -> safe failure
                                    |
                                    v
                 validate initial URL before any download request
                                    |
                                    v
        unauthenticated Requests session, TLS on, redirects disabled
                                    |
               redirect? --yes--> resolve -> validate -> next hop
                    |                          |
                    no                   unsafe -> safe failure
                    |
                    v
     validate status/Content-Length -> stream to private temp artifact
                    |
         count bytes + SHA-256 + periodic redacted progress
                    |
            oversize/stall/I/O -> close + clean partial + safe failure
                    |
                    v
            finalize artifact without overwrite -> final evidence
```

### Recommended Project Structure

```text
read_mailbox.py                 # guarded CLI/config/orchestration only
vicmap.toml                     # non-secret, reviewable acquisition policy/defaults
vicmap_acquire/
├── __init__.py
├── graph.py                    # O365 account, bounded metadata iterator, MIME fetch
├── candidates.py               # pure recognition, link extraction, validation, selection
├── download.py                 # URL policy, manual redirects, bounded stream, temp finalization
└── evidence.py                 # fingerprints, masking, typed safe events/failures
tests/
├── test_graph.py
├── test_candidates.py
├── test_download.py
└── test_evidence.py
```

This split is a planning recommendation, not an existing structure. It keeps the two HTTP clients and all secret-bearing/raw-data objects out of the evidence module. [ASSUMED]

### Configuration Contract

Keep only the existing credential inputs in environment variables. Put mailbox identity, Inbox name, sender/order/host allowlists, lookback, size/time/progress/redirect limits, mismatch policy, and output directory in a non-secret TOML file parsed by stdlib `tomllib`; expose only `--config` as the CLI policy selector. This makes the mismatch override a deliberate, reviewable configuration change instead of an interactive or one-off bypass. [ASSUMED]

Recommended initial discretionary values are 10 seconds for connection establishment, 60 seconds without response bytes, 5 seconds between progress events, five redirect hops, and 16 lowercase hexadecimal characters from SHA-256 for correlation fingerprints. Keep these values configurable and tune only from observed live behavior. [ASSUMED]

At startup, validate the whole configuration before authenticating: nonempty allowlists, positive lookback/size/time/interval values, HTTPS host entries represented as hostnames rather than URLs, known keys only, and an output directory that can be created or written without resolving to an existing final artifact. Emit a safe configuration error without echoing the offending raw value. [ASSUMED]

### Component Responsibilities

| Component | Owns | Must Not Own |
|-----------|------|--------------|
| `read_mailbox.py` | Parse non-secret config, call stages in order, map success/failure to exit status | Network details, body/link parsing, raw exception formatting. [ASSUMED] |
| `graph.py` | Correct O365 authentication, configured mailbox/Inbox, cutoff query, full pagination, selective MIME retrieval | Candidate trust decisions or external artifact HTTP. [ASSUMED] |
| `candidates.py` | Exact sender/subject checks, text-first/HTML-fallback link extraction, filename/order consistency, deterministic total ordering | I/O and logging. [ASSUMED] |
| `download.py` | URL validation, manual redirect state machine, timeouts, size enforcement, stream/hash/temp lifecycle | Graph authorization/session or operator-facing raw errors. [ASSUMED] |
| `evidence.py` | Allowlisted event fields, masking/fingerprints, safe reason codes and hints | Subjects, bodies, query strings, complete URLs, bearer tokens, raw exception strings. [ASSUMED] |

### Pattern 1: Metadata First, Content Only After Header Qualification

**What:** List only `id`, `receivedDateTime`, `sender`, and `subject` within the server-side received-time window. Iterate all SDK pages. Retrieve MIME only for exact sender/subject matches, choose `text/plain` first, and inspect HTML anchors only if plain text provides no candidate link. [CITED: https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0] [CITED: https://docs.python.org/3/library/email.message.html]

**When to use:** Every Phase 1 mailbox scan. This reduces sensitive body exposure and makes D-04 literal rather than depending on Graph's HTML-to-text conversion. [ASSUMED]

**Example:**

```python
# Sources:
# https://o365.github.io/python-o365/latest/usage/mailbox.html
# installed O365 2.1.0 Query/get_messages runtime probe
query = (
    inbox.new_query("receivedDateTime")
    .greater_equal(cutoff_utc)
    .select("id", "receivedDateTime", "sender", "subject")
)
for message in inbox.get_messages(limit=None, query=query, batch=999):
    consider_metadata(message)
```

The installed O365 source sets a maximum top value of 999 and returns its `Pagination` iterator when `limit=None`; Microsoft Graph requires following the entire opaque next-link until it disappears. [VERIFIED: installed O365 2.1.0 source/runtime probe] [CITED: https://learn.microsoft.com/en-us/graph/paging]

### Pattern 2: Total Ordering After Full Validation

**What:** Treat a candidate as selectable only after sender, exact ready subject, body link cardinality, filename/order agreement, and URL structure pass. The locked ordering keys are Graph received time followed by message ID. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:16-30] This research recommends retaining the maximum `(received_datetime_utc, graph_message_id)` tuple across the whole iterator and displaying only a fingerprint of the second key. [ASSUMED]

**When to use:** During metadata iteration; never stop at the first apparent match, and never fall back after the selected newest valid candidate fails to download. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:24-30]

### Pattern 3: Validate Before Every HTTP Request

**What:** Parse a URL, reject malformed authority/userinfo, require the configured scheme and exact hostname, send a request with `allow_redirects=False`, and repeat the same validation for the resolved `Location` value before the next request. Keep the artifact client distinct from `account.con`, with no bearer header, cookies, or `.netrc` credential lookup. [CITED: https://docs.python.org/3/library/urllib.parse.html] [CITED: https://requests.readthedocs.io/en/stable/user/authentication/] [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html]

**When to use:** The initial artifact URL and every redirect hop. Validation after automatic following is too late. [CITED: https://requests.readthedocs.io/en/latest/user/quickstart/]

**Example:**

```python
# Sources:
# https://docs.python.org/3/library/urllib.parse.html
# https://requests.readthedocs.io/en/latest/user/quickstart/
def fetch_one_hop(session, url, allowed_hosts, timeout):
    parsed = validate_https_target(url, allowed_hosts)
    return session.get(
        parsed.geturl(),
        allow_redirects=False,
        stream=True,
        timeout=timeout,
        headers={"Accept-Encoding": "identity"},
    )
```

Requests automatically decodes gzip/deflate in `iter_content`; asking for identity encoding and rejecting a non-identity `Content-Encoding` keeps the size and checksum tied to one byte representation. [CITED: https://requests.readthedocs.io/en/latest/user/quickstart/]

### Pattern 4: Stream, Bound, Hash, Then Publish

**What:** Treat `Content-Length` as an early rejection hint, not the enforcement mechanism. Before writing each chunk, check whether the prospective observed count exceeds the configured limit; update SHA-256 and count using exactly the accepted bytes; close every response; remove the partial on any failure; and expose the final path only after the stream completes. [CITED: https://requests.readthedocs.io/en/stable/api/] [CITED: https://docs.python.org/3/library/hashlib.html] [CITED: https://docs.python.org/3/library/tempfile.html]

**When to use:** The final non-redirect response only.

### Pattern 5: Closed Failure and Evidence Vocabulary

**What:** Define structured stage and reason-code enums and render output only from their known-safe fields. Recommended reason codes are `config_invalid`, `graph_auth_failed`, `mailbox_access_failed`, `graph_scan_failed`, `candidate_none`, `candidate_ambiguous`, `order_id_mismatch`, `download_url_rejected`, `download_redirect_rejected`, `download_expired_or_missing`, `download_timeout`, `download_too_large`, `download_http_failed`, and `artifact_write_failed`. [ASSUMED]

**When to use:** Every non-success path. Each code should have a fixed remediation hint; exception objects may be used internally for control flow but must not be interpolated into operator output. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:38-42]

### Anti-Patterns to Avoid

- **Reusing `account.con` for the S3 request:** that connection owns the Graph bearer token; use a clean Requests session so authentication cannot cross the service boundary. [VERIFIED: installed O365 2.1.0 source inspection]
- **Validating only the first or final URL:** an intermediate redirect may already have reached a forbidden destination. Validate before every send. [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html]
- **Calling `list(inbox.get_messages(...))`:** the phase has no message-count cap; stream pages and retain only the best validated candidate. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:25-30]
- **Counting unique URLs rather than link occurrences:** D-05 defines duplicate links as blocking; do not deduplicate before cardinality validation. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:20-22]
- **Logging `message`, exceptions, response objects, or request URLs:** their string forms can contain subjects, opaque IDs, query secrets, or Graph error URLs. Emit project-owned safe events only. [VERIFIED: read_mailbox.py:42-43] [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html]
- **Publishing a destination name before success or overwriting an existing artifact:** a partial/ambiguous artifact must not look complete. Use a private temporary file and fail closed if the intended final path already exists. [ASSUMED]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OAuth/client-credentials tokens | Token request signing, caching, or refresh | O365 `Account` + `MemoryTokenBackend` | OAuth and token lifecycle already exist; memory storage avoids a plaintext checkout token for this one-run proof. [CITED: https://o365.github.io/python-o365/latest/getting_started.html] |
| Graph pagination | `$skip` arithmetic or reconstructed next URLs | O365 `Pagination` via `get_messages(limit=None, batch=999)` | Microsoft says next links are opaque and must be followed whole. [CITED: https://learn.microsoft.com/en-us/graph/paging] |
| MIME decoding | Manual multipart boundary/charset parsing | `email.parser.BytesParser(policy=default)` + `EmailMessage.get_body()` | Standard-library MIME selection handles content types, dispositions, and charset decoding. [CITED: https://docs.python.org/3/library/email.message.html] |
| HTML parsing | Regex over HTML markup | `html.parser.HTMLParser` limited to anchor `href` values | The standard parser decodes tag/attribute structure; never render or execute source HTML. [CITED: https://docs.python.org/3/library/html.parser.html] |
| URL parsing | Regex as the authority parser | `urllib.parse.urlsplit`, followed by explicit policy checks | Python warns that URL parsing itself is not validation. [CITED: https://docs.python.org/3/library/urllib.parse.html] |
| Redirect following | Recursive calls or Requests defaults | One bounded iterative state machine with `allow_redirects=False` | The loop can validate every next target before contact and close prior responses. [CITED: https://requests.readthedocs.io/en/latest/user/quickstart/] |
| Checksum | Buffering the complete archive then hashing | `hashlib.sha256().update(chunk)` in the write loop | Repeated updates are equivalent to hashing the concatenation while keeping memory bounded. [CITED: https://docs.python.org/3/library/hashlib.html] |
| Temporary names | Predictable `.part` names created after an existence check | `tempfile.mkstemp`/`NamedTemporaryFile` in the output directory | Python's secure temporary APIs create the file without the name-allocation race. [CITED: https://docs.python.org/3/library/tempfile.html] |

**Key insight:** The custom work is policy composition—what qualifies, what may be contacted, and what may be disclosed—not reimplementation of OAuth, pagination, MIME, URL decomposition, or hashing.

## Runtime State Inventory

This phase replaces/refactors the prototype's authentication and message-reading behavior, so runtime state outside ordinary source files was audited before planning. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:64-79]

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None for Phase 1 — durable scan/audit state is explicitly deferred, and no database/datastore integration exists in the repository. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:93-99] [VERIFIED: repository file inventory on 2026-09-07] | No migration. Do not introduce a watermark or processing ledger in this phase. |
| Live service config | Microsoft Entra application permissions and Exchange mailbox resource scope live outside git. The current code proves only that an app ID/secret/tenant can address the configured mailbox; tenant-side RBAC scope is not represented locally. [VERIFIED: read_mailbox.py:6-38] [CITED: https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac] | Live security checkpoint: confirm read-only mail access and resource scope for the automation mailbox; this is external configuration, not a code migration. [ASSUMED] |
| OS-registered state | No repository unit files were found and unattended systemd operation is out of scope, but the local user/system service registries could not be queried because this research environment could not access either D-Bus. This is no observation, not proof of absence. [VERIFIED: .planning/REQUIREMENTS.md:53-61] [VERIFIED: local `systemctl` probes failed with permission errors] | Operator checkpoint: inspect user and system unit registries for Vicmap/Vegetation Link names. Do not add scheduling in Phase 1. [ASSUMED] |
| Secrets/env vars | The source reads `O365_AUTH_ID`, `O365_AUTH_SECRET`, and `TENANT_ID`; the Nix shell injects these via opnix. The prototype configures a filesystem token at the verbatim path `token/my_token.txt`. [VERIFIED: read_mailbox.py:6-8] [VERIFIED: flake.nix:20-27] [VERIFIED: read_mailbox.py:23-24] | Code edit: use `MemoryTokenBackend`. Operator security action: once the new flow is verified, revoke/rotate as appropriate and remove/quarantine legacy token material without ever printing it; add ignore protection so tokens cannot be committed. [ASSUMED] |
| Build artifacts / installed packages | A direnv-managed environment cache exists; no project egg-info, Python bytecode cache, or flake result link was found. Runtime dependencies are supplied by the Nix shell. [VERIFIED: local filesystem inventory on 2026-09-07] [VERIFIED: flake.nix:58-63] | Reload direnv/re-enter the flake after dependency changes; no installed project package migration is needed. [ASSUMED] |

**Canonical answer:** after source edits, the remaining old runtime state is the legacy filesystem OAuth token plus tenant-side Entra/Exchange configuration. Both require explicit operational handling; neither is fixed merely by refactoring `read_mailbox.py`. [VERIFIED: read_mailbox.py:23-30] [CITED: https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac]

## Common Pitfalls

### Pitfall 1: Fresh Authentication Never Receives the Scope

**What goes wrong:** A new run without a usable token raises or fails before Graph access.

**Why it happens:** The current code calls `authenticate(scopes=[...])`, but installed O365 2.1.0 accepts `requested_scopes=`; its credential-flow implementation rejects a missing requested scope. [VERIFIED: read_mailbox.py:32-34] [VERIFIED: installed O365 2.1.0 source inspection]

**How to avoid:** Use `MemoryTokenBackend()` and `account.authenticate(requested_scopes=["https://graph.microsoft.com/.default"])`; check the boolean and emit only a safe authentication result. [VERIFIED: installed O365 2.1.0 source inspection] [CITED: https://o365.github.io/python-o365/latest/usage/connection.html]

**Warning signs:** Authentication works only while a checkout token file exists, or the fresh-token path reports that the default scope is missing. [VERIFIED: read_mailbox.py:23-34]

### Pitfall 2: A Count-Limited Scan Masquerades as a Time-Bounded Scan

**What goes wrong:** The newest valid message is missed when more messages than the SDK default occur inside the 15-day window.

**Why it happens:** The current `limit=500` iterator is discarded and the actual loop uses the installed default `limit=25`. [VERIFIED: read_mailbox.py:40-43] [VERIFIED: installed O365 2.1.0 source/runtime probe]

**How to avoid:** Put `receivedDateTime ge <UTC cutoff>` in the Graph query, select minimal fields, and call `get_messages(limit=None, batch=999)` so O365 drains all next links. [VERIFIED: installed O365 2.1.0 query/runtime probe] [CITED: https://learn.microsoft.com/en-us/graph/paging]

**Warning signs:** Tests pass with fewer than 25 fixtures but fail when the valid item is in a later page.

### Pitfall 3: Library Logging Defeats Application Redaction

**What goes wrong:** Even if the CLI catches an exception, O365 debug/error logging can emit request URLs containing mailbox or full message identifiers before the safe mapper runs.

**Why it happens:** The installed O365 connection logs request URLs and HTTP exception strings internally. [VERIFIED: installed O365 2.1.0 source inspection]

**How to avoid:** Configure/suppress third-party loggers before constructing the account, never enable HTTP debug output, and map exceptions to a closed application failure contract. Test stdout and stderr for seeded secret strings. [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html]

**Warning signs:** A failing Graph request prints `graph.microsoft.com/.../messages/<opaque-id>` or an exception traceback.

### Pitfall 4: Redirect Policy Is Checked After the Connection

**What goes wrong:** Requests follows an email-controlled redirect to HTTP or an unapproved host, and only then does code inspect `response.history`.

**Why it happens:** Requests follows redirects for GET by default. [CITED: https://requests.readthedocs.io/en/latest/user/quickstart/]

**How to avoid:** Set `allow_redirects=False`, resolve one `Location`, validate it, then send the next request. Add a bounded hop count to stop loops. [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html]

**Warning signs:** The fake transport records a call to a disallowed URL in an off-host or HTTPS-to-HTTP redirect test.

### Pitfall 5: `Content-Length` Becomes the Only Size Check

**What goes wrong:** A missing, invalid, or dishonest header allows more than the configured maximum to reach disk.

**Why it happens:** Headers describe the response but do not constrain the stream.

**How to avoid:** Reject an excessive declared length early, but enforce the limit again against cumulative accepted chunk bytes before each write; optionally verify a present declared length equals the completed count. [ASSUMED]

**Warning signs:** An oversize mocked stream writes one chunk beyond the ceiling, or a no-header response is unbounded.

### Pitfall 6: Text/HTML Fallback Accidentally Creates Ambiguity

**What goes wrong:** Code concatenates text and HTML links, counts the same archive twice, or silently chooses one among duplicates.

**Why it happens:** Fallback is implemented as aggregation rather than precedence.

**How to avoid:** Examine plain text and stop if it yields any archive-link candidates; only if it yields zero candidates parse HTML, then require exactly one occurrence in the selected representation. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:20-22]

**Warning signs:** A normal multipart/alternative message is rejected because the same link appears once in each representation.

## Code Examples

Verified patterns from official sources and the installed SDK:

### Client-Credentials Authentication Without Checkout Token Persistence

```python
# Sources:
# https://o365.github.io/python-o365/latest/getting_started.html
# installed O365 2.1.0 Account.authenticate inspection
from O365 import Account
from O365.utils.token import MemoryTokenBackend

account = Account(
    credentials,
    auth_flow_type="credentials",
    tenant_id=tenant_id,
    token_backend=MemoryTokenBackend(),
)
if not account.authenticate(
    requested_scopes=["https://graph.microsoft.com/.default"]
):
    raise AuthenticationFailed()
```

The exact local source currently supplies credential names `O365_AUTH_ID`, `O365_AUTH_SECRET`, and `TENANT_ID`, an authentication flow value `credentials`, and a Graph scope `https://graph.microsoft.com/.default`. [VERIFIED: read_mailbox.py:6-10,25-33]

### Plain MIME Body Then HTML Fallback

```python
# Sources:
# https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0
# https://docs.python.org/3/library/email.message.html
from email import policy
from email.parser import BytesParser

mail = BytesParser(policy=policy.default).parsebytes(message.get_mime_content())
plain = mail.get_body(preferencelist=("plain",))
links = extract_text_urls(plain.get_content()) if plain else []
if not links:
    html = mail.get_body(preferencelist=("html",))
    links = extract_anchor_hrefs(html.get_content()) if html else []
```

O365 2.1.0's installed `Message.get_mime_content()` calls Graph's message MIME endpoint and returns bytes; Microsoft documents `/{message-id}/$value` for MIME retrieval. [VERIFIED: installed O365 2.1.0 source inspection] [CITED: https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0]

### Bounded Incremental Hash

```python
# Sources:
# https://requests.readthedocs.io/en/stable/api/
# https://docs.python.org/3/library/hashlib.html
digest = hashlib.sha256()
received = 0
for chunk in response.iter_content(chunk_size=chunk_size):
    if not chunk:
        continue
    next_count = received + len(chunk)
    if next_count > max_bytes:
        raise ArtifactTooLarge()
    output.write(chunk)
    digest.update(chunk)
    received = next_count
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| O365 2.1.0 local pin | O365 2.1.9 is current on PyPI | 2026-01-30 | Do not silently mix latest-doc assumptions with the pinned API; this research inspected the installed 2.1.0 calls. [CITED: https://pypi.org/project/o365/] |
| Legacy Application Access Policies | Exchange Online RBAC for Applications | Microsoft documentation now marks access policies legacy | Tenant administrators can resource-scope app-only mail access; existing tenant scope is not visible in the repo and needs an operational confirmation, not a code assumption. [CITED: https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac] |
| Persisted filesystem token for this proof | O365 `MemoryTokenBackend` | Available in O365 2.1.0 and current docs | Avoids creating new bearer-token material in the repository for a one-run client-credentials flow. [VERIFIED: installed O365 2.1.0 source/runtime probe] [CITED: https://o365.github.io/python-o365/latest/getting_started.html] |

**Deprecated/outdated:**

- Application Access Policies are documented by Microsoft as legacy and replaced by Exchange Online RBAC for Applications. [CITED: https://learn.microsoft.com/en-us/exchange/permissions-exo/application-access-policies]
- The current call `account.authenticate(scopes=[...])` is not the installed O365 2.1.0 credential-flow API; replace it with `requested_scopes=`. [VERIFIED: read_mailbox.py:32-34] [VERIFIED: installed O365 2.1.0 source inspection]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Use a 10-second connect timeout, 60-second stalled-read timeout, 5-second progress interval, and five redirect hops as initial safe defaults. [ASSUMED] | Configuration recommendation | Too tight causes false failures; too loose delays diagnosis. All must remain configurable and be tuned against the real artifact. |
| A2 | Use SHA-256 with the first 16 lowercase hex characters for message-ID and path fingerprints. [ASSUMED] | Redacted evidence | A shorter value raises collision risk; a longer value is more identifying than needed. The full artifact SHA-256 remains untruncated. |
| A3 | Normalize configured and observed sender addresses with surrounding whitespace removed and `casefold()` before exact equality. [ASSUMED] | Candidate recognition | Literal case-sensitive interpretation could reject a semantically identical address; normalization must not broaden to display name or domain suffix matching. |
| A4 | Use an inclusive UTC cutoff (`receivedDateTime ge cutoff`) computed once at process start. [ASSUMED] | Graph query | A message exactly on the boundary differs under an exclusive policy; the inclusive rule is safer for acquisition completeness. |
| A5 | Fail rather than overwrite an existing final artifact path. [ASSUMED] | Download finalization | An operator retry may require choosing a fresh output path, but silent replacement would destroy provenance. |
| A6 | Use the proposed module split and responsibility boundaries, including metadata-first body retrieval. [ASSUMED] | Project structure, component map, Pattern 1 | A different split could work, but mixing boundaries would make disclosure and network-policy tests harder. |
| A7 | Enforce observed bytes in addition to `Content-Length`, request identity encoding, and clean partial output on failure. [ASSUMED] | Pattern 3/4, Pitfalls 5, stream tests | Header or representation behavior could differ on the real S3 response; live verification must confirm it without weakening the hard ceiling. |
| A8 | Require an explicit live security/UAT checkpoint, never broaden a failed hostname automatically, and accept only omitted port or explicit 443. [ASSUMED] | Open Questions | Tenant and live URL behavior are external state that cannot be established from repository research. |
| A9 | Implementation has no missing dependency; mocks replace live Graph/S3 only in automated tests, not acceptance. [ASSUMED] | Environment Availability | A Nix/runtime or tenant dependency could surface during execution and require a Wave 0 adjustment. |
| A10 | Use the documented `unittest` commands, security regression cases, per-task/per-wave sampling, and a live phase gate. [ASSUMED] | Validation Architecture | Test module names or plan boundaries may change, requiring command updates without reducing coverage. |
| A11 | Use the proposed closed reason-code vocabulary and fixed remediation mapping. [ASSUMED] | Pattern 5 | Different names are safe if they remain closed, stable, tested, and never include source-controlled raw text. |
| A12 | Store non-secret acquisition policy in `vicmap.toml`, keep credentials in the existing environment inputs, and accept only `--config` as the policy selector. [ASSUMED] | Configuration Contract | Future systemd integration may prefer another format, but Phase 1 must preserve deliberate reviewable overrides. |
| A13 | Break equal received-time ties by choosing the lexicographically greatest Graph message ID through `max((received, id))`. [ASSUMED] | Pattern 2 | Choosing the opposite direction is also deterministic; tests and evidence must lock one direction consistently. |
| A14 | Treat tenant-role confirmation and legacy token rotation/removal as explicit operational checkpoints around the code refactor. [ASSUMED] | Runtime State Inventory | These systems live outside source control and could retain broader access or old bearer material after code is corrected. |
| A15 | Have the operator check OS service registries and reload the direnv/Nix environment after relevant changes. [ASSUMED] | Runtime State Inventory | D-Bus was unavailable during research and local caches may otherwise preserve old runtime state. |

## Open Questions

1. **Is the Entra/Exchange application permission resource-scoped to the automation mailbox?**
   - What we know: app-only `Mail.Read` permits reading all mailboxes unless the tenant adds a resource scope; Microsoft now recommends Exchange Online RBAC for Applications. [CITED: https://learn.microsoft.com/en-us/graph/permissions-reference] [CITED: https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac]
   - What's unclear: repository state cannot show the tenant-side role assignment.
   - Recommendation: make this a live security/UAT checkpoint. It need not block code planning, but the operator should record a safe pass/fail result before declaring MAIL-01 complete. [ASSUMED]

2. **Does the real S3 response redirect outside the exact locked hostname?**
   - What we know: the locked policy allows only `s3.ap-southeast-2.amazonaws.com`; every other hostname must fail, including bucket-style or accelerator names. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:32-36]
   - What's unclear: the current unexpired Vicmap URL and redirect chain were not accessed during research.
   - Recommendation: retain fail-closed behavior and use the one real proof run to discover whether the allowlist needs a future explicit user decision. Do not broaden it automatically. [ASSUMED]

3. **Should explicit `:443` be accepted as equivalent to an omitted port?**
   - What we know: the decision locks HTTPS plus an exact hostname, but says nothing about an explicit port. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:32-36]
   - What's unclear: whether the real link includes a port (normally it does not). [ASSUMED]
   - Recommendation: accept only no explicit port or 443, and test both; reject all other ports. [ASSUMED]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Nix | Reproducible runtime | ✓ | 2.34.8 | — [VERIFIED: local command probe] |
| Python | Entire phase | ✓ | 3.14.7 in `nix develop path:.` | — [VERIFIED: local Nix-shell probe] |
| O365 | Graph auth/mail | ✓ | 2.1.0 | Raw Graph calls are unnecessary for the planned path. [VERIFIED: local Nix-shell import/source probe] |
| Requests | Artifact download | ✓ | 2.34.2 | — [VERIFIED: local Nix-shell import probe] |
| opnix-injected credential variables | Graph auth | ✓ (presence only; values were not printed) | `O365_AUTH_ID`, `O365_AUTH_SECRET`, `TENANT_ID` | Operator repairs secret injection if absent. [VERIFIED: local Nix-shell presence probe] [VERIFIED: flake.nix:20-27] |
| Microsoft Graph mailbox access | Live proof | Configured; not exercised in research | v1.0 endpoint through O365 | Mock adapters for automated tests; live UAT still required. [VERIFIED: read_mailbox.py:25-38] |
| Approved artifact host/link | Live download proof | URL not known until a qualifying message is selected | HTTPS | No fallback: fail safely and obtain a fresh ready email. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:29-36] |

**Missing dependencies with no fallback:** None identified for implementation. A current qualifying message/link is required only for the final live proof. [ASSUMED]

**Missing dependencies with fallback:** Live Graph and S3 are replaced by mocks for automated tests, but not for acceptance/UAT. [ASSUMED]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Python 3.14.7 standard-library `unittest`/`unittest.mock` [VERIFIED: local Nix-shell probe] |
| Config file | none required [VERIFIED: Python standard-library test framework] |
| Quick run command | `nix develop path:. -c python -m unittest tests.test_candidates tests.test_evidence -v` [ASSUMED] |
| Full suite command | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` [ASSUMED] |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MAIL-01 | correct auth arguments, memory token backend, guarded import, safe mailbox-access/failure output | unit + adapter | `nix develop path:. -c python -m unittest tests.test_graph tests.test_evidence -v` | ❌ Wave 0 [VERIFIED: repository file inventory on 2026-09-07] |
| MAIL-02 | UTC cutoff filter, minimal select, all-page iteration, exact configured marker recognition | unit + adapter | `nix develop path:. -c python -m unittest tests.test_graph tests.test_candidates -v` | ❌ Wave 0 [VERIFIED: repository file inventory on 2026-09-07] |
| MAIL-03 | validate-before-select, newest timestamp, message-ID tie, only redacted identity | unit | `nix develop path:. -c python -m unittest tests.test_candidates tests.test_evidence -v` | ❌ Wave 0 [VERIFIED: repository file inventory on 2026-09-07] |
| MAIL-04 | URL/authority checks, manual hops, timeout tuple, declared/observed sizes, partial cleanup | unit + mocked integration | `nix develop path:. -c python -m unittest tests.test_download -v` | ❌ Wave 0 [VERIFIED: repository file inventory on 2026-09-07] |
| MAIL-05 | byte count, known SHA-256, progress with/without total, final evidence | unit + mocked integration | `nix develop path:. -c python -m unittest tests.test_download tests.test_evidence -v` | ❌ Wave 0 [VERIFIED: repository file inventory on 2026-09-07] |

### Required Security Regression Matrix

| Boundary | Cases that must be automated |
|----------|-----------------------------|
| Graph | fresh auth uses `requested_scopes`; no filesystem token backend; valid message only on a later page; iterator order shuffled; equal timestamps; naive/malformed timestamp safely rejected. [VERIFIED: installed O365 2.1.0 source/runtime probe] |
| Recognition | sender/subject near misses; multiple allowed order IDs; zero/one/two link occurrences; plain wins when it has a candidate; HTML fallback only on zero; subject/filename mismatch with override off/on. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:16-30] |
| URL | HTTP, userinfo, trailing-dot hostname, suffix host, uppercase hostname, invalid port, non-443 port, relative redirect, HTTPS downgrade, off-host redirect, missing `Location`, loop/hop exhaustion. [CITED: https://docs.python.org/3/library/urllib.parse.html] |
| Stream | missing/invalid/negative/excessive `Content-Length`; declared short/long body; empty keepalive chunks; crossing limit by one byte; read/connect timeout; HTTP error; write failure; no partial/final exposure on failure. [ASSUMED] |
| Disclosure | seed credentials, full message ID, subject, body, complete URL/query, and raw exception text; assert none appear in captured stdout/stderr for every failure path. [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html] |

### Sampling Rate

- **Per task commit:** `nix develop path:. -c python -m unittest <touched test modules> -v` [ASSUMED]
- **Per wave merge:** `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` [ASSUMED]
- **Phase gate:** Full suite green plus one controlled live acquisition whose output is reviewed for forbidden raw values before `$gsd-verify-work`. [ASSUMED]

### Wave 0 Gaps

- [ ] `tests/test_graph.py` — auth construction, cutoff query, pagination adapter, no-body metadata contract
- [ ] `tests/test_candidates.py` — D-01 through D-10 and D-12 pure policy cases
- [ ] `tests/test_download.py` — D-13 through D-16 and stream/hash lifecycle
- [ ] `tests/test_evidence.py` — D-17 through D-20 disclosure contract
- [ ] Shared fake message, response, and transport helpers (keep local to tests unless duplication becomes material)
- [ ] No framework install; `unittest` is in the verified runtime. [VERIFIED: local Nix-shell probe]

## Security Domain

Security enforcement is enabled because `.planning/config.json` does not set `security_enforcement` to false. [VERIFIED: .planning/config.json:1-20]

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | O365/MSAL client-credentials flow; secrets injected by opnix; access tokens kept in memory and excluded from output. [CITED: https://o365.github.io/python-o365/latest/getting_started.html] |
| V3 Session Management | no interactive user session | OAuth bearer-token lifecycle still remains inside O365/MSAL; do not expose or reuse the Graph session for S3. [CITED: https://o365.github.io/python-o365/latest/getting_started.html] |
| V4 Access Control | yes | Address only the configured mailbox; use read-only mail permission and verify tenant resource scoping operationally. [CITED: https://learn.microsoft.com/en-us/graph/permissions-reference] |
| V5 Input Validation | yes | Exact sender/order/subject/filename/host allowlists; structured URL parsing plus explicit checks; validate each redirect before contact. [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html] |
| V6 Cryptography | yes | Requests TLS certificate verification remains enabled; SHA-256 comes from `hashlib`; no custom cryptographic code. [CITED: https://requests.readthedocs.io/en/stable/api/] [CITED: https://docs.python.org/3/library/hashlib.html] |

### Known Threat Patterns for Python/O365/Requests

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Sender/subject/link spoofing | Spoofing | Layer independent exact checks: sender allowlist, subject/order allowlist, filename/order agreement, and target-host allowlist. [VERIFIED: .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md:16-36] |
| Redirect-based SSRF | Spoofing / Information disclosure | Disable automatic redirects and revalidate scheme/authority before every request. [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html] |
| Graph token leakage to artifact host | Information disclosure | Never reuse O365's authenticated connection/session; clean artifact session with no auth, cookies, or `.netrc`. [VERIFIED: installed O365 2.1.0 source inspection] [CITED: https://requests.readthedocs.io/en/stable/user/authentication/] |
| Presigned query/body leakage in logs | Information disclosure | Closed safe-event schema; host plus path fingerprint only; suppress third-party raw HTTP logs; adversarial output tests. [CITED: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html] |
| Oversized or stalled response | Denial of service | Declared and observed byte ceilings, streamed chunks, separate connect/read timeouts, bounded redirects, prompt response close. [CITED: https://requests.readthedocs.io/en/stable/user/advanced/] |
| Partial artifact mistaken for complete | Tampering | Private temporary output, cleanup on failure, finalization only after complete byte/hash accounting, no overwrite. [CITED: https://docs.python.org/3/library/tempfile.html] |
| Malicious MIME/HTML | Tampering / Denial of service | Standard parsers, no rendering/execution, href-only extraction, content retrieval only after header qualification. [CITED: https://docs.python.org/3/library/email.message.html] [CITED: https://docs.python.org/3/library/html.parser.html] |

## Sources

### Primary (HIGH confidence for local facts)

- [`read_mailbox.py`](../../../read_mailbox.py) — existing authentication, token path, mailbox, Inbox, and enumeration behavior inspected line by line. [VERIFIED: read_mailbox.py:1-43]
- [`flake.nix`](../../../flake.nix) — pinned O365 source and propagated runtime dependencies inspected line by line. [VERIFIED: flake.nix:1-76]
- Installed Nix runtime probe — Python 3.14.7, O365 2.1.0, Requests 2.34.2, exact method signatures/source, query rendering, and credential-variable presence without values. [VERIFIED: local Nix-shell probes]

### Secondary (MEDIUM confidence, official documentation reached through web search)

- [Microsoft Graph: List messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0) — minimal selects, application access, page sizing, opaque next-link handling.
- [Microsoft Graph: Paging](https://learn.microsoft.com/en-us/graph/paging) — full next-link traversal.
- [Microsoft Graph: Get message](https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0) — text body preference and MIME endpoint.
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference) — application `Mail.Read` breadth and resource-scoping note.
- [Exchange Online RBAC for Applications](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac) — current resource-scoped app permission model.
- [O365 getting started](https://o365.github.io/python-o365/latest/getting_started.html) — client credentials and token backend protection/options.
- [O365 protocols/resources](https://o365.github.io/python-o365/latest/usage/connection.html) — mailbox resource selection and credentials flow.
- [Requests advanced usage](https://requests.readthedocs.io/en/stable/user/advanced/) — connect/read timeout semantics and streamed response lifecycle.
- [Requests quickstart](https://requests.readthedocs.io/en/latest/user/quickstart/) — redirect defaults/control and content decoding.
- [Requests authentication](https://requests.readthedocs.io/en/stable/user/authentication/) — `.netrc` and `trust_env` behavior.
- [Python `urllib.parse`](https://docs.python.org/3/library/urllib.parse.html) — URL components and explicit security warning.
- [Python `email.message`](https://docs.python.org/3/library/email.message.html) — body preference behavior.
- [Python `hashlib`](https://docs.python.org/3/library/hashlib.html) — incremental SHA-256.
- [Python `tempfile`](https://docs.python.org/3/library/tempfile.html) — secure temporary creation.
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — allowlists and redirect bypass prevention.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — secret/token/identifier exclusion and sanitization.
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) — security verification framework; latest stable documented as 5.0.0.

### Tertiary (LOW confidence)

- None used as authoritative support. All implementation judgments without an authoritative source are marked `[ASSUMED]` and listed in the Assumptions Log.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — exact installed versions and relevant APIs were executed/inspected; no new package is proposed. [VERIFIED: local Nix-shell probes]
- Architecture: MEDIUM — built from locked decisions, local code, and official provider/security documentation; the real message/link path is not available in research. [CITED: sources above]
- Pitfalls: MEDIUM — local SDK defects are verified; network-edge behavior is documentation-backed and requires mocked plus live verification. [CITED: sources above]

**Research date:** 2026-09-07
**Valid until:** 2026-10-07 for the local pinned stack; re-check Microsoft Graph/Exchange guidance before later production-hardening phases.
