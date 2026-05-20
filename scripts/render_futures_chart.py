#!/usr/bin/env python3
"""Render a Binance USDⓈ-M futures candlestick chart as SVG or PNG."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from binance_proxy import (  # noqa: E402
    DISABLED_PROXY_CONFIG,
    BinanceProxyConfig,
    add_proxy_auth_headers,
    load_proxy_config_from_candidates,
    resolve_proxy_base_url,
)
from http_transport import ProxyConfigError, urlopen_with_env_proxy  # noqa: E402


BASE_URL = "https://fapi.binance.com"
EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"
KLINES_PATH = "/fapi/v1/klines"
DEFAULT_INTERVAL = "1h"
DEFAULT_LIMIT = 96
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_OUTPUT_DIR = Path("/tmp/trading-tools/charts")
CHART_WIDTH = 1200
CHART_HEIGHT = 780
MAX_KLINE_LIMIT = 1500
INTERVALS = {
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
}
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9_]+$")


class ChartError(Exception):
    """Raised when chart generation fails."""


@dataclass(frozen=True)
class Candle:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str
    status: str
    contract_type: str
    base_asset: str
    quote_asset: str
    underlying_type: str


@dataclass(frozen=True)
class ChartOptions:
    symbol: str
    interval: str = DEFAULT_INTERVAL
    limit: int = DEFAULT_LIMIT
    timezone: str = DEFAULT_TIMEZONE
    output_format: str = "svg"
    output: Path | None = None


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise ChartError("symbol must be a non-empty string")
    if not SYMBOL_PATTERN.fullmatch(normalized):
        raise ChartError("symbol may contain only letters, digits, and underscores")
    return normalized


def validate_interval(interval: str) -> str:
    if interval not in INTERVALS:
        accepted = ", ".join(sorted(INTERVALS))
        raise ChartError(f"interval must be one of: {accepted}")
    return interval


def validate_limit(limit: int) -> int:
    if limit < 1 or limit > MAX_KLINE_LIMIT:
        raise ChartError(f"limit must be between 1 and {MAX_KLINE_LIMIT}")
    return limit


def timezone_info(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ChartError(f"timezone was not found: {name}") from exc


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def config_candidates(root: Path | None = None, home: Path | None = None) -> list[Path]:
    root_path = root or skill_root()
    home_path = home or Path.home()
    return [
        root_path / ".trading-tools" / "config.json",
        home_path / ".trading-tools" / "config.json",
    ]


def load_optional_proxy_config(root: Path | None = None, home: Path | None = None) -> BinanceProxyConfig:
    return load_proxy_config_from_candidates(config_candidates(root=root, home=home), ChartError)


def build_url(
    path: str,
    params: Iterable[tuple[str, str | int]] | None = None,
    proxy_config: BinanceProxyConfig = DISABLED_PROXY_CONFIG,
) -> str:
    query = urlencode(list(params or []))
    base_url = resolve_proxy_base_url(BASE_URL, proxy_config)
    if query:
        return f"{base_url}{path}?{query}"
    return f"{base_url}{path}"


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
        raise ChartError(f"proxy configuration error: {exc}") from exc
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise ChartError(f"Binance market data returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise ChartError(f"Binance market data request failed: {exc}") from exc
    except OSError as exc:
        raise ChartError(f"Binance market data request failed: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ChartError(f"Binance market data returned invalid JSON: {exc}") from exc


def fetch_exchange_info(
    opener: Callable[..., Any] | None = None,
    timeout: int = 15,
    proxy_config: BinanceProxyConfig = DISABLED_PROXY_CONFIG,
) -> dict[str, Any]:
    data = fetch_json(
        build_url(EXCHANGE_INFO_PATH, proxy_config=proxy_config),
        headers=add_proxy_auth_headers({}, proxy_config),
        opener=opener,
        timeout=timeout,
    )
    if not isinstance(data, dict):
        raise ChartError("Binance exchangeInfo response must be a JSON object")
    return data


def fetch_klines(
    symbol: str,
    interval: str,
    limit: int,
    opener: Callable[..., Any] | None = None,
    timeout: int = 15,
    proxy_config: BinanceProxyConfig = DISABLED_PROXY_CONFIG,
) -> Any:
    url = build_url(
        KLINES_PATH,
        [
            ("symbol", symbol),
            ("interval", interval),
            ("limit", limit),
        ],
        proxy_config=proxy_config,
    )
    return fetch_json(url, headers=add_proxy_auth_headers({}, proxy_config), opener=opener, timeout=timeout)


def validate_futures_symbol(exchange_info: dict[str, Any], symbol: str) -> SymbolInfo:
    symbols = exchange_info.get("symbols")
    if not isinstance(symbols, list):
        raise ChartError("Binance exchangeInfo response is missing the symbols list")

    for item in symbols:
        if not isinstance(item, dict):
            continue
        if str(item.get("symbol", "")).upper() == symbol:
            status = str(item.get("status", ""))
            if status != "TRADING":
                raise ChartError(f"{symbol} is present on Binance USDⓈ-M futures with status {status}")
            return SymbolInfo(
                symbol=symbol,
                status=status,
                contract_type=str(item.get("contractType", "")),
                base_asset=str(item.get("baseAsset", "")),
                quote_asset=str(item.get("quoteAsset", "")),
                underlying_type=str(item.get("underlyingType", "")),
            )

    raise ChartError(f"{symbol} was not found on Binance USDⓈ-M futures")


def decimal_field(value: Any, field_name: str, index: int) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ChartError(f"kline row {index} has invalid {field_name}: {value!r}") from exc


def parse_klines(data: Any) -> list[Candle]:
    if not isinstance(data, list):
        raise ChartError("Binance klines response must be a JSON array")
    if not data:
        raise ChartError("Binance returned no klines for this request")

    candles: list[Candle] = []
    for index, row in enumerate(data):
        if not isinstance(row, list) or len(row) < 6:
            raise ChartError(f"kline row {index} must be a list with at least 6 fields")
        try:
            open_time_ms = int(row[0])
        except (TypeError, ValueError) as exc:
            raise ChartError(f"kline row {index} has invalid open time: {row[0]!r}") from exc
        candle = Candle(
            open_time_ms=open_time_ms,
            open=decimal_field(row[1], "open", index),
            high=decimal_field(row[2], "high", index),
            low=decimal_field(row[3], "low", index),
            close=decimal_field(row[4], "close", index),
            volume=decimal_field(row[5], "volume", index),
        )
        if candle.high < candle.low:
            raise ChartError(f"kline row {index} has high below low")
        candles.append(candle)

    return sorted(candles, key=lambda candle: candle.open_time_ms)


def format_price(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 100:
        return f"{value:.2f}"
    if abs_value >= 1:
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{value:.6f}".rstrip("0").rstrip(".")


def format_volume(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def format_time(open_time_ms: int, tz: ZoneInfo) -> str:
    return datetime.fromtimestamp(open_time_ms / 1000, tz).strftime("%m-%d %H:%M")


def text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def render_svg(candles: list[Candle], symbol_info: SymbolInfo, interval: str, timezone_name: str) -> str:
    if not candles:
        raise ChartError("at least one candle is required to render a chart")

    tz = timezone_info(timezone_name)
    width = CHART_WIDTH
    height = CHART_HEIGHT
    margin_left = 80
    margin_top = 132
    margin_right = 112
    margin_bottom = 112
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    volume_height = 104
    gap = 28
    price_height = plot_height - volume_height - gap
    price_top = margin_top
    price_bottom = margin_top + price_height
    volume_top = price_bottom + gap
    volume_bottom = margin_top + plot_height

    lows = [float(candle.low) for candle in candles]
    highs = [float(candle.high) for candle in candles]
    volumes = [max(0.0, float(candle.volume)) for candle in candles]
    min_price = min(lows)
    max_price = max(highs)
    price_span = max_price - min_price
    if price_span <= 0:
        price_span = max(abs(max_price) * 0.01, 1.0)
    min_price -= price_span * 0.06
    max_price += price_span * 0.06
    price_span = max_price - min_price
    max_volume = max(volumes) if volumes else 1.0
    if max_volume <= 0:
        max_volume = 1.0

    candle_count = len(candles)
    step = plot_width / candle_count
    body_width = max(3.0, min(18.0, step * 0.58))

    def x_at(index: int) -> float:
        return margin_left + (index + 0.5) * step

    def y_price(price: Decimal | float) -> float:
        return price_bottom - (float(price) - min_price) / price_span * price_height

    def y_volume(volume: Decimal | float) -> float:
        return volume_bottom - max(0.0, float(volume)) / max_volume * volume_height

    first = candles[0]
    last = candles[-1]
    change_pct = (float(last.close - first.open) / float(first.open) * 100) if first.open != 0 else 0.0
    title = f"{symbol_info.symbol} USD-M Futures"
    contract_bits = [symbol_info.contract_type, symbol_info.underlying_type]
    contract_text = " · ".join(bit for bit in contract_bits if bit)
    subtitle = (
        f"{interval} · {len(candles)} candles · {format_time(first.open_time_ms, tz)}"
        f" → {format_time(last.open_time_ms, tz)} {timezone_name}"
    )
    if contract_text:
        subtitle = f"{subtitle} · {contract_text}"

    svg: list[str] = []
    add = svg.append
    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{text(title)} candlestick chart">'
    )
    add("<defs>")
    add(
        "<style><![CDATA["
        "text{font-family:Inter,Segoe UI,Arial,sans-serif}"
        ".bg{fill:#0b1020}.panel{fill:#0f172a}.title{fill:#f8fafc;font-size:24px;font-weight:650}"
        ".subtitle{fill:#94a3b8;font-size:13px}.axis{fill:#9aa4b2;font-size:12px}"
        ".section{fill:#cbd5e1;font-size:12px;font-weight:600}.footnote{fill:#64748b;font-size:11px}"
        ".metric{fill:#cbd5e1;font-size:13px}.grid{stroke:#1f2937;stroke-width:1}"
        ".axisline{stroke:#334155;stroke-width:1}.headerline{stroke:#1f2937;stroke-width:1}"
        ".lastline{stroke:#64748b;stroke-width:1;stroke-dasharray:4 5}"
        ".up{stroke:#22c55e;fill:#22c55e}.down{stroke:#ef4444;fill:#ef4444}"
        ".volup{fill:#22c55e;opacity:.32}.voldown{fill:#ef4444;opacity:.32}"
        "]]></style>"
    )
    add("</defs>")
    add('<rect class="bg" width="100%" height="100%"/>')
    add(f'<rect class="panel" x="24" y="20" width="{width - 48}" height="{height - 44}" rx="18"/>')
    add(f'<text class="title" x="{margin_left}" y="52">{text(title)}</text>')
    add(f'<text class="subtitle" x="{margin_left}" y="78">{text(subtitle)}</text>')
    add(
        f'<text class="metric" x="{width - margin_right}" y="104" text-anchor="end">'
        f'O {format_price(float(last.open))}  H {format_price(float(last.high))}  '
        f'L {format_price(float(last.low))}  C {format_price(float(last.close))}  '
        f'Δ {change_pct:+.2f}%</text>'
    )
    add(f'<line class="headerline" x1="{margin_left}" y1="116" x2="{width - margin_right}" y2="116"/>')

    price_ticks = 6
    for tick_index in range(price_ticks):
        price = min_price + price_span * tick_index / (price_ticks - 1)
        y = price_bottom - (price - min_price) / price_span * price_height
        add(f'<line class="grid" x1="{margin_left}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}"/>')
        add(
            f'<text class="axis" x="{width - margin_right + 10}" y="{y + 4:.2f}" '
            f'text-anchor="start">{text(format_price(price))}</text>'
        )

    volume_ticks = [0.0, max_volume]
    for volume in volume_ticks:
        y = y_volume(volume)
        add(f'<line class="grid" x1="{margin_left}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}"/>')
        add(
            f'<text class="axis" x="{width - margin_right + 10}" y="{y + 4:.2f}" '
            f'text-anchor="start">{text(format_volume(volume))}</text>'
        )

    add(f'<line class="axisline" x1="{margin_left}" y1="{price_top}" x2="{margin_left}" y2="{volume_bottom}"/>')
    add(f'<line class="axisline" x1="{margin_left}" y1="{price_bottom}" x2="{width - margin_right}" y2="{price_bottom}"/>')
    add(f'<line class="axisline" x1="{margin_left}" y1="{volume_bottom}" x2="{width - margin_right}" y2="{volume_bottom}"/>')
    add(f'<text class="section" x="{margin_left}" y="{price_top - 14}">Price ({text(symbol_info.quote_asset or "USDT")})</text>')
    add(f'<text class="section" x="{margin_left}" y="{volume_top - 10}">Volume</text>')

    last_y = y_price(last.close)
    add(
        f'<line class="lastline" x1="{margin_left}" y1="{last_y:.2f}" '
        f'x2="{width - margin_right}" y2="{last_y:.2f}"/>'
    )

    for index, candle in enumerate(candles):
        x = x_at(index)
        is_up = candle.close >= candle.open
        candle_class = "up" if is_up else "down"
        volume_class = "volup" if is_up else "voldown"
        high_y = y_price(candle.high)
        low_y = y_price(candle.low)
        open_y = y_price(candle.open)
        close_y = y_price(candle.close)
        body_top = min(open_y, close_y)
        body_height = max(1.2, abs(open_y - close_y))
        volume_y = y_volume(candle.volume)
        add(
            f'<line class="{candle_class}" x1="{x:.2f}" y1="{high_y:.2f}" '
            f'x2="{x:.2f}" y2="{low_y:.2f}" stroke-width="1.4"/>'
        )
        add(
            f'<rect class="{candle_class}" x="{x - body_width / 2:.2f}" y="{body_top:.2f}" '
            f'width="{body_width:.2f}" height="{body_height:.2f}" rx="1"/>'
        )
        add(
            f'<rect class="{volume_class}" x="{x - body_width / 2:.2f}" y="{volume_y:.2f}" '
            f'width="{body_width:.2f}" height="{volume_bottom - volume_y:.2f}"/>'
        )

    label_count = min(6, candle_count)
    label_indexes = [round(i * (candle_count - 1) / max(1, label_count - 1)) for i in range(label_count)]
    for index in dict.fromkeys(label_indexes):
        add(
            f'<text class="axis" x="{x_at(index):.2f}" y="{height - 58}" text-anchor="middle">'
            f'{text(format_time(candles[index].open_time_ms, tz))}</text>'
        )

    add(
        f'<text class="footnote" x="{width - margin_right}" y="{height - 28}" text-anchor="end">'
        f'Data: Binance USD-M Futures public market data · Generated {text(datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"))} {text(timezone_name)}</text>'
    )
    add("</svg>")
    return "\n".join(svg)


def timestamp_for_filename() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def default_output_path(symbol: str, interval: str, output_format: str) -> Path:
    filename = f"{symbol}-{interval}-{timestamp_for_filename()}.{output_format}"
    return DEFAULT_OUTPUT_DIR / filename


def resolve_output_path(symbol: str, interval: str, output_format: str, output: Path | None) -> Path:
    if output is None:
        return default_output_path(symbol, interval, output_format)

    output_path = output.expanduser()
    if output_path.exists() and output_path.is_dir():
        return output_path / default_output_path(symbol, interval, output_format).name
    if not output_path.suffix:
        return output_path / default_output_path(symbol, interval, output_format).name
    return output_path


def write_svg(svg: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def convert_svg_to_png(svg: str, output_path: Path, width: int = CHART_WIDTH, height: int = CHART_HEIGHT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import cairosvg  # type: ignore[import-not-found]
    except ImportError:
        cairosvg = None

    if cairosvg is not None:
        cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(output_path))
        return

    browsers = [
        candidate
        for candidate in (
            shutil.which("google-chrome-stable"),
            shutil.which("google-chrome"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
        )
        if candidate
    ]
    browser_errors: list[str] = []
    for browser in dict.fromkeys(browsers):
        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "chart.html"
            html_path.write_text(
                "<!doctype html>"
                "<html><head><meta charset=\"utf-8\">"
                "<style>html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#0b1020;}"
                "svg{display:block;width:100vw;height:100vh;}</style>"
                "</head><body>"
                f"{svg}"
                "</body></html>",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    browser,
                    "--headless",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--no-sandbox",
                    "--force-device-scale-factor=1",
                    f"--window-size={width},{height}",
                    f"--screenshot={output_path}",
                    html_path.as_uri(),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode == 0:
                return
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            browser_errors.append(f"{browser}: {detail[-1] if detail else f'exit {result.returncode}'}")

    if browser_errors:
        raise ChartError("PNG output failed with available browsers: " + "; ".join(browser_errors))
    raise ChartError("PNG output requires CairoSVG or a headless Chromium/Chrome executable")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a Binance USDⓈ-M futures candlestick chart.")
    parser.add_argument("--symbol", required=True, help="required futures symbol, for example NVDAUSDT")
    parser.add_argument("--interval", default=DEFAULT_INTERVAL, help=f"kline interval, default: {DEFAULT_INTERVAL}")
    parser.add_argument("--limit", default=DEFAULT_LIMIT, type=int, help=f"number of candles, default: {DEFAULT_LIMIT}")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help=f"timezone for x-axis labels, default: {DEFAULT_TIMEZONE}")
    parser.add_argument("--format", choices=("svg", "png"), default="svg", dest="output_format", help="output image format")
    parser.add_argument("--output", type=Path, help="output file or directory")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    return parser


def render_chart(options: ChartOptions, opener: Callable[..., Any] | None = None, timeout: int = 15) -> Path:
    symbol = normalize_symbol(options.symbol)
    interval = validate_interval(options.interval)
    limit = validate_limit(options.limit)
    timezone_info(options.timezone)
    proxy_config = load_optional_proxy_config()

    exchange_info = fetch_exchange_info(opener=opener, timeout=timeout, proxy_config=proxy_config)
    symbol_info = validate_futures_symbol(exchange_info, symbol)
    raw_klines = fetch_klines(symbol, interval, limit, opener=opener, timeout=timeout, proxy_config=proxy_config)
    candles = parse_klines(raw_klines)
    svg = render_svg(candles, symbol_info, interval, options.timezone)
    output_path = resolve_output_path(symbol, interval, options.output_format, options.output)

    if options.output_format == "svg":
        write_svg(svg, output_path)
    else:
        convert_svg_to_png(svg, output_path)
    return output_path


def main(argv: list[str] | None = None, stdout: Any = sys.stdout, stderr: Any = sys.stderr) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        options = ChartOptions(
            symbol=args.symbol,
            interval=args.interval,
            limit=args.limit,
            timezone=args.timezone,
            output_format=args.output_format,
            output=args.output,
        )
        output_path = render_chart(options, timeout=args.timeout)
        print(output_path, file=stdout)
        return 0
    except ChartError as exc:
        print(f"error: {exc}", file=stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
