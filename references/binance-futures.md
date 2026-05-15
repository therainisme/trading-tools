# Binance futures API reference

## Purpose

Shared Binance futures API notes for the `trading-tools` scripts. Tool-specific usage and script parameters live in:

- `references/render-futures-chart.md`
- `references/futures-investment-analysis.md`
- `references/list-futures-orders.md`
- `references/list-futures-positions.md`

## Public market-data endpoints

Used by `scripts/render_futures_chart.py` and `scripts/futures_investment_analysis.py`.

### USD-M exchange information

Endpoint: `GET https://fapi.binance.com/fapi/v1/exchangeInfo`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| None | None | None | Current tools download exchange metadata and validate symbols client-side. |

### USD-M kline/candlestick data

Endpoint: `GET https://fapi.binance.com/fapi/v1/klines`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | Yes | Yes | Futures symbol, for example `NVDAUSDT`. |
| `interval` | Yes | Yes | Kline interval. Chart tool accepts `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1M`. |
| `startTime` | No | Omitted | Optional historical window start time in milliseconds. |
| `endTime` | No | Omitted | Optional historical window end time in milliseconds. |
| `limit` | No | Yes | Number of klines. Binance default is `500`, max is `1500`; chart tool default is `96`. |

### USD-M premium index / mark price

Endpoint: `GET https://fapi.binance.com/fapi/v1/premiumIndex`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | No | Yes | Optional symbol filter. Investment-analysis tool sends the requested symbol. |

### USD-M funding rate history

Endpoint: `GET https://fapi.binance.com/fapi/v1/fundingRate`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | No | Yes | Symbol filter. |
| `startTime` | No | Optional | Historical window start in milliseconds. |
| `endTime` | No | Optional | Historical window end in milliseconds. |
| `limit` | No | Yes | Number of rows. Investment-analysis tool uses `--limit`. |

### USD-M current open interest

Endpoint: `GET https://fapi.binance.com/fapi/v1/openInterest`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | Yes | Yes | Futures symbol. |

### USD-M open interest statistics

Endpoint: `GET https://fapi.binance.com/futures/data/openInterestHist`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | Yes | Yes | Futures symbol. |
| `period` | Yes | Yes | Statistics period: `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `12h`, `1d`. |
| `limit` | No | Yes | Number of rows. |
| `startTime` | No | Optional | Historical window start in milliseconds. |
| `endTime` | No | Optional | Historical window end in milliseconds. |

### USD-M long/short ratio statistics

Endpoints:

- `GET https://fapi.binance.com/futures/data/globalLongShortAccountRatio`
- `GET https://fapi.binance.com/futures/data/topLongShortAccountRatio`
- `GET https://fapi.binance.com/futures/data/topLongShortPositionRatio`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | Yes | Yes | Futures symbol. |
| `period` | Yes | Yes | Statistics period: `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `12h`, `1d`. |
| `limit` | No | Yes | Number of rows. |
| `startTime` | No | Optional | Historical window start in milliseconds. |
| `endTime` | No | Optional | Historical window end in milliseconds. |

### USD-M taker buy/sell volume

Endpoint: `GET https://fapi.binance.com/futures/data/takerlongshortRatio`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | Yes | Yes | Futures symbol. |
| `period` | Yes | Yes | Statistics period: `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `12h`, `1d`. |
| `limit` | No | Yes | Number of rows. |
| `startTime` | No | Optional | Historical window start in milliseconds. |
| `endTime` | No | Optional | Historical window end in milliseconds. |

### USD-M order book depth

Endpoint: `GET https://fapi.binance.com/fapi/v1/depth`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | Yes | Yes | Futures symbol. |
| `limit` | No | Yes | Depth levels. Investment-analysis tool accepts `5`, `10`, `20`, `50`, `100`, `500`, `1000`. |

### USD-M book ticker

Endpoint: `GET https://fapi.binance.com/fapi/v1/ticker/bookTicker`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | No | Yes | Symbol filter. Investment-analysis tool sends the requested symbol. |

### USD-M aggregate trades

Endpoint: `GET https://fapi.binance.com/fapi/v1/aggTrades`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | Yes | Yes | Futures symbol. |
| `fromId` | No | Omitted | Aggregate trade id to fetch from. |
| `startTime` | No | Optional | Historical window start in milliseconds. |
| `endTime` | No | Optional | Historical window end in milliseconds. |
| `limit` | No | Yes | Number of rows. Investment-analysis tool accepts `1` through `1000`. |

## USER_DATA endpoints

Used by `scripts/list_futures_positions.py` and `scripts/futures_investment_analysis.py`.

### USD-M position risk V3

Endpoint: `GET https://fapi.binance.com/fapi/v3/positionRisk`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | No | Sent when market is `um` and symbol is set | Optional USD-M symbol filter. |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |

### COIN-M position risk

Endpoint: `GET https://dapi.binance.com/dapi/v1/positionRisk`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `marginAsset` | No | Omitted | Optional official COIN-M margin-asset filter. |
| `pair` | No | Omitted | Optional official COIN-M pair filter. |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |


### USD-M open orders

Endpoint: `GET https://fapi.binance.com/fapi/v1/openOrders`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | No | Optional | Optional USD-M symbol filter. |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |

### USD-M order history

Endpoint: `GET https://fapi.binance.com/fapi/v1/allOrders`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | Yes | Yes | Symbol filter. |
| `orderId` | No | Optional | Optional order id filter. |
| `startTime` | No | Optional | Historical window start in milliseconds. |
| `endTime` | No | Optional | Historical window end in milliseconds. |
| `limit` | No | Yes | Number of rows. |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |

### USD-M account trades

Endpoint: `GET https://fapi.binance.com/fapi/v1/userTrades`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | Yes | Yes | Symbol filter. |
| `orderId` | No | Optional | Optional order id filter. |
| `startTime` | No | Optional | Historical window start in milliseconds. |
| `endTime` | No | Optional | Historical window end in milliseconds. |
| `limit` | No | Yes | Number of rows. |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |

### USD-M current conditional orders

Endpoint: `GET https://fapi.binance.com/fapi/v1/openAlgoOrders`

Official docs: [Current All Algo Open Orders](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Algo-Open-Orders)

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `algoType` | No | Optional | Algo type filter, for example `CONDITIONAL`. |
| `symbol` | No | Optional | Symbol filter. The order tool requires `--all-symbols` when symbol is absent. |
| `algoId` | No | Optional | Binance algo order id filter. |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |

### USD-M conditional order history

Endpoint: `GET https://fapi.binance.com/fapi/v1/allAlgoOrders`

Official docs: [Query All Algo Orders](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-All-Algo-Orders)

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | Yes | Yes | Symbol filter. |
| `algoId` | No | Optional | Binance algo order id filter. |
| `startTime` | No | Optional | Historical window start in milliseconds. |
| `endTime` | No | Optional | Historical window end in milliseconds. |
| `limit` | No | Yes | Number of rows. Binance default is 500 and max is 1000. |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |

### USD-M account information V3

Endpoint: `GET https://fapi.binance.com/fapi/v3/account`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |

### USD-M account balance V3

Endpoint: `GET https://fapi.binance.com/fapi/v3/balance`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |

### USD-M notional and leverage brackets

Endpoint: `GET https://fapi.binance.com/fapi/v1/leverageBracket`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | No | Yes | Symbol filter. Investment-analysis tool sends the requested symbol. |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |

### USD-M income history

Endpoint: `GET https://fapi.binance.com/fapi/v1/income`

| Parameter | Required | Sent by current tools | Description |
| --- | --- | --- | --- |
| `symbol` | No | Yes | Symbol filter. Investment-analysis tool sends the requested symbol. |
| `incomeType` | No | Optional | Income type, such as `FUNDING_FEE`, `COMMISSION`, or `REALIZED_PNL`. |
| `startTime` | No | Optional | Historical window start in milliseconds. |
| `endTime` | No | Optional | Historical window end in milliseconds. |
| `page` | No | Omitted | Official pagination parameter. |
| `limit` | No | Yes | Number of rows. Investment-analysis tool accepts `1` through `1000`. |
| `recvWindow` | No | Yes | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Yes | Current timestamp in milliseconds. |
| `signature` | Yes for signed request | Yes | HMAC-SHA256 signature over the query string. |

Endpoint base URLs:

| Market/API | Production base URL | Testnet base URL | Paths |
| --- | --- | --- | --- |
| USD-M public and signed | `https://fapi.binance.com` | `https://demo-fapi.binance.com` for signed account-risk dry/live endpoints | `/fapi/*`, `/futures/data/*` |
| COIN-M signed account/order data | `https://dapi.binance.com` | `https://testnet.binancefuture.com` | `/dapi/*` |

## Signing

USER_DATA requests require:

- Header: `X-MBX-APIKEY`
- Query parameter: `timestamp`
- Optional query parameter: `recvWindow`
- Query parameter: `signature`, generated with HMAC SHA256 over the query string using `api_secret`

The tools sign the exact query string they send. Dry-run output replaces the signature with `<redacted>` and prints only a shortened API key.

## Common errors

- Config file missing: create `.trading-tools/config.json` in the skill root or the user home directory.
- Invalid API key: verify the key is active and has read access.
- Timestamp or recvWindow error: check local clock sync or increase `recv_window`.
- Region or product access error: verify the account can access Binance futures in the relevant environment.
- Public market-data symbol error: confirm the symbol is listed on Binance USD-M futures and has `status: TRADING`.

## Official docs

- Binance Derivatives Quick Start: https://developers.binance.com/docs/zh-CN/derivatives/quick-start
- USD-M futures exchange information: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information
- USD-M futures kline/candlestick data: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data
- USD-M mark price / premium index: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price
- USD-M funding rate history: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History
- USD-M open interest: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest
- USD-M open interest statistics: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics
- USD-M long/short ratio: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio
- USD-M top trader long/short account ratio: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio
- USD-M top trader long/short position ratio: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio
- USD-M taker buy/sell volume: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume
- USD-M order book: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book
- USD-M aggregate trades: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List
- USD-M open orders: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders
- USD-M order history: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Orders
- USD-M account trades: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List
- USD-M current conditional orders: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Algo-Open-Orders
- USD-M conditional order history: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-All-Algo-Orders
- USD-M account information V3: https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3
- USD-M account balance V3: https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V3
- USD-M notional and leverage brackets: https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets
- USD-M income history: https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History
- USD-M position risk V3: https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3
- COIN-M open orders: https://developers.binance.com/docs/derivatives/coin-margined-futures/trade/rest-api/Current-All-Open-Orders
- COIN-M order history: https://developers.binance.com/docs/derivatives/coin-margined-futures/trade/rest-api/All-Orders
- COIN-M account trades: https://developers.binance.com/docs/derivatives/coin-margined-futures/trade/rest-api/Account-Trade-List
- COIN-M position risk: https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/trade/rest-api/Position-Information
