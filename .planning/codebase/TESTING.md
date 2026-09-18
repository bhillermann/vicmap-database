# Testing Patterns

**Analysis Date:** 2026-09-18

## Test Framework

**Runner:**
- `unittest` (Python standard library)
- Test discovery via `python -m unittest discover` or direct module execution
- No pytest/nose configuration detected

**Assertion Library:**
- `unittest.TestCase` assertion methods: `assertEqual()`, `assertTrue()`, `assertRaises()`, `assertIn()`, `assertIsNone()`

**Run Commands:**
```bash
python -m unittest discover tests/       # Run all tests
python -m unittest tests.test_discovery  # Run specific test module
python -m unittest tests.test_discovery.FindDatasetsTest  # Run specific test class
```

## Test File Organization

**Location:**
- Tests co-located in separate `tests/` directory (not in source tree)
- Test files mirror source structure by naming: `tests/test_discovery.py` tests `vicmap_acquire/discovery.py`
- Fixtures in `tests/fixtures/` subdirectory
- Fixture builders in `tests/fixtures/build_fixtures.py`

**Naming:**
- Test modules: `test_<module_name>.py` (e.g., `test_discovery.py`)
- Test classes: `<ComponentName>Test` or `<ComponentName>Test<Aspect>` (e.g., `FindDatasetsTest`, `NormalizeTargetTableNameTest`)
- Test methods: `test_<behavior_description>()` (e.g., `test_finds_the_single_vmadd_dataset()`)

**Structure:**
```
tests/
├── __init__.py
├── test_discovery.py         # Tests for discovery.py
├── test_discovery_differential.py  # Cross-check vs oracle
├── test_discovery_tracer.py
├── test_discovery_config.py
├── test_manifest.py
├── test_naming.py
├── test_extraction.py
├── test_download.py
├── test_evidence.py
├── test_candidates.py
├── test_origin.py
├── test_graph.py
├── test_provenance.py
├── test_repository_policy.py
├── test_html_visibility_differential.py  # Differential oracle test
├── fixtures/
│   ├── Order_TRACER1.zip              # Real fixture data
│   ├── geometryless_gdb.zip
│   ├── point_z_gdb.zip
│   └── build_fixtures.py
```

## Test Structure

**Suite Organization:**
- Each test class inherits from `unittest.TestCase`
- `setUp()` method initializes test fixtures and temporary resources
- Test methods are independent; setUp runs before each test
- Example from `tests/test_discovery.py`:

```python
class FindDatasetsTest(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        self.run_dir = self.make_temp_dir("find-datasets-")
        _extract(ORDER_TRACER1, self.run_dir)

    def test_finds_the_single_vmadd_dataset(self):
        datasets = discovery.find_datasets(self.run_dir, DEFAULT_POLICY)
        self.assertEqual(1, len(datasets))
        path, driver = datasets[0]
        self.assertTrue(str(path).endswith("VMADD.gdb"))
        self.assertEqual("OpenFileGDB", driver)
```

**Patterns:**
- **Cleanup via context managers**: `addCleanup()` used to register cleanup functions (e.g., `shutil.rmtree`)
  ```python
  def make_temp_dir(self, prefix: str) -> Path:
      temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
      self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
      return temp_dir
  ```

- **Mixins for shared setup**: `_TempDirMixin` shared by multiple test classes
  
- **Exception testing with context managers**: `assertRaises()` captures and inspects exceptions
  ```python
  with self.assertRaises(discovery.UnsupportedFormat):
      discovery.find_datasets(empty_dir, DEFAULT_POLICY)
  ```

- **Exception message inspection**: Captured context object inspected for redacted output
  ```python
  with self.assertRaises(discovery.LayerUnreadable) as ctx:
      discovery.find_datasets(lying_dir, DEFAULT_POLICY)
  self.assertNotIn("pyogrio", str(ctx.exception))
  self.assertEqual("layer_unreadable", str(ctx.exception))
  ```

- **Parametric testing via `subTest()`**: Not unittest's `subTest` in traditional use; instead loops test multiple cases
  ```python
  invalid_inputs = [("", "ADDRESS"), ("VMADD", ""), ...]
  for dataset_stem, layer_name in invalid_inputs:
      with self.subTest(dataset_stem=dataset_stem, layer_name=layer_name):
          try:
              normalize_target_table_name(dataset_stem, layer_name)
          except TableNameInvalid:
              pass
          except Exception as exc:
              self.fail(f"expected TableNameInvalid, got {type(exc).__name__}")
          else:
              self.fail("expected TableNameInvalid, no exception raised")
  ```

## Mocking

**Framework:** `unittest.mock` (Python standard library)

**Patterns:**
- `patch.object()` to mock specific module attributes/functions
- `MagicMock()` for fake return values
- `side_effect` to raise exceptions on call
- Mocking only external seams (pyogrio, subprocess, file I/O)

**Example from `test_discovery.py`:**
```python
def test_injected_list_layers_exception_surfaces_as_layer_unreadable(self):
    lying_dir = self.make_temp_dir("list-layers-raises-")
    (lying_dir / "FAKE.gdb").mkdir()
    with patch.object(
        discovery.pyogrio,
        "list_layers",
        side_effect=RuntimeError("some pyogrio/GDAL diagnostic text"),
    ):
        with self.assertRaises(discovery.LayerUnreadable) as ctx:
            discovery.find_datasets(lying_dir, DEFAULT_POLICY)
    self.assertNotIn("pyogrio", str(ctx.exception))
```

**What to Mock:**
- External libraries/drivers: `pyogrio`, `pyproj`, `subprocess`
- File system operations when determinism is needed
- Network calls (none in this codebase)
- Do NOT mock standard library primitives like `Path` unless absolutely necessary

**What NOT to Mock:**
- Internal vicmap_acquire modules (unit test boundaries instead)
- Data structures and value objects
- Exception classes
- Pure functions (call directly instead)

## Fixtures and Factories

**Test Data:**
- Real data in `tests/fixtures/`: `Order_TRACER1.zip`, `geometryless_gdb.zip`, `point_z_gdb.zip`
- ZIP archives extracted to temporary directories for each test via `_extract()` helper
- Lightweight stand-in objects created on-the-fly for isolated unit tests

**Factory Pattern from `test_manifest.py`:**
```python
def _field(name: str, ogr_type: str, *, width=None, precision=None, nullable=True):
    return discovery.FieldProfile(
        name=name, ogr_type=ogr_type, width=width, precision=precision, nullable=nullable
    )

def _layer_profile(**overrides) -> discovery.LayerProfile:
    defaults = dict(
        dataset_relative_path="gda2020_vicgrid/filegdb/whole_of_dataset/victoria/VMADD.gdb",
        dataset_stem="VMADD",
        ...
    )
    return discovery.LayerProfile(**{**defaults, **overrides})
```

**Location:**
- Fixtures directory: `tests/fixtures/`
- Factories and helpers at top of test modules or in test classes as static methods
- Shared helpers (e.g., `_extract()`, `_TempDirMixin`) defined in test modules

## Coverage

**Requirements:** Not explicitly configured
- No `.coverage` configuration file detected
- Coverage not enforced in the build

**View Coverage:**
```bash
python -m coverage run -m unittest discover tests/
python -m coverage report
python -m coverage html
```

## Test Types

**Unit Tests (Primary):**
- Scope: Single function or closely related functions
- Approach: Fast, deterministic, no external dependencies
- Example: `NormalizeTargetTableNameTest` tests pure naming normalization without geodatabases
- Files: `test_naming.py`, `test_origin.py` (pure functions with no I/O)

**Integration Tests:**
- Scope: Multiple modules working together or with real fixtures
- Approach: Use real fixture data and isolated temporary directories
- Example: `ReadFieldSchemaTest` in `test_discovery.py` uses real `Order_TRACER1.zip` fixture
- Files: `test_discovery.py`, `test_extraction.py`, `test_manifest.py` (composition tests)

**Differential/Oracle Tests:**
- Scope: Implementation cross-checked against independent oracle
- Approach: Oracle is hand-written, completely independent of implementation
- Constraint: Oracles MUST NOT import implementation functions, only public data containers
- Example: `test_discovery_differential.py` compares `discover_layers()` output against independent `ogrinfo -json` parsing
  - Oracle functions: `_run_ogrinfo_json()`, `_oracle_layer()`, `_oracle_geometry_normalized()`
  - Module imports ONLY: `discover_layers`, `DiscoveryPolicy` (data container)
  - Never imports: `read_field_schema`, `profile_layer`, geometry normalization helpers
- Enforced by: `ImportIndependenceTest` uses `ast` module to verify import constraint at runtime
- Files: `test_discovery_differential.py`, `test_html_visibility_differential.py`

## Common Patterns

**Async Testing:**
- Not applicable (synchronous Python project)

**Error Testing:**
- All error testing uses `assertRaises()` context manager
- Exception code/message validated by inspecting `ctx.exception`
- Pattern ensures exceptions are closed (no raw subprocess/driver text exposed)
- Example:
  ```python
  with self.assertRaises(discovery.LayerUnreadable) as ctx:
      discovery.find_datasets(lying_dir, DEFAULT_POLICY)
  self.assertNotIn("GDAL", str(ctx.exception))
  self.assertEqual("layer_unreadable", str(ctx.exception))
  ```

**Module Independence Verification:**
- `ast` module used to inspect source code imports at test time
- Verifies layer/dependency constraints are maintained
- Examples:
  - `NamingModulePurityTest` in `test_naming.py` confirms `naming` has no database/socket imports
  - `ImportIndependenceTest` in `test_discovery_differential.py` confirms differential oracle stays independent

---

*Testing analysis: 2026-09-18*
