"""Guarded CLI and ``run_discovery`` orchestration seam for Phase 2.

Mirrors ``read_mailbox.py``'s shape: no work on import, a frozen config
object accepted as an argument, and one ordered orchestration seam composing
verify -> extract -> discover -> name -> build -> write -> render as ordered
typed-failure calls where no stage swallows another stage's exception. For
this tracer, ``ExtractionPolicy`` and ``DiscoveryPolicy`` are constructed
from explicit ``DiscoveryConfig`` fields; 02-02 replaces this with
``vicmap.toml`` loading, mirroring ``read_mailbox.load_config``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from vicmap_acquire.discovery import DiscoveryFailure, DiscoveryPolicy, discover_layers
from vicmap_acquire.evidence import (
    ReasonCode,
    SafeFailure,
    SuccessEvent,
    fingerprint,
    render_failure,
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


def run_discovery(config: DiscoveryConfig, *, event_sink: EventSink) -> ImportManifest:
    """Compose verify -> extract -> discover -> name -> build -> write -> render.

    Each stage is an ordered typed-failure call; no stage swallows another
    stage's exception. A failure at any stage emits one redacted
    ``SafeFailure`` event (order ID and stage/reason/hint only, never a raw
    filesystem path or source layer name) and then re-raises the original
    typed exception unchanged.
    """

    try:
        verify_artifact(
            config.artifact_path,
            expected_sha256=config.expected_sha256,
            expected_byte_count=config.expected_byte_count,
        )
        event_sink(
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
        event_sink(
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
        event_sink(
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
        return manifest
    except (ArchiveFailure, DiscoveryFailure, NamingFailure, ManifestFailure) as error:
        event_sink(
            SafeFailure(
                _reason_for(error.code),
                order_id=config.order_id,
                fingerprint_hex_chars=config.fingerprint_hex_chars,
            )
        )
        raise
    except Exception:
        event_sink(
            SafeFailure(
                ReasonCode.INTERNAL_FAILURE,
                order_id=config.order_id,
                fingerprint_hex_chars=config.fingerprint_hex_chars,
            )
        )
        raise


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Full ``vicmap.toml``-driven configuration (artifact provenance, run
    root, extraction/discovery ceilings) lands in 02-02; this guarded stub
    exists so ``discover_order.py`` is complete, importable, and
    zero-side-effect-on-import per the ``read_mailbox.py`` shape, with a
    single command-line entry point behind ``if __name__ == "__main__":``.
    """

    parser = argparse.ArgumentParser(description="Discover a Vicmap order's geospatial layers")
    parser.add_argument("--config", type=Path, default=Path("vicmap.toml"))
    parser.parse_args(argv)

    try:
        render_failure(SafeFailure(ReasonCode.CONFIG_INVALID))
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        pass
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
