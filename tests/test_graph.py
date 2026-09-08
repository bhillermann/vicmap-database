from __future__ import annotations

import contextlib
import hashlib
import importlib
import io
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


READY_SUBJECT = "Your DataShare Order OK0VUZ is ready to download"
MESSAGE_ID = "opaque-graph-message-id-do-not-log"
OLDER_MESSAGE_ID = "older-opaque-message-id-do-not-log"
BODY_MARKER = "private source body marker"
ARTIFACT_URL = (
    "https://s3.ap-southeast-2.amazonaws.com/private/Order_OK0VUZ.zip"
    "?signature=private-query-marker"
)
PAYLOAD = b"authentic-shaped-archive-bytes"


class _LegacyFolder:
    def get_messages(self, *args, **kwargs):
        return ()


class _LegacyMailbox:
    def get_folder(self, *args, **kwargs):
        return _LegacyFolder()


class _LegacyAccount:
    is_authenticated = True

    def __init__(self, *args, **kwargs):
        pass

    def authenticate(self, *args, **kwargs):
        return True

    def mailbox(self, *args, **kwargs):
        return _LegacyMailbox()


class _LegacyTokenBackend:
    def __init__(self, *args, **kwargs):
        pass


def _import_read_mailbox_without_legacy_effects():
    """Import the prototype without allowing its current top-level Graph path."""

    sys.modules.pop("read_mailbox", None)
    captured = io.StringIO()
    with (
        patch("O365.Account", _LegacyAccount),
        patch("O365.FileSystemTokenBackend", _LegacyTokenBackend),
        contextlib.redirect_stdout(captured),
        contextlib.redirect_stderr(captured),
    ):
        module = importlib.import_module("read_mailbox")
    return module


class _FakeResponse:
    status_code = 200

    def __init__(self, payload: bytes):
        self.headers = {
            "Content-Length": str(len(payload)),
            "Content-Encoding": "identity",
        }
        self._payload = payload
        self.closed = False

    def iter_content(self, chunk_size: int):
        midpoint = len(self._payload) // 2
        yield self._payload[:midpoint]
        yield self._payload[midpoint:]

    def close(self):
        self.closed = True


class _FakeSession:
    def __init__(self, payload: bytes = PAYLOAD):
        self.auth = ("ambient", "must-be-cleared")
        self.cookies = SimpleNamespace(clear=lambda: None)
        self.headers = {}
        self.trust_env = True
        self.calls = []
        self.response = _FakeResponse(payload)

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs, self.auth, self.trust_env))
        return self.response


class _FakeGraph:
    def __init__(self, metadata, mime_by_id):
        self.metadata = metadata
        self.mime_by_id = mime_by_id
        self.mime_requests = []

    def iter_metadata(self, cutoff_utc):
        self.cutoff_utc = cutoff_utc
        return iter(self.metadata)

    def get_mime_content(self, graph_message_id: str):
        self.mime_requests.append(graph_message_id)
        return self.mime_by_id[graph_message_id]


def _mime(url: str) -> bytes:
    return (
        "From: noreply@datashare.maps.vic.gov.au\r\n"
        "To: automations@vegetationlink.com.au\r\n"
        f"Subject: {READY_SUBJECT}\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"{BODY_MARKER}\r\nDownload: {url}\r\n"
    ).encode()


class PipelineTracerTest(unittest.TestCase):
    def test_pipeline_streams_one_candidate_and_emits_only_redacted_evidence(self):
        read_mailbox = _import_read_mailbox_without_legacy_effects()
        self.assertTrue(
            callable(getattr(read_mailbox, "run_acquisition", None)),
            "run_acquisition must expose the production tracer seam",
        )

        from vicmap_acquire.graph import MessageMetadata

        received = datetime(2026, 9, 7, 1, 2, 3, tzinfo=timezone.utc)
        metadata = MessageMetadata(
            graph_message_id=MESSAGE_ID,
            received_datetime_utc=received,
            sender="noreply@datashare.maps.vic.gov.au",
            subject=READY_SUBJECT,
        )
        graph = _FakeGraph([metadata], {MESSAGE_ID: _mime(ARTIFACT_URL)})
        session = _FakeSession()
        events = []

        with tempfile.TemporaryDirectory() as output_dir:
            config = read_mailbox.AcquisitionConfig(
                mailbox="automations@vegetationlink.com.au",
                folder="Inbox",
                allowed_senders=("noreply@datashare.maps.vic.gov.au",),
                allowed_order_ids=("OK0VUZ",),
                allowed_hosts=("s3.ap-southeast-2.amazonaws.com",),
                lookback_days=15,
                max_bytes=10 * 1024**3,
                connect_timeout_seconds=10,
                read_timeout_seconds=60,
                progress_interval_seconds=5,
                max_redirects=5,
                fingerprint_hex_chars=16,
                allow_order_id_mismatch=False,
                output_dir=Path(output_dir),
            )
            result = read_mailbox.run_acquisition(
                config,
                {
                    "O365_AUTH_ID": "seed-client-id",
                    "O365_AUTH_SECRET": "seed-client-secret",
                    "TENANT_ID": "seed-tenant-id",
                },
                graph_factory=lambda **kwargs: graph,
                session_factory=lambda: session,
                event_sink=events.append,
            )

            self.assertEqual(len(PAYLOAD), result.byte_count)
            self.assertEqual(hashlib.sha256(PAYLOAD).hexdigest(), result.sha256)
            self.assertEqual(PAYLOAD, result.path.read_bytes())
            self.assertEqual([MESSAGE_ID], graph.mime_requests)
            self.assertEqual(1, len(session.calls))
            self.assertTrue(session.response.closed)
            _, request_kwargs, request_auth, trust_env = session.calls[0]
            self.assertIsNone(request_auth)
            self.assertFalse(trust_env)
            self.assertFalse(request_kwargs["allow_redirects"])
            self.assertEqual((10, 60), request_kwargs["timeout"])

        rendered = repr(events)
        self.assertIn("OK0VUZ", rendered)
        self.assertIn("2026-09-07T01:02:03+00:00", rendered)
        self.assertIn("n*****y@datashare.maps.vic.gov.au", rendered)
        self.assertIn("message_fingerprint", rendered)
        self.assertIn("s3.ap-southeast-2.amazonaws.com", rendered)
        self.assertIn("path_fingerprint", rendered)
        self.assertIn(str(len(PAYLOAD)), rendered)
        self.assertIn(hashlib.sha256(PAYLOAD).hexdigest(), rendered)
        for forbidden in (
            "seed-client-id",
            "seed-client-secret",
            "seed-tenant-id",
            READY_SUBJECT,
            BODY_MARKER,
            MESSAGE_ID,
            ARTIFACT_URL,
            "private-query-marker",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_rejected_newest_target_is_closed_and_never_falls_back(self):
        read_mailbox = _import_read_mailbox_without_legacy_effects()
        self.assertTrue(
            callable(getattr(read_mailbox, "run_acquisition", None)),
            "run_acquisition must expose the production tracer seam",
        )

        from vicmap_acquire.graph import MessageMetadata

        older = MessageMetadata(
            graph_message_id=OLDER_MESSAGE_ID,
            received_datetime_utc=datetime(2026, 9, 6, tzinfo=timezone.utc),
            sender="noreply@datashare.maps.vic.gov.au",
            subject=READY_SUBJECT,
        )
        newest = MessageMetadata(
            graph_message_id=MESSAGE_ID,
            received_datetime_utc=datetime(2026, 9, 7, tzinfo=timezone.utc),
            sender="noreply@datashare.maps.vic.gov.au",
            subject=READY_SUBJECT,
        )
        graph = _FakeGraph(
            [older, newest],
            {
                OLDER_MESSAGE_ID: _mime(ARTIFACT_URL),
                MESSAGE_ID: _mime(
                    "https://attacker.example/Order_OK0VUZ.zip?private=marker"
                ),
            },
        )
        session = _FakeSession()
        events = []

        with tempfile.TemporaryDirectory() as output_dir:
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
                output_dir=Path(output_dir),
            )
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.run_acquisition(
                    config,
                    {
                        "O365_AUTH_ID": "seed-client-id",
                        "O365_AUTH_SECRET": "seed-client-secret",
                        "TENANT_ID": "seed-tenant-id",
                    },
                    graph_factory=lambda **kwargs: graph,
                    session_factory=lambda: session,
                    event_sink=events.append,
                )

        self.assertEqual("download_url_rejected", caught.exception.code)
        self.assertEqual([], session.calls)
        self.assertEqual("failure", events[-1]["event"])
        self.assertEqual("download_url_rejected", events[-1]["reason"])
        self.assertNotIn(ARTIFACT_URL, repr(events))


VALID_TOML = """\
[mailbox]
address = "automations@vegetationlink.com.au"
folder = "Inbox"
allowed_senders = ["noreply@datashare.maps.vic.gov.au"]
allowed_order_ids = ["OK0VUZ"]
lookback_days = 15
allow_order_id_mismatch = false

[download]
allowed_hosts = ["s3.ap-southeast-2.amazonaws.com"]
max_bytes = 10737418240
connect_timeout_seconds = 10
read_timeout_seconds = 60
progress_interval_seconds = 5
max_redirects = 5
fingerprint_hex_chars = 16
output_dir = "artifacts"
"""


class ConfigurationTest(unittest.TestCase):
    def _write_policy(self, directory: str, text: str = VALID_TOML) -> Path:
        path = Path(directory) / "policy.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_valid_policy_loads_locked_allowlists_and_defaults(self):
        import read_mailbox

        with tempfile.TemporaryDirectory() as directory:
            try:
                config = read_mailbox.load_config(self._write_policy(directory))
            except read_mailbox.AcquisitionFailure:
                config = None

            self.assertIsNotNone(
                config,
                "the exact reviewable Phase 1 policy must load successfully",
            )
            self.assertEqual("automations@vegetationlink.com.au", config.mailbox)
            self.assertEqual("Inbox", config.folder)
            self.assertEqual(
                ("noreply@datashare.maps.vic.gov.au",), config.allowed_senders
            )
            self.assertEqual(("OK0VUZ",), config.allowed_order_ids)
            self.assertEqual(
                ("s3.ap-southeast-2.amazonaws.com",), config.allowed_hosts
            )
            self.assertEqual(15, config.lookback_days)
            self.assertEqual(10 * 1024**3, config.max_bytes)
            self.assertEqual(10, config.connect_timeout_seconds)
            self.assertEqual(60, config.read_timeout_seconds)
            self.assertEqual(5, config.progress_interval_seconds)
            self.assertEqual(5, config.max_redirects)
            self.assertEqual(16, config.fingerprint_hex_chars)
            self.assertFalse(config.allow_order_id_mismatch)
            self.assertEqual(Path(directory) / "artifacts", config.output_dir)

    def test_invalid_policy_cases_fail_closed_without_constructing_adapters(self):
        import read_mailbox

        cases = {
            "unknown top-level": VALID_TOML + "\nextra = true\n",
            "unknown nested": VALID_TOML.replace(
                "folder = \"Inbox\"", 'folder = "Inbox"\nextra = true'
            ),
            "missing value": VALID_TOML.replace("lookback_days = 15\n", ""),
            "blank mailbox": VALID_TOML.replace(
                'address = "automations@vegetationlink.com.au"', 'address = "   "'
            ),
            "empty allowlist": VALID_TOML.replace(
                'allowed_senders = ["noreply@datashare.maps.vic.gov.au"]',
                "allowed_senders = []",
            ),
            "boolean integer": VALID_TOML.replace(
                "lookback_days = 15", "lookback_days = true"
            ),
            "non-positive integer": VALID_TOML.replace(
                "max_bytes = 10737418240", "max_bytes = 0"
            ),
            "malformed host": VALID_TOML.replace(
                'allowed_hosts = ["s3.ap-southeast-2.amazonaws.com"]',
                'allowed_hosts = ["https://s3.ap-southeast-2.amazonaws.com"]',
            ),
            "unsafe output": VALID_TOML.replace(
                'output_dir = "artifacts"', 'output_dir = "../outside"'
            ),
        }
        for label, policy_text in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                    read_mailbox.load_config(self._write_policy(directory, policy_text))
                self.assertEqual("config_invalid", caught.exception.code)

    def test_invalid_policy_stops_main_before_credentials_or_network(self):
        import read_mailbox

        marker = "raw-invalid-policy-marker"
        invalid = VALID_TOML.replace(
            'address = "automations@vegetationlink.com.au"', f'address = "{marker}"'
        ).replace("lookback_days = 15", "lookback_days = false")
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            policy = self._write_policy(directory, invalid)
            with (
                patch.object(read_mailbox, "run_acquisition") as run,
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(output),
            ):
                result = read_mailbox.main(["--config", str(policy)])
        self.assertEqual(1, result)
        run.assert_not_called()
        self.assertIn("config_invalid", output.getvalue())
        self.assertNotIn(marker, output.getvalue())

    def test_blank_credentials_fail_before_graph_or_http_construction(self):
        import read_mailbox

        graph_factory = unittest.mock.Mock()
        session_factory = unittest.mock.Mock()
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
                output_dir=Path(directory) / "artifacts",
            )
            for name in ("O365_AUTH_ID", "O365_AUTH_SECRET", "TENANT_ID"):
                credentials = {
                    "O365_AUTH_ID": "opaque-id",
                    "O365_AUTH_SECRET": "opaque-secret",
                    "TENANT_ID": "opaque-tenant",
                }
                credentials[name] = "   "
                with self.subTest(name=name):
                    with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                        read_mailbox.run_acquisition(
                            config,
                            credentials,
                            graph_factory=graph_factory,
                            session_factory=session_factory,
                        )
                    self.assertEqual("config_invalid", caught.exception.code)
        graph_factory.assert_not_called()
        session_factory.assert_not_called()

    def test_import_constructs_no_clients_and_creates_no_output(self):
        import O365
        import requests

        sys.modules.pop("read_mailbox", None)
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "must-not-exist"
            with (
                patch.object(O365, "Account") as account,
                patch.object(requests, "Session") as session,
                patch("pathlib.Path.mkdir") as mkdir,
            ):
                imported = importlib.import_module("read_mailbox")
            self.assertTrue(callable(imported.main))
            account.assert_not_called()
            session.assert_not_called()
            mkdir.assert_not_called()
            self.assertFalse(sentinel.exists())


if __name__ == "__main__":
    unittest.main()
