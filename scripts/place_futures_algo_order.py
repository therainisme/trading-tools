#!/usr/bin/env python3
"""Prepare or place a Binance USD-M futures conditional/algo order.

Default mode is dry-run. Live algo orders require a matching dry-run plan hash.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from futures_trade_utils import (  # noqa: E402
    POSITION_SIDE_VALUES,
    SIDE_VALUES,
    TIME_IN_FORCE_VALUES,
    WORKING_TYPE_VALUES,
    BinanceFuturesConfig,
    RequestPlan,
    TradeAPIError,
    TradeConfigError,
    TradeValidationError,
    bool_param,
    build_plan_hash,
    build_signed_request,
    decimal_string,
    enforce_symbol_whitelist,
    fetch_json,
    load_config,
    normalize_client_id,
    normalize_enum,
    normalize_symbol,
    optional_decimal_string,
    request_preview,
    require_live_confirmation,
)


ALGO_ORDER_TYPES = {"STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET"}
TRIGGER_PRICE_TYPES = {"STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"}
LIMIT_AFTER_TRIGGER_TYPES = {"STOP", "TAKE_PROFIT"}
MODES = {"dry-run", "live"}
ALGO_ORDER_PATH = "/fapi/v1/algoOrder"


@dataclass(frozen=True)
class AlgoOrderOptions:
    symbol: str
    side: str
    order_type: str
    quantity: str | None = None
    trigger_price: str | None = None
    price: str | None = None
    activation_price: str | None = None
    callback_rate: str | None = None
    position_side: str = "BOTH"
    time_in_force: str | None = None
    working_type: str = "MARK_PRICE"
    reduce_only: bool = False
    close_position: bool = False
    price_protect: bool = True
    client_algo_id: str | None = None
    allow_open_position: bool = False
    mode: str = "dry-run"
    confirm_plan_hash: str | None = None
    confirm: str | None = None


def validate_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in MODES:
        raise TradeValidationError(f"mode must be one of: {', '.join(sorted(MODES))}")
    return normalized


def build_algo_order_params(options: AlgoOrderOptions) -> list[tuple[str, str]]:
    symbol = normalize_symbol(options.symbol)
    assert symbol is not None
    enforce_symbol_whitelist(symbol)
    side = normalize_enum(options.side, SIDE_VALUES, "side")
    order_type = normalize_enum(options.order_type, ALGO_ORDER_TYPES, "order type")
    position_side = normalize_enum(options.position_side, POSITION_SIDE_VALUES, "position side")
    working_type = normalize_enum(options.working_type, WORKING_TYPE_VALUES, "working type")
    client_algo_id = normalize_client_id(options.client_algo_id, "client algo id")

    if options.close_position:
        if order_type not in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
            raise TradeValidationError("close-position is supported only for STOP_MARKET and TAKE_PROFIT_MARKET")
        if options.quantity is not None:
            raise TradeValidationError("close-position orders must omit quantity")
        if options.reduce_only:
            raise TradeValidationError("close-position orders must omit reduceOnly")
    else:
        if options.quantity is None:
            raise TradeValidationError("quantity is required unless --close-position is set")
        if not options.reduce_only and not options.allow_open_position:
            raise TradeValidationError("non-reduce-only algo orders require --allow-open-position")

    params: list[tuple[str, str]] = [
        ("symbol", symbol),
        ("algoType", "CONDITIONAL"),
        ("side", side),
        ("positionSide", position_side),
        ("type", order_type),
        ("workingType", working_type),
        ("priceProtect", bool_param(options.price_protect)),
    ]

    if options.close_position:
        params.append(("closePosition", "true"))
    else:
        params.append(("quantity", decimal_string(options.quantity, "quantity")))
        if options.reduce_only:
            params.append(("reduceOnly", "true"))

    if order_type in TRIGGER_PRICE_TYPES:
        params.append(("triggerPrice", decimal_string(options.trigger_price, "trigger price")))
    else:
        if options.trigger_price is not None:
            raise TradeValidationError("TRAILING_STOP_MARKET does not accept triggerPrice")

    if order_type in LIMIT_AFTER_TRIGGER_TYPES:
        params.append(("price", decimal_string(options.price, "price")))
        params.append(("timeInForce", normalize_enum(options.time_in_force or "GTC", TIME_IN_FORCE_VALUES, "time in force")))
    else:
        if options.price is not None:
            raise TradeValidationError(f"{order_type} does not accept price")
        if options.time_in_force is not None:
            raise TradeValidationError(f"{order_type} does not accept timeInForce")

    if order_type == "TRAILING_STOP_MARKET":
        activation_price = optional_decimal_string(options.activation_price, "activation price")
        callback_rate = decimal_string(options.callback_rate, "callback rate")
        if activation_price:
            params.append(("activationPrice", activation_price))
        params.append(("callbackRate", callback_rate))
    else:
        if options.activation_price is not None:
            raise TradeValidationError(f"{order_type} does not accept activationPrice")
        if options.callback_rate is not None:
            raise TradeValidationError(f"{order_type} does not accept callbackRate")

    if client_algo_id:
        params.append(("clientAlgoId", client_algo_id))
    return params


def build_plan(options: AlgoOrderOptions) -> RequestPlan:
    validate_mode(options.mode)
    return RequestPlan("place_futures_algo_order", "POST", ALGO_ORDER_PATH, tuple(build_algo_order_params(options)))


def build_request(config: BinanceFuturesConfig, options: AlgoOrderOptions):
    plan = build_plan(options)
    return build_signed_request(config, plan.method, plan.path, plan.params), plan


def execute_algo_order(
    config: BinanceFuturesConfig,
    options: AlgoOrderOptions,
    opener: Callable[..., Any] | None = None,
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
    parser = argparse.ArgumentParser(description="Prepare or place a Binance USD-M futures conditional/algo order.")
    parser.add_argument("--symbol", required=True, help="USD-M futures symbol, for example NVDAUSDT")
    parser.add_argument("--side", required=True, choices=sorted(SIDE_VALUES), help="BUY or SELL")
    parser.add_argument("--order-type", required=True, choices=sorted(ALGO_ORDER_TYPES), help="conditional order type")
    parser.add_argument("--quantity", help="order quantity; omit with --close-position")
    parser.add_argument("--trigger-price", help="trigger price for stop/take-profit orders")
    parser.add_argument("--price", help="limit price after trigger for STOP or TAKE_PROFIT")
    parser.add_argument("--activation-price", help="optional activation price for trailing stop")
    parser.add_argument("--callback-rate", help="callback rate for trailing stop")
    parser.add_argument("--position-side", default="BOTH", choices=sorted(POSITION_SIDE_VALUES), help="position side, default: BOTH")
    parser.add_argument("--time-in-force", choices=sorted(TIME_IN_FORCE_VALUES), help="limit-after-trigger time in force, default: GTC")
    parser.add_argument("--working-type", default="MARK_PRICE", choices=sorted(WORKING_TYPE_VALUES), help="trigger source, default: MARK_PRICE")
    parser.add_argument("--reduce-only", action="store_true", help="send reduceOnly=true")
    parser.add_argument("--close-position", action="store_true", help="send closePosition=true and omit quantity")
    parser.add_argument("--no-price-protect", action="store_true", help="send priceProtect=false")
    parser.add_argument("--client-algo-id", help="optional Binance clientAlgoId")
    parser.add_argument("--allow-open-position", action="store_true", help="allow an algo order that can increase or open exposure")
    parser.add_argument("--mode", default="dry-run", choices=sorted(MODES), help="dry-run prints a redacted plan; live places an order")
    parser.add_argument("--confirm-plan-hash", help="required for --mode live; copy from dry-run output")
    parser.add_argument("--confirm", help="required as LIVE for --mode live")
    parser.add_argument("--json", action="store_true", dest="json_output", help="print JSON output")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    return parser


def options_from_args(args: argparse.Namespace) -> AlgoOrderOptions:
    return AlgoOrderOptions(
        symbol=args.symbol,
        side=args.side,
        order_type=args.order_type,
        quantity=args.quantity,
        trigger_price=args.trigger_price,
        price=args.price,
        activation_price=args.activation_price,
        callback_rate=args.callback_rate,
        position_side=args.position_side,
        time_in_force=args.time_in_force,
        working_type=args.working_type,
        reduce_only=args.reduce_only,
        close_position=args.close_position,
        price_protect=not args.no_price_protect,
        client_algo_id=args.client_algo_id,
        allow_open_position=args.allow_open_position,
        mode=args.mode,
        confirm_plan_hash=args.confirm_plan_hash,
        confirm=args.confirm,
    )


def main(argv: list[str] | None = None, stdout: Any = sys.stdout, stderr: Any = sys.stderr) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = execute_algo_order(load_config(), options_from_args(args), timeout=args.timeout)
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
        return 0
    except (TradeConfigError, TradeValidationError, TradeAPIError) as exc:
        print(f"error: {exc}", file=stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
