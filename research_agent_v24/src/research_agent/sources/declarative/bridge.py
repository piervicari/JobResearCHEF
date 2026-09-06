#!/usr/bin/env python3
"""Source-agnostic bridge: rendered source_spec request -> FetchRequest.

Canonical Phase-2 location of the bridge first proven in Phase 1.
``runtime/jobresearchchef_bridge.py`` is a symlink to this module, so
there is exactly one implementation. Pure serializer, standard library
only (``urllib.parse`` is URL string handling, not an HTTP client).
No networking, no retry, no pacing, no cache: everything transport
stays in ``HttpFetcher``.
"""
from __future__ import annotations

import copy
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


class BridgeError(ValueError):
    """A rendered request cannot be represented as a FetchRequest."""


_SUPPORTED_METHODS = ("GET", "POST")


def _quote_rfc3986(string: str, safe: str = "", encoding: str = "utf-8",
                   errors: str = "strict") -> str:
    """quote_via-compatible encoder: strict RFC 3986, spaces as %20."""
    return quote(string, safe="", encoding=encoding, errors=errors)


def _scalar_to_text(value: object, *, param: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    raise BridgeError(
        f"query parameter {param!r} must be str/int/float/bool "
        f"(or a list thereof), got {type(value).__name__}: refusing to guess"
    )


def _fold_query_into_url(url: str, query: dict) -> str:
    """Merge ``query`` into ``url``, preserving order, repeats and fragment.

    Pre-existing query pairs in the URL come first, rendered pairs after
    them, both in insertion order. Repeated parameters (list values)
    are emitted as repeated pairs. Fragment (if any) is preserved.
    """
    pairs: list[tuple[str, str]] = []
    for key, value in query.items():
        if not isinstance(key, str) or not key:
            raise BridgeError(f"query parameter names must be non-empty strings, got {key!r}")
        if value is None:
            raise BridgeError(f"query parameter {key!r} is None: refusing to guess its encoding")
        items = list(value) if isinstance(value, (list, tuple)) else [value]
        if not items:
            raise BridgeError(f"query parameter {key!r} has an empty value list")
        for item in items:
            pairs.append((key, _scalar_to_text(item, param=key)))
    if not pairs:
        return url
    parts = urlsplit(url)
    existing = parse_qsl(parts.query, keep_blank_values=True)
    # quote_via with safe='' keeps spaces as %20 and encodes `/` too
    # (RFC 3986 form), matching the Phase-1 hand-rolled encoder
    # bit-for-bit; the urlencode default (quote_plus) would emit `+`
    # for spaces, which is equivalent on the wire but churns URLs.
    merged = urlencode(existing + pairs, doseq=True,
                       quote_via=_quote_rfc3986)  # type: ignore[arg-type]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, merged, parts.fragment))


def _default_fetch_request_cls() -> type:
    try:
        from research_agent.pipeline.http import FetchRequest
    except ImportError as exc:
        raise BridgeError(
            "the JobResearCHEF FetchRequest contract is not importable "
            f"(research_agent.pipeline.http): {exc}"
        ) from exc
    return FetchRequest


def to_fetch_request(rendered: dict, *, fetch_request_cls: type | None = None) -> Any:
    """Translate one rendered v0.1 request dict into a FetchRequest.

    ``rendered`` is the ``{method, url, headers, query, body}`` mapping
    produced by ``render_catalog_request`` / ``render_detail_request``.
    Nothing in ``rendered`` (nor any nested mapping) is mutated; every
    container placed on the FetchRequest is a fresh copy. POST bodies
    map to ``json_body`` only; ``form_body`` is never produced and no
    value is ever silently converted to it.
    """
    if not isinstance(rendered, dict):
        raise BridgeError(f"rendered request must be a dict, got {type(rendered).__name__}")
    for field in ("method", "url", "headers", "query", "body"):
        if field not in rendered:
            raise BridgeError(f"rendered request is missing required field: {field!r}")

    method = rendered["method"]
    if not isinstance(method, str) or not method.strip():
        raise BridgeError(f"method must be a non-empty string, got {method!r}")
    method = method.strip().upper()
    if method not in _SUPPORTED_METHODS:
        raise BridgeError(f"unsupported method {method!r}: v0.1 renders only GET/POST")

    url = rendered["url"]
    if not isinstance(url, str) or not url:
        raise BridgeError(f"url must be a non-empty string, got {url!r}")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise BridgeError(f"url must be absolute http(s), got {url!r}")

    headers = rendered["headers"]
    if headers is None:
        headers = {}
    if not isinstance(headers, dict):
        raise BridgeError(f"headers must be a mapping, got {type(headers).__name__}")
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise BridgeError(
                f"headers must be str->str, got {key!r}: {value!r} (no coercion)"
            )

    query = rendered["query"]
    if query is None:
        query = {}
    if not isinstance(query, dict):
        raise BridgeError(f"query must be a mapping, got {type(query).__name__}")

    body = rendered["body"]
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise BridgeError(
            "body must be a JSON object (dict) or empty; "
            f"got {type(body).__name__}: refusing to guess an encoding "
            "(and never silently converting to form-encoded)"
        )

    if method == "GET" and body:
        raise BridgeError("GET requests cannot include a request body (body is non-empty)")
    json_body: dict | None = copy.deepcopy(body) if (method == "POST" and body) else None

    final_url = _fold_query_into_url(url, query)

    cls = fetch_request_cls if fetch_request_cls is not None else _default_fetch_request_cls()
    return cls(
        final_url,
        headers=dict(headers),
        method=method,
        json_body=json_body,
        allow_cache=(method == "GET"),
    )
