import tempfile
import unittest
import base64
from pathlib import Path
from unittest import mock

from modules import fedex_module as fedex


def piece(number, code="DL", description="Delivered", delivered_at=""):
    value = {
        "trackingNumberInfo": {"trackingNumber": str(number)},
        "latestStatusDetail": {
            "code": code,
            "statusByLocale": description,
        },
    }
    if delivered_at:
        value["dateAndTimes"] = [
            {"type": "ACTUAL_DELIVERY", "dateTime": delivered_at}
        ]
    return value


class FedexBusinessRulesTests(unittest.TestCase):
    def test_default_status_cache_is_in_data_folder(self):
        self.assertEqual("data", fedex.STATUS_CACHE_FILE.parent.name)
        self.assertEqual("fedex_status_cache.json", fedex.STATUS_CACHE_FILE.name)

    def query_live(self, associated, main=None, save_pdf=True):
        main = main or piece("MASTER")
        session = mock.Mock()
        with mock.patch.object(fedex, "_query_trackingnumbers", return_value=(main, "")), \
             mock.patch.object(fedex, "_query_assoc", return_value=(associated, "")), \
             mock.patch.object(fedex, "_download_pod_to_result") as download:
            result = fedex._query_fedex_one_live(
                "MASTER",
                api_key="key",
                api_secret="secret",
                save_pdf=save_pdf,
                pdf_dir="pod",
                _session=session,
                _token="token",
            )
        return result, download

    def test_single_shipment_uses_main_status(self):
        main = piece("MASTER", "IT", "In transit")
        result, download = self.query_live([piece("MASTER")], main=main)
        self.assertEqual("In transit", result["status"])
        self.assertEqual("", result["is_delivered"])
        download.assert_not_called()

    def test_two_to_thirty_nine_require_every_piece_delivered(self):
        all_delivered = [piece(f"P{i}") for i in range(6)]
        result, download = self.query_live(all_delivered)
        self.assertEqual("Delivered", result["status"])
        self.assertEqual("Y", result["is_delivered"])
        self.assertNotIn("40", result["flag"])
        download.assert_called_once()

        partial = all_delivered[:-1] + [piece("P5", "IT", "In transit")]
        result, download = self.query_live(partial)
        self.assertEqual("In transit", result["status"])
        self.assertEqual("", result["is_delivered"])
        self.assertIn("P5=In transit", result["flag"])
        download.assert_not_called()

    def test_forty_returned_pieces_require_manual_review(self):
        associated = [piece(f"P{i:02}") for i in range(40)]
        result, download = self.query_live(associated)
        self.assertEqual("Delivered", result["status"])
        self.assertEqual("Y", result["is_delivered"])
        self.assertIn("40", result["flag"])
        self.assertIn("人工复核", result["flag"])
        download.assert_called_once()

    def test_undelivered_piece_never_downloads_pod(self):
        associated = [piece(f"P{i:02}") for i in range(39)]
        associated.append(piece("P39", "OD", "Out for delivery"))
        result, download = self.query_live(associated)
        self.assertNotEqual("Y", result["is_delivered"])
        download.assert_not_called()

    def test_status_only_never_downloads_pod(self):
        result, download = self.query_live([piece("P1"), piece("P2")], save_pdf=False)
        self.assertEqual("Y", result["is_delivered"])
        download.assert_not_called()

    def test_pod_numbers_prefer_master_and_deduplicate(self):
        master = piece("MASTER")
        child = piece("CHILD")
        self.assertEqual(
            ["MASTER", "CHILD"],
            fedex._pod_request_numbers("CHILD", child, master),
        )
        self.assertEqual(
            ["MASTER"],
            fedex._pod_request_numbers("MASTER", master, master),
        )

    def test_temporary_failure_cache_fallback(self):
        failed = {
            "status": "",
            "is_delivered": "",
            "arrival_time": "",
            "pdf_file": "",
            "error": "tracking API HTTP 429: too many requests",
            "flag": "",
        }
        cached = {
            "status": "Delivered",
            "is_delivered": "Y",
            "arrival_time": "2026-08-17 11:42",
        }
        merged = fedex._apply_cached_status(failed, cached)
        self.assertTrue(merged["from_cache"])
        self.assertEqual("Delivered", merged["status"])
        self.assertIn("429", merged["error"])

    def test_batch_deduplicates_and_reuses_token(self):
        calls = []

        def fake_query(tracking_number=None, **kwargs):
            calls.append((tracking_number, kwargs["session"], kwargs["token"]))
            return {"tracking_number": tracking_number, "status": "In transit", "error": ""}

        session = object()
        with mock.patch.object(fedex, "query_fedex_one", side_effect=fake_query), \
             mock.patch.object(fedex, "_get_token", return_value="shared-token") as token, \
             mock.patch.object(fedex, "get_shared_session", return_value=session):
            result = fedex.query_fedex_batch(
                ["111", "111", " 222 "],
                api_key="key",
                api_secret="secret",
                request_interval=0,
                failed_queue_rounds=0,
            )

        self.assertEqual(["111", "222"], [item["tracking_number"] for item in result])
        self.assertEqual(["111", "222"], [item[0] for item in calls])
        self.assertTrue(all(item[1] is session for item in calls))
        self.assertTrue(all(item[2] == "shared-token" for item in calls))
        token.assert_called_once()

    def test_cache_file_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cache.json"
            data = {"123": {"status": "Delivered"}}
            fedex._save_status_cache(data, path)
            self.assertEqual(data, fedex._load_status_cache(path))

    def test_public_single_query_uses_shared_session(self):
        shared = object()
        with mock.patch.object(fedex, "get_shared_session", return_value=shared), \
             mock.patch.object(
                 fedex,
                 "_query_fedex_one_live",
                 return_value={"status": "In transit", "error": ""},
             ) as live:
            fedex.query_fedex_one(
                "123",
                api_key="key",
                api_secret="secret",
                use_cache=False,
            )
        self.assertIs(shared, live.call_args.kwargs["_session"])

    def test_signed_pod_request_uses_exact_piece_and_billing_account(self):
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {
            "output": {
                "documents": [base64.b64encode(b"%PDF-signed").decode("ascii")]
            }
        }
        session = mock.Mock()
        exact_piece = {
            "trackingNumberInfo": {
                "trackingNumber": "492670345899",
                "carrierCode": "FDXE",
                "trackingNumberUniqueId": "UNIQUE-ID",
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(
                 fedex, "_query_trackingnumbers", return_value=(exact_piece, "")
             ) as lookup, \
             mock.patch.object(fedex, "_post_with_retry", return_value=response) as post:
            pdf_file, error = fedex._save_pod(
                session,
                "492670345899",
                "token",
                exact_piece,
                temp_dir,
            )
            saved_bytes = Path(pdf_file).read_bytes()

        self.assertEqual("", error)
        self.assertEqual(b"%PDF-signed", saved_bytes)
        lookup.assert_called_once_with(
            session=session,
            token="token",
            tracking_number="492670345899",
            timeout=fedex.REQUEST_TIMEOUT_SECONDS,
        )
        payload = post.call_args.kwargs["json"]
        specification = payload["trackDocumentSpecification"][0]
        self.assertEqual(fedex.FEDEX_ACCOUNT_NUMBER, specification["accountNumber"])
        self.assertEqual(
            "UNIQUE-ID",
            specification["trackingNumberInfo"]["trackingNumberUniqueId"],
        )
        self.assertEqual(
            "SIGNATURE_PROOF_OF_DELIVERY",
            payload["trackDocumentDetail"]["documentType"],
        )
        self.assertTrue(
            post.call_args.kwargs["headers"]["x-customer-transaction-id"]
        )


if __name__ == "__main__":
    unittest.main()
