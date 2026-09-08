"""SSRF-resistant, bounded streaming artifact downloader."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import requests


_REDIRECTS = {301, 302, 303, 307, 308}


class DownloadError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    byte_count: int
    sha256: str


def validate_https_target(url: str, allowed_hosts: tuple[str, ...]):
    """Validate a target before transport connects to it."""

    try:
        target = urlsplit(url)
        port = target.port
    except (TypeError, ValueError):
        raise DownloadError("download_url_rejected") from None
    allowed = {host.casefold() for host in allowed_hosts}
    if (
        target.scheme.casefold() != "https"
        or not target.hostname
        or target.hostname.casefold() not in allowed
        or target.username is not None
        or target.password is not None
        or port not in (None, 443)
        or not target.path.startswith("/")
        or target.fragment
    ):
        raise DownloadError("download_url_rejected")
    return target


def _clean_session(session) -> None:
    session.auth = None
    session.trust_env = False
    if hasattr(session, "cookies"):
        session.cookies.clear()
    if hasattr(session, "headers"):
        session.headers.clear()


def _final_filename(url: str) -> str:
    try:
        filename = unquote(urlsplit(url).path.rsplit("/", 1)[-1], errors="strict")
    except (UnicodeDecodeError, ValueError):
        raise DownloadError("download_url_rejected") from None
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise DownloadError("download_url_rejected")
    return filename


def download_artifact(
    url: str,
    *,
    output_dir: Path,
    allowed_hosts: tuple[str, ...],
    max_bytes: int,
    connect_timeout_seconds: int,
    read_timeout_seconds: int,
    max_redirects: int,
    session,
) -> DownloadResult:
    """Validate every hop, stream exact bytes privately, then publish atomically."""

    _clean_session(session)
    current_url = url
    response = None
    for hop in range(max_redirects + 1):
        validate_https_target(current_url, allowed_hosts)
        try:
            response = session.get(
                current_url,
                allow_redirects=False,
                stream=True,
                timeout=(connect_timeout_seconds, read_timeout_seconds),
                headers={"Accept-Encoding": "identity"},
            )
        except requests.Timeout:
            raise DownloadError("download_timeout") from None
        except requests.RequestException:
            raise DownloadError("download_http_failed") from None
        if response.status_code not in _REDIRECTS:
            break
        location = response.headers.get("Location")
        response.close()
        response = None
        if not location or hop >= max_redirects:
            raise DownloadError("download_redirect_rejected")
        current_url = urljoin(current_url, location)
        try:
            validate_https_target(current_url, allowed_hosts)
        except DownloadError:
            raise DownloadError("download_redirect_rejected") from None
    if response is None:
        raise DownloadError("download_redirect_rejected")

    temp_path: Path | None = None
    try:
        if response.status_code == 404:
            raise DownloadError("download_expired_or_missing")
        if response.status_code >= 400:
            raise DownloadError("download_http_failed")
        encoding = response.headers.get("Content-Encoding", "identity").casefold()
        if encoding not in ("", "identity"):
            raise DownloadError("download_http_failed")
        declared = response.headers.get("Content-Length")
        if declared is not None:
            try:
                declared_bytes = int(declared)
            except (TypeError, ValueError):
                raise DownloadError("download_http_failed") from None
            if declared_bytes < 0:
                raise DownloadError("download_http_failed")
            if declared_bytes > max_bytes:
                raise DownloadError("download_too_large")

        output_dir.mkdir(parents=True, exist_ok=True)
        descriptor, raw_temp_path = tempfile.mkstemp(
            prefix=".vicmap-download-", suffix=".part", dir=output_dir
        )
        temp_path = Path(raw_temp_path)
        digest = hashlib.sha256()
        received = 0
        with os.fdopen(descriptor, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                next_count = received + len(chunk)
                if next_count > max_bytes:
                    raise DownloadError("download_too_large")
                output.write(chunk)
                digest.update(chunk)
                received = next_count
            output.flush()
            os.fsync(output.fileno())

        final_path = output_dir / _final_filename(current_url)
        try:
            os.link(temp_path, final_path)
        except FileExistsError:
            raise DownloadError("artifact_write_failed") from None
        temp_path.unlink()
        temp_path = None
        return DownloadResult(
            path=final_path,
            byte_count=received,
            sha256=digest.hexdigest(),
        )
    except DownloadError:
        raise
    except OSError:
        raise DownloadError("artifact_write_failed") from None
    finally:
        response.close()
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
