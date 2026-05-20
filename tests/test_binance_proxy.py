import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import binance_proxy  # noqa: E402


class BinanceProxyTests(unittest.TestCase):
    def test_parse_enabled_proxy_config(self):
        """Purpose: verify the shared config parser accepts the Caddy proxy fields."""
        config = binance_proxy.parse_proxy_config(
            {
                "proxy": {
                    "enabled": True,
                    "base_url": "https://proxy.example.test/",
                    "auth_header": "X-Trading-Proxy-Key",
                    "auth_key": "proxy-secret-1234",
                }
            },
            Path("config.json"),
        )

        self.assertTrue(config.enabled)
        self.assertEqual(config.base_url, "https://proxy.example.test")
        self.assertEqual(config.auth_header, "X-Trading-Proxy-Key")
        self.assertEqual(config.auth_key, "proxy-secret-1234")

    def test_missing_enabled_proxy_secret_raises(self):
        """Purpose: verify enabled proxy config requires a request header secret."""
        with self.assertRaises(ValueError) as raised:
            binance_proxy.parse_proxy_config(
                {
                    "proxy": {
                        "enabled": True,
                        "base_url": "https://proxy.example.test",
                    }
                },
                Path("config.json"),
            )

        self.assertIn("auth_key", str(raised.exception))

    def test_resolve_proxy_base_urls(self):
        """Purpose: verify official Binance bases map to the Caddy path prefixes."""
        proxy_config = binance_proxy.BinanceProxyConfig(
            enabled=True,
            base_url="https://proxy.example.test",
            auth_key="proxy-secret-1234",
        )

        self.assertEqual(
            binance_proxy.resolve_proxy_base_url("https://fapi.binance.com", proxy_config),
            "https://proxy.example.test/fapi",
        )
        self.assertEqual(
            binance_proxy.resolve_proxy_base_url("https://dapi.binance.com", proxy_config),
            "https://proxy.example.test/dapi",
        )
        self.assertEqual(
            binance_proxy.resolve_proxy_base_url("https://demo-fapi.binance.com", proxy_config),
            "https://proxy.example.test/demo-fapi",
        )
        self.assertEqual(
            binance_proxy.resolve_proxy_base_url("https://testnet.binancefuture.com", proxy_config),
            "https://proxy.example.test/testnet-future",
        )

    def test_headers_are_added_and_redacted(self):
        """Purpose: verify proxy auth is sent live and redacted in dry-run data."""
        proxy_config = binance_proxy.BinanceProxyConfig(
            enabled=True,
            base_url="https://proxy.example.test",
            auth_key="proxy-secret-1234",
        )

        live_headers = binance_proxy.add_proxy_auth_headers({"X-MBX-APIKEY": "binance-key"}, proxy_config)
        dry_headers = binance_proxy.redacted_proxy_auth_headers(proxy_config)

        self.assertEqual(live_headers["X-Trading-Proxy-Key"], "proxy-secret-1234")
        self.assertEqual(dry_headers["X-Trading-Proxy-Key"], "prox...1234")

    def test_load_optional_proxy_from_first_config_file(self):
        """Purpose: verify public tools can load proxy settings without requiring credentials."""
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "binance": {
                            "futures": {
                                "proxy": {
                                    "enabled": True,
                                    "base_url": "https://proxy.example.test",
                                    "auth_key": "proxy-secret-1234",
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            config = binance_proxy.load_proxy_config_from_candidates([path])

        self.assertTrue(config.enabled)
        self.assertEqual(config.base_url, "https://proxy.example.test")


if __name__ == "__main__":
    unittest.main()
