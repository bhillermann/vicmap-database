"""Pure D-21/D-22 normalization and D-23/D-24 collision detection.

This module has no I/O, no database access (D-23), and does not import
``discovery`` or ``manifest`` -- dependency direction stays leaf-ward. It
answers exactly two questions: what is the deterministic target table name
for one source layer, and do two source layers in the same delivery collide
on that name.

02-05 adds the reserved-word, leading-digit, and 63-byte rules and their
full test matrix; this tracer implements only the charset/separator-collapse
core those later checks build on.
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

_T = TypeVar("_T")


def normalize_target_table_name(dataset_stem: str, layer_name: str) -> str:
    """Compose ``{dataset_stem}_{layer_name}``, casefold, and normalize (D-21/D-22).

    Collapses runs of ``-``, ``_``, space, and ``.`` to a single ``_``.
    Anything outside ``[a-z0-9_]`` after normalization is a typed closed
    failure -- no silent truncation, no hash suffixes.
    """

    if not isinstance(dataset_stem, str) or not dataset_stem:
        raise TableNameInvalid()
    if not isinstance(layer_name, str) or not layer_name:
        raise TableNameInvalid()

    combined = f"{dataset_stem}_{layer_name}".casefold()
    collapsed = _SEPARATOR_RUN.sub("_", combined)

    if _VALID_CHARSET.fullmatch(collapsed) is None:
        raise TableNameInvalid()

    return collapsed


def assign_target_table_names(
    profiles: Sequence[_T],
) -> tuple[tuple[_T, str], ...]:
    """Assign a normalized target name to each profile; hard-stop on collision.

    A collision is two distinct source layers in the same delivery
    normalizing to the same target name (D-23/D-24) -- never silently
    resolved by picking one variant.
    """

    assigned: dict[str, _T] = {}
    result: list[tuple[_T, str]] = []
    for profile in profiles:
        target = normalize_target_table_name(profile.dataset_stem, profile.layer_name)
        if target in assigned:
            raise TableNameCollision()
        assigned[target] = profile
        result.append((profile, target))
    return tuple(result)
