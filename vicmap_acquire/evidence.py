"""Closed, disclosure-safe JSON Lines evidence for artifact acquisition."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
import sys
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import TextIO


_HEX_LOWER = re.compile(r"[0-9a-f]+")
_HEX_64 = re.compile(r"[0-9a-f]{64}")
_ORDER_ID = re.compile(r"[A-Za-z0-9]+")
# WR-06: mirrors staging._HOSTNAME/read_mailbox._HOSTNAME exactly (253-byte
# total bound, per-label DNS structure) rather than the looser pattern this
# module used to carry -- this is the last safety net before an
# operator-facing value is written into the event stream, so it should not
# be looser than the validators that, today, are its only callers.
_HOST = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)
_MIN_FINGERPRINT_HEX_CHARS = 8
_MAX_FINGERPRINT_HEX_CHARS = 64

# D-61: server-controlled identity text (version(), PostGIS_Full_Version())
# rendered in clear, bounded to printable ASCII with no control characters
# so a hostile or malformed server banner cannot inject newlines into the
# JSON Lines stream or smuggle unbounded text into operator output. 1024 (not
# the original 200) is the bound: a real PostGIS_Full_Version() string on a
# live PostgreSQL 17.5/PostGIS 3.5.2 server observed during 03-04's live
# verification is 345 characters (it enumerates GEOS/PROJ/LIBXML/LIBJSON/
# LIBPROTOBUF/WAGYU versions plus PROJ's writable-directory and DB paths) --
# 200 rejected genuine server output as a raw ValueError, not a closed
# failure. 1024 stays a finite bound, just one wide enough for real banners.
_SERVER_VERSION_TEXT = re.compile(r"[ -~]{1,1024}")
_GEOMETRY_TYPE_NAME = re.compile(r"[A-Z]{1,32}")

# D-43: staging.diagnostics_path's own deterministic shape
# ("db_load_{staging_table}.stderr"), where {staging_table} is already a
# safe scalar (_TARGET_TABLE below). This is a bare file *name*, never a
# path -- SafeFailure.diagnostics_file exists precisely so the operator's
# failure line can name the file without carrying its directory or content.
_DIAGNOSTICS_FILENAME = re.compile(r"db_load_[a-z][a-z0-9_]*\.stderr")


def _require_fingerprint_length(expected_length: int) -> int:
    if (
        isinstance(expected_length, bool)
        or not isinstance(expected_length, int)
        or not (_MIN_FINGERPRINT_HEX_CHARS <= expected_length <= _MAX_FINGERPRINT_HEX_CHARS)
    ):
        raise ValueError(
            "fingerprint length must be an int between "
            f"{_MIN_FINGERPRINT_HEX_CHARS} and {_MAX_FINGERPRINT_HEX_CHARS}"
        )
    return expected_length


class Stage(str, Enum):
    CONFIGURATION = "configuration"
    GRAPH_AUTHENTICATION = "graph_authentication"
    MAILBOX_ACCESS = "mailbox_access"
    SCAN = "scan"
    CANDIDATE = "candidate"
    DOWNLOAD = "download"
    ARTIFACT_WRITE = "artifact_write"
    INTERNAL = "internal"
    ARTIFACT_VERIFY = "artifact_verify"
    EXTRACTION = "extraction"
    DISCOVERY = "discovery"
    NAMING = "naming"
    MANIFEST = "manifest"
    DB_PREFLIGHT = "db_preflight"
    DB_LOAD = "db_load"
    DB_VALIDATION = "db_validation"
    DB_STAGING_DDL = "db_staging_ddl"
    DB_AUDIT = "db_audit"
    DB_PUBLISH = "db_publish"
    DB_READER_VERIFY = "db_reader_verify"
    # D-91: summary assembly and write boundary (05.1). The success event
    # SuccessEvent.publication_summary shares this string as its "event"
    # value, never its "stage" -- no literal key collision in either
    # rendered JSON object.
    PUBLICATION_SUMMARY = "publication_summary"


class ReasonCode(str, Enum):
    CONFIG_INVALID = "config_invalid"
    GRAPH_AUTH_FAILED = "graph_auth_failed"
    MAILBOX_ACCESS_FAILED = "mailbox_access_failed"
    GRAPH_SCAN_FAILED = "graph_scan_failed"
    CANDIDATE_NONE = "candidate_none"
    CANDIDATE_AMBIGUOUS = "candidate_ambiguous"
    ORDER_ID_MISMATCH = "order_id_mismatch"
    ORIGIN_UNAUTHENTICATED = "origin_unauthenticated"
    DOWNLOAD_URL_REJECTED = "download_url_rejected"
    DOWNLOAD_REDIRECT_REJECTED = "download_redirect_rejected"
    DOWNLOAD_EXPIRED_OR_MISSING = "download_expired_or_missing"
    DOWNLOAD_TIMEOUT = "download_timeout"
    DOWNLOAD_TOO_LARGE = "download_too_large"
    DOWNLOAD_HTTP_FAILED = "download_http_failed"
    ARTIFACT_WRITE_FAILED = "artifact_write_failed"
    INTERNAL_FAILURE = "internal_failure"
    ARTIFACT_CHECKSUM_MISMATCH = "artifact_checksum_mismatch"
    PROVENANCE_UNAVAILABLE = "provenance_unavailable"
    ARCHIVE_TRAVERSAL_REJECTED = "archive_traversal_rejected"
    ARCHIVE_UNSAFE_MEMBER_REJECTED = "archive_unsafe_member_rejected"
    ARCHIVE_CEILING_EXCEEDED = "archive_ceiling_exceeded"
    ARCHIVE_UNREADABLE = "archive_unreadable"
    RUN_DIRECTORY_WRITE_FAILED = "run_directory_write_failed"
    UNSUPPORTED_FORMAT = "unsupported_format"
    DELIVERY_EMPTY = "delivery_empty"
    LAYER_UNREADABLE = "layer_unreadable"
    LAYER_EMPTY = "layer_empty"
    GEOMETRY_TYPE_UNRESOLVED = "geometry_type_unresolved"
    CRS_UNRESOLVED = "crs_unresolved"
    LAYER_SCHEMA_INCOMPLETE = "layer_schema_incomplete"
    TABLE_NAME_INVALID = "table_name_invalid"
    TABLE_NAME_COLLISION = "table_name_collision"
    MANIFEST_WRITE_FAILED = "manifest_write_failed"
    MANIFEST_UNREADABLE = "manifest_unreadable"
    MANIFEST_DIGEST_MISMATCH = "manifest_digest_mismatch"
    DB_CONNECTION_FAILED = "db_connection_failed"
    DB_POSTGIS_UNAVAILABLE = "db_postgis_unavailable"
    DB_TARGET_SRID_UNRESOLVED = "db_target_srid_unresolved"
    DB_PRIVILEGE_DENIED = "db_privilege_denied"
    DB_LOAD_FAILED = "db_load_failed"
    DB_VALIDATION_QUERY_FAILED = "db_validation_query_failed"
    DB_ROW_COUNT_MISMATCH = "db_row_count_mismatch"
    DB_SRID_MISMATCH = "db_srid_mismatch"
    DB_GEOMETRY_TYPE_MISMATCH = "db_geometry_type_mismatch"
    DB_GEOMETRY_REPAIR_CHANGED_TYPE = "db_geometry_repair_changed_type"
    DB_GEOMETRY_REPAIR_INCOMPLETE = "db_geometry_repair_incomplete"
    DB_STAGING_DDL_FAILED = "db_staging_ddl_failed"
    DB_AUDIT_PRIVILEGE_DENIED = "db_audit_privilege_denied"
    DB_AUDIT_RECORD_FAILED = "db_audit_record_failed"
    PUB_VALIDATION_MISSING = "pub_validation_missing"
    PUB_PROMOTION_FAILED = "pub_promotion_failed"
    READER_ROLE_UNAVAILABLE = "reader_role_unavailable"
    READER_VERIFICATION_FAILED = "reader_verification_failed"
    READER_WRITE_NOT_DENIED = "reader_write_not_denied"
    # 05.1 (D-87/D-90/D-91): the resume-path vocabulary extension.
    PUB_GENERATION_SUPERSEDED = "pub_generation_superseded"
    PUB_GENERATION_AMBIGUOUS = "pub_generation_ambiguous"
    DB_AUDIT_READ_FAILED = "db_audit_read_failed"
    PUB_SUMMARY_FAILED = "pub_summary_failed"


_FAILURE_POLICY = MappingProxyType(
    {
        ReasonCode.CONFIG_INVALID: (
            Stage.CONFIGURATION,
            "review_non_secret_configuration",
        ),
        ReasonCode.GRAPH_AUTH_FAILED: (
            Stage.GRAPH_AUTHENTICATION,
            "verify_application_credentials_and_permissions",
        ),
        ReasonCode.MAILBOX_ACCESS_FAILED: (
            Stage.MAILBOX_ACCESS,
            "verify_mailbox_identity_and_resource_scope",
        ),
        ReasonCode.GRAPH_SCAN_FAILED: (
            Stage.SCAN,
            "retry_bounded_mailbox_scan",
        ),
        ReasonCode.CANDIDATE_NONE: (
            Stage.CANDIDATE,
            "request_a_current_ready_delivery",
        ),
        ReasonCode.CANDIDATE_AMBIGUOUS: (
            Stage.CANDIDATE,
            "review_ready_message_against_policy",
        ),
        ReasonCode.ORDER_ID_MISMATCH: (
            Stage.CANDIDATE,
            "review_order_identity_without_bypassing_policy",
        ),
        ReasonCode.ORIGIN_UNAUTHENTICATED: (
            Stage.CANDIDATE,
            "review_message_authentication_without_bypassing_policy",
        ),
        ReasonCode.DOWNLOAD_URL_REJECTED: (
            Stage.DOWNLOAD,
            "review_target_without_broadening_allowlist",
        ),
        ReasonCode.DOWNLOAD_REDIRECT_REJECTED: (
            Stage.DOWNLOAD,
            "review_redirect_without_broadening_allowlist",
        ),
        ReasonCode.DOWNLOAD_EXPIRED_OR_MISSING: (
            Stage.DOWNLOAD,
            "request_a_fresh_delivery",
        ),
        ReasonCode.DOWNLOAD_TIMEOUT: (
            Stage.DOWNLOAD,
            "retry_when_transport_is_available",
        ),
        ReasonCode.DOWNLOAD_TOO_LARGE: (
            Stage.DOWNLOAD,
            "review_artifact_size_policy",
        ),
        ReasonCode.DOWNLOAD_HTTP_FAILED: (
            Stage.DOWNLOAD,
            "retry_or_request_a_fresh_delivery",
        ),
        ReasonCode.ARTIFACT_WRITE_FAILED: (
            Stage.ARTIFACT_WRITE,
            "review_destination_and_preserve_existing_artifact",
        ),
        ReasonCode.INTERNAL_FAILURE: (
            Stage.INTERNAL,
            "review_safe_diagnostics_and_retry",
        ),
        ReasonCode.ARTIFACT_CHECKSUM_MISMATCH: (
            Stage.ARTIFACT_VERIFY,
            "request_a_fresh_delivery",
        ),
        ReasonCode.PROVENANCE_UNAVAILABLE: (
            Stage.ARTIFACT_VERIFY,
            "supply_phase_one_provenance_before_retrying",
        ),
        ReasonCode.ARCHIVE_TRAVERSAL_REJECTED: (
            Stage.EXTRACTION,
            "review_delivery_without_bypassing_extraction_guards",
        ),
        ReasonCode.ARCHIVE_UNSAFE_MEMBER_REJECTED: (
            Stage.EXTRACTION,
            "review_delivery_without_bypassing_extraction_guards",
        ),
        ReasonCode.ARCHIVE_CEILING_EXCEEDED: (
            Stage.EXTRACTION,
            "review_extraction_ceiling_policy",
        ),
        ReasonCode.ARCHIVE_UNREADABLE: (
            Stage.EXTRACTION,
            "request_a_fresh_delivery",
        ),
        ReasonCode.RUN_DIRECTORY_WRITE_FAILED: (
            Stage.EXTRACTION,
            "review_run_root_and_preserve_existing_runs",
        ),
        ReasonCode.UNSUPPORTED_FORMAT: (
            Stage.DISCOVERY,
            "review_supported_formats_without_broadening_allowlist",
        ),
        ReasonCode.DELIVERY_EMPTY: (
            Stage.DISCOVERY,
            "request_a_fresh_delivery",
        ),
        ReasonCode.LAYER_UNREADABLE: (
            Stage.DISCOVERY,
            "request_a_fresh_delivery",
        ),
        ReasonCode.LAYER_EMPTY: (
            Stage.DISCOVERY,
            "request_a_fresh_delivery",
        ),
        ReasonCode.GEOMETRY_TYPE_UNRESOLVED: (
            Stage.DISCOVERY,
            "request_a_fresh_delivery",
        ),
        ReasonCode.CRS_UNRESOLVED: (
            Stage.DISCOVERY,
            "request_a_fresh_delivery",
        ),
        ReasonCode.LAYER_SCHEMA_INCOMPLETE: (
            Stage.DISCOVERY,
            "request_a_fresh_delivery",
        ),
        ReasonCode.TABLE_NAME_INVALID: (
            Stage.NAMING,
            "review_layer_and_dataset_names_without_bypassing_normalization",
        ),
        ReasonCode.TABLE_NAME_COLLISION: (
            Stage.NAMING,
            "narrow_the_order_or_configure_a_crs_format_preference",
        ),
        ReasonCode.MANIFEST_WRITE_FAILED: (
            Stage.MANIFEST,
            "review_run_directory_permissions_and_retry",
        ),
        ReasonCode.MANIFEST_UNREADABLE: (
            Stage.MANIFEST,
            "regenerate_the_order_manifest",
        ),
        ReasonCode.MANIFEST_DIGEST_MISMATCH: (
            Stage.MANIFEST,
            "regenerate_the_order_manifest",
        ),
        ReasonCode.DB_CONNECTION_FAILED: (
            Stage.DB_PREFLIGHT,
            "verify_database_service_and_non_secret_connection_policy",
        ),
        ReasonCode.DB_POSTGIS_UNAVAILABLE: (
            Stage.DB_PREFLIGHT,
            "enable_the_postgis_extension_in_the_target_database",
        ),
        ReasonCode.DB_TARGET_SRID_UNRESOLVED: (
            Stage.DB_PREFLIGHT,
            "review_configured_target_srid",
        ),
        ReasonCode.DB_PRIVILEGE_DENIED: (
            Stage.DB_PREFLIGHT,
            "run_the_documented_provisioning_script_as_superuser",
        ),
        ReasonCode.DB_LOAD_FAILED: (
            Stage.DB_LOAD,
            "review_the_named_loader_diagnostic_file",
        ),
        ReasonCode.DB_VALIDATION_QUERY_FAILED: (
            Stage.DB_VALIDATION,
            "retry_validation_or_review_staging_table_directly",
        ),
        ReasonCode.DB_ROW_COUNT_MISMATCH: (
            Stage.DB_VALIDATION,
            "recheck_source_layer_against_manifest_feature_count",
        ),
        ReasonCode.DB_SRID_MISMATCH: (
            Stage.DB_VALIDATION,
            "review_configured_target_srid",
        ),
        ReasonCode.DB_GEOMETRY_TYPE_MISMATCH: (
            Stage.DB_VALIDATION,
            "review_declared_geometry_type",
        ),
        ReasonCode.DB_GEOMETRY_REPAIR_CHANGED_TYPE: (
            Stage.DB_VALIDATION,
            "review_source_geometry_before_reloading",
        ),
        ReasonCode.DB_GEOMETRY_REPAIR_INCOMPLETE: (
            Stage.DB_VALIDATION,
            "review_source_geometry_before_reloading",
        ),
        ReasonCode.DB_STAGING_DDL_FAILED: (
            Stage.DB_STAGING_DDL,
            "review_the_named_loader_diagnostic_file",
        ),
        # D-68/D-70: the DB_AUDIT boundary covers both the Phase 3 backfill
        # write and the Phase 4 gate read against vicmap_audit.
        ReasonCode.DB_AUDIT_PRIVILEGE_DENIED: (
            Stage.DB_AUDIT,
            "run_the_documented_provisioning_script_as_superuser",
        ),
        ReasonCode.DB_AUDIT_RECORD_FAILED: (
            Stage.DB_AUDIT,
            "retry_recording_validation_or_review_audit_schema",
        ),
        ReasonCode.PUB_VALIDATION_MISSING: (
            Stage.DB_AUDIT,
            "stage_and_validate_every_order_layer_before_publishing",
        ),
        # D-77 (EVID-02): the single promote/drop/rename/grant transaction
        # boundary -- any failure inside it (DDL error, name-discovery
        # mismatch, grant failure) surfaces here.
        ReasonCode.PUB_PROMOTION_FAILED: (
            Stage.DB_PUBLISH,
            "review_the_named_publish_boundary_and_retry",
        ),
        # D-74: the DB_READER_VERIFY boundary is the post-commit reader-role
        # proof -- READER_WRITE_NOT_DENIED carries the phase's most urgent
        # hint (immediate revocation, never a routine retry) because it
        # signals a broken grant model (T-04-07).
        ReasonCode.READER_ROLE_UNAVAILABLE: (
            Stage.DB_READER_VERIFY,
            "provision_the_reader_role_and_set_its_password",
        ),
        ReasonCode.READER_VERIFICATION_FAILED: (
            Stage.DB_READER_VERIFY,
            "review_reader_grants_and_published_tables",
        ),
        ReasonCode.READER_WRITE_NOT_DENIED: (
            Stage.DB_READER_VERIFY,
            "revoke_reader_write_immediately_grant_model_is_broken",
        ),
        # D-87: order-level classification (D-86) fail-closed outcomes.
        # Superseded means this run DID publish, but the live table has
        # since been replaced; ambiguous means the live state's provenance
        # cannot be proven at all. Both stage a fresh run, never a retry.
        ReasonCode.PUB_GENERATION_SUPERSEDED: (
            Stage.DB_PUBLISH,
            "nothing_to_resume_stage_a_fresh_run",
        ),
        ReasonCode.PUB_GENERATION_AMBIGUOUS: (
            Stage.DB_PUBLISH,
            "inspect_vicmap_and_vicmap_audit_then_stage_a_fresh_run",
        ),
        # D-90: any non-privilege vicmap_audit/catalog read failure during
        # classification or a post-commit re-read -- never pub_promotion_failed.
        ReasonCode.DB_AUDIT_READ_FAILED: (
            Stage.DB_AUDIT,
            "retry_audit_read_or_review_audit_schema",
        ),
        # D-91: the summary assembly and write boundary, replacing the
        # former fall-through to internal_failure.
        ReasonCode.PUB_SUMMARY_FAILED: (
            Stage.PUBLICATION_SUMMARY,
            "review_the_run_directory_then_rerun_publish_to_resume",
        ),
    }
)


# D-57: a non-spatial layer's geometry, SRID, and extent checks are recorded
# as this exact literal -- never as passed.
NOT_APPLICABLE = "not_applicable"


def fingerprint(value: str, expected_length: int = 16) -> str:
    """Return the ``expected_length``-hex correlation fingerprint for one value."""

    if not isinstance(value, str) or not value:
        raise ValueError("fingerprint input must be a non-empty string")
    expected_length = _require_fingerprint_length(expected_length)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:expected_length]


def mask_sender(sender: str) -> str:
    """Mask only the local part of one syntactically bounded sender address."""

    if not isinstance(sender, str) or sender.count("@") != 1:
        raise ValueError("sender must be one email address")
    local, domain = sender.split("@", 1)
    if not local or not domain or any(character.isspace() for character in sender):
        raise ValueError("sender must be one email address")
    if len(local) <= 2:
        masked_local = local[:1] + "*" * max(1, len(local) - 1)
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain.casefold()}"


def reason_stage_vocabulary() -> dict[str, str]:
    """Return a reviewable copy of the complete closed reason/stage mapping."""

    return {reason.value: stage.value for reason, (stage, _) in _FAILURE_POLICY.items()}


def remediation_hint(reason: ReasonCode) -> str:
    if not isinstance(reason, ReasonCode):
        raise TypeError("reason must be a ReasonCode")
    return _FAILURE_POLICY[reason][1]


def _require_order_id(value: str) -> str:
    if not isinstance(value, str) or _ORDER_ID.fullmatch(value) is None:
        raise ValueError("order_id is not a safe scalar")
    return value


def _require_fingerprint(value: str, expected_length: int = 16) -> str:
    expected_length = _require_fingerprint_length(expected_length)
    if (
        not isinstance(value, str)
        or len(value) != expected_length
        or _HEX_LOWER.fullmatch(value) is None
    ):
        raise ValueError(
            f"fingerprint is not a {expected_length}-character lowercase hex value"
        )
    return value


def _require_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("byte_count must be a non-negative integer")
    return value


# WR-06: mirrors staging._identifier's 63-byte bound (PostgreSQL's own
# NAMEDATALEN-1 limit) rather than the previously unbounded pattern.
_TARGET_TABLE = re.compile(r"[a-z][a-z0-9_]{0,62}")


def _require_target_table(value: str) -> str:
    if not isinstance(value, str) or _TARGET_TABLE.fullmatch(value) is None:
        raise ValueError("target table name is not a safe scalar")
    return value


def _require_diagnostics_filename(value: str) -> str:
    if not isinstance(value, str) or _DIAGNOSTICS_FILENAME.fullmatch(value) is None:
        raise ValueError("diagnostics file name is not a safe scalar")
    return value


def _require_server_version(value: str) -> str:
    if not isinstance(value, str) or _SERVER_VERSION_TEXT.fullmatch(value) is None:
        raise ValueError("server version text is not a safe scalar")
    return value


def _require_port(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= 65535):
        raise ValueError("port must be an int between 1 and 65535")
    return value


def _require_database_host(value: str) -> str:
    if isinstance(value, str) and _HOST.fullmatch(value) is not None:
        return value
    try:
        ipaddress.ip_address(value)
    except (ValueError, TypeError):
        raise ValueError("host is not a safe scalar") from None
    return value


def _require_geometry_type_or_not_applicable(value: str) -> str:
    if value == NOT_APPLICABLE:
        return value
    if not isinstance(value, str) or _GEOMETRY_TYPE_NAME.fullmatch(value) is None:
        raise ValueError("geometry type is not a safe scalar")
    return value


def _require_srid_or_not_applicable(value: int | str) -> int | str:
    if value == NOT_APPLICABLE:
        return value
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= 998999):
        raise ValueError("srid must be an int between 1 and 998999, or not_applicable")
    return value


def _require_count_or_not_applicable(value: int | str) -> int | str:
    if value == NOT_APPLICABLE:
        return value
    return _require_count(value)


def _require_extent_or_not_applicable(
    value: tuple[float, float, float, float] | str,
) -> tuple[float, float, float, float] | str:
    if value == NOT_APPLICABLE:
        return value
    if not isinstance(value, tuple) or len(value) != 4:
        raise ValueError("extent must be a 4-tuple, or not_applicable")
    xmin, ymin, xmax, ymax = value
    for scalar in (xmin, ymin, xmax, ymax):
        if (
            isinstance(scalar, bool)
            or not isinstance(scalar, (int, float))
            or not math.isfinite(scalar)
        ):
            raise ValueError("extent values must be finite numbers")
    if xmin > xmax or ymin > ymax:
        raise ValueError("extent must be ordered (xmin<=xmax, ymin<=ymax)")
    return (float(xmin), float(ymin), float(xmax), float(ymax))


def _require_utc_timestamp(value: datetime) -> str:
    """D-84: the same timezone-aware check ``SuccessEvent.candidate_selected``
    already applies, plus a fixed-width microsecond render -- the lossless
    precision contract against PostgreSQL ``timestamptz`` -- so a whole-second
    input still renders ``.000000+00:00`` rather than losing its trailing
    zeros to ``datetime.isoformat``'s default variable-width behaviour."""

    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


class _SafeEvent(Mapping[str, object]):
    __slots__ = ("_fields",)

    def __init__(self, fields: dict[str, object]) -> None:
        self._fields = MappingProxyType(dict(fields))

    def __getitem__(self, key: str) -> object:
        return self._fields[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._fields)

    def __len__(self) -> int:
        return len(self._fields)

    def __repr__(self) -> str:
        return repr(dict(self._fields))


class SuccessEvent(_SafeEvent):
    @classmethod
    def candidate_selected(
        cls,
        *,
        order_id: str,
        received_at: datetime,
        sender: str,
        graph_message_id: str,
        fingerprint_hex_chars: int = 16,
    ) -> "SuccessEvent":
        if (
            not isinstance(received_at, datetime)
            or received_at.tzinfo is None
            or received_at.utcoffset() is None
        ):
            raise ValueError("received_at must be timezone-aware")
        received_utc = received_at.astimezone(timezone.utc)
        return cls(
            {
                "event": "candidate_selected",
                "order_id": _require_order_id(order_id),
                "received_at": received_utc.isoformat(),
                "sender": mask_sender(sender),
                "message_fingerprint": fingerprint(
                    graph_message_id, fingerprint_hex_chars
                ),
            }
        )

    @classmethod
    def download_target(
        cls,
        *,
        approved_hostname: str,
        path_fingerprint: str,
        fingerprint_hex_chars: int = 16,
    ) -> "SuccessEvent":
        if (
            not isinstance(approved_hostname, str)
            or approved_hostname != approved_hostname.casefold()
            or _HOST.fullmatch(approved_hostname) is None
        ):
            raise ValueError("approved hostname is not a safe scalar")
        return cls(
            {
                "event": "download_target",
                "host": approved_hostname,
                "path_fingerprint": _require_fingerprint(
                    path_fingerprint, fingerprint_hex_chars
                ),
            }
        )

    @classmethod
    def artifact_finalized(cls, *, byte_count: int, sha256: str) -> "SuccessEvent":
        if not isinstance(sha256, str) or _HEX_64.fullmatch(sha256) is None:
            raise ValueError("sha256 is not a complete lowercase SHA-256 value")
        return cls(
            {
                "event": "artifact_finalized",
                "byte_count": _require_count(byte_count),
                "sha256": sha256,
            }
        )

    @classmethod
    def artifact_verified(
        cls, *, order_id: str, byte_count: int, sha256: str
    ) -> "SuccessEvent":
        if not isinstance(sha256, str) or _HEX_64.fullmatch(sha256) is None:
            raise ValueError("sha256 is not a complete lowercase SHA-256 value")
        return cls(
            {
                "event": "artifact_verified",
                "order_id": _require_order_id(order_id),
                "byte_count": _require_count(byte_count),
                "sha256": sha256,
            }
        )

    @classmethod
    def archive_extracted(
        cls,
        *,
        order_id: str,
        member_count: int,
        total_byte_count: int,
        run_path_fingerprint: str,
        fingerprint_hex_chars: int = 16,
    ) -> "SuccessEvent":
        return cls(
            {
                "event": "archive_extracted",
                "order_id": _require_order_id(order_id),
                "member_count": _require_count(member_count),
                "total_byte_count": _require_count(total_byte_count),
                "run_path_fingerprint": _require_fingerprint(
                    run_path_fingerprint, fingerprint_hex_chars
                ),
            }
        )

    @classmethod
    def manifest_completed(
        cls,
        *,
        order_id: str,
        layer_count: int,
        companion_count: int,
        target_tables: tuple[str, ...],
        manifest_sha256: str,
        run_path_fingerprint: str,
        fingerprint_hex_chars: int = 16,
    ) -> "SuccessEvent":
        if not isinstance(target_tables, tuple) or not all(
            isinstance(table, str) for table in target_tables
        ):
            raise ValueError("target_tables must be a tuple of strings")
        validated_tables = [_require_target_table(table) for table in target_tables]
        if not isinstance(manifest_sha256, str) or _HEX_64.fullmatch(manifest_sha256) is None:
            raise ValueError("manifest_sha256 is not a complete lowercase SHA-256 value")
        return cls(
            {
                "event": "manifest_completed",
                "order_id": _require_order_id(order_id),
                "layer_count": _require_count(layer_count),
                "companion_count": _require_count(companion_count),
                "target_tables": validated_tables,
                "manifest_sha256": manifest_sha256,
                "run_path_fingerprint": _require_fingerprint(
                    run_path_fingerprint, fingerprint_hex_chars
                ),
            }
        )

    @classmethod
    def database_identity(
        cls,
        *,
        host: str,
        port: int,
        dbname: str,
        role: str,
        server_version: str,
        postgis_version: str,
    ) -> "SuccessEvent":
        """D-61: connection identity shown in clear -- host is never fingerprinted."""

        return cls(
            {
                "event": "database_identity",
                "host": _require_database_host(host),
                "port": _require_port(port),
                "dbname": _require_target_table(dbname),
                "role": _require_target_table(role),
                "server_version": _require_server_version(server_version),
                "postgis_version": _require_server_version(postgis_version),
            }
        )

    @classmethod
    def staging_table_loaded(
        cls,
        *,
        order_id: str,
        target_table: str,
        staging_table: str,
        row_count: int,
    ) -> "SuccessEvent":
        return cls(
            {
                "event": "staging_table_loaded",
                "order_id": _require_order_id(order_id),
                "target_table": _require_target_table(target_table),
                "staging_table": _require_target_table(staging_table),
                "row_count": _require_count(row_count),
            }
        )

    @classmethod
    def staging_layer_validated(
        cls,
        *,
        order_id: str,
        staging_table: str,
        spatial: bool,
        row_count: int,
        geometry_type: str,
        srid: int | str,
        repaired_count: int | str,
        extent: tuple[float, float, float, float] | str,
        ddl_objects_created: tuple[str, ...] = (),
    ) -> "SuccessEvent":
        """D-57: a non-spatial layer reports geometry fields as ``not_applicable``,
        never as passed; a spatial layer must never carry ``not_applicable``."""

        if isinstance(spatial, bool) is False:
            raise ValueError("spatial must be a bool")
        four = (geometry_type, srid, repaired_count, extent)
        if spatial:
            if any(value == NOT_APPLICABLE for value in four):
                raise ValueError(
                    "a spatial layer cannot report not_applicable geometry fields"
                )
        else:
            if any(value != NOT_APPLICABLE for value in four):
                raise ValueError(
                    "a non-spatial layer must report not_applicable for all geometry fields"
                )

        validated_geometry_type = _require_geometry_type_or_not_applicable(geometry_type)
        validated_srid = _require_srid_or_not_applicable(srid)
        validated_repaired_count = _require_count_or_not_applicable(repaired_count)
        validated_extent = _require_extent_or_not_applicable(extent)
        rendered_extent = (
            validated_extent
            if validated_extent == NOT_APPLICABLE
            else list(validated_extent)
        )

        if not isinstance(ddl_objects_created, tuple) or not all(
            isinstance(name, str) for name in ddl_objects_created
        ):
            raise ValueError("ddl_objects_created must be a tuple of strings")
        validated_ddl_objects_created = [
            _require_target_table(name) for name in ddl_objects_created
        ]

        return cls(
            {
                "event": "staging_layer_validated",
                "order_id": _require_order_id(order_id),
                "staging_table": _require_target_table(staging_table),
                "spatial": spatial,
                "row_count": _require_count(row_count),
                "geometry_type": validated_geometry_type,
                "srid": validated_srid,
                "repaired_count": validated_repaired_count,
                "extent": rendered_extent,
                "ddl_objects_created": validated_ddl_objects_created,
            }
        )

    @classmethod
    def publication_summary(
        cls,
        *,
        order_id: str,
        message_fingerprint: str,
        artifact_sha256: str,
        manifest_sha256: str,
        layer_count: int,
        published_tables: tuple[str, ...],
        reader_tables_discovered: int,
        reader_spatial_query_row_count: int,
        reader_write_denied: bool,
        fingerprint_hex_chars: int = 16,
    ) -> "SuccessEvent":
        """D-75: the operator-visible, redacted publication summary (EVID-01).

        Links message -> checksum -> layers -> published tables -> reader
        verification through safe scalars only (fingerprints, checksums,
        counts, target-table names, booleans) -- never a raw id, path, or
        secret. The durable ``summary.json`` file assembled in 04-06 is the
        deliverable; this event is its everything-is-an-event mirror. This
        classmethod only defines and validates the vocabulary -- emitting or
        assembling the event is 04-06's job.
        """

        validated_order_id = _require_order_id(order_id)
        validated_message_fingerprint = _require_fingerprint(
            message_fingerprint, fingerprint_hex_chars
        )
        if not isinstance(artifact_sha256, str) or _HEX_64.fullmatch(artifact_sha256) is None:
            raise ValueError("artifact_sha256 is not a complete lowercase SHA-256 value")
        if not isinstance(manifest_sha256, str) or _HEX_64.fullmatch(manifest_sha256) is None:
            raise ValueError("manifest_sha256 is not a complete lowercase SHA-256 value")
        validated_layer_count = _require_count(layer_count)
        if not isinstance(published_tables, tuple) or not all(
            isinstance(table, str) for table in published_tables
        ):
            raise ValueError("published_tables must be a tuple of strings")
        validated_published_tables = [
            _require_target_table(table) for table in published_tables
        ]
        validated_reader_tables_discovered = _require_count(reader_tables_discovered)
        validated_reader_spatial_query_row_count = _require_count(
            reader_spatial_query_row_count
        )
        if isinstance(reader_write_denied, bool) is False:
            raise ValueError("reader_write_denied must be a bool")

        return cls(
            {
                "event": "publication_summary",
                "order_id": validated_order_id,
                "message_fingerprint": validated_message_fingerprint,
                "artifact_sha256": artifact_sha256,
                "manifest_sha256": manifest_sha256,
                "layer_count": validated_layer_count,
                "published_tables": validated_published_tables,
                "reader_tables_discovered": validated_reader_tables_discovered,
                "reader_spatial_query_row_count": (
                    validated_reader_spatial_query_row_count
                ),
                "reader_write_denied": reader_write_denied,
            }
        )


class ProgressEvent(_SafeEvent):
    @classmethod
    def from_counts(cls, byte_count: int, total_bytes: int | None) -> "ProgressEvent":
        count = _require_count(byte_count)
        fields: dict[str, object] = {
            "event": "download_progress",
            "byte_count": count,
        }
        if total_bytes is not None:
            total = _require_count(total_bytes)
            if total:
                fields["percent"] = min(1000, (count * 1000) // total) / 10
        return cls(fields)

    @classmethod
    def from_download_event(cls, event: Mapping[str, object]) -> "ProgressEvent":
        if not isinstance(event, Mapping) or set(event) not in (
            {"byte_count"},
            {"byte_count", "percent"},
        ):
            raise TypeError("download progress must use the closed downloader schema")
        count = _require_count(event["byte_count"])
        fields: dict[str, object] = {
            "event": "download_progress",
            "byte_count": count,
        }
        if "percent" in event:
            percent = event["percent"]
            if (
                isinstance(percent, bool)
                or not isinstance(percent, (int, float))
                or percent < 0
                or percent > 100
                or float(percent * 10).is_integer() is False
            ):
                raise ValueError("percent must be one exact decimal")
            fields["percent"] = percent
        return cls(fields)

    @classmethod
    def staging_layer_position(cls, *, position: int, total: int) -> "ProgressEvent":
        """Per-layer granularity around each loader child-process call (Pitfall 4a).

        This module never parses a loader's own terminal progress bar --
        that is a carriage-return-driven stream, not a structured one.
        """

        if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
            raise ValueError("total must be a positive integer")
        if (
            isinstance(position, bool)
            or not isinstance(position, int)
            or not (1 <= position <= total)
        ):
            raise ValueError("position must be an integer between 1 and total")
        percent = min(1000, (position * 1000) // total) / 10
        return cls(
            {
                "event": "staging_progress",
                "layer_position": position,
                "layer_total": total,
                "percent": percent,
            }
        )

    @classmethod
    def publication_resumed(
        cls, *, published_tables: tuple[str, ...], published_at: datetime
    ) -> "ProgressEvent":
        """D-84: a resumed run is visible on the JSON Lines stream. Carries
        no order id, run-directory path, or secret -- only the closed target
        table names this run resumed and the original commit's own
        ``published_at`` (D-82), rendered through ``_require_utc_timestamp``
        so a naive datetime can never reach the operator-visible stream."""

        if not isinstance(published_tables, tuple) or not published_tables:
            raise ValueError("published_tables must be a non-empty tuple of strings")
        validated_tables = [
            _require_target_table(table) for table in published_tables
        ]
        return cls(
            {
                "event": "publication_resumed",
                "published_tables": validated_tables,
                "published_at": _require_utc_timestamp(published_at),
            }
        )


class SafeFailure(_SafeEvent):
    def __init__(
        self,
        reason: ReasonCode,
        *,
        order_id: str | None = None,
        message_fingerprint: str | None = None,
        path_fingerprint: str | None = None,
        staging_table: str | None = None,
        diagnostics_file: str | None = None,
        fingerprint_hex_chars: int = 16,
    ) -> None:
        if not isinstance(reason, ReasonCode):
            raise TypeError("reason must be a ReasonCode")
        stage, hint = _FAILURE_POLICY[reason]
        fields: dict[str, object] = {
            "event": "failure",
            "stage": stage.value,
            "reason": reason.value,
            "hint": hint,
        }
        if order_id is not None:
            fields["order_id"] = _require_order_id(order_id)
        if message_fingerprint is not None:
            fields["message_fingerprint"] = _require_fingerprint(
                message_fingerprint, fingerprint_hex_chars
            )
        if path_fingerprint is not None:
            fields["path_fingerprint"] = _require_fingerprint(
                path_fingerprint, fingerprint_hex_chars
            )
        if staging_table is not None:
            # D-43: names the failing layer without carrying any
            # driver/subprocess/SQL text -- the same safe-scalar pattern
            # SuccessEvent.staging_table_loaded already uses.
            fields["staging_table"] = _require_target_table(staging_table)
        if diagnostics_file is not None:
            fields["diagnostics_file"] = _require_diagnostics_filename(
                diagnostics_file
            )
        super().__init__(fields)

    @property
    def reason(self) -> ReasonCode:
        return ReasonCode(self._fields["reason"])


def _render(event: _SafeEvent, expected_type: type[_SafeEvent], stream: TextIO) -> None:
    if type(event) is not expected_type:
        raise TypeError(f"event must be {expected_type.__name__}")
    stream.write(json.dumps(dict(event), sort_keys=True, separators=(",", ":")))
    stream.write("\n")


def render_success(event: SuccessEvent, *, stream: TextIO | None = None) -> None:
    _render(event, SuccessEvent, sys.stdout if stream is None else stream)


def render_progress(event: ProgressEvent, *, stream: TextIO | None = None) -> None:
    _render(event, ProgressEvent, sys.stdout if stream is None else stream)


def render_failure(event: SafeFailure, *, stream: TextIO | None = None) -> None:
    _render(event, SafeFailure, sys.stderr if stream is None else stream)
