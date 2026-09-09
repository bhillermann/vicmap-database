---
schema_version: 1
open_count: 1
waived_count: 0
fixed_count: 0
total_count: 1
last_updated: 2026-09-09T04:36:34.412Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 01 | stub | vicmap.toml |  | allowed_url_prefixes placeholder REPLACE-WITH-EXACT-TRUSTED-BUCKET-PREFIX is deliberately fail-closed pending operator confirmation at the 01-11 checkpoint | open |  | 2026-09-09T04:36:34.412Z |  |

````json
[
  {
    "id": 1,
    "kind": "stub",
    "phase": "01",
    "file": "vicmap.toml",
    "line": null,
    "description": "allowed_url_prefixes placeholder REPLACE-WITH-EXACT-TRUSTED-BUCKET-PREFIX is deliberately fail-closed pending operator confirmation at the 01-11 checkpoint",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-09T04:36:34.412Z",
    "resolved_at": null
  }
]
````
