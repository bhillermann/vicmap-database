"""Differential fuzz test: extraction vs an independently-written oracle.

CRITICAL PROPERTY OF THIS FILE (state it here so a future refactor does not
casually undo it): the oracle below (`_oracle_url_is_visible`) MUST stay
independent of `vicmap_acquire.candidates`'s extraction implementation. It
parses the same html5lib tree the implementation parses, but decides
visibility with its OWN, separately-authored walk -- a different traversal
shape (an explicit iterative stack, not recursion), its own locally-defined
hidden-tag set (not imported from `candidates.py`), and a simple
"does this string appear anywhere visible" existence check rather than
building an ordered href/text list.

This independence is the entire point of this test. A hand-picked test case
already shares the implementation's blind spot -- that is precisely how a
flat suppression counter survived four review passes (01-07's original
depth counter, CR-01, CR-02, and a fourth report that turned out to be a
false positive). If this file ever imports `_walk_visible`,
`_collect_html_urls`, `_HIDDEN_ELEMENTS`, or any other visibility-decision
helper from `vicmap_acquire.candidates` -- even for deduplication -- it
proves nothing anymore. Do not make that refactor.
"""

from __future__ import annotations

import random
import unittest

import html5lib

from vicmap_acquire.candidates import _extract_html_urls

ARCHIVE_URL = "https://s3.ap-southeast-2.amazonaws.com/private/Order_OK0VUZ.zip"
SEED = 20260914
DOCUMENT_COUNT = 2000

# Independently-authored hidden-tag set. Deliberately NOT imported from
# vicmap_acquire.candidates -- see the module docstring above.
_ORACLE_HIDDEN_TAGS = frozenset(
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

_ORACLE_VOID_TAGS = (
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
)

_ORACLE_CONTAINER_TAGS = (
    "div",
    "p",
    "span",
    "section",
    "article",
    "b",
    "i",
    "ul",
    "li",
    "html",
    "body",
    "head",
)

_ORACLE_OPENABLE_TAGS = tuple(
    sorted(_ORACLE_HIDDEN_TAGS | set(_ORACLE_CONTAINER_TAGS))
)

# Measured baseline for THIS generator, THIS seed, and DOCUMENT_COUNT
# documents against the current tree-based implementation: zero
# strand-direction disagreements were observed at authorship time (see
# SUMMARY for the measurement). Strands (we hide what the oracle shows) fail
# closed -- they reject a message rather than accept a bad one -- so they
# are a correctness concern, not a security one. Holding this at its
# measured value means any future regression that starts hiding content the
# oracle considers visible is caught, without blocking on shapes no real
# sender emits. Do not raise this without re-measuring and understanding
# why the count grew.
STRAND_BASELINE = 0


def _oracle_url_is_visible(html: str, needle: str) -> bool:
    """Independently answer "would a reader see `needle` in `html`?"

    Iterative (not recursive), stack-based walk over the same html5lib
    parse tree the implementation parses, written from scratch: its own
    hidden-tag set, its own traversal order, and a plain existence check
    rather than the implementation's ordered href/text-occurrence lists.
    Must never call into `vicmap_acquire.candidates`.
    """

    root = html5lib.parse(html, namespaceHTMLElements=False)
    stack: list[tuple[object, bool]] = [(root, False)]
    while stack:
        node, inherited_hidden = stack.pop()
        tag = node.tag
        is_element = isinstance(tag, str)
        here_hidden = inherited_hidden or (
            is_element and tag.casefold() in _ORACLE_HIDDEN_TAGS
        )
        if is_element and not here_hidden:
            if tag.casefold() == "a":
                href = node.get("href")
                if href and needle in href:
                    return True
            if node.text and needle in node.text:
                return True
        for child in node:
            if child.tail and not here_hidden and needle in child.tail:
                return True
            stack.append((child, here_hidden))
    return False


def _generate_document(rng: random.Random) -> str:
    """Build one fuzz document from a vocabulary of open tags, close tags,
    self-closing forms, void elements, and comments, with the archive URL
    (as plain text or as an anchor href) inserted at a random position.
    Some opened containers are deliberately left unclosed at the end,
    producing malformed nesting.
    """

    as_anchor = rng.random() < 0.5
    marker = f'<a href="{ARCHIVE_URL}">x</a>' if as_anchor else ARCHIVE_URL

    token_count = rng.randint(3, 12)
    marker_index = rng.randint(0, token_count)
    tokens: list[str] = []
    open_stack: list[str] = []

    for index in range(token_count):
        if index == marker_index:
            tokens.append(marker)
        choice = rng.random()
        if choice < 0.30:
            tag = rng.choice(_ORACLE_OPENABLE_TAGS)
            tokens.append(f"<{tag}>")
            open_stack.append(tag)
        elif choice < 0.50 and open_stack:
            tokens.append(f"</{open_stack.pop()}>")
        elif choice < 0.65:
            tag = rng.choice(_ORACLE_OPENABLE_TAGS)
            tokens.append(f"<{tag}/>")
        elif choice < 0.80:
            void_tag = rng.choice(_ORACLE_VOID_TAGS)
            tokens.append(
                f"<{void_tag}>" if rng.random() < 0.5 else f"<{void_tag}/>"
            )
        else:
            tokens.append(f"<!-- {rng.randint(0, 999999)} -->")

    if marker_index == token_count:
        tokens.append(marker)

    while open_stack and rng.random() < 0.5:
        tokens.append(f"</{open_stack.pop()}>")

    return "".join(tokens)


class HtmlVisibilityDifferentialTest(unittest.TestCase):
    def test_zero_leak_direction_disagreements_across_the_seeded_corpus(self):
        rng = random.Random(SEED)
        leaks: list[str] = []
        strand_count = 0

        for _ in range(DOCUMENT_COUNT):
            document = _generate_document(rng)
            implementation_visible = ARCHIVE_URL in _extract_html_urls(document)
            oracle_visible = _oracle_url_is_visible(document, ARCHIVE_URL)

            if implementation_visible and not oracle_visible:
                leaks.append(document)
            elif oracle_visible and not implementation_visible:
                strand_count += 1

        if leaks:
            self.fail(
                f"{len(leaks)} leak-direction disagreement(s) out of "
                f"{DOCUMENT_COUNT} documents (seed {SEED}): the "
                "implementation collected the archive URL as visible, but "
                "the independent oracle says a reader would never see it. "
                "First offending document, reproducible from the seed "
                f"alone:\n{leaks[0]!r}"
            )

        self.assertLessEqual(
            strand_count,
            STRAND_BASELINE,
            f"strand-direction disagreements grew to {strand_count} "
            f"(recorded baseline {STRAND_BASELINE}) across "
            f"{DOCUMENT_COUNT} documents (seed {SEED}) -- investigate "
            "before raising the baseline",
        )


if __name__ == "__main__":
    unittest.main()
