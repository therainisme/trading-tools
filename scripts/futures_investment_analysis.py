#!/usr/bin/env python3
"""Fetch Binance USD-M futures investment-analysis datasets."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import time
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from http_transport import ProxyConfigError, urlopen_with_env_proxy  # noqa: E402


PUBLIC_BASE_URL = "https://fapi.binance.com"
SIGNED_BASE_URLS = {
    False: "https://fapi.binance.com",
    True: "https://demo-fapi.binance.com",
}
DEFAULT_RECV_WINDOW = 5000
DEFAULT_PERIOD = "1h"
DEFAULT_LIMIT = 30
DEFAULT_DEPTH_LIMIT = 20
DEFAULT_AGG_TRADES_LIMIT = 100
DEFAULT_INCOME_LIMIT = 100
GROUPS = {"valuation", "positioning", "sentiment", "liquidity", "account-risk"}
PERIODS = {"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}
DEPTH_LIMITS = {5, 10, 20, 50, 100, 500, 1000}


class AnalysisError(Exception):
    """Raised when investment-analysis data fetching fails."""


class ConfigError(Exception):
    """Raised when trading-tools configuration is missing or invalid."""


@dataclass(frozen=True)
class BinanceCredentials:
    api_key: str
    api_secret: str
    recv_window: int = DEFAULT_RECV_WINDOW
    testnet: bool = False
    config_path: Path | None = None


@dataclass(frozen=True)
class EndpointSpec:
    name: str
    group: str
    method: str
    path: str
    params: list[tuple[str, str | int]] = field(default_factory=list)
    signed: bool = False


@dataclass(frozen=True)
class SignedRequest:
    method: str
    base_url: str
    path: str
    query: str
    signature: str
    url: str
    headers: dict[str, str]


@dataclass(frozen=True)
class AnalysisOptions:
    symbol: str
    groups: tuple[str, ...] = ("valuation", "positioning", "sentiment", "liquidity")
    period: str = DEFAULT_PERIOD
    limit: int = DEFAULT_LIMIT
    depth_limit: int = DEFAULT_DEPTH_LIMIT
    agg_trades_limit: int = DEFAULT_AGG_TRADES_LIMIT
    income_limit: int = DEFAULT_INCOME_LIMIT
    start_time: int | None = None
    end_time: int | None = None
    income_type: str | None = None
    recv_window: int | None = None
    testnet: bool = False
    json_output: bool = False
    dry_run: bool = False


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
    for path in config_candidates(root=root, home=home):
        if path.is_file():
            return path
    paths = "\n".join(f"  - {path}" for path in config_candidates(root=root, home=home))
    raise ConfigError("trading-tools config file was not found. Create one of:\n" + paths)


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


def parse_positive_int(value: Any, field_name: str, path: Path) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"config field '{field_name}' in {path} must be a positive integer") from exc
    if parsed <= 0:
        raise ConfigError(f"config field '{field_name}' in {path} must be a positive integer")
    return parsed


def load_credentials(root: Path | None = None, home: Path | None = None) -> BinanceCredentials:
    path = find_config_path(root=root, home=home)
    data = load_json_file(path)
    binance = _required_object(data, "binance", path)
    futures = _required_object(binance, "futures", path)
    return BinanceCredentials(
        api_key=_required_non_empty_string(binance, "api_key", path),
        api_secret=_required_non_empty_string(binance, "api_secret", path),
        recv_window=parse_positive_int(
            futures.get("recv_window", DEFAULT_RECV_WINDOW), "binance.futures.recv_window", path
        ),
        testnet=parse_bool(futures.get("testnet", False), "binance.futures.testnet", path),
        config_path=path,
    )


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise AnalysisError("symbol must be a non-empty string")
    if any(char for char in normalized if not (char.isalnum() or char == "_")):
        raise AnalysisError("symbol may contain only letters, digits, and underscores")
    return normalized


def parse_groups(value: str) -> tuple[str, ...]:
    groups = tuple(dict.fromkeys(part.strip().lower() for part in value.split(",") if part.strip()))
    if not groups:
        raise AnalysisError("groups must include at least one value")
    invalid = [group for group in groups if group not in GROUPS]
    if invalid:
        raise AnalysisError(f"groups must contain only: {', '.join(sorted(GROUPS))}")
    return groups


def validate_period(period: str) -> str:
    if period not in PERIODS:
        raise AnalysisError(f"period must be one of: {', '.join(sorted(PERIODS))}")
    return period


def validate_positive_limit(value: int, name: str, maximum: int) -> int:
    if value < 1 or value > maximum:
        raise AnalysisError(f"{name} must be between 1 and {maximum}")
    return value


def validate_depth_limit(value: int) -> int:
    if value not in DEPTH_LIMITS:
        raise AnalysisError(f"depth limit must be one of: {', '.join(str(item) for item in sorted(DEPTH_LIMITS))}")
    return value


def current_timestamp_ms() -> int:
    return int(time.time() * 1000)


def add_time_window(
    params: list[tuple[str, str | int]], start_time: int | None, end_time: int | None
) -> list[tuple[str, str | int]]:
    updated = list(params)
    if start_time is not None:
        updated.append(("startTime", start_time))
    if end_time is not None:
        updated.append(("endTime", end_time))
    return updated


def build_endpoint_specs(options: AnalysisOptions) -> list[EndpointSpec]:
    symbol = normalize_symbol(options.symbol)
    period = validate_period(options.period)
    limit = validate_positive_limit(options.limit, "limit", 500)
    depth_limit = validate_depth_limit(options.depth_limit)
    agg_trades_limit = validate_positive_limit(options.agg_trades_limit, "agg-trades-limit", 1000)
    income_limit = validate_positive_limit(options.income_limit, "income-limit", 1000)

    specs: list[EndpointSpec] = []
    historical_params = [("symbol", symbol), ("period", period), ("limit", limit)]
    historical_params = add_time_window(historical_params, options.start_time, options.end_time)

    if "valuation" in options.groups:
        specs.extend(
            [
                EndpointSpec("premium_index", "valuation", "GET", "/fapi/v1/premiumIndex", [("symbol", symbol)]),
                EndpointSpec(
                    "funding_rate",
                    "valuation",
                    "GET",
                    "/fapi/v1/fundingRate",
                    add_time_window([("symbol", symbol), ("limit", limit)], options.start_time, options.end_time),
                ),
            ]
        )

    if "positioning" in options.groups:
        specs.extend(
            [
                EndpointSpec("open_interest", "positioning", "GET", "/fapi/v1/openInterest", [("symbol", symbol)]),
                EndpointSpec("open_interest_history", "positioning", "GET", "/futures/data/openInterestHist", historical_params),
            ]
        )

    if "sentiment" in options.groups:
        specs.extend(
            [
                EndpointSpec("global_long_short_account_ratio", "sentiment", "GET", "/futures/data/globalLongShortAccountRatio", historical_params),
                EndpointSpec("top_trader_long_short_account_ratio", "sentiment", "GET", "/futures/data/topLongShortAccountRatio", historical_params),
                EndpointSpec("top_trader_long_short_position_ratio", "sentiment", "GET", "/futures/data/topLongShortPositionRatio", historical_params),
                EndpointSpec("taker_buy_sell_volume", "sentiment", "GET", "/futures/data/takerlongshortRatio", historical_params),
            ]
        )

    if "liquidity" in options.groups:
        specs.extend(
            [
                EndpointSpec("order_book_depth", "liquidity", "GET", "/fapi/v1/depth", [("symbol", symbol), ("limit", depth_limit)]),
                EndpointSpec("book_ticker", "liquidity", "GET", "/fapi/v1/ticker/bookTicker", [("symbol", symbol)]),
                EndpointSpec(
                    "aggregate_trades",
                    "liquidity",
                    "GET",
                    "/fapi/v1/aggTrades",
                    add_time_window([("symbol", symbol), ("limit", agg_trades_limit)], options.start_time, options.end_time),
                ),
            ]
        )

    if "account-risk" in options.groups:
        income_params: list[tuple[str, str | int]] = [("symbol", symbol), ("limit", income_limit)]
        if options.income_type:
            income_params.append(("incomeType", options.income_type.strip().upper()))
        income_params = add_time_window(income_params, options.start_time, options.end_time)
        specs.extend(
            [
                EndpointSpec("account_information", "account-risk", "GET", "/fapi/v3/account", signed=True),
                EndpointSpec("account_balance", "account-risk", "GET", "/fapi/v3/balance", signed=True),
                EndpointSpec("leverage_bracket", "account-risk", "GET", "/fapi/v1/leverageBracket", [("symbol", symbol)], signed=True),
                EndpointSpec("income_history", "account-risk", "GET", "/fapi/v1/income", income_params, signed=True),
            ]
        )

    return specs


def build_public_url(spec: EndpointSpec) -> str:
    query = urlencode(spec.params)
    if query:
        return f"{PUBLIC_BASE_URL}{spec.path}?{query}"
    return f"{PUBLIC_BASE_URL}{spec.path}"


def sign_query(query: str, api_secret: str) -> str:
    return hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


def build_signed_request(
    spec: EndpointSpec,
    credentials: BinanceCredentials,
    timestamp_ms: int | None = None,
    recv_window: int | None = None,
    testnet: bool = False,
) -> SignedRequest:
    timestamp = timestamp_ms if timestamp_ms is not None else current_timestamp_ms()
    effective_recv_window = recv_window or credentials.recv_window
    params = list(spec.params) + [("recvWindow", effective_recv_window), ("timestamp", timestamp)]
    query = urlencode(params)
    signature = sign_query(query, credentials.api_secret)
    base_url = SIGNED_BASE_URLS[testnet or credentials.testnet]
    signed_query = f"{query}&signature={signature}"
    return SignedRequest(
        method=spec.method,
        base_url=base_url,
        path=spec.path,
        query=query,
        signature=signature,
        url=f"{base_url}{spec.path}?{signed_query}",
        headers={"X-MBX-APIKEY": credentials.api_key},
    )


def fetch_json(
    url: str,
    headers: dict[str, str] | None = None,
    opener: Callable[..., Any] | None = None,
    timeout: int = 15,
) -> Any:
    request = Request(url, headers={"User-Agent": "trading-tools/1.0", **(headers or {})}, method="GET")
    http_open = opener or urlopen_with_env_proxy
    try:
        with http_open(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except ProxyConfigError as exc:
        raise AnalysisError(f"proxy configuration error: {exc}") from exc
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise AnalysisError(f"Binance API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise AnalysisError(f"Binance API request failed: {exc}") from exc
    except OSError as exc:
        raise AnalysisError(f"Binance API request failed: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise AnalysisError(f"Binance API returned invalid JSON: {exc}") from exc


def redact_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "<redacted>"
    return f"{api_key[:4]}...{api_key[-4:]}"


def redacted_url(request: SignedRequest) -> str:
    return f"{request.base_url}{request.path}?{request.query}&signature=<redacted>"


def request_preview(
    spec: EndpointSpec,
    credentials: BinanceCredentials | None = None,
    timestamp_ms: int | None = None,
    recv_window: int | None = None,
    testnet: bool = False,
) -> dict[str, Any]:
    if spec.signed:
        if credentials is None:
            raise ConfigError("signed endpoint preview requires Binance credentials")
        request = build_signed_request(spec, credentials, timestamp_ms=timestamp_ms, recv_window=recv_window, testnet=testnet)
        return {
            "name": spec.name,
            "group": spec.group,
            "signed": True,
            "method": request.method,
            "base_url": request.base_url,
            "path": request.path,
            "query": request.query,
            "url": redacted_url(request),
            "headers": {"X-MBX-APIKEY": redact_api_key(credentials.api_key)},
            "signature": "<redacted>",
        }
    return {
        "name": spec.name,
        "group": spec.group,
        "signed": False,
        "method": spec.method,
        "url": build_public_url(spec),
    }


def collect_analysis(
    options: AnalysisOptions,
    credentials: BinanceCredentials | None = None,
    opener: Callable[..., Any] | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    specs = build_endpoint_specs(options)
    if any(spec.signed for spec in specs) and credentials is None:
        credentials = load_credentials()
    if credentials is not None and options.recv_window is not None:
        credentials = replace(credentials, recv_window=validate_positive_limit(options.recv_window, "recv-window", 60000))

    metadata = {
        "symbol": normalize_symbol(options.symbol),
        "groups": list(options.groups),
        "period": options.period,
        "limit": options.limit,
        "start_time": options.start_time,
        "end_time": options.end_time,
        "testnet": bool(options.testnet or (credentials.testnet if credentials else False)),
    }

    if options.dry_run:
        return {
            "metadata": metadata,
            "dry_run": True,
            "requests": [
                request_preview(
                    spec,
                    credentials=credentials,
                    recv_window=options.recv_window,
                    testnet=options.testnet,
                )
                for spec in specs
            ],
        }

    data: dict[str, Any] = {}
    for spec in specs:
        if spec.signed:
            if credentials is None:
                raise ConfigError("signed endpoint requires Binance credentials")
            request = build_signed_request(
                spec,
                credentials,
                recv_window=options.recv_window,
                testnet=options.testnet,
            )
            data[spec.name] = fetch_json(request.url, headers=request.headers, opener=opener, timeout=timeout)
        else:
            data[spec.name] = fetch_json(build_public_url(spec), opener=opener, timeout=timeout)

    return {"metadata": metadata, "dry_run": False, "data": data}


def decimal_value(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def latest_item(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list) and value and isinstance(value[-1], dict):
        return value[-1]
    if isinstance(value, dict):
        return value
    return None


def fmt_decimal(value: Any, places: int = 4) -> str:
    parsed = decimal_value(value)
    if parsed is None:
        return "-"
    quant = Decimal(10) ** -places
    formatted = format(parsed.quantize(quant), "f").rstrip("0").rstrip(".")
    return formatted or "0"


def format_summary(payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata", {})
    lines = [f"Investment analysis for {metadata.get('symbol', '-')} ({', '.join(metadata.get('groups', []))})"]
    if payload.get("dry_run"):
        lines.append("Dry run: requests were not sent.")
        for item in payload.get("requests", []):
            lines.append(f"- {item['group']} {item['name']}: {item.get('url')}")
        return "\n".join(lines)

    data = payload.get("data", {})
    premium = latest_item(data.get("premium_index"))
    if premium:
        lines.append(
            "Premium/mark: "
            f"mark={fmt_decimal(premium.get('markPrice'))} "
            f"index={fmt_decimal(premium.get('indexPrice'))} "
            f"funding={fmt_decimal(premium.get('lastFundingRate'), 8)}"
        )

    funding = latest_item(data.get("funding_rate"))
    if funding:
        lines.append(
            "Latest funding: "
            f"rate={fmt_decimal(funding.get('fundingRate'), 8)} "
            f"mark={fmt_decimal(funding.get('markPrice'))}"
        )

    open_interest = latest_item(data.get("open_interest"))
    if open_interest:
        lines.append(f"Open interest: {fmt_decimal(open_interest.get('openInterest'), 4)}")

    open_interest_hist = latest_item(data.get("open_interest_history"))
    if open_interest_hist:
        lines.append(
            "Open interest history latest: "
            f"qty={fmt_decimal(open_interest_hist.get('sumOpenInterest'), 4)} "
            f"value={fmt_decimal(open_interest_hist.get('sumOpenInterestValue'), 2)}"
        )

    for key, label in [
        ("global_long_short_account_ratio", "Global long/short"),
        ("top_trader_long_short_account_ratio", "Top trader account long/short"),
        ("top_trader_long_short_position_ratio", "Top trader position long/short"),
    ]:
        item = latest_item(data.get(key))
        if item:
            lines.append(
                f"{label}: ratio={fmt_decimal(item.get('longShortRatio'), 4)} "
                f"long={fmt_decimal(item.get('longAccount'), 4)} short={fmt_decimal(item.get('shortAccount'), 4)}"
            )

    taker = latest_item(data.get("taker_buy_sell_volume"))
    if taker:
        lines.append(
            "Taker flow: "
            f"buy={fmt_decimal(taker.get('buyVol'), 4)} "
            f"sell={fmt_decimal(taker.get('sellVol'), 4)} "
            f"ratio={fmt_decimal(taker.get('buySellRatio'), 4)}"
        )

    ticker = latest_item(data.get("book_ticker"))
    if ticker:
        lines.append(
            "Book ticker: "
            f"bid={fmt_decimal(ticker.get('bidPrice'))} x {fmt_decimal(ticker.get('bidQty'))} "
            f"ask={fmt_decimal(ticker.get('askPrice'))} x {fmt_decimal(ticker.get('askQty'))}"
        )

    depth = data.get("order_book_depth")
    if isinstance(depth, dict):
        bids = depth.get("bids") if isinstance(depth.get("bids"), list) else []
        asks = depth.get("asks") if isinstance(depth.get("asks"), list) else []
        if bids and asks:
            lines.append(f"Depth top: bid={bids[0][0]} x {bids[0][1]} ask={asks[0][0]} x {asks[0][1]}")

    account = data.get("account_information")
    if isinstance(account, dict):
        lines.append(
            "Account risk: "
            f"wallet={fmt_decimal(account.get('totalWalletBalance'), 4)} "
            f"margin={fmt_decimal(account.get('totalMarginBalance'), 4)} "
            f"unrealized={fmt_decimal(account.get('totalUnrealizedProfit'), 4)}"
        )

    balance = data.get("account_balance")
    if isinstance(balance, list):
        nonzero = []
        for item in balance:
            if not isinstance(item, dict):
                continue
            bal = decimal_value(item.get("balance")) or Decimal("0")
            if bal != 0:
                nonzero.append(f"{item.get('asset')}={fmt_decimal(item.get('balance'), 4)}")
        if nonzero:
            lines.append("Balances: " + ", ".join(nonzero[:6]))

    income = data.get("income_history")
    if isinstance(income, list):
        lines.append(f"Income rows: {len(income)}")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch Binance USD-M futures investment-analysis datasets.")
    parser.add_argument("--symbol", required=True, help="required futures symbol, for example NVDAUSDT")
    parser.add_argument("--groups", default="valuation,positioning,sentiment,liquidity", help="comma-separated groups: valuation,positioning,sentiment,liquidity,account-risk")
    parser.add_argument("--period", default=DEFAULT_PERIOD, help=f"statistics period, default: {DEFAULT_PERIOD}")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"historical rows for valuation, positioning, and sentiment datasets, default: {DEFAULT_LIMIT}")
    parser.add_argument("--depth-limit", type=int, default=DEFAULT_DEPTH_LIMIT, help=f"order book depth limit, default: {DEFAULT_DEPTH_LIMIT}")
    parser.add_argument("--agg-trades-limit", type=int, default=DEFAULT_AGG_TRADES_LIMIT, help=f"aggregate trades limit, default: {DEFAULT_AGG_TRADES_LIMIT}")
    parser.add_argument("--income-limit", type=int, default=DEFAULT_INCOME_LIMIT, help=f"income history limit, default: {DEFAULT_INCOME_LIMIT}")
    parser.add_argument("--start-time", type=int, help="optional historical window start time in milliseconds")
    parser.add_argument("--end-time", type=int, help="optional historical window end time in milliseconds")
    parser.add_argument("--income-type", help="optional Binance income type filter, for example FUNDING_FEE")
    parser.add_argument("--recv-window", type=int, help="override signed request recvWindow in milliseconds")
    parser.add_argument("--testnet", action="store_true", help="use USD-M futures testnet for signed account-risk endpoints")
    parser.add_argument("--json", action="store_true", dest="json_output", help="print full JSON payload")
    parser.add_argument("--dry-run", action="store_true", help="print request plan without sending requests")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    return parser


def options_from_args(args: argparse.Namespace) -> AnalysisOptions:
    return AnalysisOptions(
        symbol=args.symbol,
        groups=parse_groups(args.groups),
        period=validate_period(args.period),
        limit=validate_positive_limit(args.limit, "limit", 500),
        depth_limit=validate_depth_limit(args.depth_limit),
        agg_trades_limit=validate_positive_limit(args.agg_trades_limit, "agg-trades-limit", 1000),
        income_limit=validate_positive_limit(args.income_limit, "income-limit", 1000),
        start_time=args.start_time,
        end_time=args.end_time,
        income_type=args.income_type,
        recv_window=args.recv_window,
        testnet=args.testnet,
        json_output=args.json_output,
        dry_run=args.dry_run,
    )


def main(argv: list[str] | None = None, stdout: Any = sys.stdout, stderr: Any = sys.stderr) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        options = options_from_args(args)
        payload = collect_analysis(options, timeout=args.timeout)
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
        else:
            print(format_summary(payload), file=stdout)
        return 0
    except (AnalysisError, ConfigError) as exc:
        print(f"error: {exc}", file=stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
