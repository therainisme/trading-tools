# trading-tools config.json reference

## Location

The tools read the first existing JSON file from:

1. `<skill-root>/.trading-tools/config.json`
2. `~/.trading-tools/config.json`

In this repo, `<skill-root>` is `/home/vivy/trading-tools`, so the project-local path is:

```text
/home/vivy/trading-tools/.trading-tools/config.json
```

The project-local config file is ignored by git. Put real API keys and proxy keys there.

## Recommended config for the current setup

Use this shape for the current Caddy proxy at `bnp.therainisme.com`:

```json
{
  "binance": {
    "api_key": "your-binance-api-key",
    "api_secret": "your-binance-api-secret",
    "futures": {
      "market": "um",
      "testnet": false,
      "recv_window": 5000,
      "symbol": null,
      "proxy": {
        "enabled": true,
        "base_url": "https://bnp.therainisme.com",
        "auth_header": "X-Trading-Proxy-Key",
        "auth_key": "your-proxy-key"
      }
    }
  }
}
```

`auth_key` must match the `TRADING_PROXY_KEY` environment variable configured on the Caddy VPS. The tools redact this value in dry-run output.

## Minimal direct-Binance config

Use this shape when calling Binance directly:

```json
{
  "binance": {
    "api_key": "your-binance-api-key",
    "api_secret": "your-binance-api-secret",
    "futures": {
      "market": "um",
      "testnet": false,
      "recv_window": 5000,
      "symbol": null
    }
  }
}
```

## Field reference

| Field | Required | Values | Default | Meaning |
| --- | --- | --- | --- | --- |
| `binance` | Yes | JSON object | None | Parent object for Binance credentials and futures settings. |
| `binance.api_key` | Yes | Non-empty string | None | Binance API key sent as `X-MBX-APIKEY` on signed requests. |
| `binance.api_secret` | Yes | Non-empty string | None | Secret used to HMAC-SHA256 sign Binance query strings. |
| `binance.futures` | Yes | JSON object | None | Parent object for futures settings. |
| `binance.futures.market` | Yes for positions/orders/trading | `um`, `cm` | None | `um` means USD-M futures. `cm` means COIN-M futures. Trading execution scripts currently use `um`. |
| `binance.futures.testnet` | No | `true`, `false` | `false` | Routes signed requests to the matching futures testnet when supported. |
| `binance.futures.recv_window` | No | Positive integer milliseconds | `5000` | Binance signed request validity window. |
| `binance.futures.symbol` | No | String or `null` | `null` | Optional default symbol. Strings are trimmed and uppercased by the tools. |
| `binance.futures.proxy` | No | JSON object | Disabled | Optional endpoint proxy settings. |
| `binance.futures.proxy.enabled` | Yes when `proxy` exists | `true`, `false` | `false` | Enables route rewriting through `base_url`. |
| `binance.futures.proxy.base_url` | Yes when enabled | `http(s)` URL without query or fragment | None | Proxy origin, such as `https://bnp.therainisme.com`. |
| `binance.futures.proxy.auth_header` | No | HTTP header name | `X-Trading-Proxy-Key` | Header name used to pass the proxy key. |
| `binance.futures.proxy.auth_key` | Yes when enabled | Non-empty string | None | Client-side proxy key. Must match the Caddy `TRADING_PROXY_KEY`. |

## Proxy route mapping

When `binance.futures.proxy.enabled` is `true`, the tools keep each Binance API path unchanged and only replace the base URL:

| Official base URL | Proxied base URL |
| --- | --- |
| `https://fapi.binance.com` | `https://bnp.therainisme.com/fapi` |
| `https://dapi.binance.com` | `https://bnp.therainisme.com/dapi` |
| `https://demo-fapi.binance.com` | `https://bnp.therainisme.com/demo-fapi` |
| `https://testnet.binancefuture.com` | `https://bnp.therainisme.com/testnet-future` |

Example: official `https://fapi.binance.com/fapi/v3/positionRisk?...` becomes `https://bnp.therainisme.com/fapi/fapi/v3/positionRisk?...`.

## Verify config without sending a signed request

```bash
python /home/vivy/trading-tools/scripts/list_futures_positions.py --dry-run --json
```

Expected proxy-enabled fields:

```json
{
  "base_url": "https://bnp.therainisme.com/fapi",
  "url": "https://bnp.therainisme.com/fapi/fapi/v3/positionRisk?...&signature=<redacted>",
  "headers": {
    "X-MBX-APIKEY": "abcd...wxyz",
    "X-Trading-Proxy-Key": "<redacted>"
  }
}
```

The command prints a redacted request plan and does not call Binance.

## Environment proxy interaction

If shell proxy variables are set, they still apply to the Python HTTP transport. For the Caddy endpoint, prefer bypassing local HTTP proxies:

```bash
NO_PROXY=bnp.therainisme.com python /home/vivy/trading-tools/scripts/list_futures_positions.py --json
```

Or clear proxy variables for one command:

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u PROXY \
    -u http_proxy -u https_proxy -u all_proxy -u proxy \
    python /home/vivy/trading-tools/scripts/list_futures_positions.py --json
```
