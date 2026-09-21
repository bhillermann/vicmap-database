---
schema_version: 1
open_count: 2
waived_count: 0
fixed_count: 0
total_count: 2
last_updated: 2026-09-21T05:06:39.643Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 01 | stub | vicmap.toml |  | allowed_url_prefixes placeholder REPLACE-WITH-EXACT-TRUSTED-BUCKET-PREFIX is deliberately fail-closed pending operator confirmation at the 01-11 checkpoint | open |  | 2026-09-09T04:36:34.412Z |  |
| 2 | 03 | unmet-truth | flake.nix |  | Vendored ICSM grid is resolvable via PROJ_DATA but is not selected as PROJ's 'best' GDA94/GDA2020 operation under OGR_CT_ONLY_BEST=YES/OGR_CT_ALLOW_BALLPARK=NO; a grid-free Helmert transform ranks higher by declared accuracy and reproduces the same shift research flagged. See 03-01-SUMMARY.md Deviations item 3. | open |  | 2026-09-21T05:06:39.643Z |  |

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
  },
  {
    "id": 2,
    "kind": "unmet-truth",
    "phase": "03",
    "file": "flake.nix",
    "line": null,
    "description": "Vendored ICSM grid is resolvable via PROJ_DATA but is not selected as PROJ's 'best' GDA94/GDA2020 operation under OGR_CT_ONLY_BEST=YES/OGR_CT_ALLOW_BALLPARK=NO; a grid-free Helmert transform ranks higher by declared accuracy and reproduces the same shift research flagged. See 03-01-SUMMARY.md Deviations item 3.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-21T05:06:39.643Z",
    "resolved_at": null
  }
]
````
