# Binance futures API reference

## Purpose

Shared Binance futures API notes for the `trading-tools` scripts. Tool-specific usage and script parameters live in:

- `references/render-futures-chart.md`
- `references/list-futures-positions.md`

## Public market-data endpoints

Used by `scripts/render_futures_chart.py`.

### USDⓈ-M exchange information

Endpoint: `GET https://fapi.binance.com/fapi/v1/exchangeInfo`

| Parameter | Required | Sent by current tool | Description |
| --- | --- | --- | --- |
| None | None | None | The current tool downloads exchange metadata and validates symbols client-side. |

### USDⓈ-M kline/candlestick data

Endpoint: `GET https://fapi.binance.com/fapi/v1/klines`

| Parameter | Required | Sent by current tool | Description |
| --- | --- | --- | --- |
| `symbol` | Yes | Yes | Futures symbol, for example `NVDAUSDT`. |
| `interval` | Yes | Yes | Kline interval. Current tool accepts `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1M`. |
| `startTime` | No | Omitted | Optional historical window start time in milliseconds. |
| `endTime` | No | Omitted | Optional historical window end time in milliseconds. |
| `limit` | No | Yes | Number of klines. Binance default is `500`, max is `1500`; current tool default is `96`. |

Kline response array fields used by the chart tool:

| Index | Field | Used by current tool |
| --- | --- | --- |
| `0` | Open time | Yes |
| `1` | Open price | Yes |
| `2` | High price | Yes |
| `3` | Low price | Yes |
| `4` | Close price | Yes |
| `5` | Volume | Yes |
| `6` | Close time | Ignored |
| `7` | Quote asset volume | Ignored |
| `8` | Number of trades | Ignored |
| `9` | Taker buy base asset volume | Ignored |
| `10` | Taker buy quote asset volume | Ignored |
| `11` | Ignore field | Ignored |

## USER_DATA position endpoints

Used by `scripts/list_futures_positions.py`.

### USDⓈ-M position risk V3

Endpoint: `GET https://fapi.binance.com/fapi/v3/positionRisk`

| Parameter | Required | Sent by current tool | Description |
| --- | --- | --- | --- |
| `symbol` | No | Sent when market is `um` and symbol is set | Optional USDⓈ-M symbol filter. |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |

### COIN-M position risk

Endpoint: `GET https://dapi.binance.com/dapi/v1/positionRisk`

| Parameter | Required | Sent by current tool | Description |
| --- | --- | --- | --- |
| `marginAsset` | No | Omitted | Optional official COIN-M margin-asset filter. |
| `pair` | No | Omitted | Optional official COIN-M pair filter. |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |

Endpoint base URLs:

| Market | Production base URL | Testnet base URL | Path |
| --- | --- | --- | --- |
| `um` | `https://fapi.binance.com` | `https://demo-fapi.binance.com` | `/fapi/v3/positionRisk` |
| `cm` | `https://dapi.binance.com` | `https://testnet.binancefuture.com` | `/dapi/v1/positionRisk` |

## Signing

USER_DATA requests require:

- Header: `X-MBX-APIKEY`
- Query parameter: `timestamp`
- Optional query parameter: `recvWindow`
- Query parameter: `signature`, generated with HMAC SHA256 over the query string using `api_secret`

The position-listing script signs the exact query string it sends. Dry-run output replaces the signature with `<redacted>`.

## Common errors

- Config file missing: create `.trading-tools/config.json` in the skill root or the user home directory.
- Invalid API key: verify the key is active and has read access.
- Timestamp or recvWindow error: check local clock sync or increase `recv_window`.
- Region or product access error: verify the account can access Binance futures in the relevant environment.
- Public market-data symbol error: confirm the symbol is listed on Binance USDⓈ-M futures and has `status: TRADING`.

## Official docs

- Binance Derivatives Quick Start: https://developers.binance.com/docs/zh-CN/derivatives/quick-start
- USDⓈ-M futures exchange information: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information
- USDⓈ-M futures kline/candlestick data: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data
- USDⓈ-M futures position risk V3: https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3
- COIN-M futures position risk: https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/trade/rest-api/Position-Information
