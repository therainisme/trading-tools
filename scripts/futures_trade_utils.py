#!/usr/bin/env python3
"""Shared helpers for Binance USD-M futures trading scripts."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PUBLIC_ALLOWED_SYMBOLS = {"NVDAUSDT", "TSMUSDT", "MUUSDT", "AMDUSDT"}
DEFAULT_RECV_WINDOW = 5000
USD_M_BASE_URLS = {
    False: "https://fapi.binance.com",
    True: "https://demo-fapi.binance.com",
}
SIDE_VALUES = {"BUY", "SELL"}
POSITION_SIDE_VALUES = {"BOTH", "LONG", "SHORT"}
TIME_IN_FORCE_VALUES = {"GTC", "IOC", "FOK", "GTX", "GTD"}
WORKING_TYPE_VALUES = {"MARK_PRICE", "CONTRACT_PRICE"}
RESPONSE_TYPE_VALUES = {"ACK", "RESULT"}
CLIENT_ID_PATTERN = re.compile(r"^[\.A-Z\:/a-z0-9_-]{1,36}$")


class TradeConfigError(Exception):
    """Raised when trading-tools configuration is missing or invalid."""


class TradeValidationError(Exception):
    """Raised when a proposed trading action fails local validation."""


class TradeAPIError(Exception):
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
class SignedRequest:
    method: str
    base_url: str
    path: str
    query: str
    signature: str
    url: str
    headers: dict[str, str]


@dataclass(frozen=True)
class RequestPlan:
    tool: str
    method: str
    path: str
    params: tuple[tuple[str, str], ...]


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
    raise TradeConfigError("trading-tools config file was not found. Create one of:\n" f"{candidate_text}")


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TradeConfigError(f"invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise TradeConfigError(f"failed to read config file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TradeConfigError(f"config file {path} must contain a JSON object")
    return data


def _required_object(data: dict[str, Any], key: str, path: Path) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise TradeConfigError(f"config field '{key}' in {path} must be a JSON object")
    return value


def _required_non_empty_string(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TradeConfigError(f"config field 'binance.{key}' in {path} must be a non-empty string")
    return value.strip()


def parse_bool(value: Any, field_name: str, path: Path) -> bool:
    if isinstance(value, bool):
        return value
    raise TradeConfigError(f"config field '{field_name}' in {path} must be true or false")


def parse_positive_int(value: Any, field_name: str, path: Path) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise TradeConfigError(f"config field '{field_name}' in {path} must be a positive integer") from exc
    if parsed <= 0:
        raise TradeConfigError(f"config field '{field_name}' in {path} must be a positive integer")
    return parsed


def normalize_config_symbol(value: Any, path: Path) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return normalize_symbol(value, allow_none=True)
    raise TradeConfigError(f"config field 'binance.futures.symbol' in {path} must be a string or null")


def normalize_config(data: dict[str, Any], path: Path) -> BinanceFuturesConfig:
    binance = _required_object(data, "binance", path)
    futures = _required_object(binance, "futures", path)
    market = str(futures.get("market", "")).strip().lower()
    if market != "um":
        raise TradeConfigError("trading execution scripts currently support USD-M futures only: set binance.futures.market to 'um'")
    return BinanceFuturesConfig(
        api_key=_required_non_empty_string(binance, "api_key", path),
        api_secret=_required_non_empty_string(binance, "api_secret", path),
        market=market,
        testnet=parse_bool(futures.get("testnet", False), "binance.futures.testnet", path),
        recv_window=parse_positive_int(futures.get("recv_window", DEFAULT_RECV_WINDOW), "binance.futures.recv_window", path),
        symbol=normalize_config_symbol(futures.get("symbol"), path),
        config_path=path,
    )


def load_config(root: Path | None = None, home: Path | None = None) -> BinanceFuturesConfig:
    path = find_config_path(root=root, home=home)
    return normalize_config(load_json_file(path), path)


def normalize_symbol(symbol: str | None, allow_none: bool = False) -> str | None:
    if symbol is None:
        if allow_none:
            return None
        raise TradeValidationError("symbol is required")
    normalized = symbol.strip().upper()
    if not normalized:
        if allow_none:
            return None
        raise TradeValidationError("symbol is required")
    if any(char for char in normalized if not (char.isalnum() or char == "_")):
        raise TradeValidationError("symbol may contain only letters, digits, and underscores")
    return normalized


def enforce_symbol_whitelist(symbol: str, allowed_symbols: set[str] | None = None) -> None:
    allowed = allowed_symbols or PUBLIC_ALLOWED_SYMBOLS
    if symbol not in allowed:
        accepted = ", ".join(sorted(allowed))
        raise TradeValidationError(f"symbol {symbol} is outside the local trading whitelist: {accepted}")


def normalize_enum(value: str, accepted: set[str], field_name: str) -> str:
    normalized = value.strip().upper()
    if normalized not in accepted:
        raise TradeValidationError(f"{field_name} must be one of: {', '.join(sorted(accepted))}")
    return normalized


def normalize_client_id(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if not CLIENT_ID_PATTERN.fullmatch(normalized):
        raise TradeValidationError(f"{field_name} must match Binance client id rules")
    return normalized


def decimal_string(value: str | Decimal | int | float | None, field_name: str) -> str:
    if value is None:
        raise TradeValidationError(f"{field_name} is required")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TradeValidationError(f"{field_name} must be a decimal number") from exc
    if parsed <= 0:
        raise TradeValidationError(f"{field_name} must be greater than zero")
    text = format(parsed.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def optional_decimal_string(value: str | Decimal | int | float | None, field_name: str) -> str | None:
    if value is None:
        return None
    return decimal_string(value, field_name)


def bool_param(value: bool) -> str:
    return "true" if value else "false"


def current_timestamp_ms() -> int:
    return int(time.time() * 1000)


def sign_query(query: str, api_secret: str) -> str:
    return hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


def redacted_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "<redacted>"
    return f"{api_key[:4]}...{api_key[-4:]}"


def redacted_url(request: SignedRequest) -> str:
    return f"{request.base_url}{request.path}?{request.query}&signature=<redacted>"


def build_plan_hash(plan: RequestPlan) -> str:
    canonical = json.dumps(
        {
            "tool": plan.tool,
            "method": plan.method,
            "path": plan.path,
            "params": list(plan.params),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_signed_request(
    config: BinanceFuturesConfig,
    method: str,
    path: str,
    params: Iterable[tuple[str, str | int]],
    timestamp_ms: int | None = None,
    recv_window: int | None = None,
) -> SignedRequest:
    timestamp = timestamp_ms if timestamp_ms is not None else current_timestamp_ms()
    effective_recv_window = recv_window or config.recv_window
    signed_params = [(key, str(value)) for key, value in params]
    signed_params.append(("recvWindow", str(effective_recv_window)))
    signed_params.append(("timestamp", str(timestamp)))
    query = urlencode(signed_params)
    signature = sign_query(query, config.api_secret)
    base_url = USD_M_BASE_URLS[config.testnet]
    return SignedRequest(
        method=method.upper(),
        base_url=base_url,
        path=path,
        query=query,
        signature=signature,
        url=f"{base_url}{path}?{query}&signature={signature}",
        headers={"X-MBX-APIKEY": config.api_key},
    )


def request_preview(
    config: BinanceFuturesConfig,
    plan: RequestPlan,
    request: SignedRequest,
    mode: str,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "plan_hash": build_plan_hash(plan),
        "config_path": str(config.config_path) if config.config_path else None,
        "testnet": config.testnet,
        "method": request.method,
        "base_url": request.base_url,
        "path": request.path,
        "params": [{"name": key, "value": value} for key, value in plan.params],
        "query": request.query,
        "url": redacted_url(request),
        "headers": {"X-MBX-APIKEY": redacted_api_key(config.api_key)},
        "signature": "<redacted>",
    }


def require_live_confirmation(mode: str, plan_hash: str, confirm_plan_hash: str | None, confirm: str | None) -> None:
    if mode != "live":
        return
    if confirm != "LIVE":
        raise TradeValidationError("live mode requires --confirm LIVE")
    if confirm_plan_hash != plan_hash:
        raise TradeValidationError("live mode requires --confirm-plan-hash matching the dry-run plan_hash")


def fetch_json(request: SignedRequest, opener: Callable[..., Any] = urlopen, timeout: int = 15) -> Any:
    req = Request(
        request.url,
        data=b"" if request.method in {"POST", "DELETE"} else None,
        headers={"User-Agent": "trading-tools/1.0", **request.headers},
        method=request.method,
    )
    try:
        with opener(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise TradeAPIError(f"Binance API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise TradeAPIError(f"Binance API request failed: {exc}") from exc
    except OSError as exc:
        raise TradeAPIError(f"Binance API request failed: {exc}") from exc
    if not body.strip():
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise TradeAPIError(f"Binance API returned invalid JSON: {exc}") from exc
