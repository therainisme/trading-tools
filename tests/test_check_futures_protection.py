import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT_PATH = SCRIPT_DIR / "check_futures_protection.py"
SPEC = importlib.util.spec_from_file_location("check_futures_protection", SCRIPT_PATH)
check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check
SPEC.loader.exec_module(check)


class CheckFuturesProtectionTests(unittest.TestCase):
    def test_position_with_full_stop_and_tp_is_ok(self):
        """Purpose: verify full protective stop and take-profit coverage passes."""
        position = {"symbol": "NVDAUSDT", "positionAmt": "0.50", "positionSide": "BOTH", "markPrice": "231"}
        conditional = [
            {"symbol": "NVDAUSDT", "algoId": 1, "algoStatus": "NEW", "orderType": "STOP_MARKET", "side": "SELL", "quantity": "0.5", "reduceOnly": True, "workingType": "MARK_PRICE"},
            {"symbol": "NVDAUSDT", "algoId": 2, "algoStatus": "NEW", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "quantity": "0.25", "reduceOnly": True, "workingType": "MARK_PRICE"},
            {"symbol": "NVDAUSDT", "algoId": 3, "algoStatus": "NEW", "orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "quantity": "0.25", "reduceOnly": True, "workingType": "MARK_PRICE"},
        ]

        result = check.analyze_position(position, [], conditional)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["stopCoverageQty"], "0.5")
        self.assertEqual(result["takeProfitCoverageQty"], "0.50")
        self.assertEqual(result["issues"], [])

    def test_missing_stop_is_issue(self):
        """Purpose: verify missing stop coverage is reported as an issue."""
        position = {"symbol": "TSMUSDT", "positionAmt": "0.20", "positionSide": "BOTH", "markPrice": "408"}

        result = check.analyze_position(position, [], [])

        self.assertEqual(result["status"], "needs-attention")
        self.assertIn("stop coverage 0/0.20", result["issues"])

    def test_oversized_protective_order_is_issue(self):
        """Purpose: verify reduce-only quantities larger than the current position are flagged."""
        position = {"symbol": "MUUSDT", "positionAmt": "0.05", "positionSide": "BOTH", "markPrice": "757"}
        conditional = [
            {"symbol": "MUUSDT", "algoId": 9, "algoStatus": "NEW", "orderType": "STOP_MARKET", "side": "SELL", "quantity": "0.10", "reduceOnly": True, "workingType": "MARK_PRICE"},
        ]

        result = check.analyze_position(position, [], conditional)

        self.assertEqual(result["status"], "needs-attention")
        self.assertTrue(any("oversized protective order" in issue for issue in result["issues"]))

    def test_contract_price_warning(self):
        """Purpose: verify non-preferred workingType is reported as a warning."""
        position = {"symbol": "NVDAUSDT", "positionAmt": "0.50", "positionSide": "BOTH", "markPrice": "231"}
        conditional = [
            {"symbol": "NVDAUSDT", "algoId": 1, "algoStatus": "NEW", "orderType": "STOP_MARKET", "side": "SELL", "quantity": "0.5", "reduceOnly": True, "workingType": "CONTRACT_PRICE"},
        ]

        result = check.analyze_position(position, [], conditional)

        self.assertTrue(any("workingType differs" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
