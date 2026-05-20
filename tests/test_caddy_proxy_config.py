import unittest
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / "deploy" / "caddy" / "Caddyfile"


class CaddyProxyConfigTests(unittest.TestCase):
    def test_caddyfile_contains_expected_proxy_routes(self):
        """Purpose: verify the deploy config keeps the same Binance proxy route mapping as the Python tools."""
        text = CONFIG_PATH.read_text(encoding="utf-8")

        self.assertIn("bnp.therainisme.com", text)
        self.assertIn("header X-Trading-Proxy-Key {$TRADING_PROXY_KEY:__TRADING_PROXY_KEY_NOT_SET__}", text)
        self.assertIn("path /fapi /fapi/*", text)
        self.assertIn("reverse_proxy https://fapi.binance.com", text)
        self.assertIn("path /dapi /dapi/*", text)
        self.assertIn("reverse_proxy https://dapi.binance.com", text)
        self.assertIn("path /demo-fapi /demo-fapi/*", text)
        self.assertIn("reverse_proxy https://demo-fapi.binance.com", text)
        self.assertIn("path /testnet-future /testnet-future/*", text)
        self.assertIn("reverse_proxy https://testnet.binancefuture.com", text)
        self.assertIn("respond 404", text)


if __name__ == "__main__":
    unittest.main()
