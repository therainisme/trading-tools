# futures trading executor reference

## Purpose

Prepare, validate, place, cancel, and check Binance USD-M futures orders. Trading scripts are conservative by default: they print a dry-run plan unless explicitly switched to live mode. Live mode requires a matching `plan_hash` from dry-run output.

Use these tools only with a dedicated Binance API key that has Reading + Futures permissions, IP restrictions, and a narrow symbol whitelist.

## Local safety rules

- USD-M futures only.
- Local symbol whitelist: `NVDAUSDT`, `TSMUSDT`, `MUUSDT`, `AMDUSDT`.
- Default mode is `dry-run`; no request that changes orders is sent.
- Live mode requires both `--mode live --confirm LIVE --confirm-plan-hash <plan_hash>`.
- Standard test mode uses Binance `/fapi/v1/order/test`; it validates the request without creating an order.
- Secrets, API keys, and signatures are redacted in dry-run output.
- Conditional protective orders default to `workingType=MARK_PRICE` and `priceProtect=true`.
- Non-reduce-only conditional orders require `--allow-open-position`.

## Standard order tool

Command:

```bash
python /home/vivy/trading-tools/scripts/place_futures_order.py --symbol NVDAUSDT --side SELL --type LIMIT --quantity 0.25 --price 236.8 --reduce-only
```

Supported order types: `LIMIT`, `MARKET`.

Important parameters:

| Parameter | Required | Description |
| --- | --- | --- |
| `--symbol` | Yes | Whitelisted USD-M symbol. |
| `--side` | Yes | `BUY` or `SELL`. |
| `--type` | Yes | `LIMIT` or `MARKET`. |
| `--quantity` | Yes | Positive decimal quantity. |
| `--price` | LIMIT only | Positive decimal limit price. |
| `--reduce-only` | No | Sends `reduceOnly=true`. |
| `--mode` | No | `dry-run`, `test`, or `live`; default `dry-run`. |
| `--confirm-plan-hash` | Live only | Must match dry-run output. |
| `--confirm` | Live only | Must be `LIVE`. |

Live flow:

```bash
python /home/vivy/trading-tools/scripts/place_futures_order.py --symbol NVDAUSDT --side SELL --type LIMIT --quantity 0.25 --price 236.8 --reduce-only
python /home/vivy/trading-tools/scripts/place_futures_order.py --symbol NVDAUSDT --side SELL --type LIMIT --quantity 0.25 --price 236.8 --reduce-only --mode live --confirm LIVE --confirm-plan-hash <plan_hash>
```

## Conditional/algo order tool

Command:

```bash
python /home/vivy/trading-tools/scripts/place_futures_algo_order.py --symbol NVDAUSDT --side SELL --order-type STOP_MARKET --quantity 0.5 --trigger-price 227.6 --reduce-only
```

Supported order types: `STOP`, `STOP_MARKET`, `TAKE_PROFIT`, `TAKE_PROFIT_MARKET`, `TRAILING_STOP_MARKET`.

Common protective examples:

```bash
python /home/vivy/trading-tools/scripts/place_futures_algo_order.py --symbol NVDAUSDT --side SELL --order-type STOP_MARKET --quantity 0.5 --trigger-price 227.6 --reduce-only
python /home/vivy/trading-tools/scripts/place_futures_algo_order.py --symbol NVDAUSDT --side SELL --order-type TAKE_PROFIT_MARKET --quantity 0.25 --trigger-price 236.8 --reduce-only
python /home/vivy/trading-tools/scripts/place_futures_algo_order.py --symbol NVDAUSDT --side SELL --order-type STOP_MARKET --trigger-price 227.6 --close-position
```

Opening or adding exposure requires an explicit flag:

```bash
python /home/vivy/trading-tools/scripts/place_futures_algo_order.py --symbol NVDAUSDT --side BUY --order-type STOP --quantity 0.25 --trigger-price 234.9 --price 234.9 --allow-open-position
```

## Cancel tool

Dry-run cancellation of a conditional order:

```bash
python /home/vivy/trading-tools/scripts/cancel_futures_order.py --kind algo --algo-id 3000001548266417
```

Dry-run cancellation of a standard order:

```bash
python /home/vivy/trading-tools/scripts/cancel_futures_order.py --kind standard --symbol NVDAUSDT --order-id 123456
```

Live cancellation uses the same two-step hash confirmation pattern.

## Protection checker

Check all active positions:

```bash
python /home/vivy/trading-tools/scripts/check_futures_protection.py
```

Check one symbol:

```bash
python /home/vivy/trading-tools/scripts/check_futures_protection.py --symbol NVDAUSDT --json
```

The checker reads current positions, standard open orders, and conditional open orders. It reports stop coverage, take-profit coverage, oversized reduce-only orders, and working type warnings.

## Binance endpoints

- `POST /fapi/v1/order`: standard order.
- `POST /fapi/v1/order/test`: validate standard order request without creating an order.
- `POST /fapi/v1/algoOrder`: conditional/algo order.
- `DELETE /fapi/v1/order`: cancel standard order.
- `DELETE /fapi/v1/algoOrder`: cancel conditional/algo order.
- `GET /fapi/v1/openAlgoOrders`: verify current conditional orders.

Official docs:

- https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order
- https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Algo-Order
- https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order
- https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Algo-Order
- https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Algo-Open-Orders
