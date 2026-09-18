---
phase: 02
phase_name: "safe-geospatial-discovery"
project: "Vicmap Database"
generated: "2026-09-18"
counts:
  decisions: 10
  lessons: 7
  patterns: 8
  surprises: 5
missing_artifacts:
  - "02-UAT.md"
---

# Phase 02 Learnings: safe-geospatial-discovery

## Decisions

### D-21 locked: target table name is `{gdb_stem}_{layer}`, normalized, no configurable prefix
`VMADD.gdb`/`ADDRESS` publishes as `vmadd_address`. Confirmed at an operator checkpoint in 02-01 and again end to end against the real 233 MB delivery in 02-06 (`vicmap.vmadd_address`).

**Rationale:** A configurable prefix adds a policy knob with no demonstrated need; the deterministic derivation is verifiable against a real delivery.
**Source:** 02-01-SUMMARY.md, 02-06-SUMMARY.md, STATE.md

---

### Reserved-keyword list fetched from live PostgreSQL 18.6 documentation, not retyped
Parsed Appendix C's HTML table programmatically: 101 keywords across both blocking categories.

**Rationale:** The plan warned that a hand-typed shortlist misses the second blocking category (`binary`, `concurrently`, `current_schema`). Programmatic extraction guarantees completeness against the actual categorization.
**Source:** 02-05-SUMMARY.md, STATE.md

---

### Recalibrated `vicmap.toml`'s `max_compression_ratio` from 20 to 200 rather than adding a size-floor exemption
Evidence-justified against both measured worst cases: the real delivery at 139.2432x and the tracer fixture at 122.6667x.

**Rationale:** `max_total_bytes`/`max_member_bytes` are the binding resource guard, enforced per 1 MiB chunk during streaming. The ratio check runs after a member is fully written and is an anomaly detector, so raising it does not change worst-case bytes written. A size-floor exemption mechanism would add a second policy surface for no additional safety.
**Source:** 02-07-SUMMARY.md, STATE.md

---

### Kept two complementary aliasing guards instead of consolidating into one
The pre-pass identity key (resolved destination `Path` plus case-folded string) and the write-time `os.open(O_EXCL)` were deliberately left as separate guards.

**Rationale:** The pre-pass is provably order-independent and catches nearly everything before any bytes are written; the exclusive create is the filesystem's own truth and defends against identity-key edge cases the two Python-level keys did not anticipate.
**Source:** 02-08-SUMMARY.md, STATE.md

---

### Rejected `02-REVIEW.md`'s proposed `destination.exists()` aliasing check
Recorded explicitly as a correction rather than silently substituting a different fix.

**Rationale:** `_validate_members` runs to completion before any output handle opens, and `temp_dir` is freshly created immediately beforehand, so `destination.exists()` is `False` for every member in the same archive — it would have caught nothing. The review's diagnosis of the defect was correct even though its proposed mechanism was not.
**Source:** 02-08-SUMMARY.md, STATE.md

---

### Scoped `write_manifest`'s rollback to a nested `try` around only the sidecar write
Placed after the manifest write already returned without raising.

**Rationale:** That success is the proof this call created `manifest.json` via its own `O_EXCL` open, so the rollback can never remove a file it did not create. A broad handler around both writes could unlink a pre-existing manifest.
**Source:** 02-09-SUMMARY.md, STATE.md

---

### Added `ensure_ascii=False` to `write_manifest`'s `json.dumps`, left `evidence.py`'s identical idiom unchanged
Treated as a behavior fix, not a cosmetic one.

**Rationale:** Without it, non-ASCII layer/dataset names serialize as `\uXXXX` escapes, so the manifest's byte length can never exceed its decoded character length — falsifying the required byte-identity property. `evidence.py`'s payload is already-redacted, ASCII-safe operator output, so the same change there would carry risk without benefit.
**Source:** 02-09-SUMMARY.md, STATE.md

---

### Kept `_fsync_directory` as a third private per-module copy
`manifest.py` duplicates the helper rather than importing `extraction.py`'s.

**Rationale:** Avoids coupling `manifest.py` to `extraction.py` for a durability helper, matching the existing independent copies in `extraction.py` and `download.py`.
**Source:** 02-09-SUMMARY.md

---

### `load_discovery_config` reuses `load_config` instead of duplicating shared validation
Layers `[extraction]`/`[discovery]` parsing on top, then delegates to `validate_discovery_policy`.

**Rationale:** One root of truth for the shared fields (`artifacts_dir`, `fingerprint_hex_chars`, `allowed_order_ids`) instead of ~40 duplicated lines, while keeping the two config loaders structurally parallel.
**Source:** 02-02-SUMMARY.md

---

### `run_discovery` re-raises the original typed exception after emitting a redacted failure event
No new orchestration-specific wrapper type.

**Rationale:** Keeps the acceptance criterion's literal wording true ("raises the closed `ArtifactChecksumMismatch`") and makes "no stage swallows another stage's exception" exact rather than approximate.
**Source:** 02-01-SUMMARY.md, STATE.md

---

## Lessons

### CPython's `zipfile` architecturally caps decompressed output at the declared `file_size`
`ZipExtFile._read1` truncates all output to `zinfo.file_size` (`data = data[:self._left]`) regardless of how `compress_size` or CRC-32 are crafted.

**Context:** An acceptance criterion asked for a member that "declares a small `file_size`, decompresses beyond it." That fixture cannot be built through the public `ZipFile.open()` API — any attempt either truncates or fails CRC-32. The test was rewritten to prove the equivalent constructible property: a tiny compressed footprint whose accurately-declared decompressed size legitimately exceeds the ceiling, tripping it from streamed bytes rather than from metadata.
**Source:** 02-03-SUMMARY.md, STATE.md

---

### `ZipFile.writestr()` and `ZipFile.open(mode="w")` both recompute `flag_bits` at write time
A pre-set encryption bit is discarded.

**Context:** Building a genuinely adversarial encrypted-member fixture required patching the on-disk general-purpose flag field directly after construction (`_patch_general_purpose_flag_bit`), not setting `ZipInfo.flag_bits`.
**Source:** 02-03-SUMMARY.md

---

### Compression-ratio calibration from overall and largest-member ratios misses the small-index case
Calibration in `02-RESEARCH.md` used the overall (~4.18x) and largest-member (~4.26x) ratios and set the ceiling at 20.

**Context:** The real delivery's tiny OpenFileGDB index members (`.gdbtablx`, `.atx`, 4–5 KB compressing to 35–90 bytes) reach ~139x. The shipped ceiling would have hard-stopped a real production run. The same blind spot had already surfaced locally in 02-01's tracer fixture and been worked around test-locally twice before being fixed in the shipped config in 02-07.
**Source:** 02-06-SUMMARY.md, 02-07-SUMMARY.md

---

### A research figure is not a verified figure
`02-RESEARCH.md` recorded 40 attribute fields for the real `ADDRESS` layer; a live `ogrinfo -json -al -so` run returned 61, all genuine Vicmap schema attributes.

**Context:** Found when the test asserted the plan's stated value and failed with `40 != 61`. The test now pins the live-verified 61, with an inline comment recording the discrepancy so a future reader is not confused by `02-RESEARCH.md`. The `PFI`/`EZI_ADDRESS`/`UFI` widths from the same research were independently reconfirmed correct — the research was not wholesale wrong, which is precisely why each figure needs its own check.
**Source:** 02-06-SUMMARY.md, STATE.md

---

### A test that builds its own policy object proves nothing about the shipped configuration
`LiveDeliveryRegressionTest` originally constructed a hand-built `ExtractionPolicy` with a test-local ceiling.

**Context:** That let the shipped `vicmap.toml` stay broken for the real delivery while the live test passed. It now sources every ceiling from the repository's own shipped file via `read_mailbox.load_discovery_config`, so the test proves the shipped policy works rather than a private copy of it. `run_root` stays test-local, since it must never point at the repository's own `runs/` directory.
**Source:** 02-07-SUMMARY.md, STATE.md, 02-VERIFICATION.md

---

### A correct defect diagnosis can carry an incorrect proposed mechanism
`02-REVIEW.md` correctly identified the aliasing bypass but proposed `destination.exists()`, which would have caught nothing.

**Context:** Accepting a review's fix verbatim because its diagnosis is sound is unsafe. The correction was recorded explicitly in the SUMMARY rather than silently substituted.
**Source:** 02-08-SUMMARY.md

---

### Mocking `os.open` must accommodate every call site's arity
A `side_effect` requiring all three positional arguments raised `TypeError` when `_fsync_directory` called `os.open(directory, os.O_RDONLY)` with two.

**Context:** The outer catch-all mapped that `TypeError` to `ArchiveUnreadable`, masking the intended `RunDirectoryWriteFailed` RED failure. Giving the mock's `mode` parameter a default fixed it — production code was already correct, so this was a test-fixture-only fix.
**Source:** 02-08-SUMMARY.md

---

## Patterns

### Reject-before-write member validation
`_validate_members(infolist, destination_root, policy)` runs one archive-wide pass — member-count ceiling, per-member path/mode/encryption guards, then duplicate detection — completing entirely before the write phase begins.

**When to use:** Any archive or batch ingestion where a partially-written output is worse than no output.
**Source:** 02-01-SUMMARY.md, 02-03-SUMMARY.md

---

### Differential-oracle test with an `ast` self-check on imports
`test_discovery_differential.py` derives expected values from `ogrinfo`'s own JSON via its own subprocess call and parsing, never from `vicmap_acquire.discovery`'s output. An `ast` self-check enforces the allowed import set as exactly `{discover_layers, DiscoveryPolicy}`.

**When to use:** Parsing, normalization, or visibility logic where hand-written tests would share the implementation's blind spot. The `ast` check turns the independence rule from a comment into a machine-checked invariant.
**Source:** 02-04-SUMMARY.md, 02-01-SUMMARY.md

---

### Calibration test that derives its threshold at test time
`ShippedCeilingCalibrationTest` computes the worst-case ratio from an independent bare `zipfile` walk of the real archive rather than from a number copied into the test.

**When to use:** Any tuned ceiling or threshold. The test goes red both if the ceiling regresses and if a future delivery's data shape changes — a hardcoded expected value catches only the first.
**Source:** 02-07-SUMMARY.md, 02-VERIFICATION.md

---

### Provenance-integrity oracle written from the contract, not the guard
Recomputes every recorded member's byte count and SHA-256 from disk, never from the extraction result's own bookkeeping.

**When to use:** Wherever recorded provenance could drift from reality. It fails for any future defect that lets the two diverge, regardless of the mechanism, so it survives reimplementation of the guard it protects.
**Source:** 02-VERIFICATION.md

---

### Atomic publish via `os.rename` from a private `.tmp-` sibling
The rename into the published run directory is the sole commit point. Failed guard trips leave the `.tmp-` directory behind for inspection (D-25) and never delete it.

**When to use:** Any multi-file publish that must be all-or-nothing, where post-mortem inspection of a failed attempt has value.
**Source:** 02-01-SUMMARY.md

---

### Total-function-with-catch-all at every entry point
Each discovery entry point collapses unexpected exceptions into one typed closed failure, never raw driver or subprocess text, mirroring `download_artifact`'s `except <TypedFailure>` / `except OSError` / `finally` shape.

**When to use:** Boundaries where third-party libraries (GDAL, pyogrio, subprocesses) can raise anything, and where leaking their text would expose paths or internals to an operator-facing report.
**Source:** 02-01-SUMMARY.md, 02-03-SUMMARY.md

---

### Scoped rollback keyed on a prior `O_EXCL` success
Only the just-created file — provably created by this call, because its `O_EXCL` open already returned without raising — is unlinked when a later step fails.

**When to use:** Multi-step publishes where a broad rollback handler risks deleting a pre-existing file the current call did not create.
**Source:** 02-09-SUMMARY.md

---

### Exclusive-create output handles as the write-time complement to a pre-pass guard
`os.open(..., O_EXCL)` per member makes the filesystem the last oracle for any alias the Python-level pre-pass might miss.

**When to use:** Defense in depth for adversarial input, where the pre-pass guard's key derivation is the thing most likely to be wrong.
**Source:** 02-08-SUMMARY.md

---

## Surprises

### The hardening that closed CR-01 introduced a new defect of its own
The write-time exclusive-create guard leaked the destination file descriptor and orphaned a 0-byte file whenever `zip_file.open()` raised after `os.open()` had already succeeded — a compound `with` ordering bug.

**Impact:** Raised as WR-03 and live-reproduced twice (in `02-REVIEW.md` and independently in `02-VERIFICATION.md`). Non-blocking: no provenance corruption, no false success, no survival past process exit. Fixed after verification in commit `d6b0754` by reordering the compound `with` so the descriptor's context manager enters first, with a file-descriptor-count regression test. A fix is a change like any other, and deserves the same adversarial reading as the code it replaces.
**Source:** 02-VERIFICATION.md, 02-REVIEW.md

---

### The shipped configuration had never been exercised against a real delivery
`vicmap.toml`'s `max_compression_ratio = 20` would have hard-stopped `discover_order.py` against the real `Order_OK0VUZ.zip` on the first production run.

**Impact:** Surfaced only in 02-06, the first plan to run the complete path against the real 233 MB artifact. It was flagged rather than fixed there (the file was a completed sibling plan's), and closed in 02-07. Three separate plans had worked around the same symptom test-locally before anyone tested the shipped value.
**Source:** 02-06-SUMMARY.md, 02-07-SUMMARY.md

---

### An acceptance criterion described a fixture that cannot exist
The "declares a small `file_size`, decompresses beyond it" member is unconstructable through CPython's public `zipfile` API.

**Impact:** Required reading CPython 3.14's `zipfile.py` source to establish, then rewriting the criterion to its closest constructible equivalent and documenting the finding in the test module's docstring. The implemented ceiling logic still never consults `info.file_size`, so the plan's underlying intent held even though its literal wording could not.
**Source:** 02-03-SUMMARY.md

---

### Plan-to-plan token cost varied more than 5x
Actuals ranged from 3,410 tokens (02-07) to 18,529 (02-02) across nine plans of comparable nominal scope.

**Impact:** The three cheapest plans (02-07, 02-08, 02-09 — 3.4k, 4.0k, 4.0k) were all narrow gap-closure plans written against a specific review finding. The expensive ones were greenfield module builds. Scope shape predicts cost far better than task count does.
**Source:** 02-01 through 02-09 SUMMARY.md `actuals` blocks

---

### Splitting tasks into separate commits was fought in five of nine plans
02-02, 02-03, 02-04 and 02-05 all recorded a commit-sequencing deviation; 02-02 reconstructed an artificial Task-1-only file state to preserve atomicity.

**Impact:** The recurring cause was the same: 02-01 left several modules substantially complete, so later plans' "two tasks" were two edits to one function body sharing one exception wrap. Each SUMMARY chose honest history over fabricated intermediate commits and ran both tasks' `<verify>` commands against the final state. Worth treating as a planning signal — tasks that touch one function body are one task.
**Source:** 02-02-SUMMARY.md, 02-03-SUMMARY.md, 02-04-SUMMARY.md, 02-05-SUMMARY.md
