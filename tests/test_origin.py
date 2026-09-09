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


if __name__ == "__main__":
    unittest.main()
