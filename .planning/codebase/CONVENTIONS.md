# Coding Conventions

**Analysis Date:** 2026-09-22

## Naming Patterns

**Files:**
- Source modules: `lowercase_with_underscores.py`
- Test files: `test_<module_name>.py`
- Examples: `vicmap_acquire/evidence.py`, `vicmap_acquire/staging.py`, `tests/test_evidence.py`

**Functions:**
- snake_case for all function and variable names
- Private functions/internal helpers: prefix with `_` (e.g., `_positive_integer`, `_bounded_integer`)
- Validator functions: `_<type_name>` (e.g., `_host`, `_identifier`, `_index_columns`)
- Examples in `vicmap_acquire/staging.py`: `_host()`, `_identifier()`, `_bounded_composed_identifier()`

**Classes:**
- PascalCase for all class names
- Exception classes: named descriptively (CandidateNone, CandidateAmbiguous) or inherit from base class
- Dataclasses: use frozen=True for immutable data structures
- Examples: `ImportManifest`, `StagingPolicy`, `DownloadFailure` in `vicmap_acquire/manifest.py`, `vicmap_acquire/staging.py`, `vicmap_acquire/download.py`

**Types and Type Aliases:**
- Type aliases: UPPER_CASE or descriptive name
- Example: `EventSink = Callable[[object], None]` in `discover_order.py`

**Constants and Module-Level Variables:**
- Public constants: UPPER_CASE
- Private/internal: prefix with `_` (e.g., `_HIDDEN_ELEMENTS`, `_HEX_64`)
- Regex patterns: prefix with `_` (e.g., `_SIDECAR_DIGEST`, `_HOSTNAME`)
- Mapping/lookup tables: `_<NAME>` (e.g., `_REASON_BY_CODE`, `_FAILURE_POLICY`)
- Examples in `vicmap_acquire/evidence.py`: `_HEX_64`, `_ORDER_ID`, `_HOST`, `_FAILURE_POLICY`

## Code Style

**Formatting:**
- No linter/formatter configured; follow PEP 8 implicitly
- Line length: appears to be followed naturally (~100-120 chars typical)
- Indentation: 4 spaces

**Imports:**
- Place `from __future__ import annotations` at top of every file (enables postponed evaluation)
- Order: stdlib imports, third-party imports, local imports
- Type imports from `typing` module (Callable, Iterable, Mapping, etc.)
- Example structure in `vicmap_acquire/staging.py`:
  ```python
  from __future__ import annotations
  
  import hashlib
  import ipaddress
  import os
  import re
  import subprocess
  from dataclasses import dataclass
  from pathlib import Path
  
  import psycopg
  from psycopg import sql
  from psycopg import errors as pg_errors
  
  import read_mailbox
  from vicmap_acquire.evidence import NOT_APPLICABLE, ProgressEvent, SuccessEvent
  ```

**Type Hints:**
- Use full type hints on all function signatures
- Use `tuple[X, ...]` for variable-length tuples
- Use `frozenset` for immutable sets
- Use union types with `|` syntax (Python 3.10+)
- Example from `vicmap_acquire/manifest.py`:
  ```python
  def build_manifest(
      *,
      order_id: str,
      run_timestamp: str,
      run_directory: Path,
      ...
  ) -> ImportManifest:
  ```

## Import Organization

**Order:**
1. Standard library imports (`import hashlib`, `import json`, etc.)
2. Type annotations from typing module (`from typing import Callable, Iterable`)
3. Third-party imports (`import requests`, `import psycopg`)
4. Local package imports (`import read_mailbox`, `from vicmap_acquire.evidence import ...`)

**Path Aliases:**
- No absolute import aliases configured
- All imports use full module paths from package root
- Example: `from vicmap_acquire.evidence import ReasonCode`

## Error Handling

**Exception Hierarchy:**
- Base exception classes define a `.code` attribute (string)
- Exception code matches the corresponding `ReasonCode` enum value
- Subclasses inherit and override `.code` attribute
- Example from `vicmap_acquire/download.py`:
  ```python
  class DownloadFailure(RuntimeError):
      code = "download_http_failed"
      def __init__(self) -> None:
          super().__init__(self.code)
  
  class DownloadUrlRejected(DownloadFailure):
      code = "download_url_rejected"
  ```

**Exception Messages:**
- Never include sensitive information (file paths, SQL text, driver diagnostics)
- Exception message == exception code only (e.g., `"download_url_rejected"`)
- No detailed error context in exception text
- Comments reference validation checkpoints (WR-06, D-58, etc.)

**Validator Pattern:**
- Internal validators return validated/coerced value on success
- Raise `ValueError` with brief description on failure
- Named `_<type>` to indicate internal validator
- Examples from `vicmap_acquire/staging.py`:
  ```python
  def _positive_integer(value: object) -> int:
      if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
          raise ValueError("staging policy values must be positive integers")
      return value
  
  def _identifier(value: object) -> str:
      if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
          raise ValueError("staging policy identifier is not a safe scalar")
      return value
  ```

**Exception Chaining:**
- Use `from None` to suppress context when converting exceptions
- Example from `vicmap_acquire/candidates.py`:
  ```python
  except Exception:
      raise CandidateAmbiguous() from None
  ```

## Logging

**Framework:** `print()` to stdout (no logging library)

**Patterns:**
- Evidence events serialized to JSON Lines via `evidence` module
- No application-level debug logging
- Diagnostics captured separately for operator review (e.g., stderr from db_load)

## Comments

**When to Comment:**
- Explain non-obvious algorithm behavior
- Document security/validation rationale
- Reference design decisions and checkpoints (D-58, WR-06, etc.)
- Explain workarounds and constraints

**Style:**
- Inline comments explain WHY, not WHAT
- Comments reference requirement IDs (D-61, GEO-02, DB-01, WR-01, etc.)
- Example from `vicmap_acquire/evidence.py`:
  ```python
  # D-61: server-controlled identity text (version(), PostGIS_Full_Version())
  # rendered in clear, bounded to printable ASCII with no control characters
  # so a hostile or malformed server banner cannot inject newlines into the
  # JSON Lines stream...
  _SERVER_VERSION_TEXT = re.compile(r"[ -~]{1,1024}")
  ```

**Docstrings:**
- Module docstrings: explain purpose and key contracts
- Function docstrings: one-line purpose, explain behavior
- Class docstrings: explain responsibility
- Example from `vicmap_acquire/staging.py`:
  ```python
  """The PostGIS staging boundary: connect, prove privilege, load, validate (D-41..D-64).
  
  This is the first and only module in the package permitted to import a
  PostgreSQL driver (D-41) -- every other module in ``vicmap_acquire`` stays
  driver-free by construction...
  """
  ```

## Function Design

**Size:** Functions are typically 10-50 lines; complex operations broken into helpers

**Parameters:**
- Use keyword-only arguments for clarity (function definition with `*` separator)
- Example from `vicmap_acquire/manifest.py`:
  ```python
  def build_manifest(
      *,
      order_id: str,
      run_timestamp: str,
      ...
  ) -> ImportManifest:
  ```

**Return Values:**
- Return frozen dataclasses for immutable results
- Return None for operations without meaningful return value
- Return tuple for multiple values

**Pure Functions:**
- Private helpers are typically pure (no side effects)
- Public functions may perform I/O but clearly documented
- Examples: `_positive_integer()`, `_identifier()` are pure validators

## Module Design

**Exports:**
- `__all__` is empty (e.g., `__all__ = []` in `vicmap_acquire/__init__.py`)
- No barrel files; import specific items from modules
- Private module functions/classes use `_` prefix

**Data Structures:**
- Immutable dataclasses with `frozen=True`
- Use frozenset for immutable sets
- Use tuple (not list) for fixed collections
- Example from `vicmap_acquire/manifest.py`:
  ```python
  @dataclass(frozen=True)
  class ImportManifest:
      schema_version: int
      order_id: str
      ...
      layers: tuple[ManifestLayer, ...]
      companions: tuple[CompanionFile, ...]
  ```

**Validation in Dataclasses:**
- Use `__post_init__` to validate dataclass fields
- Raise `ValueError` for validation errors
- Example from `vicmap_acquire/staging.py`:
  ```python
  def __post_init__(self) -> None:
      _host(self.host)
      _bounded_integer(self.port, 1, 65535)
      ...
      if self.lock_timeout_seconds > self.statement_timeout_seconds:
          raise ValueError("lock_timeout_seconds must not exceed statement_timeout_seconds")
  ```

---

*Convention analysis: 2026-09-22*
