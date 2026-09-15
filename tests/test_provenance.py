"""D-32/D-28 provenance sidecar regressions: write, read, and CLI backfill."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from vicmap_acquire import download


ORDER_ID = "OK0VUZ"
FINGERPRINT = "0123456789abcdef"
SHA256 = hashlib.sha256(b"authentic-artifact-bytes").hexdigest()
BYTE_COUNT = len(b"authentic-artifact-bytes")


class WriteProvenanceSidecarTest(unittest.TestCase):
    def test_writes_a_sidecar_with_exactly_the_four_expected_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            final_path = Path(directory) / f"Order_{ORDER_ID}.zip"
            final_path.write_bytes(b"authentic-artifact-bytes")

            sidecar_path = download.write_provenance_sidecar(
                final_path,
                order_id=ORDER_ID,
                message_fingerprint=FINGERPRINT,
                sha256=SHA256,
                byte_count=BYTE_COUNT,
            )

            self.assertTrue(sidecar_path.exists())
            self.assertEqual(
                final_path.parent / f"Order_{ORDER_ID}.provenance.json", sidecar_path
            )
            payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {"order_id", "message_fingerprint", "sha256", "byte_count"},
                set(payload),
            )
            self.assertEqual(ORDER_ID, payload["order_id"])
            self.assertEqual(FINGERPRINT, payload["message_fingerprint"])
            self.assertEqual(SHA256, payload["sha256"])
            self.assertEqual(BYTE_COUNT, payload["byte_count"])

    def test_sidecar_bytes_are_canonical_and_newline_terminated(self):
        with tempfile.TemporaryDirectory() as directory:
            final_path = Path(directory) / f"Order_{ORDER_ID}.zip"
            final_path.write_bytes(b"authentic-artifact-bytes")

            sidecar_path = download.write_provenance_sidecar(
                final_path,
                order_id=ORDER_ID,
                message_fingerprint=FINGERPRINT,
                sha256=SHA256,
                byte_count=BYTE_COUNT,
            )

            raw = sidecar_path.read_bytes()
            self.assertTrue(raw.endswith(b"\n"))
            expected = (
                json.dumps(
                    {
                        "order_id": ORDER_ID,
                        "message_fingerprint": FINGERPRINT,
                        "sha256": SHA256,
                        "byte_count": BYTE_COUNT,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            self.assertEqual(expected, raw)

    def test_writing_over_an_existing_sidecar_raises_and_leaves_it_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            final_path = Path(directory) / f"Order_{ORDER_ID}.zip"
            final_path.write_bytes(b"authentic-artifact-bytes")
            download.write_provenance_sidecar(
                final_path,
                order_id=ORDER_ID,
                message_fingerprint=FINGERPRINT,
                sha256=SHA256,
                byte_count=BYTE_COUNT,
            )
            sidecar_path = (
                final_path.parent / f"Order_{ORDER_ID}.provenance.json"
            )
            original_bytes = sidecar_path.read_bytes()

            with self.assertRaises(download.ArtifactWriteFailed):
                download.write_provenance_sidecar(
                    final_path,
                    order_id=ORDER_ID,
                    message_fingerprint="fedcba9876543210",
                    sha256=hashlib.sha256(b"different bytes").hexdigest(),
                    byte_count=999,
                )

            self.assertEqual(original_bytes, sidecar_path.read_bytes())

    def test_no_leftover_temp_names_after_a_successful_write(self):
        with tempfile.TemporaryDirectory() as directory:
            final_path = Path(directory) / f"Order_{ORDER_ID}.zip"
            final_path.write_bytes(b"authentic-artifact-bytes")
            download.write_provenance_sidecar(
                final_path,
                order_id=ORDER_ID,
                message_fingerprint=FINGERPRINT,
                sha256=SHA256,
                byte_count=BYTE_COUNT,
            )
            leftovers = [
                entry
                for entry in Path(directory).iterdir()
                if entry.name.startswith(".vicmap-download-")
            ]
            self.assertEqual([], leftovers)


class ReadProvenanceSidecarTest(unittest.TestCase):
    def _write_sidecar(self, directory: Path, payload: dict) -> Path:
        sidecar_path = directory / f"Order_{ORDER_ID}.provenance.json"
        sidecar_path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return sidecar_path

    def test_reads_back_a_well_formed_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            self._write_sidecar(
                directory_path,
                {
                    "order_id": ORDER_ID,
                    "message_fingerprint": FINGERPRINT,
                    "sha256": SHA256,
                    "byte_count": BYTE_COUNT,
                },
            )
            artifact_path = directory_path / f"Order_{ORDER_ID}.zip"

            provenance = download.read_provenance_sidecar(
                artifact_path, order_id=ORDER_ID
            )

            self.assertEqual(ORDER_ID, provenance.order_id)
            self.assertEqual(FINGERPRINT, provenance.message_fingerprint)
            self.assertEqual(SHA256, provenance.sha256)
            self.assertEqual(BYTE_COUNT, provenance.byte_count)

    def test_round_trip_through_write_and_read_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            final_path = Path(directory) / f"Order_{ORDER_ID}.zip"
            final_path.write_bytes(b"authentic-artifact-bytes")
            download.write_provenance_sidecar(
                final_path,
                order_id=ORDER_ID,
                message_fingerprint=FINGERPRINT,
                sha256=SHA256,
                byte_count=BYTE_COUNT,
            )

            provenance = download.read_provenance_sidecar(
                final_path, order_id=ORDER_ID
            )
            self.assertEqual(ORDER_ID, provenance.order_id)
            self.assertEqual(FINGERPRINT, provenance.message_fingerprint)
            self.assertEqual(SHA256, provenance.sha256)
            self.assertEqual(BYTE_COUNT, provenance.byte_count)

    def test_missing_file_is_provenance_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_path = Path(directory) / f"Order_{ORDER_ID}.zip"
            with self.assertRaises(download.ProvenanceUnavailable):
                download.read_provenance_sidecar(artifact_path, order_id=ORDER_ID)

    def test_invalid_json_is_provenance_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            sidecar_path = directory_path / f"Order_{ORDER_ID}.provenance.json"
            sidecar_path.write_text("{not valid json", encoding="utf-8")
            artifact_path = directory_path / f"Order_{ORDER_ID}.zip"
            with self.assertRaises(download.ProvenanceUnavailable):
                download.read_provenance_sidecar(artifact_path, order_id=ORDER_ID)

    def test_extra_key_is_provenance_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            self._write_sidecar(
                directory_path,
                {
                    "order_id": ORDER_ID,
                    "message_fingerprint": FINGERPRINT,
                    "sha256": SHA256,
                    "byte_count": BYTE_COUNT,
                    "extra": "unexpected",
                },
            )
            artifact_path = directory_path / f"Order_{ORDER_ID}.zip"
            with self.assertRaises(download.ProvenanceUnavailable):
                download.read_provenance_sidecar(artifact_path, order_id=ORDER_ID)

    def test_missing_key_is_provenance_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            self._write_sidecar(
                directory_path,
                {
                    "order_id": ORDER_ID,
                    "message_fingerprint": FINGERPRINT,
                    "sha256": SHA256,
                },
            )
            artifact_path = directory_path / f"Order_{ORDER_ID}.zip"
            with self.assertRaises(download.ProvenanceUnavailable):
                download.read_provenance_sidecar(artifact_path, order_id=ORDER_ID)

    def test_uppercase_or_short_sha256_is_provenance_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            for bad_sha256 in (SHA256.upper(), SHA256[:63], "0" * 64 + "x"):
                with self.subTest(sha256=bad_sha256):
                    self._write_sidecar(
                        directory_path,
                        {
                            "order_id": ORDER_ID,
                            "message_fingerprint": FINGERPRINT,
                            "sha256": bad_sha256,
                            "byte_count": BYTE_COUNT,
                        },
                    )
                    artifact_path = directory_path / f"Order_{ORDER_ID}.zip"
                    with self.assertRaises(download.ProvenanceUnavailable):
                        download.read_provenance_sidecar(
                            artifact_path, order_id=ORDER_ID
                        )

    def test_byte_count_true_is_provenance_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            self._write_sidecar(
                directory_path,
                {
                    "order_id": ORDER_ID,
                    "message_fingerprint": FINGERPRINT,
                    "sha256": SHA256,
                    "byte_count": True,
                },
            )
            artifact_path = directory_path / f"Order_{ORDER_ID}.zip"
            with self.assertRaises(download.ProvenanceUnavailable):
                download.read_provenance_sidecar(artifact_path, order_id=ORDER_ID)

    def test_byte_count_negative_is_provenance_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            self._write_sidecar(
                directory_path,
                {
                    "order_id": ORDER_ID,
                    "message_fingerprint": FINGERPRINT,
                    "sha256": SHA256,
                    "byte_count": -1,
                },
            )
            artifact_path = directory_path / f"Order_{ORDER_ID}.zip"
            with self.assertRaises(download.ProvenanceUnavailable):
                download.read_provenance_sidecar(artifact_path, order_id=ORDER_ID)

    def test_mismatched_order_id_is_provenance_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            self._write_sidecar(
                directory_path,
                {
                    "order_id": "DIFFERENT",
                    "message_fingerprint": FINGERPRINT,
                    "sha256": SHA256,
                    "byte_count": BYTE_COUNT,
                },
            )
            artifact_path = directory_path / f"Order_{ORDER_ID}.zip"
            with self.assertRaises(download.ProvenanceUnavailable):
                download.read_provenance_sidecar(artifact_path, order_id=ORDER_ID)

    def test_malformed_message_fingerprint_is_provenance_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            for bad_fingerprint in ("TOOSHORT", "0" * 3, "NOTLOWERHEX0000"):
                with self.subTest(fingerprint=bad_fingerprint):
                    self._write_sidecar(
                        directory_path,
                        {
                            "order_id": ORDER_ID,
                            "message_fingerprint": bad_fingerprint,
                            "sha256": SHA256,
                            "byte_count": BYTE_COUNT,
                        },
                    )
                    artifact_path = directory_path / f"Order_{ORDER_ID}.zip"
                    with self.assertRaises(download.ProvenanceUnavailable):
                        download.read_provenance_sidecar(
                            artifact_path, order_id=ORDER_ID
                        )


class RunAcquisitionSidecarIntegrationTest(unittest.TestCase):
    """``run_acquisition`` writes the sidecar beside a real published artifact."""

    def test_successful_run_writes_a_matching_sidecar(self):
        import read_mailbox
        from vicmap_acquire.graph import MessageMetadata

        message_id = "opaque-provenance-message-id"
        artifact_url = (
            "https://s3.ap-southeast-2.amazonaws.com/private/Order_OK0VUZ.zip"
        )
        payload = b"authentic-artifact-bytes"
        metadata = [
            MessageMetadata(
                graph_message_id=message_id,
                received_datetime_utc=__import__("datetime").datetime(
                    2026, 9, 7, tzinfo=__import__("datetime").timezone.utc
                ),
                sender="noreply@datashare.maps.vic.gov.au",
                subject="Your DataShare Order OK0VUZ is ready to download",
            )
        ]

        class Graph:
            def __init__(self, **kwargs):
                pass

            def iter_metadata(self, cutoff_utc):
                return iter(metadata)

            def get_mime_content(self, graph_message_id):
                lines = [
                    "From: noreply@datashare.maps.vic.gov.au",
                    "To: automations@vegetationlink.com.au",
                    "Subject: Your DataShare Order OK0VUZ is ready to download",
                    "Authentication-Results: spf=pass smtp.mailfrom=maps.vic.gov.au;"
                    "dkim=pass (signature was verified) header.d=maps.vic.gov.au;"
                    "dmarc=pass action=none header.from=datashare.maps.vic.gov.au;"
                    "compauth=pass reason=100",
                    "MIME-Version: 1.0",
                    "Content-Type: text/plain; charset=utf-8",
                    "",
                    f"Download: {artifact_url}",
                ]
                return ("\r\n".join(lines) + "\r\n").encode()

        class _Response:
            status_code = 200

            def __init__(self, body: bytes) -> None:
                self.headers = {
                    "Content-Length": str(len(body)),
                    "Content-Encoding": "identity",
                }
                self._body = body
                self.closed = False

            def iter_content(self, chunk_size: int):
                yield self._body

            def close(self) -> None:
                self.closed = True

        class _Session:
            def __init__(self, body: bytes) -> None:
                self.auth = None
                self.cookies = type("C", (), {"clear": lambda self: None})()
                self.headers = {}
                self.trust_env = True
                self.response = _Response(body)
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append(url)
                return self.response

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "artifacts"
            config = read_mailbox.AcquisitionConfig(
                mailbox="automations@vegetationlink.com.au",
                folder="Inbox",
                allowed_senders=("noreply@datashare.maps.vic.gov.au",),
                allowed_order_ids=(ORDER_ID,),
                allowed_hosts=("s3.ap-southeast-2.amazonaws.com",),
                lookback_days=15,
                max_bytes=1024,
                connect_timeout_seconds=10,
                read_timeout_seconds=60,
                progress_interval_seconds=5,
                max_redirects=5,
                fingerprint_hex_chars=16,
                allow_order_id_mismatch=False,
                output_dir=output_dir,
                required_authentication_results=("dkim", "dmarc", "compauth"),
                allowed_url_prefixes=(
                    "https://s3.ap-southeast-2.amazonaws.com/private/",
                ),
            )
            result = read_mailbox.run_acquisition(
                config,
                {
                    "O365_AUTH_ID": "private-client-id",
                    "O365_AUTH_SECRET": "private-client-secret",
                    "TENANT_ID": "private-tenant-id",
                },
                graph_factory=lambda **kwargs: Graph(),
                session_factory=lambda: _Session(payload),
                event_sink=lambda event: None,
            )

            sidecar_path = output_dir / f"Order_{ORDER_ID}.provenance.json"
            self.assertTrue(sidecar_path.exists())
            provenance = download.read_provenance_sidecar(
                result.path, order_id=ORDER_ID
            )
            self.assertEqual(result.sha256, provenance.sha256)
            self.assertEqual(result.byte_count, provenance.byte_count)
            from vicmap_acquire.evidence import fingerprint as compute_fingerprint

            self.assertEqual(
                compute_fingerprint(message_id, 16), provenance.message_fingerprint
            )


class ProvenanceOnlyCliTest(unittest.TestCase):
    """``read_mailbox.py --provenance-only`` backfills without downloading."""

    def _metadata_and_graph(self, message_id: str, artifact_url: str):
        from vicmap_acquire.graph import MessageMetadata
        import datetime as _datetime

        metadata = [
            MessageMetadata(
                graph_message_id=message_id,
                received_datetime_utc=_datetime.datetime(
                    2026, 9, 7, tzinfo=_datetime.timezone.utc
                ),
                sender="noreply@datashare.maps.vic.gov.au",
                subject="Your DataShare Order OK0VUZ is ready to download",
            )
        ]

        class Graph:
            def __init__(self, **kwargs):
                pass

            def iter_metadata(self, cutoff_utc):
                return iter(metadata)

            def get_mime_content(self, graph_message_id):
                lines = [
                    "From: noreply@datashare.maps.vic.gov.au",
                    "To: automations@vegetationlink.com.au",
                    "Subject: Your DataShare Order OK0VUZ is ready to download",
                    "Authentication-Results: spf=pass smtp.mailfrom=maps.vic.gov.au;"
                    "dkim=pass (signature was verified) header.d=maps.vic.gov.au;"
                    "dmarc=pass action=none header.from=datashare.maps.vic.gov.au;"
                    "compauth=pass reason=100",
                    "MIME-Version: 1.0",
                    "Content-Type: text/plain; charset=utf-8",
                    "",
                    f"Download: {artifact_url}",
                ]
                return ("\r\n".join(lines) + "\r\n").encode()

        return Graph

    def test_provenance_only_writes_sidecar_and_never_calls_download_artifact(self):
        import read_mailbox

        message_id = "opaque-provenance-only-message-id"
        artifact_url = (
            "https://s3.ap-southeast-2.amazonaws.com/private/Order_OK0VUZ.zip"
        )
        Graph = self._metadata_and_graph(message_id, artifact_url)

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "artifacts"
            output_dir.mkdir(parents=True)
            artifact_path = output_dir / f"Order_{ORDER_ID}.zip"
            artifact_path.write_bytes(b"already-downloaded-bytes")

            config = read_mailbox.AcquisitionConfig(
                mailbox="automations@vegetationlink.com.au",
                folder="Inbox",
                allowed_senders=("noreply@datashare.maps.vic.gov.au",),
                allowed_order_ids=(ORDER_ID,),
                allowed_hosts=("s3.ap-southeast-2.amazonaws.com",),
                lookback_days=15,
                max_bytes=1024,
                connect_timeout_seconds=10,
                read_timeout_seconds=60,
                progress_interval_seconds=5,
                max_redirects=5,
                fingerprint_hex_chars=16,
                allow_order_id_mismatch=False,
                output_dir=output_dir,
                required_authentication_results=("dkim", "dmarc", "compauth"),
                allowed_url_prefixes=(
                    "https://s3.ap-southeast-2.amazonaws.com/private/",
                ),
            )

            def _forbidden_download_artifact(*args, **kwargs):
                raise AssertionError(
                    "run_provenance must never call download_artifact"
                )

            from unittest.mock import patch

            with patch.object(
                read_mailbox, "download_artifact", _forbidden_download_artifact
            ):
                provenance = read_mailbox.run_provenance(
                    config,
                    {
                        "O365_AUTH_ID": "private-client-id",
                        "O365_AUTH_SECRET": "private-client-secret",
                        "TENANT_ID": "private-tenant-id",
                    },
                    graph_factory=lambda **kwargs: Graph(),
                    event_sink=lambda event: None,
                )

            self.assertEqual(ORDER_ID, provenance.order_id)
            self.assertEqual(
                hashlib.sha256(b"already-downloaded-bytes").hexdigest(),
                provenance.sha256,
            )
            self.assertEqual(len(b"already-downloaded-bytes"), provenance.byte_count)

            sidecar_path = output_dir / f"Order_{ORDER_ID}.provenance.json"
            self.assertTrue(sidecar_path.exists())

    def test_missing_artifact_is_provenance_unavailable(self):
        import read_mailbox

        message_id = "opaque-missing-artifact-message-id"
        artifact_url = (
            "https://s3.ap-southeast-2.amazonaws.com/private/Order_OK0VUZ.zip"
        )
        Graph = self._metadata_and_graph(message_id, artifact_url)

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "artifacts"
            config = read_mailbox.AcquisitionConfig(
                mailbox="automations@vegetationlink.com.au",
                folder="Inbox",
                allowed_senders=("noreply@datashare.maps.vic.gov.au",),
                allowed_order_ids=(ORDER_ID,),
                allowed_hosts=("s3.ap-southeast-2.amazonaws.com",),
                lookback_days=15,
                max_bytes=1024,
                connect_timeout_seconds=10,
                read_timeout_seconds=60,
                progress_interval_seconds=5,
                max_redirects=5,
                fingerprint_hex_chars=16,
                allow_order_id_mismatch=False,
                output_dir=output_dir,
                required_authentication_results=("dkim", "dmarc", "compauth"),
                allowed_url_prefixes=(
                    "https://s3.ap-southeast-2.amazonaws.com/private/",
                ),
            )

            with self.assertRaises(read_mailbox.AcquisitionFailure) as caught:
                read_mailbox.run_provenance(
                    config,
                    {
                        "O365_AUTH_ID": "private-client-id",
                        "O365_AUTH_SECRET": "private-client-secret",
                        "TENANT_ID": "private-tenant-id",
                    },
                    graph_factory=lambda **kwargs: Graph(),
                    event_sink=lambda event: None,
                )
            self.assertEqual("provenance_unavailable", caught.exception.code)

    def test_main_provenance_only_flag_routes_to_run_provenance(self):
        import read_mailbox
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "vicmap.toml"
            config_path.write_text("placeholder", encoding="utf-8")
            fake_config = object()

            calls = []

            def fake_run_provenance(config, credentials, **kwargs):
                calls.append("run_provenance")
                return None

            def fake_run_acquisition(config, credentials, **kwargs):
                calls.append("run_acquisition")
                return None

            with (
                patch.object(read_mailbox, "load_config", return_value=fake_config),
                patch.object(
                    read_mailbox, "run_provenance", side_effect=fake_run_provenance
                ),
                patch.object(
                    read_mailbox, "run_acquisition", side_effect=fake_run_acquisition
                ),
            ):
                exit_code = read_mailbox.main(
                    ["--config", str(config_path), "--provenance-only"]
                )

            self.assertEqual(0, exit_code)
            self.assertEqual(["run_provenance"], calls)


if __name__ == "__main__":
    unittest.main()
