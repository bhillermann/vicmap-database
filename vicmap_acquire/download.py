"""SSRF-resistant, bounded streaming artifact downloader."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import SplitResult, unquote, urljoin, urlsplit

import requests


_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_NO_PROGRESS: Callable[[dict[str, object]], None] = lambda event: None


class DownloadFailure(RuntimeError):
    """A closed download failure carrying no remote or local source text."""

    code = "download_http_failed"

    def __init__(self) -> None:
        super().__init__(self.code)


class DownloadUrlRejected(DownloadFailure):
    code = "download_url_rejected"


class DownloadRedirectRejected(DownloadFailure):
    code = "download_redirect_rejected"


class DownloadExpiredOrMissing(DownloadFailure):
    code = "download_expired_or_missing"


class DownloadTimeout(DownloadFailure):
    code = "download_timeout"


class DownloadTooLarge(DownloadFailure):
    code = "download_too_large"


class DownloadHttpFailed(DownloadFailure):
    code = "download_http_failed"


class ArtifactWriteFailed(DownloadFailure):
    code = "artifact_write_failed"


# Plan 01 compatibility: existing callers catch this name and inspect only ``code``.
DownloadError = DownloadFailure


def _positive_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("download policy values must be positive integers")
    return value


def _normalize_url_prefix(value: object) -> str:
    """Validate and normalize one exact HTTPS URL prefix.

    Requires an exact ``https://`` scheme, no userinfo, no query, no
    fragment, no control characters, no whitespace, a hostname that is a
    valid exact hostname by the ``_normalize_allowed_host`` rules, and a
    path that starts with ``/``, contains at least one non-empty segment,
    and ends with ``/``. Returns the value with scheme and authority
    casefolded and the path left byte-exact.
    """

    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
        or any(character.isspace() for character in value)
    ):
        raise ValueError("allowed_url_prefixes entries must be safe scalar strings")
    if value[:8].casefold() != "https://":
        raise ValueError("allowed_url_prefixes entries must use https")

    parsed = urlsplit(value)
    if (
        parsed.scheme.casefold() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "allowed_url_prefixes entries must be a bare https authority and path"
        )

    hostname = parsed.hostname
    if hostname is None or parsed.netloc.casefold() != hostname.casefold():
        raise ValueError(
            "allowed_url_prefixes entries must name an exact host with no port"
        )
    normalized_host = _normalize_allowed_host(hostname)

    path = parsed.path
    segments = [segment for segment in path.split("/") if segment]
    if not path.startswith("/") or not path.endswith("/") or not segments:
        raise ValueError(
            "allowed_url_prefixes path must be a non-root directory prefix"
        )

    return f"https://{normalized_host}{path}"


def _normalize_allowed_host(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("allowed hosts must be exact hostnames")
    normalized = value.casefold()
    if (
        normalized.endswith(".")
        or any(character in normalized for character in "/\\@:#?[]")
        or any(character.isspace() or ord(character) < 32 for character in normalized)
    ):
        raise ValueError("allowed hosts must be exact hostnames")
    parsed = urlsplit(f"https://{normalized}/")
    if parsed.hostname != normalized or parsed.netloc != normalized:
        raise ValueError("allowed hosts must be exact hostnames")
    return normalized


@dataclass(frozen=True)
class DownloadPolicy:
    """Complete non-secret policy for one artifact transfer."""

    allowed_hosts: tuple[str, ...]
    allowed_url_prefixes: tuple[str, ...]
    max_bytes: int
    connect_timeout_seconds: int
    stalled_read_timeout_seconds: int
    progress_interval_seconds: int
    max_redirects: int
    fingerprint_hex_length: int

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_hosts, tuple) or not self.allowed_hosts:
            raise ValueError("allowed_hosts must be a non-empty tuple")
        normalized = tuple(_normalize_allowed_host(host) for host in self.allowed_hosts)
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed_hosts must not contain duplicates")
        object.__setattr__(self, "allowed_hosts", normalized)

        if not isinstance(self.allowed_url_prefixes, tuple) or not self.allowed_url_prefixes:
            raise ValueError("allowed_url_prefixes must be a non-empty tuple")
        normalized_prefixes = tuple(
            _normalize_url_prefix(prefix) for prefix in self.allowed_url_prefixes
        )
        if len(set(normalized_prefixes)) != len(normalized_prefixes):
            raise ValueError("allowed_url_prefixes must not contain duplicates")
        allowed_host_set = set(normalized)
        for prefix in normalized_prefixes:
            prefix_host = urlsplit(prefix).hostname
            if prefix_host is None or prefix_host.casefold() not in allowed_host_set:
                raise ValueError(
                    "allowed_url_prefixes host must be one of allowed_hosts"
                )
        object.__setattr__(self, "allowed_url_prefixes", normalized_prefixes)

        for value in (
            self.max_bytes,
            self.connect_timeout_seconds,
            self.stalled_read_timeout_seconds,
            self.progress_interval_seconds,
            self.max_redirects,
            self.fingerprint_hex_length,
        ):
            _positive_integer(value)
        if self.fingerprint_hex_length > 64:
            raise ValueError("fingerprint length exceeds SHA-256 output")


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    byte_count: int
    sha256: str
    approved_hostname: str = ""
    path_fingerprint: str = ""
    temp_cleanup_deferred: bool = False


def _nonnegative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def format_progress(byte_count: int, total_bytes: int | None) -> dict[str, object]:
    """Build safe progress using integer tenths before presentation conversion."""

    count = _nonnegative_integer(byte_count, "byte_count")
    event: dict[str, object] = {"byte_count": count}
    if total_bytes is None:
        return event
    total = _nonnegative_integer(total_bytes, "total_bytes")
    if total == 0:
        return event
    percent_tenths = min(1000, (count * 1000) // total)
    event["percent"] = percent_tenths / 10
    return event


def validate_https_target(
    url: str, allowed_hosts: tuple[str, ...], allowed_url_prefixes: tuple[str, ...]
) -> SplitResult:
    """Validate a target completely before transport connects to it."""

    try:
        if (
            not isinstance(url, str)
            or not url
            or url != url.strip()
            or any(ord(character) < 32 for character in url)
        ):
            raise ValueError
        target = urlsplit(url)
        port = target.port
        hostname = target.hostname
    except (TypeError, ValueError):
        raise DownloadUrlRejected() from None

    allowed = {host.casefold() for host in allowed_hosts}
    authority = target.netloc.casefold()
    normalized_hostname = hostname.casefold() if hostname else ""
    permitted_authorities = {normalized_hostname, f"{normalized_hostname}:443"}
    if (
        target.scheme.casefold() != "https"
        or not hostname
        or normalized_hostname not in allowed
        or target.username is not None
        or target.password is not None
        or port not in (None, 443)
        or authority not in permitted_authorities
        or not target.path.startswith("/")
        or bool(target.fragment)
    ):
        raise DownloadUrlRejected()

    normalized_target = f"{target.scheme.casefold()}://{normalized_hostname}{target.path}"
    if not any(
        normalized_target.startswith(prefix) for prefix in allowed_url_prefixes
    ):
        raise DownloadUrlRejected()

    return target


def _fsync_directory(directory: Path) -> None:
    """Fsync a directory entry so a completed publish is durably recorded.

    Directory fsync is unsupported on some platforms; any ``OSError`` raised
    by opening, syncing, or closing the directory descriptor is swallowed
    because the publish itself has already committed and this call only
    strengthens durability, never correctness.
    """

    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _publish_artifact(temp_path: Path, final_path: Path) -> bool:
    """Publish ``temp_path`` at ``final_path``; this call is the one commit point.

    A same-directory hard link is the atomic publication step. A
    ``FileExistsError`` from ``os.link`` propagates uncaught -- publication
    did not happen, so the caller translates it to ``ArtifactWriteFailed``
    exactly as before this existed. Once ``os.link`` succeeds, publication is
    committed and cannot be undone by this function: the parent directory is
    fsynced for durability and the temporary name is best-effort removed.
    Returns ``True`` when that cleanup also succeeded, ``False`` when the
    temporary name could not be removed (``temp_cleanup_deferred``). No
    exception raised by post-commit cleanup may leave this function.
    """

    os.link(temp_path, final_path)
    _fsync_directory(final_path.parent)
    try:
        temp_path.unlink()
    except OSError:
        return False
    return True


def _clean_session(session: object) -> None:
    session.auth = None
    session.trust_env = False
    cookies = getattr(session, "cookies", None)
    if cookies is not None:
        cookies.clear()
    headers = getattr(session, "headers", None)
    if headers is not None:
        headers.clear()


def _close(value: object | None) -> None:
    close = getattr(value, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            # Cleanup must never replace a closed project failure with provider text.
            pass


def _target_identity(target: SplitResult) -> tuple[str, int, str, str]:
    return (
        (target.hostname or "").casefold(),
        target.port or 443,
        target.path,
        target.query,
    )


def _request_final_response(
    session: object, url: str, policy: DownloadPolicy
) -> tuple[object, SplitResult]:
    current_url = url
    seen: set[tuple[str, int, str, str]] = set()

    for hop in range(policy.max_redirects + 1):
        try:
            target = validate_https_target(
                current_url, policy.allowed_hosts, policy.allowed_url_prefixes
            )
        except DownloadUrlRejected:
            if hop == 0:
                raise
            raise DownloadRedirectRejected() from None

        identity = _target_identity(target)
        if identity in seen:
            raise DownloadRedirectRejected()
        seen.add(identity)

        try:
            response = session.get(
                current_url,
                allow_redirects=False,
                stream=True,
                timeout=(
                    policy.connect_timeout_seconds,
                    policy.stalled_read_timeout_seconds,
                ),
                headers={"Accept-Encoding": "identity"},
                verify=True,
            )
        except requests.Timeout:
            raise DownloadTimeout() from None
        except requests.RequestException:
            raise DownloadHttpFailed() from None

        status_code = getattr(response, "status_code", None)
        if status_code in _REDIRECTS:
            location = getattr(response, "headers", {}).get("Location")
            _close(response)
            if not isinstance(location, str) or not location or hop >= policy.max_redirects:
                raise DownloadRedirectRejected()
            current_url = urljoin(current_url, location)
            try:
                validate_https_target(
                    current_url, policy.allowed_hosts, policy.allowed_url_prefixes
                )
            except DownloadUrlRejected:
                raise DownloadRedirectRejected() from None
            continue

        if status_code == 404:
            _close(response)
            raise DownloadExpiredOrMissing()
        if status_code != 200:
            _close(response)
            raise DownloadHttpFailed()
        return response, target

    raise DownloadRedirectRejected()


def _final_filename(url: str) -> str:
    try:
        filename = unquote(urlsplit(url).path.rsplit("/", 1)[-1], errors="strict")
    except (UnicodeDecodeError, ValueError):
        raise DownloadUrlRejected() from None
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise DownloadUrlRejected()
    return filename


def _legacy_arguments(
    final_path: Path | None,
    policy: DownloadPolicy | None,
    progress_sink: Callable[[dict[str, object]], None] | None,
    session_factory,
    legacy: dict[str, object],
) -> tuple[
    Path | None,
    DownloadPolicy,
    Callable[[dict[str, object]], None],
    Callable[[], object],
    Path | None,
]:
    """Translate the Plan 01 tracer call without widening the new public policy."""

    if policy is not None:
        if legacy:
            raise TypeError("legacy and policy arguments cannot be combined")
        if final_path is None:
            raise TypeError("final_path is required")
        if not isinstance(policy, DownloadPolicy):
            raise TypeError("policy must be DownloadPolicy")
        sink = _NO_PROGRESS if progress_sink is None else progress_sink
        if not callable(sink):
            raise TypeError("progress_sink must be callable")
        return (
            Path(final_path),
            policy,
            sink,
            session_factory,
            None,
        )

    expected = {
        "output_dir",
        "allowed_hosts",
        "allowed_url_prefixes",
        "max_bytes",
        "connect_timeout_seconds",
        "read_timeout_seconds",
        "max_redirects",
        "session",
    }
    if final_path is not None or set(legacy) != expected:
        raise TypeError("use final_path and DownloadPolicy")
    output_dir = Path(legacy["output_dir"])
    session = legacy["session"]
    translated = DownloadPolicy(
        allowed_hosts=legacy["allowed_hosts"],
        allowed_url_prefixes=legacy["allowed_url_prefixes"],
        max_bytes=legacy["max_bytes"],
        connect_timeout_seconds=legacy["connect_timeout_seconds"],
        stalled_read_timeout_seconds=legacy["read_timeout_seconds"],
        progress_interval_seconds=5,
        max_redirects=legacy["max_redirects"],
        fingerprint_hex_length=16,
    )
    sink = _NO_PROGRESS if progress_sink is None else progress_sink
    if not callable(sink):
        raise TypeError("progress_sink must be callable")
    return None, translated, sink, lambda: session, output_dir


def download_artifact(
    url: str,
    final_path: Path | None = None,
    policy: DownloadPolicy | None = None,
    progress_sink: Callable[[dict[str, object]], None] | None = None,
    session_factory=requests.Session,
    **legacy,
) -> DownloadResult:
    """Validate each hop, stream exact bytes privately, then publish atomically.

    Publication has exactly one commit point: the successful return of
    ``_publish_artifact`` (a same-directory hard link from the private
    temporary name to ``final_path``, fsynced for durability). Every failure
    before that point leaves no final path and removes the private partial.
    Once committed, a failure of the post-commit temporary-name cleanup can
    never be reported as a transfer failure -- the returned
    ``DownloadResult.temp_cleanup_deferred`` records that condition instead,
    so a successful return always agrees with on-disk state: the final path
    exists and nothing this call already decided about gets a second,
    contradictory outcome from the surrounding ``finally`` block.
    """

    final_path, policy, progress_sink, session_factory, legacy_output_dir = (
        _legacy_arguments(final_path, policy, progress_sink, session_factory, legacy)
    )
    session = None
    response = None
    temp_path: Path | None = None
    try:
        try:
            session = session_factory()
            _clean_session(session)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            raise DownloadHttpFailed() from None
        response, target = _request_final_response(session, url, policy)

        try:
            encoding_value = response.headers.get("Content-Encoding", "identity")
        except Exception:
            raise DownloadHttpFailed() from None
        if not isinstance(encoding_value, str):
            raise DownloadHttpFailed()
        encoding = encoding_value.casefold()
        if encoding not in ("", "identity"):
            raise DownloadHttpFailed()
        declared = response.headers.get("Content-Length")
        declared_bytes = None
        if declared is not None:
            if (
                not isinstance(declared, str)
                or not declared
                or not declared.isascii()
                or not declared.isdecimal()
            ):
                raise DownloadHttpFailed()
            declared_bytes = int(declared)
            if declared_bytes > policy.max_bytes:
                raise DownloadTooLarge()

        if legacy_output_dir is not None:
            legacy_output_dir.mkdir(parents=True, exist_ok=True)
            final_path = legacy_output_dir / _final_filename(target.geturl())
        assert final_path is not None
        output_dir = final_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        descriptor, raw_temp_path = tempfile.mkstemp(
            prefix=".vicmap-download-", suffix=".part", dir=output_dir
        )
        temp_path = Path(raw_temp_path)
        digest = hashlib.sha256()
        received = 0
        last_progress_at = time.monotonic()
        with os.fdopen(descriptor, "wb") as output:
            try:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    if not isinstance(chunk, bytes):
                        raise DownloadHttpFailed()
                    next_count = received + len(chunk)
                    if next_count > policy.max_bytes:
                        raise DownloadTooLarge()
                    written = output.write(chunk)
                    if written != len(chunk):
                        raise ArtifactWriteFailed()
                    digest.update(chunk)
                    received = next_count

                    now = time.monotonic()
                    if now - last_progress_at >= policy.progress_interval_seconds:
                        try:
                            progress_sink(format_progress(received, declared_bytes))
                        except (KeyboardInterrupt, SystemExit):
                            raise
                        except Exception:
                            raise ArtifactWriteFailed() from None
                        last_progress_at = now
            except requests.Timeout:
                raise DownloadTimeout() from None
            except requests.RequestException:
                raise DownloadHttpFailed() from None
            output.flush()
            os.fsync(output.fileno())

        if declared_bytes is not None and declared_bytes != received:
            raise DownloadHttpFailed()
        try:
            cleanup_succeeded = _publish_artifact(temp_path, final_path)
        except FileExistsError:
            raise ArtifactWriteFailed() from None
        temp_path = None
        return DownloadResult(
            path=final_path,
            byte_count=received,
            sha256=digest.hexdigest(),
            approved_hostname=(target.hostname or "").casefold(),
            path_fingerprint=hashlib.sha256(target.path.encode("utf-8")).hexdigest()[
                : policy.fingerprint_hex_length
            ],
            temp_cleanup_deferred=not cleanup_succeeded,
        )
    except DownloadFailure:
        raise
    except OSError:
        raise ArtifactWriteFailed() from None
    finally:
        _close(response)
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass
        _close(session)
