# Phase 1: Trusted Graph Acquisition - Pattern Map

**Mapped:** 2026-09-07
**Files analyzed:** 12 new/modified files
**Analogs found:** 0 / 12

## Repository Pattern Baseline

The repository currently has no git-tracked application or test source. The only tracked files are planning documents. Although an untracked 43-line mailbox prototype and an untracked Nix environment definition exist in the worktree, the tracked-source gate forbids assigning either as an analog. Consequently, every implementation file below must use the verified examples in `01-RESEARCH.md` and the responsibility boundaries in this map rather than copying a purported established implementation pattern.

This is an intentional no-analog result, not a search gap. The scan covered the repository root, all Python files, prospective package/test locations, and the tracked-file index.

## File Classification

| New/Modified File | Role | Data Flow | Closest Tracked Analog | Match Quality |
|---|---|---|---|---|
| `read_mailbox.py` | controller / CLI | request-response | none | no analog |
| `vicmap.toml` | config | transform | none | no analog |
| `.gitignore` | config | file-I/O | none | no analog |
| `vicmap_acquire/__init__.py` | config / package boundary | transform | none | no analog |
| `vicmap_acquire/graph.py` | service / API adapter | request-response, paginated | none | no analog |
| `vicmap_acquire/candidates.py` | service / domain policy | transform | none | no analog |
| `vicmap_acquire/download.py` | service / network adapter | streaming, file-I/O | none | no analog |
| `vicmap_acquire/evidence.py` | utility | event-driven, transform | none | no analog |
| `tests/test_graph.py` | test | request-response | none | no analog |
| `tests/test_candidates.py` | test | transform | none | no analog |
| `tests/test_download.py` | test | streaming, file-I/O | none | no analog |
| `tests/test_evidence.py` | test | event-driven, transform | none | no analog |

`flake.nix` was inspected as an integration point but is not assigned as a Phase 1 modification: research verified that O365 and Requests are already available and explicitly recommends no new dependency. Modify it only if execution proves the verified runtime assumption false.

## Pattern Assignments

### `read_mailbox.py` (controller / CLI, request-response)

**Analog:** None. Use `01-RESEARCH.md` “Configuration Contract” and “Component Responsibilities.”

**Required shape:** Keep this file as orchestration only: parse `--config`, load and validate policy, suppress unsafe third-party logging, call Graph scan, select one candidate, download it automatically, render safe evidence, and convert typed failures to exit status. It must expose `main()` and guard execution so imports have no Graph or filesystem effects.

```python
def main(argv: list[str] | None = None) -> int:
    # parse config -> scan -> select -> download -> render safe event
    ...

if __name__ == "__main__":
    raise SystemExit(main())
```

Do not preserve prototype patterns of module-level authentication, filesystem token persistence, raw `print(message)`, duplicate retrieval calls, or raw exception propagation.

### `vicmap.toml` (config, transform)

**Analog:** None. Use `01-RESEARCH.md` “Configuration Contract.”

Keep credentials out of TOML. Define mailbox identity, folder, sender/order/host allowlists, lookback, size, connect/read/progress timeouts, redirect ceiling, mismatch override, and output directory. Use these initial research defaults: 15 days, 10 GiB, 10-second connect timeout, 60-second stalled-read timeout, 5-second progress interval, 5 redirects, and 16 hex fingerprint characters. The initial allowlists are exactly `noreply@datashare.maps.vic.gov.au`, `OK0VUZ`, and `s3.ap-southeast-2.amazonaws.com`.

Validate unknown keys and all values before authentication. The mismatch override must be a deliberate boolean configuration value, never an interactive switch.

### `.gitignore` (config, file-I/O)

**Analog:** None. This file is implied by the research runtime-state audit.

Ignore OAuth token material, local 1Password/opnix state, `.direnv`, Python bytecode/test caches, and downloaded artifacts. Do not use a broad rule that hides source TOML or test fixtures. Existing token-bearing worktree files are runtime state and must never become examples or fixtures.

### `vicmap_acquire/__init__.py` (package boundary, transform)

**Analog:** None.

Keep the package initializer free of network and filesystem side effects. Export only stable domain types if doing so reduces import coupling; otherwise leave it empty. In particular, importing the package must not read credentials, authenticate, open Inbox, or create output paths.

### `vicmap_acquire/graph.py` (service / API adapter, request-response)

**Analog:** None. Copy the verified SDK usage from `01-RESEARCH.md` “Client-Credentials Authentication Without Checkout Token Persistence” and “Metadata First.”

**Imports pattern:**

```python
from datetime import datetime
from collections.abc import Iterator

from O365 import Account
from O365.utils.token import MemoryTokenBackend
```

**Authentication pattern:**

```python
account = Account(
    credentials,
    auth_flow_type="credentials",
    tenant_id=tenant_id,
    token_backend=MemoryTokenBackend(),
)
if not account.authenticate(
    requested_scopes=["https://graph.microsoft.com/.default"]
):
    raise GraphAuthenticationFailed()
```

**Pagination/core pattern:**

```python
query = (
    inbox.new_query("receivedDateTime")
    .greater_equal(cutoff_utc)
    .select("id", "receivedDateTime", "sender", "subject")
)
for message in inbox.get_messages(limit=None, query=query, batch=999):
    yield to_message_metadata(message)
```

Own mailbox resource selection, `Inbox`, an inclusive cutoff computed once, complete SDK pagination, minimal metadata conversion, and selective MIME retrieval. Return project-owned values; do not expose O365 objects to policy or evidence code. Catch provider exceptions at this boundary and raise closed typed failures without embedding raw exception text.

### `vicmap_acquire/candidates.py` (service / domain policy, transform)

**Analog:** None. Use `01-CONTEXT.md` D-01–D-12 and `01-RESEARCH.md` Patterns 1–2.

**MIME precedence pattern:**

```python
mail = BytesParser(policy=policy.default).parsebytes(mime_bytes)
plain = mail.get_body(preferencelist=("plain",))
links = extract_text_urls(plain.get_content()) if plain else []
if not links:
    html = mail.get_body(preferencelist=("html",))
    links = extract_anchor_hrefs(html.get_content()) if html else []
```

Implement pure functions for exact normalized sender membership, case-insensitive exact subject-template parsing, occurrence-preserving URL extraction, exact `Order_{ORDER_ID}.zip` matching, configured mismatch handling, and deterministic selection. Plain text has precedence: HTML is inspected only when plain text yields zero candidate links. Require exactly one occurrence; do not deduplicate duplicates.

Choose only after full validation, retaining the maximum total key:

```python
selection_key = (candidate.received_datetime_utc, candidate.graph_message_id)
selected = max(valid_candidates, key=lambda candidate: candidate.selection_key)
```

Never log within this module and never truncate the ID used for ordering; truncation belongs only to evidence rendering.

### `vicmap_acquire/download.py` (service / network adapter, streaming + file-I/O)

**Analog:** None. Use `01-RESEARCH.md` Patterns 3–4.

**One-hop request pattern:**

```python
parsed = validate_https_target(url, allowed_hosts)
response = session.get(
    parsed.geturl(),
    allow_redirects=False,
    stream=True,
    timeout=(connect_timeout, read_timeout),
    headers={"Accept-Encoding": "identity"},
)
```

Construct a clean `requests.Session` with no Graph bearer state, cookies, or `.netrc` lookup (`trust_env = False`). Validate scheme, authority, userinfo absence, exact normalized hostname, and port before the first request and before every redirected request. Resolve relative `Location` values, bound the iterative redirect loop, and close each response.

**Bounded stream pattern:**

```python
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

Reject excessive declared lengths before reading, but always enforce observed bytes. Create a private temporary file in the destination directory, remove it on every failure, and atomically publish only after successful completion; fail if the final path exists. Translate HTTP, timeout, and I/O exceptions to typed safe failures. Return byte count and full SHA-256, not raw response data.

### `vicmap_acquire/evidence.py` (utility, event-driven + transform)

**Analog:** None. Use `01-CONTEXT.md` D-17–D-20 and `01-RESEARCH.md` Pattern 5.

Define closed stage/reason enums and typed safe events. Render only allowlisted fields. Recommended reason codes are `config_invalid`, `graph_auth_failed`, `mailbox_access_failed`, `graph_scan_failed`, `candidate_none`, `candidate_ambiguous`, `order_id_mismatch`, `download_url_rejected`, `download_redirect_rejected`, `download_expired_or_missing`, `download_timeout`, `download_too_large`, `download_http_failed`, and `artifact_write_failed`.

Use SHA-256 and the configured display length for opaque ID/path fingerprints. Mask the sender locally. Success evidence may contain order ID, received timestamp, masked sender, message fingerprint, approved hostname, path fingerprint, final bytes, and artifact checksum. Failure evidence may contain stage, closed reason code, redacted identifiers, and a fixed hint. Subjects, bodies, complete URLs/query strings, credentials, tokens, response objects, and `str(exception)` must not enter the renderer.

### `tests/test_graph.py` (test, request-response)

**Analog:** None. Use standard-library `unittest` and `unittest.mock` as specified by `01-RESEARCH.md` Validation Architecture.

Test account construction with `MemoryTokenBackend`, `requested_scopes`, mailbox/folder selection, inclusive UTC query, selected fields, `limit=None`, `batch=999`, later-page candidates, malformed timestamps, and safe exception translation. Importing both the package and CLI must produce no network calls.

### `tests/test_candidates.py` (test, transform)

**Analog:** None.

Use small immutable fake metadata and synthetic MIME bytes. Cover sender/subject near misses, every allowed order ID, zero/one/two link occurrences, plain-over-HTML precedence, HTML fallback, filename/order mismatch with override off/on, shuffled iteration, newest selection, and equal-time message-ID ties. Tests must establish that duplicates are counted, not deduplicated.

### `tests/test_download.py` (test, streaming + file-I/O)

**Analog:** None.

Use mocked Sessions/Responses with ordered side effects and `tempfile.TemporaryDirectory`. Assert the transport never contacts rejected targets. Cover HTTP, userinfo, trailing-dot/suffix hosts, uppercase hostname normalization, invalid/non-443 ports, relative redirects, downgrade/off-host redirects, missing Location, redirect exhaustion, all Content-Length edge cases, empty chunks, ceiling plus one byte, both timeout classes, HTTP/write failures, known checksum, and cleanup/no overwrite.

### `tests/test_evidence.py` (test, event-driven + transform)

**Analog:** None.

Table-test all success/failure event variants and progress with/without total length. Seed credentials, full IDs, subject/body text, full presigned URL/query, and exception strings, capture stdout/stderr, and assert every seeded secret is absent while required safe fields and fixed remediation hints remain present.

## Shared Patterns

### Dependency Direction

`read_mailbox.py` composes `graph`, `candidates`, `download`, and `evidence`. `graph` and `download` are independent adapters. `candidates` is pure and has no adapter imports. `evidence` receives only project-owned safe values. No production module imports the CLI.

### Closed Error Translation

Every external boundary catches its provider exceptions and raises a project-owned failure carrying only a stage and reason code. The CLI renders through `evidence.py`; it never prints exception, message, response, or URL objects. Fixed code-to-hint mappings make output useful without copying attacker-controlled input.

### Configuration and Secrets

Read only `O365_AUTH_ID`, `O365_AUTH_SECRET`, and `TENANT_ID` from the environment. Load all non-secret policy from TOML and validate it as a whole before any network request. Never persist O365 access tokens in the checkout.

### Test Structure

Use `unittest.TestCase`, local fakes or `unittest.mock`, and dependency injection at Graph/Requests/filesystem boundaries. The deterministic suite must not contact real Graph or S3. Mirror each production module with one focused `tests/test_*.py` module and run all tests with:

```text
nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v
```

### Security Invariants

- Validate all email-derived URLs before every request.
- Never reuse the authenticated Graph connection for artifact download.
- Never select until every candidate check succeeds and all pages are exhausted.
- Never fall back to an older candidate after the selected download fails.
- Never expose a partial file as final or overwrite an existing final artifact.
- Never render source-controlled raw text or raw exceptions.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `read_mailbox.py` | controller / CLI | request-response | No tracked application source; current prototype is untracked and unsafe to copy. |
| `vicmap.toml` | config | transform | No tracked application configuration exists. |
| `.gitignore` | config | file-I/O | No tracked ignore/config precedent exists. |
| `vicmap_acquire/__init__.py` | package boundary | transform | No tracked Python package exists. |
| `vicmap_acquire/graph.py` | API adapter | request-response | No tracked adapter exists. |
| `vicmap_acquire/candidates.py` | domain service | transform | No tracked domain module exists. |
| `vicmap_acquire/download.py` | network/storage service | streaming, file-I/O | No tracked downloader or artifact writer exists. |
| `vicmap_acquire/evidence.py` | utility | event-driven, transform | No tracked logging/evidence contract exists. |
| `tests/test_graph.py` | test | request-response | No tracked tests exist. |
| `tests/test_candidates.py` | test | transform | No tracked tests exist. |
| `tests/test_download.py` | test | streaming, file-I/O | No tracked tests exist. |
| `tests/test_evidence.py` | test | event-driven, transform | No tracked tests exist. |

## Metadata

**Analog search scope:** repository root, Python/Nix/config files, prospective `vicmap_acquire/` and `tests/` trees, and complete `git ls-files` index

**Files scanned:** 2 implementation/environment files plus tracked planning guidance

**Tracked source candidates:** 0

**Pattern extraction date:** 2026-09-07

**Primary fallback source:** `.planning/phases/01-trusted-graph-acquisition/01-RESEARCH.md`
