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


_TEXT_URL = re.compile(r"https://[^\s<>\"']+")


class CandidateError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Candidate:
    order_id: str
    received_datetime_utc: datetime
    graph_message_id: str
    sender: str
    artifact_url: str


class _AnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.casefold() != "a":
            return
        for key, value in attrs:
            if key.casefold() == "href" and isinstance(value, str):
                self.urls.append(value)


def _subject_order_id(subject: str, allowed_order_ids: tuple[str, ...]) -> str | None:
    for order_id in allowed_order_ids:
        expected = f"Your DataShare Order {order_id} is ready to download"
        if subject.casefold() == expected.casefold():
            return order_id
    return None


def _archive_order_id(url: str) -> str | None:
    try:
        filename = unquote(urlsplit(url).path.rsplit("/", 1)[-1], errors="strict")
    except (UnicodeDecodeError, ValueError):
        return None
    match = re.fullmatch(r"Order_([^/]+)\.zip", filename)
    return match.group(1) if match else None


def _mime_urls(mime_content: bytes) -> list[str]:
    try:
        message = BytesParser(policy=policy.default).parsebytes(mime_content)
        plain = message.get_body(preferencelist=("plain",))
        urls = _TEXT_URL.findall(plain.get_content()) if plain is not None else []
        if urls:
            return urls
        html = message.get_body(preferencelist=("html",))
        if html is None:
            return []
        parser = _AnchorCollector()
        parser.feed(html.get_content())
        return parser.urls
    except Exception:
        return []


def recognize_candidate(
    metadata: MessageMetadata,
    mime_loader: Callable[[], bytes],
    *,
    allowed_senders: tuple[str, ...],
    allowed_order_ids: tuple[str, ...],
    allow_order_id_mismatch: bool = False,
) -> Candidate | None:
    """Return a candidate only after independent header, MIME, and order checks."""

    if metadata.received_datetime_utc.tzinfo is None:
        return None
    sender = metadata.sender.strip()
    if sender.casefold() not in {item.strip().casefold() for item in allowed_senders}:
        return None
    subject_order_id = _subject_order_id(metadata.subject, allowed_order_ids)
    if subject_order_id is None:
        return None

    links = []
    for url in _mime_urls(mime_loader()):
        filename_order_id = _archive_order_id(url)
        if filename_order_id in allowed_order_ids:
            links.append((url, filename_order_id))
    if len(links) != 1:
        return None
    artifact_url, filename_order_id = links[0]
    if filename_order_id != subject_order_id and not allow_order_id_mismatch:
        return None
    return Candidate(
        order_id=subject_order_id,
        received_datetime_utc=metadata.received_datetime_utc.astimezone(timezone.utc),
        graph_message_id=metadata.graph_message_id,
        sender=sender,
        artifact_url=artifact_url,
    )


def select_candidate(candidates: Iterable[Candidate]) -> Candidate | None:
    """Select by the complete `(UTC received instant, Graph ID)` ordering key."""

    by_key: dict[tuple[datetime, str], Candidate] = {}
    for candidate in candidates:
        key = (candidate.received_datetime_utc, candidate.graph_message_id)
        previous = by_key.get(key)
        if previous is not None and previous != candidate:
            raise CandidateError("candidate_ambiguous")
        by_key[key] = candidate
    return max(
        by_key.values(),
        key=lambda item: (item.received_datetime_utc, item.graph_message_id),
        default=None,
    )
