#!/usr/bin/env python3
"""Check whether current Binance USD-M futures positions have protective exit orders."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import list_futures_orders as orders  # noqa: E402
import list_futures_positions as positions_mod  # noqa: E402


STOP_TYPES = {"STOP", "STOP_MARKET"}
TAKE_PROFIT_TYPES = {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"}
EXIT_LIMIT_TYPES = {"LIMIT"}
ACTIVE_CONDITIONAL_STATUSES = {"NEW", "PARTIALLY_FILLED"}
ACTIVE_STANDARD_STATUSES = {"NEW", "PARTIALLY_FILLED"}


class ProtectionError(Exception):
    """Raised when protection checks cannot be completed."""


def decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def normalize_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    normalized = symbol.strip().upper()
    return normalized or None


def active_positions(rows: list[dict[str, Any]], symbol: str | None = None) -> list[dict[str, Any]]:
    symbol_filter = normalize_symbol(symbol)
    result: list[dict[str, Any]] = []
    for row in rows:
        if symbol_filter and str(row.get("symbol", "")).upper() != symbol_filter:
            continue
        if decimal_value(row.get("positionAmt")) != 0:
            result.append(row)
    return result


def exit_side_for_position(position_amt: Decimal) -> str:
    return "SELL" if position_amt > 0 else "BUY"


def conditional_order_type(order: dict[str, Any]) -> str:
    return str(order.get("orderType") or order.get("type") or "").upper()


def standard_order_type(order: dict[str, Any]) -> str:
    return str(order.get("type") or "").upper()


def is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def remaining_standard_qty(order: dict[str, Any]) -> Decimal:
    orig = decimal_value(order.get("origQty"))
    executed = decimal_value(order.get("executedQty"))
    remaining = orig - executed
    return remaining if remaining > 0 else Decimal("0")


def conditional_qty(order: dict[str, Any], position_qty: Decimal) -> Decimal:
    if is_true(order.get("closePosition")):
        return position_qty
    return decimal_value(order.get("quantity"))


def is_active_conditional(order: dict[str, Any]) -> bool:
    return str(order.get("algoStatus", "")).upper() in ACTIVE_CONDITIONAL_STATUSES


def is_active_standard(order: dict[str, Any]) -> bool:
    return str(order.get("status", "")).upper() in ACTIVE_STANDARD_STATUSES


def is_reduce_or_close(order: dict[str, Any]) -> bool:
    return is_true(order.get("reduceOnly")) or is_true(order.get("closePosition"))


def analyze_position(
    position: dict[str, Any],
    standard_orders: list[dict[str, Any]],
    conditional_orders: list[dict[str, Any]],
    preferred_working_type: str = "MARK_PRICE",
) -> dict[str, Any]:
    symbol = str(position.get("symbol", "")).upper()
    amount = decimal_value(position.get("positionAmt"))
    qty = abs(amount)
    exit_side = exit_side_for_position(amount)
    issues: list[str] = []
    warnings: list[str] = []
    stop_qty = Decimal("0")
    take_profit_qty = Decimal("0")
    oversized_orders: list[str] = []
    wrong_working_type: list[str] = []

    for order in conditional_orders:
        if str(order.get("symbol", "")).upper() != symbol or not is_active_conditional(order):
            continue
        if str(order.get("side", "")).upper() != exit_side:
            continue
        order_type = conditional_order_type(order)
        order_qty = conditional_qty(order, qty)
        protective = is_reduce_or_close(order)
        if order_type in STOP_TYPES and protective:
            stop_qty += order_qty
        elif order_type in TAKE_PROFIT_TYPES and protective:
            take_profit_qty += order_qty
        else:
            continue
        if not is_true(order.get("closePosition")) and order_qty > qty:
            oversized_orders.append(f"algo {order.get('algoId')} qty {order_qty}")
        working_type = str(order.get("workingType", "")).upper()
        if working_type and working_type != preferred_working_type:
            wrong_working_type.append(f"algo {order.get('algoId')} {working_type}")

    for order in standard_orders:
        if str(order.get("symbol", "")).upper() != symbol or not is_active_standard(order):
            continue
        if str(order.get("side", "")).upper() != exit_side:
            continue
        if not is_reduce_or_close(order):
            continue
        order_type = standard_order_type(order)
        order_qty = remaining_standard_qty(order)
        if order_type in STOP_TYPES:
            stop_qty += order_qty
        elif order_type in TAKE_PROFIT_TYPES or order_type in EXIT_LIMIT_TYPES:
            take_profit_qty += order_qty
        else:
            continue
        if order_qty > qty:
            oversized_orders.append(f"order {order.get('orderId')} qty {order_qty}")

    if stop_qty < qty:
        issues.append(f"stop coverage {stop_qty}/{qty}")
    if take_profit_qty < qty:
        warnings.append(f"take-profit coverage {take_profit_qty}/{qty}")
    if oversized_orders:
        issues.append("oversized protective order: " + ", ".join(oversized_orders))
    if wrong_working_type:
        warnings.append("workingType differs from preferred " + preferred_working_type + ": " + ", ".join(wrong_working_type))

    return {
        "symbol": symbol,
        "positionSide": position.get("positionSide"),
        "positionAmt": str(amount),
        "entryPrice": position.get("entryPrice"),
        "markPrice": position.get("markPrice"),
        "exitSide": exit_side,
        "stopCoverageQty": str(stop_qty),
        "takeProfitCoverageQty": str(take_profit_qty),
        "positionQty": str(qty),
        "status": "ok" if not issues else "needs-attention",
        "issues": issues,
        "warnings": warnings,
    }


def fetch_current_state(symbol: str | None = None, timeout: int = 15) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    pos_config = positions_mod.load_config()
    raw_positions = positions_mod.fetch_json(positions_mod.build_signed_request(pos_config), timeout=timeout)
    position_rows = positions_mod.ensure_position_list(raw_positions)

    order_config = orders.apply_overrides(
        orders.load_config(),
        orders.OrderRequestOptions(kind="open", symbol=symbol, include_empty_symbol=symbol is None),
    )
    standard_request = orders.build_signed_request(
        order_config,
        orders.OrderRequestOptions(kind="open", symbol=symbol, include_empty_symbol=symbol is None),
    )
    standard_rows = orders.ensure_list(orders.fetch_json(standard_request, timeout=timeout), "open")

    conditional_options = orders.OrderRequestOptions(
        kind="conditional-open",
        symbol=symbol,
        algo_type="CONDITIONAL",
        include_empty_symbol=symbol is None,
    )
    conditional_config = orders.apply_overrides(orders.load_config(), conditional_options)
    conditional_request = orders.build_signed_request(conditional_config, conditional_options)
    conditional_rows = orders.ensure_list(orders.fetch_json(conditional_request, timeout=timeout), "conditional-open")
    return position_rows, standard_rows, conditional_rows


def check_protection(
    position_rows: list[dict[str, Any]],
    standard_rows: list[dict[str, Any]],
    conditional_rows: list[dict[str, Any]],
    symbol: str | None = None,
    preferred_working_type: str = "MARK_PRICE",
) -> dict[str, Any]:
    positions = active_positions(position_rows, symbol=symbol)
    checks = [analyze_position(row, standard_rows, conditional_rows, preferred_working_type=preferred_working_type) for row in positions]
    return {
        "symbol": normalize_symbol(symbol),
        "preferredWorkingType": preferred_working_type,
        "positionCount": len(checks),
        "ok": all(item["status"] == "ok" for item in checks),
        "checks": checks,
    }


def format_table(payload: dict[str, Any]) -> str:
    checks = payload.get("checks", [])
    if not checks:
        return "No active futures positions to check."
    fields = ["symbol", "positionAmt", "markPrice", "stopCoverageQty", "takeProfitCoverageQty", "status", "issues", "warnings"]
    rows = []
    for item in checks:
        rows.append([
            str(item.get("symbol", "-")),
            str(item.get("positionAmt", "-")),
            str(item.get("markPrice", "-")),
            str(item.get("stopCoverageQty", "-")),
            str(item.get("takeProfitCoverageQty", "-")),
            str(item.get("status", "-")),
            "; ".join(item.get("issues", [])),
            "; ".join(item.get("warnings", [])),
        ])
    widths = [len(field) for field in fields]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def fmt(row: list[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    return "\n".join([fmt(fields), "  ".join("-" * width for width in widths), *(fmt(row) for row in rows)])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check futures positions against current protective exit orders.")
    parser.add_argument("--symbol", help="optional symbol filter, for example NVDAUSDT")
    parser.add_argument("--preferred-working-type", default="MARK_PRICE", choices=("MARK_PRICE", "CONTRACT_PRICE"), help="workingType preference for protective triggers")
    parser.add_argument("--json", action="store_true", dest="json_output", help="print JSON output")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    return parser


def main(argv: list[str] | None = None, stdout: Any = sys.stdout, stderr: Any = sys.stderr) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        position_rows, standard_rows, conditional_rows = fetch_current_state(symbol=args.symbol, timeout=args.timeout)
        payload = check_protection(
            position_rows,
            standard_rows,
            conditional_rows,
            symbol=args.symbol,
            preferred_working_type=args.preferred_working_type,
        )
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
        else:
            print(format_table(payload), file=stdout)
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
