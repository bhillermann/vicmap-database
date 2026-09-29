"""Tests for ``publish_order.py`` -- the fourth one-CLI-per-phase entry point.

Mirrors ``test_publish.py``'s offline-only shape: every test here patches the
library seams ``publish_order.main`` composes (``read_mailbox``'s config
loaders, the run-directory/manifest reads, and ``publish``'s
gate+promote/reader-verify/summary functions) so no test in this file ever
touches a real filesystem run directory or a real database connection.
EVID-02's contract is what is under test: every failure boundary returns a
non-zero exit, names its stage/reason via one rendered ``SafeFailure`` line,
and leaks no secret, path, or driver text; the success path returns 0 and
renders exactly one ``publication_summary`` success event.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import publish_order
import read_mailbox
from vicmap_acquire import publish, staging
from vicmap_acquire.manifest import ManifestUnreadable


_ORDER_ID = "ORD123"
_LOADER_PASSWORD = "sentinel-loader-secret"
_READER_PASSWORD = "sentinel-reader-secret"
_RUN_DIRECTORY = Path("/fake/runs") / _ORDER_ID / "20260918t041500z"


def _discovery_config(**overrides) -> read_mailbox.DiscoveryRunConfig:
    kwargs = dict(
        artifacts_dir=Path("/fake/artifacts"),
        run_root=Path("/fake/runs"),
        fingerprint_hex_chars=16,
        allowed_order_ids=(_ORDER_ID,),
        max_total_bytes=10**12,
        max_member_bytes=10**11,
        max_member_count=1000,
        max_compression_ratio=100,
        supported_formats=("FileGDB",),
        ogrinfo_timeout_seconds=60,
    )
    kwargs.update(overrides)
    return read_mailbox.DiscoveryRunConfig(**kwargs)


def _database_config(**overrides) -> read_mailbox.DatabaseRunConfig:
    kwargs = dict(
        run_root=Path("/fake/runs"),
        fingerprint_hex_chars=16,
        allowed_order_ids=(_ORDER_ID,),
        host="127.0.0.1",
        port=5432,
        dbname="vicmap",
        user="vicmap_loader",
        staging_schema="vicmap_staging",
        publish_schema="vicmap",
        target_srid=7899,
        index_columns=("geom",),
        gt=65536,
        connect_timeout_seconds=5,
        statement_timeout_seconds=3600,
        lock_timeout_seconds=30,
        reader_user="vicmap_reader",
    )
    kwargs.update(overrides)
    return read_mailbox.DatabaseRunConfig(**kwargs)


class _FakeManifestLayer:
    def __init__(self, target_table: str) -> None:
        self.target_table = target_table


class _FakeManifest:
    def __init__(self, target_tables=("vmadd_address",)) -> None:
        self.layers = tuple(_FakeManifestLayer(table) for table in target_tables)


_FIXED_PUBLISHED_AT = datetime(2026, 9, 24, 7, 9, 27, 495000, tzinfo=timezone.utc)


def _promotion_result(**overrides) -> publish.PromotionResult:
    kwargs = dict(
        server_version="PostgreSQL 18.6 (fake build)",
        published_tables=("vmadd_address",),
        published_at=_FIXED_PUBLISHED_AT,
        promotion=publish.PROMOTION_PERFORMED,
    )
    kwargs.update(overrides)
    return publish.PromotionResult(**kwargs)


def _reader_verification(**overrides) -> publish.ReaderVerification:
    kwargs = dict(
        tables_discovered=("vmadd_address",),
        spatial_query_row_count=2,
        write_denied=True,
    )
    kwargs.update(overrides)
    return publish.ReaderVerification(**kwargs)


def _validation_records(**overrides):
    kwargs = dict(
        target_table="vmadd_address",
        verdict="pass",
        spatial=True,
        row_count=4222035,
        srid=7899,
        geometry_type="POINT",
        repaired_count=0,
    )
    kwargs.update(overrides)
    return (publish.LayerValidationRecord(**kwargs),)


def _fixed_summary() -> dict:
    return {
        "order_id": _ORDER_ID,
        "message_fingerprint": "a" * 16,
        "artifact_sha256": "b" * 64,
        "manifest_sha256": "c" * 64,
        "layer_count": 1,
        "published_tables": ["vmadd_address"],
        "server_version": "PostgreSQL 18.6 (fake build)",
        "staging_validation": [
            {
                "target_table": "vmadd_address",
                "spatial": True,
                "row_count": 4222035,
                "srid": 7899,
                "geometry_type": "POINT",
                "repaired_count": 0,
            }
        ],
        "reader": {
            "tables_discovered": ["vmadd_address"],
            "tables_discovered_count": 1,
            "spatial_query_row_count": 2,
            "write_denied": True,
        },
    }


@contextlib.contextmanager
def _patched_pipeline(**overrides):
    """Patch every seam ``publish_order.main`` composes with a working
    default, so a single ``overrides`` entry (a callable side_effect, or a
    replacement return value) is enough to isolate exactly one failure
    boundary at a time -- never a real filesystem or database touch."""

    defaults = dict(
        load_discovery_config=lambda path: _discovery_config(),
        load_database_config=lambda path: _database_config(),
        most_recent_run_directory=lambda run_root, order_id: _RUN_DIRECTORY,
        read_manifest=lambda run_directory: _FakeManifest(),
        manifest_digest=lambda run_directory: "c" * 64,
        promote_or_resume=lambda *a, **k: _promotion_result(),
        verify_reader_access=lambda *a, **k: _reader_verification(),
        read_layer_validations=lambda *a, **k: _validation_records(),
        assemble_summary=lambda **k: _fixed_summary(),
        write_summary=lambda run_directory, summary: Path(run_directory) / "summary.json",
        summary_to_publication_event=lambda summary: publish.SuccessEvent.publication_summary(
            order_id=summary["order_id"],
            message_fingerprint=summary["message_fingerprint"],
            artifact_sha256=summary["artifact_sha256"],
            manifest_sha256=summary["manifest_sha256"],
            layer_count=summary["layer_count"],
            published_tables=tuple(summary["published_tables"]),
            reader_tables_discovered=summary["reader"]["tables_discovered_count"],
            reader_spatial_query_row_count=summary["reader"]["spatial_query_row_count"],
            reader_write_denied=summary["reader"]["write_denied"],
        ),
    )
    defaults.update(overrides)

    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch.object(read_mailbox, "load_discovery_config", defaults["load_discovery_config"])
        )
        stack.enter_context(
            patch.object(read_mailbox, "load_database_config", defaults["load_database_config"])
        )
        stack.enter_context(
            patch.object(
                publish_order,
                "_most_recent_run_directory",
                defaults["most_recent_run_directory"],
            )
        )
        stack.enter_context(
            patch.object(publish_order, "read_manifest", defaults["read_manifest"])
        )
        stack.enter_context(
            patch.object(publish_order, "manifest_digest", defaults["manifest_digest"])
        )
        stack.enter_context(
            patch.object(publish, "promote_or_resume", defaults["promote_or_resume"])
        )
        stack.enter_context(
            patch.object(publish, "verify_reader_access", defaults["verify_reader_access"])
        )
        stack.enter_context(
            patch.object(
                publish, "read_layer_validations", defaults["read_layer_validations"]
            )
        )
        stack.enter_context(
            patch.object(publish, "assemble_summary", defaults["assemble_summary"])
        )
        stack.enter_context(
            patch.object(publish, "write_summary", defaults["write_summary"])
        )
        stack.enter_context(
            patch.object(
                publish,
                "summary_to_publication_event",
                defaults["summary_to_publication_event"],
            )
        )
        yield


def _run_main_capturing_output(**env_overrides) -> tuple[int, str, str]:
    env = {
        staging.PASSWORD_ENV_VAR: _LOADER_PASSWORD,
        publish.READER_PASSWORD_ENV_VAR: _READER_PASSWORD,
    }
    env.update(env_overrides)
    # A missing key (rather than an empty string) means "truly unset" --
    # patch.dict can only set values, so pop unwanted keys after entering.
    unset = [key for key, value in env.items() if value is None]
    for key in unset:
        del env[key]
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.dict(os.environ, env, clear=False):
        for key in unset:
            os.environ.pop(key, None)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = publish_order.main([])
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _forbidden_text_absent(test: unittest.TestCase, *texts: str) -> None:
    for text in texts:
        for forbidden in (_LOADER_PASSWORD, _READER_PASSWORD, "psycopg", "Traceback"):
            test.assertNotIn(forbidden, text)


class SuccessPathTest(unittest.TestCase):
    """No database. A fully successful run returns 0, renders exactly one
    ``publication_summary`` success event, and leaks no secret."""

    def test_successful_run_returns_zero_and_renders_the_summary_event(self):
        with _patched_pipeline():
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(0, exit_code)
        self.assertEqual("", stderr)
        payload = json.loads(stdout.strip())
        self.assertEqual("publication_summary", payload["event"])
        self.assertEqual(_ORDER_ID, payload["order_id"])
        _forbidden_text_absent(self, stdout, stderr)


class ResumeBranchTest(unittest.TestCase):
    """No database. A resumed promotion result (D-83) is otherwise
    indistinguishable from a fresh promotion to this CLI's own exception
    ladder -- it completes the full pipeline and exits 0 with exactly one
    ``publication_summary`` event."""

    def test_resumed_promotion_exits_zero_with_one_summary_event(self):
        with _patched_pipeline(
            promote_or_resume=lambda *a, **k: _promotion_result(
                promotion=publish.PROMOTION_RESUMED
            )
        ):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(0, exit_code)
        self.assertEqual("", stderr)
        events = [json.loads(line) for line in stdout.splitlines() if line]
        self.assertEqual(["publication_summary"], [e.get("event") for e in events])
        _forbidden_text_absent(self, stdout, stderr)


class PromoteOrResumeSeamTest(unittest.TestCase):
    """No database. ``main``'s one publication seam (D-83) passes the
    manifest, policy, the loader password, the run directory name as
    ``run_timestamp``, and the manifest digest to ``promote_or_resume``."""

    def test_main_passes_loader_password_run_timestamp_and_digest(self):
        captured: dict[str, object] = {}

        def _capture(manifest, policy, password, run_timestamp, manifest_digest):
            captured["manifest"] = manifest
            captured["policy"] = policy
            captured["password"] = password
            captured["run_timestamp"] = run_timestamp
            captured["manifest_digest"] = manifest_digest
            return _promotion_result()

        with _patched_pipeline(
            promote_or_resume=_capture,
            manifest_digest=lambda run_directory: "c" * 64,
        ):
            exit_code, _stdout, _stderr = _run_main_capturing_output()

        self.assertEqual(0, exit_code)
        self.assertEqual(_LOADER_PASSWORD, captured["password"])
        self.assertEqual(_RUN_DIRECTORY.name, captured["run_timestamp"])
        self.assertEqual("c" * 64, captured["manifest_digest"])
        self.assertIsInstance(captured["policy"], publish.PublishPolicy)


class ConfigInvalidTest(unittest.TestCase):
    """No database. A missing loader password fails closed as
    ``config_invalid`` before any connection is attempted."""

    def test_missing_loader_password_is_config_invalid(self):
        with _patched_pipeline():
            exit_code, stdout, stderr = _run_main_capturing_output(
                **{staging.PASSWORD_ENV_VAR: None}
            )
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("configuration", failure["stage"])
        self.assertEqual("config_invalid", failure["reason"])
        _forbidden_text_absent(self, stdout, stderr)

    def test_more_than_one_allowed_order_id_is_config_invalid(self):
        with _patched_pipeline(
            load_database_config=lambda path: _database_config(
                allowed_order_ids=(_ORDER_ID, "ORD456")
            )
        ):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("config_invalid", failure["reason"])


class ManifestFailureTest(unittest.TestCase):
    """No database. A manifest read failure maps to the manifest stage."""

    def test_manifest_unreadable_maps_to_manifest_stage(self):
        def _raise(run_directory):
            raise ManifestUnreadable()

        with _patched_pipeline(read_manifest=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("manifest", failure["stage"])
        self.assertEqual("manifest_unreadable", failure["reason"])
        _forbidden_text_absent(self, stdout, stderr)

    def test_no_run_directory_maps_to_manifest_stage(self):
        def _raise(run_root, order_id):
            raise ManifestUnreadable()

        with _patched_pipeline(most_recent_run_directory=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("manifest_unreadable", failure["reason"])


class PublicationGateFailureTest(unittest.TestCase):
    """No database. The D-68 gate's own failures surface via DB_AUDIT."""

    def test_publication_validation_missing_maps_to_db_audit_stage(self):
        def _raise(*a, **k):
            raise publish.PublicationValidationMissing()

        with _patched_pipeline(promote_or_resume=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("db_audit", failure["stage"])
        self.assertEqual("pub_validation_missing", failure["reason"])
        _forbidden_text_absent(self, stdout, stderr)

    def test_audit_privilege_denied_maps_to_db_audit_stage(self):
        def _raise(*a, **k):
            raise staging.AuditPrivilegeDenied()

        with _patched_pipeline(promote_or_resume=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("db_audit", failure["stage"])
        self.assertEqual("db_audit_privilege_denied", failure["reason"])

    def test_read_layer_validations_audit_privilege_denied_maps_to_db_audit_stage(self):
        def _raise(*a, **k):
            raise staging.AuditPrivilegeDenied()

        with _patched_pipeline(read_layer_validations=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("db_audit_privilege_denied", failure["reason"])


class PromotionFailureTest(unittest.TestCase):
    """No database. A mid-promotion failure surfaces via DB_PUBLISH; the
    prior published tables are untouched by construction (PUB-03), which is
    ``promote_order``'s own contract, not this CLI's -- only the exit-code
    mapping is under test here."""

    def test_promotion_failed_maps_to_db_publish_stage(self):
        def _raise(*a, **k):
            raise publish.PromotionFailed()

        with _patched_pipeline(promote_or_resume=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("db_publish", failure["stage"])
        self.assertEqual("pub_promotion_failed", failure["reason"])
        _forbidden_text_absent(self, stdout, stderr)


class ReaderVerificationFailureTest(unittest.TestCase):
    """No database. Every reader-verification failure surfaces via
    DB_READER_VERIFY -- promotion has already committed by the time any of
    these can be raised (D-74)."""

    def test_reader_role_unavailable_maps_to_db_reader_verify_stage(self):
        def _raise(*a, **k):
            raise publish.ReaderRoleUnavailable()

        with _patched_pipeline(verify_reader_access=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("db_reader_verify", failure["stage"])
        self.assertEqual("reader_role_unavailable", failure["reason"])
        _forbidden_text_absent(self, stdout, stderr)

    def test_missing_reader_password_reaches_reader_role_unavailable(self):
        # The real verify_reader_access (not a stand-in raiser) proves the
        # "unset reader password" path this CLI deliberately leaves to
        # publish.verify_reader_access's own guard (D-74).
        with _patched_pipeline(
            verify_reader_access=publish.verify_reader_access,
        ):
            exit_code, stdout, stderr = _run_main_capturing_output(
                **{publish.READER_PASSWORD_ENV_VAR: None}
            )
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("reader_role_unavailable", failure["reason"])
        _forbidden_text_absent(self, stdout, stderr)

    def test_reader_verification_failed_maps_to_db_reader_verify_stage(self):
        def _raise(*a, **k):
            raise publish.ReaderVerificationFailed()

        with _patched_pipeline(verify_reader_access=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("reader_verification_failed", failure["reason"])

    def test_reader_write_not_denied_maps_to_db_reader_verify_stage(self):
        # T-04-02, security-critical: this must surface as a hard failure,
        # never a downgraded warning or a silent pass.
        def _raise(*a, **k):
            raise publish.ReaderWriteNotDenied()

        with _patched_pipeline(verify_reader_access=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("db_reader_verify", failure["stage"])
        self.assertEqual("reader_write_not_denied", failure["reason"])
        _forbidden_text_absent(self, stdout, stderr)


class InternalFailureTest(unittest.TestCase):
    """No database. Any unanticipated exception -- never a typed closed
    failure -- maps to the one fixed ``INTERNAL_FAILURE``, with no
    interpolated exception text ever reaching the operator."""

    def test_unexpected_exception_maps_to_internal_failure(self):
        def _raise(*a, **k):
            raise RuntimeError("a raw driver/subprocess detail that must never leak")

        with _patched_pipeline(assemble_summary=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("internal", failure["stage"])
        self.assertEqual("internal_failure", failure["reason"])
        self.assertNotIn("raw driver", stderr)
        _forbidden_text_absent(self, stdout, stderr)

    def test_summary_write_failure_maps_to_internal_failure(self):
        def _raise(run_directory, summary):
            raise OSError("disk full")

        with _patched_pipeline(write_summary=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("internal_failure", failure["reason"])
        self.assertNotIn("disk full", stderr)


class ResumeVocabularyBoundaryTest(unittest.TestCase):
    """No database. The three ``promote_or_resume`` raisers this plan closes
    the vocabulary for (D-87), plus an ``assemble_summary`` raiser of the new
    D-91 ``PublicationSummaryFailed`` -- each surfaces at its own named
    boundary, never ``pub_promotion_failed`` or ``internal_failure``."""

    def test_publication_ambiguous_maps_to_db_publish_stage(self):
        def _raise(*a, **k):
            raise publish.PublicationAmbiguous()

        with _patched_pipeline(promote_or_resume=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("db_publish", failure["stage"])
        self.assertEqual("pub_generation_ambiguous", failure["reason"])
        _forbidden_text_absent(self, stdout, stderr)

    def test_publication_superseded_maps_to_db_publish_stage(self):
        def _raise(*a, **k):
            raise publish.PublicationSuperseded()

        with _patched_pipeline(promote_or_resume=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("db_publish", failure["stage"])
        self.assertEqual("pub_generation_superseded", failure["reason"])
        _forbidden_text_absent(self, stdout, stderr)

    def test_audit_read_failed_maps_to_db_audit_stage(self):
        def _raise(*a, **k):
            raise publish.AuditReadFailed()

        with _patched_pipeline(promote_or_resume=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("db_audit", failure["stage"])
        self.assertEqual("db_audit_read_failed", failure["reason"])
        _forbidden_text_absent(self, stdout, stderr)

    def test_publication_summary_failed_maps_to_publication_summary_stage(self):
        def _raise(**k):
            raise publish.PublicationSummaryFailed()

        with _patched_pipeline(assemble_summary=_raise):
            exit_code, stdout, stderr = _run_main_capturing_output()
        self.assertEqual(1, exit_code)
        failure = json.loads(stderr.strip())
        self.assertEqual("publication_summary", failure["stage"])
        self.assertEqual("pub_summary_failed", failure["reason"])
        _forbidden_text_absent(self, stdout, stderr)


class ExitContractShapeTest(unittest.TestCase):
    """No database. Structural pin of ``main``'s own exception ladder, so a
    future refactor cannot silently drop a mapped boundary or the catch-all
    (mirrors ``test_publish.py``'s ``ClosedFailureVocabularyTest`` shape)."""

    def test_every_failure_case_returns_exactly_one(self):
        for override in (
            {"read_manifest": lambda run_directory: (_ for _ in ()).throw(ManifestUnreadable())},
            {"promote_or_resume": lambda *a, **k: (_ for _ in ()).throw(publish.PromotionFailed())},
            {
                "verify_reader_access": lambda *a, **k: (_ for _ in ()).throw(
                    publish.ReaderRoleUnavailable()
                )
            },
        ):
            with _patched_pipeline(**override):
                exit_code, _stdout, _stderr = _run_main_capturing_output()
            self.assertEqual(1, exit_code)


if __name__ == "__main__":
    unittest.main()
