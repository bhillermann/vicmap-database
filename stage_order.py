"""Guarded Phase 3 CLI: read policy, prove identity/privilege, stage one manifest.

Modeled on ``discover_order.py``'s shape -- a frozen policy loaded from
``vicmap.toml``, one ordered orchestration seam, and the same
deliberately-unguarded ``render_event`` idiom (``run_staging`` wraps every
call to this sink in its own ``read_mailbox._EmitOnce`` guard -- the one
emit-once isolation boundary -- so a rendering fault must be visible to that
guard, not silently absorbed a second time here). ``--preflight-only`` stops
after reporting the connection identity and proving the loader's staging
privileges, before any manifest is read or any layer is loaded.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import read_mailbox
from vicmap_acquire import staging
from vicmap_acquire.evidence import (
    ProgressEvent,
    ReasonCode,
    SafeFailure,
    SuccessEvent,
    render_failure,
    render_progress,
    render_success,
)
from vicmap_acquire.manifest import ManifestFailure, ManifestUnreadable, read_manifest


_REASON_BY_CODE = {reason.value: reason for reason in ReasonCode}


def _reason_for(code: str) -> ReasonCode:
    return _REASON_BY_CODE.get(code, ReasonCode.INTERNAL_FAILURE)


def _most_recent_run_directory(run_root: Path, order_id: str) -> Path:
    """Return the lexicographically greatest (D-32's ``%Y%m%dT%H%M%SZ``
    timestamp sorts chronologically) run subdirectory for ``order_id`` --
    the same directory ``extract_artifact`` created and ``manifest.json``
    lives in. No such directory is the closed ``manifest_unreadable``
    failure, not a configuration error: the order's Phase 2 run is simply
    missing, not misconfigured."""

    order_root = run_root / order_id
    try:
        candidates = sorted(
            (path for path in order_root.iterdir() if path.is_dir()),
            key=lambda path: path.name,
        )
    except OSError:
        raise ManifestUnreadable() from None
    if not candidates:
        raise ManifestUnreadable()
    return candidates[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage one Vicmap order's manifest layers")
    parser.add_argument("--config", type=Path, default=Path("vicmap.toml"))
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help=(
            "Report connection identity and prove staging privileges, then "
            "exit without reading a manifest or loading anything."
        ),
    )
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

    order_id: str | None = None
    try:
        run_config = read_mailbox.load_database_config(args.config)
        if len(run_config.allowed_order_ids) != 1:
            raise read_mailbox.AcquisitionFailure("config_invalid")
        order_id = run_config.allowed_order_ids[0]

        password = os.environ.get(staging.PASSWORD_ENV_VAR)
        if not password:
            raise read_mailbox.AcquisitionFailure("config_invalid")

        policy = staging.StagingPolicy(
            host=run_config.host,
            port=run_config.port,
            dbname=run_config.dbname,
            user=run_config.user,
            staging_schema=run_config.staging_schema,
            publish_schema=run_config.publish_schema,
            target_srid=run_config.target_srid,
            index_columns=run_config.index_columns,
            gt=run_config.gt,
            connect_timeout_seconds=run_config.connect_timeout_seconds,
            statement_timeout_seconds=run_config.statement_timeout_seconds,
            lock_timeout_seconds=run_config.lock_timeout_seconds,
        )

        identity = staging.read_database_identity(policy, password=password)
        render_event(
            SuccessEvent.database_identity(
                host=identity.host,
                port=identity.port,
                dbname=identity.dbname,
                role=identity.role,
                server_version=identity.server_version,
                postgis_version=identity.postgis_version,
            )
        )
        staging.preflight_staging_privileges(policy, password=password)

        if args.preflight_only:
            return 0

        run_directory = _most_recent_run_directory(run_config.run_root, order_id)
        manifest = read_manifest(run_directory)
        # D-48's suffix names the *discovery* run the manifest came from --
        # the run directory's own timestamp component -- rather than the
        # moment staging happened. Two staging attempts over the same
        # manifest then reuse the same staging table name, and the second
        # fails loudly on an existing table (ogr2ogr rejects a layer that
        # already exists without -overwrite/-append) rather than silently
        # creating a near-duplicate under a fresh now() timestamp.
        run_timestamp = run_directory.name

        staging.run_staging(
            manifest,
            policy,
            password=password,
            run_timestamp=run_timestamp,
            diagnostics_dir=run_directory,
            event_sink=render_event,
        )
    except read_mailbox.AcquisitionFailure as error:
        try:
            render_failure(SafeFailure(error.failure.reason, order_id=order_id))
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            pass
        return 1
    except staging.StagingFailure as error:
        try:
            render_failure(
                SafeFailure(
                    _reason_for(error.code),
                    order_id=order_id,
                    staging_table=getattr(error, "staging_table", None),
                    diagnostics_file=getattr(error, "diagnostics_file", None),
                )
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            pass
        return 1
    except ManifestFailure as error:
        try:
            render_failure(SafeFailure(_reason_for(error.code), order_id=order_id))
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            pass
        return 1
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        try:
            render_failure(SafeFailure(ReasonCode.INTERNAL_FAILURE, order_id=order_id))
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
