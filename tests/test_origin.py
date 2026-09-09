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


if __name__ == "__main__":
    unittest.main()
