import contextlib
import hmac
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "list_futures_orders.py"
SPEC = importlib.util.spec_from_file_location("list_futures_orders", SCRIPT_PATH)
orders = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = orders
SPEC.loader.exec_module(orders)


def write_config(base, api_key="root_key_123456", api_secret="root_secret", market="um", **futures):
    config_dir = Path(base) / ".trading-tools"
    config_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "binance": {
            "api_key": api_key,
            "api_secret": api_secret,
            "futures": {
                "market": market,
                "testnet": futures.pop("testnet", False),
                "recv_window": futures.pop("recv_window", 5000),
                "symbol": futures.pop("symbol", None),
            },
        }
    }
    data["binance"]["futures"].update(futures)
    path = config_dir / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class ListFuturesOrdersTests(unittest.TestCase):
    def test_load_config_uses_root_before_home(self):
        """Purpose: verify order listing uses the same config lookup order as other tools."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as home:
            root_path = write_config(root, api_key="root_api_key_abcdef")
            write_config(home, api_key="home_api_key_abcdef")

            config = orders.load_config(root=Path(root), home=Path(home))

            self.assertEqual(config.config_path, root_path)
            self.assertEqual(config.api_key, "root_api_key_abcdef")

    def test_um_open_orders_signed_request_uses_symbol(self):
        """Purpose: verify USD-M open order requests use the configured symbol and endpoint."""
        config = orders.BinanceFuturesConfig(api_key="api_key_123456", api_secret="secret", market="um", symbol="NVDAUSDT")
        options = orders.OrderRequestOptions(kind="open")

        request = orders.build_signed_request(config, options, timestamp_ms=1700000000000)

        self.assertEqual(request.base_url, "https://fapi.binance.com")
        self.assertEqual(request.path, "/fapi/v1/openOrders")
        self.assertIn("symbol=NVDAUSDT", request.query)
        self.assertIn("recvWindow=5000", request.query)
        self.assertIn("timestamp=1700000000000", request.query)
        self.assertIn("signature=", request.url)

    def test_history_requires_symbol(self):
        """Purpose: verify history and trade queries require an explicit or configured symbol."""
        config = orders.BinanceFuturesConfig(api_key="api_key_123456", api_secret="secret", market="um")
        options = orders.OrderRequestOptions(kind="history")

        with self.assertRaises(orders.ConfigError):
            orders.build_order_params(config, options, timestamp_ms=1700000000000)

    def test_cm_open_orders_require_symbol_pair_or_all_symbols(self):
        """Purpose: verify COIN-M open order queries avoid accidental broad requests by default."""
        config = orders.BinanceFuturesConfig(api_key="api_key_123456", api_secret="secret", market="cm")
        options = orders.OrderRequestOptions(kind="open")

        with self.assertRaises(orders.ConfigError):
            orders.build_order_params(config, options, timestamp_ms=1700000000000)

    def test_cm_open_orders_accept_pair(self):
        """Purpose: verify COIN-M open order requests can use the official pair filter."""
        config = orders.BinanceFuturesConfig(api_key="api_key_123456", api_secret="secret", market="cm")
        options = orders.OrderRequestOptions(kind="open", pair="btcusd")

        params = orders.build_order_params(config, options, timestamp_ms=1700000000000)

        self.assertIn(("pair", "BTCUSD"), params)

    def test_all_orders_request_includes_history_parameters(self):
        """Purpose: verify order-history requests include supported filters."""
        config = orders.BinanceFuturesConfig(api_key="api_key_123456", api_secret="secret", market="um", symbol="NVDAUSDT")
        options = orders.OrderRequestOptions(kind="history", order_id=123, start_time=1, end_time=2, limit=50)

        params = orders.build_order_params(config, options, timestamp_ms=1700000000000)

        self.assertIn(("symbol", "NVDAUSDT"), params)
        self.assertIn(("orderId", "123"), params)
        self.assertIn(("startTime", "1"), params)
        self.assertIn(("endTime", "2"), params)
        self.assertIn(("limit", "50"), params)

    def test_conditional_open_orders_signed_request_uses_algo_endpoint(self):
        """Purpose: verify USD-M conditional open order requests use the algo endpoint and filters."""
        config = orders.BinanceFuturesConfig(api_key="api_key_123456", api_secret="secret", market="um", symbol="NVDAUSDT")
        options = orders.OrderRequestOptions(kind="conditional-open", algo_type="conditional", algo_id=77)

        request = orders.build_signed_request(config, options, timestamp_ms=1700000000000)

        self.assertEqual(request.path, "/fapi/v1/openAlgoOrders")
        self.assertIn("symbol=NVDAUSDT", request.query)
        self.assertIn("algoType=CONDITIONAL", request.query)
        self.assertIn("algoId=77", request.query)
        self.assertNotIn("limit=", request.query)

    def test_conditional_open_requires_symbol_or_all_symbols(self):
        """Purpose: verify broad conditional open order requests require an explicit flag."""
        config = orders.BinanceFuturesConfig(api_key="api_key_123456", api_secret="secret", market="um")

        with self.assertRaises(orders.ConfigError):
            orders.build_order_params(
                config,
                orders.OrderRequestOptions(kind="conditional-open"),
                timestamp_ms=1700000000000,
            )

        params = orders.build_order_params(
            config,
            orders.OrderRequestOptions(kind="conditional-open", include_empty_symbol=True),
            timestamp_ms=1700000000000,
        )
        self.assertNotIn(("symbol", "NVDAUSDT"), params)

    def test_conditional_history_request_includes_history_parameters(self):
        """Purpose: verify USD-M conditional order history requests use the all algo endpoint and filters."""
        config = orders.BinanceFuturesConfig(api_key="api_key_123456", api_secret="secret", market="um", symbol="NVDAUSDT")
        options = orders.OrderRequestOptions(kind="conditional-history", algo_id=123, start_time=1, end_time=2, limit=50)

        request = orders.build_signed_request(config, options, timestamp_ms=1700000000000)

        self.assertEqual(request.path, "/fapi/v1/allAlgoOrders")
        self.assertIn("symbol=NVDAUSDT", request.query)
        self.assertIn("algoId=123", request.query)
        self.assertIn("startTime=1", request.query)
        self.assertIn("endTime=2", request.query)
        self.assertIn("limit=50", request.query)

    def test_conditional_orders_support_usd_m_market(self):
        """Purpose: verify conditional order queries report a clear error for unsupported market selection."""
        config = orders.BinanceFuturesConfig(api_key="api_key_123456", api_secret="secret", market="cm", symbol="BTCUSD_PERP")
        options = orders.OrderRequestOptions(kind="conditional-open")

        with self.assertRaises(orders.ConfigError):
            orders.build_signed_request(config, options, timestamp_ms=1700000000000)

    def test_sign_query_is_stable(self):
        """Purpose: verify HMAC-SHA256 signing is stable."""
        query = "symbol=NVDAUSDT&recvWindow=5000&timestamp=1700000000000"
        expected = hmac.new(b"secret", query.encode("utf-8"), hashlib.sha256).hexdigest()

        self.assertEqual(orders.sign_query(query, "secret"), expected)

    def test_dry_run_redacts_secrets(self):
        """Purpose: verify dry-run output hides API keys, secrets, and signatures."""
        config = orders.BinanceFuturesConfig(api_key="ABCDEFGHIJKL", api_secret="VERY_SECRET_VALUE", market="um", symbol="NVDAUSDT")
        options = orders.OrderRequestOptions(kind="open")
        request = orders.build_signed_request(config, options, timestamp_ms=1700000000000)

        payload = orders.dry_run_payload(config, options, request)
        text = json.dumps(payload)

        self.assertNotIn("ABCDEFGHIJKL", text)
        self.assertNotIn("VERY_SECRET_VALUE", text)
        self.assertNotIn(request.signature, text)
        self.assertIn("<redacted>", text)

    def test_fetch_json_uses_fake_opener(self):
        """Purpose: verify fetching passes signed request details to urllib."""
        captured = {}

        def fake_opener(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["api_key"] = request.get_header("X-mbx-apikey")
            return FakeResponse(b'[{"symbol":"NVDAUSDT","orderId":1}]')

        signed = orders.SignedRequest(
            method="GET",
            base_url="https://fapi.binance.com",
            path="/fapi/v1/openOrders",
            query="symbol=NVDAUSDT&recvWindow=5000&timestamp=1",
            signature="sig",
            url="https://fapi.binance.com/fapi/v1/openOrders?symbol=NVDAUSDT&recvWindow=5000&timestamp=1&signature=sig",
            headers={"X-MBX-APIKEY": "api_key"},
        )

        data = orders.fetch_json(signed, opener=fake_opener, timeout=3)

        self.assertEqual(data, [{"symbol": "NVDAUSDT", "orderId": 1}])
        self.assertEqual(captured["timeout"], 3)
        self.assertEqual(captured["api_key"], "api_key")

    def test_format_table_handles_missing_fields(self):
        """Purpose: verify table rendering fills absent order fields with placeholders."""
        table = orders.format_table([{"symbol": "NVDAUSDT", "orderId": 1}], "open")

        self.assertIn("NVDAUSDT", table)
        self.assertIn("-", table)

    def test_conditional_table_handles_algo_fields(self):
        """Purpose: verify table rendering includes conditional order identifiers."""
        table = orders.format_table([{"symbol": "NVDAUSDT", "algoId": 99, "algoStatus": "NEW"}], "conditional-open")

        self.assertIn("algoId", table)
        self.assertIn("99", table)
        self.assertIn("NEW", table)

    def test_main_missing_config_returns_nonzero(self):
        """Purpose: verify CLI exits with an error when config loading fails."""
        with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_home:
            stderr = io.StringIO()
            original_home = orders.Path.home
            original_skill_root = orders.skill_root
            try:
                orders.skill_root = lambda: Path(tmp_root)
                orders.Path.home = staticmethod(lambda: Path(tmp_home))
                with contextlib.redirect_stderr(stderr):
                    exit_code = orders.main(["--dry-run"], stdout=io.StringIO(), stderr=stderr)
            finally:
                orders.skill_root = original_skill_root
                orders.Path.home = original_home

        self.assertEqual(exit_code, 1)
        self.assertIn("config file", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
