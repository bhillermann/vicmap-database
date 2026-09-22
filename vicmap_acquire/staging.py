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
    """D-43: on a non-zero ``ogr2ogr`` exit, ``diagnostics_file`` carries the
    *name* (never the full path, never the stderr content) of the local file
    ``load_layer`` already wrote the complete unredacted stderr to -- an
    attribute for the operator-facing caller to surface, never interpolated
    into ``str(self)``, which stays exactly ``self.code`` like every other
    ``StagingFailure``."""

    code = "db_load_failed"

    def __init__(self, *, diagnostics_file: str | None = None) -> None:
        self.diagnostics_file = diagnostics_file
        super().__init__()


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
            # PostgreSQL's SET is a utility statement, not DML, and rejects a
            # bind parameter outright ("syntax error at or near $1") -- there
            # is no parameterized form. Both values are already validated
            # positive integers (StagingPolicy.__post_init__), so composing
            # them as sql.Literal is exactly as safe as a bind parameter
            # would have been, with no string-formatted SQL involved.
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
        "-ct_opt",
        "ONLY_BEST=YES",
        "-ct_opt",
        "ALLOW_BALLPARK=NO",
        "-gt",
        str(policy.gt),
    ]


_DIAGNOSTICS_FILENAME_TEMPLATE = "db_load_{staging_table}.stderr"


def diagnostics_path(diagnostics_dir: str | Path, staging_table: str) -> Path:
    """D-43's stderr file location: ``diagnostics_dir /
    "db_load_{staging_table}.stderr"``. Pure -- no I/O, no environment read."""

    return Path(diagnostics_dir) / _DIAGNOSTICS_FILENAME_TEMPLATE.format(
        staging_table=staging_table
    )


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
    unredacted stderr is written to ``diagnostics_path(diagnostics_dir,
    staging_table)`` before ``LoadFailed`` is ever raised for a non-zero
    exit -- never branched on for control flow, and never interpolated into
    the raised exception's own text (D-43: the file gets everything, the
    exception carries only its file *name* via ``diagnostics_file``)."""

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

    stderr_path = diagnostics_path(diagnostics_dir, staging_table)
    try:
        stderr_path.write_text(result.stderr or "", encoding="utf-8")
    except OSError:
        pass

    if result.returncode != 0:
        raise LoadFailed(diagnostics_file=stderr_path.name)


# D-56: the ZM-suffix vocabulary a declared geometry-type name may carry,
# mapped onto ST_Zmflag(geom)'s own integer encoding.
_ZM_SUFFIX_FLAGS = {"": 0, "M": 1, "Z": 2, "ZM": 3}

_BASE_GEOMETRY_NAMES = frozenset(
    {
        "POINT",
        "LINESTRING",
        "POLYGON",
        "MULTIPOINT",
        "MULTILINESTRING",
        "MULTIPOLYGON",
        "GEOMETRYCOLLECTION",
    }
)

def _split_declared_geometry_type(declared: object) -> tuple[str, str]:
    """Split a ``LayerProfile.geometry_type`` string into its base name and
    ZM suffix token, validating both against D-38's closed vocabulary.
    Raises ``GeometryTypeMismatch`` for anything else, including ``None``,
    ``""``, and the literal ``"Unknown"`` -- D-38 already hard-stops on
    ``Unknown`` upstream in ``discovery.py``; silently accepting it here
    would reopen that gap."""

    if not isinstance(declared, str) or not declared:
        raise GeometryTypeMismatch()
    tokens = declared.split()
    if not tokens or len(tokens) > 2:
        raise GeometryTypeMismatch()
    base = tokens[0].upper()
    suffix_token = tokens[1].upper() if len(tokens) == 2 else ""
    if base not in _BASE_GEOMETRY_NAMES:
        raise GeometryTypeMismatch()
    if suffix_token not in _ZM_SUFFIX_FLAGS:
        raise GeometryTypeMismatch()
    return base, suffix_token


def normalize_declared_geometry_type(declared: object) -> tuple[str, int]:
    """Map a ``pyogrio`` geometry-type name (``LayerProfile.geometry_type``,
    e.g. ``"Point Z"``) onto ``(name, zmflag)``: the base name concatenated
    with its ZM suffix and no space (``"POINTZ"``), and ``ST_Zmflag(geom)``'s
    integer encoding (``0`` 2D, ``1`` M, ``2`` Z, ``3`` ZM).

    This concatenated name is a fixed, tested contract for this function's
    *return value* -- it is not a literal prediction of what PostGIS's own
    ``GeometryType(geom)`` reports. Live verification against a real
    PostgreSQL 17.5/PostGIS 3.5.2 server found ``GeometryType()`` never
    appends a bare ``Z`` or ``ZM`` suffix at all (``GeometryType(
    ST_GeomFromText('POINT Z (1 1 1)')) = 'POINT'``, not ``'POINTZ'``; a
    genuine XYZM point also comes back bare ``'POINT'``) and only ever
    appends ``M`` for the historically ambiguous XYM case (``GeometryType(
    ST_GeomFromText('POINT M (1 1 1)')) = 'POINTM'``). ``validate_layer``
    accounts for that quirk with ``_geometry_type_base_name`` and leans on
    ``ST_Zmflag`` -- never this function's suffixed string -- as the
    authoritative Z/M signal when comparing against a live table."""

    base, suffix_token = _split_declared_geometry_type(declared)
    return base + suffix_token, _ZM_SUFFIX_FLAGS[suffix_token]


# Try the longest suffix first so "POINTZM" strips to "POINT" in one pass
# rather than mis-stripping "M" and leaving "POINTZ" unresolved.
_SUFFIX_TOKENS_BY_LENGTH = ("ZM", "Z", "M")

_EXTENT_TEXT = re.compile(
    r"BOX\(\s*(?P<xmin>[+-]?[0-9.eE]+)\s+(?P<ymin>[+-]?[0-9.eE]+)\s*,\s*"
    r"(?P<xmax>[+-]?[0-9.eE]+)\s+(?P<ymax>[+-]?[0-9.eE]+)\s*\)"
)


def _geometry_type_base_name(name: str) -> str:
    """Strip a trailing ZM/Z/M suffix from a geometry-type name, leaving it
    unchanged if no such suffix is present or stripping it would not yield
    one of the seven OGC base names. Used to compare
    ``normalize_declared_geometry_type``'s suffixed contract against
    PostGIS's own ``GeometryType(geom)`` output -- which, per the live
    finding documented on that function, only ever carries an ``M`` suffix
    in practice. The same helper handles both vocabularies so the
    comparison never depends on which one produced a given string."""

    for suffix in _SUFFIX_TOKENS_BY_LENGTH:
        if name.endswith(suffix) and name[: -len(suffix)] in _BASE_GEOMETRY_NAMES:
            return name[: -len(suffix)]
    return name


def build_validation_query(
    *, staging_schema: str, staging_table: str, spatial: bool
) -> "sql.Composed":
    """The single read-only D-56/D-57 validation query for the selected
    profile. Pure: composes identifiers, touches no connection.

    The non-spatial profile (D-57) selects only a row count and contains no
    ``ST_`` call and no reference to a geometry column at all -- D-35's
    lookup tables and relationship classes have no geometry column to query.

    The spatial profile computes every fact in one query: row count,
    null-geometry count, invalid count, the D-55 pre-write type-change
    count, and the two-element-capped distinct sets for SRID/geometry-type/
    ZM-flag that make a *mixed* table blocking, not just a wrong single
    value. Every scalar subquery is uncorrelated (each references
    ``{table}`` directly, never an outer row), so the composed ``SELECT``
    carries no outer ``FROM`` clause at all and always returns exactly one
    row, including when the table itself holds zero rows."""

    table_ref = sql.Identifier(staging_schema, staging_table)
    if not spatial:
        return sql.SQL("SELECT COUNT(*) AS row_count FROM {table}").format(
            table=table_ref
        )
    return sql.SQL(
        "SELECT "
        "(SELECT COUNT(*) FROM {table}) AS row_count, "
        "(SELECT COUNT(*) FROM {table} WHERE geom IS NULL) AS null_geom_count, "
        "(SELECT COUNT(*) FROM {table} WHERE NOT ST_IsValid(geom)) AS invalid_count, "
        "(SELECT COUNT(*) FROM {table} WHERE NOT ST_IsValid(geom) "
        "AND GeometryType(ST_MakeValid(geom)) IS DISTINCT FROM GeometryType(geom)"
        ") AS type_changed_count, "
        "(SELECT array_agg(srid) FROM (SELECT DISTINCT ST_SRID(geom) AS srid "
        "FROM {table} WHERE geom IS NOT NULL LIMIT 2) AS srid_sample) AS srids_seen, "
        "(SELECT array_agg(geometry_type) FROM (SELECT DISTINCT GeometryType(geom) "
        "AS geometry_type FROM {table} WHERE geom IS NOT NULL LIMIT 2) AS type_sample"
        ") AS geometry_types_seen, "
        "(SELECT array_agg(zmflag) FROM (SELECT DISTINCT ST_Zmflag(geom) AS zmflag "
        "FROM {table} WHERE geom IS NOT NULL LIMIT 2) AS zmflag_sample) AS zmflags_seen, "
        "(SELECT ST_Extent(geom)::text FROM {table}) AS extent"
    ).format(table=table_ref)


def build_repair_statement(
    *, staging_schema: str, staging_table: str
) -> "sql.Composed":
    """D-54's counted repair: ``UPDATE ... SET geom = ST_MakeValid(geom)
    WHERE NOT ST_IsValid(geom)``. Pure, ``sql.Identifier``-composed. D-55
    explicitly rejected a geometry-collection-extracting salvage function
    because it discards geometry silently, and rejected a hand-rolled
    zero-distance-buffer repair too -- this module never calls either."""

    table_ref = sql.Identifier(staging_schema, staging_table)
    return sql.SQL(
        "UPDATE {table} SET geom = ST_MakeValid(geom) WHERE NOT ST_IsValid(geom)"
    ).format(table=table_ref)


def _parse_extent(text: object) -> tuple[float, float, float, float]:
    """Parse PostGIS's ``ST_Extent(geom)::text`` ``BOX(xmin ymin,xmax ymax)``
    form into the four floats ``LayerValidation.extent`` holds. Never
    called on a table this function's caller has not already proven holds
    at least one row (an empty table's ``ST_Extent`` is ``NULL``, which
    ``row_count``'s earlier ``RowCountMismatch`` check would already have
    stopped the run over, for any manifest with a positive feature count)."""

    if not isinstance(text, str):
        raise LoadFailed()
    match = _EXTENT_TEXT.fullmatch(text.strip())
    if match is None:
        raise LoadFailed()
    return (
        float(match["xmin"]),
        float(match["ymin"]),
        float(match["xmax"]),
        float(match["ymax"]),
    )


def validate_layer(
    *,
    manifest_layer: ManifestLayer,
    staging_table: str,
    policy: StagingPolicy,
    password: str,
) -> LayerValidation:
    """DB-04: validate the staging table this run just loaded, against the
    manifest's own baseline (D-53/D-56/D-57). The subject is the staging
    table after ``ogr2ogr``'s ``-t_srs`` transform -- never the source file.
    The profile is selected by ``manifest_layer.profile.spatial`` (D-57),
    not by probing the table or checking whether ``geometry_type`` is
    ``None``. Every disagreement raises its own named ``StagingFailure``
    subclass; an invalid geometry whose ``ST_MakeValid`` output changes
    ``GeometryType`` is never written, and a repair that leaves a row
    invalid is never committed (the connection's implicit rollback on close
    undoes the partial ``UPDATE``)."""

    spatial = manifest_layer.profile.spatial
    table_ref = sql.Identifier(policy.staging_schema, staging_table)
    connection = _connect(policy, password)
    try:
        query = build_validation_query(
            staging_schema=policy.staging_schema,
            staging_table=staging_table,
            spatial=spatial,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                row = cursor.fetchone()
        except Exception:
            raise LoadFailed() from None

        if not spatial:
            (row_count,) = row
            if row_count != manifest_layer.profile.feature_count:
                raise RowCountMismatch()
            return LayerValidation(
                staging_table=staging_table,
                spatial=False,
                row_count=row_count,
                geometry_type=NOT_APPLICABLE,
                srid=NOT_APPLICABLE,
                repaired_count=NOT_APPLICABLE,
                extent=NOT_APPLICABLE,
            )

        (
            row_count,
            null_geom_count,
            invalid_count,
            type_changed_count,
            srids_seen,
            geometry_types_seen,
            zmflags_seen,
            extent_text,
        ) = row

        # 1. Row count first (D-37/D-56) -- every later check is meaningless
        # over the wrong row set.
        if row_count != manifest_layer.profile.feature_count:
            raise RowCountMismatch()

        # 2. A NULL geometry matches no declared type, and D-63 requires
        # NOT NULL on the column before promotion -- naming the cause here
        # is more useful than letting 03-06's ALTER surface a raw error.
        if null_geom_count:
            raise GeometryTypeMismatch()

        # 3. SRID: exactly one value, and it must be the configured target.
        srids_seen = list(srids_seen or [])
        if len(srids_seen) != 1 or srids_seen[0] != policy.target_srid:
            raise SridMismatch()

        # 4. Geometry type and ZM dimensionality: exactly one of each,
        # matching the manifest's declaration. Compared via
        # _geometry_type_base_name (see normalize_declared_geometry_type's
        # docstring for why) so PostGIS's own inconsistent GeometryType()
        # suffix behavior never produces a false mismatch; ST_Zmflag is the
        # authoritative Z/M signal.
        expected_type, expected_zmflag = normalize_declared_geometry_type(
            manifest_layer.profile.geometry_type
        )
        expected_base = _geometry_type_base_name(expected_type)
        geometry_types_seen = list(geometry_types_seen or [])
        zmflags_seen = list(zmflags_seen or [])
        if (
            len(geometry_types_seen) != 1
            or _geometry_type_base_name(geometry_types_seen[0]) != expected_base
        ):
            raise GeometryTypeMismatch()
        if len(zmflags_seen) != 1 or zmflags_seen[0] != expected_zmflag:
            raise GeometryTypeMismatch()

        # 5. Repair: a type-changing candidate blocks with nothing written;
        # otherwise repair, then re-check invalidity is actually zero before
        # ever committing the UPDATE.
        repaired_count = 0
        if invalid_count > 0:
            if type_changed_count > 0:
                raise GeometryRepairChangedType()
            repair_statement = build_repair_statement(
                staging_schema=policy.staging_schema,
                staging_table=staging_table,
            )
            try:
                with connection.cursor() as cursor:
                    cursor.execute(repair_statement)
                    repaired_count = cursor.rowcount
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL(
                            "SELECT COUNT(*) FROM {table} WHERE NOT ST_IsValid(geom)"
                        ).format(table=table_ref)
                    )
                    (remaining_invalid,) = cursor.fetchone()
            except Exception:
                raise LoadFailed() from None
            if remaining_invalid > 0:
                raise GeometryRepairIncomplete()
            connection.commit()

        # 6. Extent: reported, never blocking (D-56).
        extent = _parse_extent(extent_text)

        return LayerValidation(
            staging_table=staging_table,
            spatial=True,
            row_count=row_count,
            geometry_type=expected_type,
            srid=policy.target_srid,
            repaired_count=repaired_count,
            extent=extent,
        )
    except (
        RowCountMismatch,
        SridMismatch,
        GeometryTypeMismatch,
        GeometryRepairChangedType,
        GeometryRepairIncomplete,
        LoadFailed,
    ):
        raise
    except Exception:
        raise LoadFailed() from None
    finally:
        connection.close()


def secondary_index_columns(
    manifest_layer: ManifestLayer, policy: StagingPolicy
) -> tuple[str, ...]:
    """D-64: pure allowlist decision, no database. A manifest field
    "launders to" an allowlist entry when GDAL's ``LAUNDER=YES`` would fold
    it onto that entry -- here, comparing each declared field's name
    casefolded against ``policy.index_columns`` (already lowercase,
    D-58/``StagingPolicy.__post_init__``). Result order follows
    ``policy.index_columns``' own order, not field-declaration order, so it
    is deterministic and reproducible from the frozen manifest and policy
    alone. A layer declaring none of the allowlisted columns returns an
    empty tuple and this never raises. A non-spatial layer is treated
    identically -- the allowlist is about ordinary columns, not geometry."""

    declared = {field.name.casefold() for field in manifest_layer.profile.fields}
    return tuple(column for column in policy.index_columns if column in declared)


def apply_post_validation_ddl(
    *,
    validation: LayerValidation,
    manifest_layer: ManifestLayer,
    staging_table: str,
    policy: StagingPolicy,
    password: str,
) -> tuple[str, ...]:
    """D-62/D-63/D-64: constrain and index a staging table ``validate_layer``
    has already returned without raising, against a table ``ogr2ogr`` has
    already fully populated and then exited -- no concurrent writer, no
    reason to have built the index during the load.

    Everything here runs inside the one implicit transaction a fresh
    ``psycopg`` connection opens (``_connect`` never sets ``autocommit``):
    it commits once, at the end, or rolls back together on any failure, so
    Phase 4 can never see a half-constrained table (T-03-33). Any
    non-``StagingDdlFailed`` exception -- a real ``psycopg`` error -- is
    re-raised as the closed ``StagingDdlFailed`` with no driver text.

    Branches on ``validation.spatial`` (the same boolean the validation
    profile used, per D-57) rather than re-deriving it, so the two can never
    disagree: a non-spatial layer only gets the primary key and any
    allowlisted secondary index, never geometry-related DDL.

    Research Open Question 1 -- whether GDAL's PostgreSQL driver already
    creates a typed ``geometry(Type, SRID)`` column, or always a bare
    ``geometry`` column -- is answered here empirically by reading
    ``geometry_columns`` rather than assuming either answer, live-confirmed
    against the real 4,222,035-row ADDRESS staging table: GDAL's driver
    (``FID=gid``, known geometry type, known ``-t_srs``) already created
    both the primary key on ``gid`` and a fully typed ``geometry(Point,
    7899)`` column with no ``ALTER`` needed for either -- see this plan's
    SUMMARY for the full live record. A table whose column disagrees with
    what ``validate_layer`` already asserted (the two functions would then
    be reading different things) raises ``StagingDdlFailed`` rather than
    silently re-typing it.

    Returns the constraint and index names this call created, in creation
    order -- an empty tuple when every constraint GDAL's own load already
    satisfied and the manifest declares no allowlisted column."""

    table_ref = sql.Identifier(policy.staging_schema, staging_table)
    created: list[str] = []
    connection = _connect(policy, password)
    try:
        with connection.cursor() as cursor:
            # 1. Primary key on gid (D-63) -- unconditional unless GDAL's
            # own FID=gid load option already created one.
            cursor.execute(
                "SELECT 1 FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = %s AND t.relname = %s AND c.contype = 'p'",
                (policy.staging_schema, staging_table),
            )
            has_primary_key = cursor.fetchone() is not None
            if not has_primary_key:
                cursor.execute(
                    sql.SQL("ALTER TABLE {table} ADD PRIMARY KEY (gid)").format(
                        table=table_ref
                    )
                )
                created.append(f"{staging_table}_pkey")

            if validation.spatial:
                # 2. Typed geometry column with its SRID (D-63) --
                # conditionally, per Open Question 1: read geometry_columns,
                # never assume.
                cursor.execute(
                    "SELECT type, srid FROM geometry_columns "
                    "WHERE f_table_schema = %s AND f_table_name = %s "
                    "AND f_geometry_column = 'geom'",
                    (policy.staging_schema, staging_table),
                )
                row = cursor.fetchone()
                if row is None:
                    raise StagingDdlFailed()
                observed_type, observed_srid = row
                declared_type, _ = normalize_declared_geometry_type(
                    manifest_layer.profile.geometry_type
                )
                declared_base = _geometry_type_base_name(declared_type)

                if observed_type == "GEOMETRY":
                    # Bare, untyped column -- Open Question 1's "no" branch
                    # for this table.
                    needs_alter = True
                elif _geometry_type_base_name(observed_type) == declared_base:
                    needs_alter = observed_srid != policy.target_srid
                else:
                    # geometry_columns disagrees with what validate_layer
                    # already asserted -- the two read different things.
                    raise StagingDdlFailed()

                if needs_alter:
                    cursor.execute(
                        sql.SQL(
                            "ALTER TABLE {table} ALTER COLUMN geom "
                            "TYPE geometry({type}, {srid}) USING geom"
                        ).format(
                            table=table_ref,
                            type=sql.SQL(declared_type),
                            srid=sql.Literal(policy.target_srid),
                        )
                    )
                    created.append(f"{staging_table}_geom_typed")

                # 3. NOT NULL on the geometry column (D-63). 03-05 already
                # proved no row holds a NULL geometry; this makes the
                # constraint part of the published contract.
                cursor.execute(
                    sql.SQL(
                        "ALTER TABLE {table} ALTER COLUMN geom SET NOT NULL"
                    ).format(table=table_ref)
                )
                created.append(f"{staging_table}_geom_not_null")

                # 4. GiST index (D-62), built once over the populated
                # table, as an ordinary blocking CREATE INDEX inside this
                # same transaction -- the non-blocking online-build variant
                # is deliberately not used here: it cannot run inside a
                # transaction block, and there is no concurrent reader to
                # protect against in the first place.
                gist_index_name = f"{staging_table}_geom_gist"
                cursor.execute(
                    sql.SQL(
                        "CREATE INDEX {index} ON {table} USING GIST (geom)"
                    ).format(index=sql.Identifier(gist_index_name), table=table_ref)
                )
                created.append(gist_index_name)

            # 5. Secondary btree indexes from the allowlist (D-64) --
            # applies to spatial and non-spatial layers alike.
            for column in secondary_index_columns(manifest_layer, policy):
                index_name = f"{staging_table}_{column}_idx"
                cursor.execute(
                    sql.SQL("CREATE INDEX {index} ON {table} ({column})").format(
                        index=sql.Identifier(index_name),
                        table=table_ref,
                        column=sql.Identifier(column),
                    )
                )
                created.append(index_name)
        connection.commit()
    except StagingDdlFailed:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise StagingDdlFailed() from None
    finally:
        connection.close()

    return tuple(created)


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
    apply post-validation DDL -> emit, in the manifest's own order (D-42).
    One ``ogr2ogr`` invocation at a time -- sequentially, with no concurrent
    execution framework and no batching. On the first failure at any step
    for a layer, the original
    typed exception is re-raised unchanged (now carrying a ``staging_table``
    attribute so the operator's failure line can name the failing layer;
    ``LoadFailed`` additionally carries ``diagnostics_file``) and no later
    layer is attempted. A zero-layer manifest is unreachable in practice
    (Phase 2's ``DeliveryEmpty`` hard-stops before a manifest exists) but is
    still a no-op here, returning an empty tuple and raising nothing. Every
    emission is wrapped in ``read_mailbox._EmitOnce``, exactly as
    ``discover_order.run_discovery`` does, so a faulty sink can never turn a
    closed failure into a raw exception."""

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
        try:
            # Per-layer progress (research Pitfall 4's option (a)): emitted
            # before the ogr2ogr call, not derived from parsing its
            # terminal output.
            guard.emit(
                ProgressEvent.staging_layer_position(position=position, total=total)
            )
            dataset_path = (
                Path(manifest.run_directory) / layer.profile.dataset_relative_path
            )
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
            # staging_table_loaded is emitted here -- after the ogr2ogr
            # call succeeds, as the plan requires -- using validate_layer's
            # own counted row_count rather than the manifest's declared
            # feature_count, so the event always reports what the database
            # actually holds, not merely what was expected.
            guard.emit(
                SuccessEvent.staging_table_loaded(
                    order_id=manifest.order_id,
                    target_table=layer.target_table,
                    staging_table=staging_table,
                    row_count=validation.row_count,
                )
            )
            # D-62/D-63: post-validation DDL goes after validation, never
            # before -- an index over a populated table beats maintaining
            # one during the COPY, and the typed column enforces at
            # database level exactly what validation just asserted.
            ddl_objects_created = apply_post_validation_ddl(
                validation=validation,
                manifest_layer=layer,
                staging_table=staging_table,
                policy=policy,
                password=password,
            )
            guard.emit(
                SuccessEvent.staging_layer_validated(
                    order_id=manifest.order_id,
                    staging_table=staging_table,
                    spatial=validation.spatial,
                    row_count=validation.row_count,
                    geometry_type=validation.geometry_type,
                    srid=validation.srid,
                    repaired_count=validation.repaired_count,
                    extent=validation.extent,
                    ddl_objects_created=ddl_objects_created,
                )
            )
        except StagingFailure as error:
            # Names the failing layer for the operator without carrying any
            # driver/subprocess/SQL text -- staging_table is already a safe
            # scalar (evidence._require_target_table).
            error.staging_table = staging_table
            raise
        validations.append(validation)

    return tuple(validations)
