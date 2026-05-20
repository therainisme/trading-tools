# futures_investment_analysis.py reference

## Purpose

Fetch Binance USD-M futures datasets used for investment analysis. The tool groups endpoints by business category:

- `valuation`: mark price, index price, premium, and funding-rate history.
- `positioning`: current open interest and open-interest history.
- `sentiment`: global account ratio, top-trader ratios, and taker buy/sell volume.
- `liquidity`: order book depth, book ticker, and aggregate trades.
- `account-risk`: signed account risk, balance, leverage bracket, and income data.

`valuation`, `positioning`, `sentiment`, and `liquidity` use public market-data endpoints. `account-risk` uses signed USER_DATA endpoints and reads credentials from the standard trading-tools JSON config.

## Command

```bash
python /home/vivy/trading-tools/scripts/futures_investment_analysis.py --symbol NVDAUSDT --groups valuation,positioning,sentiment,liquidity
```

Use account-risk with dry-run first:

```bash
python /home/vivy/trading-tools/scripts/futures_investment_analysis.py --symbol NVDAUSDT --groups account-risk --dry-run --json
```

## CLI parameters

| Parameter | Required | Values | Default | Validation and behavior |
| --- | --- | --- | --- | --- |
| `--symbol SYMBOL` | Yes | Binance USD-M futures symbol, for example `NVDAUSDT` | None | Trim whitespace, uppercase, accept only letters, digits, and underscores. Used by every endpoint that supports a symbol filter. |
| `--groups GROUPS` | No | Comma-separated `valuation`, `positioning`, `sentiment`, `liquidity`, `account-risk` | `valuation,positioning,sentiment,liquidity` | Select endpoint groups. Order is preserved and duplicate group names are removed. |
| `--period PERIOD` | No | `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `12h`, `1d` | `1h` | Period used by Binance `/futures/data/*` statistical endpoints. |
| `--limit LIMIT` | No | Integer from `1` to `500` | `30` | Historical rows for valuation, positioning, and sentiment datasets. |
| `--depth-limit DEPTH_LIMIT` | No | `5`, `10`, `20`, `50`, `100`, `500`, `1000` | `20` | Order book depth row count for bids and asks. |
| `--agg-trades-limit AGG_TRADES_LIMIT` | No | Integer from `1` to `1000` | `100` | Aggregate trade rows. |
| `--income-limit INCOME_LIMIT` | No | Integer from `1` to `1000` | `100` | Account-risk income history rows. |
| `--start-time START_TIME` | No | Millisecond timestamp | None | Optional historical window start for funding rate, `/futures/data/*`, aggregate trades, and income history. |
| `--end-time END_TIME` | No | Millisecond timestamp | None | Optional historical window end for funding rate, `/futures/data/*`, aggregate trades, and income history. |
| `--income-type INCOME_TYPE` | No | Binance income type such as `FUNDING_FEE`, `COMMISSION`, `REALIZED_PNL` | None | Optional account-risk income filter. Input is uppercased. |
| `--recv-window RECV_WINDOW` | No | Positive integer up to `60000` | Config value or `5000` | Override signed request validity window for account-risk endpoints. |
| `--testnet` | No | Flag | Config value | Use USD-M futures testnet base URL for signed account-risk endpoints. |
| `--json` | No | Flag | Summary output | Print full JSON payload including raw endpoint responses. |
| `--dry-run` | No | Flag | Send requests | Print request plan without sending requests. Signed URLs redact signatures and API keys. |
| `--timeout TIMEOUT` | No | Integer seconds | `15` | HTTP timeout for each request. |
| `-h`, `--help` | No | Flag | None | Print CLI help and exit. |

## Config parameters for account-risk

The tool reads the first existing config file:

1. `<skill-root>/.trading-tools/config.json`
2. `~/.trading-tools/config.json`

See `references/configuration.md` for the complete `config.json` shape, including the optional Caddy proxy block. Public market-data requests also use the proxy block when it is present.

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

| Config field | Required for account-risk | Values | Default | Validation and behavior |
| --- | --- | --- | --- | --- |
| `binance` | Yes | JSON object | None | Parent object for Binance credentials and futures config. |
| `binance.api_key` | Yes | Non-empty string | None | Sent as `X-MBX-APIKEY` for signed requests. Dry-run displays only a redacted form. |
| `binance.api_secret` | Yes | Non-empty string | None | Used only for HMAC-SHA256 signing. Never printed. |
| `binance.futures` | Yes | JSON object | None | Parent object for futures options. |
| `binance.futures.recv_window` | No | Positive integer milliseconds | `5000` | Used as account-risk `recvWindow` unless `--recv-window` is passed. |
| `binance.futures.testnet` | No | `true`, `false` | `false` | Used as account-risk testnet setting unless `--testnet` is passed. |
| `binance.futures.market` | No | `um`, `cm` | None | Present for compatibility with position tools. The investment-analysis account-risk endpoints are USD-M. |
| `binance.futures.symbol` | No | String or `null` | `null` | Present for compatibility with position tools. This tool uses `--symbol`. |
| `binance.futures.proxy` | No | JSON object | Disabled | Optional endpoint proxy config used by public and signed requests. |
| `binance.futures.proxy.enabled` | Yes when `proxy` exists | `true`, `false` | `false` | Enables proxy route rewriting. |
| `binance.futures.proxy.base_url` | Yes when enabled | HTTP(S) URL | None | Proxy origin. Current Caddy proxy uses `https://bnp.therainisme.com`. |
| `binance.futures.proxy.auth_header` | No | HTTP header name | `X-Trading-Proxy-Key` | Header used for proxy authentication. |
| `binance.futures.proxy.auth_key` | Yes when enabled | Non-empty string | None | Proxy key. Must match the Caddy `TRADING_PROXY_KEY` environment variable. |

## Valuation endpoints

| Dataset name | Endpoint | API parameters sent | Purpose |
| --- | --- | --- | --- |
| `premium_index` | `GET /fapi/v1/premiumIndex` | `symbol` | Mark price, index price, estimated settlement price, last funding rate, next funding time. |
| `funding_rate` | `GET /fapi/v1/fundingRate` | `symbol`, `limit`, optional `startTime`, `endTime` | Historical funding-rate costs and crowding signal. |

## Positioning endpoints

| Dataset name | Endpoint | API parameters sent | Purpose |
| --- | --- | --- | --- |
| `open_interest` | `GET /fapi/v1/openInterest` | `symbol` | Current open interest quantity. |
| `open_interest_history` | `GET /futures/data/openInterestHist` | `symbol`, `period`, `limit`, optional `startTime`, `endTime` | Open interest history and open interest value. |

## Sentiment endpoints

| Dataset name | Endpoint | API parameters sent | Purpose |
| --- | --- | --- | --- |
| `global_long_short_account_ratio` | `GET /futures/data/globalLongShortAccountRatio` | `symbol`, `period`, `limit`, optional `startTime`, `endTime` | Global account long/short ratio. |
| `top_trader_long_short_account_ratio` | `GET /futures/data/topLongShortAccountRatio` | `symbol`, `period`, `limit`, optional `startTime`, `endTime` | Top-trader account long/short ratio. |
| `top_trader_long_short_position_ratio` | `GET /futures/data/topLongShortPositionRatio` | `symbol`, `period`, `limit`, optional `startTime`, `endTime` | Top-trader position long/short ratio. |
| `taker_buy_sell_volume` | `GET /futures/data/takerlongshortRatio` | `symbol`, `period`, `limit`, optional `startTime`, `endTime` | Taker buy volume, sell volume, and buy/sell ratio. |

## Liquidity endpoints

| Dataset name | Endpoint | API parameters sent | Purpose |
| --- | --- | --- | --- |
| `order_book_depth` | `GET /fapi/v1/depth` | `symbol`, `limit` | Order book bids and asks. |
| `book_ticker` | `GET /fapi/v1/ticker/bookTicker` | `symbol` | Best bid/ask and quantities. |
| `aggregate_trades` | `GET /fapi/v1/aggTrades` | `symbol`, `limit`, optional `startTime`, `endTime` | Recent aggregate trades and buyer/seller aggressor flag. |

## Account-risk endpoints

| Dataset name | Endpoint | API parameters sent | Purpose |
| --- | --- | --- | --- |
| `account_information` | `GET /fapi/v3/account` | `recvWindow`, `timestamp`, `signature` | Account margin, wallet balance, unrealized PnL, positions, and assets. |
| `account_balance` | `GET /fapi/v3/balance` | `recvWindow`, `timestamp`, `signature` | Account asset balances. |
| `leverage_bracket` | `GET /fapi/v1/leverageBracket` | `symbol`, `recvWindow`, `timestamp`, `signature` | Symbol notional and leverage bracket. |
| `income_history` | `GET /fapi/v1/income` | `symbol`, `limit`, optional `incomeType`, `startTime`, `endTime`, plus `recvWindow`, `timestamp`, `signature` | Income rows such as funding fees, commissions, and realized PnL. |

## Output behavior

Default output is a compact summary with the latest values from each selected dataset. `--json` prints the full raw response bundle:

```json
{
  "metadata": {
    "symbol": "NVDAUSDT",
    "groups": ["valuation", "positioning"],
    "period": "1h",
    "limit": 30
  },
  "dry_run": false,
  "data": {
    "premium_index": {},
    "funding_rate": [],
    "open_interest": {}
  }
}
```

Dry-run output uses `requests` instead of `data` and redacts account-risk credentials:

```json
{
  "name": "account_information",
  "signed": true,
  "url": "https://fapi.binance.com/fapi/v3/account?recvWindow=5000&timestamp=...&signature=<redacted>",
  "headers": {"X-MBX-APIKEY": "ABCD...IJKL"},
  "signature": "<redacted>"
}
```

## Examples

Fetch public analysis summary:

```bash
python /home/vivy/trading-tools/scripts/futures_investment_analysis.py --symbol NVDAUSDT --groups valuation,positioning,sentiment,liquidity --period 1h --limit 30
```

Fetch full JSON for public datasets:

```bash
python /home/vivy/trading-tools/scripts/futures_investment_analysis.py --symbol NVDAUSDT --groups valuation,positioning,sentiment,liquidity --json
```

Preview signed account-risk requests:

```bash
python /home/vivy/trading-tools/scripts/futures_investment_analysis.py --symbol NVDAUSDT --groups account-risk --dry-run --json
```

Fetch account-risk data:

```bash
python /home/vivy/trading-tools/scripts/futures_investment_analysis.py --symbol NVDAUSDT --groups account-risk --json
```

Fetch funding-fee income rows:

```bash
python /home/vivy/trading-tools/scripts/futures_investment_analysis.py --symbol NVDAUSDT --groups account-risk --income-type FUNDING_FEE --income-limit 50 --json
```

## Failure handling

- Missing `--symbol`: argparse exits with code `2`.
- Invalid group, period, depth limit, or numeric limit: the tool exits before sending requests.
- Account-risk config missing or invalid: the tool reports all checked config paths or the invalid field name.
- Binance HTTP error: the tool reports the HTTP status and Binance response body.
- Invalid JSON response: the tool reports a JSON parse error.
- Dry-run never sends requests and never prints full API keys, secrets, or signatures.
