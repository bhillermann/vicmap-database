"""Pure recognition and deterministic selection of trusted mail candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from typing import Callable, Iterable
from urllib.parse import unquote, urlsplit

from vicmap_acquire.graph import MessageMetadata


_TEXT_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"']+")


class CandidateFailure(RuntimeError):
    """Closed candidate-policy failure containing no source-controlled values."""

    code = "candidate_ambiguous"

    def __init__(self):
        super().__init__(self.code)


class CandidateNone(CandidateFailure):
    code = "candidate_none"


class CandidateAmbiguous(CandidateFailure):
    code = "candidate_ambiguous"


class OrderIdMismatch(CandidateFailure):
    code = "order_id_mismatch"


# Compatibility name consumed by the Plan 01 acquisition controller.
CandidateError = CandidateFailure


@dataclass(frozen=True)
class CandidatePolicy:
    allowed_senders: tuple[str, ...]
    allowed_order_ids: tuple[str, ...]
    allow_order_id_mismatch: bool = False


@dataclass(frozen=True)
class Candidate:
    order_id: str
    received_datetime_utc: datetime
    graph_message_id: str
    sender: str
    artifact_url: str

    @property
    def selection_key(self) -> tuple[datetime, str]:
        try:
            received = self.received_datetime_utc
            if (
                not isinstance(received, datetime)
                or received.tzinfo is None
                or received.utcoffset() is None
                or not isinstance(self.graph_message_id, str)
                or not self.graph_message_id
            ):
                raise CandidateAmbiguous()
            return (received.astimezone(timezone.utc), self.graph_message_id)
        except CandidateFailure:
            raise
        except Exception:
            raise CandidateAmbiguous() from None


class _AnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []
        self.visible_urls: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.casefold() != "a":
            return
        for key, value in attrs:
            if key.casefold() == "href" and isinstance(value, str):
                self.urls.append(value)

    def handle_data(self, data):
        self.visible_urls.extend(extract_text_urls(data))


def _subject_order_id(subject: str, allowed_order_ids: tuple[str, ...]) -> str | None:
    for order_id in allowed_order_ids:
        expected = f"Your DataShare Order {order_id} is ready to download"
        if subject.casefold() == expected.casefold():
            return order_id
    return None


def _archive_order_id(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        filename = unquote(parsed.path.rsplit("/", 1)[-1], errors="strict")
    except (UnicodeDecodeError, ValueError):
        return None
    match = re.fullmatch(r"Order_([^/]+)\.zip", filename)
    return match.group(1) if match else None


def extract_text_urls(text: str) -> list[str]:
    """Return URL occurrences from plain text without deduplication."""

    return _TEXT_URL.findall(text)


def extract_html_hrefs(html: str) -> list[str]:
    """Return anchor href occurrences without rendering or executing HTML."""

    parser = _AnchorCollector()
    parser.feed(html)
    return parser.urls


def _extract_html_urls(html: str) -> list[str]:
    parser = _AnchorCollector()
    parser.feed(html)
    return parser.urls + parser.visible_urls


def _archive_links(urls: Iterable[str]) -> list[tuple[str, str]]:
    links = []
    for url in urls:
        order_id = _archive_order_id(url)
        if order_id is not None:
            links.append((url, order_id))
    return links


def _mime_archive_links(mime_content: bytes) -> list[tuple[str, str]]:
    try:
        if not isinstance(mime_content, bytes):
            raise TypeError
        message = BytesParser(policy=policy.default).parsebytes(mime_content)
        plain = message.get_body(preferencelist=("plain",))
        if plain is not None:
            plain_links = _archive_links(extract_text_urls(plain.get_content()))
            if plain_links:
                return plain_links
        html = message.get_body(preferencelist=("html",))
        if html is None:
            return []
        return _archive_links(_extract_html_urls(html.get_content()))
    except Exception:
        raise CandidateAmbiguous() from None


def recognize_candidate(
    metadata: MessageMetadata,
    mime_content: bytes | Callable[[], bytes],
    policy_config: CandidatePolicy | None = None,
    *,
    allowed_senders: tuple[str, ...] = (),
    allowed_order_ids: tuple[str, ...] = (),
    allow_order_id_mismatch: bool = False,
) -> Candidate | None:
    """Return a candidate only after independent header, MIME, and order checks."""

    candidate_policy = policy_config or CandidatePolicy(
        allowed_senders=allowed_senders,
        allowed_order_ids=allowed_order_ids,
        allow_order_id_mismatch=allow_order_id_mismatch,
    )
    sender = metadata.sender.strip()
    if sender.casefold() not in {
        item.strip().casefold() for item in candidate_policy.allowed_senders
    }:
        return None
    subject_order_id = _subject_order_id(
        metadata.subject, candidate_policy.allowed_order_ids
    )
    if subject_order_id is None:
        return None
    if (
        not isinstance(metadata.received_datetime_utc, datetime)
        or metadata.received_datetime_utc.tzinfo is None
        or metadata.received_datetime_utc.utcoffset() is None
    ):
        raise CandidateAmbiguous()

    try:
        loaded_mime = mime_content() if callable(mime_content) else mime_content
    except Exception:
        raise CandidateAmbiguous() from None
    links = _mime_archive_links(loaded_mime)
    if len(links) != 1:
        raise CandidateAmbiguous()
    artifact_url, filename_order_id = links[0]
    if (
        filename_order_id != subject_order_id
        and not candidate_policy.allow_order_id_mismatch
    ):
        raise OrderIdMismatch()
    return Candidate(
        order_id=subject_order_id,
        received_datetime_utc=metadata.received_datetime_utc.astimezone(timezone.utc),
        graph_message_id=metadata.graph_message_id,
        sender=sender,
        artifact_url=artifact_url,
    )


def select_candidate(candidates: Iterable[Candidate] | None) -> Candidate:
    """Consume all candidates and select one by the complete stable total key."""

    if candidates is None:
        raise CandidateNone()

    by_key: dict[tuple[datetime, str], Candidate] = {}
    try:
        for candidate in candidates:
            if not isinstance(candidate, Candidate):
                raise CandidateAmbiguous()
            key = candidate.selection_key
            previous = by_key.get(key)
            if previous is not None and previous != candidate:
                raise CandidateAmbiguous()
            by_key[key] = candidate
    except CandidateFailure:
        raise
    except Exception:
        raise CandidateAmbiguous() from None

    if not by_key:
        raise CandidateNone()
    return max(by_key.items(), key=lambda item: item[0])[1]
