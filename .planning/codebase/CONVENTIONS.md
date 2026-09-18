# Coding Conventions

**Analysis Date:** 2026-09-18

## Naming Patterns

**Files:**
- Snake_case for module files: `discovery.py`, `extraction.py`, `naming.py`, `manifest.py`
- Test files follow pattern: `test_<module_name>.py` (e.g., `test_discovery.py`, `test_naming.py`)

**Functions:**
- Snake_case for all functions and methods
- Private functions prefixed with single underscore: `_positive_integer()`, `_strip_comments()`
- Public functions are verbs or descriptive phrases: `find_datasets()`, `read_field_schema()`, `normalize_target_table_name()`

**Variables:**
- Local variables use snake_case
- Constants use UPPER_SNAKE_CASE: `_EXTENSION_DRIVERS`, `MANIFEST_SCHEMA_VERSION`, `_MAX_NAME_BYTES`
- Private constants prefixed with underscore: `_HEX_64`, `_RESERVED_KEYWORDS`

**Types:**
- Class names use PascalCase: `DiscoveryPolicy`, `LayerProfile`, `ImportManifest`
- Exception classes use PascalCase ending with "Failure" or "Error": `DiscoveryFailure`, `LayerUnreadable`, `NamingFailure`
- TypeVars and generics use UPPER_CASE: `_T = TypeVar("_T")`

## Code Style

**Formatting:**
- Nix flake defines dev environment with Python 3 packages
- No explicit linting/formatting tool configured (no `.eslintrc`, `.flake8`, `pyproject.toml` found)
- No `.prettierrc` or similar formatters configured
- Code style appears to follow PEP 8 implicitly

**Linting:**
- No explicit linter configuration visible
- Conventions appear to be enforced via code review (see phase documentation)

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first, enables forward references)
2. Standard library imports (stdlib modules)
3. Third-party imports (pyogrio, pyproj, O365, etc.)
4. Local imports (vicmap_acquire modules, discover_order, read_mailbox)

**Example from `discover_order.py`:**
```python
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import read_mailbox
from vicmap_acquire.discovery import DiscoveryFailure, DiscoveryPolicy, discover_layers
from vicmap_acquire.extraction import ArchiveFailure, ExtractionPolicy, extract_artifact
```

**Path Aliases:**
- No `__init__.py` aliases detected
- Direct imports from modules: `from vicmap_acquire.discovery import ...`
- Relative imports not used; absolute imports from package root preferred

## Error Handling

**Patterns:**
- **Closed exception hierarchy**: Each module defines a base `*Failure` class inheriting from `RuntimeError`
  - `DiscoveryFailure` in `vicmap_acquire/discovery.py`
  - `NamingFailure` in `vicmap_acquire/naming.py`
  - `DownloadFailure` in `vicmap_acquire/download.py`
  - `ArchiveFailure` in `vicmap_acquire/extraction.py`

- **Exception codes**: All custom exceptions define a `code` class attribute with a string code
  ```python
  class LayerUnreadable(DiscoveryFailure):
      code = "layer_unreadable"
  ```

- **No raw exception text**: Exceptions capture no external text (subprocess output, driver diagnostics, etc.)
  - Constructor raises with only `self.code` via `super().__init__(self.code)`
  - Exception chaining suppressed with `raise ... from None` when converting external exceptions

- **Total functions**: Public entry points are total with respect to their inputs
  - An unexpected exception collapses to one typed closed failure, never raw text
  - Example: `find_datasets()` catches all `Exception` and raises `LayerUnreadable()` from None

## Logging

**Framework:** No dedicated logging framework detected
- Code does not import `logging` module
- Logging/diagnostics appear to be handled externally via evidence.py event sink

**Patterns:**
- No inline print statements in acquisition modules
- `evidence.py` uses JSON Lines format for structured event output
- Events route through `event_sink` callable for emission

## Comments

**When to Comment:**
- Comments explain design rationale and reference design documents (D-21, D-23, D-34, etc.)
- Comments on classes/functions that are part of a closed protocol describe the protocol
- Inline comments explain non-obvious logic or edge cases
- Comments reference code review decisions and task tracking

**JSDoc/TSDoc:**
- Not applicable (Python project)
- Docstrings used instead

**Docstring Style:**
- First line is a one-line summary
- Blank line followed by extended description
- Design document references embedded: `D-21 through D-24 target-table normalization`
- Behavior description of public functions explains inputs, outputs, and failure modes
- Example from `discovery.py`:
  ```python
  def find_datasets(
      run_directory: Path, policy: DiscoveryPolicy
  ) -> tuple[tuple[Path, str], ...]:
      """Return every recognized dataset beneath ``run_directory``, paired with
      its actual driver, ordered by relative path under plain code-point
      comparison (D-34).
      
      A path is a *candidate* only when its suffix is in ``_EXTENSION_DRIVERS``
      ...
      """
  ```

## Function Design

**Size:** Functions are generally 20-60 lines
- Focused on single responsibility
- Complex logic broken into helper functions with leading underscore
- Example: `find_datasets()` is ~60 lines handling enumeration logic

**Parameters:**
- Use keyword-only arguments where appropriate via `*` separator in function signature
- Type hints on all parameters: `def build_manifest(*, order_id: str, run_timestamp: str, ...)`
- Dataclass frozen objects used for configuration/policy objects requiring multiple parameters

**Return Values:**
- All functions explicitly annotated with return type
- Return None explicitly only when appropriate; don't return bare None implicitly
- Tuples used for multiple return values: `tuple[tuple[Path, str], ...]`
- Return values are often immutable types: tuples, frozensets, frozen dataclasses

## Module Design

**Exports:**
- All public functions/classes documented in module docstring
- Private symbols prefixed with underscore
- Module docstrings explain overall responsibility and design constraints
- Example from `naming.py`: "This module has no I/O, opens no database connection (D-23), and does not import discovery, manifest, extraction, or read_mailbox"

**Dataclasses:**
- Frozen dataclasses used extensively for immutable value objects: `@dataclass(frozen=True)`
- Validation in `__post_init__()` method for policy/configuration objects
- No mutable state in dataclasses once created

**Example from `discovery.py`:**
```python
@dataclass(frozen=True)
class DiscoveryPolicy:
    """Complete non-secret policy for one discovery pass (D-34)."""
    supported_formats: tuple[str, ...]
    ogrinfo_timeout_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.supported_formats, tuple) or not self.supported_formats:
            raise ValueError("supported_formats must be a non-empty tuple")
        ...
```

**Immutable Collections:**
- `frozenset` for constant sets: `_AUTH_METHODS = frozenset({...})`
- `MappingProxyType` for immutable dicts: `_EXTENSION_DRIVERS = MappingProxyType({...})`
- Tuple unpacking preferred over lists

## Type Annotations

**Pattern:**
- PEP 484 style type hints throughout
- Forward reference strings not needed (enabled by `from __future__ import annotations`)
- Use `|` for unions (Python 3.10+): `str | None` instead of `Optional[str]`
- Use `collections.abc` for protocol types: `Iterator`, `Mapping`, `Callable`
- Use `typing` for special forms: `TypeVar`, `TextIO`, `TYPE_CHECKING`

**Example from `discovery.py`:**
```python
def read_field_schema(
    dataset_path: Path, policy: DiscoveryPolicy
) -> dict[str, tuple[FieldProfile, ...]]:
    """..."""
```

---

*Convention analysis: 2026-09-18*
