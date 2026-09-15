"""Guarded CLI and ``run_discovery`` orchestration seam for Phase 2.

Mirrors ``read_mailbox.py``'s shape: no work on import, a frozen config
object accepted as an argument, and one ordered orchestration seam composing
verify -> extract -> discover -> name -> build -> write -> render as ordered
typed-failure calls where no stage swallows another stage's exception.
``DiscoveryConfig``'s ``extraction_policy``/``discovery_policy`` fields keep
the shape 02-01's tracer fixed; ``main`` builds them from
``read_mailbox.load_discovery_config``'s ``vicmap.toml`` policy and reads the
artifact's D-32/D-28 provenance sidecar rather than hardcoding either.

Every event ``run_discovery`` emits is routed through
``read_mailbox._EmitOnce`` -- the same guard ``run_acquisition`` uses, reused
rather than reimplemented -- so a faulty ``event_sink`` can never turn a
closed failure into a raw exception and is never retried once it has
failed. Automatic selection is unconditional: every discovered layer flows
straight from ``discover_layers`` into ``assign_target_table_names`` with no
filter, no prompt, and no allowlist between them (D-30).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import read_mailbox
from vicmap_acquire.discovery import DiscoveryFailure, DiscoveryPolicy, discover_layers
from vicmap_acquire.download import ProvenanceUnavailable, read_provenance_sidecar
from vicmap_acquire.evidence import (
    ReasonCode,
    SafeFailure,
    SuccessEvent,
    fingerprint,
    render_failure,
    render_success,
)
from vicmap_acquire.extraction import (
    ArchiveFailure,
    ExtractionPolicy,
    extract_artifact,
    verify_artifact,
)
from vicmap_acquire.manifest import (
    CompanionFile,
    ImportManifest,
    ManifestFailure,
    ManifestLayer,
    build_manifest,
    write_manifest,
)
from vicmap_acquire.naming import NamingFailure, assign_target_table_names


EventSink = Callable[[object], None]

_REASON_BY_CODE = {reason.value: reason for reason in ReasonCode}


@dataclass(frozen=True)
class DiscoveryConfig:
    """Complete non-secret policy for one artifact-to-manifest discovery run."""

    artifact_path: Path
    order_id: str
    run_timestamp: str
    expected_sha256: str
    expected_byte_count: int
    message_fingerprint: str
    extraction_policy: ExtractionPolicy
    discovery_policy: DiscoveryPolicy
    fingerprint_hex_chars: int = 16


def _reason_for(code: str) -> ReasonCode:
    return _REASON_BY_CODE.get(code, ReasonCode.INTERNAL_FAILURE)


def _is_dataset_member(relative_path: str) -> bool:
    """A member belongs to a discovered dataset iff its path enters a ``.gdb`` dir."""

    return ".gdb/" in f"{relative_path}/"


class RunDiscoveryReportingFailed(RuntimeError):
    """The pipeline completed (manifest written) but the event sink itself failed.

    Raised only when ``guard.failed`` is still true once every stage has
    returned successfully -- the operator's evidence stream broke silently,
    so a run that otherwise succeeded is reported as failed rather than
    silently returning 0. Mirrors ``read_mailbox.run_acquisition``'s own
    ``if guard.failed: raise AcquisitionFailure(...)`` check. Never raised
    for, and never masks, an already-published manifest: the manifest and
    its sidecar are already committed to disk by the time this is raised.
    """

    code = "internal_failure"


def run_discovery(config: DiscoveryConfig, *, event_sink: EventSink) -> ImportManifest:
    """Compose verify -> extract -> discover -> name -> build -> write -> render.

    Each stage is an ordered typed-failure call; no stage swallows another
    stage's exception, and no stage begins before the previous one has
    returned successfully. Automatic selection is unconditional: every
    profile ``discover_layers`` returns flows straight into
    ``assign_target_table_names`` with no filter, no prompt, and no
    allowlist between them (D-30).

    Every event -- success and failure alike -- passes through a
    ``read_mailbox._EmitOnce`` guard, so a faulty ``event_sink`` can never
    turn a closed failure into a raw exception and is never retried once it
    has failed. A failure at any stage emits at most one redacted
    ``SafeFailure`` event (order ID and stage/reason/hint only, never a raw
    filesystem path or source layer name) and then re-raises the original
    typed exception unchanged. Reaching the end with a failed guard raises
    ``RunDiscoveryReportingFailed`` without touching the already-written
    manifest.
    """

    guard = read_mailbox._EmitOnce(event_sink)

    try:
        verify_artifact(
            config.artifact_path,
            expected_sha256=config.expected_sha256,
            expected_byte_count=config.expected_byte_count,
        )
        guard.emit(
            SuccessEvent.artifact_verified(
                order_id=config.order_id,
                byte_count=config.expected_byte_count,
                sha256=config.expected_sha256,
            )
        )

        extraction_result = extract_artifact(
            config.artifact_path,
            order_id=config.order_id,
            run_timestamp=config.run_timestamp,
            policy=config.extraction_policy,
        )
        run_path_fingerprint = fingerprint(
            str(extraction_result.run_directory), config.fingerprint_hex_chars
        )
        guard.emit(
            SuccessEvent.archive_extracted(
                order_id=config.order_id,
                member_count=len(extraction_result.members),
                total_byte_count=extraction_result.total_byte_count,
                run_path_fingerprint=run_path_fingerprint,
                fingerprint_hex_chars=config.fingerprint_hex_chars,
            )
        )

        profiles = discover_layers(extraction_result.run_directory, config.discovery_policy)
        named = assign_target_table_names(profiles)
        layers = tuple(
            ManifestLayer(profile=profile, target_table=target) for profile, target in named
        )

        companions = tuple(
            CompanionFile(
                relative_path=member.relative_path,
                byte_count=member.byte_count,
                sha256=member.sha256,
            )
            for member in extraction_result.members
            if not _is_dataset_member(member.relative_path)
        )

        manifest = build_manifest(
            order_id=config.order_id,
            run_timestamp=config.run_timestamp,
            run_directory=extraction_result.run_directory,
            artifact_sha256=config.expected_sha256,
            artifact_byte_count=config.expected_byte_count,
            message_fingerprint=config.message_fingerprint,
            layers=layers,
            companions=companions,
        )
        manifest_sha256 = write_manifest(manifest, extraction_result.run_directory)

        target_tables = tuple(layer.target_table for layer in layers)
        guard.emit(
            SuccessEvent.manifest_completed(
                order_id=config.order_id,
                layer_count=len(layers),
                companion_count=len(companions),
                target_tables=target_tables,
                manifest_sha256=manifest_sha256,
                run_path_fingerprint=run_path_fingerprint,
                fingerprint_hex_chars=config.fingerprint_hex_chars,
            )
        )

        if guard.failed:
            raise RunDiscoveryReportingFailed()
        return manifest
    except (ArchiveFailure, DiscoveryFailure, NamingFailure, ManifestFailure) as error:
        guard.emit_failure(
            SafeFailure(
                _reason_for(error.code),
                order_id=config.order_id,
                fingerprint_hex_chars=config.fingerprint_hex_chars,
            )
        )
        raise
    except Exception:
        guard.emit_failure(
            SafeFailure(
                ReasonCode.INTERNAL_FAILURE,
                order_id=config.order_id,
                fingerprint_hex_chars=config.fingerprint_hex_chars,
            )
        )
        raise


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Loads the complete non-secret Phase 2 policy through
    ``read_mailbox.load_discovery_config`` (the same ``vicmap.toml`` contract
    ``read_mailbox.load_config`` enforces), builds ``ExtractionPolicy`` and
    ``DiscoveryPolicy`` from it, reads the artifact's durable D-32/D-28
    provenance sidecar, and runs one ``run_discovery`` pass. No ceiling or
    format value is ever written literally here. ``run_discovery``'s ordered
    composition and exit-code contract are complete as of this plan (02-06);
    multi-order CLI ergonomics remain out of scope -- this CLI still
    requires ``vicmap.toml``'s ``allowed_order_ids`` to name exactly one
    order.
    """

    parser = argparse.ArgumentParser(description="Discover a Vicmap order's geospatial layers")
    parser.add_argument("--config", type=Path, default=Path("vicmap.toml"))
    args = parser.parse_args(argv)

    def render_event(event: object) -> None:
        # Deliberately unguarded here: run_discovery wraps every call to
        # this sink in its own read_mailbox._EmitOnce guard, which is the
        # one emit-once isolation boundary (never retried once failed). A
        # rendering fault must be visible to that guard -- swallowing it a
        # second time here would hide it from guard.failed and let a broken
        # render_success silently report a successful exit.
        if isinstance(event, SuccessEvent):
            render_success(event)
        elif isinstance(event, SafeFailure):
            render_failure(event)
        else:
            render_failure(SafeFailure(ReasonCode.INTERNAL_FAILURE))

    order_id: str | None = None
    try:
        run_config = read_mailbox.load_discovery_config(args.config)
        if len(run_config.allowed_order_ids) != 1:
            raise read_mailbox.AcquisitionFailure("config_invalid")
        order_id = run_config.allowed_order_ids[0]

        artifact_path = run_config.artifacts_dir / f"Order_{order_id}.zip"
        provenance = read_provenance_sidecar(artifact_path, order_id=order_id)

        extraction_policy = ExtractionPolicy(
            run_root=run_config.run_root,
            max_total_bytes=run_config.max_total_bytes,
            max_member_bytes=run_config.max_member_bytes,
            max_member_count=run_config.max_member_count,
            max_compression_ratio=run_config.max_compression_ratio,
        )
        discovery_policy = DiscoveryPolicy(
            supported_formats=run_config.supported_formats,
            ogrinfo_timeout_seconds=run_config.ogrinfo_timeout_seconds,
        )
        run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        config = DiscoveryConfig(
            artifact_path=artifact_path,
            order_id=order_id,
            run_timestamp=run_timestamp,
            expected_sha256=provenance.sha256,
            expected_byte_count=provenance.byte_count,
            message_fingerprint=provenance.message_fingerprint,
            extraction_policy=extraction_policy,
            discovery_policy=discovery_policy,
            fingerprint_hex_chars=run_config.fingerprint_hex_chars,
        )
        run_discovery(config, event_sink=render_event)
    except read_mailbox.AcquisitionFailure as error:
        try:
            render_failure(error.failure)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            pass
        return 1
    except ProvenanceUnavailable:
        try:
            render_failure(
                SafeFailure(ReasonCode.PROVENANCE_UNAVAILABLE, order_id=order_id)
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            pass
        return 1
    except (ArchiveFailure, DiscoveryFailure, NamingFailure, ManifestFailure):
        # run_discovery already emitted exactly one redacted SafeFailure
        # through its own guard.
        return 1
    except Exception:
        # Covers RunDiscoveryReportingFailed (the guard's own sink already
        # failed exactly once and is never retried -- see run_discovery)
        # and any other unexpected exception. This render_failure call is
        # outside the guard entirely, so it still reaches the operator even
        # when the guarded sink itself is what broke.
        try:
            render_failure(SafeFailure(ReasonCode.INTERNAL_FAILURE))
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
