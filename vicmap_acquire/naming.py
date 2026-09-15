"""Pure D-21 through D-24 target-table normalization and collision detection.

This module has no I/O, opens no database connection (D-23), and does not
import ``discovery``, ``manifest``, ``extraction``, or ``read_mailbox`` --
dependency direction stays leaf-ward. It answers exactly two questions: what
is the deterministic target table name for one source layer, and do two
source layers in the same delivery collide on that name.
"""

from __future__ import annotations

import re
from typing import Sequence, TypeVar


class NamingFailure(RuntimeError):
    """A closed naming failure carrying no source-controlled text."""

    code = "table_name_invalid"

    def __init__(self) -> None:
        super().__init__(self.code)


class TableNameInvalid(NamingFailure):
    code = "table_name_invalid"


class TableNameCollision(NamingFailure):
    code = "table_name_collision"


POSTGRES_KEYWORD_SNAPSHOT = (
    "PostgreSQL 18.6 documentation, Appendix C. SQL Key Words "
    "(https://www.postgresql.org/docs/18/sql-keywords-appendix.html), "
    "'reserved' and 'reserved (can be function or type)' categories of the "
    "PostgreSQL column, transcribed 2026-09-16."
)

# Every keyword whose PostgreSQL column in the Appendix C table is either
# "reserved" or "reserved (can be function or type)" (both categories block
# unquoted use as a table name; the "requires AS" annotation some entries
# carry is orthogonal -- it governs column-label use, not this rule).
# Transcribed from the appendix table itself, not a hand-typed shortlist --
# see POSTGRES_KEYWORD_SNAPSHOT.
_RESERVED_KEYWORDS = frozenset(
    {
        "all", "analyse", "analyze", "and", "any", "array", "as", "asc",
        "asymmetric", "authorization", "binary", "both", "case", "cast", "check",
        "collate", "collation", "column", "concurrently", "constraint", "create",
        "cross", "current_catalog", "current_date", "current_role",
        "current_schema", "current_time", "current_timestamp", "current_user",
        "default", "deferrable", "desc", "distinct", "do", "else", "end",
        "except", "false", "fetch", "for", "foreign", "freeze", "from", "full",
        "grant", "group", "having", "ilike", "in", "initially", "inner",
        "intersect", "into", "is", "isnull", "join", "lateral", "leading",
        "left", "like", "limit", "localtime", "localtimestamp", "natural", "not",
        "notnull", "null", "offset", "on", "only", "or", "order", "outer",
        "overlaps", "placing", "primary", "references", "returning", "right",
        "select", "session_user", "similar", "some", "symmetric", "system_user",
        "table", "tablesample", "then", "to", "trailing", "true", "union",
        "unique", "user", "using", "variadic", "verbose", "when", "where",
        "window", "with",
    }
)

_MAX_NAME_BYTES = 63

_SEPARATOR_RUN = re.compile(r"[-_ .]+")
_VALID_CHARSET = re.compile(r"[a-z0-9_]+")
_LEADING_DIGIT = re.compile(r"[0-9]")

_T = TypeVar("_T")


def _compose_and_casefold(dataset_stem: object, layer_name: object) -> str:
    """Validate both inputs are non-blank strings and casefold their join.

    A non-string input, an empty string, or a whitespace-only string on
    either side is a typed closed failure -- the function is total with
    respect to its inputs, never a bare ``TypeError``.
    """

    if not isinstance(dataset_stem, str) or not dataset_stem.strip():
        raise TableNameInvalid()
    if not isinstance(layer_name, str) or not layer_name.strip():
        raise TableNameInvalid()
    return f"{dataset_stem}_{layer_name}".casefold()


def _collapse_separators(value: str) -> str:
    """Collapse runs of ``-``, ``_``, space, and ``.`` to one ``_``.

    Leading and trailing underscores are then stripped from the result.
    """

    collapsed = _SEPARATOR_RUN.sub("_", value)
    return collapsed.strip("_")


def _check_charset(value: str) -> None:
    """Reject anything outside ``[a-z0-9_]``, and reject an empty result.

    Runs before the byte-length check so a non-ASCII character fails on
    charset rather than producing a byte length that disagrees with its
    character length (no character survives this check that could ever
    make that disagreement possible). Nothing is transliterated,
    Unicode-normalized, or silently dropped -- a value outside the
    admitted set is always a typed closed failure.
    """

    if not value or _VALID_CHARSET.fullmatch(value) is None:
        raise TableNameInvalid()


def _check_leading_digit(value: str) -> None:
    """Reject a result whose first character is a digit."""

    if _LEADING_DIGIT.match(value):
        raise TableNameInvalid()


def _check_reserved_keyword(value: str) -> None:
    """Reject a result equal to a blocking-category PostgreSQL keyword."""

    if value in _RESERVED_KEYWORDS:
        raise TableNameInvalid()


def _check_byte_length(value: str) -> None:
    """Reject a result whose UTF-8 encoding exceeds 63 bytes.

    Never truncated and never given a hash suffix -- exceeding the limit
    is always a typed closed failure. Measured in bytes regardless of the
    admitted charset being ASCII-only, so the rule stays byte-exact if the
    admitted set is ever widened.
    """

    if len(value.encode("utf-8")) > _MAX_NAME_BYTES:
        raise TableNameInvalid()


def normalize_target_table_name(dataset_stem: str, layer_name: str) -> str:
    """Compose ``{dataset_stem}_{layer_name}``, casefold, and normalize (D-21/D-22).

    Runs of ``-``, ``_``, space, and ``.`` collapse to a single ``_``, and
    leading/trailing underscores are stripped from the composed result.
    Every deviation from the strict ``[a-z0-9_]`` result -- an
    out-of-charset character, a leading digit, a PostgreSQL reserved word
    (either blocking category), or a UTF-8 encoding over 63 bytes -- raises
    ``TableNameInvalid``. No silent truncation, no hash suffixes, and the
    function is total with respect to its inputs (a non-string input raises
    ``TableNameInvalid`` rather than a bare ``TypeError``).
    """

    combined = _compose_and_casefold(dataset_stem, layer_name)
    collapsed = _collapse_separators(combined)
    _check_charset(collapsed)
    _check_leading_digit(collapsed)
    _check_reserved_keyword(collapsed)
    _check_byte_length(collapsed)
    return collapsed


def assign_target_table_names(
    profiles: Sequence[_T],
) -> tuple[tuple[_T, str], ...]:
    """Assign a normalized target name to each profile; hard-stop on collision.

    Every profile is normalized first, in input order, before any collision
    comparison happens -- a delivery containing both an invalid name and a
    collision always reports the invalid name (``TableNameInvalid``), never
    whichever the iteration order happened to reach first. A collision is
    two distinct source layers in the same delivery normalizing to the same
    target name (D-23/D-24) -- never silently resolved by picking one
    variant, and compared by exact equality over the normalized name only.
    An empty ``profiles`` sequence returns an empty tuple: a zero-layer
    delivery is discovery's ``DeliveryEmpty`` concern, not naming's. Each
    call's collision scope is exactly the profiles passed to it -- nothing
    persists across calls, so an existing published table can never be
    treated as a collision here (D-23 never opens a database connection).
    """

    try:
        normalized = tuple(
            (profile, normalize_target_table_name(profile.dataset_stem, profile.layer_name))
            for profile in profiles
        )
    except NamingFailure:
        raise
    except Exception:
        raise TableNameInvalid() from None

    seen: dict[str, _T] = {}
    for profile, target in normalized:
        if target in seen:
            raise TableNameCollision()
        seen[target] = profile
    return normalized
