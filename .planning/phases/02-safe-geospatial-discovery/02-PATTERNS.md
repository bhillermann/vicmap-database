# Phase 2: Safe Geospatial Discovery - Pattern Map

**Mapped:** 2026-09-14
**Files analyzed:** 8 (4 new modules, 1 config, 1 flake, 1 gitignore, N test files)
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `vicmap_acquire/extraction.py` (NEW) | service (fail-closed guard chain + atomic filesystem publish) | streaming / file-I/O | `vicmap_acquire/download.py` | exact (same shape: frozen `*Policy` dataclass, typed exception hierarchy, chunked digest loop, atomic publish) |
| `vicmap_acquire/discovery.py` (NEW) | service (external-reader introspection) | request-response (subprocess + library calls, no streaming state) | `vicmap_acquire/candidates.py` (pure recognition over parsed structure, closed failures) + `vicmap_acquire/origin.py` (independent, dependency-leafward verification with typed closed failure) | role-match |
| `vicmap_acquire/naming.py` (NEW) | utility (pure string/set transform, no I/O) | transform | `vicmap_acquire/origin.py` (pure function, total w.r.t. inputs, typed closed failure on any deviation) | role-match |
| `vicmap_acquire/manifest.py` (NEW) | model + service (frozen typed object + JSON serialization) | transform / file-I/O | `vicmap_acquire/evidence.py` (frozen `_SafeEvent`/dataclass style, canonical `json.dumps` idiom, redaction split) | exact |
| `vicmap_acquire/evidence.py` (MODIFIED) | model (enum + typed-closed-failure vocabulary) | transform | itself — extend `Stage`/`ReasonCode`/`_FAILURE_POLICY`, following existing entries | exact (in-place extension) |
| `vicmap_acquire/origin.py` composition pattern → run entry point (likely `run_discovery` in a new or existing CLI-style module) | controller (compose stages, orchestrate fail-closed pipeline) | request-response | `vicmap_acquire/candidates.py::recognize_candidate` / `select_candidate` composition, and the overall `download_artifact` orchestration in `download.py` | role-match |
| `vicmap.toml` (MODIFIED) | config | — | existing `[mailbox]` / `[download]` sections | exact |
| `flake.nix` (MODIFIED) | config | — | existing `python3.withPackages` / `packages` list | exact |
| `.gitignore` (MODIFIED) | config | — | existing `artifacts/` unanchored entry | exact |
| `tests/test_extraction.py` (NEW) | test | file-I/O | `tests/test_download.py` (security/lifecycle regressions against a policy dataclass + fake transport/filesystem) | exact |
| `tests/test_discovery.py` / `tests/test_naming.py` / `tests/test_manifest.py` (NEW) | test | CRUD/transform | `tests/test_candidates.py`, `tests/test_origin.py` | role-match |
| `tests/test_discovery_differential.py` (NEW, recommended) | test | transform (independent-oracle check) | `tests/test_html_visibility_differential.py` | exact — **use this pattern for cross-checking pyogrio's discovery output against an independently-invoked `ogrinfo` call** (per user's memory note on differential-oracle testing for parsing/visibility logic; geometry-type string vocabulary mismatches noted in RESEARCH.md Pitfall 3 make this especially load-bearing) |

## Pattern Assignments

### `vicmap_acquire/extraction.py` (service, streaming/file-I/O)

**Analog:** `vicmap_acquire/download.py`

**Frozen policy + validators pattern** (`download.py:135-183`):
```python
@dataclass(frozen=True)
class DownloadPolicy:
    allowed_hosts: tuple[str, ...]
    allowed_url_prefixes: tuple[str, ...]
    max_bytes: int
    connect_timeout_seconds: int
    stalled_read_timeout_seconds: int
    progress_interval_seconds: int
    max_redirects: int
    fingerprint_hex_length: int

    def __post_init__(self) -> None:
        # normalize + validate every field; object.__setattr__ to fix up
        # normalized values on a frozen dataclass; raise ValueError on any
        # invalid input, never silently coerce
```
Copy this exact shape for `ExtractionPolicy`: `max_total_bytes`, `max_member_bytes`, `max_member_count`, `max_compression_ratio`, validated with the same `_positive_integer`-style helper, frozen and `__post_init__`-validated.

**Typed exception hierarchy** (`download.py:21-59`):
```python
class DownloadFailure(RuntimeError):
    code = "download_http_failed"
    def __init__(self) -> None:
        super().__init__(self.code)

class DownloadUrlRejected(DownloadFailure):
    code = "download_url_rejected"
```
Mirror this for extraction: `ArchiveFailure` base, `ArchiveTraversalRejected`, `ArchiveUnsafeMemberRejected`, `ArchiveCeilingExceeded`, `ArtifactChecksumMismatch` (D-28) — each a bare `code`, no interpolated text, matching `evidence.py`'s "raw exception text never reaches output" rule.

**Reject-before-write member validation** (RESEARCH.md Pattern 1, verified against CPython 3.14's `zipfile.py` this session) — this is new code with no existing in-repo analog, but must follow `download.py`'s validate-before-connect posture (`validate_https_target` runs completely before `session.get` is ever called, `download.py:216-258`). Apply the same "validate the whole guard list before any side effect" ordering to per-member checks (absolute path, `..`, symlink/hardlink via `create_system`-gated `external_attr`, non-regular member, resolved-path escape) before opening any output file handle.

**Streamed extraction with running ceiling + digest** (`download.py:546-579`, the `for chunk in response.iter_content(...)` loop):
```python
digest = hashlib.sha256()
received = 0
...
for chunk in response.iter_content(chunk_size=1024 * 1024):
    ...
    next_count = received + len(chunk)
    if next_count > policy.max_bytes:
        raise DownloadTooLarge()
    written = output.write(chunk)
    if written != len(chunk):
        raise ArtifactWriteFailed()
    digest.update(chunk)
    received = next_count
```
Copy directly for per-member extraction (`zip_file.open(member).read(chunk)` in place of `response.iter_content`), enforcing both per-member and running-total ceilings inside the same loop, exactly as RESEARCH.md Pattern 2 already sketches.

**Atomic publish pattern** (`download.py:261-306`, `_fsync_directory` + `_publish_artifact`):
```python
def _publish_artifact(temp_path: Path, final_path: Path) -> bool:
    os.link(temp_path, final_path)
    _fsync_directory(final_path.parent)
    try:
        temp_path.unlink()
    except OSError:
        return False
    return True
```
D-25/extraction's "write to `.tmp-{ts}/` then rename into `runs/{order}/{ts}/`" should reuse this exact commit-point discipline: one atomic filesystem operation (`os.rename` for a directory, in place of `os.link` for a single file) is the sole commit point, with the same `finally`-block temp cleanup shown in `download.py:602-609`.

**Error-boundary wrapping at the top-level function** (`download.py:598-609`):
```python
except DownloadFailure:
    raise
except OSError:
    raise ArtifactWriteFailed() from None
finally:
    _close(response)
    if temp_path is not None:
        try:
            temp_path.unlink()
        except OSError:
            pass
```
Mirror this `except <TypedFailure>: raise` / `except OSError: raise <TypedFailure>() from None` / `finally: cleanup` structure in `extraction.py`'s top-level `extract_artifact`.

---

### `vicmap_acquire/discovery.py` (service, request-response over pyogrio + ogrinfo subprocess)

**Analog:** `vicmap_acquire/candidates.py` (pure recognition, closed failures on ambiguity) and `vicmap_acquire/origin.py` (independent verification, total function w.r.t. inputs)

**Total-function-with-single-catch-all pattern** (`origin.py:118-198`):
```python
def verify_authenticated_origin(mime_content, metadata_sender, policy) -> str:
    try:
        ...
        return from_address
    except OriginUnauthenticated:
        raise
    except Exception:
        raise OriginUnauthenticated() from None
```
Apply this to every discovery entry point (`profile_layer`, `list_supported_datasets`) — any unexpected pyogrio/subprocess exception collapses to one typed closed failure (`LAYER_UNREADABLE` per D-36), never leaking raw driver text, matching `evidence.py`'s "unexpected exceptions map to one fixed internal failure" rule.

**None vs distinguished-sentinel discipline** (`candidates.py`'s `_subject_order_id` returning `None` for "no match" vs raising `CandidateAmbiguous` for a malformed state) — apply directly to D-38's `geometry_type is None` (legitimate non-spatial layer, D-35) vs `geometry_type == "Unknown"` (typed hard stop) distinction RESEARCH.md flags as Pitfall 3/the "Common Pitfalls" section. Never conflate a `None` ordinary-non-match with a malformed-state failure — this is exactly `evidence.py`'s stated pattern ("`None` is reserved for ordinary non-matches; malformed, ambiguous, or mismatched states get their own typed failures").

**Subprocess invocation with strict decoding** — no existing subprocess call exists in the codebase to copy verbatim, but `download.py`'s `_request_final_response` shows the required posture: wrap the external call, catch its specific exception types, translate immediately to a typed failure, never let library-native exception text reach the caller. Apply the same shape to the `ogrinfo -json -al -so` subprocess call (RESEARCH.md Pattern 3):
```python
result = subprocess.run(
    ["ogrinfo", "-json", "-al", "-so", dataset_path],
    capture_output=True, text=True, timeout=60, check=True,
)
```
Wrap `subprocess.CalledProcessError`, `subprocess.TimeoutExpired`, and `json.JSONDecodeError` each into `LAYER_UNREADABLE`, following `origin.py`'s catch-all-collapse pattern above.

---

### `vicmap_acquire/naming.py` (utility, pure transform, D-21–D-24)

**Analog:** `vicmap_acquire/origin.py` — pure, no I/O, total w.r.t. inputs, one narrow public function plus small validated helpers (`_domain_aligned`, `_strip_comments`).

**Structure to copy:**
```python
"""Pure ... policy over already-... This module has no I/O ...
dependency direction stays leaf-ward."""
```
Copy `origin.py`'s module-docstring convention (state the purity/no-I/O/no-cross-import contract explicitly) for `naming.py`: normalization and collision detection never import `discovery.py` or touch a database connection (D-23's explicit "Phase 2 never contacts the database").

**Validation-helper-per-rule pattern** (`download.py`'s `_normalize_url_prefix`, `_normalize_allowed_host` — one function per distinct validation concern, each raising `ValueError` on violation) — apply per D-22 rule: one helper for charset/leading-digit, one for reserved-word lookup (static frozenset per RESEARCH.md's "Don't Hand-Roll" table — full Postgres keyword appendix, not a hand-typed shortlist), one for the 63-byte length check, composed by a single `normalize_target_table_name(gdb_stem: str, layer_name: str) -> str` entry point that raises a typed `TableNameInvalid` (mirroring `DownloadUrlRejected`'s single-purpose exception style) on any violation.

**Collision detection** — same shape as `candidates.py::select_candidate`'s `by_key: dict[...]` accumulate-and-compare loop (`candidates.py:312-335`): accumulate normalized names in a dict, raise a typed `TableNameCollision` the moment two distinct source layers produce the same key, never silently pick one (matches D-23/D-24's "never silently picks a variant").

---

### `vicmap_acquire/manifest.py` (model + service, D-29/D-31/D-32)

**Analog:** `vicmap_acquire/evidence.py`

**Frozen dataclass result objects** (`download.py:185-192`, `DownloadResult`) — the in-process `ImportManifest` object Phase 3 consumes should be a `@dataclass(frozen=True)` in the same style, not a dict, matching `DownloadResult`'s role as "the API the next phase consumes in-process."

**Canonical JSON serialization** (`evidence.py:360-364`, the *only* existing precedent for deterministic hashable JSON in this repo):
```python
stream.write(json.dumps(dict(event), sort_keys=True, separators=(",", ":")))
```
Reuse this exact call shape for `manifest.json` (RESEARCH.md's own recommended `write_manifest` already follows it) — do not invent a second JSON convention.

**Redacted vs full-detail split** (`evidence.py`'s `SuccessEvent`/`SafeFailure` classes carry only safe, allowlisted fields — `order_id`, `sender` (masked via `mask_sender`), fingerprints — while raw values like the full mailbox path or message body never enter a `_SafeEvent`). Apply the identical split for D-31: `manifest.json` (full detail, git-ignored) vs. the redacted `SuccessEvent`-style operator evidence rendered via `evidence.py`'s existing `render_success`/`SuccessEvent` machinery — add a new `SuccessEvent.discovery_completed(...)`-style classmethod following the exact pattern of `SuccessEvent.candidate_selected` (`evidence.py:218-245`) and `SuccessEvent.artifact_finalized` (`evidence.py:271-281`), carrying only order ID, counts, target table names, and path fingerprints (never full filesystem paths or real layer names beyond the target table name).

**Fingerprinting reuse** — `manifest.py` should call `evidence.fingerprint()` (`evidence.py:137-143`) for any path/name that must appear in redacted output, exactly as `download.py`'s `DownloadResult.path_fingerprint` already does (`download.py:592-595`).

---

### `vicmap_acquire/evidence.py` (extend in place — new `Stage`/`ReasonCode` members)

**Analog:** itself — extend the existing closed enums and `_FAILURE_POLICY` mapping, never introduce a parallel vocabulary.

**Pattern to copy** (`evidence.py:37-134`):
```python
class Stage(str, Enum):
    ...
    ARTIFACT_WRITE = "artifact_write"
    INTERNAL = "internal"

class ReasonCode(str, Enum):
    ...
    ARTIFACT_WRITE_FAILED = "artifact_write_failed"
    INTERNAL_FAILURE = "internal_failure"

_FAILURE_POLICY = MappingProxyType({
    ReasonCode.ARTIFACT_WRITE_FAILED: (
        Stage.ARTIFACT_WRITE,
        "review_destination_and_preserve_existing_artifact",
    ),
    ...
})
```
Add new `Stage` members (e.g. `EXTRACTION`, `DISCOVERY`, `NAMING`, `MANIFEST`) and `ReasonCode` members for every typed failure named above (`ARCHIVE_TRAVERSAL_REJECTED`, `ARCHIVE_UNSAFE_MEMBER_REJECTED`, `ARCHIVE_CEILING_EXCEEDED`, `ARTIFACT_CHECKSUM_MISMATCH`, `UNSUPPORTED_FORMAT`, `LAYER_UNREADABLE`, `LAYER_EMPTY`, `GEOMETRY_TYPE_UNRESOLVED`, `CRS_UNRESOLVED`, `LAYER_SCHEMA_INCOMPLETE`, `TABLE_NAME_INVALID`, `TABLE_NAME_COLLISION`), each with a remediation hint string in the same `snake_case_imperative` style as existing hints (`"review_target_without_broadening_allowlist"`, `"request_a_fresh_delivery"`). `reason_stage_vocabulary()` (`evidence.py:161-164`) must remain complete — every new `ReasonCode` needs an entry.

---

### Run/orchestration entry point (controller, request-response)

**Analog:** `candidates.py::recognize_candidate`/`select_candidate` composition style, and `download.py::download_artifact`'s top-level orchestration.

Compose the pipeline stages (checksum re-verify → extract → discover → name → manifest) the same way the existing acquisition flow composes recognition → selection → download: each stage is a pure/typed-failure function call, no stage silently swallows another stage's exception, and the top-level function's docstring states its commit-point/failure-boundary contract explicitly, exactly as `download_artifact`'s docstring does (`download.py:483-495`).

---

### `vicmap.toml` (config)

**Analog:** existing `[mailbox]` and `[download]` sections (`vicmap.toml:1-19`)

```toml
[download]
allowed_hosts = ["s3.ap-southeast-2.amazonaws.com"]
max_bytes = 10737418240
...
```
Add `[extraction]` (D-26 ceilings: `max_total_bytes`, `max_member_bytes`, `max_member_count`, `max_compression_ratio`) and `[discovery]` (D-34's `supported_formats = ["OpenFileGDB"]`) sections in the identical flat, explicitly-validated-key style — no nested tables, one allowlist entry to start, matching the file's existing "flat keys, single-entry allowlists" posture noted in RESEARCH.md's Integration Points.

---

### `flake.nix` (config)

**Analog:** existing `python3.withPackages` list and `packages` array (`flake.nix:58-63`)

```nix
devShells.default = pkgs.mkShell {
  packages = with pkgs; [
    git
    buildOpnix
    (python3.withPackages (ps: [ python-o365 ps.html5lib ]))
  ];
```
Extend to:
```nix
packages = with pkgs; [
  git
  buildOpnix
  gdal  # provides ogrinfo/ogr2ogr CLI — NOT propagated by python3Packages.pyogrio
  (python3.withPackages (ps: [ python-o365 ps.html5lib ps.pyogrio ps.pyproj ]))
];
```
Per RESEARCH.md's Package Legitimacy Audit, `pyogrio`/`pyproj` are `[SUS]`-flagged pending a `checkpoint:human-verify` task — the plan must gate this edit behind that checkpoint, not add it silently.

---

### `.gitignore` (config)

**Analog:** existing unanchored `artifacts/` entry (`.gitignore:19`, under "Private partial downloads and finalized acquisition output")

```
**/.vicmap-download-*.part
artifacts/
```
Add `runs/` as its own unanchored entry in the same section/style per D-25's "git-ignored the same way" requirement.

---

### Tests

**Analog:** `tests/test_download.py` (policy-dataclass + fake-transport regression style) for `test_extraction.py`; `tests/test_candidates.py` / `tests/test_origin.py` (pure-function unit style) for `test_naming.py`/`test_manifest.py`; `tests/test_html_visibility_differential.py` for a new differential-oracle discovery test.

**unittest class + fixture-builder idiom** (`test_download.py:1-40`):
```python
class _FakeResponse:
    def __init__(self, status_code=200, *, headers=None, chunks=(b"payload",), stream_error=None):
        ...
```
Mirror this fixture-object style for extraction tests: a `_FakeZipFile`/`_FakeZipInfo` builder constructing archives with specific traversal/symlink/ceiling-breaching members, rather than writing real zip files to disk for every case (though real small fixture zips are also fine per the calibration-archive precedent).

**Differential-oracle discipline** (`test_html_visibility_differential.py:1-20` docstring) — per the user's own memory note ("hand-written tests share the code's blind spot; use an independent oracle for parsing/visibility logic"), a discovery test that cross-checks `discovery.py`'s pyogrio-based output against a **separately invoked** `ogrinfo` call (not importing any of `discovery.py`'s parsing helpers) is the correct pattern here — this is explicitly the geometry-type string vocabulary risk RESEARCH.md's Pitfall 3 calls out (`'Point Z'` vs `'PointZ'` vs `'3D Point'` are three different spellings from the same GDAL install). State the independence constraint in the test's module docstring exactly as `test_html_visibility_differential.py` does, to prevent a future refactor from importing the implementation's own geometry-type-normalization helper into the oracle.

## Shared Patterns

### Typed Closed Failure (applies to every new module)
**Source:** `vicmap_acquire/download.py:21-59` (exception hierarchy) + `vicmap_acquire/evidence.py:37-134` (`Stage`/`ReasonCode`/`_FAILURE_POLICY`)
**Apply to:** `extraction.py`, `discovery.py`, `naming.py`, `manifest.py`, and the orchestration entry point.
```python
class DownloadFailure(RuntimeError):
    code = "download_http_failed"
    def __init__(self) -> None:
        super().__init__(self.code)

class DownloadUrlRejected(DownloadFailure):
    code = "download_url_rejected"
```
Every new failure type: bare `code` class attribute, no interpolated/dynamic message text, a matching `ReasonCode` member, and a `_FAILURE_POLICY` entry supplying `(Stage, remediation_hint)`.

### Frozen Policy Dataclass with `__post_init__` Validation
**Source:** `vicmap_acquire/download.py:135-183` (`DownloadPolicy`)
**Apply to:** `ExtractionPolicy` (D-26 ceilings), any `DiscoveryPolicy` (D-34's `supported_formats` allowlist).
Validate every field in `__post_init__`, normalize via `object.__setattr__` where needed (never mutate a frozen field directly), raise `ValueError` on any invalid configuration — matches `vicmap.toml`'s "explicitly validated keys with allowlists" posture already established for `[mailbox]`/`[download]`.

### Canonical Deterministic JSON
**Source:** `vicmap_acquire/evidence.py:360-364`
**Apply to:** `manifest.py`'s `manifest.json` writer and its `.sha256` sidecar.
```python
json.dumps(payload, sort_keys=True, separators=(",", ":"))
```
Do not invent a second serialization convention (RESEARCH.md's Code Examples section explicitly confirms this is the only existing precedent).

### Redacted vs Full-Detail Evidence Split
**Source:** `vicmap_acquire/evidence.py`'s `_SafeEvent`/`SuccessEvent`/`SafeFailure` classes, `mask_sender`, `fingerprint`
**Apply to:** All operator-facing stdout/stderr output from the new pipeline stages (extraction result, discovery result, naming/collision result, final manifest summary) — full detail only ever goes to `manifest.json` (git-ignored); rendered evidence uses `SuccessEvent`/`SafeFailure` subclasses/classmethods carrying only order ID, counts, target table names, and path fingerprints, per D-31.

### Atomic Publish / Single Commit Point
**Source:** `vicmap_acquire/download.py:261-306` (`_fsync_directory`, `_publish_artifact`)
**Apply to:** `extraction.py`'s run-directory publication (write to a `.tmp-{utc_ts}` sibling, one atomic rename as the sole commit point, `finally`-block best-effort cleanup that never overrides an already-decided outcome).

## No Analog Found

None — every new file has at least a role-match analog in `vicmap_acquire/`. The one genuine gap is not a file but a data-flow gap already flagged in RESEARCH.md Pitfall 5: **the Phase 1 → Phase 2 message-fingerprint handoff does not currently exist** (D-32 requires the manifest to record it, but `read_mailbox.py`'s `run_acquisition` never persists it anywhere Phase 2 can read after the process exits). This is not a pattern-mapping gap — it is a planning input the planner must resolve as its own task (e.g., extend `DownloadResult`/`run_acquisition`'s return value, or write a small durable sidecar file), not something an existing analog can silently paper over.

## Metadata

**Analog search scope:** `vicmap_acquire/` (all 6 modules), `vicmap.toml`, `flake.nix`, `.gitignore`, `tests/` (all 7 files, 2 read in full: `test_download.py` header, `test_html_visibility_differential.py` header)
**Files scanned:** `vicmap_acquire/download.py` (609 lines, full), `vicmap_acquire/evidence.py` (376 lines, full), `vicmap_acquire/candidates.py` (335 lines, full), `vicmap_acquire/origin.py` (198 lines, full), `vicmap.toml` (19 lines, full), `flake.nix` (76 lines, full), `.gitignore` (full), plus targeted reads of `tests/test_download.py` and `tests/test_html_visibility_differential.py` headers
**Pattern extraction date:** 2026-09-14
