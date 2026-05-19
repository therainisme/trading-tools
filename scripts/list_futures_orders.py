#!/usr/bin/env python3
"""List Binance futures open orders, conditional orders, order history, or account trades.

Configuration is read from JSON only:
1. <skill-root>/.trading-tools/config.json
2. ~/.trading-tools/config.json
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from http_transport import ProxyConfigError, urlopen_with_env_proxy  # noqa: E402


MARKETS = {"um", "cm"}
KINDS = {"open", "history", "trades", "conditional-open", "conditional-history"}
CONDITIONAL_KINDS = {"conditional-open", "conditional-history"}
DEFAULT_RECV_WINDOW = 5000
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
ORDER_PATHS = {
    ("um", "open"): "/fapi/v1/openOrders",
    ("um", "history"): "/fapi/v1/allOrders",
    ("um", "trades"): "/fapi/v1/userTrades",
    ("um", "conditional-open"): "/fapi/v1/openAlgoOrders",
    ("um", "conditional-history"): "/fapi/v1/allAlgoOrders",
    ("cm", "open"): "/dapi/v1/openOrders",
    ("cm", "history"): "/dapi/v1/allOrders",
    ("cm", "trades"): "/dapi/v1/userTrades",
}
BASE_URLS = {
    ("um", False): "https://fapi.binance.com",
    ("um", True): "https://demo-fapi.binance.com",
    ("cm", False): "https://dapi.binance.com",
    ("cm", True): "https://testnet.binancefuture.com",
}
OPEN_ORDER_FIELDS = [
    "symbol",
    "orderId",
    "side",
    "positionSide",
    "type",
    "status",
    "price",
    "origQty",
    "executedQty",
    "reduceOnly",
    "timeInForce",
    "time",
]
HISTORY_ORDER_FIELDS = [
    "symbol",
    "orderId",
    "side",
    "positionSide",
    "type",
    "status",
    "avgPrice",
    "price",
    "origQty",
    "executedQty",
    "time",
]
TRADE_FIELDS = [
    "symbol",
    "id",
    "orderId",
    "side",
    "positionSide",
    "price",
    "qty",
    "quoteQty",
    "realizedPnl",
    "commission",
    "commissionAsset",
    "time",
]
CONDITIONAL_ORDER_FIELDS = [
    "symbol",
    "algoId",
    "algoType",
    "orderType",
    "side",
    "positionSide",
    "algoStatus",
    "quantity",
    "triggerPrice",
    "price",
    "actualOrderId",
    "actualQty",
    "actualPrice",
    "workingType",
    "closePosition",
    "reduceOnly",
    "createTime",
    "updateTime",
    "triggerTime",
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


@dataclass(frozen=True)
class OrderRequestOptions:
    kind: str = "open"
    market: str | None = None
    symbol: str | None = None
    pair: str | None = None
    order_id: int | None = None
    algo_id: int | None = None
    algo_type: str | None = None
    start_time: int | None = None
    end_time: int | None = None
    limit: int = DEFAULT_LIMIT
    include_empty_symbol: bool = False
    testnet: bool = False


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
    raise ConfigError("trading-tools config file was not found. Create one of:\n" f"{candidate_text}")


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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
        raise ConfigError("config field 'binance.futures.recv_window' in " f"{path} must be a positive integer") from exc
    if recv_window <= 0:
        raise ConfigError("config field 'binance.futures.recv_window' in " f"{path} must be a positive integer")
    return recv_window


def normalize_config_symbol(value: Any, path: Path) -> str | None:
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

    return BinanceFuturesConfig(
        api_key=api_key,
        api_secret=api_secret,
        market=market,
        testnet=parse_bool(futures.get("testnet", False), "binance.futures.testnet", path),
        recv_window=parse_recv_window(futures.get("recv_window", DEFAULT_RECV_WINDOW), path),
        symbol=normalize_config_symbol(futures.get("symbol"), path),
        config_path=path,
    )


def load_config(root: Path | None = None, home: Path | None = None) -> BinanceFuturesConfig:
    path = find_config_path(root=root, home=home)
    return normalize_config(load_json_file(path), path)


def normalize_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    normalized = symbol.strip().upper()
    if not normalized:
        return None
    if any(char for char in normalized if not (char.isalnum() or char == "_")):
        raise ConfigError("symbol may contain only letters, digits, and underscores")
    return normalized


def normalize_pair(pair: str | None) -> str | None:
    if pair is None:
        return None
    normalized = pair.strip().upper()
    if not normalized:
        return None
    if any(char for char in normalized if not (char.isalnum() or char == "_")):
        raise ConfigError("pair may contain only letters, digits, and underscores")
    return normalized


def apply_overrides(config: BinanceFuturesConfig, options: OrderRequestOptions) -> BinanceFuturesConfig:
    changes: dict[str, Any] = {}
    if options.market is not None:
        market = options.market.strip().lower()
        if market not in MARKETS:
            raise ConfigError("--market must be 'um' or 'cm'")
        changes["market"] = market
    if options.symbol is not None:
        changes["symbol"] = normalize_symbol(options.symbol)
    if options.testnet:
        changes["testnet"] = True
    return replace(config, **changes)


def validate_kind(kind: str) -> str:
    normalized = kind.strip().lower()
    if normalized not in KINDS:
        raise ConfigError(f"--kind must be one of: {', '.join(sorted(KINDS))}")
    return normalized


def validate_market_kind(market: str, kind: str) -> None:
    if (market, kind) in ORDER_PATHS:
        return
    if kind in CONDITIONAL_KINDS:
        raise ConfigError("conditional order queries currently support --market um")
    raise ConfigError(f"unsupported market/kind combination: market={market}, kind={kind}")


def validate_limit(limit: int) -> int:
    if limit < 1 or limit > MAX_LIMIT:
        raise ConfigError(f"--limit must be between 1 and {MAX_LIMIT}")
    return limit


def validate_time_window(start_time: int | None, end_time: int | None) -> None:
    if start_time is not None and start_time < 0:
        raise ConfigError("--start-time must be a non-negative millisecond timestamp")
    if end_time is not None and end_time < 0:
        raise ConfigError("--end-time must be a non-negative millisecond timestamp")
    if start_time is not None and end_time is not None and start_time > end_time:
        raise ConfigError("--start-time must be less than or equal to --end-time")


def validate_non_negative_id(value: int, option_name: str) -> int:
    if value < 0:
        raise ConfigError(f"{option_name} must be a non-negative integer")
    return value


def normalize_algo_type(algo_type: str | None) -> str | None:
    if algo_type is None:
        return None
    normalized = algo_type.strip().upper()
    if not normalized:
        return None
    if any(char for char in normalized if not (char.isalnum() or char == "_")):
        raise ConfigError("algo type may contain only letters, digits, and underscores")
    return normalized


def current_timestamp_ms() -> int:
    return int(time.time() * 1000)


def build_order_params(config: BinanceFuturesConfig, options: OrderRequestOptions, timestamp_ms: int) -> list[tuple[str, str]]:
    kind = validate_kind(options.kind)
    validate_market_kind(config.market, kind)
    limit = validate_limit(options.limit)
    validate_time_window(options.start_time, options.end_time)

    symbol = normalize_symbol(options.symbol) if options.symbol is not None else config.symbol
    pair = normalize_pair(options.pair)
    algo_type = normalize_algo_type(options.algo_type)
    params: list[tuple[str, str]] = []

    if kind == "open":
        if symbol:
            params.append(("symbol", symbol))
        elif pair and config.market == "cm":
            params.append(("pair", pair))
        elif config.market == "cm" and not options.include_empty_symbol:
            raise ConfigError("COIN-M open order queries require --symbol, --pair, or --all-symbols")
    elif kind == "conditional-open":
        if symbol:
            params.append(("symbol", symbol))
        elif not options.include_empty_symbol:
            raise ConfigError("--symbol is required for conditional-open unless --all-symbols is set")
        if algo_type:
            params.append(("algoType", algo_type))
        if options.algo_id is not None:
            params.append(("algoId", str(validate_non_negative_id(options.algo_id, "--algo-id"))))
        if options.order_id is not None:
            raise ConfigError("--algo-id is used for conditional order queries")
    elif kind == "conditional-history":
        if not symbol:
            raise ConfigError("--symbol is required when --kind is conditional-history")
        params.append(("symbol", symbol))
        if algo_type:
            raise ConfigError("--algo-type is used with --kind conditional-open")
        if options.algo_id is not None:
            params.append(("algoId", str(validate_non_negative_id(options.algo_id, "--algo-id"))))
        if options.order_id is not None:
            raise ConfigError("--algo-id is used for conditional order queries")
    else:
        if not symbol:
            raise ConfigError("--symbol is required when --kind is history or trades")
        params.append(("symbol", symbol))

    if options.order_id is not None:
        if kind not in {"history", "trades"}:
            raise ConfigError("--order-id is used with --kind history or trades")
        validate_non_negative_id(options.order_id, "--order-id")
        params.append(("orderId", str(options.order_id)))
    if kind in {"history", "trades", "conditional-history"}:
        if options.start_time is not None:
            params.append(("startTime", str(options.start_time)))
        if options.end_time is not None:
            params.append(("endTime", str(options.end_time)))
        params.append(("limit", str(limit)))
    params.append(("recvWindow", str(config.recv_window)))
    params.append(("timestamp", str(timestamp_ms)))
    return params


def sign_query(query: str, api_secret: str) -> str:
    return hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


def build_signed_request(
    config: BinanceFuturesConfig,
    options: OrderRequestOptions,
    timestamp_ms: int | None = None,
) -> SignedRequest:
    timestamp = timestamp_ms if timestamp_ms is not None else current_timestamp_ms()
    kind = validate_kind(options.kind)
    validate_market_kind(config.market, kind)
    base_url = BASE_URLS[(config.market, config.testnet)]
    path = ORDER_PATHS[(config.market, kind)]
    query = urlencode(build_order_params(config, options, timestamp))
    signature = sign_query(query, config.api_secret)
    signed_query = f"{query}&signature={signature}"
    return SignedRequest(
        method="GET",
        base_url=base_url,
        path=path,
        query=query,
        signature=signature,
        url=f"{base_url}{path}?{signed_query}",
        headers={"X-MBX-APIKEY": config.api_key},
    )


def redact_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "<redacted>"
    return f"{api_key[:4]}...{api_key[-4:]}"


def redacted_url(request: SignedRequest) -> str:
    return f"{request.base_url}{request.path}?{request.query}&signature=<redacted>"


def dry_run_payload(config: BinanceFuturesConfig, options: OrderRequestOptions, request: SignedRequest) -> dict[str, Any]:
    return {
        "config_path": str(config.config_path) if config.config_path else None,
        "market": config.market,
        "testnet": config.testnet,
        "kind": validate_kind(options.kind),
        "method": request.method,
        "base_url": request.base_url,
        "path": request.path,
        "query": request.query,
        "url": redacted_url(request),
        "headers": {"X-MBX-APIKEY": redact_api_key(config.api_key)},
        "signature": "<redacted>",
    }


def fetch_json(
    request: SignedRequest,
    opener: Callable[..., Any] | None = None,
    timeout: int = 15,
) -> Any:
    req = Request(request.url, headers={"User-Agent": "trading-tools/1.0", **request.headers}, method=request.method)
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


def ensure_list(data: Any, kind: str) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise BinanceAPIError(f"Binance {kind} response must be a JSON array")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise BinanceAPIError(f"Binance {kind} response item {index} must be a JSON object")
        rows.append(item)
    return rows


def fields_for_kind(kind: str) -> list[str]:
    if kind == "open":
        return OPEN_ORDER_FIELDS
    if kind == "history":
        return HISTORY_ORDER_FIELDS
    if kind in CONDITIONAL_KINDS:
        return CONDITIONAL_ORDER_FIELDS
    return TRADE_FIELDS


def format_table(rows: list[dict[str, Any]], kind: str) -> str:
    if not rows:
        return f"No futures {kind} records to display."
    fields = fields_for_kind(kind)
    table_rows = [[str(row.get(field, "-")) for field in fields] for row in rows]
    widths = [len(field) for field in fields]
    for row in table_rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def fmt(row: list[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    header = fmt(fields)
    separator = "  ".join("-" * width for width in widths)
    body = "\n".join(fmt(row) for row in table_rows)
    return f"{header}\n{separator}\n{body}"


def render_orders(rows: list[dict[str, Any]], kind: str, json_output: bool = False) -> str:
    if json_output:
        return json.dumps(rows, ensure_ascii=False, indent=2)
    return format_table(rows, kind)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List Binance futures open orders, conditional orders, order history, or account trades.")
    parser.add_argument(
        "--kind",
        choices=sorted(KINDS),
        default="open",
        help="record type to fetch: open, history, trades, conditional-open, or conditional-history",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="print raw JSON response")
    parser.add_argument("--market", choices=sorted(MARKETS), help="override configured futures market: um or cm")
    parser.add_argument("--symbol", help="override configured symbol, for example NVDAUSDT")
    parser.add_argument("--pair", help="COIN-M pair filter for open orders, for example BTCUSD")
    parser.add_argument("--all-symbols", action="store_true", help="allow open order queries without a symbol when supported")
    parser.add_argument("--order-id", type=int, help="filter history or trades by order id")
    parser.add_argument("--algo-id", type=int, help="filter conditional orders by Binance algoId")
    parser.add_argument("--algo-type", help="conditional order algo type filter, for example CONDITIONAL")
    parser.add_argument("--start-time", type=int, help="history/trades/conditional-history window start time in milliseconds")
    parser.add_argument("--end-time", type=int, help="history/trades/conditional-history window end time in milliseconds")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"history/trades/conditional-history row limit, default: {DEFAULT_LIMIT}")
    parser.add_argument("--testnet", action="store_true", help="use Binance futures testnet for this run")
    parser.add_argument("--dry-run", action="store_true", help="print a redacted signed request without sending it")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    return parser


def options_from_args(args: argparse.Namespace) -> OrderRequestOptions:
    return OrderRequestOptions(
        kind=args.kind,
        market=args.market,
        symbol=args.symbol,
        pair=args.pair,
        order_id=args.order_id,
        algo_id=args.algo_id,
        algo_type=args.algo_type,
        start_time=args.start_time,
        end_time=args.end_time,
        limit=args.limit,
        include_empty_symbol=args.all_symbols,
        testnet=args.testnet,
    )


def main(argv: list[str] | None = None, stdout: Any = sys.stdout, stderr: Any = sys.stderr) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        options = options_from_args(args)
        config = apply_overrides(load_config(), options)
        request = build_signed_request(config, options)
        if args.dry_run:
            payload = dry_run_payload(config, options, request)
            if args.json_output:
                print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
            else:
                print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
            return 0
        data = fetch_json(request, timeout=args.timeout)
        rows = ensure_list(data, validate_kind(options.kind))
        print(render_orders(rows, validate_kind(options.kind), json_output=args.json_output), file=stdout)
        return 0
    except (ConfigError, BinanceAPIError) as exc:
        print(f"error: {exc}", file=stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
