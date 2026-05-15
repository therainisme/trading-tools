import importlib.util
import json
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT_PATH = SCRIPT_DIR / "place_futures_algo_order.py"
SPEC = importlib.util.spec_from_file_location("place_futures_algo_order", SCRIPT_PATH)
algo = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = algo
SPEC.loader.exec_module(algo)

from futures_trade_utils import BinanceFuturesConfig, TradeValidationError  # noqa: E402


class PlaceFuturesAlgoOrderTests(unittest.TestCase):
    def test_stop_market_reduce_only_defaults_to_mark_price(self):
        """Purpose: verify protective stop-market orders use reduce-only and MARK_PRICE by default."""
        options = algo.AlgoOrderOptions(
            symbol="NVDAUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            quantity="0.5",
            trigger_price="227.6",
            reduce_only=True,
        )

        params = algo.build_algo_order_params(options)

        self.assertIn(("algoType", "CONDITIONAL"), params)
        self.assertIn(("type", "STOP_MARKET"), params)
        self.assertIn(("workingType", "MARK_PRICE"), params)
        self.assertIn(("priceProtect", "true"), params)
        self.assertIn(("quantity", "0.5"), params)
        self.assertIn(("reduceOnly", "true"), params)
        self.assertIn(("triggerPrice", "227.6"), params)

    def test_close_position_omits_quantity_and_reduce_only(self):
        """Purpose: verify close-position stop orders are encoded without quantity and reduceOnly."""
        options = algo.AlgoOrderOptions(
            symbol="NVDAUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            trigger_price="227.6",
            close_position=True,
        )

        params = algo.build_algo_order_params(options)

        self.assertIn(("closePosition", "true"), params)
        self.assertNotIn("quantity", [key for key, _ in params])
        self.assertNotIn("reduceOnly", [key for key, _ in params])

    def test_opening_algo_order_requires_explicit_allow_flag(self):
        """Purpose: verify add-position conditional orders require an explicit override flag."""
        options = algo.AlgoOrderOptions(
            symbol="NVDAUSDT",
            side="BUY",
            order_type="STOP",
            quantity="0.25",
            trigger_price="234.9",
            price="234.9",
        )

        with self.assertRaises(TradeValidationError):
            algo.build_algo_order_params(options)

    def test_opening_algo_order_with_allow_flag(self):
        """Purpose: verify explicit add-position conditional orders include trigger and limit prices."""
        options = algo.AlgoOrderOptions(
            symbol="NVDAUSDT",
            side="BUY",
            order_type="STOP",
            quantity="0.25",
            trigger_price="234.9",
            price="234.9",
            allow_open_position=True,
        )

        params = algo.build_algo_order_params(options)

        self.assertIn(("side", "BUY"), params)
        self.assertIn(("type", "STOP"), params)
        self.assertIn(("triggerPrice", "234.9"), params)
        self.assertIn(("price", "234.9"), params)
        self.assertNotIn(("reduceOnly", "true"), params)

    def test_dry_run_uses_algo_endpoint_and_redacts(self):
        """Purpose: verify dry-run output uses the algo endpoint and redacts credentials."""
        config = BinanceFuturesConfig(api_key="ABCDEFGHIJKL", api_secret="VERY_SECRET", market="um")
        options = algo.AlgoOrderOptions(
            symbol="NVDAUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            quantity="0.25",
            trigger_price="236.8",
            reduce_only=True,
        )

        payload = algo.execute_algo_order(config, options)
        text = json.dumps(payload)

        self.assertEqual(payload["path"], "/fapi/v1/algoOrder")
        self.assertIn("plan_hash", payload)
        self.assertNotIn("ABCDEFGHIJKL", text)
        self.assertNotIn("VERY_SECRET", text)


if __name__ == "__main__":
    unittest.main()
