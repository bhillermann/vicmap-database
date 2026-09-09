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
from types import SimpleNamespace
from unittest.mock import patch


try:
    evidence = importlib.import_module("vicmap_acquire.evidence")
except ModuleNotFoundError:
    evidence = None


AUTH_RESULTS_PASS = (
    "spf=pass smtp.mailfrom=maps.vic.gov.au;"
    "dkim=pass (signature was verified) header.d=maps.vic.gov.au;"
    "dmarc=pass action=none header.from=datashare.maps.vic.gov.au;"
    "compauth=pass reason=100"
)
AUTH_RESULTS_DKIM_FAIL = (
    "spf=pass smtp.mailfrom=maps.vic.gov.au;"
    "dkim=fail (signature verification failed) header.d=maps.vic.gov.au;"
    "dmarc=pass action=none header.from=datashare.maps.vic.gov.au;"
    "compauth=pass reason=100"
)


def _e2e_mime(
    *,
    artifact_url: str,
    from_header: str = "noreply@datashare.maps.vic.gov.au",
    auth_results: tuple[str, ...] = (AUTH_RESULTS_PASS,),
) -> bytes:
    lines = [
        f"From: {from_header}",
        "To: automations@vegetationlink.com.au",
        "Subject: Your DataShare Order OK0VUZ is ready to download",
    ]
    for value in auth_results:
        lines.append(f"Authentication-Results: {value}")
    lines.extend(
        [
            "MIME-Version: 1.0",
            "Content-Type: text/plain; charset=utf-8",
            "",
            f"Download: {artifact_url}",
        ]
    )
    return ("\r\n".join(lines) + "\r\n").encode()


class _E2EResponse:
    status_code = 200

    def __init__(self, payload: bytes) -> None:
        self.headers = {
            "Content-Length": str(len(payload)),
            "Content-Encoding": "identity",
        }
        self._payload = payload
        self.closed = False

    def iter_content(self, chunk_size: int):
        yield self._payload

    def close(self) -> None:
        self.closed = True


class _E2ESession:
    def __init__(self, payload: bytes = b"authentic-artifact-bytes") -> None:
        self.auth = ("ambient", "must-be-cleared")
        self.cookies = SimpleNamespace(clear=lambda: None)
        self.headers = {}
        self.trust_env = True
        self.calls: list[str] = []
        self.response = _E2EResponse(payload)

    def get(self, url: str, **kwargs):
        self.calls.append(url)
        return self.response


class _E2EGraph:
    def __init__(self, metadata, mime_by_id, **kwargs) -> None:
        self._metadata = metadata
        self._mime_by_id = mime_by_id
        self.mime_requests: list[str] = []

    def iter_metadata(self, cutoff_utc):
        return iter(self._metadata)

    def get_mime_content(self, graph_message_id):
        self.mime_requests.append(graph_message_id)
        return self._mime_by_id[graph_message_id]


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
            "origin_unauthenticated": "candidate",
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
                required_authentication_results=("dkim", "dmarc", "compauth"),
                allowed_url_prefixes=("https://s3.ap-southeast-2.amazonaws.com/private/",),
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


class ControllerCompositionTest(unittest.TestCase):
    @staticmethod
    def _config(
        output_dir: Path,
        *,
        allowed_senders: tuple[str, ...] = ("noreply@datashare.maps.vic.gov.au",),
    ):
        import read_mailbox

        return read_mailbox.AcquisitionConfig(
            mailbox="automations@vegetationlink.com.au",
            folder="Inbox",
            allowed_senders=allowed_senders,
            allowed_order_ids=("OK0VUZ",),
            allowed_hosts=("s3.ap-southeast-2.amazonaws.com",),
            lookback_days=15,
            max_bytes=987654,
            connect_timeout_seconds=17,
            read_timeout_seconds=23,
            progress_interval_seconds=29,
            max_redirects=3,
            fingerprint_hex_chars=16,
            allow_order_id_mismatch=False,
            output_dir=output_dir,
            required_authentication_results=("dkim", "dmarc", "compauth"),
            allowed_url_prefixes=("https://s3.ap-southeast-2.amazonaws.com/private/",),
        )

    @staticmethod
    def _credentials():
        return {
            "O365_AUTH_ID": "private-client-id",
            "O365_AUTH_SECRET": "private-client-secret",
            "TENANT_ID": "private-tenant-id",
        }

    @staticmethod
    def _candidate(message_id: str, received_at: datetime, artifact_url: str):
        from vicmap_acquire.candidates import Candidate

        return Candidate(
            order_id="OK0VUZ",
            received_datetime_utc=received_at,
            graph_message_id=message_id,
            sender="noreply@datashare.maps.vic.gov.au",
            artifact_url=artifact_url,
        )

    def test_authenticated_origin_completes_end_to_end_with_expected_events(self):
        import read_mailbox
        from vicmap_acquire.graph import MessageMetadata

        message_id = "opaque-e2e-message-id"
        artifact_url = (
            "https://s3.ap-southeast-2.amazonaws.com/private/Order_OK0VUZ.zip"
        )
        payload = b"authentic-artifact-bytes"
        metadata = [
            MessageMetadata(
                graph_message_id=message_id,
                received_datetime_utc=datetime(2026, 9, 7, tzinfo=timezone.utc),
                sender="noreply@datashare.maps.vic.gov.au",
                subject="Your DataShare Order OK0VUZ is ready to download",
            )
        ]
        graph = _E2EGraph(metadata, {message_id: _e2e_mime(artifact_url=artifact_url)})
        session = _E2ESession(payload)
        events = []

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "artifacts"
            config = self._config(output_dir)
            result = read_mailbox.run_acquisition(
                config,
                self._credentials(),
                graph_factory=lambda **kwargs: graph,
                session_factory=lambda: session,
                event_sink=events.append,
            )

        self.assertEqual(len(payload), result.byte_count)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), result.sha256)
        self.assertEqual(
            ["candidate_selected", "download_target", "artifact_finalized"],
            [event["event"] for event in events],
        )
        self.assertEqual(1, len(session.calls))

    def test_matching_message_pointing_outside_the_configured_prefix_is_rejected(self):
        import read_mailbox
        from vicmap_acquire.graph import MessageMetadata

        message_id = "opaque-wrong-bucket-message-id"
        artifact_url = "https://s3.ap-southeast-2.amazonaws.com/other/Order_OK0VUZ.zip"
        metadata = [
            MessageMetadata(
                graph_message_id=message_id,
                received_datetime_utc=datetime(2026, 9, 7, tzinfo=timezone.utc),
                sender="noreply@datashare.maps.vic.gov.au",
                subject="Your DataShare Order OK0VUZ is ready to download",
            )
        ]
        graph = _E2EGraph(metadata, {message_id: _e2e_mime(artifact_url=artifact_url)})
        session = _E2ESession()
        events = []

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "artifacts"
            config = self._config(output_dir)
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.run_acquisition(
                    config,
                    self._credentials(),
                    graph_factory=lambda **kwargs: graph,
                    session_factory=lambda: session,
                    event_sink=events.append,
                )
            self.assertFalse(output_dir.exists())

        self.assertEqual("download_url_rejected", caught.exception.code)
        self.assertEqual([], session.calls)
        self.assertEqual("download_url_rejected", events[-1]["reason"])

    def test_unauthenticated_dkim_verdict_is_rejected_before_any_download_contact(self):
        import read_mailbox
        from vicmap_acquire.graph import MessageMetadata

        message_id = "opaque-dkim-fail-message-id"
        artifact_url = "https://s3.ap-southeast-2.amazonaws.com/private/Order_OK0VUZ.zip"
        metadata = [
            MessageMetadata(
                graph_message_id=message_id,
                received_datetime_utc=datetime(2026, 9, 7, tzinfo=timezone.utc),
                sender="noreply@datashare.maps.vic.gov.au",
                subject="Your DataShare Order OK0VUZ is ready to download",
            )
        ]
        graph = _E2EGraph(
            metadata,
            {
                message_id: _e2e_mime(
                    artifact_url=artifact_url,
                    auth_results=(AUTH_RESULTS_DKIM_FAIL,),
                )
            },
        )
        session = _E2ESession()
        events = []

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "artifacts"
            config = self._config(output_dir)
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.run_acquisition(
                    config,
                    self._credentials(),
                    graph_factory=lambda **kwargs: graph,
                    session_factory=lambda: session,
                    event_sink=events.append,
                )

        self.assertEqual("origin_unauthenticated", caught.exception.code)
        self.assertEqual([message_id], graph.mime_requests)
        self.assertEqual([], session.calls)
        self.assertEqual("origin_unauthenticated", events[-1]["reason"])

    def test_injected_passing_header_cannot_rescue_a_genuine_failing_verdict(self):
        import read_mailbox
        from vicmap_acquire.graph import MessageMetadata

        message_id = "opaque-injected-header-message-id"
        artifact_url = "https://s3.ap-southeast-2.amazonaws.com/private/Order_OK0VUZ.zip"
        metadata = [
            MessageMetadata(
                graph_message_id=message_id,
                received_datetime_utc=datetime(2026, 9, 7, tzinfo=timezone.utc),
                sender="noreply@datashare.maps.vic.gov.au",
                subject="Your DataShare Order OK0VUZ is ready to download",
            )
        ]
        graph = _E2EGraph(
            metadata,
            {
                message_id: _e2e_mime(
                    artifact_url=artifact_url,
                    auth_results=(AUTH_RESULTS_PASS, AUTH_RESULTS_DKIM_FAIL),
                )
            },
        )
        session = _E2ESession()
        events = []

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "artifacts"
            config = self._config(output_dir)
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.run_acquisition(
                    config,
                    self._credentials(),
                    graph_factory=lambda **kwargs: graph,
                    session_factory=lambda: session,
                    event_sink=events.append,
                )

        self.assertEqual("origin_unauthenticated", caught.exception.code)
        self.assertEqual([], session.calls)

    def test_from_header_disagreeing_with_graph_metadata_sender_is_rejected(self):
        import read_mailbox
        from vicmap_acquire.graph import MessageMetadata

        message_id = "opaque-sender-mismatch-message-id"
        artifact_url = "https://s3.ap-southeast-2.amazonaws.com/private/Order_OK0VUZ.zip"
        graph_sender = "noreply@datashare.maps.vic.gov.au"
        from_sender = "reports@datashare.maps.vic.gov.au"
        metadata = [
            MessageMetadata(
                graph_message_id=message_id,
                received_datetime_utc=datetime(2026, 9, 7, tzinfo=timezone.utc),
                sender=graph_sender,
                subject="Your DataShare Order OK0VUZ is ready to download",
            )
        ]
        graph = _E2EGraph(
            metadata,
            {
                message_id: _e2e_mime(
                    artifact_url=artifact_url, from_header=from_sender
                )
            },
        )
        session = _E2ESession()
        events = []

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "artifacts"
            config = self._config(
                output_dir, allowed_senders=(graph_sender, from_sender)
            )
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.run_acquisition(
                    config,
                    self._credentials(),
                    graph_factory=lambda **kwargs: graph,
                    session_factory=lambda: session,
                    event_sink=events.append,
                )

        self.assertEqual("origin_unauthenticated", caught.exception.code)
        self.assertEqual([], session.calls)

    def test_controller_passes_complete_policy_to_one_newest_download(self):
        import read_mailbox
        from vicmap_acquire.download import DownloadPolicy, DownloadResult
        from vicmap_acquire.graph import MessageMetadata

        older_id = "older-complete-graph-id"
        newest_id = "newest-complete-graph-id"
        older_url = (
            "https://s3.ap-southeast-2.amazonaws.com/private/older/"
            "Order_OK0VUZ.zip?signature=older-private-query"
        )
        newest_url = (
            "https://s3.ap-southeast-2.amazonaws.com/private/newest/"
            "Order_OK0VUZ.zip?signature=newest-private-query"
        )
        older_at = datetime(2026, 9, 7, 1, tzinfo=timezone.utc)
        newest_at = datetime(2026, 9, 7, 2, tzinfo=timezone.utc)
        metadata = [
            MessageMetadata(older_id, older_at, "ignored@example.test", "ignored"),
            MessageMetadata(newest_id, newest_at, "ignored@example.test", "ignored"),
        ]

        class Graph:
            def __init__(self, **kwargs):
                pass

            def iter_metadata(self, cutoff_utc):
                return iter(metadata)

            def get_mime_content(self, graph_message_id):
                raise AssertionError("recognition is isolated by this controller test")

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "artifacts"
            config = self._config(output_dir)
            final_path = output_dir / "Order_OK0VUZ.zip"
            result = DownloadResult(
                path=final_path,
                byte_count=13,
                sha256=hashlib.sha256(b"archive bytes").hexdigest(),
                approved_hostname="s3.ap-southeast-2.amazonaws.com",
                path_fingerprint="0123456789abcdef",
            )
            with (
                patch.object(
                    read_mailbox,
                    "recognize_candidate",
                    side_effect=(
                        self._candidate(older_id, older_at, older_url),
                        self._candidate(newest_id, newest_at, newest_url),
                    ),
                ),
                patch.object(
                    read_mailbox, "download_artifact", return_value=result
                ) as downloader,
            ):
                actual = read_mailbox.run_acquisition(
                    config,
                    self._credentials(),
                    graph_factory=Graph,
                    session_factory=lambda: object(),
                    event_sink=lambda event: None,
                )

        self.assertEqual(result, actual)
        downloader.assert_called_once()
        args, kwargs = downloader.call_args
        self.assertEqual((newest_url,), args)
        self.assertIsInstance(
            kwargs.get("policy"),
            DownloadPolicy,
            "the final controller must pass the complete configured DownloadPolicy",
        )
        policy = kwargs["policy"]
        self.assertEqual(987654, policy.max_bytes)
        self.assertEqual(17, policy.connect_timeout_seconds)
        self.assertEqual(23, policy.stalled_read_timeout_seconds)
        self.assertEqual(29, policy.progress_interval_seconds)
        self.assertEqual(3, policy.max_redirects)
        self.assertEqual(16, policy.fingerprint_hex_length)
        self.assertEqual(final_path, kwargs["final_path"])
        self.assertNotIn("session", kwargs)

    def test_empty_complete_scan_fails_candidate_stage_without_download(self):
        import read_mailbox

        class EmptyGraph:
            def __init__(self, **kwargs):
                pass

            def iter_metadata(self, cutoff_utc):
                return iter(())

        events = []
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(read_mailbox, "download_artifact") as downloader:
                with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                    read_mailbox.run_acquisition(
                        self._config(Path(directory)),
                        self._credentials(),
                        graph_factory=EmptyGraph,
                        event_sink=events.append,
                    )

        self.assertEqual("candidate_none", caught.exception.code)
        downloader.assert_not_called()
        self.assertEqual("candidate", events[-1]["stage"])
        self.assertEqual("candidate_none", events[-1]["reason"])

    def test_expired_newest_download_stops_after_one_attempt_without_fallback(self):
        import read_mailbox
        from vicmap_acquire.download import DownloadExpiredOrMissing
        from vicmap_acquire.graph import MessageMetadata

        older_id = "older-complete-graph-id"
        newest_id = "newest-complete-graph-id"
        older_url = "https://s3.ap-southeast-2.amazonaws.com/a/Order_OK0VUZ.zip"
        newest_url = "https://s3.ap-southeast-2.amazonaws.com/b/Order_OK0VUZ.zip"
        older_at = datetime(2026, 9, 7, 1, tzinfo=timezone.utc)
        newest_at = datetime(2026, 9, 7, 2, tzinfo=timezone.utc)
        metadata = [
            MessageMetadata(older_id, older_at, "ignored@example.test", "ignored"),
            MessageMetadata(newest_id, newest_at, "ignored@example.test", "ignored"),
        ]

        class Graph:
            def __init__(self, **kwargs):
                pass

            def iter_metadata(self, cutoff_utc):
                return iter(metadata)

        events = []
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(
                    read_mailbox,
                    "recognize_candidate",
                    side_effect=(
                        self._candidate(older_id, older_at, older_url),
                        self._candidate(newest_id, newest_at, newest_url),
                    ),
                ),
                patch.object(
                    read_mailbox,
                    "download_artifact",
                    side_effect=DownloadExpiredOrMissing(),
                ) as downloader,
            ):
                with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                    read_mailbox.run_acquisition(
                        self._config(Path(directory)),
                        self._credentials(),
                        graph_factory=Graph,
                        event_sink=events.append,
                    )

        self.assertEqual("download_expired_or_missing", caught.exception.code)
        downloader.assert_called_once()
        self.assertEqual(newest_url, downloader.call_args.args[0])
        self.assertEqual("download", events[-1]["stage"])
        self.assertEqual("download_expired_or_missing", events[-1]["reason"])


if __name__ == "__main__":
    unittest.main()
