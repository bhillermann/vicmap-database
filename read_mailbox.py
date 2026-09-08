"""Guarded CLI and orchestration for trusted Vicmap artifact acquisition."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
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


EventSink = Callable[[dict[str, object]], None]


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

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _fingerprint(value: str, length: int) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _mask_sender(sender: str) -> str:
    local, separator, domain = sender.partition("@")
    if not separator:
        return "***"
    if len(local) <= 2:
        masked_local = local[:1] + "*" * max(1, len(local) - 1)
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def _emit_failure(event_sink: EventSink, reason: str) -> None:
    event_sink(
        {
            "event": "failure",
            "stage": reason.split("_", 1)[0],
            "reason": reason,
            "hint": "review_configuration_or_request_a_fresh_delivery",
        }
    )


def _require_credentials(credentials: Mapping[str, str]) -> None:
    for name in ("O365_AUTH_ID", "O365_AUTH_SECRET", "TENANT_ID"):
        value = credentials.get(name)
        if not isinstance(value, str) or not value.strip():
            raise AcquisitionFailure("config_invalid")


def run_acquisition(
    config: AcquisitionConfig,
    credentials: Mapping[str, str],
    graph_factory=GraphMailbox,
    session_factory=requests.Session,
    event_sink: EventSink = lambda event: None,
) -> DownloadResult:
    """Run the ordered Graph-to-artifact path through injectable I/O seams."""

    try:
        _require_credentials(credentials)
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
        if selected is None:
            raise AcquisitionFailure("candidate_none")

        event_sink(
            {
                "event": "candidate_selected",
                "order_id": selected.order_id,
                "received_at": selected.received_datetime_utc.isoformat(),
                "sender": _mask_sender(selected.sender),
                "message_fingerprint": _fingerprint(
                    selected.graph_message_id, config.fingerprint_hex_chars
                ),
            }
        )

        target = validate_https_target(selected.artifact_url, config.allowed_hosts)
        event_sink(
            {
                "event": "download_target",
                "host": target.hostname or "",
                "path_fingerprint": _fingerprint(
                    target.path, config.fingerprint_hex_chars
                ),
            }
        )
        result = download_artifact(
            selected.artifact_url,
            output_dir=config.output_dir,
            allowed_hosts=config.allowed_hosts,
            max_bytes=config.max_bytes,
            connect_timeout_seconds=config.connect_timeout_seconds,
            read_timeout_seconds=config.read_timeout_seconds,
            max_redirects=config.max_redirects,
            session=session_factory(),
        )
        event_sink(
            {
                "event": "artifact_finalized",
                "byte_count": result.byte_count,
                "sha256": result.sha256,
            }
        )
        return result
    except AcquisitionFailure as error:
        _emit_failure(event_sink, error.code)
        raise
    except (GraphError, CandidateError, DownloadError) as error:
        _emit_failure(event_sink, error.code)
        raise AcquisitionFailure(error.code) from None
    except Exception:
        _emit_failure(event_sink, "graph_scan_failed")
        raise AcquisitionFailure("graph_scan_failed") from None


def load_config(path: Path) -> AcquisitionConfig:
    """Load policy from TOML. Full fail-closed validation is added in Task 2."""

    raise AcquisitionFailure("config_invalid")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire one trusted Vicmap artifact")
    parser.add_argument("--config", type=Path, default=Path("vicmap.toml"))
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        result = run_acquisition(config, os.environ, event_sink=lambda event: print(event))
    except AcquisitionFailure as error:
        print({"event": "failure", "reason": error.code}, file=sys.stderr)
        return 1
    print(
        {
            "event": "complete",
            "byte_count": result.byte_count,
            "sha256": result.sha256,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
