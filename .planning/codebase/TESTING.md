# Testing Patterns

**Analysis Date:** 2026-09-22

## Test Framework

**Runner:**
- unittest (Python standard library)
- Discovery and execution via `python -m unittest discover -s tests -p 'test_*.py' -v`
- Individual test modules via `python -m unittest tests.test_<module_name> -v`
- Single test class via `python -m unittest tests.test_<module_name>.<ClassName> -v`

**Assertion Library:**
- unittest built-in assertions (`assertEqual`, `assertRaises`, `assertIsNone`, etc.)
- Standard Python `assert` statements in some helper functions

**Run Commands:**
```bash
# Run all tests
python -m unittest discover -s tests -p 'test_*.py' -v

# Watch mode
# (Not configured - manual re-run required)

# Run a specific module
python -m unittest tests.test_staging -v

# Run a specific test class
python -m unittest tests.test_staging.DatabaseConfigTest -v

# Coverage
# (No coverage configuration detected)
```

## Test File Organization

**Location:**
- Test files co-located in `tests/` directory (separate from source)
- Pattern: `tests/test_<module_name>.py` mirrors `vicmap_acquire/<module_name>.py`
- Examples:
  - `tests/test_evidence.py` → `vicmap_acquire/evidence.py`
  - `tests/test_staging.py` → `vicmap_acquire/staging.py`
  - `tests/test_discovery.py` → `vicmap_acquire/discovery.py`
  - `tests/test_candidates.py` → `vicmap_acquire/candidates.py`

**Naming:**
- Test files: `test_<module>.py`
- Test classes: `<Description>Test` (e.g., `DatabaseConfigTest`, `FindDatasetsTest`, `CandidateRecognitionTest`)
- Test methods: `test_<specific_behavior>` (e.g., `test_happy_path_loads_every_field`, `test_missing_database_key_in_turn`)

**Fixture Location:**
- `tests/fixtures/` directory contains archived test data
- Example: `tests/fixtures/Order_TRACER1.zip`, `tests/fixtures/geometryless_gdb.zip`
- Fixtures referenced via `REPO_ROOT` constant at module level

## Test Structure

**Suite Organization:**
```python
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

class SomeTest(unittest.TestCase):
    def setUp(self):
        # Per-test setup
        pass
    
    def tearDown(self):
        # Per-test cleanup
        pass
    
    def test_specific_behavior(self):
        # Test implementation
        pass
```

**Patterns:**
- **Setup pattern** (from `tests/test_discovery.py`):
  ```python
  def setUp(self):
      self.run_dir = self.make_temp_dir("find-datasets-")
      _extract(ORDER_TRACER1, self.run_dir)
  ```

- **Teardown/Cleanup pattern** (using `addCleanup`):
  ```python
  def make_temp_dir(self, prefix: str) -> Path:
      temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
      self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
      return temp_dir
  ```

- **Assertion pattern**:
  ```python
  def test_loads_config(self):
      config = read_mailbox.load_database_config(path)
      self.assertEqual("127.0.0.1", config.host)
      self.assertEqual(5432, config.port)
  ```

## Mocking

**Framework:** `unittest.mock` (built-in)

**Patterns:**

- **Patch specific methods** (from `tests/test_discovery.py`):
  ```python
  with patch.object(discovery.pyogrio, "list_layers", return_value=[]):
      with self.assertRaises(discovery.DeliveryEmpty):
          discovery.find_datasets(empty_gdb_dir, DEFAULT_POLICY)
  ```

- **Patch with side effects**:
  ```python
  with patch.object(
      discovery.pyogrio,
      "list_layers",
      side_effect=RuntimeError("some pyogrio/GDAL diagnostic text"),
  ):
      with self.assertRaises(discovery.LayerUnreadable) as ctx:
          discovery.find_datasets(lying_dir, DEFAULT_POLICY)
  ```

- **MagicMock for complex objects** (from `tests/test_discovery.py`):
  ```python
  with patch.object(discovery.pyogrio, "read_info") as mock_info:
      mock_info.return_value = {"driver": "GPKG"}
      ...
  ```

**Import Pattern:**
```python
from unittest.mock import Mock, patch, MagicMock

# In test:
with patch("module.function", return_value=value):
    ...
```

**What to Mock:**
- External I/O (file system, network, database)
- Third-party library calls with hard-to-control behavior (pyogrio, psycopg)
- Timestamp generation (use datetime fixtures instead)
- Environment variables

**What NOT to Mock:**
- Internal functions (test them directly)
- Data validation logic
- Pure functions (they're deterministic)
- Exception classes

## Fixtures and Factories

**Test Data:**

- **Constant test data** (module-level):
  ```python
  AUTH_RESULTS_PASS = (
      "spf=pass smtp.mailfrom=maps.vic.gov.au;"
      "dkim=pass (signature was verified) header.d=maps.vic.gov.au;"
      ...
  )
  ```

- **Helper factory functions** (prefixed with `_`):
  ```python
  def _policy_kwargs(output_dir: Path, **overrides: object) -> dict[str, object]:
      """Build a complete, valid ``AcquisitionConfig`` kwargs mapping.
      
      ``overrides`` replaces individual fields so malformed-policy tests can
      mutate exactly one field while every other field remains valid.
      """
      base: dict[str, object] = dict(
          mailbox="automations@vegetationlink.com.au",
          folder="Inbox",
          allowed_senders=("noreply@datashare.maps.vic.gov.au",),
          ...
      )
      base.update(overrides)
      return base
  ```

- **Parameterized fixture data** (from `tests/test_evidence.py`):
  ```python
  _POLICY_MALFORMED_CASES: dict[str, tuple[dict[str, object], str | None]] = {
      "non-inbox folder": ({"folder": "Archive"}, None),
      "sender missing exactly one at-sign": (
          {"allowed_senders": ("not-an-email",)},
          None,
      ),
      ...
  }
  ```

**Location:**
- Archive fixtures: `tests/fixtures/`
- Shared constants: module-level in test file
- Helper builders: private functions prefixed with `_`

## Coverage

**Requirements:** No coverage tool configured; no target enforced

**View Coverage:** Not applicable

## Test Types

**Unit Tests (primary):**
- Scope: Single function or class method
- Approach: Pure function tests with fixtures; isolated from I/O
- Database connection tests: skip gracefully if PostgreSQL unavailable
- Examples: `test_happy_path_loads_every_field`, `test_fingerprint_length_is_configurable_within_bounds`

**Integration Tests:**
- Scope: Multiple functions/modules working together
- Approach: Use real fixtures (archived data) but mock external services
- Examples: end-to-end discovery tests using fixture archives
- Location: Same test file as unit tests, denoted by descriptive names like `LiveDeliveryRegressionTest`

**E2E Tests:**
- Not used in this codebase
- Database-dependent tests skip if PostgreSQL is unavailable

## Common Patterns

**Async Testing:**
Not applicable (synchronous codebase)

**Error Testing:**

- **Expected exception pattern**:
  ```python
  def test_missing_database_section_entirely(self):
      text = VALID_TOML.replace("\n" + _DATABASE_SECTION, "\n")
      with tempfile.TemporaryDirectory() as directory:
          path = _write_policy(directory, text)
          with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
              read_mailbox.load_database_config(path)
      self.assertEqual("config_invalid", caught.exception.code)
  ```

- **Exception message validation** (from `tests/test_discovery.py`):
  ```python
  with self.assertRaises(discovery.LayerUnreadable) as ctx:
      discovery.find_datasets(lying_dir, DEFAULT_POLICY)
  self.assertNotIn("pyogrio", str(ctx.exception))
  self.assertNotIn("GDAL", str(ctx.exception))
  ```

**Parametrized Testing (using subTest):**

- **Single parameter iteration**:
  ```python
  for sender in near_misses:
      with self.subTest(sender=sender):
          candidate = recognize_candidate(
              _metadata(sender=sender),
              lambda: loaded.append(True) or _mime(plain=f"Download {_url()}"),
              allowed_senders=(SENDER,),
              allowed_order_ids=("OK0VUZ",),
          )
          self.assertIsNone(candidate)
  ```

- **Multiple parameter iteration**:
  ```python
  for key in _DATABASE_KEY_NAMES:
      with self.subTest(key=key):
          lines = _DATABASE_SECTION.splitlines(keepends=True)
          remaining = [line for line in lines if not line.startswith(f"{key} ")]
          text = VALID_TOML.replace(_DATABASE_SECTION, "".join(remaining))
          self._assert_rejected(text)
  ```

**Mixin Pattern for Test Utilities:**

- **Reusable test helper mixin** (from `tests/test_discovery.py`):
  ```python
  class _TempDirMixin:
      def make_temp_dir(self, prefix: str) -> Path:
          temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
          self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
          return temp_dir
  
  class FindDatasetsTest(_TempDirMixin, unittest.TestCase):
      def setUp(self):
          self.run_dir = self.make_temp_dir("find-datasets-")
  ```

**Private Test Helper Functions:**

- Prefix with `_` to indicate internal to test module
- Examples from `tests/test_candidates.py`:
  ```python
  def _metadata(...) -> MessageMetadata:
      return MessageMetadata(...)
  
  def _url(filename: str = "Order_OK0VUZ.zip") -> str:
      return BASE_URL.format(filename=filename)
  
  def _mime(*, plain: str | None = None, html: str | None = None) -> bytes:
      message = EmailMessage()
      ...
      return message.as_bytes()
  
  def _recognize(...):
      return recognize_candidate(
          metadata,
          lambda: mime_bytes,
          allowed_senders=(SENDER,),
          ...
      )
  ```

**Test Organization by Concern:**

- Related test classes in same file
- Example from `tests/test_discovery.py`:
  - `FindDatasetsTest` - tests dataset enumeration
  - `ProfileLayerTest` - tests layer profiling
  - `DiscoverLayersTest` - tests full discovery flow

**Regression Documentation:**

- Test docstrings reference design checkpoints
- Example from `tests/test_discovery.py`:
  ```python
  def test_uppercase_geodatabase_extension_is_recognized(self):
      # At HEAD (pre-02-07) this ends in DeliveryEmpty: the uppercase
      # directory is never examined because the extension lookup is
      # case-sensitive (WR-01).
      ...
  ```

## Test Data Conventions

**TOML Configuration:**
- Store complete valid TOML in module constants
- Example from `tests/test_staging.py`:
  ```python
  VALID_TOML = """\
  [mailbox]
  address = "automations@vegetationlink.com.au"
  ...
  """
  ```

**Archived Fixtures:**
- Version control as `.zip` files in `tests/fixtures/`
- Extract to temp directory in test setup
- Clean up using `addCleanup(shutil.rmtree, ...)`

**Identifier Constants:**
- Reuse in test helpers and assertions
- Examples: `SENDER`, `READY`, `BASE_URL`, `AUTH_RESULTS_PASS`

---

*Testing analysis: 2026-09-22*
