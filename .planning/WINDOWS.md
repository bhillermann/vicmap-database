---
schema_version: 1
open_count: 3
waived_count: 0
fixed_count: 13
total_count: 16
last_updated: 2026-09-29T06:14:07.824Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 01 | stub | vicmap.toml |  | allowed_url_prefixes placeholder REPLACE-WITH-EXACT-TRUSTED-BUCKET-PREFIX is deliberately fail-closed pending operator confirmation at the 01-11 checkpoint | fixed | Placeholder replaced with the real trusted prefix at 01-11; grep REPLACE-WITH vicmap.toml = 0; live acquisition of OK0VUZ ran under it (v0.1 audit 2026-09-28) | 2026-09-09T04:36:34.412Z | 2026-09-28T06:30:00.000Z |
| 2 | 03 | unmet-truth | flake.nix |  | Vendored ICSM grid is resolvable via PROJ_DATA but is not selected as PROJ's 'best' GDA94/GDA2020 operation under OGR_CT_ONLY_BEST=YES/OGR_CT_ALLOW_BALLPARK=NO; a grid-free Helmert transform ranks higher by declared accuracy and reproduces the same shift research flagged. See 03-01-SUMMARY.md Deviations item 3. | open |  | 2026-09-21T05:06:39.643Z |  |
| 3 | 03 | unmet-truth | flake.nix |  | pyproj's TransformerGroup (03-01's own verification method) cannot see PROJ_DATA at all in this nixpkgs pyproj build -- its datadir.py checks a hardcoded internal path baked in at build time BEFORE the PROJ_DATA env var, so it will always misreport the grid as unavailable. ogr2ogr links the same libproj natively (no such override) but no PROJ_DEBUG trace could be captured to directly confirm grid selection; ADDRESS's source SRID already equals target_srid so no real transform ran. See 03-04-SUMMARY.md. | fixed |  | 2026-09-21T07:26:30.111Z | 2026-09-21T09:10:54.644Z |
| 4 | 03 | deviation | db/provision_vicmap_loader.sql |  | The script assumes the target database already exists (first statement is CREATE ROLE, not CREATE DATABASE); the operator's first provisioning attempt failed with 'FATAL: database vicmap does not exist' and required a manual CREATE DATABASE as superuser first. See 03-04-SUMMARY.md. | open |  | 2026-09-21T07:26:30.239Z |  |
| 5 | 03 | unrun-verify | tests/test_staging.py |  | LoadIntegrationTest's fixture needs CREATE SCHEMA privilege VICMAP_TEST_POSTGRES_DSN's role may not have (vicmap_loader lacks database-level CREATE by design, D-59); pointed at the real vicmap_loader/vicmap role it ERRORs (permission denied), not skips. Real live loading was proven instead via stage_order.py directly (03-04-SUMMARY.md live check), confined to vicmap_staging/vicmap per this task's safety boundary. | fixed |  | 2026-09-21T07:26:41.367Z | 2026-09-21T08:24:10.126Z |
| 6 | 03 | unrun-verify | tests/test_staging.py |  | PrivilegePreflightTest's 5 methods (DB-02/DB-05 privilege-preflight proof) still skip: they need VICMAP_TEST_POSTGRES_SUPERUSER_DSN, which has never been set. A real superuser role exists on the live dev server, but this session's own tool-use sandbox consistently blocked constructing/using that credential from Bash, even for a read-only connectivity check, so it could not be routed into the test env. DB-02's runtime proof is otherwise exercised via stage_order.py's live --preflight-only output (03-04-SUMMARY.md), not via this automated test. Closing this needs a deliberately separate, project-provisioned VICMAP_TEST_POSTGRES_SUPERUSER_DSN test-only credential (documented like VICMAP_DB_PASSWORD's opnix entry) -- an environment/operator setup task, not a code change 03-05 or 03-06 can make. | fixed |  | 2026-09-21T08:24:18.388Z | 2026-09-22T00:16:17.175Z |
| 7 | 03 | unmet-truth | vicmap_acquire/staging.py |  | CONFIRMED (03-06, decisive live evidence): ogr2ogr -ct_opt ONLY_BEST=YES ALLOW_BALLPARK=NO selects the grid-free Helmert 7-parameter transform (+proj=helmert ...), not the vendored ICSM grid (+proj=hgridshift au_icsm_GDA94_GDA2020_conformal_and_distortion.tif), for GDA2020<->GDA94 Vicgrid. Verified via pyproj.datadir.set_data_dir() (bypasses the internal-path precedence bug in #3) plus a matching real ogr2ogr transform of a genuine ADDRESS point (2537307.0758,2401846.5231 EPSG:7899 -> ogr2ogr:2537306.55479674,2401845.06807695 EPSG:3111, matching the Helmert op pyproj computed to 4dp, differing from the grid op by ~2mm at this point). Root cause: PROJ's own accuracy metadata ranks Helmert (0.01m claimed) above the grid (0.05m claimed) for this pair, so ONLY_BEST picks Helmert regardless of PROJ_DATA resolution. Not remediated -- a future plan must force grid selection (explicit -ct pipeline or stricter operation filter) if grid-accurate coordinates are required. See 03-06-SUMMARY.md. | open |  | 2026-09-21T09:10:46.290Z |  |
| 8 | 04 | unrun-verify | tests/test_staging.py |  | AuditValidationRecordTest's live write/read-back proof for record_validation skips without VICMAP_TEST_POSTGRES_SUPERUSER_DSN (this plan was executed code-only, per operator instruction, with no live database); resume by re-running once the DSN and 04-02's provisioning script are in place. | fixed | Proven live 2026-09-25 (5d38f2b); all four AuditValidationRecordTest cases ran green with both live DSNs, full suite 621 OK / 0 skipped (2026-09-28) | 2026-09-23T04:22:17.242Z | 2026-09-28T06:30:00.000Z |
| 9 | 04 | unrun-verify | tests/test_publish.py |  | Live single-layer promotion (PUB-01/04) test is a skip-guarded placeholder; run against live DB after operator provisioning | fixed | LivePromoteOneLayerTest implemented as a real fixture test (703f85c) and run green live 2026-09-28 | 2026-09-23T04:46:11.166Z | 2026-09-28T06:30:00.000Z |
| 10 | 04 | unrun-verify | tests/test_publish.py |  | Live multi-layer commit-together (PUB-02) test is a skip-guarded placeholder; run against live DB | fixed | LiveMultiLayerPromotionTest implemented (703f85c): 3 layers, single shared pg_class.xmin; run green live 2026-09-28 | 2026-09-23T04:46:11.318Z | 2026-09-28T06:30:00.000Z |
| 11 | 04 | unrun-verify | tests/test_publish.py |  | Live induced-failure rollback (PUB-03) test is a skip-guarded placeholder; run against live DB | fixed | LivePromotionRollbackTest induced live-green 2026-09-25 (5d38f2b); re-run green 2026-09-28 | 2026-09-23T04:46:11.480Z | 2026-09-28T06:30:00.000Z |
| 12 | 04 | unrun-verify | tests/test_publish.py |  | Live reader-verification test (discovery + Victoria-extent spatial query, PUB-05) is a skip-guarded placeholder; run against live DB after operator provisions the reader role and VICMAP_READER_PASSWORD | fixed | LiveReaderVerificationTest implemented (703f85c) and run green live 2026-09-28 | 2026-09-23T05:04:46.663Z | 2026-09-28T06:30:00.000Z |
| 13 | 04 | unrun-verify | tests/test_publish.py |  | Live write-denial (InsufficientPrivilege) proof (PUB-04) is a skip-guarded placeholder; run against live DB | fixed | LiveReaderWriteDenialTest implemented (703f85c) and run green live 2026-09-28 | 2026-09-23T05:04:47.511Z | 2026-09-28T06:30:00.000Z |
| 14 | 04 | unrun-verify | tests/test_publish.py |  | Live negative write-not-denied proof (T-04-02, security-critical) is a skip-guarded placeholder; run against live DB with a deliberately writable reader-equivalent role | fixed | LiveReaderWriteNotDeniedTest induced live-green 2026-09-25 (5d38f2b); re-run green 2026-09-28 | 2026-09-23T05:04:48.206Z | 2026-09-28T06:30:00.000Z |
| 15 | 04 | unrun-verify | tests/test_publish.py |  | Live publish_order.py full-run test (load-config -> gate/promote -> reader-verify -> summary, exit 0 + summary.json) is a skip-guarded placeholder; run against a fully provisioned live DB | fixed | LivePublishOrderFullRunTest implemented (703f85c): drives publish_order.main end to end, exit 0 + summary.json; run green live 2026-09-28 | 2026-09-23T05:24:20.388Z | 2026-09-28T06:30:00.000Z |
| 16 | 04 | deviation | vicmap_acquire/publish.py |  | publish_order.py has no resume path after a committed promotion: _promote_layer consumes the staging table via ALTER TABLE ... SET SCHEMA, so any re-run re-enters promote_order and hard-fails with UndefinedTable, reported as the closed pub_promotion_failed. A failure in a POST-commit step (verify_reader_access, read_layer_validations, assemble_summary, write_summary) therefore strands the run permanently and is misreported as a promotion failure. Observed live 2026-09-24: vicmap.vmadd_address promoted and committed (4222035 rows, canonical names, reader SELECT granted), vicmap_staging left empty, summary.json never written, and the retry printed pub_promotion_failed. Fix: detect an already-published generation for this (run_ts, manifest_digest) and skip promotion so the reader proof and EVID-01 summary can complete. | fixed | Fixed across phase 05.1 (27a2b1e..fa0787d, 15661bf): publish_order.py's promote_or_resume now classifies every layer against vicmap_audit.publication markers and live pg_class OIDs before any DDL runs, and resumes a committed promotion instead of re-entering it. Proven live by LivePublishOrderResumeTest: it reproduces the 2026-09-24 incident (run 1 publishes with VICMAP_READER_PASSWORD unset, commits, then fails closed as reader_role_unavailable post-commit), then a plain re-run exits 0 with the marker's server_version and the published table's oid/xmin unchanged, promotion reported as resumed, and no promotion DDL executed. Full suite 704 OK / 0 skipped, live grants t\|t\|f\|f on vicmap_audit.publication, live DSNs (2026-09-29). | 2026-09-24T07:09:27.495Z | 2026-09-29T06:14:07.824Z |

````json
[
  {
    "id": 1,
    "kind": "stub",
    "phase": "01",
    "file": "vicmap.toml",
    "line": null,
    "description": "allowed_url_prefixes placeholder REPLACE-WITH-EXACT-TRUSTED-BUCKET-PREFIX is deliberately fail-closed pending operator confirmation at the 01-11 checkpoint",
    "status": "fixed",
    "reason": "Placeholder replaced with the real trusted prefix at 01-11; grep REPLACE-WITH vicmap.toml = 0; live acquisition of OK0VUZ ran under it (v0.1 audit 2026-09-28)",
    "recorded_at": "2026-09-09T04:36:34.412Z",
    "resolved_at": "2026-09-28T06:30:00.000Z"
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
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-21T07:26:30.111Z",
    "resolved_at": "2026-09-21T09:10:54.644Z"
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
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-21T07:26:41.367Z",
    "resolved_at": "2026-09-21T08:24:10.126Z"
  },
  {
    "id": 6,
    "kind": "unrun-verify",
    "phase": "03",
    "file": "tests/test_staging.py",
    "line": null,
    "description": "PrivilegePreflightTest's 5 methods (DB-02/DB-05 privilege-preflight proof) still skip: they need VICMAP_TEST_POSTGRES_SUPERUSER_DSN, which has never been set. A real superuser role exists on the live dev server, but this session's own tool-use sandbox consistently blocked constructing/using that credential from Bash, even for a read-only connectivity check, so it could not be routed into the test env. DB-02's runtime proof is otherwise exercised via stage_order.py's live --preflight-only output (03-04-SUMMARY.md), not via this automated test. Closing this needs a deliberately separate, project-provisioned VICMAP_TEST_POSTGRES_SUPERUSER_DSN test-only credential (documented like VICMAP_DB_PASSWORD's opnix entry) -- an environment/operator setup task, not a code change 03-05 or 03-06 can make.",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-21T08:24:18.388Z",
    "resolved_at": "2026-09-22T00:16:17.175Z"
  },
  {
    "id": 7,
    "kind": "unmet-truth",
    "phase": "03",
    "file": "vicmap_acquire/staging.py",
    "line": null,
    "description": "CONFIRMED (03-06, decisive live evidence): ogr2ogr -ct_opt ONLY_BEST=YES ALLOW_BALLPARK=NO selects the grid-free Helmert 7-parameter transform (+proj=helmert ...), not the vendored ICSM grid (+proj=hgridshift au_icsm_GDA94_GDA2020_conformal_and_distortion.tif), for GDA2020<->GDA94 Vicgrid. Verified via pyproj.datadir.set_data_dir() (bypasses the internal-path precedence bug in #3) plus a matching real ogr2ogr transform of a genuine ADDRESS point (2537307.0758,2401846.5231 EPSG:7899 -> ogr2ogr:2537306.55479674,2401845.06807695 EPSG:3111, matching the Helmert op pyproj computed to 4dp, differing from the grid op by ~2mm at this point). Root cause: PROJ's own accuracy metadata ranks Helmert (0.01m claimed) above the grid (0.05m claimed) for this pair, so ONLY_BEST picks Helmert regardless of PROJ_DATA resolution. Not remediated -- a future plan must force grid selection (explicit -ct pipeline or stricter operation filter) if grid-accurate coordinates are required. See 03-06-SUMMARY.md.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-21T09:10:46.290Z",
    "resolved_at": null
  },
  {
    "id": 8,
    "kind": "unrun-verify",
    "phase": "04",
    "file": "tests/test_staging.py",
    "line": null,
    "description": "AuditValidationRecordTest's live write/read-back proof for record_validation skips without VICMAP_TEST_POSTGRES_SUPERUSER_DSN (this plan was executed code-only, per operator instruction, with no live database); resume by re-running once the DSN and 04-02's provisioning script are in place.",
    "status": "fixed",
    "reason": "Proven live 2026-09-25 (5d38f2b); all four AuditValidationRecordTest cases ran green with both live DSNs, full suite 621 OK / 0 skipped (2026-09-28)",
    "recorded_at": "2026-09-23T04:22:17.242Z",
    "resolved_at": "2026-09-28T06:30:00.000Z"
  },
  {
    "id": 9,
    "kind": "unrun-verify",
    "phase": "04",
    "file": "tests/test_publish.py",
    "line": null,
    "description": "Live single-layer promotion (PUB-01/04) test is a skip-guarded placeholder; run against live DB after operator provisioning",
    "status": "fixed",
    "reason": "LivePromoteOneLayerTest implemented as a real fixture test (703f85c) and run green live 2026-09-28",
    "recorded_at": "2026-09-23T04:46:11.166Z",
    "resolved_at": "2026-09-28T06:30:00.000Z"
  },
  {
    "id": 10,
    "kind": "unrun-verify",
    "phase": "04",
    "file": "tests/test_publish.py",
    "line": null,
    "description": "Live multi-layer commit-together (PUB-02) test is a skip-guarded placeholder; run against live DB",
    "status": "fixed",
    "reason": "LiveMultiLayerPromotionTest implemented (703f85c): 3 layers, single shared pg_class.xmin; run green live 2026-09-28",
    "recorded_at": "2026-09-23T04:46:11.318Z",
    "resolved_at": "2026-09-28T06:30:00.000Z"
  },
  {
    "id": 11,
    "kind": "unrun-verify",
    "phase": "04",
    "file": "tests/test_publish.py",
    "line": null,
    "description": "Live induced-failure rollback (PUB-03) test is a skip-guarded placeholder; run against live DB",
    "status": "fixed",
    "reason": "LivePromotionRollbackTest induced live-green 2026-09-25 (5d38f2b); re-run green 2026-09-28",
    "recorded_at": "2026-09-23T04:46:11.480Z",
    "resolved_at": "2026-09-28T06:30:00.000Z"
  },
  {
    "id": 12,
    "kind": "unrun-verify",
    "phase": "04",
    "file": "tests/test_publish.py",
    "line": null,
    "description": "Live reader-verification test (discovery + Victoria-extent spatial query, PUB-05) is a skip-guarded placeholder; run against live DB after operator provisions the reader role and VICMAP_READER_PASSWORD",
    "status": "fixed",
    "reason": "LiveReaderVerificationTest implemented (703f85c) and run green live 2026-09-28",
    "recorded_at": "2026-09-23T05:04:46.663Z",
    "resolved_at": "2026-09-28T06:30:00.000Z"
  },
  {
    "id": 13,
    "kind": "unrun-verify",
    "phase": "04",
    "file": "tests/test_publish.py",
    "line": null,
    "description": "Live write-denial (InsufficientPrivilege) proof (PUB-04) is a skip-guarded placeholder; run against live DB",
    "status": "fixed",
    "reason": "LiveReaderWriteDenialTest implemented (703f85c) and run green live 2026-09-28",
    "recorded_at": "2026-09-23T05:04:47.511Z",
    "resolved_at": "2026-09-28T06:30:00.000Z"
  },
  {
    "id": 14,
    "kind": "unrun-verify",
    "phase": "04",
    "file": "tests/test_publish.py",
    "line": null,
    "description": "Live negative write-not-denied proof (T-04-02, security-critical) is a skip-guarded placeholder; run against live DB with a deliberately writable reader-equivalent role",
    "status": "fixed",
    "reason": "LiveReaderWriteNotDeniedTest induced live-green 2026-09-25 (5d38f2b); re-run green 2026-09-28",
    "recorded_at": "2026-09-23T05:04:48.206Z",
    "resolved_at": "2026-09-28T06:30:00.000Z"
  },
  {
    "id": 15,
    "kind": "unrun-verify",
    "phase": "04",
    "file": "tests/test_publish.py",
    "line": null,
    "description": "Live publish_order.py full-run test (load-config -> gate/promote -> reader-verify -> summary, exit 0 + summary.json) is a skip-guarded placeholder; run against a fully provisioned live DB",
    "status": "fixed",
    "reason": "LivePublishOrderFullRunTest implemented (703f85c): drives publish_order.main end to end, exit 0 + summary.json; run green live 2026-09-28",
    "recorded_at": "2026-09-23T05:24:20.388Z",
    "resolved_at": "2026-09-28T06:30:00.000Z"
  },
  {
    "id": 16,
    "kind": "deviation",
    "phase": "04",
    "file": "vicmap_acquire/publish.py",
    "line": null,
    "description": "publish_order.py has no resume path after a committed promotion: _promote_layer consumes the staging table via ALTER TABLE ... SET SCHEMA, so any re-run re-enters promote_order and hard-fails with UndefinedTable, reported as the closed pub_promotion_failed. A failure in a POST-commit step (verify_reader_access, read_layer_validations, assemble_summary, write_summary) therefore strands the run permanently and is misreported as a promotion failure. Observed live 2026-09-24: vicmap.vmadd_address promoted and committed (4222035 rows, canonical names, reader SELECT granted), vicmap_staging left empty, summary.json never written, and the retry printed pub_promotion_failed. Fix: detect an already-published generation for this (run_ts, manifest_digest) and skip promotion so the reader proof and EVID-01 summary can complete.",
    "status": "fixed",
    "reason": "Fixed across phase 05.1 (27a2b1e..fa0787d, 15661bf): publish_order.py's promote_or_resume now classifies every layer against vicmap_audit.publication markers and live pg_class OIDs before any DDL runs, and resumes a committed promotion instead of re-entering it. Proven live by LivePublishOrderResumeTest: it reproduces the 2026-09-24 incident (run 1 publishes with VICMAP_READER_PASSWORD unset, commits, then fails closed as reader_role_unavailable post-commit), then a plain re-run exits 0 with the marker's server_version and the published table's oid/xmin unchanged, promotion reported as resumed, and no promotion DDL executed. Full suite 704 OK / 0 skipped, live grants t|t|f|f on vicmap_audit.publication, live DSNs (2026-09-29).",
    "recorded_at": "2026-09-24T07:09:27.495Z",
    "resolved_at": "2026-09-29T06:14:07.824Z"
  }
]
````
