"""Guarded Phase 4 CLI: gate, promote, verify the reader, assemble the summary.

Modeled on ``stage_order.py``'s shape -- a frozen policy loaded from
``vicmap.toml``, one ordered orchestration seam, and the same
deliberately-unguarded ``render_event`` idiom this repository's other three
CLIs (``read_mailbox.py`` -> ``discover_order.py`` -> ``stage_order.py`` ->
``publish_order.py``, D-77) all use. This is the fourth and final one; no
top-level Phases-1->4 orchestrator is built here (OPS-05 stays deferred).

Two secrets reach this process, both only through the environment, never
through ``vicmap.toml`` or argv (D-58/D-74): the loader's password via
``staging.PASSWORD_ENV_VAR`` (``VICMAP_DB_PASSWORD``) and the reader's own
password via ``publish.READER_PASSWORD_ENV_VAR`` (``VICMAP_READER_PASSWORD``).
A missing loader password fails closed as ``config_invalid`` before any
connection is attempted; a missing reader password is left to
``publish.verify_reader_access``'s own guard, which fails closed with
``READER_ROLE_UNAVAILABLE`` -- deliberately *after* promotion has already
committed, since D-66..D-73's metadata-move publish is durable the moment its
own transaction commits, independent of whether the reader proof that follows
it can run. A plain re-run with the reader password now set completes that
same order: ``promote_or_resume`` resumes from the durable markers (D-78..D-83)
instead of re-entering promotion, so a run that only ever failed on the
reader proof can be finished by a bare retry (closes WINDOWS.md #16).

``publish.promote_or_resume`` runs the D-68 publication gate
(``assert_all_layers_validated``) first on every invocation (D-89), whether
this run promotes or resumes -- so this CLI does not call the gate a second
time. It then classifies the order's published state (D-86) and either
promotes a freshly staged order or resumes a committed one by reconstructing
``PromotionResult`` from the durable ``vicmap_audit.publication`` markers
(D-82) -- auto-detected on a plain re-run, with no flag (D-83).
``publish.read_layer_validations`` re-reads the same durable ``vicmap_audit``
rows independently (D-76) for the EVID-01 summary, never threading the
gate's own in-memory pass/fail result forward.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import read_mailbox
from vicmap_acquire import publish, staging
from vicmap_acquire.evidence import (
    ProgressEvent,
    ReasonCode,
    SafeFailure,
    SuccessEvent,
    render_failure,
    render_progress,
    render_success,
)
from vicmap_acquire.manifest import (
    ManifestFailure,
    ManifestUnreadable,
    manifest_digest,
    read_manifest,
)


_REASON_BY_CODE = {reason.value: reason for reason in ReasonCode}


def _reason_for(code: str) -> ReasonCode:
    return _REASON_BY_CODE.get(code, ReasonCode.INTERNAL_FAILURE)


def _most_recent_run_directory(run_root: Path, order_id: str) -> Path:
    """Return the lexicographically greatest (D-32's ``%Y%m%dT%H%M%SZ``
    timestamp sorts chronologically) run subdirectory for ``order_id`` --
    the exact directory ``stage_order.py``'s own helper of the same name
    locates, re-implemented here rather than imported (each CLI in this
    repository is a self-contained script). No such directory is the closed
    ``manifest_unreadable`` failure: the order's staged run is simply
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
    parser = argparse.ArgumentParser(
        description="Publish one Vicmap order's validated staging layers"
    )
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

    order_id: str | None = None
    try:
        discovery_config = read_mailbox.load_discovery_config(args.config)
        run_config = read_mailbox.load_database_config(args.config)
        if len(run_config.allowed_order_ids) != 1:
            raise read_mailbox.AcquisitionFailure("config_invalid")
        order_id = run_config.allowed_order_ids[0]

        # D-58: the loader's own secret -- VICMAP_DB_PASSWORD, read only from
        # the environment, exactly as stage_order.py's preflight requires.
        loader_password = os.environ.get(staging.PASSWORD_ENV_VAR)
        if not loader_password:
            raise read_mailbox.AcquisitionFailure("config_invalid")

        # D-74: the reader's own secret -- VICMAP_READER_PASSWORD, read only
        # from the environment. An unset value is deliberately not checked
        # here: publish.verify_reader_access fails closed with the correct
        # READER_ROLE_UNAVAILABLE reason on its own, after promotion (which
        # has already durably committed) has run.
        reader_password = os.environ.get(publish.READER_PASSWORD_ENV_VAR)

        policy = publish.PublishPolicy(
            host=run_config.host,
            port=run_config.port,
            dbname=run_config.dbname,
            user=run_config.user,
            staging_schema=run_config.staging_schema,
            publish_schema=run_config.publish_schema,
            target_srid=run_config.target_srid,
            reader_user=run_config.reader_user,
            connect_timeout_seconds=run_config.connect_timeout_seconds,
            statement_timeout_seconds=run_config.statement_timeout_seconds,
            lock_timeout_seconds=run_config.lock_timeout_seconds,
        )

        run_directory = _most_recent_run_directory(run_config.run_root, order_id)
        manifest = read_manifest(run_directory)
        digest = manifest_digest(run_directory)
        run_timestamp = run_directory.name
        target_tables = tuple(layer.target_table for layer in manifest.layers)

        # D-68/D-83/D-86: the gate runs as promote_or_resume's own first
        # action; a hard-stopped gate never reaches any DDL (T-04-06). The
        # classify-then-branch step that follows either commits a fresh
        # promotion durably right here, independent of everything that
        # follows, or resumes from an already-committed one without opening
        # a promotion connection at all.
        publication_result = publish.promote_or_resume(
            manifest, policy, loader_password, run_timestamp, digest
        )

        # D-74/PUB-04/PUB-05: a real, independently-authenticated reader
        # login -- never SET ROLE from the loader connection.
        reader_verification = publish.verify_reader_access(
            policy,
            reader_password=reader_password,
            published_tables=publication_result.published_tables,
        )

        # D-76: re-read the durable vicmap_audit rows independently for the
        # summary -- never the gate's own in-memory pass/fail result.
        validation_rows = publish.read_layer_validations(
            policy,
            loader_password,
            run_timestamp=run_timestamp,
            manifest_digest=digest,
            target_tables=target_tables,
        )

        artifact_path = discovery_config.artifacts_dir / f"Order_{order_id}.zip"
        summary = publish.assemble_summary(
            order_id=order_id,
            artifact_path=artifact_path,
            manifest=manifest,
            manifest_digest=digest,
            validation_rows=validation_rows,
            publication_result=publication_result,
            reader_verification=reader_verification,
            fingerprint_hex_chars=run_config.fingerprint_hex_chars,
        )
        publish.write_summary(run_directory, summary)

        # D-75: the durable summary.json file is the deliverable; this is
        # its everything-is-an-event mirror, the one success event this CLI
        # renders.
        render_event(publish.summary_to_publication_event(summary))
    except read_mailbox.AcquisitionFailure as error:
        try:
            render_failure(SafeFailure(error.failure.reason, order_id=order_id))
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
    except (publish.PublishFailure, staging.StagingFailure) as error:
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
