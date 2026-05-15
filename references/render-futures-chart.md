# render_futures_chart.py reference

## Purpose

Render a Binance USDⓈ-M futures candlestick chart from public market data. The tool validates the symbol with Binance `exchangeInfo`, fetches OHLCV candles with `klines`, then writes an SVG or PNG image.

This tool uses public market-data endpoints. It reads no API key, account config, or trading credentials.

## Command

```bash
python /home/vivy/trading-tools/scripts/render_futures_chart.py --symbol NVDAUSDT
```

The tool prints the output image path on success.

## CLI parameters

| Parameter | Required | Values | Default | Validation and behavior |
| --- | --- | --- | --- | --- |
| `--symbol SYMBOL` | Yes | Binance USDⓈ-M futures symbol, for example `NVDAUSDT` | None | Trim whitespace, uppercase, accept only letters, digits, and underscores. Validate through `exchangeInfo`; symbol must exist with `status: TRADING`. |
| `--interval INTERVAL` | No | `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1M` | `1h` | Kline interval. One candle represents this duration. Invalid values fail before the HTTP request. |
| `--limit LIMIT` | No | Integer from `1` to `1500` | `96` | Number of candles to fetch. `96` with `1h` shows about 4 days. `120` with `15m` shows about 30 hours. |
| `--timezone TIMEZONE` | No | IANA timezone name, for example `Asia/Shanghai` or `UTC` | `Asia/Shanghai` | Timezone used for x-axis labels and generated timestamp text. Invalid timezone names fail before the HTTP request. |
| `--format {svg,png}` | No | `svg`, `png` | `svg` | Output image format. SVG is written directly. PNG conversion uses CairoSVG first, then headless Chrome/Chromium. |
| `--output OUTPUT` | No | File path or directory path | `/tmp/trading-tools/charts` | Output destination. Existing directory paths receive an auto-generated filename. Paths without a suffix are treated as directories. File paths use the provided path. |
| `--timeout TIMEOUT` | No | Integer seconds | `15` | HTTP timeout for each Binance request. The same timeout applies to `exchangeInfo` and `klines`. |
| `-h`, `--help` | No | Flag | None | Print CLI help and exit. |

## Binance API parameters used by this tool

### `GET /fapi/v1/exchangeInfo`

| API parameter | Required by Binance | Source in script | Sent by script | Description |
| --- | --- | --- | --- | --- |
| None | None | None | None | The endpoint takes no request parameters. The script downloads the symbol list and validates `--symbol` client-side. |

### `GET /fapi/v1/klines`

| API parameter | Required by Binance | Source in script | Sent by script | Description |
| --- | --- | --- | --- | --- |
| `symbol` | Yes | `--symbol` | Yes | Binance USDⓈ-M futures symbol after normalization. |
| `interval` | Yes | `--interval` | Yes | Kline interval after local validation. |
| `startTime` | No | None | Omitted | Binance uses this to start a historical window. Current script requests the most recent candles. |
| `endTime` | No | None | Omitted | Binance uses this to end a historical window. Current script requests the most recent candles. |
| `limit` | No | `--limit` | Yes | Number of candles. Binance default is `500`, max is `1500`; this script defaults to `96` and enforces max `1500`. |

Kline request weight depends on `limit`: `[1,100)` uses weight `1`; `[100,500)` uses weight `2`; `[500,1000]` uses weight `5`; values above `1000` use weight `10`.

## Supported kline intervals

Binance USDⓈ-M kline intervals accepted by this tool:

- Minute: `1m`, `3m`, `5m`, `15m`, `30m`
- Hour: `1h`, `2h`, `4h`, `6h`, `8h`, `12h`
- Day/week/month: `1d`, `3d`, `1w`, `1M`

## Output parameters and file naming

Default SVG filename format:

```text
/tmp/trading-tools/charts/<SYMBOL>-<INTERVAL>-<YYYYMMDDTHHMMSSZ>.svg
```

Generated chart content:

- Candlesticks from OHLC values
- Volume bars
- Price axis using quote asset labels
- Time axis using `--timezone`
- Latest candle OHLC values
- Percentage change from first candle open to last candle close
- Data source and generation timestamp

Display a generated SVG in Codex desktop with Markdown:

```markdown
![NVDAUSDT chart](/tmp/trading-tools/charts/NVDAUSDT-1h-YYYYMMDDTHHMMSSZ.svg)
```

## Examples

Render the default 1-hour SVG chart:

```bash
python /home/vivy/trading-tools/scripts/render_futures_chart.py --symbol NVDAUSDT
```

Render a 15-minute chart with 120 candles:

```bash
python /home/vivy/trading-tools/scripts/render_futures_chart.py --symbol NVDAUSDT --interval 15m --limit 120 --timezone Asia/Shanghai
```

Render PNG fallback:

```bash
python /home/vivy/trading-tools/scripts/render_futures_chart.py --symbol NVDAUSDT --format png
```

Write to a chosen directory:

```bash
python /home/vivy/trading-tools/scripts/render_futures_chart.py --symbol NVDAUSDT --output /tmp/trading-tools/charts
```

Write to a chosen file:

```bash
python /home/vivy/trading-tools/scripts/render_futures_chart.py --symbol NVDAUSDT --output /tmp/nvdausdt.svg
```

## Data and rendering flow

1. Normalize `--symbol` to uppercase.
2. Validate `--interval`, `--limit`, and `--timezone` locally.
3. Fetch `GET https://fapi.binance.com/fapi/v1/exchangeInfo`.
4. Confirm the symbol exists and has `status: TRADING`.
5. Fetch `GET https://fapi.binance.com/fapi/v1/klines` with `symbol`, `interval`, and `limit`.
6. Render candlesticks, volume bars, price axis, time axis, latest OHLC, and percentage change.
7. Write SVG directly, or convert SVG to PNG when `--format png` is selected.

## Failure handling

- Missing `--symbol`: argparse exits with code `2`.
- Unknown symbol: the tool reports that the symbol was not found on Binance USDⓈ-M futures.
- Non-trading symbol: the tool reports the current Binance status.
- Empty kline response: the tool reports that Binance returned no klines.
- PNG conversion dependency missing: the tool reports that CairoSVG or headless Chrome/Chromium is required.
- HTTP or JSON failure: the tool wraps the Binance request error in a chart-generation error.
