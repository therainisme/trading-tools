import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "futures_investment_analysis.py"
SPEC = importlib.util.spec_from_file_location("futures_investment_analysis", SCRIPT_PATH)
analysis = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = analysis
SPEC.loader.exec_module(analysis)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


def fake_opener(request, timeout):
    url = request.full_url
    if "/fapi/v1/premiumIndex" in url:
        return FakeResponse(
            json.dumps(
                {
                    "symbol": "NVDAUSDT",
                    "markPrice": "230.23000000",
                    "indexPrice": "229.76065300",
                    "lastFundingRate": "0.00000000",
                }
            ).encode("utf-8")
        )
    if "/fapi/v1/fundingRate" in url:
        return FakeResponse(
            json.dumps(
                [{"symbol": "NVDAUSDT", "fundingRate": "0.00029952", "markPrice": "234.94803196"}]
            ).encode("utf-8")
        )
    if "/fapi/v1/openInterest" in url:
        return FakeResponse(json.dumps({"symbol": "NVDAUSDT", "openInterest": "46142.07"}).encode("utf-8"))
    if "/futures/data/openInterestHist" in url:
        return FakeResponse(
            json.dumps(
                [
                    {
                        "symbol": "NVDAUSDT",
                        "sumOpenInterest": "45717.74000000",
                        "sumOpenInterestValue": "10647838.38209647",
                    }
                ]
            ).encode("utf-8")
        )
    if "/futures/data/globalLongShortAccountRatio" in url:
        return FakeResponse(
            json.dumps(
                [{"symbol": "NVDAUSDT", "longAccount": "0.6122", "longShortRatio": "1.5786", "shortAccount": "0.3878"}]
            ).encode("utf-8")
        )
    if "/futures/data/topLongShortAccountRatio" in url:
        return FakeResponse(
            json.dumps(
                [{"symbol": "NVDAUSDT", "longAccount": "0.5871", "longShortRatio": "1.4219", "shortAccount": "0.4129"}]
            ).encode("utf-8")
        )
    if "/futures/data/topLongShortPositionRatio" in url:
        return FakeResponse(
            json.dumps(
                [{"symbol": "NVDAUSDT", "longAccount": "0.5413", "longShortRatio": "1.1801", "shortAccount": "0.4587"}]
            ).encode("utf-8")
        )
    if "/futures/data/takerlongshortRatio" in url:
        return FakeResponse(json.dumps([{"buySellRatio": "0.8849", "sellVol": "8100.3300", "buyVol": "7167.8300"}]).encode("utf-8"))
    if "/fapi/v1/depth" in url:
        return FakeResponse(json.dumps({"bids": [["230.34", "8.10"]], "asks": [["230.35", "2.12"]]}).encode("utf-8"))
    if "/fapi/v1/ticker/bookTicker" in url:
        return FakeResponse(
            json.dumps({"bidPrice": "230.34000", "bidQty": "7.64", "askPrice": "230.35000", "askQty": "2.03"}).encode("utf-8")
        )
    if "/fapi/v1/aggTrades" in url:
        return FakeResponse(json.dumps([{"a": 1, "p": "230.37", "q": "0.03", "m": True}]).encode("utf-8"))
    raise AssertionError(f"unexpected url: {url}")


class FuturesInvestmentAnalysisTests(unittest.TestCase):
    def test_parse_groups_is_ordered_and_unique(self):
        """Purpose: verify group parsing keeps user order and removes duplicates."""
        self.assertEqual(analysis.parse_groups("sentiment,valuation,sentiment"), ("sentiment", "valuation"))

    def test_parse_groups_rejects_unknown_group(self):
        """Purpose: verify unsupported group names fail before fetching data."""
        with self.assertRaises(analysis.AnalysisError):
            analysis.parse_groups("valuation,unknown")

    def test_build_endpoint_specs_includes_all_analysis_groups(self):
        """Purpose: verify the endpoint set covers every requested priority group."""
        options = analysis.AnalysisOptions(symbol="nvdausdt", groups=("valuation", "positioning", "sentiment", "liquidity", "account-risk"), limit=3)

        names = [spec.name for spec in analysis.build_endpoint_specs(options)]

        self.assertIn("premium_index", names)
        self.assertIn("open_interest_history", names)
        self.assertIn("top_trader_long_short_position_ratio", names)
        self.assertIn("order_book_depth", names)
        self.assertIn("account_information", names)
        self.assertIn("income_history", names)

    def test_public_collection_with_fake_opener(self):
        """Purpose: verify public analysis collection works without credentials."""
        options = analysis.AnalysisOptions(symbol="NVDAUSDT", groups=("valuation", "positioning", "sentiment", "liquidity"), limit=1, depth_limit=5, agg_trades_limit=1)

        payload = analysis.collect_analysis(options, opener=fake_opener, timeout=1)

        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["metadata"]["symbol"], "NVDAUSDT")
        self.assertEqual(payload["data"]["premium_index"]["symbol"], "NVDAUSDT")
        self.assertIn("book_ticker", payload["data"])

    def test_summary_formats_zero_plainly(self):
        """Purpose: verify zero decimal values are displayed without exponent notation."""
        payload = {
            "metadata": {"symbol": "NVDAUSDT", "groups": ["valuation"]},
            "dry_run": False,
            "data": {"premium_index": {"markPrice": "1", "indexPrice": "1", "lastFundingRate": "0.00000000"}},
        }

        summary = analysis.format_summary(payload)

        self.assertIn("funding=0", summary)
        self.assertNotIn("0E", summary)

    def test_account_risk_dry_run_redacts_credentials(self):
        """Purpose: verify signed endpoint previews hide API secrets, signatures, and full API keys."""
        credentials = analysis.BinanceCredentials(api_key="ABCDEFGHIJKL", api_secret="VERY_SECRET_VALUE")
        options = analysis.AnalysisOptions(symbol="NVDAUSDT", groups=("account-risk",), dry_run=True)

        payload = analysis.collect_analysis(options, credentials=credentials)
        text = json.dumps(payload)

        self.assertIn("<redacted>", text)
        self.assertNotIn("VERY_SECRET_VALUE", text)
        self.assertNotIn("ABCDEFGHIJKL", text)
        self.assertIn("account_information", text)

    def test_public_dry_run_uses_proxy_and_redacts_key(self):
        """Purpose: verify public endpoint previews show the Caddy URL with a redacted proxy key."""
        options = analysis.AnalysisOptions(symbol="NVDAUSDT", groups=("valuation",), dry_run=True)
        proxy_config = analysis.BinanceProxyConfig(
            enabled=True,
            base_url="https://proxy.example.test",
            auth_key="proxy-secret-1234",
        )

        preview = analysis.request_preview(
            analysis.build_endpoint_specs(options)[0],
            proxy_config=proxy_config,
        )
        text = json.dumps(preview)

        self.assertTrue(preview["url"].startswith("https://proxy.example.test/fapi/fapi/v1/premiumIndex?"))
        self.assertEqual(preview["headers"]["X-Trading-Proxy-Key"], "prox...1234")
        self.assertNotIn("proxy-secret-1234", text)

    def test_load_credentials_reads_first_config(self):
        """Purpose: verify credential loading follows the skill-root before home lookup order."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as home:
            config_dir = Path(root) / ".trading-tools"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "binance": {
                            "api_key": "root_key_123456",
                            "api_secret": "root_secret",
                            "futures": {"market": "um", "testnet": False, "recv_window": 6000},
                        }
                    }
                ),
                encoding="utf-8",
            )

            credentials = analysis.load_credentials(root=Path(root), home=Path(home))

            self.assertEqual(credentials.config_path, config_path)
            self.assertEqual(credentials.api_key, "root_key_123456")
            self.assertEqual(credentials.recv_window, 6000)

    def test_fetch_json_wraps_network_errors(self):
        """Purpose: verify network errors are returned as analysis errors."""
        def failing_opener(request, timeout):
            raise URLError("offline")

        with self.assertRaises(analysis.AnalysisError):
            analysis.fetch_json("https://example.test", opener=failing_opener, timeout=1)


if __name__ == "__main__":
    unittest.main()
