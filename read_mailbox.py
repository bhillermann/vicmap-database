"""Guarded CLI and orchestration for trusted Vicmap artifact acquisition."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlsplit

import requests

from vicmap_acquire.candidates import CandidateError, recognize_candidate, select_candidate
from vicmap_acquire.download import (
    ArtifactProvenance,
    DownloadError,
    DownloadPolicy,
    DownloadResult,
    _normalize_url_prefix,
    download_artifact,
    write_provenance_sidecar,
)
from vicmap_acquire.graph import GraphError, GraphMailbox
from vicmap_acquire.origin import _AUTH_METHODS, OriginUnauthenticated
from vicmap_acquire.evidence import (
    ProgressEvent,
    ReasonCode,
    SafeFailure,
    SuccessEvent,
    fingerprint,
    render_failure,
    render_progress,
    render_success,
)


EventSink = Callable[[object], None]

_MAILBOX_KEYS = {
    "address",
    "folder",
    "allowed_senders",
    "allowed_order_ids",
    "lookback_days",
    "allow_order_id_mismatch",
    "required_authentication_results",
}
_DOWNLOAD_KEYS = {
    "allowed_hosts",
    "max_bytes",
    "connect_timeout_seconds",
    "read_timeout_seconds",
    "progress_interval_seconds",
    "max_redirects",
    "fingerprint_hex_chars",
    "output_dir",
    "allowed_url_prefixes",
}
_EXTRACTION_KEYS = {
    "run_dir",
    "max_total_bytes",
    "max_member_bytes",
    "max_member_count",
    "max_compression_ratio",
}
_DISCOVERY_KEYS = {
    "supported_formats",
    "ogrinfo_timeout_seconds",
}
_ORDER_ID = re.compile(r"[A-Za-z0-9]+")
_HOSTNAME = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)
_ALLOWED_OUTPUT_NAMES = frozenset({"artifacts"})
_ALLOWED_RUN_DIR_NAMES = frozenset({"runs"})
# D-34's initial single-entry format allowlist. Widening is a one-line change.
_RECOGNIZED_DISCOVERY_FORMATS = frozenset({"OpenFileGDB"})


@dataclass(frozen=True)
class AcquisitionConfig:
    mailbox: str
    folder: str
    allowed_senders: tuple[str, ...]
    allowed_order_ids: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    lookback_days: int
    max_bytes: int
    connect_timeout_seconds: int
    read_timeout_seconds: int
    progress_interval_seconds: int
    max_redirects: int
    fingerprint_hex_chars: int
    allow_order_id_mismatch: bool
    output_dir: Path
    required_authentication_results: tuple[str, ...]
    allowed_url_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class DiscoveryRunConfig:
    """Complete non-secret Phase 2 policy, reviewable in ``vicmap.toml``."""

    artifacts_dir: Path
    run_root: Path
    fingerprint_hex_chars: int
    allowed_order_ids: tuple[str, ...]
    max_total_bytes: int
    max_member_bytes: int
    max_member_count: int
    max_compression_ratio: int
    supported_formats: tuple[str, ...]
    ogrinfo_timeout_seconds: int


class AcquisitionFailure(RuntimeError):
    """A closed acquisition failure carrying no untrusted detail."""

    def __init__(self, reason: ReasonCode | str, *, reported: bool = False):
        self.failure = SafeFailure(_reason_code(reason))
        self.code = self.failure.reason.value
        self.reported = reported
        super().__init__(self.code)


_REASON_ALIASES = {
    "authentication_failed": ReasonCode.GRAPH_AUTH_FAILED,
}


def _reason_code(reason: ReasonCode | str) -> ReasonCode:
    if isinstance(reason, ReasonCode):
        return reason
    if isinstance(reason, str):
        if reason in _REASON_ALIASES:
            return _REASON_ALIASES[reason]
        try:
            return ReasonCode(reason)
        except ValueError:
            pass
    return ReasonCode.INTERNAL_FAILURE


class _EmitOnce:
    """Isolate evidence-sink I/O from acquisition control flow.

    ``emit`` returns immediately once the sink has failed -- a failed sink is
    never retried -- and otherwise calls the sink inside a guard that catches
    every exception except ``KeyboardInterrupt``/``SystemExit``, marking
    ``failed`` without inspecting or interpolating the caught exception's
    text. ``emit_failure`` delivers at most one failure event per run.
    """

    def __init__(self, sink: EventSink) -> None:
        self._sink = sink
        self.failed = False
        self.emitted_failure = False

    def emit(self, event: object) -> None:
        if self.failed:
            return
        try:
            self._sink(event)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.failed = True

    def emit_failure(self, failure: SafeFailure) -> None:
        if self.emitted_failure:
            return
        self.emitted_failure = True
        self.emit(failure)


def _emit_failure(
    guard: "_EmitOnce",
    reason: ReasonCode | str,
    *,
    fingerprint_hex_chars: int = 16,
) -> SafeFailure:
    failure = SafeFailure(
        _reason_code(reason), fingerprint_hex_chars=fingerprint_hex_chars
    )
    guard.emit_failure(failure)
    return failure


def _require_credentials(credentials: Mapping[str, str]) -> None:
    for name in ("O365_AUTH_ID", "O365_AUTH_SECRET", "TENANT_ID"):
        value = credentials.get(name)
        if not isinstance(value, str) or not value.strip():
            raise AcquisitionFailure("config_invalid")


def _suppress_dependency_logs() -> None:
    for logger_name in ("O365", "msal", "requests", "urllib3"):
        logging.getLogger(logger_name).setLevel(logging.CRITICAL + 1)


def _strict_string(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AcquisitionFailure("config_invalid")
    return value


def _string_list(value: object) -> tuple[str, ...]:
    """Extract a non-empty tuple of strict strings; no semantic checks here.

    Format, duplicate, and closed-set checks all live in
    ``validate_acquisition_policy`` -- the one configuration contract -- so a
    directly constructed ``AcquisitionConfig`` cannot bypass them.
    """

    if not isinstance(value, list) or not value:
        raise AcquisitionFailure("config_invalid")
    return tuple(_strict_string(item) for item in value)


def _strict_email(value: object) -> str:
    value = _strict_string(value)
    if value.count("@") != 1 or any(character.isspace() for character in value):
        raise AcquisitionFailure("config_invalid")
    return value


def _bounded_integer(value: object, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AcquisitionFailure("config_invalid")
    if value < minimum or value > maximum:
        raise AcquisitionFailure("config_invalid")
    return value


def validate_acquisition_policy(config: AcquisitionConfig) -> None:
    """The one configuration contract enforced identically by every entry point.

    Both ``load_config`` (the TOML path) and ``run_acquisition`` (the
    programmatic seam) call this and nothing else for semantic policy
    checks, so a directly constructed ``AcquisitionConfig`` cannot bypass a
    rule the TOML loader would have enforced. Every check here runs before
    any credential is read, any Graph adapter is constructed, any network
    call is made, and any directory is created.

    All string comparisons use ``str.casefold()`` on the exact code-point
    sequence; nothing here calls ``unicodedata.normalize``, so two values
    that are canonically equivalent but differ in code points are treated as
    different values, while two values differing only by ASCII case are
    treated as the same value.
    """

    _strict_email(config.mailbox)
    if config.folder != "Inbox":
        raise AcquisitionFailure("config_invalid")

    if not isinstance(config.allowed_senders, tuple) or not config.allowed_senders:
        raise AcquisitionFailure("config_invalid")
    for sender in config.allowed_senders:
        _strict_email(sender)
    if len({sender.casefold() for sender in config.allowed_senders}) != len(
        config.allowed_senders
    ):
        raise AcquisitionFailure("config_invalid")

    if not isinstance(config.allowed_order_ids, tuple) or not config.allowed_order_ids:
        raise AcquisitionFailure("config_invalid")
    for order_id in config.allowed_order_ids:
        if not isinstance(order_id, str) or _ORDER_ID.fullmatch(order_id) is None:
            raise AcquisitionFailure("config_invalid")
    if len(set(config.allowed_order_ids)) != len(config.allowed_order_ids):
        raise AcquisitionFailure("config_invalid")

    if not isinstance(config.allowed_hosts, tuple) or not config.allowed_hosts:
        raise AcquisitionFailure("config_invalid")
    for host in config.allowed_hosts:
        if (
            not isinstance(host, str)
            or host != host.casefold()
            or host.endswith(".")
            or _HOSTNAME.fullmatch(host) is None
        ):
            raise AcquisitionFailure("config_invalid")
    if len(set(config.allowed_hosts)) != len(config.allowed_hosts):
        raise AcquisitionFailure("config_invalid")

    if (
        not isinstance(config.allowed_url_prefixes, tuple)
        or not config.allowed_url_prefixes
    ):
        raise AcquisitionFailure("config_invalid")
    allowed_host_set = set(config.allowed_hosts)
    normalized_prefixes = []
    for prefix in config.allowed_url_prefixes:
        try:
            normalized = _normalize_url_prefix(prefix)
        except ValueError:
            raise AcquisitionFailure("config_invalid") from None
        prefix_host = urlsplit(normalized).hostname
        if prefix_host is None or prefix_host not in allowed_host_set:
            raise AcquisitionFailure("config_invalid")
        normalized_prefixes.append(normalized)
    if len(set(normalized_prefixes)) != len(normalized_prefixes):
        raise AcquisitionFailure("config_invalid")

    if (
        not isinstance(config.required_authentication_results, tuple)
        or not config.required_authentication_results
    ):
        raise AcquisitionFailure("config_invalid")
    for method in config.required_authentication_results:
        if (
            not isinstance(method, str)
            or method != method.casefold()
            or method not in _AUTH_METHODS
        ):
            raise AcquisitionFailure("config_invalid")
    if "dkim" not in config.required_authentication_results:
        raise AcquisitionFailure("config_invalid")
    if len(set(config.required_authentication_results)) != len(
        config.required_authentication_results
    ):
        raise AcquisitionFailure("config_invalid")

    _bounded_integer(config.lookback_days, 1, 3660)
    _bounded_integer(config.max_bytes, 1, 10 * 1024**4)
    _bounded_integer(config.connect_timeout_seconds, 1, 3600)
    _bounded_integer(config.read_timeout_seconds, 1, 3600)
    _bounded_integer(config.progress_interval_seconds, 1, 3600)
    _bounded_integer(config.max_redirects, 1, 20)
    _bounded_integer(config.fingerprint_hex_chars, 8, 64)

    if not isinstance(config.allow_order_id_mismatch, bool):
        raise AcquisitionFailure("config_invalid")

    if (
        not isinstance(config.output_dir, Path)
        or not config.output_dir.is_absolute()
        or config.output_dir.name not in _ALLOWED_OUTPUT_NAMES
        or config.output_dir.is_symlink()
        or (config.output_dir.exists() and not config.output_dir.is_dir())
    ):
        raise AcquisitionFailure("config_invalid")


def _positive_bounded_integer(value: object, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AcquisitionFailure("config_invalid")
    if value < minimum or value > maximum:
        raise AcquisitionFailure("config_invalid")
    return value


def validate_discovery_policy(config: DiscoveryRunConfig) -> None:
    """The one semantic contract for Phase 2's ceilings and format allowlist.

    Mirrors ``validate_acquisition_policy``: every check here runs before any
    archive is opened or any subprocess is spawned, so a directly constructed
    ``DiscoveryRunConfig`` cannot bypass a rule the TOML loader would have
    enforced.
    """

    if not isinstance(config.artifacts_dir, Path) or not config.artifacts_dir.is_absolute():
        raise AcquisitionFailure("config_invalid")

    if (
        not isinstance(config.run_root, Path)
        or not config.run_root.is_absolute()
        or config.run_root.name not in _ALLOWED_RUN_DIR_NAMES
    ):
        raise AcquisitionFailure("config_invalid")

    _positive_bounded_integer(config.fingerprint_hex_chars, 8, 64)

    if not isinstance(config.allowed_order_ids, tuple) or not config.allowed_order_ids:
        raise AcquisitionFailure("config_invalid")

    _positive_bounded_integer(config.max_total_bytes, 1, 10 * 1024**4)
    _positive_bounded_integer(config.max_member_bytes, 1, 10 * 1024**4)
    if config.max_member_bytes > config.max_total_bytes:
        raise AcquisitionFailure("config_invalid")
    _positive_bounded_integer(config.max_member_count, 1, 10_000_000)
    _positive_bounded_integer(config.max_compression_ratio, 1, 10_000)

    if (
        not isinstance(config.supported_formats, tuple)
        or not config.supported_formats
    ):
        raise AcquisitionFailure("config_invalid")
    for fmt in config.supported_formats:
        if not isinstance(fmt, str) or fmt not in _RECOGNIZED_DISCOVERY_FORMATS:
            raise AcquisitionFailure("config_invalid")
    if len(set(config.supported_formats)) != len(config.supported_formats):
        raise AcquisitionFailure("config_invalid")

    _positive_bounded_integer(config.ogrinfo_timeout_seconds, 1, 3600)


def run_acquisition(
    config: AcquisitionConfig,
    credentials: Mapping[str, str],
    graph_factory=None,
    session_factory=None,
    event_sink: EventSink = lambda event: None,
) -> DownloadResult:
    """Run the ordered Graph-to-artifact path through injectable I/O seams.

    Every event -- success, progress, and failure -- is routed through an
    ``_EmitOnce`` guard so a faulty ``event_sink`` can never turn a closed
    failure into a raw exception, and is never retried once it has failed.
    A sink fault on a success event means the operator saw nothing, so a
    guard failure detected after the final emission converts an otherwise
    successful run into ``AcquisitionFailure(INTERNAL_FAILURE)`` without
    touching the already-published artifact.
    """

    guard = _EmitOnce(event_sink)

    try:
        validate_acquisition_policy(config)
        _require_credentials(credentials)
        _suppress_dependency_logs()
        graph_factory = GraphMailbox if graph_factory is None else graph_factory
        session_factory = requests.Session if session_factory is None else session_factory
        graph = graph_factory(config=config, credentials=credentials)
        cutoff_utc = datetime.now(timezone.utc) - timedelta(days=config.lookback_days)
        candidates = []
        for metadata in graph.iter_metadata(cutoff_utc):
            candidate = recognize_candidate(
                metadata,
                lambda message_id=metadata.graph_message_id: graph.get_mime_content(
                    message_id
                ),
                allowed_senders=config.allowed_senders,
                allowed_order_ids=config.allowed_order_ids,
                allow_order_id_mismatch=config.allow_order_id_mismatch,
                required_authentication_results=config.required_authentication_results,
            )
            if candidate is not None:
                candidates.append(candidate)
        selected = select_candidate(candidates)
        message_fingerprint = fingerprint(
            selected.graph_message_id, config.fingerprint_hex_chars
        )
        guard.emit(
            SuccessEvent.candidate_selected(
                order_id=selected.order_id,
                received_at=selected.received_datetime_utc,
                sender=selected.sender,
                graph_message_id=selected.graph_message_id,
                fingerprint_hex_chars=config.fingerprint_hex_chars,
            )
        )

        download_policy = DownloadPolicy(
            allowed_hosts=config.allowed_hosts,
            allowed_url_prefixes=config.allowed_url_prefixes,
            max_bytes=config.max_bytes,
            connect_timeout_seconds=config.connect_timeout_seconds,
            stalled_read_timeout_seconds=config.read_timeout_seconds,
            progress_interval_seconds=config.progress_interval_seconds,
            max_redirects=config.max_redirects,
            fingerprint_hex_length=config.fingerprint_hex_chars,
        )
        result = download_artifact(
            selected.artifact_url,
            final_path=config.output_dir / f"Order_{selected.order_id}.zip",
            policy=download_policy,
            session_factory=session_factory,
            progress_sink=lambda progress: guard.emit(
                ProgressEvent.from_download_event(progress)
            ),
        )
        write_provenance_sidecar(
            result.path,
            order_id=selected.order_id,
            message_fingerprint=message_fingerprint,
            sha256=result.sha256,
            byte_count=result.byte_count,
        )
        guard.emit(
            SuccessEvent.artifact_verified(
                order_id=selected.order_id,
                byte_count=result.byte_count,
                sha256=result.sha256,
            )
        )
        guard.emit(
            SuccessEvent.download_target(
                approved_hostname=result.approved_hostname,
                path_fingerprint=result.path_fingerprint,
                fingerprint_hex_chars=config.fingerprint_hex_chars,
            )
        )
        guard.emit(
            SuccessEvent.artifact_finalized(
                byte_count=result.byte_count,
                sha256=result.sha256,
            )
        )
        if guard.failed:
            raise AcquisitionFailure(ReasonCode.INTERNAL_FAILURE)
        return result
    except AcquisitionFailure as error:
        if error.reported:
            raise
        failure = _emit_failure(
            guard,
            error.failure.reason,
            fingerprint_hex_chars=getattr(config, "fingerprint_hex_chars", 16),
        )
        raise AcquisitionFailure(failure.reason, reported=True) from None
    except (GraphError, CandidateError, DownloadError, OriginUnauthenticated) as error:
        failure = _emit_failure(
            guard,
            error.code,
            fingerprint_hex_chars=getattr(config, "fingerprint_hex_chars", 16),
        )
        raise AcquisitionFailure(failure.reason, reported=True) from None
    except Exception:
        failure = _emit_failure(
            guard,
            ReasonCode.INTERNAL_FAILURE,
            fingerprint_hex_chars=getattr(config, "fingerprint_hex_chars", 16),
        )
        raise AcquisitionFailure(failure.reason, reported=True) from None


def run_provenance(
    config: AcquisitionConfig,
    credentials: Mapping[str, str],
    graph_factory=None,
    event_sink: EventSink = lambda event: None,
) -> ArtifactProvenance:
    """Backfill a durable provenance sidecar for an artifact already on disk.

    Selects exactly as ``run_acquisition`` does -- identical authentication,
    bounded mailbox scan, candidate recognition, and exactly-one selection --
    but never constructs a ``DownloadPolicy`` and never calls
    ``download_artifact``. The artifact named by the selected order must
    already exist at ``config.output_dir / f"Order_{selected.order_id}.zip"``;
    this streams it in 1 MiB chunks to derive the true digest and byte count
    before writing the sidecar, so an operator holding an artifact acquired
    before this existed can produce one without re-downloading it.
    """

    guard = _EmitOnce(event_sink)

    try:
        validate_acquisition_policy(config)
        _require_credentials(credentials)
        _suppress_dependency_logs()
        graph_factory = GraphMailbox if graph_factory is None else graph_factory
        graph = graph_factory(config=config, credentials=credentials)
        cutoff_utc = datetime.now(timezone.utc) - timedelta(days=config.lookback_days)
        candidates = []
        for metadata in graph.iter_metadata(cutoff_utc):
            candidate = recognize_candidate(
                metadata,
                lambda message_id=metadata.graph_message_id: graph.get_mime_content(
                    message_id
                ),
                allowed_senders=config.allowed_senders,
                allowed_order_ids=config.allowed_order_ids,
                allow_order_id_mismatch=config.allow_order_id_mismatch,
                required_authentication_results=config.required_authentication_results,
            )
            if candidate is not None:
                candidates.append(candidate)
        selected = select_candidate(candidates)
        message_fingerprint = fingerprint(
            selected.graph_message_id, config.fingerprint_hex_chars
        )
        guard.emit(
            SuccessEvent.candidate_selected(
                order_id=selected.order_id,
                received_at=selected.received_datetime_utc,
                sender=selected.sender,
                graph_message_id=selected.graph_message_id,
                fingerprint_hex_chars=config.fingerprint_hex_chars,
            )
        )

        artifact_path = config.output_dir / f"Order_{selected.order_id}.zip"
        if not artifact_path.is_file():
            raise AcquisitionFailure(ReasonCode.PROVENANCE_UNAVAILABLE)

        digest = hashlib.sha256()
        byte_count = 0
        try:
            with open(artifact_path, "rb") as source:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    byte_count += len(chunk)
        except OSError:
            raise AcquisitionFailure(ReasonCode.PROVENANCE_UNAVAILABLE) from None

        provenance = ArtifactProvenance(
            order_id=selected.order_id,
            message_fingerprint=message_fingerprint,
            sha256=digest.hexdigest(),
            byte_count=byte_count,
        )
        write_provenance_sidecar(
            artifact_path,
            order_id=provenance.order_id,
            message_fingerprint=provenance.message_fingerprint,
            sha256=provenance.sha256,
            byte_count=provenance.byte_count,
        )
        guard.emit(
            SuccessEvent.artifact_verified(
                order_id=provenance.order_id,
                byte_count=provenance.byte_count,
                sha256=provenance.sha256,
            )
        )
        if guard.failed:
            raise AcquisitionFailure(ReasonCode.INTERNAL_FAILURE)
        return provenance
    except AcquisitionFailure as error:
        if error.reported:
            raise
        failure = _emit_failure(
            guard,
            error.failure.reason,
            fingerprint_hex_chars=getattr(config, "fingerprint_hex_chars", 16),
        )
        raise AcquisitionFailure(failure.reason, reported=True) from None
    except (GraphError, CandidateError, DownloadError, OriginUnauthenticated) as error:
        failure = _emit_failure(
            guard,
            error.code,
            fingerprint_hex_chars=getattr(config, "fingerprint_hex_chars", 16),
        )
        raise AcquisitionFailure(failure.reason, reported=True) from None
    except Exception:
        failure = _emit_failure(
            guard,
            ReasonCode.INTERNAL_FAILURE,
            fingerprint_hex_chars=getattr(config, "fingerprint_hex_chars", 16),
        )
        raise AcquisitionFailure(failure.reason, reported=True) from None


def load_config(path: Path) -> AcquisitionConfig:
    """Load non-secret policy shape from TOML, then apply the shared contract.

    This body performs only TOML shape work -- key-set equality, type
    extraction, ``Path`` construction, and output-root resolution. Every
    semantic check (format, closed sets, duplicates, bounds) is delegated to
    ``validate_acquisition_policy`` so there is exactly one place those rules
    exist. The complete four-section key set -- ``mailbox``, ``download``,
    ``extraction``, ``discovery`` -- must be present so one ``vicmap.toml`` is
    the project's whole non-secret policy; a file missing the Phase 2
    sections fails closed rather than half-loading.
    """

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        if set(raw) != {"mailbox", "download", "extraction", "discovery"}:
            raise AcquisitionFailure("config_invalid")
        mailbox = raw["mailbox"]
        download = raw["download"]
        if not isinstance(mailbox, dict) or set(mailbox) != _MAILBOX_KEYS:
            raise AcquisitionFailure("config_invalid")
        if not isinstance(download, dict) or set(download) != _DOWNLOAD_KEYS:
            raise AcquisitionFailure("config_invalid")

        address = _strict_string(mailbox["address"])
        folder = _strict_string(mailbox["folder"])
        senders = _string_list(mailbox["allowed_senders"])
        order_ids = _string_list(mailbox["allowed_order_ids"])
        required_authentication_results = _string_list(
            mailbox["required_authentication_results"]
        )
        hosts = _string_list(download["allowed_hosts"])
        allowed_url_prefixes = _string_list(download["allowed_url_prefixes"])

        output_value = _strict_string(download["output_dir"])
        configured_output = Path(output_value)
        if configured_output.is_absolute() or any(
            part in {"", ".", ".."} for part in configured_output.parts
        ):
            raise AcquisitionFailure("config_invalid")
        config_root = path.parent.resolve()
        output_dir = (config_root / configured_output).resolve()
        if output_dir != config_root and config_root not in output_dir.parents:
            raise AcquisitionFailure("config_invalid")

        config = AcquisitionConfig(
            mailbox=address,
            folder=folder,
            allowed_senders=senders,
            allowed_order_ids=order_ids,
            allowed_hosts=hosts,
            lookback_days=_bounded_integer(mailbox["lookback_days"], 1, 3660),
            max_bytes=_bounded_integer(download["max_bytes"], 1, 10 * 1024**4),
            connect_timeout_seconds=_bounded_integer(
                download["connect_timeout_seconds"], 1, 3600
            ),
            read_timeout_seconds=_bounded_integer(
                download["read_timeout_seconds"], 1, 3600
            ),
            progress_interval_seconds=_bounded_integer(
                download["progress_interval_seconds"], 1, 3600
            ),
            max_redirects=_bounded_integer(download["max_redirects"], 1, 20),
            fingerprint_hex_chars=_bounded_integer(
                download["fingerprint_hex_chars"], 8, 64
            ),
            allow_order_id_mismatch=mailbox["allow_order_id_mismatch"],
            output_dir=output_dir,
            required_authentication_results=required_authentication_results,
            allowed_url_prefixes=allowed_url_prefixes,
        )
        validate_acquisition_policy(config)
        return config
    except AcquisitionFailure:
        raise
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError):
        raise AcquisitionFailure("config_invalid") from None


def load_discovery_config(path: Path) -> DiscoveryRunConfig:
    """Load Phase 2's complete non-secret policy, then apply its contract.

    Reuses ``load_config`` for the shared TOML shape work and mailbox/download
    semantics (including the complete four-section key-set check), then
    performs only TOML shape work for ``[extraction]``/``[discovery]`` --
    key-set equality, type extraction, ``Path`` construction, and run-root
    resolution against the config file's parent -- before delegating every
    semantic check to ``validate_discovery_policy``, exactly as ``load_config``
    delegates to ``validate_acquisition_policy``.
    """

    acquisition_config = load_config(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        extraction = raw["extraction"]
        discovery = raw["discovery"]
        if not isinstance(extraction, dict) or set(extraction) != _EXTRACTION_KEYS:
            raise AcquisitionFailure("config_invalid")
        if not isinstance(discovery, dict) or set(discovery) != _DISCOVERY_KEYS:
            raise AcquisitionFailure("config_invalid")

        run_dir_value = _strict_string(extraction["run_dir"])
        configured_run_dir = Path(run_dir_value)
        if configured_run_dir.is_absolute() or any(
            part in {"", ".", ".."} for part in configured_run_dir.parts
        ):
            raise AcquisitionFailure("config_invalid")
        config_root = path.parent.resolve()
        run_root = (config_root / configured_run_dir).resolve()
        if run_root != config_root and config_root not in run_root.parents:
            raise AcquisitionFailure("config_invalid")

        supported_formats = _string_list(discovery["supported_formats"])

        config = DiscoveryRunConfig(
            artifacts_dir=acquisition_config.output_dir,
            run_root=run_root,
            fingerprint_hex_chars=acquisition_config.fingerprint_hex_chars,
            allowed_order_ids=acquisition_config.allowed_order_ids,
            max_total_bytes=_bounded_integer(
                extraction["max_total_bytes"], 1, 10 * 1024**4
            ),
            max_member_bytes=_bounded_integer(
                extraction["max_member_bytes"], 1, 10 * 1024**4
            ),
            max_member_count=_bounded_integer(
                extraction["max_member_count"], 1, 10_000_000
            ),
            max_compression_ratio=_bounded_integer(
                extraction["max_compression_ratio"], 1, 10_000
            ),
            supported_formats=supported_formats,
            ogrinfo_timeout_seconds=_bounded_integer(
                discovery["ogrinfo_timeout_seconds"], 1, 3600
            ),
        )
        validate_discovery_policy(config)
        return config
    except AcquisitionFailure:
        raise
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError):
        raise AcquisitionFailure("config_invalid") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire one trusted Vicmap artifact")
    parser.add_argument("--config", type=Path, default=Path("vicmap.toml"))
    parser.add_argument(
        "--provenance-only",
        action="store_true",
        help=(
            "Backfill the provenance sidecar for an artifact already on disk "
            "instead of downloading a new one."
        ),
    )
    args = parser.parse_args(argv)

    def render_event(event: object) -> None:
        # A rendering fault (broken pipe, malformed event) must never escape
        # main -- run_acquisition's _EmitOnce guard already isolates this,
        # but this is defense in depth for any other caller of render_event.
        try:
            if isinstance(event, SuccessEvent):
                render_success(event)
            elif isinstance(event, ProgressEvent):
                render_progress(event)
            elif isinstance(event, SafeFailure):
                render_failure(event)
            else:
                render_failure(SafeFailure(ReasonCode.INTERNAL_FAILURE))
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            pass

    try:
        config = load_config(args.config)
        if args.provenance_only:
            run_provenance(config, os.environ, event_sink=render_event)
        else:
            run_acquisition(config, os.environ, event_sink=render_event)
    except AcquisitionFailure as error:
        if not error.reported:
            try:
                render_failure(error.failure)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception:
                pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
