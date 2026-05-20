#!/usr/bin/env python3
"""List the current user's Binance futures positions.

Configuration is read from JSON only:
1. <skill-root>/.trading-tools/config.json
2. ~/.trading-tools/config.json
"""

from __future__ import annotations

import argparse
import json
import hmac
import hashlib
import sys
import time
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from binance_proxy import (  # noqa: E402
    DISABLED_PROXY_CONFIG,
    BinanceProxyConfig,
    add_proxy_auth_headers,
    parse_proxy_config,
    redacted_proxy_auth_headers,
    resolve_proxy_base_url,
)
from http_transport import ProxyConfigError, urlopen_with_env_proxy  # noqa: E402


MARKETS = {"um", "cm"}
DEFAULT_RECV_WINDOW = 5000
POSITION_PATHS = {
    "um": "/fapi/v3/positionRisk",
    "cm": "/dapi/v1/positionRisk",
}
BASE_URLS = {
    ("um", False): "https://fapi.binance.com",
    ("um", True): "https://demo-fapi.binance.com",
    ("cm", False): "https://dapi.binance.com",
    ("cm", True): "https://testnet.binancefuture.com",
}
TABLE_FIELDS = [
    "symbol",
    "positionSide",
    "positionAmt",
    "entryPrice",
    "markPrice",
    "unRealizedProfit",
    "liquidationPrice",
    "leverage",
    "marginType",
]


class ConfigError(Exception):
    """Raised when trading-tools configuration is missing or invalid."""


class BinanceAPIError(Exception):
    """Raised when Binance returns an HTTP or JSON error."""


@dataclass(frozen=True)
class BinanceFuturesConfig:
    api_key: str
    api_secret: str
    market: str
    testnet: bool = False
    recv_window: int = DEFAULT_RECV_WINDOW
    symbol: str | None = None
    config_path: Path | None = None
    proxy_config: BinanceProxyConfig = DISABLED_PROXY_CONFIG


@dataclass(frozen=True)
class SignedRequest:
    method: str
    base_url: str
    path: str
    query: str
    signature: str
    url: str
    headers: dict[str, str]


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def config_candidates(root: Path | None = None, home: Path | None = None) -> list[Path]:
    root_path = root or skill_root()
    home_path = home or Path.home()
    return [
        root_path / ".trading-tools" / "config.json",
        home_path / ".trading-tools" / "config.json",
    ]


def find_config_path(root: Path | None = None, home: Path | None = None) -> Path:
    candidates = config_candidates(root=root, home=home)
    for path in candidates:
        if path.is_file():
            return path
    candidate_text = "\n".join(f"  - {path}" for path in candidates)
    raise ConfigError(
        "trading-tools config file was not found. Create one of:\n"
        f"{candidate_text}"
    )


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"failed to read config file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"config file {path} must contain a JSON object")
    return data


def _required_object(data: dict[str, Any], key: str, path: Path) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"config field '{key}' in {path} must be a JSON object")
    return value


def _required_non_empty_string(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"config field 'binance.{key}' in {path} must be a non-empty string")
    return value.strip()


def parse_bool(value: Any, field_name: str, path: Path) -> bool:
    if isinstance(value, bool):
        return value
    raise ConfigError(f"config field '{field_name}' in {path} must be true or false")


def parse_recv_window(value: Any, path: Path) -> int:
    try:
        recv_window = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"config field 'binance.futures.recv_window' in {path} must be a positive integer"
        ) from exc
    if recv_window <= 0:
        raise ConfigError(
            f"config field 'binance.futures.recv_window' in {path} must be a positive integer"
        )
    return recv_window


def normalize_symbol(value: Any, path: Path) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        symbol = value.strip().upper()
        return symbol or None
    raise ConfigError(f"config field 'binance.futures.symbol' in {path} must be a string or null")


def normalize_config(data: dict[str, Any], path: Path) -> BinanceFuturesConfig:
    binance = _required_object(data, "binance", path)
    futures = _required_object(binance, "futures", path)

    api_key = _required_non_empty_string(binance, "api_key", path)
    api_secret = _required_non_empty_string(binance, "api_secret", path)

    market_value = futures.get("market")
    if not isinstance(market_value, str) or not market_value.strip():
        raise ConfigError(f"config field 'binance.futures.market' in {path} must be 'um' or 'cm'")
    market = market_value.strip().lower()
    if market not in MARKETS:
        raise ConfigError(f"config field 'binance.futures.market' in {path} must be 'um' or 'cm'")

    testnet = parse_bool(futures.get("testnet", False), "binance.futures.testnet", path)
    recv_window = parse_recv_window(futures.get("recv_window", DEFAULT_RECV_WINDOW), path)
    symbol = normalize_symbol(futures.get("symbol"), path)

    return BinanceFuturesConfig(
        api_key=api_key,
        api_secret=api_secret,
        market=market,
        testnet=testnet,
        recv_window=recv_window,
        symbol=symbol,
        config_path=path,
        proxy_config=parse_proxy_config(futures, path, ConfigError),
    )


def load_config(root: Path | None = None, home: Path | None = None) -> BinanceFuturesConfig:
    path = find_config_path(root=root, home=home)
    return normalize_config(load_json_file(path), path)


def apply_overrides(
    config: BinanceFuturesConfig,
    market: str | None = None,
    symbol: str | None = None,
    testnet: bool = False,
) -> BinanceFuturesConfig:
    changes: dict[str, Any] = {}
    if market is not None:
        market_normalized = market.strip().lower()
        if market_normalized not in MARKETS:
            raise ConfigError("--market must be 'um' or 'cm'")
        changes["market"] = market_normalized
    if symbol is not None:
        symbol_normalized = symbol.strip().upper()
        changes["symbol"] = symbol_normalized or None
    if testnet:
        changes["testnet"] = True
    return replace(config, **changes)


def current_timestamp_ms() -> int:
    return int(time.time() * 1000)


def build_query_params(config: BinanceFuturesConfig, timestamp_ms: int) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = []
    if config.market == "um" and config.symbol:
        params.append(("symbol", config.symbol))
    params.append(("recvWindow", str(config.recv_window)))
    params.append(("timestamp", str(timestamp_ms)))
    return params


def sign_query(query: str, api_secret: str) -> str:
    return hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


def build_signed_request(config: BinanceFuturesConfig, timestamp_ms: int | None = None) -> SignedRequest:
    timestamp = timestamp_ms if timestamp_ms is not None else current_timestamp_ms()
    base_url = resolve_proxy_base_url(BASE_URLS[(config.market, config.testnet)], config.proxy_config)
    path = POSITION_PATHS[config.market]
    query = urlencode(build_query_params(config, timestamp))
    signature = sign_query(query, config.api_secret)
    signed_query = f"{query}&signature={signature}"
    return SignedRequest(
        method="GET",
        base_url=base_url,
        path=path,
        query=query,
        signature=signature,
        url=f"{base_url}{path}?{signed_query}",
        headers=add_proxy_auth_headers({"X-MBX-APIKEY": config.api_key}, config.proxy_config),
    )


def redact_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "<redacted>"
    return f"{api_key[:4]}...{api_key[-4:]}"


def redacted_url(request: SignedRequest) -> str:
    return f"{request.base_url}{request.path}?{request.query}&signature=<redacted>"


def dry_run_payload(config: BinanceFuturesConfig, request: SignedRequest) -> dict[str, Any]:
    headers = {"X-MBX-APIKEY": redact_api_key(config.api_key)}
    headers.update(redacted_proxy_auth_headers(config.proxy_config))
    return {
        "config_path": str(config.config_path) if config.config_path else None,
        "market": config.market,
        "testnet": config.testnet,
        "method": request.method,
        "base_url": request.base_url,
        "path": request.path,
        "query": request.query,
        "url": redacted_url(request),
        "headers": headers,
        "signature": "<redacted>",
        "client_side_symbol_filter": config.symbol if config.market == "cm" and config.symbol else None,
    }


def format_dry_run(payload: dict[str, Any]) -> str:
    lines = [
        "Dry run: Binance request was not sent.",
        f"config_path: {payload['config_path']}",
        f"market: {payload['market']}",
        f"testnet: {payload['testnet']}",
        f"method: {payload['method']}",
        f"base_url: {payload['base_url']}",
        f"path: {payload['path']}",
        f"query: {payload['query']}",
        f"url: {payload['url']}",
        "signature: <redacted>",
    ]
    for header_name, header_value in payload["headers"].items():
        lines.insert(-1, f"{header_name}: {header_value}")
    if payload.get("client_side_symbol_filter"):
        lines.append(f"client_side_symbol_filter: {payload['client_side_symbol_filter']}")
    return "\n".join(lines)


def fetch_json(
    request: SignedRequest,
    opener: Callable[..., Any] | None = None,
    timeout: int = 10,
) -> Any:
    req = Request(request.url, headers=request.headers, method=request.method)
    http_open = opener or urlopen_with_env_proxy
    try:
        with http_open(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except ProxyConfigError as exc:
        raise BinanceAPIError(f"proxy configuration error: {exc}") from exc
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise BinanceAPIError(f"Binance API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise BinanceAPIError(f"Binance API request failed: {exc}") from exc
    except OSError as exc:
        raise BinanceAPIError(f"Binance API request failed: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise BinanceAPIError(f"Binance API returned invalid JSON: {exc}") from exc


def ensure_position_list(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise BinanceAPIError("Binance API response must be a JSON array")
    positions: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise BinanceAPIError(f"Binance API response item {index} must be a JSON object")
        positions.append(item)
    return positions


def decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def is_nonzero_position(position: dict[str, Any]) -> bool:
    return decimal_value(position.get("positionAmt", "0")) != 0


def filter_positions(
    positions: Iterable[dict[str, Any]],
    include_zero: bool = False,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    symbol_normalized = symbol.upper() if symbol else None
    filtered: list[dict[str, Any]] = []
    for position in positions:
        if symbol_normalized and str(position.get("symbol", "")).upper() != symbol_normalized:
            continue
        if include_zero or is_nonzero_position(position):
            filtered.append(position)
    return filtered


def format_positions_table(positions: list[dict[str, Any]]) -> str:
    if not positions:
        return "No futures positions to display."

    rows = []
    for position in positions:
        rows.append([str(position.get(field, "-")) for field in TABLE_FIELDS])

    widths = [len(field) for field in TABLE_FIELDS]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def fmt(row: list[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    header = fmt(TABLE_FIELDS)
    separator = "  ".join("-" * width for width in widths)
    body = "\n".join(fmt(row) for row in rows)
    return f"{header}\n{separator}\n{body}"


def render_positions(
    positions: list[dict[str, Any]],
    json_output: bool = False,
    include_zero: bool = False,
    symbol: str | None = None,
) -> str:
    if json_output:
        return json.dumps(positions, ensure_ascii=False, indent=2)
    return format_positions_table(filter_positions(positions, include_zero=include_zero, symbol=symbol))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List the current user's Binance futures positions from trading-tools JSON config."
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="print raw JSON response")
    parser.add_argument("--include-zero", action="store_true", help="include zero-size positions")
    parser.add_argument("--market", choices=sorted(MARKETS), help="override configured futures market: um or cm")
    parser.add_argument("--symbol", help="override configured symbol, for example BTCUSDT")
    parser.add_argument("--testnet", action="store_true", help="use Binance futures testnet for this run")
    parser.add_argument("--dry-run", action="store_true", help="print a redacted signed request without sending it")
    return parser


def main(argv: list[str] | None = None, stdout: Any = sys.stdout, stderr: Any = sys.stderr) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config()
        config = apply_overrides(config, market=args.market, symbol=args.symbol, testnet=args.testnet)
        signed_request = build_signed_request(config)

        if args.dry_run:
            payload = dry_run_payload(config, signed_request)
            if args.json_output:
                print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
            else:
                print(format_dry_run(payload), file=stdout)
            return 0

        raw_data = fetch_json(signed_request)
        positions = ensure_position_list(raw_data)
        table_symbol_filter = config.symbol if config.market == "cm" else None
        print(
            render_positions(
                positions,
                json_output=args.json_output,
                include_zero=args.include_zero,
                symbol=table_symbol_filter,
            ),
            file=stdout,
        )
        return 0
    except (ConfigError, BinanceAPIError) as exc:
        print(f"error: {exc}", file=stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
