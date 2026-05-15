import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT_PATH = SCRIPT_DIR / "cancel_futures_order.py"
SPEC = importlib.util.spec_from_file_location("cancel_futures_order", SCRIPT_PATH)
cancel = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cancel
SPEC.loader.exec_module(cancel)

from futures_trade_utils import BinanceFuturesConfig, TradeValidationError  # noqa: E402


class CancelFuturesOrderTests(unittest.TestCase):
    def test_standard_cancel_requires_symbol_and_order_identifier(self):
        """Purpose: verify standard cancellation requires a symbol and order id."""
        with self.assertRaises(TradeValidationError):
            cancel.build_cancel_params(cancel.CancelOrderOptions(kind="standard", symbol="NVDAUSDT"))

        params = cancel.build_cancel_params(cancel.CancelOrderOptions(kind="standard", symbol="NVDAUSDT", order_id=123))

        self.assertEqual(params, [("symbol", "NVDAUSDT"), ("orderId", "123")])

    def test_algo_cancel_accepts_algo_id(self):
        """Purpose: verify conditional cancellation can target a Binance algoId."""
        params = cancel.build_cancel_params(cancel.CancelOrderOptions(kind="algo", algo_id=3000001))

        self.assertEqual(params, [("algoType", "CONDITIONAL"), ("algoId", "3000001")])

    def test_algo_cancel_rejects_standard_order_id(self):
        """Purpose: verify standard and algo identifiers are not mixed."""
        with self.assertRaises(TradeValidationError):
            cancel.build_cancel_params(cancel.CancelOrderOptions(kind="algo", order_id=123, algo_id=456))

    def test_dry_run_standard_uses_delete_order_endpoint(self):
        """Purpose: verify standard cancellation dry-run uses DELETE /fapi/v1/order."""
        config = BinanceFuturesConfig(api_key="api_key_123456", api_secret="secret", market="um")
        payload = cancel.execute_cancel(
            config,
            cancel.CancelOrderOptions(kind="standard", symbol="NVDAUSDT", order_id=123),
        )

        self.assertEqual(payload["method"], "DELETE")
        self.assertEqual(payload["path"], "/fapi/v1/order")
        self.assertIn("plan_hash", payload)

    def test_live_cancel_requires_hash(self):
        """Purpose: verify live cancellation requires matching dry-run hash confirmation."""
        config = BinanceFuturesConfig(api_key="api_key_123456", api_secret="secret", market="um")
        options = cancel.CancelOrderOptions(kind="algo", algo_id=123, mode="live", confirm="LIVE", confirm_plan_hash="wrong")

        with self.assertRaises(TradeValidationError):
            cancel.execute_cancel(config, options)


if __name__ == "__main__":
    unittest.main()
