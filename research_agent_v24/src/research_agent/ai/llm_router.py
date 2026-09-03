"""Provider-agnostic structured LLM routing for Research Agent.

This module intentionally copies only the fallback-routing pattern validated in the
user's News Assistant project:

- task-specific ordered routes;
- optional same-model retry for transient Google capacity/rate-limit failures;
- schema micro-repair with a cheap dedicated model before model downgrade;
- fallback to the next configured target;
- per-attempt telemetry.

No News Assistant ranking, dedupe, retrieval or evidence logic is copied here.
"""

from __future__ import annotations

import json
import os
import time
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable

import httpx

from research_agent.config import LlmRouteTargetSettings, LlmSettings


class RoutedLlmError(RuntimeError):
    """All configured routes failed or a provider request was invalid."""


class ProviderTransientError(RoutedLlmError):
    """Transient provider failure that can merit a same-target retry."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class OutputValidationError(RoutedLlmError):
    def __init__(self, message: str, *, content: str = "", validation_error: str = "") -> None:
        super().__init__(message)
        self.content = content
        self.validation_error = validation_error or message


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float | None = None


@dataclass(frozen=True)
class RoutedResult:
    data: dict
    provider: str
    model: str
    usage: TokenUsage
    response_id: str = ""
    repaired_by: str | None = None


@dataclass(frozen=True)
class RawProviderResult:
    content: str
    response_id: str
    usage: TokenUsage


class RoutedStructuredLlmClient:
    """Task router with quality-aware same-model retry and cross-provider fallback."""

    def __init__(
        self,
        settings: LlmSettings,
        *,
        event_callback: Callable[[dict], None] | None = None,
    ) -> None:
        self.settings = settings
        self.attempt_log: list[dict] = []
        self.routing_attempts: list[dict] = []
        self.event_callback = event_callback

    def _emit(self, event: dict) -> None:
        if self.event_callback is not None:
            try:
                self.event_callback(dict(event))
            except Exception:
                # Observability must never break routing.
                pass

    def _request_timeout(self, target: LlmRouteTargetSettings) -> float:
        return float(target.request_timeout_seconds or self.settings.request_timeout_seconds)

    def _start_heartbeat(
        self,
        *,
        target: LlmRouteTargetSettings,
        fallback_index: int,
        same_attempt: int,
        started: float,
    ) -> tuple[threading.Event, threading.Thread | None]:
        stop = threading.Event()
        interval = float(self.settings.progress_heartbeat_seconds)
        if self.event_callback is None or interval <= 0:
            return stop, None

        timeout = self._request_timeout(target)

        def pulse() -> None:
            while not stop.wait(interval):
                self._emit({
                    "event": "attempt_waiting",
                    "provider": target.provider,
                    "model": target.model,
                    "fallback_index": fallback_index,
                    "same_target_attempt": same_attempt,
                    "elapsed_seconds": round(time.monotonic() - started, 1),
                    "timeout_seconds": timeout,
                })

        thread = threading.Thread(target=pulse, name="llm-progress-heartbeat", daemon=True)
        thread.start()
        return stop, thread

    def route_chain(self, route_name: str) -> list[LlmRouteTargetSettings]:
        chain = list(self.settings.routing.get(route_name) or [])
        if not chain:
            raise RoutedLlmError(f"No LLM route configured for task {route_name!r}")
        return chain

    def route_description(self, route_name: str) -> list[dict]:
        return [target.model_dump(mode="json") for target in self.route_chain(route_name)]

    def chat_json(
        self,
        *,
        route_name: str,
        messages: list[dict],
        schema_name: str,
        schema: dict,
        validator: Callable[[dict], dict],
    ) -> RoutedResult:
        chain = self.route_chain(route_name)
        last_exc: Exception | None = None

        for fallback_index, target in enumerate(chain):
            max_same_target_attempts = 1 + target.transient_retries
            for same_attempt in range(1, max_same_target_attempts + 1):
                started = time.monotonic()
                self._emit({
                    "event": "attempt_start",
                    "provider": target.provider,
                    "model": target.model,
                    "thinking": target.thinking,
                    "fallback_index": fallback_index,
                    "same_target_attempt": same_attempt,
                    "timeout_seconds": self._request_timeout(target),
                })
                stop_heartbeat, heartbeat_thread = self._start_heartbeat(
                    target=target,
                    fallback_index=fallback_index,
                    same_attempt=same_attempt,
                    started=started,
                )
                try:
                    raw = self._provider_call(
                        target=target,
                        messages=messages,
                        schema_name=schema_name,
                        schema=schema,
                    )
                    stop_heartbeat.set()
                    if heartbeat_thread is not None:
                        heartbeat_thread.join(timeout=0.2)
                    try:
                        data = _validated_json(raw.content, validator)
                    except OutputValidationError as exc:
                        repaired = self._micro_repair(
                            invalid_content=exc.content,
                            validation_error=exc.validation_error,
                            schema_name=schema_name,
                            schema=schema,
                            validator=validator,
                            parent_target=target,
                            parent_fallback_index=fallback_index,
                        )
                        if repaired is not None:
                            self._record_route_attempt(
                                target,
                                fallback_index,
                                same_attempt,
                                status="success_micro_repair",
                                latency_seconds=time.monotonic() - started,
                            )
                            return repaired
                        raise

                    self._record_attempt(
                        target=target,
                        route_name=route_name,
                        fallback_index=fallback_index,
                        same_attempt=same_attempt,
                        raw=raw,
                        validated=True,
                        error="",
                        latency_seconds=time.monotonic() - started,
                    )
                    self._record_route_attempt(
                        target,
                        fallback_index,
                        same_attempt,
                        status="success",
                        latency_seconds=time.monotonic() - started,
                    )
                    return RoutedResult(
                        data=data,
                        provider=target.provider,
                        model=target.model,
                        usage=raw.usage,
                        response_id=raw.response_id,
                    )
                except Exception as exc:
                    stop_heartbeat.set()
                    if heartbeat_thread is not None:
                        heartbeat_thread.join(timeout=0.2)
                    last_exc = exc
                    can_retry_same = (
                        isinstance(exc, ProviderTransientError)
                        and same_attempt < max_same_target_attempts
                    )
                    if can_retry_same:
                        status = exc.status_code
                        retry_after = exc.retry_after_seconds
                        # Provider-specific retry discipline:
                        # - OpenRouter free/shared-pool retries are allowed only when the
                        #   provider gives an explicit Retry-After. This avoids hammering a
                        #   shared free endpoint on opaque quota/capacity failures.
                        # - Google keeps the News Assistant behavior: a 429 without
                        #   Retry-After is treated as hard quota and falls through.
                        if target.provider == "openrouter" and retry_after is None:
                            can_retry_same = False
                        elif status == 429 and retry_after is None:
                            can_retry_same = False

                    if can_retry_same:
                        base = target.retry_wait_seconds * (2 ** (same_attempt - 1))
                        wait = max(base, float(exc.retry_after_seconds or 0.0))
                        if target.max_retry_wait_seconds > 0:
                            wait = min(wait, target.max_retry_wait_seconds)
                        self._record_route_attempt(
                            target,
                            fallback_index,
                            same_attempt,
                            status="transient_retry",
                            latency_seconds=time.monotonic() - started,
                            error=f"{type(exc).__name__}: {exc}",
                            wait_seconds=wait,
                            http_status=exc.status_code,
                        )
                        self._emit({
                            "event": "retry_wait",
                            "provider": target.provider,
                            "model": target.model,
                            "fallback_index": fallback_index,
                            "same_target_attempt": same_attempt,
                            "wait_seconds": wait,
                            "http_status": exc.status_code,
                            "error": f"{type(exc).__name__}: {exc}",
                        })
                        if wait > 0:
                            time.sleep(wait)
                        continue

                    self._record_route_attempt(
                        target,
                        fallback_index,
                        same_attempt,
                        status="failed",
                        latency_seconds=time.monotonic() - started,
                        error=f"{type(exc).__name__}: {exc}",
                        http_status=(
                            exc.status_code
                            if isinstance(exc, ProviderTransientError)
                            else None
                        ),
                    )
                    break

        raise RoutedLlmError(f"All LLM routes failed for {route_name}: {last_exc}")

    def _provider_call(
        self,
        *,
        target: LlmRouteTargetSettings,
        messages: list[dict],
        schema_name: str,
        schema: dict,
    ) -> RawProviderResult:
        if target.provider == "google":
            return self._google_call(target=target, messages=messages, schema=schema)
        if target.provider == "openrouter":
            return self._openrouter_call(
                target=target,
                messages=messages,
                schema_name=schema_name,
                schema=schema,
            )
        raise RoutedLlmError(f"Unsupported LLM provider: {target.provider}")

    def _google_call(
        self,
        *,
        target: LlmRouteTargetSettings,
        messages: list[dict],
        schema: dict,
    ) -> RawProviderResult:
        api_key = (
            os.getenv(self.settings.google_api_key_env, "").strip()
            or os.getenv("GOOGLE_API_KEY", "").strip()
        )
        if not api_key:
            raise RoutedLlmError(
                f"Missing {self.settings.google_api_key_env} (or GOOGLE_API_KEY) for Google route"
            )

        system_parts: list[str] = []
        contents: list[dict] = []
        for message in messages:
            role = str(message.get("role") or "user")
            text = str(message.get("content") or "")
            if role == "system":
                if text:
                    system_parts.append(text)
                continue
            contents.append(
                {
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": text}],
                }
            )
        body: dict = {
            "contents": contents,
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                "thinkingConfig": {"thinkingLevel": target.thinking.lower()},
            },
        }
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

        url = (
            self.settings.google_base_url.rstrip("/")
            + f"/{target.model}:generateContent"
        )
        headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
        try:
            with httpx.Client(timeout=self._request_timeout(target)) as client:
                response = client.post(url, headers=headers, json=body)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderTransientError(str(exc)) from exc

        if response.status_code >= 400:
            detail = response.text[:1200]
            retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
            if response.status_code in {429, 500, 502, 503, 504}:
                raise ProviderTransientError(
                    f"Google HTTP {response.status_code}: {detail}",
                    status_code=response.status_code,
                    retry_after_seconds=retry_after,
                )
            raise RoutedLlmError(f"Google HTTP {response.status_code}: {detail}")

        body_json = response.json()
        try:
            parts = body_json["candidates"][0]["content"].get("parts") or []
            content = "".join(
                str(part.get("text"))
                for part in parts
                if isinstance(part, dict) and part.get("text") is not None
            ).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RoutedLlmError("Google response missing candidate content") from exc
        if not content:
            raise RoutedLlmError("Google response contained no text JSON")

        usage_raw = body_json.get("usageMetadata") or {}
        prompt = int(usage_raw.get("promptTokenCount", 0) or 0)
        completion = int(usage_raw.get("candidatesTokenCount", 0) or 0)
        reasoning = int(usage_raw.get("thoughtsTokenCount", 0) or 0)
        total = int(
            usage_raw.get("totalTokenCount", prompt + completion + reasoning)
            or (prompt + completion + reasoning)
        )
        return RawProviderResult(
            content=content,
            response_id=str(body_json.get("responseId") or ""),
            usage=TokenUsage(prompt, completion, total, reasoning, 0.0),
        )

    def _openrouter_call(
        self,
        *,
        target: LlmRouteTargetSettings,
        messages: list[dict],
        schema_name: str,
        schema: dict,
    ) -> RawProviderResult:
        api_key = os.getenv(self.settings.openrouter_api_key_env, "").strip()
        if not api_key:
            raise RoutedLlmError(
                f"Missing {self.settings.openrouter_api_key_env} for OpenRouter fallback"
            )
        provider_messages = list(messages)
        if target.structured_output == "json_object":
            provider_messages = provider_messages + [
                {
                    "role": "system",
                    "content": (
                        "The response must be one JSON object matching this JSON Schema exactly. "
                        "Do not omit requested job IDs and do not add prose. Schema: "
                        + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
                    ),
                }
            ]
            response_format = {"type": "json_object"}
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            }
        payload = {
            "model": target.model,
            "messages": provider_messages,
            "temperature": 0,
            "response_format": response_format,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if self.settings.http_referer:
            headers["HTTP-Referer"] = self.settings.http_referer
        if self.settings.app_title:
            headers["X-Title"] = self.settings.app_title
        url = self.settings.openrouter_base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(timeout=self._request_timeout(target)) as client:
                response = client.post(url, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderTransientError(str(exc)) from exc
        if response.status_code >= 400:
            detail = response.text[:1200]
            retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
            if response.status_code in {429, 500, 502, 503, 504}:
                raise ProviderTransientError(
                    f"OpenRouter HTTP {response.status_code}: {detail}",
                    status_code=response.status_code,
                    retry_after_seconds=retry_after,
                )
            raise RoutedLlmError(f"OpenRouter HTTP {response.status_code}: {detail}")
        body_json = response.json()
        try:
            content = body_json["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RoutedLlmError("OpenRouter response missing choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise RoutedLlmError("OpenRouter response contained no text JSON")
        usage_raw = body_json.get("usage") or {}
        prompt = int(usage_raw.get("prompt_tokens", 0) or 0)
        completion = int(usage_raw.get("completion_tokens", 0) or 0)
        total = int(usage_raw.get("total_tokens", prompt + completion) or (prompt + completion))
        details = usage_raw.get("completion_tokens_details") or {}
        reasoning = int(details.get("reasoning_tokens", 0) or 0)
        raw_cost = usage_raw.get("cost")
        try:
            cost = float(raw_cost) if raw_cost is not None else None
        except (TypeError, ValueError):
            cost = None
        return RawProviderResult(
            content=content.strip(),
            response_id=str(body_json.get("id") or ""),
            usage=TokenUsage(prompt, completion, total, reasoning, cost),
        )

    def _micro_repair(
        self,
        *,
        invalid_content: str,
        validation_error: str,
        schema_name: str,
        schema: dict,
        validator: Callable[[dict], dict],
        parent_target: LlmRouteTargetSettings,
        parent_fallback_index: int,
    ) -> RoutedResult | None:
        if not self.settings.schema_micro_repair or not invalid_content.strip():
            return None
        repair = self.settings.repair_route
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a JSON contract repair engine. Preserve semantic content exactly. "
                    "Do not re-analyze the job, invent facts, or change classifications. Repair only "
                    "JSON structure, field placement, types, cardinality and schema violations."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "validation_error": validation_error,
                        "invalid_model_answer": invalid_content,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ]
        try:
            self._emit({
                "event": "repair_start",
                "provider": repair.provider,
                "model": repair.model,
                "timeout_seconds": self._request_timeout(repair),
            })
            raw = self._provider_call(
                target=repair,
                messages=messages,
                schema_name=f"{schema_name}__repair",
                schema=schema,
            )
            data = _validated_json(raw.content, validator)
            self.attempt_log.append(
                {
                    "route": "repair",
                    "provider": repair.provider,
                    "model": repair.model,
                    "thinking": repair.thinking,
                    "repair_for_provider": parent_target.provider,
                    "repair_for_model": parent_target.model,
                    "parent_fallback_index": parent_fallback_index,
                    "validated": True,
                    "usage": asdict(raw.usage),
                }
            )
            self._emit({
                "event": "repair_result",
                "provider": repair.provider,
                "model": repair.model,
                "status": "success",
            })
            return RoutedResult(
                data=data,
                provider=parent_target.provider,
                model=parent_target.model,
                usage=raw.usage,
                response_id=raw.response_id,
                repaired_by=f"{repair.provider}/{repair.model}",
            )
        except Exception as exc:
            self.attempt_log.append(
                {
                    "route": "repair",
                    "provider": repair.provider,
                    "model": repair.model,
                    "thinking": repair.thinking,
                    "repair_for_provider": parent_target.provider,
                    "repair_for_model": parent_target.model,
                    "parent_fallback_index": parent_fallback_index,
                    "validated": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            self._emit({
                "event": "repair_result",
                "provider": repair.provider,
                "model": repair.model,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            })
            return None

    def _record_attempt(
        self,
        *,
        target: LlmRouteTargetSettings,
        route_name: str,
        fallback_index: int,
        same_attempt: int,
        raw: RawProviderResult,
        validated: bool,
        error: str,
        latency_seconds: float,
    ) -> None:
        self.attempt_log.append(
            {
                "route": route_name,
                "provider": target.provider,
                "model": target.model,
                "thinking": target.thinking,
                "fallback_index": fallback_index,
                "same_target_attempt": same_attempt,
                "validated": validated,
                "error": error,
                "usage": asdict(raw.usage),
                "response_id": raw.response_id,
                "latency_seconds": round(latency_seconds, 3),
            }
        )

    def _record_route_attempt(
        self,
        target: LlmRouteTargetSettings,
        fallback_index: int,
        same_attempt: int,
        *,
        status: str,
        latency_seconds: float,
        error: str = "",
        wait_seconds: float | None = None,
        http_status: int | None = None,
    ) -> None:
        row = {
            "provider": target.provider,
            "model": target.model,
            "thinking": target.thinking,
            "fallback_index": fallback_index,
            "same_target_attempt": same_attempt,
            "status": status,
            "latency_seconds": round(latency_seconds, 3),
        }
        if error:
            row["error"] = error
        if wait_seconds is not None:
            row["wait_seconds"] = round(wait_seconds, 3)
        if http_status is not None:
            row["http_status"] = http_status
        self.routing_attempts.append(row)
        self._emit({"event": "attempt_result", **row})


def _validated_json(content: str, validator: Callable[[dict], dict]) -> dict:
    raw = content.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
    try:
        candidate = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OutputValidationError(
            f"Model output was not parseable JSON: {exc}",
            content=content,
            validation_error=str(exc),
        ) from exc
    if not isinstance(candidate, dict):
        raise OutputValidationError(
            "Model output must be a JSON object",
            content=content,
            validation_error="top_level_not_object",
        )
    try:
        return validator(candidate)
    except Exception as exc:
        raise OutputValidationError(
            f"Model output failed local validation: {exc}",
            content=content,
            validation_error=str(exc),
        ) from exc


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    raw = value.strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None
