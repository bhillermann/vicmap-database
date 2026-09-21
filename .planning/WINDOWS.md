---
schema_version: 1
open_count: 5
waived_count: 0
fixed_count: 0
total_count: 5
last_updated: 2026-09-21T07:26:41.367Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 01 | stub | vicmap.toml |  | allowed_url_prefixes placeholder REPLACE-WITH-EXACT-TRUSTED-BUCKET-PREFIX is deliberately fail-closed pending operator confirmation at the 01-11 checkpoint | open |  | 2026-09-09T04:36:34.412Z |  |
| 2 | 03 | unmet-truth | flake.nix |  | Vendored ICSM grid is resolvable via PROJ_DATA but is not selected as PROJ's 'best' GDA94/GDA2020 operation under OGR_CT_ONLY_BEST=YES/OGR_CT_ALLOW_BALLPARK=NO; a grid-free Helmert transform ranks higher by declared accuracy and reproduces the same shift research flagged. See 03-01-SUMMARY.md Deviations item 3. | open |  | 2026-09-21T05:06:39.643Z |  |
| 3 | 03 | unmet-truth | flake.nix |  | pyproj's TransformerGroup (03-01's own verification method) cannot see PROJ_DATA at all in this nixpkgs pyproj build -- its datadir.py checks a hardcoded internal path baked in at build time BEFORE the PROJ_DATA env var, so it will always misreport the grid as unavailable. ogr2ogr links the same libproj natively (no such override) but no PROJ_DEBUG trace could be captured to directly confirm grid selection; ADDRESS's source SRID already equals target_srid so no real transform ran. See 03-04-SUMMARY.md. | open |  | 2026-09-21T07:26:30.111Z |  |
| 4 | 03 | deviation | db/provision_vicmap_loader.sql |  | The script assumes the target database already exists (first statement is CREATE ROLE, not CREATE DATABASE); the operator's first provisioning attempt failed with 'FATAL: database vicmap does not exist' and required a manual CREATE DATABASE as superuser first. See 03-04-SUMMARY.md. | open |  | 2026-09-21T07:26:30.239Z |  |
| 5 | 03 | unrun-verify | tests/test_staging.py |  | LoadIntegrationTest's fixture needs CREATE SCHEMA privilege VICMAP_TEST_POSTGRES_DSN's role may not have (vicmap_loader lacks database-level CREATE by design, D-59); pointed at the real vicmap_loader/vicmap role it ERRORs (permission denied), not skips. Real live loading was proven instead via stage_order.py directly (03-04-SUMMARY.md live check), confined to vicmap_staging/vicmap per this task's safety boundary. | open |  | 2026-09-21T07:26:41.367Z |  |

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
  },
  {
    "id": 3,
    "kind": "unmet-truth",
    "phase": "03",
    "file": "flake.nix",
    "line": null,
    "description": "pyproj's TransformerGroup (03-01's own verification method) cannot see PROJ_DATA at all in this nixpkgs pyproj build -- its datadir.py checks a hardcoded internal path baked in at build time BEFORE the PROJ_DATA env var, so it will always misreport the grid as unavailable. ogr2ogr links the same libproj natively (no such override) but no PROJ_DEBUG trace could be captured to directly confirm grid selection; ADDRESS's source SRID already equals target_srid so no real transform ran. See 03-04-SUMMARY.md.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-21T07:26:30.111Z",
    "resolved_at": null
  },
  {
    "id": 4,
    "kind": "deviation",
    "phase": "03",
    "file": "db/provision_vicmap_loader.sql",
    "line": null,
    "description": "The script assumes the target database already exists (first statement is CREATE ROLE, not CREATE DATABASE); the operator's first provisioning attempt failed with 'FATAL: database vicmap does not exist' and required a manual CREATE DATABASE as superuser first. See 03-04-SUMMARY.md.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-21T07:26:30.239Z",
    "resolved_at": null
  },
  {
    "id": 5,
    "kind": "unrun-verify",
    "phase": "03",
    "file": "tests/test_staging.py",
    "line": null,
    "description": "LoadIntegrationTest's fixture needs CREATE SCHEMA privilege VICMAP_TEST_POSTGRES_DSN's role may not have (vicmap_loader lacks database-level CREATE by design, D-59); pointed at the real vicmap_loader/vicmap role it ERRORs (permission denied), not skips. Real live loading was proven instead via stage_order.py directly (03-04-SUMMARY.md live check), confined to vicmap_staging/vicmap per this task's safety boundary.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-21T07:26:41.367Z",
    "resolved_at": null
  }
]
````
