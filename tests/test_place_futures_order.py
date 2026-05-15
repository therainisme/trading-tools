import importlib.util
import json
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT_PATH = SCRIPT_DIR / "place_futures_order.py"
SPEC = importlib.util.spec_from_file_location("place_futures_order", SCRIPT_PATH)
place = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = place
SPEC.loader.exec_module(place)

from futures_trade_utils import BinanceFuturesConfig, TradeValidationError  # noqa: E402


class PlaceFuturesOrderTests(unittest.TestCase):
    def test_limit_reduce_only_params(self):
        """Purpose: verify reduce-only LIMIT orders include price and GTC."""
        options = place.StandardOrderOptions(
            symbol="nvdausdt",
            side="SELL",
            order_type="LIMIT",
            quantity="0.25",
            price="236.80",
            reduce_only=True,
        )

        params = place.build_order_params(options)

        self.assertIn(("symbol", "NVDAUSDT"), params)
        self.assertIn(("side", "SELL"), params)
        self.assertIn(("type", "LIMIT"), params)
        self.assertIn(("quantity", "0.25"), params)
        self.assertIn(("price", "236.8"), params)
        self.assertIn(("timeInForce", "GTC"), params)
        self.assertIn(("reduceOnly", "true"), params)

    def test_market_rejects_price(self):
        """Purpose: verify MARKET orders cannot accidentally carry a limit price."""
        options = place.StandardOrderOptions(
            symbol="NVDAUSDT",
            side="SELL",
            order_type="MARKET",
            quantity="0.25",
            price="236.8",
        )

        with self.assertRaises(TradeValidationError):
            place.build_order_params(options)

    def test_symbol_whitelist_rejects_unlisted_symbol(self):
        """Purpose: verify live-capable trading scripts enforce the local symbol whitelist."""
        options = place.StandardOrderOptions(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity="0.001",
        )

        with self.assertRaises(TradeValidationError):
            place.build_order_params(options)

    def test_dry_run_payload_redacts_secret_material(self):
        """Purpose: verify dry-run output contains a plan hash and redacts credentials."""
        config = BinanceFuturesConfig(api_key="ABCDEFGHIJKL", api_secret="VERY_SECRET", market="um")
        options = place.StandardOrderOptions(
            symbol="NVDAUSDT",
            side="SELL",
            order_type="LIMIT",
            quantity="0.25",
            price="236.8",
            reduce_only=True,
        )

        payload = place.execute_order(config, options)
        text = json.dumps(payload)

        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["path"], "/fapi/v1/order")
        self.assertIn("plan_hash", payload)
        self.assertNotIn("ABCDEFGHIJKL", text)
        self.assertNotIn("VERY_SECRET", text)
        self.assertIn("<redacted>", text)

    def test_live_mode_requires_matching_hash(self):
        """Purpose: verify live orders require the dry-run plan hash confirmation."""
        config = BinanceFuturesConfig(api_key="api_key_123456", api_secret="secret", market="um")
        options = place.StandardOrderOptions(
            symbol="NVDAUSDT",
            side="SELL",
            order_type="LIMIT",
            quantity="0.25",
            price="236.8",
            reduce_only=True,
            mode="live",
            confirm="LIVE",
            confirm_plan_hash="wrong",
        )

        with self.assertRaises(TradeValidationError):
            place.execute_order(config, options)


if __name__ == "__main__":
    unittest.main()
