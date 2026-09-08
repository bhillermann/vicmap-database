from __future__ import annotations

import contextlib
import hashlib
import importlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


try:
    evidence = importlib.import_module("vicmap_acquire.evidence")
except ModuleNotFoundError:
    evidence = None


class EvidenceContractTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            evidence,
            "the planned closed evidence module must exist before its contract can pass",
        )

    def _json_line(self, renderer, event):
        stream = io.StringIO()
        renderer(event, stream=stream)
        rendered = stream.getvalue()
        self.assertTrue(rendered.endswith("\n"))
        self.assertEqual(1, rendered.count("\n"))
        self.assertNotIn(" ", rendered)
        return json.loads(rendered)

    def test_every_reason_has_one_fixed_stage_and_remediation_hint(self):
        expected = {
            "config_invalid": "configuration",
            "graph_auth_failed": "graph_authentication",
            "mailbox_access_failed": "mailbox_access",
            "graph_scan_failed": "scan",
            "candidate_none": "candidate",
            "candidate_ambiguous": "candidate",
            "order_id_mismatch": "candidate",
            "download_url_rejected": "download",
            "download_redirect_rejected": "download",
            "download_expired_or_missing": "download",
            "download_timeout": "download",
            "download_too_large": "download",
            "download_http_failed": "download",
            "artifact_write_failed": "artifact_write",
            "internal_failure": "internal",
        }
        self.assertEqual(expected, evidence.reason_stage_vocabulary())
        self.assertEqual(set(expected.values()), {stage.value for stage in evidence.Stage})

        hints = {}
        for reason in evidence.ReasonCode:
            safe = evidence.SafeFailure(reason)
            payload = self._json_line(evidence.render_failure, safe)
            self.assertEqual(
                {"event", "hint", "reason", "stage"}, set(payload)
            )
            self.assertEqual(expected[reason.value], payload["stage"])
            self.assertRegex(payload["hint"], r"^[a-z0-9_]+$")
            hints[reason] = payload["hint"]
        self.assertEqual(len(evidence.ReasonCode), len(hints))

    def test_candidate_success_identity_is_exact_and_redacted(self):
        complete_id = "opaque-complete-graph-message-id/private"
        sender = "noreply@datashare.maps.vic.gov.au"
        received = datetime(2026, 9, 7, 1, 2, 3, tzinfo=timezone.utc)
        event = evidence.SuccessEvent.candidate_selected(
            order_id="OK0VUZ",
            received_at=received,
            sender=sender,
            graph_message_id=complete_id,
        )
        payload = self._json_line(evidence.render_success, event)
        self.assertEqual(
            {
                "event": "candidate_selected",
                "message_fingerprint": hashlib.sha256(
                    complete_id.encode("utf-8")
                ).hexdigest()[:16],
                "order_id": "OK0VUZ",
                "received_at": "2026-09-07T01:02:03+00:00",
                "sender": "n*****y@datashare.maps.vic.gov.au",
            },
            payload,
        )
        rendered = json.dumps(payload)
        self.assertNotIn(complete_id, rendered)
        self.assertNotIn(sender, rendered)
        self.assertNotIn("subject", rendered)
        self.assertNotIn("body", rendered)

    def test_target_and_final_success_use_only_downloader_provenance(self):
        complete_url = (
            "https://s3.ap-southeast-2.amazonaws.com/private/Order_OK0VUZ.zip"
            "?X-Amz-Credential=secret-query"
        )
        complete_path = "/private/Order_OK0VUZ.zip"
        path_fingerprint = hashlib.sha256(complete_path.encode("utf-8")).hexdigest()[:16]

        target = evidence.SuccessEvent.download_target(
            approved_hostname="s3.ap-southeast-2.amazonaws.com",
            path_fingerprint=path_fingerprint,
        )
        target_payload = self._json_line(evidence.render_success, target)
        self.assertEqual(
            {
                "event": "download_target",
                "host": "s3.ap-southeast-2.amazonaws.com",
                "path_fingerprint": path_fingerprint,
            },
            target_payload,
        )

        checksum = hashlib.sha256(b"archive bytes").hexdigest()
        final = evidence.SuccessEvent.artifact_finalized(
            byte_count=13, sha256=checksum
        )
        final_payload = self._json_line(evidence.render_success, final)
        self.assertEqual(
            {"event": "artifact_finalized", "byte_count": 13, "sha256": checksum},
            final_payload,
        )
        rendered = json.dumps((target_payload, final_payload))
        self.assertNotIn(complete_url, rendered)
        self.assertNotIn(complete_path, rendered)
        self.assertNotIn("secret-query", rendered)

    def test_progress_uses_exact_integer_tenths_or_omits_percentage(self):
        known = evidence.ProgressEvent.from_counts(1999, 2000)
        self.assertEqual(
            {"event": "download_progress", "byte_count": 1999, "percent": 99.9},
            self._json_line(evidence.render_progress, known),
        )
        unknown = evidence.ProgressEvent.from_counts(1999, None)
        self.assertEqual(
            {"event": "download_progress", "byte_count": 1999},
            self._json_line(evidence.render_progress, unknown),
        )

    def test_renderer_rejects_raw_mapping_exception_and_source_text(self):
        unsafe_inputs = (
            {"event": "failure", "reason": "provider said bearer-token"},
            RuntimeError("bearer-token raw-exception response-body"),
            "complete-presigned-url?secret=query",
        )
        for unsafe in unsafe_inputs:
            with self.subTest(unsafe=type(unsafe).__name__):
                with self.assertRaises(TypeError):
                    evidence.render_failure(unsafe, stream=io.StringIO())

    def test_failure_optional_identifiers_are_allowlisted_and_redacted(self):
        failure = evidence.SafeFailure(
            evidence.ReasonCode.DOWNLOAD_EXPIRED_OR_MISSING,
            order_id="OK0VUZ",
            message_fingerprint="0123456789abcdef",
            path_fingerprint="fedcba9876543210",
        )
        payload = self._json_line(evidence.render_failure, failure)
        self.assertEqual(
            {
                "event": "failure",
                "hint": evidence.remediation_hint(
                    evidence.ReasonCode.DOWNLOAD_EXPIRED_OR_MISSING
                ),
                "message_fingerprint": "0123456789abcdef",
                "order_id": "OK0VUZ",
                "path_fingerprint": "fedcba9876543210",
                "reason": "download_expired_or_missing",
                "stage": "download",
            },
            payload,
        )


class ControllerDisclosureTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            evidence,
            "the planned closed evidence module must exist before controller output can pass",
        )

    def test_unexpected_exception_becomes_fixed_internal_failure_without_raw_text(self):
        import read_mailbox

        raw_exception = "bearer-token complete-message-id private-response-body"

        class ExplodingGraph:
            def __init__(self, **kwargs):
                pass

            def iter_metadata(self, cutoff_utc):
                raise RuntimeError(raw_exception)

        with tempfile.TemporaryDirectory() as directory:
            config = read_mailbox.AcquisitionConfig(
                mailbox="automations@vegetationlink.com.au",
                folder="Inbox",
                allowed_senders=("noreply@datashare.maps.vic.gov.au",),
                allowed_order_ids=("OK0VUZ",),
                allowed_hosts=("s3.ap-southeast-2.amazonaws.com",),
                lookback_days=15,
                max_bytes=1024,
                connect_timeout_seconds=10,
                read_timeout_seconds=60,
                progress_interval_seconds=5,
                max_redirects=5,
                fingerprint_hex_chars=16,
                allow_order_id_mismatch=False,
                output_dir=Path(directory),
            )
            stderr = io.StringIO()
            with (
                patch.object(read_mailbox, "load_config", return_value=config),
                patch.object(read_mailbox, "GraphMailbox", ExplodingGraph),
                patch.dict(
                    read_mailbox.os.environ,
                    {
                        "O365_AUTH_ID": "private-client-id",
                        "O365_AUTH_SECRET": "private-client-secret",
                        "TENANT_ID": "private-tenant-id",
                    },
                    clear=True,
                ),
                contextlib.redirect_stderr(stderr),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                exit_code = read_mailbox.main(["--config", "ignored.toml"])

        self.assertNotEqual(0, exit_code)
        payload = json.loads(stderr.getvalue())
        self.assertEqual("internal_failure", payload["reason"])
        self.assertEqual("internal", payload["stage"])
        rendered = stderr.getvalue()
        for forbidden in (
            raw_exception,
            "bearer-token",
            "complete-message-id",
            "private-response-body",
            "private-client-id",
            "private-client-secret",
            "private-tenant-id",
            "Traceback",
        ):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
