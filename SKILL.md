---
name: trading-tools
description: Read-only Binance futures helpers for account positions and market charts. Use when Codex needs to inspect the current user's Binance USDⓈ-M or COIN-M futures position list, check open futures positions, configure JSON-based trading API credentials, render a futures candlestick chart such as NVDAUSDT, display Binance futures trend, kline, or candlestick chart images in the Codex desktop UI, or troubleshoot Binance futures USER_DATA and public market-data queries.
---

# Trading Tools

## Tool index

Load the matching reference file before running a tool.

- `scripts/render_futures_chart.py`: render a Binance USDⓈ-M futures candlestick chart as SVG or PNG from public market data. Full usage and parameters: `references/render-futures-chart.md`.
- `scripts/list_futures_positions.py`: list Binance USDⓈ-M or COIN-M futures positions for the configured account. Full usage, parameters, and config fields: `references/list-futures-positions.md`.

## Shared reference

Read `references/binance-futures.md` for Binance endpoint details, signing behavior, official docs, and common API errors.
