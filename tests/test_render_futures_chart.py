import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "render_futures_chart.py"
SPEC = importlib.util.spec_from_file_location("render_futures_chart", SCRIPT_PATH)
charts = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = charts
SPEC.loader.exec_module(charts)


SAMPLE_EXCHANGE_INFO = {
    "symbols": [
        {
            "symbol": "NVDAUSDT",
            "status": "TRADING",
            "contractType": "TRADIFI_PERPETUAL",
            "baseAsset": "NVDA",
            "quoteAsset": "USDT",
            "underlyingType": "EQUITY",
        }
    ]
}


SAMPLE_KLINES = [
    [1774562400000, "200.00", "204.00", "198.00", "202.00", "1200.50"],
    [1774566000000, "202.00", "206.00", "201.50", "205.00", "1400.75"],
    [1774569600000, "205.00", "205.50", "199.00", "200.00", "1000.25"],
]


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
    if url.endswith("/fapi/v1/exchangeInfo"):
        return FakeResponse(json.dumps(SAMPLE_EXCHANGE_INFO).encode("utf-8"))
    if "/fapi/v1/klines?" in url:
        return FakeResponse(json.dumps(SAMPLE_KLINES).encode("utf-8"))
    raise AssertionError(f"unexpected url: {url}")


class RenderFuturesChartTests(unittest.TestCase):
    def test_normalize_symbol_uppercases(self):
        """Purpose: verify lowercase user input maps to Binance's uppercase symbol format."""
        self.assertEqual(charts.normalize_symbol(" nvdausdt "), "NVDAUSDT")

    def test_normalize_symbol_rejects_invalid_text(self):
        """Purpose: verify invalid symbol text fails before any network request."""
        with self.assertRaises(charts.ChartError):
            charts.normalize_symbol("NVDA/USDT")

    def test_validate_futures_symbol_accepts_trading_symbol(self):
        """Purpose: verify exchangeInfo validation returns metadata for a tradable symbol."""
        info = charts.validate_futures_symbol(SAMPLE_EXCHANGE_INFO, "NVDAUSDT")

        self.assertEqual(info.symbol, "NVDAUSDT")
        self.assertEqual(info.status, "TRADING")
        self.assertEqual(info.contract_type, "TRADIFI_PERPETUAL")

    def test_validate_futures_symbol_missing_raises_clear_error(self):
        """Purpose: verify missing symbols return a clear validation error."""
        with self.assertRaises(charts.ChartError) as raised:
            charts.validate_futures_symbol(SAMPLE_EXCHANGE_INFO, "BTCUSDT")

        self.assertIn("BTCUSDT", str(raised.exception))
        self.assertIn("not found", str(raised.exception))

    def test_validate_futures_symbol_non_trading_raises_clear_error(self):
        """Purpose: verify non-trading symbols are rejected before chart rendering."""
        exchange_info = {
            "symbols": [
                {
                    "symbol": "NVDAUSDT",
                    "status": "PENDING_TRADING",
                }
            ]
        }

        with self.assertRaises(charts.ChartError) as raised:
            charts.validate_futures_symbol(exchange_info, "NVDAUSDT")

        self.assertIn("PENDING_TRADING", str(raised.exception))

    def test_parse_klines_builds_candles(self):
        """Purpose: verify Binance kline arrays are parsed into candle values."""
        candles = charts.parse_klines(SAMPLE_KLINES)

        self.assertEqual(len(candles), 3)
        self.assertEqual(candles[0].open_time_ms, 1774562400000)
        self.assertEqual(str(candles[0].open), "200.00")
        self.assertEqual(str(candles[-1].close), "200.00")

    def test_parse_klines_empty_raises_clear_error(self):
        """Purpose: verify empty market-data responses fail with a useful message."""
        with self.assertRaises(charts.ChartError) as raised:
            charts.parse_klines([])

        self.assertIn("no klines", str(raised.exception))

    def test_build_url_uses_proxy_prefix(self):
        """Purpose: verify chart market-data URLs can be routed through the Worker proxy."""
        proxy_config = charts.BinanceProxyConfig(
            enabled=True,
            base_url="https://worker.example.test",
            auth_key="proxy-secret-1234",
        )

        url = charts.build_url(charts.KLINES_PATH, [("symbol", "NVDAUSDT")], proxy_config=proxy_config)

        self.assertEqual(url, "https://worker.example.test/fapi/fapi/v1/klines?symbol=NVDAUSDT")

    def test_render_svg_contains_chart_markers(self):
        """Purpose: verify SVG output includes the expected axes, title, and vector root."""
        candles = charts.parse_klines(SAMPLE_KLINES)
        symbol_info = charts.validate_futures_symbol(SAMPLE_EXCHANGE_INFO, "NVDAUSDT")

        svg = charts.render_svg(candles, symbol_info, "1h", "UTC")

        self.assertIn("<svg", svg)
        self.assertIn("NVDAUSDT USD-M Futures", svg)
        self.assertIn("Price (USDT)", svg)
        self.assertIn("Volume", svg)
        self.assertIn("</svg>", svg)

    def test_render_chart_with_fake_opener_writes_svg(self):
        """Purpose: verify the full render path writes an SVG without using live network data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "chart.svg"
            options = charts.ChartOptions(symbol="NVDAUSDT", output=output_path, timezone="UTC")

            result = charts.render_chart(options, opener=fake_opener, timeout=1)

            self.assertEqual(result, output_path)
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("<svg", content)
            self.assertIn("NVDAUSDT", content)

    def test_cli_requires_symbol(self):
        """Purpose: verify the CLI treats symbol as an explicit required input."""
        parser = charts.build_parser()

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args([])

    def test_fetch_json_wraps_network_errors(self):
        """Purpose: verify network errors are reported as chart-generation errors."""
        def failing_opener(request, timeout):
            raise URLError("offline")

        with self.assertRaises(charts.ChartError) as raised:
            charts.fetch_json("https://example.test", opener=failing_opener, timeout=1)

        self.assertIn("request failed", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
