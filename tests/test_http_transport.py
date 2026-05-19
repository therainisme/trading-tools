import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import futures_trade_utils as trade_utils  # noqa: E402
import http_transport  # noqa: E402


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class HttpTransportTests(unittest.TestCase):
    def test_proxy_maps_to_http_and_https(self):
        """Purpose: verify the project-level PROXY variable applies to both request schemes."""
        proxies = http_transport.resolve_proxy_map({"PROXY": "http://127.0.0.1:7890"})

        self.assertEqual(
            proxies,
            {
                "http": "http://127.0.0.1:7890",
                "https": "http://127.0.0.1:7890",
            },
        )

    def test_standard_scheme_proxies_override_proxy(self):
        """Purpose: verify HTTP_PROXY and HTTPS_PROXY take precedence over generic PROXY."""
        proxies = http_transport.resolve_proxy_map(
            {
                "PROXY": "http://127.0.0.1:7890",
                "HTTP_PROXY": "http://127.0.0.1:8080",
                "HTTPS_PROXY": "https://proxy.example.test:8443",
            }
        )

        self.assertEqual(proxies["http"], "http://127.0.0.1:8080")
        self.assertEqual(proxies["https"], "https://proxy.example.test:8443")

    def test_all_proxy_is_fallback_before_proxy(self):
        """Purpose: verify ALL_PROXY is preferred over PROXY when scheme-specific variables are absent."""
        proxies = http_transport.resolve_proxy_map(
            {
                "PROXY": "http://127.0.0.1:7890",
                "ALL_PROXY": "http://127.0.0.1:8899",
            }
        )

        self.assertEqual(proxies["http"], "http://127.0.0.1:8899")
        self.assertEqual(proxies["https"], "http://127.0.0.1:8899")

    def test_lowercase_proxy_variables_are_supported(self):
        """Purpose: verify lowercase proxy environment names are accepted."""
        proxies = http_transport.resolve_proxy_map({"proxy": "https://proxy.example.test:8443"})

        self.assertEqual(proxies["http"], "https://proxy.example.test:8443")
        self.assertEqual(proxies["https"], "https://proxy.example.test:8443")

    def test_blank_proxy_values_are_ignored(self):
        """Purpose: verify empty proxy variables do not configure urllib proxies."""
        proxies = http_transport.resolve_proxy_map({"PROXY": " ", "HTTPS_PROXY": "\t"})

        self.assertEqual(proxies, {})

    def test_unsupported_proxy_scheme_raises_without_credentials(self):
        """Purpose: verify SOCKS proxy URLs fail clearly without leaking credentials."""
        with self.assertRaises(http_transport.ProxyConfigError) as raised:
            http_transport.resolve_proxy_map({"PROXY": "socks5://user:secret@127.0.0.1:1080"})

        message = str(raised.exception)
        self.assertIn("http(s) proxy URL", message)
        self.assertIn("socks5", message)
        self.assertNotIn("user", message)
        self.assertNotIn("secret", message)
        self.assertIn("<credentials>", message)

    def test_malformed_proxy_url_redacts_credentials(self):
        """Purpose: verify invalid proxy URLs still avoid printing embedded credentials."""
        with self.assertRaises(http_transport.ProxyConfigError) as raised:
            http_transport.resolve_proxy_map({"PROXY": "user:secret@127.0.0.1:7890"})

        message = str(raised.exception)
        self.assertNotIn("user", message)
        self.assertNotIn("secret", message)
        self.assertIn("<credentials>", message)

    def test_trade_fetch_json_uses_default_shared_opener(self):
        """Purpose: verify fetch paths use the shared opener when no fake opener is supplied."""
        captured = {}

        def fake_default_opener(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["api_key"] = request.get_header("X-mbx-apikey")
            return FakeResponse(b'{"ok": true}')

        original_opener = trade_utils.urlopen_with_env_proxy
        trade_utils.urlopen_with_env_proxy = fake_default_opener
        try:
            signed = trade_utils.SignedRequest(
                method="GET",
                base_url="https://fapi.binance.com",
                path="/fapi/v3/account",
                query="recvWindow=5000&timestamp=1",
                signature="sig",
                url="https://fapi.binance.com/fapi/v3/account?recvWindow=5000&timestamp=1&signature=sig",
                headers={"X-MBX-APIKEY": "api_key"},
            )

            data = trade_utils.fetch_json(signed, timeout=7)
        finally:
            trade_utils.urlopen_with_env_proxy = original_opener

        self.assertEqual(data, {"ok": True})
        self.assertEqual(captured["timeout"], 7)
        self.assertEqual(captured["api_key"], "api_key")


if __name__ == "__main__":
    unittest.main()
