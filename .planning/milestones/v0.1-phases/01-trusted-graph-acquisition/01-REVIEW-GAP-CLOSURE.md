---
phase: 01-trusted-graph-acquisition
reviewed: 2026-09-14T00:28:00Z
depth: deep
files_reviewed: 12
files_reviewed_list:
  - vicmap_acquire/origin.py
  - vicmap_acquire/candidates.py
  - vicmap_acquire/download.py
  - vicmap_acquire/evidence.py
  - vicmap_acquire/graph.py
  - read_mailbox.py
  - tests/test_candidates.py
  - tests/test_download.py
  - tests/test_evidence.py
  - tests/test_graph.py
  - tests/test_origin.py
  - tests/test_repository_policy.py
findings:
  critical: 2
  warning: 3
  info: 2
  total: 7
status: issues_found
---

# Phase 01: Code Review Report (Gap Closure: 01-06 .. 01-12)

**Reviewed:** 2026-09-14T00:28:00Z
**Depth:** deep
**Files Reviewed:** 12
**Status:** issues_found

## Summary

This reviewed the diff from `5573dd9` to `HEAD`, covering gap-closure plans 01-06 through 01-12 (authenticated origin binding, rendered-context HTML extraction, the publication commit point, the shared policy validator/fingerprint threading/emit-at-most-once evidence sink, the connection-level MIME GET, and the 01-12 void-element suppression fix). Most of the individually-targeted gaps (G-01..G-06, WR-03) are closed correctly and are backed by real regressions: `origin.py`'s exception handling is genuinely total, `download.py`'s commit point (`_publish_artifact`) is a single atomic `os.link` with no double-reporting window, the redirect-hop loop is authorization-checked on every hop with loop detection, the `_EmitOnce` evidence guard correctly converts a broken sink into `INTERNAL_FAILURE` without leaking exception text, and no reviewed error path serializes a credential, token, subject, body, complete Graph message ID, or complete URL/query.

The two Critical findings below are exactly the class of defect the review priorities asked to hunt for: the 01-12 fix closed the *specific* void-element shape that failed against one live message, but the underlying `_AnchorCollector` suppression model is a flat depth counter with no awareness of how a real HTML parser tokenizes self-closing tags or recovers from unclosed containers. Two other realistic (not adversarially exotic) markup shapes reopen the exact guarantee 01-07/01-12 exist to provide, and neither is covered by the current 171-test suite. Both were verified against Python's actual `html.parser` tokenizer source, not assumed.

## Critical Issues

### CR-01: Self-closing non-void, non-rendered tags leak suppressed content back into "visible" extraction

**File:** `vicmap_acquire/candidates.py:147-158` (interacting with `handle_starttag` at 129-145 and `handle_data` at 169-172)

**Issue:** `_AnchorCollector.handle_startendtag` treats a self-closed non-void, non-rendered element (`<script .../>`, `<style/>`, `<head/>`, `<template/>`, `<object/>`, `<applet/>`, `<iframe/>`, `<title/>`, `<noscript/>`) as opening and immediately closing the suppression scope (`+1` then `max(0, -1)`, net zero). This mirrors what Python's `html.parser` tokenizer itself does at the token level — but the token level is not what matters here. Per the HTML5 tokenizer spec (and every real rendering engine, including the mail clients this pipeline exists to match), the self-closing slash is **ignored** on any element that is not a void element or a foreign (SVG/MathML) element. A browser rendering `<script src="a.js"/>PAYLOAD</script>` treats the whole thing as one open `script` element with `PAYLOAD` as literal, non-rendered script text, right up to the real `</script>`. This code instead treats the tag as fully closed, so `PAYLOAD` is parsed as ordinary markup/text and any URL inside it — including inside an `<a href>` nested "inside" the nominally-non-rendered element — is collected as a visible/href URL and can become the recognized archive link.

Verified directly against the installed CPython 3.14 `html/parser.py`: `set_cdata_mode` (which is what makes `script`/`style` raw-text) is only invoked in the `parse_starttag` branch taken for an *ordinary* start tag; the `/>`-terminated branch calls `handle_startendtag` and never enters CDATA mode. Reproduced against the actual pipeline entry point (`recognize_candidate` → `_mime_archive_links` → `_extract_html_urls`, the private function the real code path uses):

```python
>>> from vicmap_acquire.candidates import extract_html_hrefs, _extract_html_urls
>>> html = ('<html><body><script src="a.js"/>'
...         'http://evil.example.com/Order_X.zip more text</script>'
...         '<p>hello</p></body></html>')
>>> _extract_html_urls(html)
['http://evil.example.com/Order_X.zip']
```

and with an anchor instead of bare text, self-closing `<style/>`:

```python
>>> html = ('<html><body><style/>'
...         '<a href="http://evil.example.com/Order_X.zip">click</a>'
...         '</style><p>hello</p></body></html>')
>>> extract_html_hrefs(html)
['http://evil.example.com/Order_X.zip']
```

Both reopen the exact security property 01-07 was written to establish ("Hrefs on anchors nested inside non-rendered elements ... are excluded"). This is directly reachable through `recognize_candidate` whenever the message's `text/plain` alternative is absent or lacks a matching `Order_<id>.zip` URL, which `_mime_archive_links` (candidates.py:242-257) falls back to HTML for. No test in `tests/test_candidates.py` exercises a self-closing spelling of any *non-void* non-rendered element — the only self-closing regression added by 01-12 (`test_bare_and_self_closing_void_spellings_are_equivalent`) exercises `meta`/`link`, which are void and therefore not affected by this bug.

**Fix:** Stop modeling self-closing non-void tags as "open then immediately close." A self-closed non-void, non-rendered element must raise the suppression depth and leave it raised, exactly like an ordinary (unclosed) start tag, because that is what every consuming renderer does:

```python
def handle_startendtag(self, tag, attrs):
    casefolded = tag.casefold()
    if casefolded in _NON_RENDERED:
        if casefolded not in _VOID_ELEMENTS:
            # HTML5 tokenization ignores the trailing "/" on non-void,
            # non-foreign elements; the element is NOT closed by it.
            self.non_rendered_depth += 1
        return
    self.handle_starttag(tag, attrs)
    self.handle_endtag(tag)
```

Add regressions for self-closed `script`/`style`/`head`/`template`/`noscript` each followed by a payload URL, asserting zero archive links (mirroring the 01-07/01-12 negative suite but with the self-closing spelling).

---

### CR-02: Any omitted closing tag for a non-void non-rendered container (e.g. `<head>` without `</head>`) permanently suppresses the rest of the message — the same defect class 01-12 was meant to close, via a different trigger

**File:** `vicmap_acquire/candidates.py:122-185` (the flat `non_rendered_depth` counter model as a whole)

**Issue:** 01-12's own plan text names the root cause precisely: "`_NON_RENDERED` contains ... elements[] which emit no end tag, so ... the counter stays permanently raised and the entire body is suppressed." The fix correctly special-cased *void* elements. But the counter model has a broader defect of the same shape: `handle_starttag`/`handle_endtag` do plain token counting with no tree-construction awareness at all, so **any** non-rendered, non-void container whose closing tag is missing or malformed for any reason — not just "this element type is structurally void" — leaves `non_rendered_depth` permanently above zero for the remainder of the feed. The most realistic trigger is a `<head>` section with no explicit `</head>` at all, which is common, valid-enough-for-browsers HTML: every real HTML5 parser implicitly closes `head` on encountering `<body>` (or any content not valid inside head) via the "in head" insertion mode's "anything else" clause. Python's `html.parser` is a pure tokenizer with no insertion-mode/tree-construction logic, so it never performs this implicit close, and neither does `_AnchorCollector`.

Reproduced through the real entry point used by 01-12's own regressions (`extract_html_hrefs`, and by extension `recognize_candidate`):

```python
>>> from vicmap_acquire.candidates import extract_html_hrefs
>>> html = ('<html><head><title>Hi</title><meta charset="utf-8">'
...         '<body><p>Download your data:</p>'
...         '<a href="https://s3.example.com/Order_ABC123.zip">Download</a>'
...         '</body></html>')
>>> extract_html_hrefs(html)
[]
```

Every existing head-shape regression in `tests/test_candidates.py` (`_bare_email_head`, `test_bare_void_elements_in_realistic_head_do_not_suppress_the_body`, `test_bare_and_self_closing_void_spellings_are_equivalent`) always closes `<head>` explicitly with a literal `</head>`. None omits it. This means the exact operational failure that motivated 01-12 — a genuine DataShare "ready" message being rejected with `candidate_none`/`candidate_ambiguous` because the whole body was suppressed — can recur from a template variant that simply doesn't emit `</head>`, and the newly-expanded 01-12 test suite would not catch it.

This is a fail-closed failure mode (it denies a legitimate acquisition rather than accepting a forged one), so it is not a trust bypass, but it is a Critical/blocking finding because it directly reproduces, in a still-untested and still-realistic shape, the production outage 01-12 exists to have closed, and 01-12's plan explicitly frames "the head silences the body" as the defect class this run had to eliminate.

**Fix:** This needs more than another special case; the `non_rendered_depth` scalar cannot express "which container is actually still open." At minimum:
- Track a stack of currently-open non-rendered container tag names instead of an integer, so an end tag only closes the container it actually names (this also fixes cases where a stray same-category end tag, e.g. `</style>` while `<script>` is open, currently closes the wrong scope).
- Special-case `head`: force-close it (pop it off the stack) the moment a `<body>` start tag — or, conservatively, any start tag not itself a legal head-only child (`title`, `meta`, `link`, `style`, `script`, `base`, `noscript`, `template`) — is seen while `head` is the open container, mirroring the HTML5 "in head" insertion mode's implicit close.
- Add a regression with a `<head>...` that is never explicitly closed (no `</head>` token at all) followed by a body anchor/text URL, asserting the archive link is still recognized.

## Warnings

### WR-01: DMARC domain-alignment check silently no-ops when `header.from` is absent, unlike the DKIM check

**File:** `vicmap_acquire/origin.py:174-186`

**Issue:** The DKIM branch fails closed if the expected property is missing:
```python
if "dkim" in required_cf:
    header_d = properties.get("header.d")
    if not header_d or not _domain_aligned(from_domain, header_d):
        raise ValueError(...)
```
but the DMARC branch only checks alignment *if the property happens to be present*:
```python
if "dmarc" in required_cf:
    header_from = properties.get("header.from")
    if header_from is not None and header_from != from_domain:
        raise ValueError(...)
```
A message whose `Authentication-Results` header carries `dmarc=pass` but omits `header.from` (malformed, truncated, or a variant format) sails through with no alignment check at all, relying entirely on M365 having internally verified alignment before writing `dmarc=pass` — i.e. this defense-in-depth check can be silently skipped by a header shape nobody validates the opposite of. Verified:

```python
>>> from vicmap_acquire.origin import verify_authenticated_origin, OriginPolicy
>>> mime = (b'From: x <noreply@datashare.maps.vic.gov.au>\r\n'
...         b'Authentication-Results: spf=pass smtp.mailfrom=maps.vic.gov.au;'
...         b'dkim=pass header.d=maps.vic.gov.au;dmarc=pass action=none;'
...         b'compauth=pass reason=100\r\n\r\nbody\r\n')
>>> policy = OriginPolicy(allowed_senders=('noreply@datashare.maps.vic.gov.au',),
...                        required_authentication_results=('dkim','dmarc','compauth'))
>>> verify_authenticated_origin(mime, 'noreply@datashare.maps.vic.gov.au', policy)
'noreply@datashare.maps.vic.gov.au'   # accepted despite missing header.from
```

**Fix:** Make the DMARC branch fail closed the same way DKIM does when `required_authentication_results` includes `dmarc`:
```python
if "dmarc" in required_cf:
    header_from = properties.get("header.from")
    if not header_from or header_from != from_domain:
        raise ValueError("dmarc header.from is missing or disagrees with the From domain")
```

### WR-02: MSO conditional comments are unconditionally treated as non-rendered, which can cause false-negative candidate recognition

**File:** `vicmap_acquire/candidates.py:174-175`

**Issue:** `handle_comment` always returns without inspecting the comment body. Ordinary HTML comments are correctly never rendered by any client, but Outlook desktop (a common consumer of transactional HTML email) specifically renders content wrapped in `<!--[if mso]>...<![endif]-->` / `<!--[if !mso]><!-->...<!--<![endif]-->` conditional-comment blocks — a widely used technique for Outlook-specific layout in HTML email templates. If a template ever places the archive link (or its only anchor) inside such a block for Outlook-specific rendering, this parser will never see it, and `recognize_candidate` will raise `CandidateAmbiguous`/return `None` for a message a real Outlook user would see the link in. This is fail-closed (no security exposure) but is an availability risk of the same "convenient fixture, unrealistic markup" character flagged in the review priorities, and 01-11's live re-proof exercise shows this template does get rewritten by DataShare in ways not previously anticipated.

**Fix:** No change required for correctness of the current sender's template, but worth an explicit regression documenting the decision (comment-wrapped content is always suppressed, by design) so a future change to the DataShare template that relies on MSO conditional comments fails loudly (`candidate_ambiguous`) rather than being mistaken for a new bug.

### WR-03: Emitted `SafeFailure` events never carry `order_id` / `message_fingerprint` / `path_fingerprint`, even when known

**File:** `read_mailbox.py:150-160` (`_emit_failure`), compare `vicmap_acquire/evidence.py:324-353` (`SafeFailure.__init__`)

**Issue:** `evidence.SafeFailure` supports optional `order_id`, `message_fingerprint`, and `path_fingerprint` fields specifically so a failure can be correlated to the message/order/target that produced it. `read_mailbox._emit_failure` (the only call site that constructs a `SafeFailure` in the production path) never passes any of them:
```python
def _emit_failure(guard, reason, *, fingerprint_hex_chars=16):
    failure = SafeFailure(_reason_code(reason), fingerprint_hex_chars=fingerprint_hex_chars)
    guard.emit_failure(failure)
    return failure
```
Even a download failure that happens *after* `selected` (the recognized `Candidate`) is known carries no correlating detail. This is not a disclosure risk (it errs toward under-sharing), but it undercuts the audit/operability value the fingerprinting machinery in evidence.py was built for — an operator cannot tell, from evidence alone, which of several candidate messages a download failure belongs to.

**Fix:** Thread `order_id=selected.order_id` / `message_fingerprint=fingerprint(selected.graph_message_id, ...)` into `_emit_failure` calls made after `selected` is known (the `DownloadError` branch in `run_acquisition`), and `path_fingerprint` when a `DownloadResult`-adjacent target is known before the failure.

## Info

### IN-01: Duplicated, inconsistent provider-logger suppression lists

**File:** `vicmap_acquire/graph.py:68-74` (`_suppress_provider_logging`, list includes lowercase `"o365"`) vs. `read_mailbox.py:170-172` (`_suppress_dependency_logs`, omits it)

**Issue:** Both modules independently silence the same dependency loggers before any network call, with slightly different logger-name lists (harmless today since the O365 SDK only ever logs under `O365.<module>`, never lowercase `o365`, but the duplication and drift is a maintenance hazard for a control this codebase clearly treats as security-relevant — one list changing without the other is easy to miss).

**Fix:** Extract one shared `_suppress_dependency_logs(names)` helper (e.g. in a small shared module) and call it from both `GraphMailbox.__init__` and `run_acquisition`.

### IN-02: `_publish_artifact`'s "no exception may leave post-commit" claim depends on `_fsync_directory`'s argument always being a `Path`

**File:** `vicmap_acquire/download.py:261-283, 285-306`

**Issue:** The docstring for `_publish_artifact` states "No exception raised by post-commit cleanup may leave this function," but `_fsync_directory` only guards `OSError` around `os.open`/`os.fsync`/`os.close`; a non-`OSError` exception thrown before entering that guard (e.g. a `TypeError` from a malformed `directory` argument) would propagate past the "commit" point undocumented as a possibility. Not reachable today (`final_path.parent` is always a `Path`), so this is informational rather than a real defect.

**Fix:** No action required unless `_publish_artifact`'s signature is ever loosened to accept caller-supplied paths from a less-trusted source.

---

_Reviewed: 2026-09-14T00:28:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
