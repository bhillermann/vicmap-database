"""The publication boundary: gate on validation, then atomically promote (D-66..D-73).

This is the second -- and only other -- module in the package permitted to
import a PostgreSQL driver (D-41 extended). Like ``staging.py`` it performs no
connection, subprocess, or filesystem work at import time: every network call
happens inside a named function, never at import. The structural guarantee is
tested by ``tests/test_staging.py::DriverImportPolicyTest``, whose exemption
set is exactly ``{"staging.py", "publish.py"}`` and nothing else -- widened in
the same commit that first added this module's ``import psycopg`` (research
Pitfall 5).

Promoting a validated order is a *metadata move*, never a row copy (D-66): for
every manifest layer, inside one transaction that commits once or rolls back
completely, the module

  1. drops the prior published ``vicmap.{target}`` -- exactly one
     schema-qualified, single-target ``DROP TABLE IF EXISTS`` with no wildcard
     and no cascade modifier (D-71/Pitfall 4/PROHIB-10 -- the one deliberately
     authorized destructive statement in this phase, and the drop that frees
     the canonical names before they are minted, D-67 planner note),
  2. ``ALTER TABLE {staging} SET SCHEMA {publish}`` then ``ALTER TABLE
     {staging} RENAME TO {target}`` -- two separate statements, because
     ``SET SCHEMA`` and ``RENAME`` cannot be combined with any other
     alteration in one ``ALTER TABLE`` (PostgreSQL docs, research Anti-Pattern),
  3. renames the primary-key, ``NOT NULL``, and index objects to their
     canonical published names -- names *discovered from the catalog at
     promotion time* (Pattern 1), never re-derived by string formatting, so a
     staging-time name ``_bounded_composed_identifier`` truncated is still
     renamed correctly and PostgreSQL 18's named ``NOT NULL`` constraint
     (``contype = 'n'``, absent on PG < 18) is handled with the same code path
     on both versions (Pitfall 2),
  4. ``GRANT SELECT`` to the reader role -- in the *same* transaction as the
     rename, so a reader never observes a table that exists but is not yet
     selectable (D-73).

``SELECT version()`` is the first live action of the promotion transaction, so
object discovery stays version-agnostic without ever hardcoding the server's
major version (research Open Question 1). Every failure maps to one closed,
code-only exception whose ``.code`` equals the matching ``evidence.ReasonCode``;
no exception message ever carries driver, subprocess, or SQL text.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg import sql
from psycopg import errors as pg_errors

from vicmap_acquire import staging
from vicmap_acquire.staging import AuditPrivilegeDenied


# D-70: the durable publication-gate record 04-03 writes and this module reads.
AUDIT_SCHEMA = "vicmap_audit"
AUDIT_TABLE = "staging_validation"


@dataclass(frozen=True)
class PublishPolicy:
    """The publish-side subset of ``read_mailbox.DatabaseRunConfig`` (same field
    names and types the config already validated in
    ``read_mailbox.validate_database_policy``), re-checking types and ranges
    here so a directly constructed ``PublishPolicy`` cannot bypass them (D-58) --
    exactly as ``StagingPolicy`` does. It adds ``reader_user`` (D-72): the
    ``GRANT SELECT`` target the staging boundary never needs, re-checked as a
    safe identifier that is never the loader role itself (T-04-09)."""

    host: str
    port: int
    dbname: str
    user: str
    staging_schema: str
    publish_schema: str
    target_srid: int
    reader_user: str
    connect_timeout_seconds: int
    statement_timeout_seconds: int
    lock_timeout_seconds: int

    def __post_init__(self) -> None:
        staging._host(self.host)
        staging._bounded_integer(self.port, 1, 65535)
        staging._identifier(self.dbname)
        staging._identifier(self.user)
        staging._identifier(self.staging_schema)
        staging._identifier(self.publish_schema)
        staging._identifier(self.reader_user)
        if (
            self.staging_schema in staging._FORBIDDEN_SCHEMA_NAMES
            or self.publish_schema in staging._FORBIDDEN_SCHEMA_NAMES
        ):
            raise ValueError("publish policy schemas must not be public")
        if self.staging_schema == self.publish_schema:
            raise ValueError("staging and publish schemas must differ")
        # D-72/T-04-09: the reader is granted read-only SELECT, never the
        # owning loader role -- the two must be distinct identities.
        if self.reader_user == self.user:
            raise ValueError("reader_user must not be the loader role")
        staging._bounded_integer(self.target_srid, 1024, 998999)
        staging._positive_integer(self.connect_timeout_seconds)
        staging._positive_integer(self.statement_timeout_seconds)
        staging._positive_integer(self.lock_timeout_seconds)
        if self.lock_timeout_seconds > self.statement_timeout_seconds:
            raise ValueError(
                "lock_timeout_seconds must not exceed statement_timeout_seconds"
            )


@dataclass(frozen=True)
class PromotionResult:
    """What ``promote_order`` returns on a committed promotion: the live
    server's ``version()`` string (surfaced for the EVID-01 summary and proof
    that discovery was version-aware, Open Question 1) and the canonical target
    tables that are now published, in the manifest's own layer order."""

    server_version: str
    published_tables: tuple[str, ...]


class PublishFailure(RuntimeError):
    """A closed publish failure carrying no driver-, subprocess-, or
    SQL-controlled text -- ``str(self)`` is always exactly ``self.code``."""

    code = "pub_promotion_failed"

    def __init__(self) -> None:
        super().__init__(self.code)


class PromotionFailed(PublishFailure):
    """Any failure inside the one promote/drop/rename/grant transaction -- a
    DDL error, a name-discovery mismatch, a grant failure, or a connection
    problem. The transaction is always rolled back before this is raised, so
    the previous usable ``vicmap.*`` tables remain exactly as they were
    (PUB-03)."""

    code = "pub_promotion_failed"


class PublicationValidationMissing(PublishFailure):
    """D-68 gate failure: at least one manifest layer has no PASS row in
    ``vicmap_audit.staging_validation`` for this ``(run_ts, manifest_digest)``.
    Raised before any DDL runs, so an unvalidated order never reaches
    promotion (T-04-06). A missing row and a non-PASS row fail closed
    identically -- table presence is never trusted as a proxy for validation."""

    code = "pub_validation_missing"


def _connect(policy: PublishPolicy, password: str) -> "psycopg.Connection":
    """Open one connection and bound every query this module runs, following
    ``staging._connect`` exactly: no ``autocommit`` (so the promotion runs in
    one implicit transaction that commits once or rolls back completely), and
    ``statement_timeout``/``lock_timeout`` set immediately from the policy's
    millisecond-converted values so no query can hang the operator's database.
    Any driver exception from connecting or the timeout setup maps to the one
    closed ``PromotionFailed``; the driver's own error text is discarded."""

    try:
        connection = psycopg.connect(
            host=policy.host,
            port=policy.port,
            dbname=policy.dbname,
            user=policy.user,
            password=password,
            connect_timeout=policy.connect_timeout_seconds,
        )
    except Exception:
        raise PromotionFailed() from None

    try:
        with connection.cursor() as cursor:
            # SET is a utility statement that rejects a bind parameter (see
            # staging._connect / ConnectionSetupTest): both values are already
            # validated positive integers, so composing them as sql.Literal is
            # exactly as safe as a bind would have been.
            cursor.execute(
                sql.SQL("SET statement_timeout = {}").format(
                    sql.Literal(policy.statement_timeout_seconds * 1000)
                )
            )
            cursor.execute(
                sql.SQL("SET lock_timeout = {}").format(
                    sql.Literal(policy.lock_timeout_seconds * 1000)
                )
            )
        connection.commit()
    except Exception:
        connection.close()
        raise PromotionFailed() from None
    return connection


def assert_all_layers_validated(
    policy: PublishPolicy,
    password: str,
    *,
    run_timestamp: str,
    manifest_digest: str,
    target_tables,
) -> None:
    """D-68 publication gate, run before any DDL: refuse promotion unless every
    ``target_table`` has a PASS row in ``vicmap_audit.staging_validation`` for
    this ``(run_ts, manifest_digest)`` -- the exact rows 04-03 wrote, keyed by
    the digest 04-03/manifest.py computed.

    The required set must be a subset of the PASS set (research gate example);
    a missing row and a non-PASS verdict both fail closed identically with
    ``PublicationValidationMissing``, so table presence is never trusted as a
    proxy for validation (D-68). A loader that cannot read the audit table
    (schema/table missing, or the D-70 grant never applied) raises the closed
    ``AuditPrivilegeDenied``; any other read failure is ``PromotionFailed``.
    This is a read-only preflight on its own short-lived connection -- it
    executes no DDL and mutates nothing (T-04-06)."""

    required = set(target_tables)
    connection = _connect(policy, password)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "SELECT target_table, verdict FROM {table} "
                    "WHERE run_ts = %s AND manifest_digest = %s"
                ).format(table=sql.Identifier(AUDIT_SCHEMA, AUDIT_TABLE)),
                (run_timestamp, manifest_digest),
            )
            rows = cursor.fetchall()
    except pg_errors.InsufficientPrivilege:
        raise AuditPrivilegeDenied() from None
    except PublishFailure:
        raise
    except Exception:
        raise PromotionFailed() from None
    finally:
        connection.close()

    passed = {row[0] for row in rows if row[1] == "pass"}
    if not required.issubset(passed):
        raise PublicationValidationMissing()


def _discover_constraints(
    cursor, *, staging_schema: str, staging_table: str
) -> list[tuple[str, str, str | None]]:
    """Read the staging table's primary-key and ``NOT NULL`` constraints from
    the catalog (Pattern 1) as ``(conname, contype, column_name)`` rows.

    ``contype IN ('p', 'n')`` covers both the primary key and -- on
    PostgreSQL 18+ -- the named ``NOT NULL`` constraint stored in
    ``pg_constraint`` (Pitfall 2). On PG < 18 no ``'n'`` row exists and the
    caller's rename loop naturally does nothing extra: no version branch, no
    hardcoded auto-generated name. The ``NOT NULL`` column is resolved from
    ``pg_attribute`` via ``conkey[1]`` (a ``NOT NULL`` constraint always
    references exactly one column), so its canonical name is built from the
    real column, never a string-derived guess. The current constraint name is
    read here -- never reconstructed -- so a staging-time name
    ``_bounded_composed_identifier`` truncated to fit 63 bytes is still renamed
    correctly."""

    cursor.execute(
        "SELECT c.conname, c.contype, a.attname "
        "FROM pg_constraint c "
        "JOIN pg_class t ON t.oid = c.conrelid "
        "JOIN pg_namespace n ON n.oid = t.relnamespace "
        "LEFT JOIN pg_attribute a "
        "  ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
        "WHERE n.nspname = %s AND t.relname = %s AND c.contype IN ('p', 'n')",
        (staging_schema, staging_table),
    )
    return list(cursor.fetchall())


def _discover_indexes(
    cursor, *, staging_schema: str, staging_table: str
) -> list[tuple[str, str]]:
    """Read the staging table's non-primary index names and the single column
    each covers from the catalog (Pattern 1) as ``(index_name, column_name)``
    rows.

    ``pg_indexes`` is the entry point -- its ``schemaname``/``tablename``
    filter names exactly the table being promoted -- joined to
    ``pg_index``/``pg_attribute`` to resolve each index's indexed column
    authoritatively rather than parsing ``indexdef`` text. ``NOT indisprimary``
    excludes the primary key's backing index, which ``ALTER TABLE ... RENAME
    CONSTRAINT`` already renames implicitly; every remaining index in this
    schema (the GiST geometry index, the allowlisted secondary btrees) is
    single-column by construction (D-62/D-64), so one row is returned per
    index and its canonical name is ``{target}_{column}_idx`` -- the geometry
    index becoming ``{target}_geom_idx``."""

    cursor.execute(
        "SELECT idx.indexname, a.attname "
        "FROM pg_indexes idx "
        "JOIN pg_class ic ON ic.relname = idx.indexname "
        "JOIN pg_namespace icn "
        "  ON icn.oid = ic.relnamespace AND icn.nspname = idx.schemaname "
        "JOIN pg_index x ON x.indexrelid = ic.oid "
        "JOIN pg_attribute a "
        "  ON a.attrelid = x.indrelid AND a.attnum = ANY(x.indkey) "
        "WHERE idx.schemaname = %s AND idx.tablename = %s AND NOT x.indisprimary",
        (staging_schema, staging_table),
    )
    return list(cursor.fetchall())


def _promote_layer(cursor, policy: PublishPolicy, *, staging_table: str, target: str) -> None:
    """Promote one staging layer to its canonical ``{publish_schema}.{target}``
    inside the caller's already-open transaction (no commit, no rollback here --
    ``promote_order`` owns the single commit/rollback for the whole order).

    Object names are discovered from the catalog *before* the metadata move
    (the move does not rename dependent objects, so the names read here are
    still valid afterward). The prior published table is dropped first, freeing
    the canonical names before they are minted (D-67 planner note); then the
    staging table is moved and renamed; then its discovered objects are renamed
    to canonical names; then the reader is granted SELECT."""

    staging_schema = policy.staging_schema
    publish_schema = policy.publish_schema

    constraints = _discover_constraints(
        cursor, staging_schema=staging_schema, staging_table=staging_table
    )
    indexes = _discover_indexes(
        cursor, staging_schema=staging_schema, staging_table=staging_table
    )

    staging_ref = sql.Identifier(staging_schema, staging_table)
    prior_ref = sql.Identifier(publish_schema, target)
    moved_ref = sql.Identifier(publish_schema, staging_table)
    target_ref = sql.Identifier(publish_schema, target)

    # D-71 / Pitfall 4 / PROHIB-10: the one deliberately-authorized destructive
    # statement -- a single schema-qualified target, no wildcard, no cascade.
    cursor.execute(sql.SQL("DROP TABLE IF EXISTS {table}").format(table=prior_ref))

    # D-66: metadata move as two separate statements (SET SCHEMA and RENAME
    # cannot be combined with other alterations in one ALTER TABLE).
    cursor.execute(
        sql.SQL("ALTER TABLE {table} SET SCHEMA {schema}").format(
            table=staging_ref, schema=sql.Identifier(publish_schema)
        )
    )
    cursor.execute(
        sql.SQL("ALTER TABLE {table} RENAME TO {name}").format(
            table=moved_ref, name=sql.Identifier(target)
        )
    )

    # D-67: rename discovered constraints to canonical, bounded names.
    for conname, contype, column_name in constraints:
        if contype == "p":
            canonical = staging._bounded_composed_identifier(f"{target}_pkey")
        else:  # 'n' -- PG18+ named NOT NULL, column resolved from the catalog
            canonical = staging._bounded_composed_identifier(
                f"{target}_{column_name}_not_null"
            )
        cursor.execute(
            sql.SQL("ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}").format(
                table=target_ref,
                old=sql.Identifier(conname),
                new=sql.Identifier(canonical),
            )
        )

    # D-67: rename discovered indexes to canonical {target}_{column}_idx. Index
    # names are schema-scoped, so the outgoing name is qualified by the publish
    # schema it now lives in after SET SCHEMA.
    for index_name, column_name in indexes:
        canonical = staging._bounded_composed_identifier(f"{target}_{column_name}_idx")
        cursor.execute(
            sql.SQL("ALTER INDEX {old} RENAME TO {new}").format(
                old=sql.Identifier(publish_schema, index_name),
                new=sql.Identifier(canonical),
            )
        )

    # D-73: reader SELECT grant, in the same transaction as the rename, so no
    # exists-but-unselectable window is ever visible.
    cursor.execute(
        sql.SQL("GRANT SELECT ON {table} TO {reader}").format(
            table=target_ref, reader=sql.Identifier(policy.reader_user)
        )
    )


def promote_order(
    manifest,
    policy: PublishPolicy,
    password: str,
    run_timestamp: str,
    manifest_digest: str,
) -> PromotionResult:
    """Promote every layer of ``manifest`` into the publish schema in one
    transaction that commits once or rolls back completely (PUB-02/PUB-03).

    ``SELECT version()`` is the first live action, keeping catalog discovery
    version-agnostic (Open Question 1). Each layer's staging table is computed
    with ``staging.staging_table_name`` (never string-formatted here), promoted
    by ``_promote_layer``, and only after every layer has moved, renamed, and
    granted does the single ``commit()`` run. Any exception rolls the whole
    transaction back -- so no layer is ever partially published and every prior
    ``vicmap.*`` table is left exactly as it was -- and re-raises the closed
    ``PromotionFailed`` with no driver or SQL text (a ``PublishFailure`` such as
    the gate's ``PublicationValidationMissing`` is re-raised unchanged)."""

    # D-68: hard-stop an unvalidated order before any DDL. This runs first, on
    # its own read-only connection, so a missing/non-PASS layer never reaches
    # the promotion transaction below (T-04-06).
    assert_all_layers_validated(
        policy,
        password,
        run_timestamp=run_timestamp,
        manifest_digest=manifest_digest,
        target_tables=tuple(layer.target_table for layer in manifest.layers),
    )

    connection = _connect(policy, password)
    published: list[str] = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            (server_version,) = cursor.fetchone()
            for layer in manifest.layers:
                target = layer.target_table
                staging_table = staging.staging_table_name(target, run_timestamp)
                _promote_layer(
                    cursor, policy, staging_table=staging_table, target=target
                )
                published.append(target)
        connection.commit()
    except PublishFailure:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise PromotionFailed() from None
    finally:
        connection.close()

    return PromotionResult(
        server_version=server_version, published_tables=tuple(published)
    )
