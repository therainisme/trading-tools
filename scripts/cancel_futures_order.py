#!/usr/bin/env python3
"""Prepare or cancel a Binance USD-M futures standard or conditional order.

Default mode is dry-run. Live cancellations require a matching dry-run plan hash.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.request import urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from futures_trade_utils import (  # noqa: E402
    BinanceFuturesConfig,
    RequestPlan,
    TradeAPIError,
    TradeConfigError,
    TradeValidationError,
    build_plan_hash,
    build_signed_request,
    enforce_symbol_whitelist,
    fetch_json,
    load_config,
    normalize_client_id,
    normalize_symbol,
    request_preview,
    require_live_confirmation,
)


KINDS = {"standard", "algo"}
MODES = {"dry-run", "live"}
STANDARD_CANCEL_PATH = "/fapi/v1/order"
ALGO_CANCEL_PATH = "/fapi/v1/algoOrder"


@dataclass(frozen=True)
class CancelOrderOptions:
    kind: str
    symbol: str | None = None
    order_id: int | None = None
    orig_client_order_id: str | None = None
    algo_id: int | None = None
    client_algo_id: str | None = None
    mode: str = "dry-run"
    confirm_plan_hash: str | None = None
    confirm: str | None = None


def validate_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in MODES:
        raise TradeValidationError(f"mode must be one of: {', '.join(sorted(MODES))}")
    return normalized


def validate_kind(kind: str) -> str:
    normalized = kind.strip().lower()
    if normalized not in KINDS:
        raise TradeValidationError(f"kind must be one of: {', '.join(sorted(KINDS))}")
    return normalized


def validate_non_negative_id(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    if value < 0:
        raise TradeValidationError(f"{field_name} must be a non-negative integer")
    return value


def build_cancel_params(options: CancelOrderOptions) -> list[tuple[str, str]]:
    kind = validate_kind(options.kind)
    if kind == "standard":
        symbol = normalize_symbol(options.symbol)
        assert symbol is not None
        enforce_symbol_whitelist(symbol)
        order_id = validate_non_negative_id(options.order_id, "order id")
        orig_client_order_id = normalize_client_id(options.orig_client_order_id, "orig client order id")
        if order_id is None and not orig_client_order_id:
            raise TradeValidationError("standard cancellation requires --order-id or --orig-client-order-id")
        if options.algo_id is not None or options.client_algo_id is not None:
            raise TradeValidationError("standard cancellation uses order ids, not algo ids")
        params = [("symbol", symbol)]
        if order_id is not None:
            params.append(("orderId", str(order_id)))
        if orig_client_order_id:
            params.append(("origClientOrderId", orig_client_order_id))
        return params

    algo_id = validate_non_negative_id(options.algo_id, "algo id")
    client_algo_id = normalize_client_id(options.client_algo_id, "client algo id")
    if algo_id is None and not client_algo_id:
        raise TradeValidationError("algo cancellation requires --algo-id or --client-algo-id")
    if options.order_id is not None or options.orig_client_order_id is not None:
        raise TradeValidationError("algo cancellation uses algo ids, not standard order ids")
    params: list[tuple[str, str]] = [("algoType", "CONDITIONAL")]
    if options.symbol is not None:
        symbol = normalize_symbol(options.symbol)
        assert symbol is not None
        enforce_symbol_whitelist(symbol)
        params.append(("symbol", symbol))
    if algo_id is not None:
        params.append(("algoId", str(algo_id)))
    if client_algo_id:
        params.append(("clientAlgoId", client_algo_id))
    return params


def build_plan(options: CancelOrderOptions) -> RequestPlan:
    validate_mode(options.mode)
    kind = validate_kind(options.kind)
    path = STANDARD_CANCEL_PATH if kind == "standard" else ALGO_CANCEL_PATH
    return RequestPlan("cancel_futures_order", "DELETE", path, tuple(build_cancel_params(options)))


def build_request(config: BinanceFuturesConfig, options: CancelOrderOptions):
    plan = build_plan(options)
    return build_signed_request(config, plan.method, plan.path, plan.params), plan


def execute_cancel(
    config: BinanceFuturesConfig,
    options: CancelOrderOptions,
    opener: Callable[..., Any] = urlopen,
    timeout: int = 15,
) -> dict[str, Any]:
    mode = validate_mode(options.mode)
    request, plan = build_request(config, options)
    plan_hash = build_plan_hash(plan)
    if mode == "dry-run":
        return request_preview(config, plan, request, mode)
    require_live_confirmation(mode, plan_hash, options.confirm_plan_hash, options.confirm)
    return {
        "mode": mode,
        "plan_hash": plan_hash,
        "response": fetch_json(request, opener=opener, timeout=timeout),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare or cancel a Binance USD-M futures standard or conditional order.")
    parser.add_argument("--kind", required=True, choices=sorted(KINDS), help="standard or algo")
    parser.add_argument("--symbol", help="required for standard cancellation; optional local whitelist check for algo cancellation")
    parser.add_argument("--order-id", type=int, help="standard order id")
    parser.add_argument("--orig-client-order-id", help="standard origClientOrderId")
    parser.add_argument("--algo-id", type=int, help="conditional algoId")
    parser.add_argument("--client-algo-id", help="conditional clientAlgoId")
    parser.add_argument("--mode", default="dry-run", choices=sorted(MODES), help="dry-run prints a redacted plan; live cancels an order")
    parser.add_argument("--confirm-plan-hash", help="required for --mode live; copy from dry-run output")
    parser.add_argument("--confirm", help="required as LIVE for --mode live")
    parser.add_argument("--json", action="store_true", dest="json_output", help="print JSON output")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    return parser


def options_from_args(args: argparse.Namespace) -> CancelOrderOptions:
    return CancelOrderOptions(
        kind=args.kind,
        symbol=args.symbol,
        order_id=args.order_id,
        orig_client_order_id=args.orig_client_order_id,
        algo_id=args.algo_id,
        client_algo_id=args.client_algo_id,
        mode=args.mode,
        confirm_plan_hash=args.confirm_plan_hash,
        confirm=args.confirm,
    )


def main(argv: list[str] | None = None, stdout: Any = sys.stdout, stderr: Any = sys.stderr) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = execute_cancel(load_config(), options_from_args(args), timeout=args.timeout)
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
        return 0
    except (TradeConfigError, TradeValidationError, TradeAPIError) as exc:
        print(f"error: {exc}", file=stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
