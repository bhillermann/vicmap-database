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

import json
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg import errors as pg_errors

from vicmap_acquire import download, evidence, staging
from vicmap_acquire.evidence import SuccessEvent
from vicmap_acquire.manifest import ImportManifest
from vicmap_acquire.staging import AuditPrivilegeDenied


# D-70: the durable publication-gate record 04-03 writes and this module reads.
AUDIT_SCHEMA = "vicmap_audit"
AUDIT_TABLE = "staging_validation"

# D-74: the reader's own secret, exactly parallel to staging.PASSWORD_ENV_VAR
# (the loader's VICMAP_DB_PASSWORD) -- never a config key, never argv.
READER_PASSWORD_ENV_VAR = "VICMAP_READER_PASSWORD"


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
class ReaderVerification:
    """What ``verify_reader_access`` returns on a passed PUB-04/PUB-05 proof:
    the published tables the reader role can itself see (re-derived from a
    real reader-authenticated query, never trusted from the caller's
    ``published_tables`` argument alone), the row count the representative
    spatial query returned, and ``write_denied`` -- always ``True`` here,
    since the not-denied branch never returns a result (it raises
    ``ReaderWriteNotDenied`` instead)."""

    tables_discovered: tuple[str, ...]
    spatial_query_row_count: int
    write_denied: bool


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


class ReaderRoleUnavailable(PublishFailure):
    """D-72/D-74: the reader role, its ``USAGE`` grant, or
    ``VICMAP_READER_PASSWORD`` is missing or wrong -- an unset password is
    caught before any connection is attempted, and a connect/authentication
    failure as the reader maps here too. Fails closed before the proof runs,
    exposing no secret and no driver text (must-have)."""

    code = "reader_role_unavailable"


class ReaderVerificationFailed(PublishFailure):
    """D-74: discovery or the representative spatial query failed for a
    reason other than the write-denial proof itself -- e.g. the query
    raised, or there was no published table to prove against."""

    code = "reader_verification_failed"


class ReaderWriteNotDenied(PublishFailure):
    """T-04-02 (security-critical): the reader's attempted write was NOT
    rejected -- the grant model is broken. This is the phase's most urgent
    failure and must never be downgraded to a warning or a pass;
    ``evidence.py``'s remediation hint for this code is immediate
    revocation, not a routine retry."""

    code = "reader_write_not_denied"


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


def _connect_as_reader(policy: PublishPolicy, reader_password: str) -> "psycopg.Connection":
    """Open a fresh, genuinely independent connection authenticated as
    ``policy.reader_user`` -- never ``SET ROLE`` from the loader connection
    (D-74/Pattern 3: ``SET ROLE`` would prove privilege bits, not a real
    login, and would require the loader to hold membership in the reader
    role). Mirrors ``_connect``'s timeout setup so no reader query can hang
    the operator's database. Any failure -- wrong/missing password, the role
    not existing, the server unreachable, the timeout SETs failing -- maps to
    the one closed ``ReaderRoleUnavailable``, discarding all driver text."""

    try:
        connection = psycopg.connect(
            host=policy.host,
            port=policy.port,
            dbname=policy.dbname,
            user=policy.reader_user,
            password=reader_password,
            connect_timeout=policy.connect_timeout_seconds,
        )
    except Exception:
        raise ReaderRoleUnavailable() from None

    try:
        with connection.cursor() as cursor:
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
        raise ReaderRoleUnavailable() from None
    return connection


def verify_reader_access(
    policy: PublishPolicy,
    *,
    reader_password: str,
    published_tables: tuple[str, ...],
) -> ReaderVerification:
    """PUB-04/PUB-05/D-74: prove the reader role's whole access contract from
    a real, independently-authenticated login -- discover the tables it can
    see, run a representative GiST-exercising spatial query over Victoria's
    real extent, and attempt a real write that must be denied.

    A missing/unset ``reader_password`` or an empty ``published_tables``
    fails closed before any connection is attempted -- ``ReaderRoleUnavailable``
    and ``ReaderVerificationFailed`` respectively -- exposing no secret
    (must-have). ``published_tables[0]`` (this run's promoted target) is the
    representative table both the spatial query and the write-denial attempt
    run against. The reader connection is always rolled back and closed
    before this function returns or raises, so no state is ever left behind.

    Discovery uses ``information_schema.tables``, which only lists objects
    the connected role holds at least one privilege on -- so the query
    itself is part of the PUB-05 proof, not just a listing convenience
    (research Code Examples). The spatial query's envelope is Victoria's real
    WGS84 extent, ``ST_Transform``-ed into ``policy.target_srid`` at query
    time -- never EPSG:7899's own advertised projected-meters bounds, which
    are the Lambert Conformal Conic's full mathematical domain, not
    Victoria's actual footprint (Pitfall 3). The write-denial attempt is a
    real executed ``INSERT ... DEFAULT VALUES`` -- chosen over ``UPDATE``
    because PostgreSQL's ACL check runs at executor startup, before any
    ``NOT NULL`` constraint is ever evaluated -- never a grant-metadata-only
    shortcut (research Anti-Pattern). If the write is
    not rejected, the grant model is broken: this raises the security-critical
    ``ReaderWriteNotDenied`` and never returns a passing result (T-04-02)."""

    if not reader_password:
        raise ReaderRoleUnavailable()
    if not published_tables:
        raise ReaderVerificationFailed()

    target = published_tables[0]
    connection = _connect_as_reader(policy, reader_password)
    try:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = %s ORDER BY table_name",
                    (policy.publish_schema,),
                )
                tables_discovered = tuple(row[0] for row in cursor.fetchall())

                # Pattern 4/Pitfall 3: Victoria's real WGS84 extent, ST_Transform-ed
                # into target_srid at query time -- never EPSG:7899's own
                # advertised projected-meters "bounds" (the projection's full
                # mathematical domain, not Victoria's actual footprint).
                cursor.execute(
                    sql.SQL(
                        "SELECT gid FROM {table} WHERE geom && "
                        "ST_Transform(ST_MakeEnvelope(140.96, -39.2, 150.04, -33.98, 4326), %s) "
                        "LIMIT 10"
                    ).format(table=sql.Identifier(policy.publish_schema, target)),
                    (policy.target_srid,),
                )
                spatial_query_row_count = len(cursor.fetchall())
        except Exception:
            raise ReaderVerificationFailed() from None

        # D-74/Pattern 3: the write-denial proof is a real executed INSERT,
        # never a grant-metadata-only shortcut -- DEFAULT VALUES
        # needs no prior SELECT and is rejected by the executor's ACL check
        # before any NOT NULL constraint is ever evaluated.
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
            # T-04-02/security-critical: a writable reader means the grant
            # model is broken -- this must never be downgraded to a warning
            # or a pass.
            raise ReaderWriteNotDenied()
    finally:
        connection.rollback()
        connection.close()

    return ReaderVerification(
        tables_discovered=tables_discovered,
        spatial_query_row_count=spatial_query_row_count,
        write_denied=write_denied,
    )


@dataclass(frozen=True)
class LayerValidationRecord:
    """One durable ``vicmap_audit.staging_validation`` row -- the D-56 metrics
    plus verdict Phase 3's back-fill (``staging.record_validation``) actually
    persisted -- re-read independently by ``read_layer_validations`` for the
    EVID-01 summary (D-76). Never constructed from an in-memory
    ``staging.LayerValidation``; ``srid``/``geometry_type``/``repaired_count``
    are ``None`` for a non-spatial layer, exactly as the table's own nullable
    columns store them."""

    target_table: str
    verdict: str
    spatial: bool
    row_count: int
    srid: int | None
    geometry_type: str | None
    repaired_count: int | None


def read_layer_validations(
    policy: PublishPolicy,
    password: str,
    *,
    run_timestamp: str,
    manifest_digest: str,
    target_tables: tuple[str, ...],
) -> tuple[LayerValidationRecord, ...]:
    """D-76: re-read the durable ``vicmap_audit.staging_validation`` rows for
    this run's manifest layers as this run's own staging-validation facts for
    the EVID-01 summary -- a second, independent read of the same table
    ``assert_all_layers_validated`` gates on, never threading that call's
    in-memory pass/fail result forward. Read-only: executes no DDL and
    mutates nothing.

    Failure modes mirror the gate's own: the loader being unable to read the
    audit table raises the closed ``AuditPrivilegeDenied``; any other read
    failure raises ``PromotionFailed``. Rows are returned in
    ``target_tables``' own order; a target table absent from the result set
    is simply omitted -- this function stays a pure read, never itself a
    validation gate, so ``assemble_summary``'s own hard-require is what
    notices a shortfall.
    """

    connection = _connect(policy, password)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "SELECT target_table, verdict, spatial, row_count, srid, "
                    "geometry_type, repaired_count FROM {table} "
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

    by_table = {
        row[0]: LayerValidationRecord(
            target_table=row[0],
            verdict=row[1],
            spatial=row[2],
            row_count=row[3],
            srid=row[4],
            geometry_type=row[5],
            repaired_count=row[6],
        )
        for row in rows
    }
    return tuple(by_table[table] for table in target_tables if table in by_table)


def assemble_summary(
    *,
    order_id: str,
    artifact_path: Path,
    manifest: ImportManifest,
    manifest_digest: str,
    validation_rows: tuple[LayerValidationRecord, ...],
    publication_result: PromotionResult,
    reader_verification: ReaderVerification,
    fingerprint_hex_chars: int = 16,
) -> dict:
    """D-75/D-76: assemble the EVID-01 redacted summary purely by re-reading
    already-durable facts and recombining this run's own results -- never a
    growing in-memory record threaded between phase invocations.

    This function performs exactly one re-read of its own: Phase 1's
    provenance sidecar via ``download.read_provenance_sidecar`` (the message
    fingerprint and artifact checksum). Everything else it is handed by the
    caller, who has already re-read Phase 2's ``manifest.json``
    (``manifest``/``manifest_digest``) and Phase 3's ``vicmap_audit`` rows
    (``validation_rows``), plus this run's own ``promote_order`` and
    ``verify_reader_access`` results.

    Every field is validated through ``evidence.py``'s safe-scalar helpers
    before this function returns: the six EVID-01 link facts are first
    round-tripped through ``SuccessEvent.publication_summary`` (04-01's own
    redaction contract for the event mirror), and the additional per-layer
    staging-validation detail ``summary.json`` carries beyond that minimal
    vocabulary is checked with the same closed validators directly. A
    malformed input -- an unsafe scalar, a non-PASS verdict, or a manifest
    layer with no matching ``validation_rows`` entry -- raises ``ValueError``
    before anything is returned; there is no partially assembled summary.
    """

    provenance = download.read_provenance_sidecar(artifact_path, order_id=order_id)

    target_tables = tuple(layer.target_table for layer in manifest.layers)
    layer_count = len(manifest.layers)

    # D-75: round-trip the six EVID-01 link facts through the redacted event
    # vocabulary 04-01 already defined -- this is the guarantee, not a
    # decorative parallel construction.
    event = SuccessEvent.publication_summary(
        order_id=order_id,
        message_fingerprint=provenance.message_fingerprint,
        artifact_sha256=provenance.sha256,
        manifest_sha256=manifest_digest,
        layer_count=layer_count,
        published_tables=publication_result.published_tables,
        reader_tables_discovered=len(reader_verification.tables_discovered),
        reader_spatial_query_row_count=reader_verification.spatial_query_row_count,
        reader_write_denied=reader_verification.write_denied,
        fingerprint_hex_chars=fingerprint_hex_chars,
    )

    by_table = {record.target_table: record for record in validation_rows}
    missing = [table for table in target_tables if table not in by_table]
    if missing:
        raise ValueError(
            "validation_rows is missing a durable PASS row for a manifest layer"
        )

    staging_validation = []
    for table in target_tables:
        record = by_table[table]
        if record.verdict != "pass":
            raise ValueError(
                "validation_rows must carry only a durable PASS verdict"
            )
        if isinstance(record.spatial, bool) is False:
            raise ValueError("spatial must be a bool")
        if record.spatial:
            srid = record.srid
            geometry_type = record.geometry_type
            repaired_count = record.repaired_count
            if srid is None or geometry_type is None or repaired_count is None:
                raise ValueError(
                    "a spatial layer's staging validation must carry geometry facts"
                )
        else:
            srid = evidence.NOT_APPLICABLE
            geometry_type = evidence.NOT_APPLICABLE
            repaired_count = evidence.NOT_APPLICABLE

        staging_validation.append(
            {
                "target_table": evidence._require_target_table(record.target_table),
                "spatial": record.spatial,
                "row_count": evidence._require_count(record.row_count),
                "srid": evidence._require_srid_or_not_applicable(srid),
                "geometry_type": evidence._require_geometry_type_or_not_applicable(
                    geometry_type
                ),
                "repaired_count": evidence._require_count_or_not_applicable(
                    repaired_count
                ),
            }
        )

    return {
        "order_id": event["order_id"],
        "message_fingerprint": event["message_fingerprint"],
        "artifact_sha256": event["artifact_sha256"],
        "manifest_sha256": event["manifest_sha256"],
        "layer_count": event["layer_count"],
        "published_tables": event["published_tables"],
        "server_version": evidence._require_server_version(
            publication_result.server_version
        ),
        "staging_validation": staging_validation,
        "reader": {
            "tables_discovered": [
                evidence._require_target_table(table)
                for table in reader_verification.tables_discovered
            ],
            "tables_discovered_count": event["reader_tables_discovered"],
            "spatial_query_row_count": event["reader_spatial_query_row_count"],
            "write_denied": event["reader_write_denied"],
        },
    }


def summary_to_publication_event(summary: dict) -> SuccessEvent:
    """Rebuild the D-75 ``publication_summary`` event from an already-
    assembled ``summary`` dict, re-applying the same redaction validators
    ``assemble_summary`` already ran -- so the event ``publish_order.py``
    renders is provably the ``summary.json`` file's own mirror, never a
    second, independently constructed payload (the one-output-mechanism
    guarantee D-75 describes)."""

    reader = summary["reader"]
    return SuccessEvent.publication_summary(
        order_id=summary["order_id"],
        message_fingerprint=summary["message_fingerprint"],
        artifact_sha256=summary["artifact_sha256"],
        manifest_sha256=summary["manifest_sha256"],
        layer_count=summary["layer_count"],
        published_tables=tuple(summary["published_tables"]),
        reader_tables_discovered=reader["tables_discovered_count"],
        reader_spatial_query_row_count=reader["spatial_query_row_count"],
        reader_write_denied=reader["write_denied"],
    )


def write_summary(run_directory: Path, summary: dict) -> Path:
    """Durably write ``summary.json`` into ``run_directory`` (D-75's file
    deliverable) as canonical UTF-8 JSON, mirroring ``manifest.py``'s own
    ``json.dumps(..., sort_keys=True, ensure_ascii=False)`` idiom exactly, so
    the file is byte-stable given the same summary content.

    Unlike ``manifest.json``, this file is never digest-verified by another
    process (it lives in the git-ignored ``runs/`` tree as the milestone's
    proof artifact, not a durable receipt something else reads back), so a
    plain write -- not the atomic exclusive-create dance ``write_manifest``
    uses -- is sufficient; a retried publish simply overwrites it. Any
    ``OSError`` propagates unwrapped -- there is no dedicated reason code for
    a summary-write failure, so it is deliberately left for the CLI's
    catch-all ``INTERNAL_FAILURE`` mapping, exactly as an unexpected failure
    should be.
    """

    canonical = json.dumps(
        summary, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    summary_path = Path(run_directory) / "summary.json"
    summary_path.write_text(canonical + "\n", encoding="utf-8")
    return summary_path
