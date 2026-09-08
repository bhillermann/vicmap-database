"""Closed, disclosure-safe JSON Lines evidence for artifact acquisition."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import TextIO


_HEX_16 = re.compile(r"[0-9a-f]{16}")
_HEX_64 = re.compile(r"[0-9a-f]{64}")
_ORDER_ID = re.compile(r"[A-Za-z0-9]+")
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")


class Stage(str, Enum):
    CONFIGURATION = "configuration"
    GRAPH_AUTHENTICATION = "graph_authentication"
    MAILBOX_ACCESS = "mailbox_access"
    SCAN = "scan"
    CANDIDATE = "candidate"
    DOWNLOAD = "download"
    ARTIFACT_WRITE = "artifact_write"
    INTERNAL = "internal"


class ReasonCode(str, Enum):
    CONFIG_INVALID = "config_invalid"
    GRAPH_AUTH_FAILED = "graph_auth_failed"
    MAILBOX_ACCESS_FAILED = "mailbox_access_failed"
    GRAPH_SCAN_FAILED = "graph_scan_failed"
    CANDIDATE_NONE = "candidate_none"
    CANDIDATE_AMBIGUOUS = "candidate_ambiguous"
    ORDER_ID_MISMATCH = "order_id_mismatch"
    DOWNLOAD_URL_REJECTED = "download_url_rejected"
    DOWNLOAD_REDIRECT_REJECTED = "download_redirect_rejected"
    DOWNLOAD_EXPIRED_OR_MISSING = "download_expired_or_missing"
    DOWNLOAD_TIMEOUT = "download_timeout"
    DOWNLOAD_TOO_LARGE = "download_too_large"
    DOWNLOAD_HTTP_FAILED = "download_http_failed"
    ARTIFACT_WRITE_FAILED = "artifact_write_failed"
    INTERNAL_FAILURE = "internal_failure"


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
    }
)


def fingerprint(value: str) -> str:
    """Return the fixed 16-hex correlation fingerprint for one opaque value."""

    if not isinstance(value, str) or not value:
        raise ValueError("fingerprint input must be a non-empty string")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


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


def _require_fingerprint(value: str) -> str:
    if not isinstance(value, str) or _HEX_16.fullmatch(value) is None:
        raise ValueError("fingerprint is not a 16-character lowercase hex value")
    return value


def _require_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("byte_count must be a non-negative integer")
    return value


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
                "message_fingerprint": fingerprint(graph_message_id),
            }
        )

    @classmethod
    def download_target(
        cls, *, approved_hostname: str, path_fingerprint: str
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
                "path_fingerprint": _require_fingerprint(path_fingerprint),
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


class SafeFailure(_SafeEvent):
    def __init__(
        self,
        reason: ReasonCode,
        *,
        order_id: str | None = None,
        message_fingerprint: str | None = None,
        path_fingerprint: str | None = None,
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
            fields["message_fingerprint"] = _require_fingerprint(message_fingerprint)
        if path_fingerprint is not None:
            fields["path_fingerprint"] = _require_fingerprint(path_fingerprint)
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
