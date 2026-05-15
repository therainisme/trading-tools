#!/usr/bin/env python3
"""Prepare or place a Binance USD-M futures standard order.

Default mode is dry-run. Live orders require a matching dry-run plan hash.
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
    POSITION_SIDE_VALUES,
    RESPONSE_TYPE_VALUES,
    SIDE_VALUES,
    TIME_IN_FORCE_VALUES,
    BinanceFuturesConfig,
    RequestPlan,
    TradeAPIError,
    TradeConfigError,
    TradeValidationError,
    build_plan_hash,
    build_signed_request,
    decimal_string,
    enforce_symbol_whitelist,
    fetch_json,
    load_config,
    normalize_client_id,
    normalize_enum,
    normalize_symbol,
    request_preview,
    require_live_confirmation,
)


STANDARD_ORDER_TYPES = {"LIMIT", "MARKET"}
MODES = {"dry-run", "test", "live"}
ORDER_PATH = "/fapi/v1/order"
TEST_ORDER_PATH = "/fapi/v1/order/test"


@dataclass(frozen=True)
class StandardOrderOptions:
    symbol: str
    side: str
    order_type: str
    quantity: str
    price: str | None = None
    position_side: str = "BOTH"
    time_in_force: str | None = None
    reduce_only: bool = False
    new_client_order_id: str | None = None
    new_order_resp_type: str = "RESULT"
    mode: str = "dry-run"
    confirm_plan_hash: str | None = None
    confirm: str | None = None


def validate_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in MODES:
        raise TradeValidationError(f"mode must be one of: {', '.join(sorted(MODES))}")
    return normalized


def build_order_params(options: StandardOrderOptions) -> list[tuple[str, str]]:
    symbol = normalize_symbol(options.symbol)
    assert symbol is not None
    enforce_symbol_whitelist(symbol)
    side = normalize_enum(options.side, SIDE_VALUES, "side")
    order_type = normalize_enum(options.order_type, STANDARD_ORDER_TYPES, "order type")
    position_side = normalize_enum(options.position_side, POSITION_SIDE_VALUES, "position side")
    quantity = decimal_string(options.quantity, "quantity")
    client_id = normalize_client_id(options.new_client_order_id, "new client order id")
    response_type = normalize_enum(options.new_order_resp_type, RESPONSE_TYPE_VALUES, "new order response type")

    params: list[tuple[str, str]] = [
        ("symbol", symbol),
        ("side", side),
        ("positionSide", position_side),
        ("type", order_type),
        ("quantity", quantity),
        ("newOrderRespType", response_type),
    ]

    if order_type == "LIMIT":
        price = decimal_string(options.price, "price")
        time_in_force = normalize_enum(options.time_in_force or "GTC", TIME_IN_FORCE_VALUES, "time in force")
        params.extend([("timeInForce", time_in_force), ("price", price)])
    else:
        if options.price is not None:
            raise TradeValidationError("MARKET orders do not accept price")
        if options.time_in_force is not None:
            raise TradeValidationError("MARKET orders do not accept timeInForce")

    if options.reduce_only:
        params.append(("reduceOnly", "true"))
    if client_id:
        params.append(("newClientOrderId", client_id))
    return params


def build_plan(options: StandardOrderOptions) -> RequestPlan:
    mode = validate_mode(options.mode)
    path = TEST_ORDER_PATH if mode == "test" else ORDER_PATH
    return RequestPlan("place_futures_order", "POST", path, tuple(build_order_params(options)))


def build_request(config: BinanceFuturesConfig, options: StandardOrderOptions):
    plan = build_plan(options)
    return build_signed_request(config, plan.method, plan.path, plan.params), plan


def execute_order(
    config: BinanceFuturesConfig,
    options: StandardOrderOptions,
    opener: Callable[..., Any] = urlopen,
    timeout: int = 15,
) -> dict[str, Any]:
    mode = validate_mode(options.mode)
    request, plan = build_request(config, options)
    plan_hash = build_plan_hash(plan)

    if mode == "dry-run":
        return request_preview(config, plan, request, mode)
    if mode == "live":
        require_live_confirmation(mode, plan_hash, options.confirm_plan_hash, options.confirm)
    return {
        "mode": mode,
        "plan_hash": plan_hash,
        "response": fetch_json(request, opener=opener, timeout=timeout),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare or place a Binance USD-M futures standard order.")
    parser.add_argument("--symbol", required=True, help="USD-M futures symbol, for example NVDAUSDT")
    parser.add_argument("--side", required=True, choices=sorted(SIDE_VALUES), help="BUY or SELL")
    parser.add_argument("--type", required=True, choices=sorted(STANDARD_ORDER_TYPES), dest="order_type", help="LIMIT or MARKET")
    parser.add_argument("--quantity", required=True, help="order quantity")
    parser.add_argument("--price", help="required for LIMIT orders")
    parser.add_argument("--position-side", default="BOTH", choices=sorted(POSITION_SIDE_VALUES), help="position side, default: BOTH")
    parser.add_argument("--time-in-force", choices=sorted(TIME_IN_FORCE_VALUES), help="LIMIT order time in force, default: GTC")
    parser.add_argument("--reduce-only", action="store_true", help="send reduceOnly=true")
    parser.add_argument("--new-client-order-id", help="optional Binance newClientOrderId")
    parser.add_argument("--new-order-resp-type", default="RESULT", choices=sorted(RESPONSE_TYPE_VALUES), help="ACK or RESULT")
    parser.add_argument("--mode", default="dry-run", choices=sorted(MODES), help="dry-run prints a redacted plan; test calls /order/test; live places an order")
    parser.add_argument("--confirm-plan-hash", help="required for --mode live; copy from dry-run output")
    parser.add_argument("--confirm", help="required as LIVE for --mode live")
    parser.add_argument("--json", action="store_true", dest="json_output", help="print JSON output")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    return parser


def options_from_args(args: argparse.Namespace) -> StandardOrderOptions:
    return StandardOrderOptions(
        symbol=args.symbol,
        side=args.side,
        order_type=args.order_type,
        quantity=args.quantity,
        price=args.price,
        position_side=args.position_side,
        time_in_force=args.time_in_force,
        reduce_only=args.reduce_only,
        new_client_order_id=args.new_client_order_id,
        new_order_resp_type=args.new_order_resp_type,
        mode=args.mode,
        confirm_plan_hash=args.confirm_plan_hash,
        confirm=args.confirm,
    )


def main(argv: list[str] | None = None, stdout: Any = sys.stdout, stderr: Any = sys.stderr) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = execute_order(load_config(), options_from_args(args), timeout=args.timeout)
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
        return 0
    except (TradeConfigError, TradeValidationError, TradeAPIError) as exc:
        print(f"error: {exc}", file=stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
