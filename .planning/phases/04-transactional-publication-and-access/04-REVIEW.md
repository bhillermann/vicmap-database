---
phase: 04-transactional-publication-and-access
reviewed: 2026-09-25T00:00:00Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - db/provision_vicmap_loader.sql
  - flake.nix
  - publish_order.py
  - read_mailbox.py
  - stage_order.py
  - tests/test_evidence.py
  - tests/test_manifest.py
  - tests/test_publish_order.py
  - tests/test_publish.py
  - tests/test_staging.py
  - vicmap_acquire/evidence.py
  - vicmap_acquire/manifest.py
  - vicmap_acquire/publish.py
  - vicmap_acquire/staging.py
  - vicmap.toml
findings:
  critical: 1
  warning: 3
  info: 1
  total: 5
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-09-25T00:00:00Z
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

Reviewed the transactional-publication boundary (`vicmap_acquire/publish.py`), its
staging-side dependencies (`vicmap_acquire/staging.py`), the disclosure-safe
evidence vocabulary (`vicmap_acquire/evidence.py`), the by-hand provisioning
script, and the CLI/test surface around them. The SQL-injection posture is
solid throughout: every identifier reaching a query is composed via
`psycopg.sql.Identifier`/`sql.Literal`, never string-formatted into raw SQL
text, and the one place a value is composed as raw SQL text
(`apply_post_validation_ddl`'s typed-geometry `ALTER COLUMN ... TYPE`) is
first checked against a small closed enumeration before that composition
happens. The promotion transaction's atomicity (`DROP` → `SET SCHEMA` →
`RENAME` → constraint/index renames → `GRANT`, one connection, one
commit-or-rollback) is correctly built and is exercised by a genuine
rollback-composition test. Secrets are consistently kept out of exception
text, SQL text, and argv (`PGPASSWORD` via subprocess env, `VICMAP_DB_PASSWORD`
/ `VICMAP_READER_PASSWORD` via `os.environ.get` only).

However, the phase's single most security-critical check — the reader
write-denial proof that is supposed to catch a broken read-only grant model
(T-04-02, documented as "must never be downgraded to a warning or a pass") —
has a real blind spot against the exact schema this pipeline publishes: a
`gid` primary key with no default. That is CR-01 below. Three further
findings (two warnings, one info) round out the review.

## Critical Issues

### CR-01: Reader write-denial proof mis-detects a broken grant on the real published schema (NOT NULL blind spot)

**File:** `vicmap_acquire/publish.py:611-623`

**Issue:** `verify_reader_access`'s write-denial proof relies on exactly one
exception type to conclude "the reader's write was denied":

```python
try:
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("INSERT INTO {table} DEFAULT VALUES").format(
                table=sql.Identifier(policy.publish_schema, target)
            )
        )
except pg_errors.InsufficientPrivilege:
    connection.rollback()
    write_denied = True
else:
    connection.rollback()
    raise ReaderWriteNotDenied()
```

The docstring justifies `INSERT ... DEFAULT VALUES` by claiming "PostgreSQL's
ACL check runs at executor startup, before any NOT NULL constraint is ever
evaluated." That claim is only half true: it correctly describes what
happens when the role *lacks* `INSERT` (the ACL check fails first, so
`InsufficientPrivilege` is raised and no constraint is ever evaluated — the
happy/deny path). It does **not** describe what happens in the failure mode
this check exists to catch: a role that has been mistakenly granted
`INSERT` (the broken-grant scenario). In that case the ACL check *passes*,
and PostgreSQL proceeds to evaluate the row — including the `NOT NULL`
constraint implied by `gid integer PRIMARY KEY` (created either by GDAL's
`FID=gid` load option or by `apply_post_validation_ddl`'s own
`ALTER TABLE ... ADD PRIMARY KEY (gid)`, `vicmap_acquire/staging.py:1014-1029`).
`gid` has no `DEFAULT`/sequence anywhere in this codebase, so
`INSERT ... DEFAULT VALUES` against a table where the reader *does* hold
`INSERT` raises `psycopg.errors.NotNullViolation` — a completely different,
unrelated exception class from `InsufficientPrivilege` (different SQLSTATE
class: `23` integrity-constraint-violation vs `42`
syntax-or-access-rule-violation; neither is a subclass of the other).

`NotNullViolation` is not caught by the `except pg_errors.InsufficientPrivilege:`
clause, so it propagates out of `verify_reader_access` entirely uncaught
(the enclosing block only has a `finally`, no matching `except`). It is not
a `PublishFailure`/`StagingFailure`/`ManifestFailure`/`AcquisitionFailure`
either, so `publish_order.py`'s exception ladder does not recognize it and
it falls through to the CLI's generic catch-all, reporting
`internal_failure` (hint: `review_safe_diagnostics_and_retry`) instead of
the intended `reader_write_not_denied` (hint:
`revoke_reader_write_immediately_grant_model_is_broken`). The exact failure
this check exists to name loudly and urgently — a broken read-only grant on
production Vicmap data — is silently downgraded to a generic internal error
with no actionable "revoke immediately" signal, on precisely the schema
this pipeline actually publishes.

This is also a textbook case of hand-written tests sharing the
implementation's own blind spot: `tests/test_publish.py`'s
`_FakeReaderCursor` (`deny_write=False` branch, around line 481-485) simply
`return`s on `INSERT INTO` to simulate "not denied" — it never models the
real server's NOT NULL evaluation, so `test_writable_reader_raises_reader_write_not_denied`
passes even though the real database would not follow the code path the
test exercises.

**Fix:** Use a write-denial probe whose failure mode is *only* ever the ACL
check, never a downstream row constraint — e.g. a zero-row `INSERT ... SELECT`
that the executor still permission-checks even though it inserts no rows,
so a NOT NULL/PK constraint on `gid` can never fire regardless of whether
the grant is broken:

```python
cursor.execute(
    sql.SQL("INSERT INTO {table} SELECT * FROM {table} WHERE FALSE").format(
        table=sql.Identifier(policy.publish_schema, target)
    )
)
```

This still exercises a real, executed INSERT statement against the real
table (preserving the "never a grant-metadata-only shortcut" property the
docstring calls out) while making the *only* possible failure the ACL
check itself. Alternatively, keep `DEFAULT VALUES` but widen the except
clause to also treat `pg_errors.NotNullViolation` (and ideally any
non-privilege integrity error) as proof that the ACL check already passed
— i.e. still raise `ReaderWriteNotDenied()` in that branch, not just on
clean success — so the constraint failure that follows a passed ACL check
is correctly attributed to a broken grant rather than swallowed as
`internal_failure`.

## Warnings

### WR-01: Reader-verification's representative table is assumed spatial without checking

**File:** `vicmap_acquire/publish.py:579,596-602`

**Issue:** `verify_reader_access` always runs its GiST-exercising spatial
query (`SELECT gid FROM {table} WHERE geom && ...`) against
`published_tables[0]` — the manifest's first layer, in manifest order —
without checking whether that layer is spatial. `manifest.py`/`staging.py`
support non-spatial layers throughout (D-57's `NOT_APPLICABLE` vocabulary
exists precisely for this case), and nothing in `promote_order` or
`publish_order.py` guarantees the first manifest layer is spatial for a
multi-layer order. If a future order's manifest lists a non-spatial lookup
table before its spatial layer(s), the representative table chosen here has
no `geom`/`gid` columns matching this query's assumptions, and the query
raises inside the `except Exception: raise ReaderVerificationFailed()`
block — failing the entire publish's reader-verification stage even though
the reader's actual grants may be perfectly correct. (Today's single-layer
`vmadd_address` order does not trigger this, but the function is written as
general-purpose multi-layer logic and the bug is latent for any order whose
layer ordering differs.)

**Fix:** Select the representative table from the manifest's own spatial
flag (e.g. thread `manifest.layers` spatiality through to
`verify_reader_access`, or pick the first *spatial* published table and
skip the spatial-query portion — but not the discovery/write-denial
portions — when no published table is spatial).

### WR-02: No runtime proof that `vicmap_reader` lacks `CREATE` on schema `public`

**File:** `vicmap_acquire/publish.py:540-635`, `db/provision_vicmap_loader.sql:33-40`

**Issue:** `staging.preflight_staging_privileges` runtime-proves (not just
documents) that `vicmap_loader` cannot `CREATE` in schema `public`
(`has_schema_privilege(current_user, 'public', 'CREATE')`,
`vicmap_acquire/staging.py:451-459`) — explicitly because the provisioning
script's own comment admits that on a pre-15 PostgreSQL server, `PUBLIC`
retains `CREATE` on `public` by default unless an operator explicitly
revokes it, and the script deliberately does not do that revocation itself.
The equivalent runtime proof does not exist for `vicmap_reader`:
`verify_reader_access` proves SELECT discoverability, a representative
spatial read, and write-denial on the *published* table, but never checks
whether the reader role can still write somewhere else (schema `public`,
most obviously) via the same PUBLIC-role default. On a pre-15 server this
is a real least-privilege gap that nothing in this phase's evidence would
ever surface.

**Fix:** Add a `has_schema_privilege(vicmap_reader, 'public', 'CREATE')`
check (mirroring the loader's own check) to `verify_reader_access` or a
sibling verification step, so PUB-04/PUB-05's "reader has SELECT only"
claim is proven the same way the loader's "no CREATE on public" claim
already is.

### WR-03: `record_validation`'s `ON CONFLICT DO NOTHING` silently discards a corrected re-validation

**File:** `vicmap_acquire/staging.py:1146-1224`

**Issue:** `record_validation`'s `ON CONFLICT (run_ts, manifest_digest, target_table)
DO NOTHING` is documented as making a repeated back-fill idempotent, which
is correct for the identical-retry case. But it also means that if
`validate_layer`/`apply_post_validation_ddl` are ever re-run for the same
`(run_ts, manifest_digest, target_table)` key and produce a *different*
`row_count`/`srid`/`geometry_type`/`repaired_count` than a prior attempt
(e.g. a bug fix in staging logic between two runs sharing the same run
directory and manifest digest), the durable audit row silently keeps the
stale values from the first insert — `assert_all_layers_validated`'s D-68
gate would then wave through a promotion whose gate record no longer
reflects what actually happened during the most recent staging pass.

**Fix:** At minimum, log/emit a distinguishable signal when the `ON CONFLICT`
branch actually discards a row (`cursor.rowcount == 0`), so a silently
stale audit row is at least observable, or move to `ON CONFLICT ... DO
UPDATE` guarded by an equality check against the existing row so a genuine
mismatch fails loudly instead of being silently discarded.

## Info

### IN-01: `build_ogr2ogr_command`'s `PG:` connection string is not IPv6-safe

**File:** `vicmap_acquire/staging.py:519-522`

**Issue:** The GDAL PostgreSQL connection string is built as
`f"PG:dbname={policy.dbname} host={policy.host} port={policy.port} user={policy.user}"`.
`staging._host` accepts a raw IP address via `ipaddress.ip_address(value)`,
including IPv6 literals, which contain colons. GDAL's `PG:` key=value
connection-string parser is space-delimited, not colon-delimited, so an
IPv6 `host` value is unlikely to actually break parsing today, but it is
untested and the string is not defensively bracketed
(`host=[::1]`) the way most connection-string formats require for IPv6.
Currently moot (`vicmap.toml` configures `127.0.0.1`), but worth a test or
explicit bracketing if IPv6 is ever a supported deployment target.

**Fix:** Add a regression test exercising an IPv6 `host` through
`build_ogr2ogr_command`, or explicitly reject IPv6 hosts in `_host` until
the connection-string construction is verified against GDAL's actual IPv6
handling.

---

_Reviewed: 2026-09-25T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
