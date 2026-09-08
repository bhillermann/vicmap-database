"""Security and lifecycle regressions for the artifact download boundary."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from collections import deque
from pathlib import Path

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


def _legacy_download(session: _FakeSession, directory: Path, **overrides):
    arguments = {
        "output_dir": directory,
        "allowed_hosts": (ALLOWED_HOST,),
        "max_bytes": 1024,
        "connect_timeout_seconds": 10,
        "read_timeout_seconds": 60,
        "max_redirects": 5,
        "session": session,
    }
    arguments.update(overrides)
    return download.download_artifact(BASE_URL, **arguments)


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
                target = download.validate_https_target(url, (ALLOWED_HOST,))
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
                    download.validate_https_target(url, (ALLOWED_HOST,))
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
        redirect = _FakeResponse(302, headers={"Location": "../final.zip?new=secret"})
        final = _response()
        session = _FakeSession((redirect, final))
        with tempfile.TemporaryDirectory() as directory:
            _legacy_download(session, Path(directory))

        self.assertEqual(
            [
                BASE_URL,
                f"https://{ALLOWED_HOST}/final.zip?new=secret",
            ],
            [call[0] for call in session.calls],
        )
        self.assertTrue(redirect.closed)
        self.assertTrue(final.closed)

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
        first = _FakeResponse(302, headers={"Location": "/second.zip"})
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
            _FakeResponse(302, headers={"Location": f"/hop-{index}.zip"})
            for index in range(1, 7)
        )
        session = _FakeSession(responses)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(download.DownloadError) as caught:
                _legacy_download(session, Path(directory))
        self.assertEqual("download_redirect_rejected", caught.exception.code)
        self.assertEqual(6, len(session.calls))
        self.assertNotIn(
            f"https://{ALLOWED_HOST}/hop-6.zip",
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


if __name__ == "__main__":
    unittest.main()
