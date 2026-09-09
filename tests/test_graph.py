from __future__ import annotations

import contextlib
import hashlib
import importlib
import inspect
import io
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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
AUTH_RESULTS_PASS = (
    "spf=pass smtp.mailfrom=maps.vic.gov.au;"
    "dkim=pass (signature was verified) header.d=maps.vic.gov.au;"
    "dmarc=pass action=none header.from=datashare.maps.vic.gov.au;"
    "compauth=pass reason=100"
)


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
        f"Authentication-Results: {AUTH_RESULTS_PASS}\r\n"
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
                output_dir=Path(output_dir) / "artifacts",
                required_authentication_results=("dkim", "dmarc", "compauth"),
                allowed_url_prefixes=("https://s3.ap-southeast-2.amazonaws.com/private/",),
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
                output_dir=Path(output_dir) / "artifacts",
                required_authentication_results=("dkim", "dmarc", "compauth"),
                allowed_url_prefixes=("https://s3.ap-southeast-2.amazonaws.com/private/",),
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
required_authentication_results = ["dkim", "dmarc", "compauth"]

[download]
allowed_hosts = ["s3.ap-southeast-2.amazonaws.com"]
max_bytes = 10737418240
connect_timeout_seconds = 10
read_timeout_seconds = 60
progress_interval_seconds = 5
max_redirects = 5
fingerprint_hex_chars = 16
output_dir = "artifacts"
allowed_url_prefixes = ["https://s3.ap-southeast-2.amazonaws.com/private/"]
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
            self.assertTrue(config.required_authentication_results)
            self.assertIn("dkim", config.required_authentication_results)
            self.assertTrue(config.allowed_url_prefixes)

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
                required_authentication_results=("dkim", "dmarc", "compauth"),
                allowed_url_prefixes=("https://s3.ap-southeast-2.amazonaws.com/private/",),
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


class _AuthenticationFolder:
    def __init__(self):
        self.message_calls = []

    def get_messages(self, *args, **kwargs):
        self.message_calls.append((args, kwargs))
        return ()


class _AuthenticationMailbox:
    def __init__(self, folder=None, failure=None):
        self.folder = folder or _AuthenticationFolder()
        self.failure = failure
        self.folder_calls = []

    def get_folder(self, *args, **kwargs):
        self.folder_calls.append((args, kwargs))
        if self.failure is not None:
            raise self.failure
        return self.folder


class _AuthenticationAccount:
    def __init__(
        self,
        *,
        authenticated=False,
        authentication_result=True,
        authentication_failure=None,
        mailbox=None,
    ):
        self.is_authenticated = authenticated
        self.authentication_result = authentication_result
        self.authentication_failure = authentication_failure
        self.mailbox_object = mailbox or _AuthenticationMailbox()
        self.authenticate_calls = []
        self.mailbox_calls = []

    def authenticate(self, *args, **kwargs):
        self.authenticate_calls.append((args, kwargs))
        if self.authentication_failure is not None:
            raise self.authentication_failure
        return self.authentication_result

    def mailbox(self, *args, **kwargs):
        self.mailbox_calls.append((args, kwargs))
        return self.mailbox_object


class GraphAuthenticationBoundaryTest(unittest.TestCase):
    def _require_task_api(self):
        from vicmap_acquire import graph

        self.assertTrue(
            hasattr(graph.GraphMailbox, "authenticate_and_confirm"),
            "Task 1 must expose an explicit authentication confirmation boundary",
        )
        self.assertTrue(hasattr(graph, "GraphAuthenticationFailed"))
        self.assertTrue(hasattr(graph, "MailboxAccessFailed"))

    def _construct(self, account):
        from O365.utils.token import MemoryTokenBackend
        from vicmap_acquire.graph import GraphMailbox

        construction = []

        def account_factory(*args, **kwargs):
            construction.append((args, kwargs))
            return account

        adapter = GraphMailbox(
            credentials=("seed-client-id", "seed-client-secret"),
            tenant_id="seed-tenant-id",
            mailbox_address="automations@vegetationlink.com.au",
            account_factory=account_factory,
        )
        self.assertEqual(1, len(construction))
        args, kwargs = construction[0]
        self.assertEqual((("seed-client-id", "seed-client-secret"),), args)
        self.assertEqual("credentials", kwargs["auth_flow_type"])
        self.assertEqual("seed-tenant-id", kwargs["tenant_id"])
        self.assertIsInstance(kwargs["token_backend"], MemoryTokenBackend)
        return adapter

    def test_fresh_authentication_uses_default_scope_and_exact_mailbox(self):
        self._require_task_api()
        account = _AuthenticationAccount()
        adapter = self._construct(account)

        self.assertEqual(
            "automations@vegetationlink.com.au",
            adapter.authenticate_and_confirm(),
        )
        self.assertEqual(
            [
                (
                    (),
                    {
                        "requested_scopes": [
                            "https://graph.microsoft.com/.default"
                        ]
                    },
                )
            ],
            account.authenticate_calls,
        )
        self.assertEqual(
            [((), {"resource": "automations@vegetationlink.com.au"})],
            account.mailbox_calls,
        )
        self.assertEqual(
            [((), {"folder_name": "Inbox"})],
            account.mailbox_object.folder_calls,
        )
        self.assertEqual([], account.mailbox_object.folder.message_calls)

    def test_existing_authentication_skips_fresh_authentication(self):
        self._require_task_api()
        account = _AuthenticationAccount(authenticated=True)
        adapter = self._construct(account)

        self.assertEqual(
            "automations@vegetationlink.com.au",
            adapter.authenticate_and_confirm(),
        )
        self.assertEqual([], account.authenticate_calls)

    def test_false_authentication_fails_before_mailbox_access(self):
        self._require_task_api()
        from vicmap_acquire.graph import GraphAuthenticationFailed

        account = _AuthenticationAccount(authentication_result=False)
        adapter = self._construct(account)
        with self.assertRaises(GraphAuthenticationFailed) as caught:
            adapter.authenticate_and_confirm()

        self.assertEqual("authentication", caught.exception.stage)
        self.assertEqual("authentication_failed", caught.exception.reason)
        self.assertEqual([], account.mailbox_calls)

    def test_provider_failures_are_typed_and_disclosure_safe(self):
        self._require_task_api()
        from vicmap_acquire.graph import (
            GraphAuthenticationFailed,
            MailboxAccessFailed,
        )

        raw_marker = "raw-provider-secret-marker"
        output = io.StringIO()
        auth_account = _AuthenticationAccount(
            authentication_failure=RuntimeError(raw_marker)
        )
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            with self.assertRaises(GraphAuthenticationFailed) as auth_caught:
                self._construct(auth_account).authenticate_and_confirm()

        mailbox = _AuthenticationMailbox(failure=RuntimeError(raw_marker))
        mailbox_account = _AuthenticationAccount(
            authenticated=True,
            mailbox=mailbox,
        )
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            with self.assertRaises(MailboxAccessFailed) as mailbox_caught:
                self._construct(mailbox_account).authenticate_and_confirm()

        rendered = output.getvalue() + repr(auth_caught.exception) + repr(
            mailbox_caught.exception
        )
        self.assertNotIn(raw_marker, rendered)
        self.assertNotIn("seed-client-id", rendered)
        self.assertNotIn("seed-client-secret", rendered)
        self.assertEqual("mailbox_access_failed", mailbox_caught.exception.reason)

    def test_blank_runtime_inputs_stop_before_account_construction(self):
        self._require_task_api()
        from vicmap_acquire.graph import GraphAuthenticationFailed, GraphMailbox

        valid = {
            "credentials": ("seed-client-id", "seed-client-secret"),
            "tenant_id": "seed-tenant-id",
            "mailbox_address": "automations@vegetationlink.com.au",
        }
        for field in ("credentials", "tenant_id", "mailbox_address"):
            values = dict(valid)
            values[field] = ("seed-client-id", " ") if field == "credentials" else " "
            factory = unittest.mock.Mock()
            with self.subTest(field=field):
                with self.assertRaises(GraphAuthenticationFailed):
                    GraphMailbox(account_factory=factory, **values)
                factory.assert_not_called()


class _MetadataQuery:
    def __init__(self, attribute):
        self.attribute = attribute
        self.cutoff = None
        self.selected = None

    def greater_equal(self, cutoff):
        self.cutoff = cutoff
        return self

    def select(self, *fields):
        self.selected = fields
        return self


class _MetadataMessage:
    def __init__(self, message_id, received, sender, subject, mime=b"mime-bytes"):
        self.object_id = message_id
        self.received = received
        self.sender = SimpleNamespace(address=sender) if sender is not None else None
        self.subject = subject
        self.mime = mime
        self.mime_calls = 0

    def get_mime_content(self):
        self.mime_calls += 1
        if isinstance(self.mime, Exception):
            raise self.mime
        return self.mime


class _MetadataFolder:
    def __init__(self, messages=(), paging_failure=None):
        self.messages = list(messages)
        self.paging_failure = paging_failure
        self.query = None
        self.get_messages_calls = []
        self.get_message_calls = []
        self.yielded_ids = []

    def new_query(self, attribute):
        self.query = _MetadataQuery(attribute)
        return self.query

    def get_messages(self, *args, **kwargs):
        self.get_messages_calls.append((args, kwargs))

        def pages():
            for message in self.messages:
                if message.received >= self.query.cutoff:
                    self.yielded_ids.append(message.object_id)
                    yield message
            if self.paging_failure is not None:
                raise self.paging_failure

        return pages()

    def get_message(self, *args, **kwargs):
        self.get_message_calls.append((args, kwargs))
        object_id = kwargs["object_id"]
        return next(message for message in self.messages if message.object_id == object_id)


class GraphMetadataBoundaryTest(unittest.TestCase):
    def _require_task_api(self):
        from vicmap_acquire import graph

        self.assertTrue(
            hasattr(graph.GraphMailbox, "iter_message_metadata"),
            "Task 2 must expose the metadata-only pagination boundary",
        )
        self.assertTrue(hasattr(graph.GraphMailbox, "get_message_mime"))

    def _adapter(self, folder):
        from vicmap_acquire.graph import GraphMailbox

        mailbox = _AuthenticationMailbox(folder=folder)
        account = _AuthenticationAccount(authenticated=True, mailbox=mailbox)
        adapter = GraphMailbox(
            credentials=("seed-client-id", "seed-client-secret"),
            tenant_id="seed-tenant-id",
            mailbox_address="automations@vegetationlink.com.au",
            account_factory=lambda *args, **kwargs: account,
        )
        return adapter

    def test_inclusive_cutoff_selects_minimal_fields_and_exhausts_pages(self):
        self._require_task_api()
        cutoff = datetime(2026, 9, 1, tzinfo=timezone.utc)
        messages = [
            _MetadataMessage(
                "before-id",
                cutoff - timedelta(microseconds=1),
                "before@example.test",
                "before",
            ),
            _MetadataMessage(
                "equal-id",
                cutoff,
                "equal@example.test",
                "equal",
            ),
            _MetadataMessage(
                "later-page-id",
                cutoff + timedelta(microseconds=1),
                "later@example.test",
                "later",
            ),
        ]
        folder = _MetadataFolder(messages)
        metadata = list(self._adapter(folder).iter_message_metadata(cutoff))

        self.assertEqual(["equal-id", "later-page-id"], [m.graph_message_id for m in metadata])
        self.assertEqual("receivedDateTime", folder.query.attribute)
        self.assertIs(cutoff, folder.query.cutoff)
        self.assertEqual(
            ("id", "receivedDateTime", "from", "subject"),
            folder.query.selected,
        )
        self.assertEqual(
            [((), {"limit": None, "batch": 999, "query": folder.query})],
            folder.get_messages_calls,
        )
        self.assertEqual(["equal-id", "later-page-id"], folder.yielded_ids)
        self.assertEqual([0, 0, 0], [message.mime_calls for message in messages])

    def test_empty_metadata_iteration_yields_no_fabricated_values(self):
        self._require_task_api()
        folder = _MetadataFolder()
        cutoff = datetime(2026, 9, 1, tzinfo=timezone.utc)
        self.assertEqual([], list(self._adapter(folder).iter_message_metadata(cutoff)))

    def test_naive_cutoff_and_malformed_provider_metadata_fail_closed(self):
        self._require_task_api()
        from vicmap_acquire.graph import GraphScanFailed

        with self.assertRaises(GraphScanFailed):
            list(
                self._adapter(_MetadataFolder()).iter_message_metadata(
                    datetime(2026, 9, 1)
                )
            )

        malformed = (
            _MetadataMessage("", datetime(2026, 9, 1, tzinfo=timezone.utc), "a@b", "s"),
            _MetadataMessage("id", None, "a@b", "s"),
            _MetadataMessage("id", datetime(2026, 9, 1), "a@b", "s"),
            _MetadataMessage("id", datetime(2026, 9, 1, tzinfo=timezone.utc), None, "s"),
            _MetadataMessage("id", datetime(2026, 9, 1, tzinfo=timezone.utc), "a@b", None),
        )
        for message in malformed:
            with self.subTest(message_id=message.object_id, received=message.received):
                folder = _MetadataFolder([message])
                with self.assertRaises(GraphScanFailed):
                    list(
                        self._adapter(folder).iter_message_metadata(
                            datetime(2026, 8, 1, tzinfo=timezone.utc)
                        )
                    )

    def test_selective_mime_fetches_by_complete_id_only_on_explicit_call(self):
        self._require_task_api()
        message = _MetadataMessage(
            "complete-opaque-id",
            datetime(2026, 9, 1, tzinfo=timezone.utc),
            "sender@example.test",
            "subject",
            mime=b"selective-mime",
        )
        folder = _MetadataFolder([message])
        adapter = self._adapter(folder)
        adapter.authenticate_and_confirm()

        self.assertEqual(0, message.mime_calls)
        self.assertEqual(b"selective-mime", adapter.get_message_mime("complete-opaque-id"))
        self.assertEqual([((), {"object_id": "complete-opaque-id"})], folder.get_message_calls)
        self.assertEqual(1, message.mime_calls)

    def test_paging_and_mime_provider_errors_do_not_escape(self):
        self._require_task_api()
        from vicmap_acquire.graph import GraphScanFailed

        raw_marker = "raw-graph-page-or-mime-marker"
        output = io.StringIO()
        paging_folder = _MetadataFolder(paging_failure=RuntimeError(raw_marker))
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            with self.assertRaises(GraphScanFailed) as page_caught:
                list(
                    self._adapter(paging_folder).iter_message_metadata(
                        datetime(2026, 9, 1, tzinfo=timezone.utc)
                    )
                )

        mime_message = _MetadataMessage(
            "mime-id",
            datetime(2026, 9, 1, tzinfo=timezone.utc),
            "sender@example.test",
            "subject",
            mime=RuntimeError(raw_marker),
        )
        mime_adapter = self._adapter(_MetadataFolder([mime_message]))
        mime_adapter.authenticate_and_confirm()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            with self.assertRaises(GraphScanFailed) as mime_caught:
                mime_adapter.get_message_mime("mime-id")

        rendered = output.getvalue() + repr(page_caught.exception) + repr(
            mime_caught.exception
        )
        self.assertNotIn(raw_marker, rendered)

    def test_adapter_source_contains_no_mailbox_mutation_calls(self):
        self._require_task_api()
        from vicmap_acquire.graph import GraphMailbox

        source = inspect.getsource(GraphMailbox)
        for mutation in (
            ".delete(",
            ".move(",
            ".mark_as_read(",
            ".mark_as_unread(",
            ".add_category(",
        ):
            self.assertNotIn(mutation, source)


if __name__ == "__main__":
    unittest.main()
