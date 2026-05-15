# list_futures_orders.py reference

## Purpose

List Binance futures open orders, conditional orders, order history, and account trades using signed read-only USER_DATA endpoints. The tool supports USD-M (`um`) and COIN-M (`cm`) for standard orders/trades. Conditional order queries use Binance USD-M algo-order endpoints.

Use this when the user asks to see current futures orders, conditional orders, stop-loss/take-profit orders, trailing-stop orders, pending orders, order history, or fills/trades. The tool is read-only.

## Command

```bash
python /home/vivy/trading-tools/scripts/list_futures_orders.py --symbol NVDAUSDT
```

Default behavior fetches current standard open orders with `--kind open`.

## Config lookup

The tool reads JSON configuration from the first existing file:

1. `<skill-root>/.trading-tools/config.json`
2. `~/.trading-tools/config.json`

## Config parameters

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

| Config field | Required | Values | Default | Validation and behavior |
| --- | --- | --- | --- | --- |
| `binance` | Yes | JSON object | None | Parent object for Binance credentials and futures config. |
| `binance.api_key` | Yes | Non-empty string | None | Binance API key used in the `X-MBX-APIKEY` header. Dry-run prints a shortened redacted form. |
| `binance.api_secret` | Yes | Non-empty string | None | Secret used to HMAC-SHA256 sign the query string. The tool never prints this value. |
| `binance.futures` | Yes | JSON object | None | Parent object for futures options. |
| `binance.futures.market` | Yes | `um`, `cm` | None | Futures market: USD-M (`um`) or COIN-M (`cm`). Values are lowercased. |
| `binance.futures.testnet` | No | `true`, `false` | `false` | Use the Binance futures testnet endpoint for the configured market. Must be a JSON boolean. |
| `binance.futures.recv_window` | No | Positive integer milliseconds | `5000` | Signed request validity window. Values are parsed as integers and must be positive. |
| `binance.futures.symbol` | No | String or `null` | `null` | Optional symbol filter from config. Strings are trimmed and uppercased. Empty strings become `null`. |

## CLI parameters

| Parameter | Required | Values | Default | Validation and behavior |
| --- | --- | --- | --- | --- |
| `--kind KIND` | No | `open`, `history`, `trades`, `conditional-open`, `conditional-history` | `open` | Select standard open orders, historical orders, account trades, current conditional orders, or conditional order history. |
| `--json` | No | Flag | Table output | Print the validated raw JSON array. |
| `--market {cm,um}` | No | `um`, `cm` | Config value | Override `binance.futures.market` for this run. Conditional order kinds currently use `um`. |
| `--symbol SYMBOL` | No for `open`; Yes for `history`, `trades`, and `conditional-history` unless config has symbol; Yes for `conditional-open` unless `--all-symbols` is set | Futures symbol, for example `NVDAUSDT` or `BTCUSD_PERP` | Config value | Symbol filter. Input is trimmed and uppercased. |
| `--pair PAIR` | No | COIN-M pair, for example `BTCUSD` | None | COIN-M standard open-order pair filter. Used when `--market cm --kind open` and symbol is absent. |
| `--all-symbols` | No | Flag | Symbol required for broad guarded queries | Allow an open-order query without a symbol where Binance supports account-wide output. Required by this tool for `--kind conditional-open` without a symbol. |
| `--order-id ORDER_ID` | No | Non-negative integer | None | Optional standard order id filter for `history` and `trades`. |
| `--algo-id ALGO_ID` | No | Non-negative integer | None | Optional Binance algo order id filter for `conditional-open` and `conditional-history`. |
| `--algo-type ALGO_TYPE` | No | String such as `CONDITIONAL` | None | Optional algo type filter for `conditional-open`. Input is trimmed and uppercased. |
| `--start-time START_TIME` | No | Millisecond timestamp | None | Optional history/trades/conditional-history window start. |
| `--end-time END_TIME` | No | Millisecond timestamp | None | Optional history/trades/conditional-history window end. |
| `--limit LIMIT` | No | Integer from `1` to `1000` | `100` | Row limit for history, trades, and conditional-history. |
| `--testnet` | No | Flag | Config value | Use testnet for this run. |
| `--dry-run` | No | Flag | Send request | Print a redacted signed request without calling Binance. |
| `--timeout TIMEOUT` | No | Integer seconds | `15` | HTTP timeout. |
| `-h`, `--help` | No | Flag | None | Print CLI help and exit. |

## Binance API parameters used by this tool

### USD-M standard open orders: `GET /fapi/v1/openOrders`

| API parameter | Required by Binance | Source in script | Sent by script | Description |
| --- | --- | --- | --- | --- |
| `symbol` | No | Config `symbol` or `--symbol` | Sent when symbol is set | Optional USD-M symbol filter. |
| `recvWindow` | No | Config `recv_window` | Always sent | Signed request validity window in milliseconds. |
| `timestamp` | Yes | Current local time in milliseconds | Always sent | Timestamp used by Binance signature validation. |
| `signature` | Yes for signed request | HMAC-SHA256 over query string | Always sent | Redacted in dry-run output. |

### USD-M standard order history: `GET /fapi/v1/allOrders`

| API parameter | Required by Binance | Source in script | Sent by script | Description |
| --- | --- | --- | --- | --- |
| `symbol` | Yes | Config `symbol` or `--symbol` | Always sent | Symbol filter. |
| `orderId` | No | `--order-id` | Sent when provided | Optional standard order id cursor/filter. |
| `startTime` | No | `--start-time` | Sent when provided | Start of order history window. |
| `endTime` | No | `--end-time` | Sent when provided | End of order history window. |
| `limit` | No | `--limit` | Always sent | Row limit. |
| `recvWindow` | No | Config `recv_window` | Always sent | Signed request validity window. |
| `timestamp` | Yes | Current local time in milliseconds | Always sent | Timestamp used by Binance signature validation. |
| `signature` | Yes for signed request | HMAC-SHA256 over query string | Always sent | Redacted in dry-run output. |

### USD-M account trades: `GET /fapi/v1/userTrades`

| API parameter | Required by Binance | Source in script | Sent by script | Description |
| --- | --- | --- | --- | --- |
| `symbol` | Yes | Config `symbol` or `--symbol` | Always sent | Symbol filter. |
| `orderId` | No | `--order-id` | Sent when provided | Optional standard order id filter. |
| `startTime` | No | `--start-time` | Sent when provided | Start of trade window. |
| `endTime` | No | `--end-time` | Sent when provided | End of trade window. |
| `limit` | No | `--limit` | Always sent | Row limit. |
| `recvWindow` | No | Config `recv_window` | Always sent | Signed request validity window. |
| `timestamp` | Yes | Current local time in milliseconds | Always sent | Timestamp used by Binance signature validation. |
| `signature` | Yes for signed request | HMAC-SHA256 over query string | Always sent | Redacted in dry-run output. |

### USD-M current conditional orders: `GET /fapi/v1/openAlgoOrders`

| API parameter | Required by Binance | Source in script | Sent by script | Description |
| --- | --- | --- | --- | --- |
| `algoType` | No | `--algo-type` | Sent when provided | Optional algo type filter, for example `CONDITIONAL`. |
| `symbol` | No | Config `symbol` or `--symbol` | Sent when symbol is set | Optional symbol filter. The script requires `--all-symbols` when symbol is absent. |
| `algoId` | No | `--algo-id` | Sent when provided | Optional Binance algo order id filter. |
| `recvWindow` | No | Config `recv_window` | Always sent | Signed request validity window. |
| `timestamp` | Yes | Current local time in milliseconds | Always sent | Timestamp used by Binance signature validation. |
| `signature` | Yes for signed request | HMAC-SHA256 over query string | Always sent | Redacted in dry-run output. |

### USD-M conditional order history: `GET /fapi/v1/allAlgoOrders`

| API parameter | Required by Binance | Source in script | Sent by script | Description |
| --- | --- | --- | --- | --- |
| `symbol` | Yes | Config `symbol` or `--symbol` | Always sent | Symbol filter. |
| `algoId` | No | `--algo-id` | Sent when provided | Optional Binance algo order id cursor/filter. |
| `startTime` | No | `--start-time` | Sent when provided | Start of conditional order history window. |
| `endTime` | No | `--end-time` | Sent when provided | End of conditional order history window. |
| `limit` | No | `--limit` | Always sent | Row limit. Binance default is 500 and max is 1000; this tool default is 100. |
| `recvWindow` | No | Config `recv_window` | Always sent | Signed request validity window. |
| `timestamp` | Yes | Current local time in milliseconds | Always sent | Timestamp used by Binance signature validation. |
| `signature` | Yes for signed request | HMAC-SHA256 over query string | Always sent | Redacted in dry-run output. |

### COIN-M standard endpoints

COIN-M standard order queries use the same request shape against `/dapi/v1/openOrders`, `/dapi/v1/allOrders`, and `/dapi/v1/userTrades`. COIN-M open-order queries can use `pair` when no exact symbol is provided.

## Endpoint selection

| Market | Production base URL | Testnet base URL | Open orders | Order history | Trades | Conditional open | Conditional history |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `um` | `https://fapi.binance.com` | `https://demo-fapi.binance.com` | `/fapi/v1/openOrders` | `/fapi/v1/allOrders` | `/fapi/v1/userTrades` | `/fapi/v1/openAlgoOrders` | `/fapi/v1/allAlgoOrders` |
| `cm` | `https://dapi.binance.com` | `https://testnet.binancefuture.com` | `/dapi/v1/openOrders` | `/dapi/v1/allOrders` | `/dapi/v1/userTrades` | None | None |

## Examples

List standard open orders for one USD-M symbol:

```bash
python /home/vivy/trading-tools/scripts/list_futures_orders.py --symbol NVDAUSDT
```

List current USD-M conditional orders for one symbol:

```bash
python /home/vivy/trading-tools/scripts/list_futures_orders.py --kind conditional-open --symbol NVDAUSDT
```

List current USD-M conditional orders with the official algo type filter:

```bash
python /home/vivy/trading-tools/scripts/list_futures_orders.py --kind conditional-open --symbol NVDAUSDT --algo-type CONDITIONAL
```

List USD-M conditional order history for one symbol:

```bash
python /home/vivy/trading-tools/scripts/list_futures_orders.py --kind conditional-history --symbol NVDAUSDT --limit 50
```

List all USD-M standard open orders when supported by Binance:

```bash
python /home/vivy/trading-tools/scripts/list_futures_orders.py --market um --all-symbols
```

List standard order history for one symbol:

```bash
python /home/vivy/trading-tools/scripts/list_futures_orders.py --kind history --symbol NVDAUSDT --limit 50
```

List fills/account trades for one symbol:

```bash
python /home/vivy/trading-tools/scripts/list_futures_orders.py --kind trades --symbol NVDAUSDT --limit 50
```

Preview without sending a request:

```bash
python /home/vivy/trading-tools/scripts/list_futures_orders.py --kind conditional-open --symbol NVDAUSDT --dry-run --json
```

## Output fields

Standard open-order table fields: `symbol`, `orderId`, `side`, `positionSide`, `type`, `status`, `price`, `origQty`, `executedQty`, `reduceOnly`, `timeInForce`, `time`.

Standard order-history table fields: `symbol`, `orderId`, `side`, `positionSide`, `type`, `status`, `avgPrice`, `price`, `origQty`, `executedQty`, `time`.

Trade table fields: `symbol`, `id`, `orderId`, `side`, `positionSide`, `price`, `qty`, `quoteQty`, `realizedPnl`, `commission`, `commissionAsset`, `time`.

Conditional-order table fields: `symbol`, `algoId`, `algoType`, `orderType`, `side`, `positionSide`, `algoStatus`, `quantity`, `triggerPrice`, `price`, `actualOrderId`, `actualQty`, `actualPrice`, `workingType`, `closePosition`, `reduceOnly`, `createTime`, `updateTime`, `triggerTime`. Use `--json` to inspect every raw Binance field, including `clientAlgoId`, TP/SL extension fields, price protection, and good-till-date values.

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
- Invalid market: the tool accepts `um` and `cm`.
- Conditional order query with `--market cm`: the tool reports that conditional order queries currently support `--market um`.
- Missing symbol for history/trades/conditional-history: the tool exits before calling Binance.
- Missing symbol for conditional-open without `--all-symbols`: the tool exits before calling Binance.
- COIN-M broad standard open-order request without `--symbol`, `--pair`, or `--all-symbols`: the tool exits before calling Binance.
- Binance HTTP error: the tool reports the HTTP status and Binance response body.
- Invalid JSON response: the tool reports a JSON parse error.
- Unexpected response shape: the tool reports the response shape problem.
