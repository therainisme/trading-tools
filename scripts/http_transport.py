#!/usr/bin/env python3
"""HTTP transport helpers shared by trading-tools scripts."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.request import ProxyHandler, build_opener


SUPPORTED_PROXY_SCHEMES = {"http", "https"}


class ProxyConfigError(ValueError):
    """Raised when proxy environment variables are invalid."""


def _first_non_blank(environ: Mapping[str, str], names: tuple[str, ...]) -> tuple[str, str] | None:
    for name in names:
        value = environ.get(name)
        if value is not None and value.strip():
            return name, value.strip()
    return None


def redact_proxy_url(value: str) -> str:
    """Return a proxy URL with credentials removed for error messages."""
    parts = urlsplit(value)
    if "@" not in parts.netloc:
        if "@" in value:
            before_host, host = value.rsplit("@", 1)
            if "://" in before_host:
                scheme = before_host.split("://", 1)[0]
                return f"{scheme}://<credentials>@{host}"
            return f"<credentials>@{host}"
        return value
    host_port = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, f"<credentials>@{host_port}", parts.path, parts.query, parts.fragment))


def _validate_proxy_url(source: str, value: str) -> str:
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in SUPPORTED_PROXY_SCHEMES or not parts.netloc:
        supported = ", ".join(sorted(SUPPORTED_PROXY_SCHEMES))
        redacted = redact_proxy_url(value)
        raise ProxyConfigError(f"{source} must be an http(s) proxy URL; got {redacted!r}. Supported schemes: {supported}")
    return value


def resolve_proxy_map(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Resolve proxy environment variables into urllib's scheme proxy map."""
    env = environ if environ is not None else os.environ
    generic = _first_non_blank(env, ("PROXY", "proxy"))
    all_proxy = _first_non_blank(env, ("ALL_PROXY", "all_proxy"))
    http_proxy = _first_non_blank(env, ("HTTP_PROXY", "http_proxy"))
    https_proxy = _first_non_blank(env, ("HTTPS_PROXY", "https_proxy"))

    proxies: dict[str, str] = {}
    for scheme, specific in (("http", http_proxy), ("https", https_proxy)):
        selected = specific or all_proxy or generic
        if selected is None:
            continue
        source, value = selected
        proxies[scheme] = _validate_proxy_url(source, value)
    return proxies


def build_env_proxy_opener(environ: Mapping[str, str] | None = None) -> Any:
    """Build a urllib opener that applies supported proxy environment variables."""
    proxies = resolve_proxy_map(environ=environ)
    return build_opener(ProxyHandler(proxies))


def urlopen_with_env_proxy(request: Any, timeout: int = 15) -> Any:
    """Open a urllib Request using project-supported proxy environment variables."""
    return build_env_proxy_opener().open(request, timeout=timeout)
