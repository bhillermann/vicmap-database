"""The PostGIS staging boundary: connect, prove privilege, load, validate (D-41..D-64).

This is the first and only module in the package permitted to import a
PostgreSQL driver (D-41) -- every other module in ``vicmap_acquire`` stays
driver-free by construction, proved structurally by ``DriverImportPolicyTest``
in ``tests/test_staging.py``. Importing this module performs no connection,
subprocess, or filesystem work: every network or process call happens inside
a named function, never at import time.

A digest-verified manifest layer travels config -> connection -> privilege
proof -> ``ogr2ogr`` load -> row-count check -> operator output, landing in a
run-timestamped table inside the staging schema (D-48) with ``geom``/``gid``
columns and the configured target SRID (D-45/D-46/D-49). The privilege
preflight (D-59/DB-02) proves the loader cannot write to ``public`` with a
real, rolled-back ``CREATE``, never by reading grant metadata alone (Pitfall
3: ``has_table_privilege`` raises on a table that, by D-48, has never
existed). Every failure mode maps to one closed, code-only exception whose
``.code`` equals the matching ``evidence.ReasonCode`` value the database
boundary already defines; no exception message ever carries driver,
subprocess, or SQL text.
"""

from __future__ import annotations

import ipaddress
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg import errors as pg_errors

import read_mailbox
from vicmap_acquire.evidence import NOT_APPLICABLE, ProgressEvent, SuccessEvent
from vicmap_acquire.manifest import ImportManifest, ManifestLayer


# D-58: the one secret this phase needs reaches the process only through
# this environment variable -- never a config key, never a CLI argument.
PASSWORD_ENV_VAR = "VICMAP_DB_PASSWORD"

# D-62's rolled-back DB-02 capability probe table name.
PROBE_TABLE_NAME = "__db02_privilege_probe"

_HOSTNAME = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)
# Mirrors read_mailbox._PG_IDENTIFIER exactly -- re-checked here so a
# directly constructed StagingPolicy cannot bypass read_mailbox's own
# validate_database_policy contract (semantic validation's single home).
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,62}")
_FORBIDDEN_SCHEMA_NAMES = frozenset({"public"})

# Mirrors naming.py's own two structural limits (naming._MAX_NAME_BYTES and
# its [a-z0-9_] charset rule), re-implemented locally rather than imported:
# naming.py is a pure leaf module with an ``ast`` self-check proving it
# imports nothing, and a dependency in either direction would break that
# proof. A run-timestamp suffix can push an already-normalized target table
# name over these limits even though naming.py itself already validated the
# unsuffixed name.
_STAGING_NAME_CHARSET = re.compile(r"[a-z0-9_]+")
_MAX_STAGING_NAME_BYTES = 63


def _positive_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("staging policy values must be positive integers")
    return value


def _bounded_integer(value: object, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not (minimum <= value <= maximum)
    ):
        raise ValueError("staging policy value is out of range")
    return value


def _identifier(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError("staging policy identifier is not a safe scalar")
    return value


def _host(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("staging policy host must be a non-empty string")
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if _HOSTNAME.fullmatch(value) is None:
        raise ValueError("staging policy host is not a safe scalar")
    return value


def _index_columns(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError("index_columns must be a non-empty tuple")
    validated = tuple(_identifier(column) for column in value)
    if len(set(validated)) != len(validated):
        raise ValueError("index_columns must not contain duplicates")
    return validated


@dataclass(frozen=True)
class StagingPolicy:
    """The ``[database]`` subset of ``read_mailbox.DatabaseRunConfig`` (same
    field names, same types). Semantic validation already lives in
    ``read_mailbox.validate_database_policy``; this re-checks types and
    ranges here so a directly constructed ``StagingPolicy`` cannot bypass
    them (D-58)."""

    host: str
    port: int
    dbname: str
    user: str
    staging_schema: str
    publish_schema: str
    target_srid: int
    index_columns: tuple[str, ...]
    gt: int
    connect_timeout_seconds: int
    statement_timeout_seconds: int
    lock_timeout_seconds: int

    def __post_init__(self) -> None:
        _host(self.host)
        _bounded_integer(self.port, 1, 65535)
        _identifier(self.dbname)
        _identifier(self.user)
        _identifier(self.staging_schema)
        _identifier(self.publish_schema)
        if (
            self.staging_schema in _FORBIDDEN_SCHEMA_NAMES
            or self.publish_schema in _FORBIDDEN_SCHEMA_NAMES
        ):
            raise ValueError("staging policy schemas must not be public")
        if self.staging_schema == self.publish_schema:
            raise ValueError("staging and publish schemas must differ")
        _bounded_integer(self.target_srid, 1024, 998999)
        _index_columns(self.index_columns)
        _positive_integer(self.gt)
        _positive_integer(self.connect_timeout_seconds)
        _positive_integer(self.statement_timeout_seconds)
        _positive_integer(self.lock_timeout_seconds)
        if self.lock_timeout_seconds > self.statement_timeout_seconds:
            raise ValueError(
                "lock_timeout_seconds must not exceed statement_timeout_seconds"
            )


@dataclass(frozen=True)
class DatabaseIdentity:
    """D-61's six non-secret identity fields, always shown in clear."""

    host: str
    port: int
    dbname: str
    role: str
    server_version: str
    postgis_version: str


@dataclass(frozen=True)
class LayerValidation:
    """One layer's post-load validation record. ``spatial is False`` means
    the four geometry-related fields are always ``evidence.NOT_APPLICABLE``
    (D-57); 03-05 fills in the real spatial checks."""

    staging_table: str
    spatial: bool
    row_count: int
    geometry_type: str
    srid: int | str
    repaired_count: int | str
    extent: tuple[float, float, float, float] | str


class StagingFailure(RuntimeError):
    """A closed staging failure carrying no driver-, subprocess-, or
    SQL-controlled text."""

    code = "db_connection_failed"

    def __init__(self) -> None:
        super().__init__(self.code)


class DatabaseConnectionFailed(StagingFailure):
    code = "db_connection_failed"


class PostgisUnavailable(StagingFailure):
    code = "db_postgis_unavailable"


class TargetSridUnresolved(StagingFailure):
    code = "db_target_srid_unresolved"


class PrivilegeDenied(StagingFailure):
    code = "db_privilege_denied"


class LoadFailed(StagingFailure):
    code = "db_load_failed"


class RowCountMismatch(StagingFailure):
    code = "db_row_count_mismatch"


class SridMismatch(StagingFailure):
    code = "db_srid_mismatch"


class GeometryTypeMismatch(StagingFailure):
    code = "db_geometry_type_mismatch"


class GeometryRepairChangedType(StagingFailure):
    code = "db_geometry_repair_changed_type"


class GeometryRepairIncomplete(StagingFailure):
    code = "db_geometry_repair_incomplete"


class StagingDdlFailed(StagingFailure):
    code = "db_staging_ddl_failed"


class TableNameInvalid(StagingFailure):
    """Shares ``evidence.ReasonCode.TABLE_NAME_INVALID``'s code with
    ``naming.TableNameInvalid`` (same meaning: an unsafe table-name scalar).
    Re-checked here -- not imported from ``naming.py`` -- because a
    run-timestamp suffix can push an already-normalized target table name
    over the 63-byte staging-table limit that ``naming.py`` itself never
    sees."""

    code = "table_name_invalid"


def staging_table_name(target_table: str, run_timestamp: str) -> str:
    """D-48: ``f"{target_table}_{run_timestamp.casefold()}"``, re-checked
    against ``naming.py``'s own two structural limits (63 UTF-8 bytes,
    ``[a-z0-9_]`` charset)."""

    if not isinstance(target_table, str) or not target_table:
        raise TableNameInvalid()
    if not isinstance(run_timestamp, str) or not run_timestamp:
        raise TableNameInvalid()
    name = f"{target_table}_{run_timestamp.casefold()}"
    if len(name.encode("utf-8")) > _MAX_STAGING_NAME_BYTES:
        raise TableNameInvalid()
    if _STAGING_NAME_CHARSET.fullmatch(name) is None:
        raise TableNameInvalid()
    return name


def _connect(policy: StagingPolicy, password: str) -> "psycopg.Connection":
    """Open one connection and bound every query this module runs.

    Any ``psycopg`` exception from connecting is ``DatabaseConnectionFailed``
    and nothing else -- the driver's own error text is discarded.
    ``statement_timeout``/``lock_timeout`` are set immediately after
    connecting from the policy's millisecond-converted values so no query
    this module runs can hang the operator's database.
    """

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
        raise DatabaseConnectionFailed() from None

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SET statement_timeout = %s",
                (policy.statement_timeout_seconds * 1000,),
            )
            cursor.execute(
                "SET lock_timeout = %s", (policy.lock_timeout_seconds * 1000,)
            )
        connection.commit()
    except Exception:
        connection.close()
        raise DatabaseConnectionFailed() from None
    return connection


def read_database_identity(policy: StagingPolicy, *, password: str) -> DatabaseIdentity:
    """DB-01: report the six D-61 identity fields in clear, from one
    short-lived connection. A missing PostGIS extension --
    ``PostGIS_Full_Version()`` raising ``UndefinedFunction`` -- is
    ``PostgisUnavailable``, never a partial identity."""

    connection = _connect(policy, password)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, version()")
            dbname, role, server_version = cursor.fetchone()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT PostGIS_Full_Version()")
                (postgis_version,) = cursor.fetchone()
        except pg_errors.UndefinedFunction:
            raise PostgisUnavailable() from None
    except PostgisUnavailable:
        raise
    except Exception:
        raise DatabaseConnectionFailed() from None
    finally:
        connection.close()

    return DatabaseIdentity(
        host=policy.host,
        port=policy.port,
        dbname=dbname,
        role=role,
        server_version=server_version,
        postgis_version=postgis_version,
    )


def preflight_staging_privileges(policy: StagingPolicy, *, password: str) -> None:
    """DB-02: prove capability with a real, rolled-back ``CREATE`` rather
    than inferring it from grant metadata alone (research Pitfall 3:
    ``has_table_privilege`` raises on a table that, by D-48, has never
    existed). Raises ``PrivilegeDenied`` on the first of: the connected role
    is a superuser (D-59 -- a superuser would pass every check below for the
    wrong reason), it lacks ``USAGE`` or ``CREATE`` on the staging schema, it
    holds ``CREATE`` on ``public`` (DB-03/DB-05's runtime proof that the
    loader cannot write there), or the rolled-back probe ``CREATE TABLE`` /
    ``CREATE INDEX`` itself fails. Raises ``TargetSridUnresolved`` when the
    configured ``target_srid`` has no ``spatial_ref_sys`` row. The probe
    transaction is rolled back unconditionally, on both the pass and the
    fail path, so DB-05 holds by construction: nothing is left behind."""

    connection = _connect(policy, password)
    try:
        with connection.cursor() as cursor:
            # 1. Not a superuser (D-59): a superuser bypasses every ACL
            # check below, so it would pass them for the wrong reason.
            cursor.execute(
                "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
            )
            row = cursor.fetchone()
            if row is None or row[0]:
                raise PrivilegeDenied()

            # 2. Staging schema grants -- the two declarative checks valid
            # before any table exists. Schema name is a text parameter here,
            # not an sql.Identifier: has_schema_privilege takes it as data.
            cursor.execute(
                "SELECT has_schema_privilege(current_user, %s, 'USAGE'), "
                "has_schema_privilege(current_user, %s, 'CREATE')",
                (policy.staging_schema, policy.staging_schema),
            )
            has_usage, has_create = cursor.fetchone()
            if not has_usage or not has_create:
                raise PrivilegeDenied()

            # 3. No CREATE on public (DB-03/DB-05): turns D-47's structural
            # claim into a runtime proof -- the loader demonstrates it could
            # not write to public even if it tried.
            cursor.execute(
                "SELECT has_schema_privilege(current_user, 'public', 'CREATE')"
            )
            (has_public_create,) = cursor.fetchone()
            if has_public_create:
                raise PrivilegeDenied()

            # 4. Target SRID is known to PostGIS -- D-63's
            # geometry(Point, <srid>) constraint cannot be created against an
            # SRID the server does not know, and failing here names the
            # cause instead of surfacing it later as a raw DDL error.
            cursor.execute(
                "SELECT 1 FROM spatial_ref_sys WHERE srid = %s",
                (policy.target_srid,),
            )
            if cursor.fetchone() is None:
                raise TargetSridUnresolved()

            # 5. Real capability, rolled back. has_table_privilege cannot
            # perform this check (Pitfall 3): it raises rather than
            # returning false against a table that has never existed. This
            # also proves the PostGIS geometry type and the GiST access
            # method are actually usable, and that the operator's quota and
            # tablespace allow a create.
            table_ref = sql.Identifier(policy.staging_schema, PROBE_TABLE_NAME)
            try:
                cursor.execute(
                    sql.SQL(
                        "CREATE TABLE {table} "
                        "(gid integer PRIMARY KEY, geom geometry(Point, {srid}) NOT NULL)"
                    ).format(table=table_ref, srid=sql.Literal(policy.target_srid))
                )
                cursor.execute(
                    sql.SQL("CREATE INDEX ON {table} USING GIST (geom)").format(
                        table=table_ref
                    )
                )
            except Exception:
                connection.rollback()
                raise PrivilegeDenied() from None
            else:
                # The rollback is unconditional and the transaction never
                # commits, on the pass path as much as the fail path -- DB-05
                # is satisfied by construction, not by remembering to clean up.
                connection.rollback()
    except (PrivilegeDenied, TargetSridUnresolved):
        raise
    except Exception:
        raise DatabaseConnectionFailed() from None
    finally:
        connection.close()


def build_ogr2ogr_command(
    *,
    dataset_path: str | Path,
    layer_name: str,
    staging_table: str,
    policy: StagingPolicy,
) -> list[str]:
    """Build the complete ``ogr2ogr`` argument list. Pure: no environment
    read, no subprocess, no I/O. D-44: the connection string carries
    ``dbname``/``host``/``port``/``user`` only -- no credential token of any
    kind appears here or anywhere else in the returned list."""

    connection_string = (
        f"PG:dbname={policy.dbname} host={policy.host} port={policy.port} "
        f"user={policy.user}"
    )
    return [
        "ogr2ogr",
        "-f",
        "PostgreSQL",
        connection_string,
        str(dataset_path),
        layer_name,
        "-nln",
        staging_table,
        "-lco",
        f"SCHEMA={policy.staging_schema}",
        "-lco",
        "GEOMETRY_NAME=geom",
        "-lco",
        "FID=gid",
        "-lco",
        "SPATIAL_INDEX=NONE",
        "-lco",
        "LAUNDER=YES",
        "-lco",
        "PRECISION=YES",
        "-t_srs",
        f"EPSG:{policy.target_srid}",
        "--config",
        "PG_USE_COPY",
        "YES",
        "--config",
        "OGR_CT_ONLY_BEST",
        "YES",
        "--config",
        "OGR_CT_ALLOW_BALLPARK",
        "NO",
        "-gt",
        str(policy.gt),
    ]


def load_layer(
    *,
    dataset_path: str | Path,
    layer_name: str,
    staging_table: str,
    policy: StagingPolicy,
    password: str,
    diagnostics_dir: str | Path,
) -> None:
    """Run ``build_ogr2ogr_command``'s argv through ``subprocess.run``,
    injecting the credential only via the child process's ``PGPASSWORD``
    environment variable -- never argv. A non-zero return code, a
    ``TimeoutExpired``, or an ``OSError`` all map to the one fixed
    ``LoadFailed``; the exit code value is never inspected. The complete
    unredacted stderr is written to ``diagnostics_dir`` under a deterministic
    name derived from ``staging_table`` -- never branched on for control
    flow."""

    command = build_ogr2ogr_command(
        dataset_path=dataset_path,
        layer_name=layer_name,
        staging_table=staging_table,
        policy=policy,
    )
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=policy.statement_timeout_seconds,
            env={**os.environ, "PGPASSWORD": password},
        )
    except (subprocess.TimeoutExpired, OSError):
        raise LoadFailed() from None

    diagnostics_path = Path(diagnostics_dir) / f"{staging_table}.load.stderr"
    try:
        diagnostics_path.write_text(result.stderr or "", encoding="utf-8")
    except OSError:
        pass

    if result.returncode != 0:
        raise LoadFailed()


def validate_layer(
    *,
    manifest_layer: ManifestLayer,
    staging_table: str,
    policy: StagingPolicy,
    password: str,
) -> LayerValidation:
    """DB-04, row-count only for now (Task 2 of 03-04). Raises
    ``RowCountMismatch`` when the staging table's row count differs from
    ``manifest_layer.profile.feature_count`` (D-37's exact count, D-56's
    baseline). 03-05 fills in the spatial checks; the signature and return
    type stay."""

    connection = _connect(policy, password)
    try:
        with connection.cursor() as cursor:
            table_ref = sql.Identifier(policy.staging_schema, staging_table)
            cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(table_ref))
            (row_count,) = cursor.fetchone()
    except Exception:
        raise LoadFailed() from None
    finally:
        connection.close()

    if row_count != manifest_layer.profile.feature_count:
        raise RowCountMismatch()

    return LayerValidation(
        staging_table=staging_table,
        spatial=manifest_layer.profile.spatial,
        row_count=row_count,
        geometry_type=NOT_APPLICABLE,
        srid=NOT_APPLICABLE,
        repaired_count=NOT_APPLICABLE,
        extent=NOT_APPLICABLE,
    )


def run_staging(
    manifest: ImportManifest,
    policy: StagingPolicy,
    *,
    password: str,
    run_timestamp: str,
    diagnostics_dir: str | Path,
    event_sink,
) -> tuple[LayerValidation, ...]:
    """Compose read identity -> preflight -> (per layer) load -> validate ->
    emit, in the manifest's own order (D-42). A failure at any layer
    re-raises the original typed exception unchanged and no later layer is
    attempted. Every emission is wrapped in ``read_mailbox._EmitOnce``,
    exactly as ``discover_order.run_discovery`` does, so a faulty sink can
    never turn a closed failure into a raw exception."""

    guard = read_mailbox._EmitOnce(event_sink)

    identity = read_database_identity(policy, password=password)
    guard.emit(
        SuccessEvent.database_identity(
            host=identity.host,
            port=identity.port,
            dbname=identity.dbname,
            role=identity.role,
            server_version=identity.server_version,
            postgis_version=identity.postgis_version,
        )
    )
    preflight_staging_privileges(policy, password=password)

    total = len(manifest.layers)
    validations: list[LayerValidation] = []
    for position, layer in enumerate(manifest.layers, start=1):
        staging_table = staging_table_name(layer.target_table, run_timestamp)
        dataset_path = Path(manifest.run_directory) / layer.profile.dataset_relative_path
        load_layer(
            dataset_path=dataset_path,
            layer_name=layer.profile.layer_name,
            staging_table=staging_table,
            policy=policy,
            password=password,
            diagnostics_dir=diagnostics_dir,
        )
        validation = validate_layer(
            manifest_layer=layer,
            staging_table=staging_table,
            policy=policy,
            password=password,
        )
        guard.emit(
            SuccessEvent.staging_table_loaded(
                order_id=manifest.order_id,
                target_table=layer.target_table,
                staging_table=staging_table,
                row_count=validation.row_count,
            )
        )
        guard.emit(ProgressEvent.staging_layer_position(position=position, total=total))
        validations.append(validation)

    return tuple(validations)
