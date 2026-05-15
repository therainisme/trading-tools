# Binance futures positions reference

## Purpose

`trading-tools` lists the current Binance futures positions for the account represented by the configured API key. It uses read-only USER_DATA position-risk endpoints and never needs trading or withdrawal permissions.

## Config

Config is JSON only. Read order:

1. `<skill-root>/.trading-tools/config.json`
2. `~/.trading-tools/config.json`

```json
{
  "binance": {
    "api_key": "your_api_key",
    "api_secret": "your_api_secret",
    "futures": {
      "market": "um",
      "testnet": false,
      "recv_window": 5000,
      "symbol": null
    }
  }
}
```

Required fields: `binance.api_key`, `binance.api_secret`, `binance.futures.market`.

Optional fields:

- `binance.futures.testnet`: defaults to `false`.
- `binance.futures.recv_window`: defaults to `5000` milliseconds.
- `binance.futures.symbol`: defaults to `null`.

## Endpoints

- USDⓈ-M futures production: `GET https://fapi.binance.com/fapi/v3/positionRisk`
- USDⓈ-M futures testnet: `GET https://demo-fapi.binance.com/fapi/v3/positionRisk`
- COIN-M futures production: `GET https://dapi.binance.com/dapi/v1/positionRisk`
- COIN-M futures testnet: `GET https://testnet.binancefuture.com/dapi/v1/positionRisk`

USDⓈ-M accepts `symbol`, `recvWindow`, and `timestamp` parameters. COIN-M accepts `marginAsset`, `pair`, `recvWindow`, and `timestamp`; this skill performs exact `symbol` filtering client-side for COIN-M table output.

## Signing

USER_DATA requests require:

- Header: `X-MBX-APIKEY`
- Query parameter: `timestamp`
- Optional query parameter: `recvWindow`
- Query parameter: `signature`, generated with HMAC SHA256 over the query string using `api_secret`

The script signs the exact query string it sends. Dry-run output replaces the signature with `<redacted>`.

## Output

Default table fields:

- `symbol`
- `positionSide`
- `positionAmt`
- `entryPrice`
- `markPrice`
- `unRealizedProfit`
- `liquidationPrice`
- `leverage`
- `marginType`

USDⓈ-M V3 responses can omit `leverage` and `marginType`; missing values are displayed as `-`.

## Common errors

- Config file missing: create `.trading-tools/config.json` in the skill root or the user home directory.
- Invalid API key: verify the key is active and has read access.
- Timestamp or recvWindow error: check local clock sync or increase `recv_window`.
- Region or product access error: verify the account can access Binance futures in the relevant environment.

## Official docs

- Binance Derivatives Quick Start: https://developers.binance.com/docs/zh-CN/derivatives/quick-start
- USDⓈ-M futures position risk V3: https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3
- COIN-M futures position risk: https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/trade/rest-api/Position-Information
