"""Pure recognition and deterministic selection of trusted mail candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from typing import Callable, Iterable
from urllib.parse import unquote, urlsplit

import html5lib

from vicmap_acquire.graph import MessageMetadata
from vicmap_acquire.origin import OriginPolicy, verify_authenticated_origin


_TEXT_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"']+")

# Elements whose entire subtree is never rendered to a reader. Visibility is
# INHERITED down a real HTML5 parse tree from this set -- a node is hidden if
# its own tag is here, or any ancestor's is -- rather than approximated by a
# flat depth counter over a raw tokenizer. That inheritance is the whole
# point of this rewrite: a real tree-construction algorithm (html5lib)
# decides implicit closure, mis-nesting, and insertion-mode quirks (e.g. an
# omitted `</head>`, a `<body>` start tag while one is already open, a
# self-closing slash on a non-void element) exactly as a real browser would,
# instead of a counter approximating them one patched shape at a time.
#
# `head` is included: html5lib's tree construction algorithm decides what is
# actually inside `head` (including implicit closure the moment body content
# begins), so no `01-13`-style one-shot decrement is needed here -- the real
# parser already produces the correct tree.
#
# `meta` and `link` are deliberately NOT here: they are void elements with no
# content model, so a real parser never nests anything inside them -- there
# is nothing for them to suppress, and no special-casing is required the way
# the old counter needed `_VOID_ELEMENTS` to avoid over-counting.
_HIDDEN_ELEMENTS = frozenset(
    {
        "script",
        "style",
        "template",
        "noscript",
        "title",
        "object",
        "applet",
        "iframe",
        "head",
    }
)


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
    required_authentication_results: tuple[str, ...] = ("dkim", "dmarc", "compauth")


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


def _walk_visible(node, hidden: bool, urls: list[str], visible_urls: list[str]) -> None:
    """Recurse a real html5lib parse tree, inheriting hidden-ness down it.

    `hidden` is the visibility state of NODE's own content: its `text` and
    any `a` element's `href`. A child inherits `hidden` unless its own tag
    is in `_HIDDEN_ELEMENTS` -- this inheritance down a real tree, decided
    by html5lib's tree-construction algorithm, is what a flat depth counter
    over a raw tokenizer could only approximate.

    A comment node's `tag` is not a string (html5lib's etree treebuilder
    represents it with a non-string sentinel). Its own content is always
    skipped, but it does not change the hidden state its children or `tail`
    inherit -- a comment is not a hiding container.

    A node's `tail` -- the text between its end tag and the next sibling --
    belongs to its PARENT's rendered flow, not its own: text after
    `</script>` is rendered even though the script itself is not. That is
    why `tail` is gated on `hidden` (this node's own state, i.e. the
    context its children/tail inherit), not on the child's own hidden
    state.
    """

    tag = node.tag
    if isinstance(tag, str):
        own_hidden = hidden or tag.casefold() in _HIDDEN_ELEMENTS
        if not own_hidden:
            if tag.casefold() == "a":
                href = node.get("href")
                if href is not None:
                    urls.append(href)
            if node.text:
                visible_urls.extend(extract_text_urls(node.text))
    else:
        # Comment (or other non-element) node: contributes no content of
        # its own, and does not add hiddenness for its children/tail.
        own_hidden = hidden

    for child in node:
        _walk_visible(child, own_hidden, urls, visible_urls)
        if child.tail and not own_hidden:
            visible_urls.extend(extract_text_urls(child.tail))


def _collect_html_urls(html: str) -> tuple[list[str], list[str]]:
    """Parse `html` with a spec-compliant HTML5 parser and return
    (anchor hrefs, rendered-text URL occurrences), both in document order,
    from non-hidden context only.
    """

    urls: list[str] = []
    visible_urls: list[str] = []
    root = html5lib.parse(html, namespaceHTMLElements=False)
    _walk_visible(root, False, urls, visible_urls)
    return urls, visible_urls


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
    """Return anchor href occurrences from rendered HTML context only.

    Hrefs on anchors nested inside a hidden element (script, style,
    template, noscript, head, title, object, iframe, applet) or inside a
    comment are excluded. Visibility is decided by parsing `html` with a
    real, spec-compliant HTML5 parser (html5lib) and inheriting hidden-ness
    down the resulting tree, so implicit closure, mis-nesting, and
    insertion-mode quirks (an omitted `</head>`, a stray `<body>` tag, a
    self-closing slash on a non-void element) are resolved exactly as a
    real browser resolves them, not approximated by a raw-tokenizer depth
    counter.
    """

    urls, _visible_urls = _collect_html_urls(html)
    return urls


def _extract_html_urls(html: str) -> list[str]:
    urls, visible_urls = _collect_html_urls(html)
    return urls + visible_urls


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
    required_authentication_results: tuple[str, ...] = ("dkim", "dmarc", "compauth"),
) -> Candidate | None:
    """Return a candidate only after independent header, MIME, and order checks."""

    candidate_policy = policy_config or CandidatePolicy(
        allowed_senders=allowed_senders,
        allowed_order_ids=allowed_order_ids,
        allow_order_id_mismatch=allow_order_id_mismatch,
        required_authentication_results=required_authentication_results,
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
    authenticated_sender = verify_authenticated_origin(
        loaded_mime,
        sender,
        OriginPolicy(
            allowed_senders=candidate_policy.allowed_senders,
            required_authentication_results=candidate_policy.required_authentication_results,
        ),
    )
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
        sender=authenticated_sender,
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
