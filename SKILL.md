---
name: trading-tools
description: Read-only Binance futures helpers for account positions, market charts, orders, conditional orders, and investment-analysis datasets. Use when Codex needs to inspect the current user's Binance USDⓈ-M or COIN-M futures position list, check open futures positions, view futures open orders, conditional orders, order history, or account trades, configure JSON-based trading API credentials, render a futures candlestick chart such as NVDAUSDT, fetch futures investment-analysis datasets, display Binance futures trend, kline, or candlestick chart images in the Codex desktop UI, or troubleshoot Binance futures USER_DATA and public market-data queries.
---

# Trading Tools

## Tool index

Load the matching reference file before running a tool.

- `scripts/render_futures_chart.py`: render a Binance USDⓈ-M futures candlestick chart as SVG or PNG from public market data. Full usage and parameters: `references/render-futures-chart.md`.
- `scripts/futures_investment_analysis.py`: fetch Binance USD-M futures investment-analysis datasets for valuation, positioning, sentiment, liquidity, and account risk. Full usage and parameters: `references/futures-investment-analysis.md`.
- `scripts/list_futures_orders.py`: list Binance USD-M or COIN-M futures open orders, conditional orders, order history, and account trades for the configured account. Full usage, parameters, and config fields: `references/list-futures-orders.md`.
- `scripts/list_futures_positions.py`: list Binance USDⓈ-M or COIN-M futures positions for the configured account. Full usage, parameters, and config fields: `references/list-futures-positions.md`.

## Shared reference

Read `references/binance-futures.md` for Binance endpoint details, signing behavior, official docs, and common API errors.
