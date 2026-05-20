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


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "list_futures_positions.py"
SPEC = importlib.util.spec_from_file_location("list_futures_positions", SCRIPT_PATH)
positions = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = positions
SPEC.loader.exec_module(positions)


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


class TradingToolsTests(unittest.TestCase):
    def test_current_directory_config_has_priority(self):
        """Purpose: verify the project config takes priority over the home config."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as home:
            root_path = write_config(root, api_key="root_api_key_abcdef")
            write_config(home, api_key="home_api_key_abcdef")

            config = positions.load_config(root=Path(root), home=Path(home))

            self.assertEqual(config.config_path, root_path)
            self.assertEqual(config.api_key, "root_api_key_abcdef")

    def test_home_config_is_used_when_root_config_is_missing(self):
        """Purpose: verify the home config is used as the fallback config source."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as home:
            home_path = write_config(home, api_key="home_api_key_abcdef")

            config = positions.load_config(root=Path(root), home=Path(home))

            self.assertEqual(config.config_path, home_path)
            self.assertEqual(config.api_key, "home_api_key_abcdef")

    def test_missing_config_raises_error_with_candidate_paths(self):
        """Purpose: verify config lookup errors show every checked config path."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as home:
            with self.assertRaises(positions.ConfigError) as raised:
                positions.load_config(root=Path(root), home=Path(home))

            message = str(raised.exception)
            self.assertIn(str(Path(root) / ".trading-tools" / "config.json"), message)
            self.assertIn(str(Path(home) / ".trading-tools" / "config.json"), message)

    def test_missing_required_fields_raise_errors(self):
        """Purpose: verify required config fields are validated with field-specific errors."""
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "config.json"
            cases = [
                ({"binance": {"api_secret": "secret", "futures": {"market": "um"}}}, "api_key"),
                ({"binance": {"api_key": "key", "futures": {"market": "um"}}}, "api_secret"),
                ({"binance": {"api_key": "key", "api_secret": "secret", "futures": {}}}, "market"),
            ]
            for data, field in cases:
                with self.subTest(field=field):
                    with self.assertRaises(positions.ConfigError) as raised:
                        positions.normalize_config(data, path)
                    self.assertIn(field, str(raised.exception))

    def test_invalid_market_raises_error(self):
        """Purpose: verify futures market validation accepts only supported markets."""
        data = {
            "binance": {
                "api_key": "key",
                "api_secret": "secret",
                "futures": {"market": "spot"},
            }
        }
        with self.assertRaises(positions.ConfigError):
            positions.normalize_config(data, Path("config.json"))

    def test_sign_query_is_stable(self):
        """Purpose: verify query signing matches the expected HMAC-SHA256 digest."""
        query = "recvWindow=5000&timestamp=1700000000000"
        expected = hmac.new(b"secret", query.encode("utf-8"), hashlib.sha256).hexdigest()

        self.assertEqual(positions.sign_query(query, "secret"), expected)

    def test_um_signed_request_url(self):
        """Purpose: verify USD-M signed requests use the correct endpoint and query fields."""
        config = positions.BinanceFuturesConfig(
            api_key="api_key_123456",
            api_secret="secret",
            market="um",
            testnet=False,
            recv_window=5000,
            symbol="BTCUSDT",
        )

        request = positions.build_signed_request(config, timestamp_ms=1700000000000)

        self.assertEqual(request.base_url, "https://fapi.binance.com")
        self.assertEqual(request.path, "/fapi/v3/positionRisk")
        self.assertIn("symbol=BTCUSDT", request.query)
        self.assertIn("recvWindow=5000", request.query)
        self.assertIn("timestamp=1700000000000", request.query)
        self.assertIn("signature=", request.url)

    def test_cm_testnet_signed_request_url(self):
        """Purpose: verify COIN-M testnet requests use client-side symbol filtering."""
        config = positions.BinanceFuturesConfig(
            api_key="api_key_123456",
            api_secret="secret",
            market="cm",
            testnet=True,
            recv_window=6000,
            symbol="BTCUSD_PERP",
        )

        request = positions.build_signed_request(config, timestamp_ms=1700000000000)

        self.assertEqual(request.base_url, "https://testnet.binancefuture.com")
        self.assertEqual(request.path, "/dapi/v1/positionRisk")
        self.assertNotIn("symbol=", request.query)
        self.assertIn("recvWindow=6000", request.query)

    def test_proxy_signed_request_url_and_dry_run_redaction(self):
        """Purpose: verify proxy config rewrites the base URL and redacts the proxy key."""
        config = positions.BinanceFuturesConfig(
            api_key="ABCDEFGHIJKL",
            api_secret="VERY_SECRET_VALUE",
            market="um",
            testnet=False,
            recv_window=5000,
            symbol="BTCUSDT",
            proxy_config=positions.BinanceProxyConfig(
                enabled=True,
                base_url="https://worker.example.test",
                auth_key="proxy-secret-1234",
            ),
        )

        request = positions.build_signed_request(config, timestamp_ms=1700000000000)
        payload = positions.dry_run_payload(config, request)
        text = json.dumps(payload)

        self.assertEqual(request.base_url, "https://worker.example.test/fapi")
        self.assertTrue(request.url.startswith("https://worker.example.test/fapi/fapi/v3/positionRisk?"))
        self.assertEqual(request.headers["X-Trading-Proxy-Key"], "proxy-secret-1234")
        self.assertEqual(payload["headers"]["X-Trading-Proxy-Key"], "prox...1234")
        self.assertNotIn("proxy-secret-1234", text)

    def test_overrides_replace_config_values(self):
        """Purpose: verify CLI overrides replace market, symbol, and testnet settings."""
        config = positions.BinanceFuturesConfig(
            api_key="api_key_123456",
            api_secret="secret",
            market="um",
            testnet=False,
            recv_window=5000,
            symbol=None,
        )

        updated = positions.apply_overrides(config, market="cm", symbol="btcusd_perp", testnet=True)

        self.assertEqual(updated.market, "cm")
        self.assertEqual(updated.symbol, "BTCUSD_PERP")
        self.assertTrue(updated.testnet)

    def test_filter_positions_hides_zero_by_default(self):
        """Purpose: verify default position filtering returns only active positions."""
        sample = [
            {"symbol": "BTCUSDT", "positionAmt": "0"},
            {"symbol": "ETHUSDT", "positionAmt": "-0.25"},
            {"symbol": "SOLUSDT", "positionAmt": "3"},
        ]

        filtered = positions.filter_positions(sample)

        self.assertEqual([item["symbol"] for item in filtered], ["ETHUSDT", "SOLUSDT"])

    def test_filter_positions_include_zero(self):
        """Purpose: verify zero-size positions are kept when include_zero is enabled."""
        sample = [
            {"symbol": "BTCUSDT", "positionAmt": "0"},
            {"symbol": "ETHUSDT", "positionAmt": "1"},
        ]

        filtered = positions.filter_positions(sample, include_zero=True)

        self.assertEqual(len(filtered), 2)

    def test_filter_positions_by_symbol(self):
        """Purpose: verify symbol filtering is case-insensitive and exact."""
        sample = [
            {"symbol": "BTCUSD_PERP", "positionAmt": "1"},
            {"symbol": "ETHUSD_PERP", "positionAmt": "1"},
        ]

        filtered = positions.filter_positions(sample, symbol="btcusd_perp")

        self.assertEqual(filtered, [{"symbol": "BTCUSD_PERP", "positionAmt": "1"}])

    def test_format_positions_table_handles_missing_fields(self):
        """Purpose: verify table rendering fills absent position fields with placeholders."""
        table = positions.format_positions_table(
            [{"symbol": "BTCUSDT", "positionSide": "LONG", "positionAmt": "1"}]
        )

        self.assertIn("symbol", table)
        self.assertIn("BTCUSDT", table)
        self.assertIn("-", table)

    def test_render_json_returns_raw_positions(self):
        """Purpose: verify JSON output returns the raw positions payload unchanged."""
        sample = [
            {"symbol": "BTCUSDT", "positionAmt": "0"},
            {"symbol": "ETHUSDT", "positionAmt": "1"},
        ]

        rendered = positions.render_positions(sample, json_output=True)

        data = json.loads(rendered)
        self.assertEqual(data, sample)

    def test_dry_run_redacts_secrets(self):
        """Purpose: verify dry-run output hides API keys, secrets, and signatures."""
        config = positions.BinanceFuturesConfig(
            api_key="ABCDEFGHIJKL",
            api_secret="VERY_SECRET_VALUE",
            market="um",
            testnet=False,
            recv_window=5000,
            symbol="BTCUSDT",
            config_path=Path("config.json"),
        )
        request = positions.build_signed_request(config, timestamp_ms=1700000000000)

        payload = positions.dry_run_payload(config, request)
        text = json.dumps(payload)

        self.assertNotIn("ABCDEFGHIJKL", text)
        self.assertNotIn("VERY_SECRET_VALUE", text)
        self.assertNotIn(request.signature, text)
        self.assertIn("<redacted>", text)

    def test_fetch_json_uses_fake_opener(self):
        """Purpose: verify HTTP fetching passes signed request details to the opener."""
        captured = {}

        def fake_opener(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["api_key"] = request.get_header("X-mbx-apikey")
            return FakeResponse(b'[{"symbol":"BTCUSDT","positionAmt":"1"}]')

        signed = positions.SignedRequest(
            method="GET",
            base_url="https://fapi.binance.com",
            path="/fapi/v3/positionRisk",
            query="recvWindow=5000&timestamp=1",
            signature="sig",
            url="https://fapi.binance.com/fapi/v3/positionRisk?recvWindow=5000&timestamp=1&signature=sig",
            headers={"X-MBX-APIKEY": "api_key"},
        )

        data = positions.fetch_json(signed, opener=fake_opener, timeout=3)

        self.assertEqual(data, [{"symbol": "BTCUSDT", "positionAmt": "1"}])
        self.assertEqual(captured["timeout"], 3)
        self.assertEqual(captured["api_key"], "api_key")

    def test_main_missing_config_returns_nonzero(self):
        """Purpose: verify the CLI exits with an error code when config loading fails."""
        with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_home:
            stderr = io.StringIO()
            original_home = positions.Path.home
            original_skill_root = positions.skill_root
            try:
                positions.skill_root = lambda: Path(tmp_root)
                positions.Path.home = staticmethod(lambda: Path(tmp_home))
                with contextlib.redirect_stderr(stderr):
                    exit_code = positions.main(["--dry-run"], stdout=io.StringIO(), stderr=stderr)
            finally:
                positions.skill_root = original_skill_root
                positions.Path.home = original_home

        self.assertEqual(exit_code, 1)
        self.assertIn("config file", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
