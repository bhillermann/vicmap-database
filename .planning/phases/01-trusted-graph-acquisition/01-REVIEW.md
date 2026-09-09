---
phase: 01-trusted-graph-acquisition
reviewed: 2026-09-09T02:00:55Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - .gitignore
  - read_mailbox.py
  - tests/__init__.py
  - tests/test_candidates.py
  - tests/test_download.py
  - tests/test_evidence.py
  - tests/test_graph.py
  - vicmap.toml
  - vicmap_acquire/__init__.py
  - vicmap_acquire/candidates.py
  - vicmap_acquire/download.py
  - vicmap_acquire/evidence.py
  - vicmap_acquire/graph.py
findings:
  critical: 3
  warning: 5
  info: 0
  total: 8
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-09-09T02:00:55Z  
**Depth:** standard  
**Files Reviewed:** 13  
**Status:** issues_found

## Narrative Findings (AI reviewer)

The complete Phase 01 source, test, ignore, and policy scope was reviewed directly. The deterministic suite passes all 81 tests, but it does not cover several cross-boundary failure states. In particular, the acquisition trust decision does not authenticate artifact ownership, an accepted configuration value can turn a successfully published artifact into a reported failure, and publication cleanup can likewise reverse the reported outcome after the final path is visible.

## Summary

Three blocker-class defects must be resolved before shipping. Five warnings cover incomplete configuration validation, HTML recognition, an O365 SDK boundary mistake, failure-event robustness, and incomplete artifact ignore coverage. Exact-host HTTPS validation and manual redirect handling reject the tested off-host, downgrade, userinfo, port, fragment, and loop cases; no separate redirect-bypass was found in the reviewed implementation.

## Critical Issues

### CR-01: Message and URL checks do not authenticate artifact provenance

**Classification:** BLOCKER  
**Files:** `/home/brendon/Development/vicmap-database/vicmap_acquire/graph.py:169-195`, `/home/brendon/Development/vicmap-database/vicmap_acquire/candidates.py:179-215`, `/home/brendon/Development/vicmap-database/vicmap_acquire/download.py:165-180`, `/home/brendon/Development/vicmap-database/vicmap.toml:10`  
**Issue:** The trust chain accepts Graph's `from` address, an exact subject, an expected filename, and any path on `s3.ap-southeast-2.amazonaws.com`. The code never verifies authenticated sender results, a message signature, an expected S3 bucket/path prefix, an artifact signature, or a checksum obtained through an independent trusted channel. The configured regional S3 hostname is a shared authority: both `/trusted-bucket/.../Order_OK0VUZ.zip` and `/attacker-controlled-bucket/Order_OK0VUZ.zip` pass `validate_https_target`. Consequently, an email with a spoofed matching `from` value can point at an attacker-owned object on the allowed S3 authority and the pipeline will publish it as trusted.

**Fix:** Make at least one artifact-origin signal cryptographically authoritative and narrow the remaining policy. For example, validate a vendor signature or an expected digest delivered through a separate trusted channel before publication, validate sender authentication/signature results rather than `from` alone, and add an exact trusted bucket/path-prefix rule that is applied to the initial URL and every redirect. Add an end-to-end regression using a matching sender/subject and an attacker bucket on the allowed regional endpoint; it must fail before body transport or finalization.

### CR-02: Valid fingerprint settings fail only after the artifact is published

**Classification:** BLOCKER  
**Files:** `/home/brendon/Development/vicmap-database/read_mailbox.py:157-162`, `/home/brendon/Development/vicmap-database/read_mailbox.py:207-229`, `/home/brendon/Development/vicmap-database/vicmap_acquire/download.py:112-113`, `/home/brendon/Development/vicmap-database/vicmap_acquire/evidence.py:158-161`  
**Issue:** Configuration accepts `fingerprint_hex_chars` from 8 through 64 and the downloader returns exactly that many hexadecimal characters. The evidence boundary accepts exactly 16 characters. Any otherwise valid configuration using 8, 15, 17, 32, or 64 therefore completes the download and publishes the final path, then `SuccessEvent.download_target` raises `ValueError`. The controller reports `internal_failure` even though the artifact exists. A retry then encounters the existing final path and fails again. The test suite exercises only the default value 16, so it misses this post-commit inconsistency.

**Fix:** Use one shared fingerprint-length contract. If evidence fingerprints are intentionally fixed at 16, reject every other value during configuration validation before credentials or I/O and remove the misleading configurability. Otherwise, pass the configured length into evidence validation and accept exactly that length. Add tests for the minimum, default, and maximum accepted values that assert no network or filesystem operation occurs for incompatible policy.

### CR-03: Publication can succeed before cleanup converts the operation to failure

**Classification:** BLOCKER  
**File:** `/home/brendon/Development/vicmap-database/vicmap_acquire/download.py:442-466`  
**Issue:** `os.link(temp_path, final_path)` makes the complete artifact visible atomically, but the following `temp_path.unlink()` remains inside the transaction's failure path. If that unlink fails, the outer `except OSError` raises `ArtifactWriteFailed` even though `final_path` is already published. The `finally` block silently retries cleanup and can leave the private partial hard link behind. The caller therefore receives failure for committed state and cannot safely decide whether to retry. In addition, the parent directory is never fsynced, so a returned success does not establish directory-entry durability across a crash.

**Fix:** Define an explicit commit point. Prefer an atomic no-replace rename/link primitive with clear platform semantics, fsync the containing directory after publication, and treat post-commit temporary-name cleanup separately from publication success. If cleanup fails after commit, return the committed result and record a closed cleanup condition without claiming the artifact write failed. Add injected unlink-failure and crash-durability tests that assert the reported result agrees with final-path state.

## Warnings

### WR-01: The controller's configuration validator is not the configuration contract

**Classification:** WARNING  
**File:** `/home/brendon/Development/vicmap-database/read_mailbox.py:151-164`  
**Issue:** `_validate_config_object` checks that allowlists are non-empty but does not validate their element types or formats, does not require `folder == "Inbox"`, and does not constrain `output_dir`. `load_config` also accepts any nonblank folder at lines 265-266 even though `GraphMailbox` later rejects every value except `Inbox` as an authentication failure. Programmatic callers of the documented `run_acquisition` seam can therefore bypass the stronger TOML checks; malformed policy may trigger Graph/MIME access before eventually becoming `internal_failure`, and an alternate folder is misreported as an authentication problem rather than rejected as configuration before credentials are used.

**Fix:** Centralize all policy validation in one constructor or validator used by both `load_config` and `run_acquisition`. Validate exact Inbox selection, sender/order/host element syntax and uniqueness, the mismatch flag, fingerprint compatibility, and the resolved output-root constraint before credential validation or adapter construction. Add direct-`AcquisitionConfig` regressions, not only TOML-loader tests.

### WR-02: URLs inside non-rendered HTML elements are treated as visible links

**Classification:** WARNING  
**File:** `/home/brendon/Development/vicmap-database/vicmap_acquire/candidates.py:79-93`  
**Issue:** `_AnchorCollector.handle_data` extracts URLs from every HTML text node without tracking the surrounding element. URLs inside `<script>`, `<style>`, and other non-rendered content are therefore added to `visible_urls` and can become the sole accepted archive link. A synthetic `<script>const hidden="https://.../Order_OK0VUZ.zip"</script>` is accepted even when the message displays no direct download URL. This does not match the stated visible-direct-link policy and weakens candidate recognition.

**Fix:** Track element context and ignore non-rendered/raw-text elements, or use a parser/sanitizer that deliberately extracts rendered text. If the intended policy is specifically visible anchor text, collect data only while inside an `<a>` element. Add negative regressions for script, style, metadata, and malformed nested markup.

### WR-03: MIME-by-ID performs an undocumented full message fetch first

**Classification:** WARNING  
**Files:** `/home/brendon/Development/vicmap-database/vicmap_acquire/graph.py:207-219`, `/home/brendon/Development/vicmap-database/tests/test_graph.py:711-714`  
**Issue:** With the installed O365 2.1.0 SDK, `Folder.get_message(object_id=...)` issues a Graph GET for the ordinary message representation. Calling `message.get_mime_content()` then issues a second GET for the MIME `$value`. The adapter therefore does not perform a single selective MIME-by-ID read: it reads the selected message representation, including default body fields, before reading MIME. The fake folder in the test suite returns an in-memory object and hides this SDK behavior, so the asserted boundary is not production-shaped.

**Fix:** Construct an SDK `Message` wrapper locally with the confirmed folder/connection and the complete object ID, then invoke `get_mime_content`, or issue the MIME `$value` request directly through a narrow adapter method. Update the test double to count connection-level requests and assert exactly one request to the MIME endpoint.

### WR-04: A failing evidence sink can escape or replace the closed failure

**Classification:** WARNING  
**File:** `/home/brendon/Development/vicmap-database/read_mailbox.py:110-113`  
**Issue:** Every exception handler calls `_emit_failure`, which invokes the same unguarded `event_sink`. If the sink is the source of the original exception or remains unavailable, its second exception escapes from the `except` block instead of an `AcquisitionFailure`. This can mask the true reason, defeat the fixed failure vocabulary, and produce an ordinary traceback for the CLI rather than the promised closed outcome.

**Fix:** Isolate sink I/O from acquisition control flow. Emit at most once through a guarded helper, never retry a sink that just failed, and always raise a fixed `AcquisitionFailure` even when evidence delivery is unavailable. Add regressions for sinks that fail on candidate, progress, success, and failure events and assert no raw exception text escapes.

### WR-05: Final artifacts are ignored only at the default root location

**Classification:** WARNING  
**Files:** `/home/brendon/Development/vicmap-database/.gitignore:19-21`, `/home/brendon/Development/vicmap-database/read_mailbox.py:283-318`  
**Issue:** The loader permits any safe relative `output_dir` beside any selected config file, but `.gitignore` excludes only the repository-root `/artifacts/` directory. A policy under a subdirectory, or a changed output name, can place finalized private artifacts in a tracked location where `git add .` stages them. Partial files are ignored globally, but completed artifacts are not.

**Fix:** Constrain outputs to one repository-root directory that is always ignored, or generate/enforce ignore coverage for every permitted output root. At minimum, use an ignore pattern that covers nested `artifacts/` directories and add a test invoking `git check-ignore` for each supported config/output layout.

---

_Reviewed: 2026-09-09T02:00:55Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: standard_
