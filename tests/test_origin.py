"""Regressions for the pure authenticated-origin policy module."""

from __future__ import annotations

import unittest
from email.message import EmailMessage

from vicmap_acquire.origin import (
    OriginPolicy,
    OriginUnauthenticated,
    parse_authentication_results,
    verify_authenticated_origin,
)


SENDER = "noreply@datashare.maps.vic.gov.au"
AUTH_RESULTS_PASS = (
    "spf=pass smtp.mailfrom=maps.vic.gov.au;"
    "dkim=pass (signature was verified) header.d=maps.vic.gov.au;"
    "dmarc=pass action=none header.from=datashare.maps.vic.gov.au;"
    "compauth=pass reason=100"
)


def _policy(**overrides) -> OriginPolicy:
    arguments = {
        "allowed_senders": (SENDER,),
        "required_authentication_results": ("dkim", "dmarc", "compauth"),
    }
    arguments.update(overrides)
    return OriginPolicy(**arguments)


def _mime(*, from_header: str = SENDER, auth_results: str | tuple[str, ...] | None = AUTH_RESULTS_PASS) -> bytes:
    message = EmailMessage()
    message["From"] = from_header
    message["To"] = "automations@vegetationlink.com.au"
    message["Subject"] = "Your DataShare Order OK0VUZ is ready to download"
    if auth_results is None:
        pass
    elif isinstance(auth_results, tuple):
        for value in auth_results:
            message["Authentication-Results"] = value
    else:
        message["Authentication-Results"] = auth_results
    message.set_content("See the archive link.")
    return message.as_bytes()


def _auth_header(
    *,
    spf: str = "pass",
    dkim: str = "pass",
    dmarc: str = "pass",
    compauth: str = "pass",
    header_d: str = "maps.vic.gov.au",
    header_from: str = "datashare.maps.vic.gov.au",
) -> str:
    return (
        f"spf={spf} smtp.mailfrom=maps.vic.gov.au;"
        f"dkim={dkim} (signature was verified) header.d={header_d};"
        f"dmarc={dmarc} action=none header.from={header_from};"
        f"compauth={compauth} reason=100"
    )


class ParseAuthenticationResultsTest(unittest.TestCase):
    def test_verdicts_and_properties_are_extracted_with_comments_discarded(self):
        verdicts, properties = parse_authentication_results(AUTH_RESULTS_PASS)

        self.assertEqual(
            {"spf": "pass", "dkim": "pass", "dmarc": "pass", "compauth": "pass"},
            verdicts,
        )
        self.assertEqual("maps.vic.gov.au", properties["header.d"])
        self.assertEqual("datashare.maps.vic.gov.au", properties["header.from"])


class VerifyAuthenticatedOriginTest(unittest.TestCase):
    def test_passing_dkim_dmarc_compauth_returns_the_authenticated_from_address(self):
        address = verify_authenticated_origin(_mime(), SENDER, _policy())

        self.assertEqual(SENDER, address)

    def test_from_address_not_in_allowlist_is_rejected(self):
        with self.assertRaises(OriginUnauthenticated) as caught:
            verify_authenticated_origin(
                _mime(from_header="noreply@attacker.example"),
                "noreply@attacker.example",
                _policy(),
            )

        self.assertEqual("origin_unauthenticated", caught.exception.code)

    def test_metadata_sender_disagreement_is_rejected(self):
        with self.assertRaises(OriginUnauthenticated):
            verify_authenticated_origin(_mime(), "someone-else@example.test", _policy())

    def test_missing_authentication_results_header_is_rejected(self):
        with self.assertRaises(OriginUnauthenticated):
            verify_authenticated_origin(
                _mime(auth_results=None), SENDER, _policy()
            )

    def test_failing_required_verdict_is_rejected(self):
        failing = (
            "spf=pass smtp.mailfrom=maps.vic.gov.au;"
            "dkim=fail (signature verification failed) header.d=maps.vic.gov.au;"
            "dmarc=pass action=none header.from=datashare.maps.vic.gov.au;"
            "compauth=pass reason=100"
        )
        with self.assertRaises(OriginUnauthenticated):
            verify_authenticated_origin(_mime(auth_results=failing), SENDER, _policy())


class HardenedOriginParserTest(unittest.TestCase):
    def test_empty_whitespace_and_unterminated_comment_headers_are_rejected(self):
        for auth_results in ("", "   ", "dkim=pass (unterminated comment"):
            with self.subTest(auth_results=auth_results):
                with self.assertRaises(OriginUnauthenticated):
                    verify_authenticated_origin(
                        _mime(auth_results=auth_results), SENDER, _policy()
                    )

    def test_required_method_absent_from_header_is_rejected(self):
        header = (
            "spf=pass smtp.mailfrom=maps.vic.gov.au;"
            "dkim=pass (signature was verified) header.d=maps.vic.gov.au;"
            "dmarc=pass action=none header.from=datashare.maps.vic.gov.au"
        )
        with self.assertRaises(OriginUnauthenticated):
            verify_authenticated_origin(_mime(auth_results=header), SENDER, _policy())

    def test_non_pass_verdicts_are_all_rejected(self):
        for verdict in (
            "fail",
            "none",
            "neutral",
            "temperror",
            "permerror",
            "softfail",
            "bestguesspass",
        ):
            with self.subTest(verdict=verdict):
                header = _auth_header(dkim=verdict)
                with self.assertRaises(OriginUnauthenticated):
                    verify_authenticated_origin(
                        _mime(auth_results=header), SENDER, _policy()
                    )

    def test_sibling_domain_sharing_a_suffix_is_rejected_but_true_parent_is_accepted(self):
        header = _auth_header(header_d="evilmaps.vic.gov.au")
        with self.assertRaises(OriginUnauthenticated):
            verify_authenticated_origin(_mime(auth_results=header), SENDER, _policy())

        accepted_header = _auth_header(header_d="maps.vic.gov.au")
        address = verify_authenticated_origin(
            _mime(auth_results=accepted_header), SENDER, _policy()
        )
        self.assertEqual(SENDER, address)

    def test_header_from_disagreeing_with_from_domain_is_rejected(self):
        header = _auth_header(header_from="attacker.example")
        with self.assertRaises(OriginUnauthenticated):
            verify_authenticated_origin(_mime(auth_results=header), SENDER, _policy())

    def test_dmarc_header_from_absent_entirely_is_rejected(self):
        # Unlike the mismatched-value case above, this DMARC part carries
        # no header.from property at all -- absence must fail the same
        # closed path as a mismatch, not be skipped as "nothing to check".
        header = (
            "spf=pass smtp.mailfrom=maps.vic.gov.au;"
            "dkim=pass (signature was verified) header.d=maps.vic.gov.au;"
            "dmarc=pass action=none;"
            "compauth=pass reason=100"
        )
        with self.assertRaises(OriginUnauthenticated) as caught:
            verify_authenticated_origin(_mime(auth_results=header), SENDER, _policy())
        self.assertEqual("origin_unauthenticated", caught.exception.code)

    def test_dmarc_header_from_blank_or_whitespace_only_is_rejected(self):
        # The tokenizer splits each Authentication-Results segment on
        # whitespace before a token's value is ever inspected, so a value
        # consisting purely of whitespace can never survive as non-empty
        # token content -- it always resolves to the same reachable empty
        # string as a quoted-empty value. Both spellings below exercise
        # that same "blank" outcome through the two ways it is reachable:
        # an explicit empty quoted value, and a bare trailing "=" with
        # nothing after it.
        blank_headers = (
            _auth_header(header_from='""'),
            (
                "spf=pass smtp.mailfrom=maps.vic.gov.au;"
                "dkim=pass header.d=maps.vic.gov.au;"
                "dmarc=pass action=none header.from=;"
                "compauth=pass reason=100"
            ),
        )
        for header in blank_headers:
            with self.subTest(header=header):
                with self.assertRaises(OriginUnauthenticated) as caught:
                    verify_authenticated_origin(
                        _mime(auth_results=header), SENDER, _policy()
                    )
                self.assertEqual("origin_unauthenticated", caught.exception.code)

    def test_dmarc_header_from_unparseable_as_a_domain_is_rejected(self):
        header = _auth_header(header_from="not_a_domain###")
        with self.assertRaises(OriginUnauthenticated) as caught:
            verify_authenticated_origin(_mime(auth_results=header), SENDER, _policy())
        self.assertEqual("origin_unauthenticated", caught.exception.code)

    def test_dmarc_header_from_present_and_aligned_is_still_accepted(self):
        # The real, live-observed verdict/property shape: dkim=pass,
        # dmarc=pass, compauth=pass with header.d and header.from both
        # naming the sending subdomain. The fix must not reject real mail.
        header = _auth_header(
            header_d="datashare.maps.vic.gov.au",
            header_from="datashare.maps.vic.gov.au",
        )
        address = verify_authenticated_origin(
            _mime(auth_results=header), SENDER, _policy()
        )
        self.assertEqual(SENDER, address)

    def test_from_header_cardinality_violations_are_rejected(self):
        subject = "Subject: Your DataShare Order OK0VUZ is ready to download\r\n"
        auth = f"Authentication-Results: {AUTH_RESULTS_PASS}\r\n"
        to_header = "To: automations@vegetationlink.com.au\r\n"

        two_from = (
            f"From: {SENDER}\r\nFrom: {SENDER}\r\n{to_header}{subject}{auth}\r\nbody\r\n"
        ).encode()
        zero_from = (f"{to_header}{subject}{auth}\r\nbody\r\n").encode()
        two_addresses = (
            f"From: {SENDER}, other@datashare.maps.vic.gov.au\r\n"
            f"{to_header}{subject}{auth}\r\nbody\r\n"
        ).encode()

        for mime_content in (two_from, zero_from, two_addresses):
            with self.subTest(mime_content=mime_content[:40]):
                with self.assertRaises(OriginUnauthenticated):
                    verify_authenticated_origin(mime_content, SENDER, _policy())

    def test_non_bytes_empty_and_unparseable_mime_content_is_rejected(self):
        for mime_content in (None, "not-bytes", b"", 12345):
            with self.subTest(mime_content=mime_content):
                with self.assertRaises(OriginUnauthenticated):
                    verify_authenticated_origin(mime_content, SENDER, _policy())

    def test_verdict_and_property_comparison_is_casefolded(self):
        header = (
            "SPF=Pass smtp.mailfrom=maps.vic.gov.au;"
            "DKIM=Pass (signature was verified) header.D=Maps.Vic.Gov.AU;"
            "DMARC=Pass action=none header.From=Datashare.Maps.Vic.Gov.AU;"
            "COMPAUTH=Pass reason=100"
        )
        address = verify_authenticated_origin(
            _mime(auth_results=header), SENDER, _policy()
        )
        self.assertEqual(SENDER, address)

    def test_no_raised_error_leaks_seeded_private_mime_content(self):
        message = EmailMessage()
        message["From"] = "noreply@attacker.example"
        message["To"] = "automations@vegetationlink.com.au"
        message["Subject"] = "private-seeded-subject-marker"
        message["Message-ID"] = "<private-seeded-message-id-marker@example.test>"
        message.set_content("private-seeded-body-marker")
        mime_content = message.as_bytes()

        with self.assertRaises(OriginUnauthenticated) as caught:
            verify_authenticated_origin(mime_content, SENDER, _policy())

        for marker in (
            "private-seeded-subject-marker",
            "private-seeded-message-id-marker",
            "private-seeded-body-marker",
            "attacker.example",
        ):
            self.assertNotIn(marker, str(caught.exception))
            self.assertNotIn(marker, repr(caught.exception))


if __name__ == "__main__":
    unittest.main()
