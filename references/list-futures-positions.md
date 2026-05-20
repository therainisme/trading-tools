# list_futures_positions.py reference

## Purpose

List the current user's Binance futures positions using signed USER_DATA endpoints. The tool supports USDⓈ-M (`um`) and COIN-M (`cm`) futures.

Use a read-only Binance API key. Keep `api_secret` out of logs and user-facing output.

## Command

```bash
python /home/vivy/trading-tools/scripts/list_futures_positions.py
```

## Config lookup

The tool reads JSON configuration from the first existing file:

1. `<skill-root>/.trading-tools/config.json`
2. `~/.trading-tools/config.json`

## Config parameters

See `references/configuration.md` for the complete `config.json` shape, including the optional Caddy proxy block.

```json
{
  "binance": {
    "api_key": "your_api_key",
    "api_secret": "your_api_secret",
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

| Config field | Required | Values | Default | Validation and behavior |
| --- | --- | --- | --- | --- |
| `binance` | Yes | JSON object | None | Parent object for Binance credentials and futures config. |
| `binance.api_key` | Yes | Non-empty string | None | Binance API key used in the `X-MBX-APIKEY` header. Dry-run prints a shortened redacted form. |
| `binance.api_secret` | Yes | Non-empty string | None | Secret used to HMAC-SHA256 sign the query string. Never printed by the tool. |
| `binance.futures` | Yes | JSON object | None | Parent object for futures options. |
| `binance.futures.market` | Yes | `um`, `cm` | None | Futures market: USDⓈ-M (`um`) or COIN-M (`cm`). Values are lowercased. |
| `binance.futures.testnet` | No | `true`, `false` | `false` | Use the Binance futures testnet endpoint for the configured market. Must be a JSON boolean. |
| `binance.futures.recv_window` | No | Positive integer milliseconds | `5000` | Signed request validity window. Values are parsed as integers and must be positive. |
| `binance.futures.symbol` | No | String or `null` | `null` | Optional symbol filter from config. Strings are trimmed and uppercased. Empty strings become `null`. |
| `binance.futures.proxy` | No | JSON object | Disabled | Optional endpoint proxy config. Current Caddy proxy uses `https://bnp.therainisme.com`. |
| `binance.futures.proxy.enabled` | Yes when `proxy` exists | `true`, `false` | `false` | Enables proxy route rewriting. |
| `binance.futures.proxy.base_url` | Yes when enabled | HTTP(S) URL | None | Proxy origin. Official `https://fapi.binance.com` maps to `base_url + /fapi`. |
| `binance.futures.proxy.auth_header` | No | HTTP header name | `X-Trading-Proxy-Key` | Header used for proxy authentication. |
| `binance.futures.proxy.auth_key` | Yes when enabled | Non-empty string | None | Proxy key. Must match the Caddy `TRADING_PROXY_KEY` environment variable. |

## CLI parameters

| Parameter | Required | Values | Default | Validation and behavior |
| --- | --- | --- | --- | --- |
| `--json` | No | Flag | Table output | Print the validated raw JSON position array. This bypasses table formatting. |
| `--include-zero` | No | Flag | Hide zero-size positions | Include zero-size positions in table output. Zero-size filtering uses `positionAmt`. |
| `--market {cm,um}` | No | `um`, `cm` | Config value | Override `binance.futures.market` for this run. argparse validates accepted values. |
| `--symbol SYMBOL` | No | Futures symbol, for example `BTCUSDT` or `BTCUSD_PERP` | Config value | Override `binance.futures.symbol` for this run. Input is trimmed and uppercased. Empty strings become `null`. |
| `--testnet` | No | Flag | Config value | Force testnet for this run. This only turns testnet on for the current invocation. |
| `--dry-run` | No | Flag | Send request | Print a redacted signed request without calling Binance. Combines with `--json` to print the dry-run payload as JSON. |
| `-h`, `--help` | No | Flag | None | Print CLI help and exit. |

CLI overrides apply after config loading. `--market`, `--symbol`, and `--testnet` replace the corresponding loaded config values for the current run.

## Binance API parameters used by this tool

### USDⓈ-M: `GET /fapi/v3/positionRisk`

| API parameter | Required by Binance | Source in script | Sent by script | Description |
| --- | --- | --- | --- | --- |
| `symbol` | No | Config `binance.futures.symbol` or `--symbol` | Sent when market is `um` and symbol is set | Limits the USDⓈ-M request to one symbol. |
| `recvWindow` | No | Config `binance.futures.recv_window` | Always sent | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Current local time in milliseconds | Always sent | Timestamp used by Binance signature validation. |
| `signature` | Yes for signed request | HMAC-SHA256 over query string using `api_secret` | Always sent | Appended after signing. Redacted in dry-run output. |

### COIN-M: `GET /dapi/v1/positionRisk`

| API parameter | Required by Binance | Source in script | Sent by script | Description |
| --- | --- | --- | --- | --- |
| `marginAsset` | No | None | Omitted | Official endpoint filter for margin asset. Current script uses exact symbol filtering client-side for table output. |
| `pair` | No | None | Omitted | Official endpoint filter for contract pair. Current script uses exact symbol filtering client-side for table output. |
| `recvWindow` | No | Config `binance.futures.recv_window` | Always sent | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Current local time in milliseconds | Always sent | Timestamp used by Binance signature validation. |
| `signature` | Yes for signed request | HMAC-SHA256 over query string using `api_secret` | Always sent | Appended after signing. Redacted in dry-run output. |

## Endpoint selection

| Market | Production base URL | Testnet base URL | Path |
| --- | --- | --- | --- |
| `um` | `https://fapi.binance.com` | `https://demo-fapi.binance.com` | `/fapi/v3/positionRisk` |
| `cm` | `https://dapi.binance.com` | `https://testnet.binancefuture.com` | `/dapi/v1/positionRisk` |

## Output parameters and fields

Default table fields:

| Field | Description |
| --- | --- |
| `symbol` | Futures symbol. |
| `positionSide` | Position side, such as `BOTH`, `LONG`, or `SHORT`. |
| `positionAmt` | Position size. Zero means no open size for that side. |
| `entryPrice` | Average entry price. |
| `markPrice` | Current mark price in the response. |
| `unRealizedProfit` | Unrealized profit. |
| `liquidationPrice` | Liquidation price. |
| `leverage` | Position leverage when the endpoint response includes it. |
| `marginType` | Margin type when the endpoint response includes it. |

Missing fields are displayed as `-` in table output. USDⓈ-M V3 responses can omit `leverage` and `marginType`.

`--json` prints the raw validated position array returned by Binance. It is useful for debugging field availability and downstream parsing.

## Dry-run payload fields

| Field | Description |
| --- | --- |
| `config_path` | Config file path used for this run. |
| `market` | Effective market after CLI overrides. |
| `testnet` | Effective testnet flag after CLI overrides. |
| `method` | HTTP method. |
| `base_url` | Selected Binance base URL. |
| `path` | Selected position endpoint path. |
| `query` | Query string before signature is appended. |
| `url` | Redacted final URL. |
| `headers.X-MBX-APIKEY` | Redacted API key. |
| `signature` | Always shown as `<redacted>`. |
| `client_side_symbol_filter` | COIN-M symbol filter used by table output when applicable. |

## Examples

List active configured futures positions:

```bash
python /home/vivy/trading-tools/scripts/list_futures_positions.py
```

List one USDⓈ-M symbol:

```bash
python /home/vivy/trading-tools/scripts/list_futures_positions.py --market um --symbol BTCUSDT
```

List COIN-M futures positions:

```bash
python /home/vivy/trading-tools/scripts/list_futures_positions.py --market cm
```

Print raw JSON:

```bash
python /home/vivy/trading-tools/scripts/list_futures_positions.py --json
```

Verify the signed request shape without sending it:

```bash
python /home/vivy/trading-tools/scripts/list_futures_positions.py --dry-run
```

## Signing and redaction

Signed requests include:

- Header: `X-MBX-APIKEY`
- Query parameter: `timestamp`
- Query parameter: `recvWindow`
- Query parameter: `signature`

The signature is HMAC-SHA256 over the exact query string using `api_secret`. Dry-run output redacts the full API key and signature.

## Failure handling

- Missing config: the tool reports all checked config paths.
- Invalid config: the tool reports the invalid field name.
- Invalid market: the tool accepts only `um` and `cm`.
- Binance HTTP error: the tool reports the HTTP status and Binance response body.
- Invalid JSON response: the tool reports a JSON parse error.
- Unexpected response shape: the tool reports the response shape problem.
