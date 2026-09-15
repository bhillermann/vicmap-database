from __future__ import annotations

import contextlib
import hashlib
import importlib
import io
import json
import tempfile
import unicodedata
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


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


def _policy_kwargs(output_dir: Path, **overrides: object) -> dict[str, object]:
    """Build a complete, valid ``AcquisitionConfig`` kwargs mapping.

    ``overrides`` replaces individual fields so malformed-policy tests can
    mutate exactly one field while every other field remains valid.
    """

    base: dict[str, object] = dict(
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
        output_dir=output_dir,
        required_authentication_results=("dkim", "dmarc", "compauth"),
        allowed_url_prefixes=("https://s3.ap-southeast-2.amazonaws.com/private/",),
    )
    base.update(overrides)
    return base


def _toml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    raise TypeError(f"unsupported TOML scalar: {value!r}")


def _toml_list(values) -> str:
    return "[" + ", ".join(_toml_scalar(value) for value in values) + "]"


def _render_policy_toml(kwargs: dict[str, object], output_value: str) -> str:
    """Render the exact TOML shape ``load_config`` expects from ``kwargs``."""

    return (
        "[mailbox]\n"
        f'address = {_toml_scalar(kwargs["mailbox"])}\n'
        f'folder = {_toml_scalar(kwargs["folder"])}\n'
        f'allowed_senders = {_toml_list(kwargs["allowed_senders"])}\n'
        f'allowed_order_ids = {_toml_list(kwargs["allowed_order_ids"])}\n'
        f'lookback_days = {_toml_scalar(kwargs["lookback_days"])}\n'
        f'allow_order_id_mismatch = {_toml_scalar(kwargs["allow_order_id_mismatch"])}\n'
        "required_authentication_results = "
        f'{_toml_list(kwargs["required_authentication_results"])}\n'
        "\n"
        "[download]\n"
        f'allowed_hosts = {_toml_list(kwargs["allowed_hosts"])}\n'
        f'max_bytes = {_toml_scalar(kwargs["max_bytes"])}\n'
        f'connect_timeout_seconds = {_toml_scalar(kwargs["connect_timeout_seconds"])}\n'
        f'read_timeout_seconds = {_toml_scalar(kwargs["read_timeout_seconds"])}\n'
        "progress_interval_seconds = "
        f'{_toml_scalar(kwargs["progress_interval_seconds"])}\n'
        f'max_redirects = {_toml_scalar(kwargs["max_redirects"])}\n'
        f'fingerprint_hex_chars = {_toml_scalar(kwargs["fingerprint_hex_chars"])}\n'
        f'output_dir = {_toml_scalar(output_value)}\n'
        f'allowed_url_prefixes = {_toml_list(kwargs["allowed_url_prefixes"])}\n'
    )


# Each case overrides exactly one policy field (or, for the last case, only
# the TOML-only ``output_dir`` string) and must be rejected as
# ``config_invalid`` through both ``load_config`` and a direct
# ``AcquisitionConfig`` passed to ``run_acquisition`` -- the "one complete
# policy validator used by both" requirement from verification gap G-02.
_POLICY_MALFORMED_CASES: dict[str, tuple[dict[str, object], str | None]] = {
    "non-inbox folder": ({"folder": "Archive"}, None),
    "sender missing exactly one at-sign": (
        {"allowed_senders": ("not-an-email",)},
        None,
    ),
    "order id has a non-alphanumeric character": (
        {"allowed_order_ids": ("OK-0VUZ",)},
        None,
    ),
    "host has an uppercase letter": (
        {"allowed_hosts": ("S3.ap-southeast-2.amazonaws.com",)},
        None,
    ),
    "host contains a scheme": (
        {"allowed_hosts": ("https://s3.ap-southeast-2.amazonaws.com",)},
        None,
    ),
    "url prefix hostname is not allowlisted": (
        {"allowed_url_prefixes": ("https://attacker.example/private/",)},
        None,
    ),
    "duplicate sender entry": (
        {
            "allowed_senders": (
                "noreply@datashare.maps.vic.gov.au",
                "noreply@datashare.maps.vic.gov.au",
            )
        },
        None,
    ),
    "empty sender allowlist": ({"allowed_senders": ()}, None),
    "authentication method outside the closed set": (
        {"required_authentication_results": ("dkim", "not-a-real-method")},
        None,
    ),
    "authentication methods missing dkim": (
        {"required_authentication_results": ("dmarc", "compauth")},
        None,
    ),
    "non-bool order id mismatch flag": ({"allow_order_id_mismatch": 1}, None),
    "output directory name is not recognised": ({}, "nested/mydir"),
}


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
            "artifact_checksum_mismatch": "artifact_verify",
            "provenance_unavailable": "artifact_verify",
            "archive_traversal_rejected": "extraction",
            "archive_unsafe_member_rejected": "extraction",
            "archive_ceiling_exceeded": "extraction",
            "archive_unreadable": "extraction",
            "run_directory_write_failed": "extraction",
            "unsupported_format": "discovery",
            "delivery_empty": "discovery",
            "layer_unreadable": "discovery",
            "layer_empty": "discovery",
            "geometry_type_unresolved": "discovery",
            "crs_unresolved": "discovery",
            "layer_schema_incomplete": "discovery",
            "table_name_invalid": "naming",
            "table_name_collision": "naming",
            "manifest_write_failed": "manifest",
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

    def test_fingerprint_length_is_configurable_within_bounds(self):
        for length in (8, 16, 64):
            with self.subTest(length=length):
                value = evidence.fingerprint("opaque-value", length)
                self.assertEqual(length, len(value))
                self.assertRegex(value, r"^[0-9a-f]+$")
        for length in (7, 65):
            with self.subTest(length=length):
                with self.assertRaises(ValueError):
                    evidence.fingerprint("opaque-value", length)

    def test_download_target_fingerprint_length_is_configurable(self):
        short = "a" * 8
        event = evidence.SuccessEvent.download_target(
            approved_hostname="s3.ap-southeast-2.amazonaws.com",
            path_fingerprint=short,
            fingerprint_hex_chars=8,
        )
        self.assertEqual(short, dict(event)["path_fingerprint"])
        with self.assertRaises(ValueError):
            evidence.SuccessEvent.download_target(
                approved_hostname="s3.ap-southeast-2.amazonaws.com",
                path_fingerprint="a" * 16,
                fingerprint_hex_chars=8,
            )

        long = "b" * 16
        event16 = evidence.SuccessEvent.download_target(
            approved_hostname="s3.ap-southeast-2.amazonaws.com",
            path_fingerprint=long,
            fingerprint_hex_chars=16,
        )
        self.assertEqual(long, dict(event16)["path_fingerprint"])
        with self.assertRaises(ValueError):
            evidence.SuccessEvent.download_target(
                approved_hostname="s3.ap-southeast-2.amazonaws.com",
                path_fingerprint="a" * 8,
                fingerprint_hex_chars=16,
            )

    def test_candidate_selected_message_fingerprint_length_is_configurable(self):
        received = datetime(2026, 9, 7, tzinfo=timezone.utc)
        for length in (8, 16, 64):
            with self.subTest(length=length):
                event = evidence.SuccessEvent.candidate_selected(
                    order_id="OK0VUZ",
                    received_at=received,
                    sender="noreply@datashare.maps.vic.gov.au",
                    graph_message_id="opaque-id",
                    fingerprint_hex_chars=length,
                )
                self.assertEqual(length, len(dict(event)["message_fingerprint"]))

    def test_safe_failure_fingerprint_length_is_configurable(self):
        failure = evidence.SafeFailure(
            evidence.ReasonCode.DOWNLOAD_EXPIRED_OR_MISSING,
            message_fingerprint="a" * 8,
            path_fingerprint="b" * 8,
            fingerprint_hex_chars=8,
        )
        payload = dict(failure)
        self.assertEqual("a" * 8, payload["message_fingerprint"])
        self.assertEqual("b" * 8, payload["path_fingerprint"])
        with self.assertRaises(ValueError):
            evidence.SafeFailure(
                evidence.ReasonCode.DOWNLOAD_EXPIRED_OR_MISSING,
                message_fingerprint="a" * 16,
                fingerprint_hex_chars=8,
            )

    def test_phase_2_reason_codes_extend_the_closed_vocabulary(self):
        expected_additions = {
            "artifact_checksum_mismatch": "artifact_verify",
            "provenance_unavailable": "artifact_verify",
            "archive_traversal_rejected": "extraction",
            "archive_unsafe_member_rejected": "extraction",
            "archive_ceiling_exceeded": "extraction",
            "archive_unreadable": "extraction",
            "run_directory_write_failed": "extraction",
            "unsupported_format": "discovery",
            "delivery_empty": "discovery",
            "layer_unreadable": "discovery",
            "layer_empty": "discovery",
            "geometry_type_unresolved": "discovery",
            "crs_unresolved": "discovery",
            "layer_schema_incomplete": "discovery",
            "table_name_invalid": "naming",
            "table_name_collision": "naming",
            "manifest_write_failed": "manifest",
        }
        vocabulary = evidence.reason_stage_vocabulary()
        for reason, stage in expected_additions.items():
            with self.subTest(reason=reason):
                self.assertEqual(stage, vocabulary.get(reason))
        self.assertEqual(len(expected_additions), 17)
        self.assertLessEqual(set(expected_additions), set(vocabulary))

    def test_artifact_verified_rejects_unsafe_scalars(self):
        valid_sha256 = hashlib.sha256(b"tracer").hexdigest()
        event = evidence.SuccessEvent.artifact_verified(
            order_id="TRACER1", byte_count=12345, sha256=valid_sha256
        )
        self.assertEqual(
            {
                "event": "artifact_verified",
                "order_id": "TRACER1",
                "byte_count": 12345,
                "sha256": valid_sha256,
            },
            dict(event),
        )
        with self.assertRaises(ValueError):
            evidence.SuccessEvent.artifact_verified(
                order_id="TRACER1", byte_count=12345, sha256="not-a-digest"
            )
        with self.assertRaises(ValueError):
            evidence.SuccessEvent.artifact_verified(
                order_id="TRACER1", byte_count=-1, sha256=valid_sha256
            )
        with self.assertRaises(ValueError):
            evidence.SuccessEvent.artifact_verified(
                order_id="not a safe order id!", byte_count=1, sha256=valid_sha256
            )

    def test_archive_extracted_rejects_unsafe_scalars(self):
        event = evidence.SuccessEvent.archive_extracted(
            order_id="TRACER1",
            member_count=3,
            total_byte_count=4096,
            run_path_fingerprint="a" * 16,
        )
        self.assertEqual(
            {
                "event": "archive_extracted",
                "order_id": "TRACER1",
                "member_count": 3,
                "total_byte_count": 4096,
                "run_path_fingerprint": "a" * 16,
            },
            dict(event),
        )
        with self.assertRaises(ValueError):
            evidence.SuccessEvent.archive_extracted(
                order_id="TRACER1",
                member_count=-1,
                total_byte_count=4096,
                run_path_fingerprint="a" * 16,
            )
        with self.assertRaises(ValueError):
            evidence.SuccessEvent.archive_extracted(
                order_id="TRACER1",
                member_count=3,
                total_byte_count=4096,
                run_path_fingerprint="not-hex!!",
            )

    def test_manifest_completed_rejects_unsafe_scalars(self):
        manifest_sha256 = hashlib.sha256(b"manifest").hexdigest()
        event = evidence.SuccessEvent.manifest_completed(
            order_id="TRACER1",
            layer_count=1,
            companion_count=2,
            target_tables=("vmadd_address",),
            manifest_sha256=manifest_sha256,
            run_path_fingerprint="b" * 16,
        )
        self.assertEqual(
            {
                "event": "manifest_completed",
                "order_id": "TRACER1",
                "layer_count": 1,
                "companion_count": 2,
                "target_tables": ["vmadd_address"],
                "manifest_sha256": manifest_sha256,
                "run_path_fingerprint": "b" * 16,
            },
            dict(event),
        )
        with self.assertRaises(ValueError):
            evidence.SuccessEvent.manifest_completed(
                order_id="TRACER1",
                layer_count=1,
                companion_count=2,
                target_tables=("Not-Safe!",),
                manifest_sha256=manifest_sha256,
                run_path_fingerprint="b" * 16,
            )
        with self.assertRaises(ValueError):
            evidence.SuccessEvent.manifest_completed(
                order_id="TRACER1",
                layer_count=1,
                companion_count=2,
                target_tables=("vmadd_address",),
                manifest_sha256="not-a-digest",
                run_path_fingerprint="b" * 16,
            )

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
                output_dir=Path(directory) / "artifacts",
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
        fingerprint_hex_chars: int = 16,
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
            fingerprint_hex_chars=fingerprint_hex_chars,
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
            [
                "candidate_selected",
                "artifact_verified",
                "download_target",
                "artifact_finalized",
            ],
            [event["event"] for event in events],
        )
        self.assertEqual(1, len(session.calls))

    def test_end_to_end_fingerprint_length_is_threaded_through_evidence(self):
        import read_mailbox
        from vicmap_acquire.graph import MessageMetadata

        for length in (8, 16, 64):
            with self.subTest(fingerprint_hex_chars=length):
                message_id = f"opaque-length-{length}-message-id"
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
                graph = _E2EGraph(
                    metadata, {message_id: _e2e_mime(artifact_url=artifact_url)}
                )
                session = _E2ESession(payload)
                events = []

                with tempfile.TemporaryDirectory() as directory:
                    output_dir = Path(directory) / "artifacts"
                    config = self._config(output_dir, fingerprint_hex_chars=length)
                    result = read_mailbox.run_acquisition(
                        config,
                        self._credentials(),
                        graph_factory=lambda **kwargs: graph,
                        session_factory=lambda: session,
                        event_sink=events.append,
                    )

                self.assertEqual(len(payload), result.byte_count)
                by_event = {event["event"]: event for event in events}
                self.assertEqual(
                    length, len(by_event["candidate_selected"]["message_fingerprint"])
                )
                self.assertEqual(
                    length, len(by_event["download_target"]["path_fingerprint"])
                )

    def test_fingerprint_length_outside_bounds_is_rejected_pre_adapter(self):
        import read_mailbox

        for length in (7, 65):
            with self.subTest(fingerprint_hex_chars=length):
                with tempfile.TemporaryDirectory() as directory:
                    config = self._config(
                        Path(directory) / "artifacts", fingerprint_hex_chars=length
                    )
                    graph_factory = Mock()
                    session_factory = Mock()
                    with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                        read_mailbox.run_acquisition(
                            config,
                            self._credentials(),
                            graph_factory=graph_factory,
                            session_factory=session_factory,
                        )
                    self.assertEqual("config_invalid", caught.exception.code)
                    graph_factory.assert_not_called()
                    session_factory.assert_not_called()
                    self.assertEqual([], list(Path(directory).iterdir()))

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
            # download_artifact is fully mocked below (no real file write), but
            # 02-02's run_acquisition now writes a provenance sidecar beside the
            # published artifact after download_artifact returns, so the
            # directory must exist for that write to land.
            output_dir.mkdir(parents=True, exist_ok=True)
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
                        self._config(Path(directory) / "artifacts"),
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
                        self._config(Path(directory) / "artifacts"),
                        self._credentials(),
                        graph_factory=Graph,
                        event_sink=events.append,
                    )

        self.assertEqual("download_expired_or_missing", caught.exception.code)
        downloader.assert_called_once()
        self.assertEqual(newest_url, downloader.call_args.args[0])
        self.assertEqual("download", events[-1]["stage"])
        self.assertEqual("download_expired_or_missing", events[-1]["reason"])


class ControllerPolicyContractTest(unittest.TestCase):
    """Closes verification gap G-02: one complete policy validator.

    Every case here must be rejected identically -- same ``config_invalid``
    code, zero adapter calls, zero filesystem writes -- whether the malformed
    policy arrives through the TOML loader or a directly constructed
    ``AcquisitionConfig`` passed straight to ``run_acquisition``.
    """

    def test_malformed_policy_is_rejected_identically_by_both_entry_points(self):
        import read_mailbox

        for label, (overrides, output_value) in _POLICY_MALFORMED_CASES.items():
            resolved_output_value = "artifacts" if output_value is None else output_value

            with self.subTest(entry_point="load_config", label=label):
                with tempfile.TemporaryDirectory() as directory:
                    kwargs = _policy_kwargs(Path(directory), **overrides)
                    toml_text = _render_policy_toml(kwargs, resolved_output_value)
                    policy_path = Path(directory) / "policy.toml"
                    policy_path.write_text(toml_text, encoding="utf-8")

                    with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                        read_mailbox.load_config(policy_path)
                    self.assertEqual("config_invalid", caught.exception.code)
                    self.assertEqual(
                        [policy_path],
                        list(Path(directory).iterdir()),
                        "malformed policy must create no directory or file",
                    )

            with self.subTest(entry_point="run_acquisition", label=label):
                with tempfile.TemporaryDirectory() as directory:
                    output_dir = Path(directory) / resolved_output_value
                    kwargs = _policy_kwargs(output_dir, **overrides)
                    config = read_mailbox.AcquisitionConfig(**kwargs)
                    graph_factory = Mock()
                    session_factory = Mock()

                    with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                        read_mailbox.run_acquisition(
                            config,
                            {
                                "O365_AUTH_ID": "private-client-id",
                                "O365_AUTH_SECRET": "private-client-secret",
                                "TENANT_ID": "private-tenant-id",
                            },
                            graph_factory=graph_factory,
                            session_factory=session_factory,
                        )
                    self.assertEqual("config_invalid", caught.exception.code)
                    graph_factory.assert_not_called()
                    session_factory.assert_not_called()
                    self.assertEqual(
                        [],
                        list(Path(directory).iterdir()),
                        "malformed policy must create no directory or file",
                    )

    def test_single_element_allowlists_are_valid(self):
        import read_mailbox

        with tempfile.TemporaryDirectory() as directory:
            config = read_mailbox.AcquisitionConfig(
                **_policy_kwargs(Path(directory) / "artifacts")
            )
            read_mailbox.validate_acquisition_policy(config)  # must not raise
            self.assertEqual(1, len(config.allowed_senders))
            self.assertEqual(1, len(config.allowed_order_ids))
            self.assertEqual(1, len(config.allowed_hosts))
            self.assertEqual(1, len(config.allowed_url_prefixes))

    def test_nfc_equivalent_but_code_point_different_senders_are_both_accepted(self):
        import read_mailbox

        composed = "user-caf\u00e9@example.test"
        decomposed = "user-cafe\u0301@example.test"
        self.assertNotEqual(composed, decomposed)
        self.assertEqual(
            unicodedata.normalize("NFC", composed),
            unicodedata.normalize("NFC", decomposed),
        )

        with tempfile.TemporaryDirectory() as directory:
            config = read_mailbox.AcquisitionConfig(
                **_policy_kwargs(
                    Path(directory) / "artifacts",
                    allowed_senders=(composed, decomposed),
                )
            )
            read_mailbox.validate_acquisition_policy(config)  # must not raise

    def test_ascii_case_variant_sender_is_treated_as_a_duplicate(self):
        import read_mailbox

        with tempfile.TemporaryDirectory() as directory:
            config = read_mailbox.AcquisitionConfig(
                **_policy_kwargs(
                    Path(directory) / "artifacts",
                    allowed_senders=(
                        "Noreply@Datashare.Maps.Vic.Gov.Au",
                        "noreply@datashare.maps.vic.gov.au",
                    ),
                )
            )
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.validate_acquisition_policy(config)
        self.assertEqual("config_invalid", caught.exception.code)


class ControllerCredentialContractTest(unittest.TestCase):
    def test_missing_blank_and_non_string_credentials_are_rejected_pre_adapter(self):
        import read_mailbox

        valid_credentials = {
            "O365_AUTH_ID": "private-client-id",
            "O365_AUTH_SECRET": "private-client-secret",
            "TENANT_ID": "private-tenant-id",
        }
        malformed_values = ("", "   ", None, 12345)
        for name in ("O365_AUTH_ID", "O365_AUTH_SECRET", "TENANT_ID"):
            for malformed in malformed_values:
                with self.subTest(name=name, malformed=repr(malformed)):
                    credentials = dict(valid_credentials)
                    credentials[name] = malformed
                    graph_factory = Mock()
                    session_factory = Mock()
                    with tempfile.TemporaryDirectory() as directory:
                        config = ControllerCompositionTest._config(
                            Path(directory) / "artifacts"
                        )
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

            with self.subTest(name=name, malformed="missing key"):
                credentials = dict(valid_credentials)
                del credentials[name]
                graph_factory = Mock()
                session_factory = Mock()
                with tempfile.TemporaryDirectory() as directory:
                    config = ControllerCompositionTest._config(
                        Path(directory) / "artifacts"
                    )
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


class ControllerSinkFailureTest(unittest.TestCase):
    """Closes verification gap G-05: evidence delivery cannot leak into control flow.

    Whatever the caller-supplied sink does, ``run_acquisition`` and ``main``
    must always end in the closed vocabulary and a non-zero result -- never
    a raw exception, never a sink invoked twice for the same failure.
    """

    def test_emit_once_exposes_emit_and_emit_failure(self):
        import read_mailbox

        self.assertTrue(hasattr(read_mailbox, "_EmitOnce"))
        self.assertTrue(callable(getattr(read_mailbox._EmitOnce, "emit", None)))
        self.assertTrue(
            callable(getattr(read_mailbox._EmitOnce, "emit_failure", None))
        )

    def test_emit_once_swallows_sink_faults_for_any_event_without_retry(self):
        import read_mailbox

        calls = []

        def raising_sink(event):
            calls.append(event)
            raise RuntimeError("guard-swallow-private-marker")

        guard = read_mailbox._EmitOnce(raising_sink)
        self.assertFalse(guard.failed)

        guard.emit({"event": "download_progress", "byte_count": 1})
        self.assertTrue(guard.failed)
        self.assertEqual(1, len(calls))

        # The guard must never retry a sink that has already failed.
        guard.emit({"event": "download_progress", "byte_count": 2})
        self.assertEqual(1, len(calls))

    def test_sink_failing_on_candidate_selected_yields_internal_failure(self):
        import read_mailbox
        from vicmap_acquire.graph import MessageMetadata

        marker = "candidate-sink-private-marker"
        message_id = "opaque-sink-candidate-message-id"
        artifact_url = (
            "https://s3.ap-southeast-2.amazonaws.com/private/Order_OK0VUZ.zip"
        )
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

        def failing_sink(event):
            if event["event"] == "candidate_selected":
                raise RuntimeError(marker)

        with tempfile.TemporaryDirectory() as directory:
            config = ControllerCompositionTest._config(Path(directory) / "artifacts")
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.run_acquisition(
                    config,
                    ControllerCompositionTest._credentials(),
                    graph_factory=lambda **kwargs: graph,
                    session_factory=lambda: session,
                    event_sink=failing_sink,
                )

        self.assertEqual("internal_failure", caught.exception.code)
        self.assertNotIn(marker, str(caught.exception))
        self.assertNotIn(marker, repr(caught.exception.failure))

    def test_sink_failing_on_progress_completes_transfer_then_fails_closed(self):
        import read_mailbox
        from vicmap_acquire.download import DownloadResult
        from vicmap_acquire.graph import MessageMetadata

        message_id = "opaque-sink-progress-message-id"
        artifact_url = (
            "https://s3.ap-southeast-2.amazonaws.com/private/Order_OK0VUZ.zip"
        )
        metadata = [
            MessageMetadata(
                graph_message_id=message_id,
                received_datetime_utc=datetime(2026, 9, 7, tzinfo=timezone.utc),
                sender="noreply@datashare.maps.vic.gov.au",
                subject="Your DataShare Order OK0VUZ is ready to download",
            )
        ]
        graph = _E2EGraph(metadata, {message_id: _e2e_mime(artifact_url=artifact_url)})
        events_seen = []

        def failing_on_progress_sink(event):
            events_seen.append(event["event"])
            if event["event"] == "download_progress":
                raise RuntimeError("progress-sink-private-marker")

        def fake_download_artifact(url, final_path, policy, session_factory, progress_sink):
            # Simulate a real transfer that emits one progress tick, then
            # completes and publishes the artifact -- proving that a guarded
            # progress-sink fault no longer aborts the transfer.
            progress_sink({"byte_count": 5})
            final_path.parent.mkdir(parents=True, exist_ok=True)
            final_path.write_bytes(b"authentic-artifact-bytes")
            return DownloadResult(
                path=final_path,
                byte_count=25,
                sha256=hashlib.sha256(b"authentic-artifact-bytes").hexdigest(),
                approved_hostname="s3.ap-southeast-2.amazonaws.com",
                path_fingerprint="0123456789abcdef",
            )

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "artifacts"
            config = ControllerCompositionTest._config(output_dir)
            with patch.object(
                read_mailbox, "download_artifact", side_effect=fake_download_artifact
            ):
                with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                    read_mailbox.run_acquisition(
                        config,
                        ControllerCompositionTest._credentials(),
                        graph_factory=lambda **kwargs: graph,
                        session_factory=lambda: object(),
                        event_sink=failing_on_progress_sink,
                    )
            final_path = output_dir / "Order_OK0VUZ.zip"
            self.assertTrue(
                final_path.exists(), "the completed transfer must not be undone"
            )

        self.assertEqual("internal_failure", caught.exception.code)
        self.assertEqual(["candidate_selected", "download_progress"], events_seen)

    def test_sink_failing_on_a_late_success_event_does_not_delete_the_artifact(self):
        import read_mailbox
        from vicmap_acquire.graph import MessageMetadata

        for failing_event in ("download_target", "artifact_finalized"):
            with self.subTest(failing_event=failing_event):
                message_id = f"opaque-sink-{failing_event}-message-id"
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
                graph = _E2EGraph(
                    metadata, {message_id: _e2e_mime(artifact_url=artifact_url)}
                )
                session = _E2ESession(payload)

                def failing_sink(event, failing_event=failing_event):
                    if event["event"] == failing_event:
                        raise RuntimeError(f"{failing_event}-sink-private-marker")

                with tempfile.TemporaryDirectory() as directory:
                    output_dir = Path(directory) / "artifacts"
                    config = ControllerCompositionTest._config(output_dir)
                    with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                        read_mailbox.run_acquisition(
                            config,
                            ControllerCompositionTest._credentials(),
                            graph_factory=lambda **kwargs: graph,
                            session_factory=lambda: session,
                            event_sink=failing_sink,
                        )
                    final_path = output_dir / "Order_OK0VUZ.zip"
                    self.assertTrue(final_path.exists())
                    self.assertEqual(payload, final_path.read_bytes())

                self.assertEqual("internal_failure", caught.exception.code)

    def test_sink_failing_on_the_failure_event_preserves_the_original_reason(self):
        import read_mailbox

        class EmptyGraph:
            def __init__(self, **kwargs):
                pass

            def iter_metadata(self, cutoff_utc):
                return iter(())

        calls = []

        def failing_only_on_failure(event):
            calls.append(event["event"])
            if event["event"] == "failure":
                raise RuntimeError("failure-sink-private-marker")

        with tempfile.TemporaryDirectory() as directory:
            config = ControllerCompositionTest._config(Path(directory) / "artifacts")
            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.run_acquisition(
                    config,
                    ControllerCompositionTest._credentials(),
                    graph_factory=EmptyGraph,
                    event_sink=failing_only_on_failure,
                )

        self.assertEqual("candidate_none", caught.exception.code)
        self.assertEqual(["failure"], calls)

    def test_counting_sink_receives_at_most_one_failure_event(self):
        import read_mailbox

        class EmptyGraph:
            def __init__(self, **kwargs):
                pass

            def iter_metadata(self, cutoff_utc):
                return iter(())

        failure_count = 0

        def counting_sink(event):
            nonlocal failure_count
            if event["event"] == "failure":
                failure_count += 1
            raise RuntimeError("counting-sink-private-marker")

        with tempfile.TemporaryDirectory() as directory:
            config = ControllerCompositionTest._config(Path(directory) / "artifacts")
            with self.assertRaises(read_mailbox.AcquisitionFailure):
                read_mailbox.run_acquisition(
                    config,
                    ControllerCompositionTest._credentials(),
                    graph_factory=EmptyGraph,
                    event_sink=counting_sink,
                )

        self.assertLessEqual(failure_count, 1)

    def test_sink_failing_on_every_call_still_returns_a_clean_cli_result(self):
        import read_mailbox

        class EmptyGraph:
            def __init__(self, **kwargs):
                pass

            def iter_metadata(self, cutoff_utc):
                return iter(())

        marker = "always-failing-sink-private-marker"

        def always_failing(event):
            raise RuntimeError(marker)

        with tempfile.TemporaryDirectory() as directory:
            config = ControllerCompositionTest._config(Path(directory) / "artifacts")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch.object(read_mailbox, "load_config", return_value=config),
                patch.object(read_mailbox, "GraphMailbox", EmptyGraph),
                patch.dict(
                    read_mailbox.os.environ,
                    {
                        "O365_AUTH_ID": "private-client-id",
                        "O365_AUTH_SECRET": "private-client-secret",
                        "TENANT_ID": "private-tenant-id",
                    },
                    clear=True,
                ),
                patch.object(read_mailbox, "render_success", always_failing),
                patch.object(read_mailbox, "render_progress", always_failing),
                patch.object(read_mailbox, "render_failure", always_failing),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = read_mailbox.main(["--config", "ignored.toml"])

        self.assertNotEqual(0, exit_code)
        rendered = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn(marker, rendered)
        self.assertNotIn("Traceback", rendered)

    def test_main_survives_a_render_failure_fault_reporting_an_unreported_failure(self):
        import read_mailbox

        marker = "main-render-failure-private-marker"

        def exploding_render_failure(event):
            raise RuntimeError(marker)

        with tempfile.TemporaryDirectory() as directory:
            policy_path = Path(directory) / "policy.toml"
            policy_path.write_text("not valid toml [[[", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch.object(read_mailbox, "render_failure", exploding_render_failure),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = read_mailbox.main(["--config", str(policy_path)])

        self.assertEqual(1, exit_code)
        rendered = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn(marker, rendered)
        self.assertNotIn("Traceback", rendered)


if __name__ == "__main__":
    unittest.main()
