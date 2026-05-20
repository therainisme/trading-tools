#!/usr/bin/env python3
"""Binance endpoint proxy helpers shared by trading-tools scripts."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


DEFAULT_PROXY_AUTH_HEADER = "X-Trading-Proxy-Key"
SUPPORTED_PROXY_BASE_SCHEMES = {"http", "https"}
HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")

OFFICIAL_BASE_URL_TO_PROXY_PREFIX = {
    "https://fapi.binance.com": "/fapi",
    "https://dapi.binance.com": "/dapi",
    "https://demo-fapi.binance.com": "/demo-fapi",
    "https://testnet.binancefuture.com": "/testnet-future",
}


@dataclass(frozen=True)
class BinanceProxyConfig:
    enabled: bool = False
    base_url: str = ""
    auth_header: str = DEFAULT_PROXY_AUTH_HEADER
    auth_key: str = ""


DISABLED_PROXY_CONFIG = BinanceProxyConfig()


def _raise(error_type: type[Exception], message: str) -> None:
    raise error_type(message)


def redact_secret(value: str) -> str:
    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:4]}...{value[-4:]}"


def normalize_proxy_base_url(value: str, field_name: str, path: Path, error_type: type[Exception]) -> str:
    raw = value.strip()
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in SUPPORTED_PROXY_BASE_SCHEMES or not parts.netloc:
        supported = ", ".join(sorted(SUPPORTED_PROXY_BASE_SCHEMES))
        _raise(error_type, f"config field '{field_name}' in {path} must be an http(s) URL. Supported schemes: {supported}")
    if parts.query or parts.fragment:
        _raise(error_type, f"config field '{field_name}' in {path} must not include query or fragment")
    normalized_path = parts.path.rstrip("/")
    return urlunsplit((scheme, parts.netloc, normalized_path, "", ""))


def parse_proxy_config(
    futures: Mapping[str, Any],
    path: Path,
    error_type: type[Exception] = ValueError,
) -> BinanceProxyConfig:
    raw_proxy = futures.get("proxy")
    if raw_proxy is None:
        return DISABLED_PROXY_CONFIG
    if not isinstance(raw_proxy, Mapping):
        _raise(error_type, f"config field 'binance.futures.proxy' in {path} must be a JSON object")

    raw_enabled = raw_proxy.get("enabled", False)
    if not isinstance(raw_enabled, bool):
        _raise(error_type, f"config field 'binance.futures.proxy.enabled' in {path} must be true or false")
    if not raw_enabled:
        return DISABLED_PROXY_CONFIG

    raw_base_url = raw_proxy.get("base_url")
    if not isinstance(raw_base_url, str) or not raw_base_url.strip():
        _raise(error_type, f"config field 'binance.futures.proxy.base_url' in {path} must be a non-empty string")
    base_url = normalize_proxy_base_url(raw_base_url, "binance.futures.proxy.base_url", path, error_type)

    raw_auth_header = raw_proxy.get("auth_header", DEFAULT_PROXY_AUTH_HEADER)
    if not isinstance(raw_auth_header, str) or not raw_auth_header.strip():
        _raise(error_type, f"config field 'binance.futures.proxy.auth_header' in {path} must be a non-empty string")
    auth_header = raw_auth_header.strip()
    if not HEADER_NAME_PATTERN.fullmatch(auth_header):
        _raise(error_type, f"config field 'binance.futures.proxy.auth_header' in {path} must be a valid HTTP header name")

    raw_auth_key = raw_proxy.get("auth_key")
    if not isinstance(raw_auth_key, str) or not raw_auth_key.strip():
        _raise(error_type, f"config field 'binance.futures.proxy.auth_key' in {path} must be a non-empty string")

    return BinanceProxyConfig(
        enabled=True,
        base_url=base_url,
        auth_header=auth_header,
        auth_key=raw_auth_key.strip(),
    )


def load_proxy_config_from_candidates(
    candidates: Iterable[Path],
    error_type: type[Exception] = ValueError,
) -> BinanceProxyConfig:
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise error_type(f"invalid JSON in {path}: {exc}") from exc
        except OSError as exc:
            raise error_type(f"failed to read config file {path}: {exc}") from exc
        if not isinstance(data, Mapping):
            raise error_type(f"config file {path} must contain a JSON object")

        binance = data.get("binance")
        if not isinstance(binance, Mapping):
            return DISABLED_PROXY_CONFIG
        futures = binance.get("futures")
        if not isinstance(futures, Mapping):
            return DISABLED_PROXY_CONFIG
        return parse_proxy_config(futures, path, error_type)
    return DISABLED_PROXY_CONFIG


def resolve_proxy_base_url(upstream_base_url: str, proxy_config: BinanceProxyConfig) -> str:
    if not proxy_config.enabled:
        return upstream_base_url
    normalized_upstream = upstream_base_url.rstrip("/")
    prefix = OFFICIAL_BASE_URL_TO_PROXY_PREFIX.get(normalized_upstream)
    if prefix is None:
        raise ValueError(f"no Binance proxy route is configured for upstream base URL {upstream_base_url}")
    return f"{proxy_config.base_url}{prefix}"


def add_proxy_auth_headers(headers: Mapping[str, str], proxy_config: BinanceProxyConfig) -> dict[str, str]:
    merged = dict(headers)
    if proxy_config.enabled:
        merged[proxy_config.auth_header] = proxy_config.auth_key
    return merged


def redacted_proxy_auth_headers(proxy_config: BinanceProxyConfig) -> dict[str, str]:
    if not proxy_config.enabled:
        return {}
    return {proxy_config.auth_header: redact_secret(proxy_config.auth_key)}
