"""Shared validation utilities for structured ATS adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from research_agent.pipeline.http import FetchResponse


class AdapterError(RuntimeError):
    pass


class AdapterHttpError(AdapterError):
    pass


class AdapterSchemaError(AdapterError):
    pass


def require_success(response: FetchResponse) -> None:
    if not 200 <= response.status_code < 300:
        raise AdapterHttpError(
            f"HTTP {response.status_code} from {response.requested_url} "
            f"(network status {response.network_status_code})"
        )


def require_mapping(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AdapterSchemaError(f"Expected object for {context}, got {type(value).__name__}")
    return value


def require_list(value: Any, *, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise AdapterSchemaError(f"Expected list for {context}, got {type(value).__name__}")
    return value


def parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def string_value(value: object, default: str = "") -> str:
    return value.strip() if isinstance(value, str) else default

