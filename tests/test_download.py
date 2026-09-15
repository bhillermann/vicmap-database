"""Security and lifecycle regressions for the artifact download boundary."""

from __future__ import annotations

import hashlib
import inspect
import os
import stat
import tempfile
import threading
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import patch

import requests

from vicmap_acquire import download


ALLOWED_HOST = "s3.ap-southeast-2.amazonaws.com"
BASE_URL = f"https://{ALLOWED_HOST}/orders/Order_OK0VUZ.zip?signature=private"


class _FakeCookies:
    def __init__(self) -> None:
        self.cleared = False

    def clear(self) -> None:
        self.cleared = True


class _FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        *,
        headers: dict[str, str] | None = None,
        chunks: tuple[bytes, ...] = (b"payload",),
        stream_error: BaseException | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.chunks = chunks
        self.stream_error = stream_error
        self.closed = False
        self.iterated = False

    def iter_content(self, chunk_size: int):
        self.iterated = True
        for chunk in self.chunks:
            yield chunk
        if self.stream_error is not None:
            raise self.stream_error

    def close(self) -> None:
        self.closed = True


class _FakeSession:
    def __init__(
        self,
        responses: tuple[_FakeResponse, ...] = (),
        *,
        request_error: BaseException | None = None,
    ) -> None:
        self.auth = ("graph-bearer", "must-not-cross")
        self.trust_env = True
        self.cookies = _FakeCookies()
        self.headers = {
            "Authorization": "Bearer graph-secret",
            "Cookie": "graph-cookie=secret",
        }
        self.responses = deque(responses)
        self.request_error = request_error
        self.calls: list[tuple[str, dict[str, object], object, bool, dict[str, str]]] = []
        self.closed = False

    def get(self, url: str, **kwargs):
        self.calls.append(
            (url, kwargs, self.auth, self.trust_env, dict(self.headers))
        )
        if self.request_error is not None:
            raise self.request_error
        if not self.responses:
            raise AssertionError("unexpected transport contact")
        return self.responses.popleft()

    def close(self) -> None:
        self.closed = True


def _response(
    payload: bytes = b"payload",
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> _FakeResponse:
    response_headers = {
        "Content-Length": str(len(payload)),
        "Content-Encoding": "identity",
    }
    if headers:
        response_headers.update(headers)
    return _FakeResponse(status, headers=response_headers, chunks=(payload,))


ALLOWED_URL_PREFIX = f"https://{ALLOWED_HOST}/orders/"


def _legacy_download(session: _FakeSession, directory: Path, **overrides):
    arguments = {
        "output_dir": directory,
        "allowed_hosts": (ALLOWED_HOST,),
        "allowed_url_prefixes": (ALLOWED_URL_PREFIX,),
        "max_bytes": 1024,
        "connect_timeout_seconds": 10,
        "read_timeout_seconds": 60,
        "max_redirects": 5,
        "session": session,
    }
    arguments.update(overrides)
    return download.download_artifact(BASE_URL, **arguments)


def _policy(**overrides) -> download.DownloadPolicy:
    arguments = {
        "allowed_hosts": (ALLOWED_HOST,),
        "allowed_url_prefixes": (ALLOWED_URL_PREFIX,),
        "max_bytes": 1024,
        "connect_timeout_seconds": 10,
        "stalled_read_timeout_seconds": 60,
        "progress_interval_seconds": 5,
        "max_redirects": 5,
        "fingerprint_hex_length": 16,
    }
    arguments.update(overrides)
    return download.DownloadPolicy(**arguments)


def _download_new(
    response: _FakeResponse,
    directory: Path,
    *,
    filename: str = "artifact.zip",
    policy: download.DownloadPolicy | None = None,
    progress_sink=None,
    session: _FakeSession | None = None,
):
    session = session or _FakeSession((response,))
    result = download.download_artifact(
        BASE_URL,
        directory / filename,
        policy or _policy(),
        progress_sink,
        lambda: session,
    )
    return result, session


class DownloadTargetPolicyTest(unittest.TestCase):
    def test_public_policy_contract_is_explicit(self):
        policy_type = getattr(download, "DownloadPolicy", None)
        failure_type = getattr(download, "DownloadFailure", None)
        self.assertIsNotNone(
            policy_type,
            "DownloadPolicy must make all transport and evidence limits explicit",
        )
        self.assertIsNotNone(failure_type)
        parameters = list(inspect.signature(download.download_artifact).parameters)
        self.assertEqual(
            ["url", "final_path", "policy", "progress_sink", "session_factory"],
            parameters[:5],
        )

    def test_accepts_only_exact_https_host_and_normalizes_case(self):
        for url in (
            f"https://{ALLOWED_HOST}/archive.zip",
            f"HTTPS://S3.AP-SOUTHEAST-2.AMAZONAWS.COM/archive.zip",
            f"https://{ALLOWED_HOST}:443/archive.zip",
        ):
            with self.subTest(url=url):
                target = download.validate_https_target(
                    url, (ALLOWED_HOST,), (f"https://{ALLOWED_HOST}/",)
                )
                self.assertEqual(ALLOWED_HOST, target.hostname.casefold())

    def test_rejects_unsafe_or_malformed_authorities_before_transport(self):
        rejected = (
            f"http://{ALLOWED_HOST}/archive.zip",
            f"https://user@{ALLOWED_HOST}/archive.zip",
            f"https://user:password@{ALLOWED_HOST}/archive.zip",
            f"https://{ALLOWED_HOST}/archive.zip#fragment",
            f"https://{ALLOWED_HOST}:444/archive.zip",
            f"https://{ALLOWED_HOST}:/archive.zip",
            f"https://{ALLOWED_HOST}./archive.zip",
            f"https://bucket.{ALLOWED_HOST}/archive.zip",
            f"https://{ALLOWED_HOST}.attacker.example/archive.zip",
            "https:///archive.zip",
            "not a URL",
        )
        for url in rejected:
            with self.subTest(url=url):
                with self.assertRaises(download.DownloadError) as caught:
                    download.validate_https_target(
                        url, (ALLOWED_HOST,), (f"https://{ALLOWED_HOST}/",)
                    )
                self.assertEqual("download_url_rejected", caught.exception.code)

    def test_prefix_authority_narrows_the_allowed_host(self):
        prefix = (f"https://{ALLOWED_HOST}/private/",)
        accepted = download.validate_https_target(
            f"https://{ALLOWED_HOST}/private/archive.zip", (ALLOWED_HOST,), prefix
        )
        self.assertEqual(ALLOWED_HOST, accepted.hostname.casefold())

        with self.assertRaises(download.DownloadError) as caught:
            download.validate_https_target(
                f"https://{ALLOWED_HOST}/other/archive.zip", (ALLOWED_HOST,), prefix
            )
        self.assertEqual("download_url_rejected", caught.exception.code)

    def test_prefix_path_case_difference_is_rejected_byte_exact(self):
        prefix = (f"https://{ALLOWED_HOST}/Private/",)
        with self.assertRaises(download.DownloadError) as caught:
            download.validate_https_target(
                f"https://{ALLOWED_HOST}/private/archive.zip", (ALLOWED_HOST,), prefix
            )
        self.assertEqual("download_url_rejected", caught.exception.code)


class DownloadTransportBoundaryTest(unittest.TestCase):
    def test_clean_session_uses_manual_redirects_tls_and_timeout_tuple(self):
        response = _response()
        session = _FakeSession((response,))
        with tempfile.TemporaryDirectory() as directory:
            _legacy_download(session, Path(directory))

        self.assertEqual(1, len(session.calls))
        called_url, kwargs, auth, trust_env, headers = session.calls[0]
        self.assertEqual(BASE_URL, called_url)
        self.assertIsNone(auth)
        self.assertFalse(trust_env)
        self.assertEqual({}, headers)
        self.assertTrue(session.cookies.cleared)
        self.assertFalse(kwargs["allow_redirects"])
        self.assertTrue(kwargs["stream"])
        self.assertEqual((10, 60), kwargs["timeout"])
        self.assertEqual({"Accept-Encoding": "identity"}, kwargs["headers"])
        self.assertIs(True, kwargs["verify"])
        self.assertTrue(response.closed)
        self.assertTrue(session.closed)

    def test_relative_redirect_is_resolved_and_each_response_is_closed(self):
        redirect = _FakeResponse(302, headers={"Location": "final.zip?new=secret"})
        final = _response()
        session = _FakeSession((redirect, final))
        with tempfile.TemporaryDirectory() as directory:
            _legacy_download(session, Path(directory))

        self.assertEqual(
            [
                BASE_URL,
                f"https://{ALLOWED_HOST}/orders/final.zip?new=secret",
            ],
            [call[0] for call in session.calls],
        )
        self.assertTrue(redirect.closed)
        self.assertTrue(final.closed)

    def test_redirect_leaving_the_configured_prefix_is_rejected_after_one_contact(self):
        redirect = _FakeResponse(
            307, headers={"Location": f"https://{ALLOWED_HOST}/other/final.zip"}
        )
        session = _FakeSession((redirect,))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(download.DownloadError) as caught:
                _legacy_download(session, Path(directory))
        self.assertEqual("download_redirect_rejected", caught.exception.code)
        self.assertEqual([BASE_URL], [call[0] for call in session.calls])
        self.assertTrue(redirect.closed)

    def test_relative_redirect_leaving_the_configured_prefix_is_rejected_before_recontact(
        self,
    ):
        redirect = _FakeResponse(
            302, headers={"Location": "../other-bucket/Order_OK0VUZ.zip"}
        )
        session = _FakeSession((redirect,))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(download.DownloadError) as caught:
                _legacy_download(session, Path(directory))
        self.assertEqual("download_redirect_rejected", caught.exception.code)
        self.assertEqual([BASE_URL], [call[0] for call in session.calls])
        self.assertTrue(redirect.closed)

    def test_prohib_02_no_ambient_or_graph_authority_reaches_artifact_host(self):
        redirect = _FakeResponse(302, headers={"Location": "/orders/hop2.zip"})
        final = _response()
        session = _FakeSession((redirect, final))
        with tempfile.TemporaryDirectory() as directory:
            _legacy_download(session, Path(directory))

        self.assertEqual(2, len(session.calls))
        for called_url, kwargs, auth, trust_env, headers in session.calls:
            self.assertIsNone(auth)
            self.assertFalse(trust_env)
            for key in headers:
                self.assertNotIn(key.casefold(), {"authorization", "cookie"})
            request_headers = kwargs.get("headers", {})
            for key in request_headers:
                self.assertNotIn(key.casefold(), {"authorization", "cookie"})
        self.assertIsNone(session.auth)
        self.assertFalse(session.trust_env)

    def test_unsafe_redirects_are_rejected_before_contact(self):
        for location in (
            "http://s3.ap-southeast-2.amazonaws.com/archive.zip",
            "https://attacker.example/archive.zip",
            "https://s3.ap-southeast-2.amazonaws.com.:443/archive.zip",
        ):
            with self.subTest(location=location):
                redirect = _FakeResponse(307, headers={"Location": location})
                session = _FakeSession((redirect,))
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(download.DownloadError) as caught:
                        _legacy_download(session, Path(directory))
                self.assertEqual("download_redirect_rejected", caught.exception.code)
                self.assertEqual([BASE_URL], [call[0] for call in session.calls])
                self.assertTrue(redirect.closed)

    def test_missing_location_is_closed_redirect_failure(self):
        redirect = _FakeResponse(301)
        session = _FakeSession((redirect,))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(download.DownloadError) as caught:
                _legacy_download(session, Path(directory))
        self.assertEqual("download_redirect_rejected", caught.exception.code)
        self.assertTrue(redirect.closed)

    def test_redirect_loop_stops_without_recontacting_a_seen_target(self):
        first = _FakeResponse(302, headers={"Location": "/orders/second.zip"})
        second = _FakeResponse(302, headers={"Location": BASE_URL})
        session = _FakeSession((first, second))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(download.DownloadError) as caught:
                _legacy_download(session, Path(directory))
        self.assertEqual("download_redirect_rejected", caught.exception.code)
        self.assertEqual(2, len(session.calls))
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)

    def test_default_ceiling_rejects_sixth_redirect_without_contact(self):
        responses = tuple(
            _FakeResponse(302, headers={"Location": f"/orders/hop-{index}.zip"})
            for index in range(1, 7)
        )
        session = _FakeSession(responses)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(download.DownloadError) as caught:
                _legacy_download(session, Path(directory))
        self.assertEqual("download_redirect_rejected", caught.exception.code)
        self.assertEqual(6, len(session.calls))
        self.assertNotIn(
            f"https://{ALLOWED_HOST}/orders/hop-6.zip",
            [call[0] for call in session.calls],
        )
        self.assertTrue(all(response.closed for response in responses))

    def test_only_status_200_is_accepted(self):
        for status, expected in (
            (201, "download_http_failed"),
            (304, "download_http_failed"),
            (404, "download_expired_or_missing"),
            (500, "download_http_failed"),
        ):
            with self.subTest(status=status):
                response = _response(status=status)
                session = _FakeSession((response,))
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(download.DownloadError) as caught:
                        _legacy_download(session, Path(directory))
                self.assertEqual(expected, caught.exception.code)
                self.assertTrue(response.closed)

    def test_connect_and_read_timeouts_are_closed_and_do_not_leak_text(self):
        secret = "https://forbidden.example/private?signature=do-not-leak"
        for error in (
            requests.ConnectTimeout(secret),
            requests.ReadTimeout(secret),
        ):
            with self.subTest(error=type(error).__name__):
                session = _FakeSession(request_error=error)
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(download.DownloadError) as caught:
                        _legacy_download(session, Path(directory))
                self.assertEqual("download_timeout", caught.exception.code)
                self.assertEqual("download_timeout", str(caught.exception))
                self.assertNotIn(secret, str(caught.exception))
                self.assertTrue(session.closed)


class DownloadPolicyValidationTest(unittest.TestCase):
    def test_policy_normalizes_hosts_and_rejects_unsafe_values(self):
        normalized = _policy(allowed_hosts=(ALLOWED_HOST.upper(),))
        self.assertEqual((ALLOWED_HOST,), normalized.allowed_hosts)

        fields = (
            "max_bytes",
            "connect_timeout_seconds",
            "stalled_read_timeout_seconds",
            "progress_interval_seconds",
            "max_redirects",
            "fingerprint_hex_length",
        )
        for field in fields:
            for value in (True, False, 0, -1, 1.5, "1"):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        _policy(**{field: value})

        for hosts in (
            (),
            [ALLOWED_HOST],
            ("",),
            (f"{ALLOWED_HOST}.",),
            (f"{ALLOWED_HOST}:443",),
            (ALLOWED_HOST, ALLOWED_HOST.upper()),
        ):
            with self.subTest(hosts=hosts):
                with self.assertRaises(ValueError):
                    _policy(allowed_hosts=hosts)

    def test_fingerprint_length_cannot_exceed_sha256(self):
        with self.assertRaises(ValueError):
            _policy(fingerprint_hex_length=65)

    def test_allowed_url_prefixes_rejects_seven_invalid_shapes(self):
        shapes = {
            "empty": (),
            "hostname_not_allowed": ("https://other.example.com/orders/",),
            "has_query": (f"https://{ALLOWED_HOST}/orders/?x=1",),
            "has_fragment": (f"https://{ALLOWED_HOST}/orders/#frag",),
            "has_userinfo": (f"https://user@{ALLOWED_HOST}/orders/",),
            "missing_trailing_slash": (f"https://{ALLOWED_HOST}/orders",),
            "no_non_empty_segment": (f"https://{ALLOWED_HOST}/",),
            "duplicate": (ALLOWED_URL_PREFIX, ALLOWED_URL_PREFIX),
        }
        for name, prefixes in shapes.items():
            with self.subTest(shape=name):
                with self.assertRaises(ValueError):
                    _policy(allowed_url_prefixes=prefixes)

    def test_allowed_url_prefixes_casefold_scheme_and_host_but_preserve_path(self):
        normalized = _policy(
            allowed_url_prefixes=(f"HTTPS://{ALLOWED_HOST.upper()}/Orders/",)
        )
        self.assertEqual((f"https://{ALLOWED_HOST}/Orders/",), normalized.allowed_url_prefixes)


class DownloadStreamingBoundaryTest(unittest.TestCase):
    def test_format_progress_uses_exact_integer_tenths(self):
        formatter = getattr(download, "format_progress", None)
        self.assertIsNotNone(
            formatter,
            "format_progress must make exact integer progress reusable by evidence",
        )
        enormous = 2**70 + 19
        self.assertEqual(
            {"byte_count": enormous, "percent": 33.3},
            formatter(enormous, enormous * 3),
        )
        self.assertEqual(
            {"byte_count": enormous * 4, "percent": 100.0},
            formatter(enormous * 4, enormous * 3),
        )
        self.assertEqual({"byte_count": enormous}, formatter(enormous, None))
        self.assertEqual({"byte_count": 0}, formatter(0, 0))

    def test_missing_content_length_streams_and_returns_safe_provenance(self):
        payload = b"known checksum bytes"
        response = _FakeResponse(
            headers={"Content-Encoding": "identity"},
            chunks=(payload[:5], b"", payload[5:]),
        )
        with tempfile.TemporaryDirectory() as directory:
            result, session = _download_new(response, Path(directory))
            self.assertEqual(payload, result.path.read_bytes())
            self.assertEqual(len(payload), result.byte_count)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), result.sha256)
            self.assertEqual(ALLOWED_HOST, result.approved_hostname)
            expected_fingerprint = hashlib.sha256(
                "/orders/Order_OK0VUZ.zip".encode()
            ).hexdigest()[:16]
            self.assertEqual(expected_fingerprint, result.path_fingerprint)
            self.assertNotIn("private", repr(result))
            self.assertNotIn(BASE_URL, repr(result))
        self.assertTrue(response.closed)
        self.assertTrue(session.closed)

    def test_content_length_rejections_happen_before_body_consumption(self):
        for declared, expected_type in (
            ("invalid", download.DownloadHttpFailed),
            ("+1", download.DownloadHttpFailed),
            ("-1", download.DownloadHttpFailed),
            ("1025", download.DownloadTooLarge),
        ):
            with self.subTest(declared=declared):
                response = _FakeResponse(
                    headers={
                        "Content-Length": declared,
                        "Content-Encoding": "identity",
                    },
                    chunks=(b"must not be consumed",),
                )
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(expected_type):
                        _download_new(response, Path(directory))
                    self.assertEqual([], list(Path(directory).iterdir()))
                self.assertFalse(response.iterated)
                self.assertTrue(response.closed)

    def test_declared_length_must_equal_completed_observed_count(self):
        for declared in ("2", "4"):
            with self.subTest(declared=declared):
                response = _FakeResponse(
                    headers={
                        "Content-Length": declared,
                        "Content-Encoding": "identity",
                    },
                    chunks=(b"abc",),
                )
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(download.DownloadHttpFailed):
                        _download_new(response, Path(directory))
                    self.assertEqual([], list(Path(directory).iterdir()))

    def test_zero_exact_limit_and_limit_plus_one_are_inclusive(self):
        cases = (
            (b"", 0, True),
            (b"abcd", 4, True),
            (b"abcde", 4, False),
        )
        for payload, ceiling, succeeds in cases:
            with self.subTest(length=len(payload), ceiling=ceiling):
                response = _FakeResponse(
                    headers={"Content-Encoding": "identity"},
                    chunks=(payload[:ceiling], payload[ceiling:]),
                )
                with tempfile.TemporaryDirectory() as directory:
                    destination = Path(directory) / "artifact.zip"
                    if succeeds:
                        result, _ = _download_new(
                            response,
                            Path(directory),
                            policy=_policy(max_bytes=max(1, ceiling)),
                        )
                        self.assertEqual(payload, destination.read_bytes())
                        self.assertEqual(len(payload), result.byte_count)
                    else:
                        with self.assertRaises(download.DownloadTooLarge):
                            _download_new(
                                response,
                                Path(directory),
                                policy=_policy(max_bytes=ceiling),
                            )
                        self.assertFalse(destination.exists())
                        self.assertEqual([], list(Path(directory).iterdir()))

    def test_non_identity_encoding_is_rejected_before_body_consumption(self):
        for encoding in ("gzip", "br", 123):
            with self.subTest(encoding=encoding):
                response = _FakeResponse(
                    headers={"Content-Encoding": encoding},
                    chunks=(b"compressed",),
                )
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(download.DownloadHttpFailed):
                        _download_new(response, Path(directory))
                    self.assertEqual([], list(Path(directory).iterdir()))
                self.assertFalse(response.iterated)

    def test_known_progress_is_periodic_floored_and_capped(self):
        response = _FakeResponse(
            headers={"Content-Length": "10", "Content-Encoding": "identity"},
            chunks=(b"ab", b"cde", b"fghij"),
        )
        events = []
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(download.time, "monotonic", side_effect=(0, 1, 5, 10)):
                _download_new(response, Path(directory), progress_sink=events.append)
        self.assertEqual(
            [
                {"byte_count": 5, "percent": 50.0},
                {"byte_count": 10, "percent": 100.0},
            ],
            events,
        )

    def test_unknown_total_progress_contains_bytes_only(self):
        response = _FakeResponse(
            headers={"Content-Encoding": "identity"},
            chunks=(b"abc", b"def"),
        )
        events = []
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(download.time, "monotonic", side_effect=(0, 5, 10)):
                _download_new(response, Path(directory), progress_sink=events.append)
        self.assertEqual([{"byte_count": 3}, {"byte_count": 6}], events)

    def test_declared_zero_emits_no_percentage_event(self):
        response = _FakeResponse(
            headers={"Content-Length": "0", "Content-Encoding": "identity"},
            chunks=(b"",),
        )
        events = []
        with tempfile.TemporaryDirectory() as directory:
            result, _ = _download_new(
                response, Path(directory), progress_sink=events.append
            )
            self.assertEqual(hashlib.sha256(b"").hexdigest(), result.sha256)
            self.assertEqual(0, result.byte_count)
        self.assertEqual([], events)

    def test_stream_timeout_is_closed_and_private_temp_is_removed(self):
        secret = "read failed for /private/path?signature=secret"
        response = _FakeResponse(
            headers={"Content-Encoding": "identity"},
            chunks=(b"partial",),
            stream_error=requests.ReadTimeout(secret),
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(download.DownloadTimeout) as caught:
                _download_new(response, Path(directory))
            self.assertEqual("download_timeout", str(caught.exception))
            self.assertNotIn(secret, str(caught.exception))
            self.assertEqual([], list(Path(directory).iterdir()))
        self.assertTrue(response.closed)

    def test_write_failure_is_closed_and_private_temp_is_removed(self):
        response = _response(b"payload")

        class FailingWriter:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def write(self, chunk):
                raise OSError("private local path must not leak")

        def failing_fdopen(descriptor, mode):
            os.close(descriptor)
            return FailingWriter()

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(download.os, "fdopen", side_effect=failing_fdopen),
                self.assertRaises(download.ArtifactWriteFailed) as caught,
            ):
                _download_new(response, Path(directory))
            self.assertEqual("artifact_write_failed", str(caught.exception))
            self.assertEqual([], list(Path(directory).iterdir()))

    def test_keyboard_interrupt_cleans_private_state_and_reraises(self):
        response = _FakeResponse(
            headers={"Content-Encoding": "identity"},
            chunks=(b"partial",),
            stream_error=KeyboardInterrupt(),
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KeyboardInterrupt):
                _download_new(response, Path(directory))
            self.assertEqual([], list(Path(directory).iterdir()))
        self.assertTrue(response.closed)

    def test_in_progress_state_is_private_mode_and_never_final(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            final_path = output_dir / "artifact.zip"

            class InspectingResponse(_FakeResponse):
                def iter_content(self, chunk_size: int):
                    entries = list(output_dir.iterdir())
                    self_test.assertEqual(1, len(entries))
                    self_test.assertTrue(entries[0].name.startswith(".vicmap-download-"))
                    self_test.assertTrue(entries[0].name.endswith(".part"))
                    self_test.assertFalse(final_path.exists())
                    mode = stat.S_IMODE(entries[0].stat().st_mode)
                    self_test.assertEqual(0o600, mode)
                    raise KeyboardInterrupt()
                    yield b"unreachable"

            self_test = self
            response = InspectingResponse(headers={"Content-Encoding": "identity"})
            with self.assertRaises(KeyboardInterrupt):
                _download_new(response, output_dir)
            self.assertEqual([], list(output_dir.iterdir()))

    def test_existing_final_path_is_never_overwritten(self):
        response = _response(b"new")
        with tempfile.TemporaryDirectory() as directory:
            final_path = Path(directory) / "artifact.zip"
            final_path.write_bytes(b"existing")
            with self.assertRaises(download.ArtifactWriteFailed):
                _download_new(response, Path(directory))
            self.assertEqual(b"existing", final_path.read_bytes())
            self.assertEqual([final_path], list(Path(directory).iterdir()))

    def test_two_concurrent_finalizers_have_exactly_one_complete_winner(self):
        barrier = threading.Barrier(2)
        payloads = (b"first complete payload", b"second complete payload")
        results: list[download.DownloadResult] = []
        failures: list[BaseException] = []

        class RacingResponse(_FakeResponse):
            def iter_content(self, chunk_size: int):
                yield self.chunks[0]
                barrier.wait(timeout=5)

        def run_one(directory: Path, payload: bytes) -> None:
            response = RacingResponse(
                headers={"Content-Encoding": "identity"}, chunks=(payload,)
            )
            try:
                result, _ = _download_new(response, directory)
                results.append(result)
            except BaseException as error:
                failures.append(error)

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            threads = [
                threading.Thread(target=run_one, args=(output_dir, payload))
                for payload in payloads
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(1, len(results))
            self.assertEqual(1, len(failures))
            self.assertIsInstance(failures[0], download.ArtifactWriteFailed)
            self.assertIn((output_dir / "artifact.zip").read_bytes(), payloads)
            self.assertEqual(
                [output_dir / "artifact.zip"], list(output_dir.iterdir())
            )
            self.assertFalse(
                any(
                    entry.name.startswith(".vicmap-download-")
                    for entry in output_dir.iterdir()
                )
            )

    def test_exact_ceiling_byte_count_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            payload = b"abcd"
            response = _FakeResponse(
                headers={"Content-Encoding": "identity"}, chunks=(payload,)
            )
            result, _ = _download_new(
                response, output_dir, policy=_policy(max_bytes=len(payload))
            )
            self.assertEqual(len(payload), result.byte_count)
            self.assertEqual(payload, result.path.read_bytes())

    def test_ceiling_plus_one_byte_is_rejected_and_leaves_no_final_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            payload = b"abcde"
            response = _FakeResponse(
                headers={"Content-Encoding": "identity"}, chunks=(payload,)
            )
            with self.assertRaises(download.DownloadTooLarge):
                _download_new(
                    response,
                    output_dir,
                    policy=_policy(max_bytes=len(payload) - 1),
                )
            self.assertEqual([], list(output_dir.iterdir()))

    def test_over_declared_content_length_rejected_before_any_chunk_consumed(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)

            class _CountingResponse(_FakeResponse):
                def __init__(self, *args, **kwargs) -> None:
                    super().__init__(*args, **kwargs)
                    self.iter_content_calls = 0

                def iter_content(self, chunk_size: int):
                    self.iter_content_calls += 1
                    return super().iter_content(chunk_size)

            response = _CountingResponse(
                headers={"Content-Length": "5", "Content-Encoding": "identity"},
                chunks=(b"abcde",),
            )
            with self.assertRaises(download.DownloadTooLarge):
                _download_new(response, output_dir, policy=_policy(max_bytes=4))
            self.assertEqual(0, response.iter_content_calls)
            self.assertEqual([], list(output_dir.iterdir()))

    def test_precision_table_uses_floor_division_and_never_exceeds_cap(self):
        cases = (
            (1, 3, 33.3),
            (2, 3, 66.6),
            (999999, 1000000, 99.9),
            (5, 0, None),
        )
        for byte_count, total_bytes, expected_percent in cases:
            with self.subTest(byte_count=byte_count, total_bytes=total_bytes):
                event = download.format_progress(byte_count, total_bytes)
                if expected_percent is None:
                    self.assertNotIn("percent", event)
                else:
                    self.assertEqual(expected_percent, event["percent"])
                    self.assertLessEqual(event["percent"], 100.0)
                self.assertIsInstance(event["byte_count"], int)
                self.assertNotIsInstance(event["byte_count"], bool)

    def test_emitted_progress_byte_counts_are_always_int_never_float(self):
        response = _FakeResponse(
            headers={"Content-Length": "10", "Content-Encoding": "identity"},
            chunks=(b"ab", b"cde", b"fghij"),
        )
        events: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(download.time, "monotonic", side_effect=(0, 1, 5, 10)):
                _download_new(response, Path(directory), progress_sink=events.append)
        self.assertTrue(events)
        for event in events:
            self.assertIsInstance(event["byte_count"], int)
            self.assertNotIsInstance(event["byte_count"], bool)


class DownloadCommitPointTest(unittest.TestCase):
    def test_post_link_cleanup_failure_still_reports_a_committed_success(self):
        payload = b"committed despite a post-commit cleanup failure"
        response = _response(payload)
        real_unlink = Path.unlink

        def flaky_unlink(self: Path, *args, **kwargs):
            if self.name.startswith(".vicmap-download-"):
                raise OSError("simulated post-commit cleanup failure")
            return real_unlink(self, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with patch.object(Path, "unlink", flaky_unlink):
                result, session = _download_new(response, output_dir)

            self.assertTrue(result.temp_cleanup_deferred)
            self.assertEqual(len(payload), result.byte_count)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), result.sha256)
            self.assertTrue(result.path.exists())
            self.assertEqual(payload, result.path.read_bytes())
            self.assertTrue(session.closed)

    def test_post_link_cleanup_success_reports_deferred_false(self):
        payload = b"clean commit, clean cleanup"
        response = _response(payload)
        with tempfile.TemporaryDirectory() as directory:
            result, _ = _download_new(response, Path(directory))
        self.assertFalse(result.temp_cleanup_deferred)

    def test_pre_commit_timeout_family_leaves_no_final_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            response = _FakeResponse(
                headers={"Content-Encoding": "identity"},
                chunks=(b"partial",),
                stream_error=requests.ReadTimeout("boom"),
            )
            with self.assertRaises(download.DownloadTimeout):
                _download_new(response, output_dir)
            self.assertFalse((output_dir / "artifact.zip").exists())

    def test_pre_commit_over_limit_family_leaves_no_final_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            response = _FakeResponse(
                headers={"Content-Encoding": "identity"},
                chunks=(b"abcde",),
            )
            with self.assertRaises(download.DownloadTooLarge):
                _download_new(response, output_dir, policy=_policy(max_bytes=4))
            self.assertFalse((output_dir / "artifact.zip").exists())

    def test_pre_commit_short_write_family_leaves_no_final_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            response = _response(b"payload")

            class FailingWriter:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, traceback):
                    return False

                def write(self, chunk):
                    raise OSError("write failed")

            def failing_fdopen(descriptor, mode):
                os.close(descriptor)
                return FailingWriter()

            with (
                patch.object(download.os, "fdopen", side_effect=failing_fdopen),
                self.assertRaises(download.ArtifactWriteFailed),
            ):
                _download_new(response, output_dir)
            self.assertFalse((output_dir / "artifact.zip").exists())

    def test_pre_commit_declared_length_mismatch_family_leaves_no_final_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            response = _FakeResponse(
                headers={"Content-Length": "4", "Content-Encoding": "identity"},
                chunks=(b"abc",),
            )
            with self.assertRaises(download.DownloadHttpFailed):
                _download_new(response, output_dir)
            self.assertFalse((output_dir / "artifact.zip").exists())

    def test_pre_commit_existing_final_path_family_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            final_path = output_dir / "artifact.zip"
            final_path.write_bytes(b"existing")
            response = _response(b"new")
            with self.assertRaises(download.ArtifactWriteFailed):
                _download_new(response, output_dir)
            self.assertEqual(b"existing", final_path.read_bytes())


class ProvenanceSidecarPostCommitTest(unittest.TestCase):
    """A sidecar write failure after publication never re-decides the artifact."""

    def test_post_commit_sidecar_failure_never_undoes_the_published_artifact(self):
        payload = b"published despite a post-commit sidecar failure"
        response = _response(payload)
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            result, _ = _download_new(response, output_dir)
            self.assertTrue(result.path.exists())

            def failing_mkstemp(*args, **kwargs):
                raise OSError("simulated sidecar temp-file failure")

            with (
                patch.object(download.tempfile, "mkstemp", side_effect=failing_mkstemp),
                self.assertRaises(download.ArtifactWriteFailed),
            ):
                download.write_provenance_sidecar(
                    result.path,
                    order_id="OK0VUZ",
                    message_fingerprint="0123456789abcdef",
                    sha256=result.sha256,
                    byte_count=result.byte_count,
                )

            # The already-committed artifact publication is never re-decided
            # by a post-commit sidecar failure.
            self.assertTrue(result.path.exists())
            self.assertEqual(payload, result.path.read_bytes())
            sidecar_path = output_dir / "Order_OK0VUZ.provenance.json"
            self.assertFalse(sidecar_path.exists())


if __name__ == "__main__":
    unittest.main()
