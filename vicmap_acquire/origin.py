"""Pure authenticated-origin policy over already-retrieved MIME headers.

This module has no I/O and no imports from ``candidates``, ``download``, or
``read_mailbox`` -- dependency direction stays leaf-ward. It answers exactly
one question: does this already-retrieved MIME message carry a passing
authentication verdict, recorded by the trusted receiving mail
infrastructure, that binds it to an allowlisted sender domain?
"""

from __future__ import annotations

from dataclasses import dataclass
from email import policy as email_policy
from email.parser import BytesParser


_AUTH_METHODS = frozenset(
    {"spf", "dkim", "dmarc", "compauth", "arc", "bimi", "iprev", "dkim-atps"}
)


class OriginUnauthenticated(RuntimeError):
    """Closed authenticated-origin failure containing no source-controlled values."""

    code = "origin_unauthenticated"
    stage = "candidate"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class OriginPolicy:
    allowed_senders: tuple[str, ...]
    required_authentication_results: tuple[str, ...]


def _strip_comments(value: str) -> str:
    """Remove parenthesised comment groups, honouring nesting, no backtracking."""

    result: list[str] = []
    depth = 0
    for character in value:
        if character == "(":
            depth += 1
            continue
        if character == ")":
            if depth == 0:
                raise ValueError("unbalanced parenthesised comment")
            depth -= 1
            continue
        if depth == 0:
            result.append(character)
    if depth != 0:
        raise ValueError("unterminated parenthesised comment")
    return "".join(result)


def parse_authentication_results(value: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return ``(verdicts, properties)`` parsed from one header value.

    Parsing is case-insensitive on keys and values. Parenthesised comments
    (honouring nesting) are stripped before tokenizing. The remainder is
    split on ``;``; within each part, the first ``name=value`` token whose
    name is a known authentication method becomes that part's verdict, and
    every other ``name=value`` token whose name contains a ``.`` is recorded
    as a property. A part with no recognised verdict is ignored but does not
    fail the parse. A token that cannot be tokenized as ``name=value`` raises
    ``ValueError``.
    """

    if not isinstance(value, str):
        raise ValueError("Authentication-Results value must be a string")

    stripped = _strip_comments(value)
    verdicts: dict[str, str] = {}
    properties: dict[str, str] = {}

    for part in stripped.split(";"):
        tokens = part.split()
        if not tokens:
            continue

        parsed_tokens: list[tuple[str, str]] = []
        for token in tokens:
            if "=" not in token:
                raise ValueError(f"token is not name=value: {token!r}")
            name, _, raw_value = token.partition("=")
            name = name.strip().casefold()
            raw_value = raw_value.strip()
            if not name:
                raise ValueError("token name must be non-empty")
            parsed_tokens.append((name, raw_value))

        verdict_recorded = False
        for name, raw_value in parsed_tokens:
            if not verdict_recorded and name in _AUTH_METHODS:
                verdicts[name] = raw_value.strip('"').casefold()
                verdict_recorded = True
            elif "." in name:
                properties[name] = raw_value.strip('"').casefold()

    return verdicts, properties


def _domain_aligned(domain: str, header_d: str) -> bool:
    """Return True only when ``header_d`` names ``domain`` or a parent of it.

    Matches on label boundaries only: a substring suffix that does not fall
    on a ``.``-delimited boundary must not align (``evilmaps.vic.gov.au``
    must never align with ``maps.vic.gov.au``-suffixed domains it merely
    shares trailing characters with).
    """

    return domain == header_d or domain.endswith("." + header_d)


def verify_authenticated_origin(
    mime_content: bytes, metadata_sender: str, policy: OriginPolicy
) -> str:
    """Return the authenticated ``From`` address, or raise ``OriginUnauthenticated``.

    Total with respect to its inputs: any exception raised while parsing or
    evaluating the message is converted to ``OriginUnauthenticated`` and
    nothing else escapes.
    """

    try:
        if not isinstance(mime_content, bytes) or not mime_content:
            raise ValueError("mime_content must be non-empty bytes")

        message = BytesParser(policy=email_policy.default).parsebytes(mime_content)

        from_headers = message.get_all("From")
        if not from_headers or len(from_headers) != 1:
            raise ValueError("exactly one From header is required")
        addresses = from_headers[0].addresses
        if len(addresses) != 1:
            raise ValueError("exactly one From address is required")
        from_address = addresses[0].addr_spec
        if not isinstance(from_address, str) or not from_address:
            raise ValueError("From address must be a non-empty address")
        from_address_cf = from_address.casefold()

        allowed = {item.strip().casefold() for item in policy.allowed_senders}
        if from_address_cf not in allowed:
            raise ValueError("From address is not allowlisted")

        if not isinstance(metadata_sender, str):
            raise ValueError("metadata_sender must be a string")
        if metadata_sender.strip().casefold() != from_address_cf:
            raise ValueError(
                "metadata sender disagrees with the authenticated From address"
            )

        auth_results_headers = message.get_all("Authentication-Results")
        if not auth_results_headers:
            raise ValueError("Authentication-Results header is required")

        from_domain = from_address_cf.rsplit("@", 1)[-1]
        if not from_domain:
            raise ValueError("From address must include a domain")

        required_cf = {method.casefold() for method in policy.required_authentication_results}

        for raw_header in auth_results_headers:
            header_text = str(raw_header).replace("\n", " ")
            verdicts, properties = parse_authentication_results(header_text)

            for method in required_cf:
                if verdicts.get(method) != "pass":
                    raise ValueError("required authentication method did not pass")

            if "dkim" in required_cf:
                header_d = properties.get("header.d")
                if not header_d or not _domain_aligned(from_domain, header_d):
                    raise ValueError(
                        "dkim header.d is not aligned with the From domain"
                    )

            if "dmarc" in required_cf:
                header_from = properties.get("header.from")
                if header_from is not None and header_from != from_domain:
                    raise ValueError(
                        "dmarc header.from disagrees with the From domain"
                    )

        return from_address
    except OriginUnauthenticated:
        raise
    except Exception:
        raise OriginUnauthenticated() from None
