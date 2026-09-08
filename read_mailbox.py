"""Guarded CLI and orchestration for trusted Vicmap artifact acquisition."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

import requests

from vicmap_acquire.candidates import CandidateError, recognize_candidate, select_candidate
from vicmap_acquire.download import (
    DownloadError,
    DownloadResult,
    download_artifact,
    validate_https_target,
)
from vicmap_acquire.graph import GraphError, GraphMailbox
from vicmap_acquire.evidence import (
    ProgressEvent,
    ReasonCode,
    SafeFailure,
    SuccessEvent,
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
}
_ORDER_ID = re.compile(r"[A-Za-z0-9]+")
_HOSTNAME = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


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


def _emit_failure(event_sink: EventSink, reason: ReasonCode | str) -> SafeFailure:
    failure = SafeFailure(_reason_code(reason))
    event_sink(failure)
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
    if not isinstance(value, list) or not value:
        raise AcquisitionFailure("config_invalid")
    items = tuple(_strict_string(item) for item in value)
    if len(set(items)) != len(items):
        raise AcquisitionFailure("config_invalid")
    return items


def _bounded_integer(value: object, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AcquisitionFailure("config_invalid")
    if value < minimum or value > maximum:
        raise AcquisitionFailure("config_invalid")
    return value


def _validate_config_object(config: AcquisitionConfig) -> None:
    _strict_string(config.mailbox)
    _strict_string(config.folder)
    if not config.allowed_senders or not config.allowed_order_ids or not config.allowed_hosts:
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


def run_acquisition(
    config: AcquisitionConfig,
    credentials: Mapping[str, str],
    graph_factory=None,
    session_factory=None,
    event_sink: EventSink = lambda event: None,
) -> DownloadResult:
    """Run the ordered Graph-to-artifact path through injectable I/O seams."""

    try:
        _validate_config_object(config)
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
            )
            if candidate is not None:
                candidates.append(candidate)
        selected = select_candidate(candidates)
        event_sink(
            SuccessEvent.candidate_selected(
                order_id=selected.order_id,
                received_at=selected.received_datetime_utc,
                sender=selected.sender,
                graph_message_id=selected.graph_message_id,
            )
        )

        validate_https_target(selected.artifact_url, config.allowed_hosts)
        result = download_artifact(
            selected.artifact_url,
            output_dir=config.output_dir,
            allowed_hosts=config.allowed_hosts,
            max_bytes=config.max_bytes,
            connect_timeout_seconds=config.connect_timeout_seconds,
            read_timeout_seconds=config.read_timeout_seconds,
            max_redirects=config.max_redirects,
            session=session_factory(),
            progress_sink=lambda progress: event_sink(
                ProgressEvent.from_download_event(progress)
            ),
        )
        event_sink(
            SuccessEvent.download_target(
                approved_hostname=result.approved_hostname,
                path_fingerprint=result.path_fingerprint,
            )
        )
        event_sink(
            SuccessEvent.artifact_finalized(
                byte_count=result.byte_count,
                sha256=result.sha256,
            )
        )
        return result
    except AcquisitionFailure as error:
        if error.reported:
            raise
        failure = _emit_failure(event_sink, error.failure.reason)
        raise AcquisitionFailure(failure.reason, reported=True) from None
    except (GraphError, CandidateError, DownloadError) as error:
        failure = _emit_failure(event_sink, error.code)
        raise AcquisitionFailure(failure.reason, reported=True) from None
    except Exception:
        failure = _emit_failure(event_sink, ReasonCode.INTERNAL_FAILURE)
        raise AcquisitionFailure(failure.reason, reported=True) from None


def load_config(path: Path) -> AcquisitionConfig:
    """Load and fully validate non-secret policy without creating runtime state."""

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        if set(raw) != {"mailbox", "download"}:
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
        for sender in senders:
            if sender.count("@") != 1 or any(character.isspace() for character in sender):
                raise AcquisitionFailure("config_invalid")
        order_ids = _string_list(mailbox["allowed_order_ids"])
        if any(_ORDER_ID.fullmatch(order_id) is None for order_id in order_ids):
            raise AcquisitionFailure("config_invalid")
        hosts = _string_list(download["allowed_hosts"])
        if any(
            host != host.casefold()
            or host.endswith(".")
            or _HOSTNAME.fullmatch(host) is None
            for host in hosts
        ):
            raise AcquisitionFailure("config_invalid")

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
        if output_dir.exists() and not output_dir.is_dir():
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
        )
        _validate_config_object(config)
        return config
    except AcquisitionFailure:
        raise
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError):
        raise AcquisitionFailure("config_invalid") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire one trusted Vicmap artifact")
    parser.add_argument("--config", type=Path, default=Path("vicmap.toml"))
    args = parser.parse_args(argv)

    def render_event(event: object) -> None:
        if isinstance(event, SuccessEvent):
            render_success(event)
        elif isinstance(event, ProgressEvent):
            render_progress(event)
        elif isinstance(event, SafeFailure):
            render_failure(event)
        else:
            render_failure(SafeFailure(ReasonCode.INTERNAL_FAILURE))

    try:
        config = load_config(args.config)
        run_acquisition(config, os.environ, event_sink=render_event)
    except AcquisitionFailure as error:
        if not error.reported:
            render_failure(error.failure)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
