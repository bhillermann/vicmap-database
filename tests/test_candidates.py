from __future__ import annotations

import unittest
from datetime import datetime, timezone
from email.message import EmailMessage

from vicmap_acquire.candidates import CandidateError, recognize_candidate
from vicmap_acquire.graph import MessageMetadata


SENDER = "noreply@datashare.maps.vic.gov.au"
READY = "Your DataShare Order {order_id} is ready to download"
BASE_URL = "https://s3.ap-southeast-2.amazonaws.com/private/{filename}"


def _metadata(
    *,
    sender: str = SENDER,
    order_id: str = "OK0VUZ",
    subject: str | None = None,
) -> MessageMetadata:
    return MessageMetadata(
        graph_message_id="opaque-candidate-id",
        received_datetime_utc=datetime(2026, 9, 7, 1, 2, 3, tzinfo=timezone.utc),
        sender=sender,
        subject=subject if subject is not None else READY.format(order_id=order_id),
    )


def _url(filename: str = "Order_OK0VUZ.zip") -> str:
    return BASE_URL.format(filename=filename)


def _mime(*, plain: str | None = None, html: str | None = None) -> bytes:
    message = EmailMessage()
    message["From"] = SENDER
    message["To"] = "automations@vegetationlink.com.au"
    message["Subject"] = READY.format(order_id="OK0VUZ")
    if plain is not None:
        message.set_content(plain)
        if html is not None:
            message.add_alternative(html, subtype="html")
    elif html is not None:
        message.set_content(html, subtype="html")
    return message.as_bytes()


def _recognize(
    metadata: MessageMetadata,
    mime_bytes: bytes,
    *,
    order_ids: tuple[str, ...] = ("OK0VUZ",),
    allow_mismatch: bool = False,
):
    return recognize_candidate(
        metadata,
        lambda: mime_bytes,
        allowed_senders=(SENDER,),
        allowed_order_ids=order_ids,
        allow_order_id_mismatch=allow_mismatch,
    )


class CandidateRecognitionTest(unittest.TestCase):
    def test_exact_sender_allows_surrounding_whitespace_and_casefolding(self):
        candidate = _recognize(
            _metadata(sender=f"  {SENDER.upper()}  "),
            _mime(plain=f"Download {_url()}"),
        )

        self.assertIsNotNone(candidate)
        self.assertEqual("OK0VUZ", candidate.order_id)

    def test_sender_near_misses_do_not_qualify_or_load_mime(self):
        near_misses = (
            f"Vicmap <{SENDER}>",
            f"prefix-{SENDER}",
            f"{SENDER}.attacker.example",
            "noreply@sub.datashare.maps.vic.gov.au",
        )
        for sender in near_misses:
            with self.subTest(sender=sender):
                loaded = []
                candidate = recognize_candidate(
                    _metadata(sender=sender),
                    lambda: loaded.append(True) or _mime(plain=f"Download {_url()}"),
                    allowed_senders=(SENDER,),
                    allowed_order_ids=("OK0VUZ",),
                )
                self.assertIsNone(candidate)
                self.assertEqual([], loaded)

    def test_each_configured_order_uses_the_whole_ready_template_case_insensitively(self):
        for order_id in ("OK0VUZ", "SECOND2"):
            with self.subTest(order_id=order_id):
                candidate = _recognize(
                    _metadata(
                        order_id=order_id,
                        subject=READY.format(order_id=order_id).swapcase(),
                    ),
                    _mime(plain=f"Download {_url(f'Order_{order_id}.zip')}"),
                    order_ids=("OK0VUZ", "SECOND2"),
                )
                self.assertEqual(order_id, candidate.order_id)

    def test_confirmation_and_subject_adjacency_do_not_qualify(self):
        subjects = (
            "Your DataShare Order OK0VUZ is confirmed",
            f"prefix {READY.format(order_id='OK0VUZ')}",
            f"{READY.format(order_id='OK0VUZ')} suffix",
            READY.format(order_id="UNCONFIGURED"),
        )
        for subject in subjects:
            with self.subTest(subject=subject):
                self.assertIsNone(
                    _recognize(
                        _metadata(subject=subject),
                        _mime(plain=f"Download {_url()}"),
                    )
                )

    def test_missing_mime_body_fails_closed_as_ambiguous(self):
        with self.assertRaises(CandidateError) as caught:
            _recognize(_metadata(), _mime())

        self.assertEqual("candidate_ambiguous", caught.exception.code)

    def test_plain_text_archive_occurrence_takes_precedence_over_html(self):
        plain_url = _url()
        html_url = _url("Order_OTHER.zip")
        candidate = _recognize(
            _metadata(),
            _mime(
                plain=f"Download {plain_url}",
                html=f'<a href="{html_url}">other</a>',
            ),
        )

        self.assertEqual(plain_url, candidate.artifact_url)

    def test_html_anchor_href_is_used_when_plain_has_no_archive_candidate(self):
        html_url = _url()
        candidate = _recognize(
            _metadata(),
            _mime(
                plain="See https://example.invalid/instructions for help.",
                html=f'<p><a data-x="1" href="{html_url}">download</a></p>',
            ),
        )

        self.assertEqual(html_url, candidate.artifact_url)

    def test_plain_ambiguity_does_not_fall_back_to_one_html_link(self):
        plain_url = _url()
        with self.assertRaises(CandidateError) as caught:
            _recognize(
                _metadata(),
                _mime(
                    plain=f"First {plain_url}\nSecond {plain_url}",
                    html=f'<a href="{plain_url}">download</a>',
                ),
            )

        self.assertEqual("candidate_ambiguous", caught.exception.code)

    def test_zero_archive_links_fails_closed_as_ambiguous(self):
        with self.assertRaises(CandidateError) as caught:
            _recognize(
                _metadata(),
                _mime(plain="No archive here", html="<p>No archive here</p>"),
            )

        self.assertEqual("candidate_ambiguous", caught.exception.code)

    def test_two_distinct_archive_links_fail_closed_as_ambiguous(self):
        with self.assertRaises(CandidateError) as caught:
            _recognize(
                _metadata(),
                _mime(plain=f"{_url()}\n{_url('Order_SECOND2.zip')}"),
                order_ids=("OK0VUZ", "SECOND2"),
            )

        self.assertEqual("candidate_ambiguous", caught.exception.code)

    def test_repeated_identical_archive_urls_are_counted_as_two_occurrences(self):
        archive_url = _url()
        with self.assertRaises(CandidateError) as caught:
            _recognize(
                _metadata(),
                _mime(plain=f"{archive_url}\n{archive_url}"),
            )

        self.assertEqual("candidate_ambiguous", caught.exception.code)

    def test_order_mismatch_fails_with_specific_closed_reason(self):
        with self.assertRaises(CandidateError) as caught:
            _recognize(
                _metadata(),
                _mime(plain=f"Download {_url('Order_SECOND2.zip')}"),
                order_ids=("OK0VUZ", "SECOND2"),
            )

        self.assertEqual("order_id_mismatch", caught.exception.code)

    def test_reviewed_mismatch_override_retains_canonical_subject_order(self):
        candidate = _recognize(
            _metadata(),
            _mime(plain=f"Download {_url('Order_SECOND2.zip')}"),
            order_ids=("OK0VUZ", "SECOND2"),
            allow_mismatch=True,
        )

        self.assertEqual("OK0VUZ", candidate.order_id)

    def test_filename_comparison_percent_decodes_once_and_is_case_sensitive(self):
        once_encoded = _url("Order_%4F%4B0VUZ.zip")
        candidate = _recognize(_metadata(), _mime(plain=once_encoded))
        self.assertEqual(once_encoded, candidate.artifact_url)

        for filename in ("Order_ok0vuz.zip", "Order_%254F%254B0VUZ.zip"):
            with self.subTest(filename=filename):
                with self.assertRaises(CandidateError) as caught:
                    _recognize(_metadata(), _mime(plain=_url(filename)))
                self.assertEqual("order_id_mismatch", caught.exception.code)

    def test_malformed_mime_fails_with_closed_reason_only(self):
        with self.assertRaises(CandidateError) as caught:
            _recognize(
                _metadata(),
                b"Content-Type: text/plain; charset=unknown-charset\r\n\r\nsecret",
            )

        self.assertEqual("candidate_ambiguous", caught.exception.code)
        self.assertEqual("candidate_ambiguous", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
