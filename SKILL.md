---
name: trading-tools
description: Read-only trading account helpers for Binance futures positions. Use when Codex needs to inspect the current user's Binance USDⓈ-M or COIN-M futures position list, check open futures positions, configure JSON-based trading API credentials, or troubleshoot Binance futures USER_DATA position queries.
---

# Trading Tools

## Binance futures positions

Use `scripts/list_futures_positions.py` to list the current user's Binance futures positions. The script reads JSON configuration from the skill directory first, then the user's home directory:

1. `<skill-root>/.trading-tools/config.json`
2. `~/.trading-tools/config.json`

If neither file exists, or required fields are missing, report the configuration error and do not call Binance.

## Configuration

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

- Use a read-only Binance API key.
- Keep `api_secret` out of logs and user-facing output.
- `market` is `um` for USDⓈ-M futures and `cm` for COIN-M futures.
- `recv_window` is the Binance signed-request validity window in milliseconds.
- `symbol` limits results to one symbol when set; `null` means all returned positions.

## Commands

```bash
python /home/vivy/rich/scripts/list_futures_positions.py
python /home/vivy/rich/scripts/list_futures_positions.py --market um --symbol BTCUSDT
python /home/vivy/rich/scripts/list_futures_positions.py --market cm
python /home/vivy/rich/scripts/list_futures_positions.py --json
python /home/vivy/rich/scripts/list_futures_positions.py --dry-run
```

Use `--dry-run` to verify configuration and the signed request shape without sending an API request. Dry-run output must redact the full API key, secret, and signature.

## Reference

Read `references/binance-futures.md` for endpoint details, signing behavior, and common errors.
