import json

from research_agent.ai.llm_router import (
    ProviderTransientError,
    RawProviderResult,
    RoutedStructuredLlmClient,
    TokenUsage,
)
from research_agent.config import LlmRouteTargetSettings, LlmSettings


def _settings() -> LlmSettings:
    return LlmSettings(
        routing={
            "job_analysis": [
                LlmRouteTargetSettings(
                    provider="google",
                    model="primary-google",
                    thinking="medium",
                    transient_retries=1,
                    retry_wait_seconds=0,
                    max_retry_wait_seconds=0,
                ),
                LlmRouteTargetSettings(
                    provider="openrouter",
                    model="fallback-openrouter:free",
                    thinking="medium",
                ),
            ]
        },
        repair_route=LlmRouteTargetSettings(
            provider="google", model="repair-google", thinking="minimal"
        ),
    )


def _validator(candidate: dict) -> dict:
    if candidate.get("ok") is not True:
        raise ValueError("ok must be true")
    return candidate


def test_transient_google_retries_same_model_before_fallback(monkeypatch) -> None:
    router = RoutedStructuredLlmClient(_settings())
    calls = []

    def fake_call(*, target, messages, schema_name, schema):
        calls.append((target.provider, target.model))
        if len(calls) == 1:
            raise ProviderTransientError("capacity", status_code=503)
        return RawProviderResult(json.dumps({"ok": True}), "r2", TokenUsage())

    monkeypatch.setattr(router, "_provider_call", fake_call)
    result = router.chat_json(
        route_name="job_analysis",
        messages=[{"role": "user", "content": "x"}],
        schema_name="test",
        schema={"type": "object"},
        validator=_validator,
    )

    assert result.provider == "google"
    assert result.model == "primary-google"
    assert calls == [("google", "primary-google"), ("google", "primary-google")]
    assert any(row["status"] == "transient_retry" for row in router.routing_attempts)


def test_google_429_without_retry_after_skips_same_model_retry_and_falls_back(monkeypatch) -> None:
    router = RoutedStructuredLlmClient(_settings())
    calls = []

    def fake_call(*, target, messages, schema_name, schema):
        calls.append((target.provider, target.model))
        if target.provider == "google":
            raise ProviderTransientError("quota", status_code=429, retry_after_seconds=None)
        return RawProviderResult(json.dumps({"ok": True}), "r2", TokenUsage())

    monkeypatch.setattr(router, "_provider_call", fake_call)
    result = router.chat_json(
        route_name="job_analysis",
        messages=[{"role": "user", "content": "x"}],
        schema_name="test",
        schema={"type": "object"},
        validator=_validator,
    )

    assert result.provider == "openrouter"
    assert result.model == "fallback-openrouter:free"
    assert calls == [
        ("google", "primary-google"),
        ("openrouter", "fallback-openrouter:free"),
    ]


def test_micro_repair_keeps_semantic_origin_model(monkeypatch) -> None:
    router = RoutedStructuredLlmClient(_settings())
    calls = []

    def fake_call(*, target, messages, schema_name, schema):
        calls.append((target.provider, target.model))
        if target.model == "primary-google":
            return RawProviderResult(json.dumps({"ok": False}), "bad", TokenUsage())
        if target.model == "repair-google":
            return RawProviderResult(json.dumps({"ok": True}), "repair", TokenUsage())
        raise AssertionError("fallback should not be needed after successful repair")

    monkeypatch.setattr(router, "_provider_call", fake_call)
    result = router.chat_json(
        route_name="job_analysis",
        messages=[{"role": "user", "content": "x"}],
        schema_name="test",
        schema={"type": "object"},
        validator=_validator,
    )

    assert result.provider == "google"
    assert result.model == "primary-google"
    assert result.repaired_by == "google/repair-google"
    assert calls == [
        ("google", "primary-google"),
        ("google", "repair-google"),
    ]


def test_live_event_callback_reports_start_and_result(monkeypatch) -> None:
    events = []
    settings = LlmSettings(
        routing={
            "job_analysis": [
                LlmRouteTargetSettings(
                    provider="google",
                    model="primary-google",
                    thinking="medium",
                    transient_retries=0,
                    request_timeout_seconds=12,
                )
            ]
        }
    )
    router = RoutedStructuredLlmClient(settings, event_callback=events.append)

    def fake_call(*, target, messages, schema_name, schema):
        return RawProviderResult(json.dumps({"ok": True}), "r", TokenUsage())

    monkeypatch.setattr(router, "_provider_call", fake_call)
    router.chat_json(
        route_name="job_analysis",
        messages=[{"role": "user", "content": "x"}],
        schema_name="test",
        schema={"type": "object"},
        validator=_validator,
    )

    assert events[0]["event"] == "attempt_start"
    assert events[0]["timeout_seconds"] == 12.0
    assert events[-1]["event"] == "attempt_result"
    assert events[-1]["status"] == "success"


def test_no_same_model_retry_when_target_disables_it(monkeypatch) -> None:
    settings = LlmSettings(
        routing={
            "job_analysis": [
                LlmRouteTargetSettings(
                    provider="google",
                    model="primary-google",
                    transient_retries=0,
                ),
                LlmRouteTargetSettings(
                    provider="openrouter",
                    model="fallback-openrouter:free",
                ),
            ]
        }
    )
    router = RoutedStructuredLlmClient(settings)
    calls = []

    def fake_call(*, target, messages, schema_name, schema):
        calls.append((target.provider, target.model))
        if target.provider == "google":
            raise ProviderTransientError("capacity", status_code=503)
        return RawProviderResult(json.dumps({"ok": True}), "r", TokenUsage())

    monkeypatch.setattr(router, "_provider_call", fake_call)
    result = router.chat_json(
        route_name="job_analysis",
        messages=[{"role": "user", "content": "x"}],
        schema_name="test",
        schema={"type": "object"},
        validator=_validator,
    )

    assert result.provider == "openrouter"
    assert calls == [("google", "primary-google"), ("openrouter", "fallback-openrouter:free")]


def test_openrouter_free_only_rejects_paid_model() -> None:
    import pytest

    with pytest.raises(ValueError, match="free-only"):
        LlmSettings(
            routing={
                "job_analysis": [
                    LlmRouteTargetSettings(
                        provider="openrouter",
                        model="z-ai/glm-5.3-flash",
                    )
                ]
            },
            openrouter_free_only=True,
        )


def test_openrouter_free_only_accepts_free_model() -> None:
    settings = LlmSettings(
        routing={
            "job_analysis": [
                LlmRouteTargetSettings(
                    provider="openrouter",
                    model="minimax/minimax-m3:free",
                )
            ]
        },
        openrouter_free_only=True,
    )
    assert settings.routing["job_analysis"][0].model.endswith(":free")


def test_openrouter_429_with_retry_after_retries_once_before_fallback(monkeypatch) -> None:
    settings = LlmSettings(
        routing={
            "job_analysis": [
                LlmRouteTargetSettings(
                    provider="openrouter",
                    model="minimax/minimax-m3:free",
                    transient_retries=1,
                    retry_wait_seconds=0,
                    max_retry_wait_seconds=0,
                ),
                LlmRouteTargetSettings(
                    provider="google",
                    model="fallback-google",
                    transient_retries=0,
                ),
            ]
        },
        openrouter_free_only=True,
    )
    router = RoutedStructuredLlmClient(settings)
    calls = []

    def fake_call(*, target, messages, schema_name, schema):
        calls.append((target.provider, target.model))
        if len(calls) == 1:
            raise ProviderTransientError(
                "shared pool rate limit", status_code=429, retry_after_seconds=0
            )
        return RawProviderResult(json.dumps({"ok": True}), "r2", TokenUsage())

    monkeypatch.setattr(router, "_provider_call", fake_call)
    result = router.chat_json(
        route_name="job_analysis",
        messages=[{"role": "user", "content": "x"}],
        schema_name="test",
        schema={"type": "object"},
        validator=_validator,
    )

    assert result.provider == "openrouter"
    assert result.model == "minimax/minimax-m3:free"
    assert calls == [
        ("openrouter", "minimax/minimax-m3:free"),
        ("openrouter", "minimax/minimax-m3:free"),
    ]
    assert any(row["status"] == "transient_retry" for row in router.routing_attempts)


def test_openrouter_transient_without_retry_after_falls_through(monkeypatch) -> None:
    settings = LlmSettings(
        routing={
            "job_analysis": [
                LlmRouteTargetSettings(
                    provider="openrouter",
                    model="minimax/minimax-m3:free",
                    transient_retries=1,
                ),
                LlmRouteTargetSettings(
                    provider="google",
                    model="fallback-google",
                    transient_retries=0,
                ),
            ]
        },
        openrouter_free_only=True,
    )
    router = RoutedStructuredLlmClient(settings)
    calls = []

    def fake_call(*, target, messages, schema_name, schema):
        calls.append((target.provider, target.model))
        if target.provider == "openrouter":
            raise ProviderTransientError("opaque capacity", status_code=503)
        return RawProviderResult(json.dumps({"ok": True}), "r2", TokenUsage())

    monkeypatch.setattr(router, "_provider_call", fake_call)
    result = router.chat_json(
        route_name="job_analysis",
        messages=[{"role": "user", "content": "x"}],
        schema_name="test",
        schema={"type": "object"},
        validator=_validator,
    )

    assert result.provider == "google"
    assert calls == [
        ("openrouter", "minimax/minimax-m3:free"),
        ("google", "fallback-google"),
    ]
