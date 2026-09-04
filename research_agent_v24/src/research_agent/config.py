"""Centralized configuration loading."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"
PERSISTENT_ENV_PATH = Path.home() / ".config" / "research-agent" / ".env"

# API keys are intentionally not settings fields. Shell/CI variables win; then a stable
# per-user secrets file survives project ZIP upgrades; a project-local .env remains a
# harmless optional override source for development. Never print secret values.
load_dotenv(PERSISTENT_ENV_PATH, override=False)
load_dotenv(PROJECT_ROOT / ".env", override=False)


class ScannerSettings(BaseModel):
    global_concurrency: int = Field(default=8, ge=1)
    per_domain_concurrency: int = Field(default=1, ge=1)
    per_domain_min_interval_seconds: float = Field(default=1.0, ge=0)
    request_timeout_seconds: float = Field(default=20.0, gt=0)
    max_retries: int = Field(default=2, ge=0)
    backoff_base_seconds: float = Field(default=1.0, ge=0)
    backoff_max_seconds: float = Field(default=30.0, ge=0)
    max_retry_after_seconds: float = Field(default=60.0, ge=0)
    jitter_seconds: float = Field(default=0.5, ge=0)
    max_response_bytes: int = Field(default=20_000_000, ge=1)
    max_redirects: int = Field(default=10, ge=0, le=20)
    max_requests_per_host_per_run: int = Field(default=30, ge=1)
    max_requests_per_run: int = Field(default=500, ge=1)
    max_pages_per_portal: int = Field(default=30, ge=1)
    max_jobs_per_portal: int = Field(default=500, ge=1)
    # One-shot structured catalog APIs can return hundreds of jobs in a single HTTP
    # response. Their network risk is governed by request/page budgets, not by
    # discarding records already received.
    bulk_catalog_max_jobs_per_portal: int = Field(default=5000, ge=1)
    host_cooldown_hours: float = Field(default=24.0, ge=0)
    allow_private_networks: bool = False
    allow_https_to_http_redirects: bool = False
    run_timeout_seconds: float = Field(default=1800.0, gt=0)
    gate_max_failure_rate: float = Field(default=0.10, ge=0, le=1)
    gate_max_retry_rate: float = Field(default=0.20, ge=0, le=1)
    gate_max_http_429: int = Field(default=0, ge=0)
    gate_max_unexpected_empty_complete: int = Field(default=0, ge=0)
    cache_directory: Path = Path("data/cache/http")
    closure_missed_successful_runs: int = Field(default=2, ge=2)
    user_agent: str = "research-agent-pier/0.2"
    operator_contact: str = ""

    @property
    def resolved_user_agent(self) -> str:
        contact = self.operator_contact.strip()
        return f"{self.user_agent} (+{contact})" if contact else self.user_agent


class LlmRouteTargetSettings(BaseModel):
    provider: str = "google"
    model: str
    thinking: str = "medium"
    transient_retries: int = Field(default=0, ge=0, le=3)
    retry_wait_seconds: float = Field(default=30.0, ge=0)
    max_retry_wait_seconds: float = Field(default=120.0, ge=0)
    request_timeout_seconds: float | None = Field(default=None, gt=0)
    structured_output: str = "json_schema"


class LlmSettings(BaseModel):
    # Legacy single-model fields remain for backward compatibility only. The V2
    # default path uses task-specific routing below.
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = ""
    api_key_env: str = "OPENROUTER_API_KEY"

    google_base_url: str = "https://generativelanguage.googleapis.com/v1beta/models"
    google_api_key_env: str = "GEMINI_API_KEY"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key_env: str = "OPENROUTER_API_KEY"

    request_timeout_seconds: float = Field(default=120.0, gt=0)
    batch_size: int = Field(default=10, ge=1, le=50)
    triage_batch_size: int = Field(default=100, ge=1, le=200)
    triage_max_jobs_per_run: int = Field(default=2000, ge=1)
    triage_prompt_version: str = "cyber-triage-v2"
    triage_schema_version: str = "job-triage-v1"
    max_jobs_per_run: int = Field(default=50, ge=1)
    max_description_chars: int = Field(default=20000, ge=1000)
    prompt_version: str = "cyber-job-v4"
    schema_version: str = "job-analysis-v1"
    http_referer: str = ""
    app_title: str = "Research Agent PIER"
    openrouter_free_only: bool = True

    # Task -> ordered fallback chain. Routes are deliberately explicit so a run
    # is reproducible and never silently switches to an unknown free router.
    routing: dict[str, list[LlmRouteTargetSettings]] = Field(default_factory=dict)
    task_difficulty: dict[str, str] = Field(default_factory=dict)
    repair_route: LlmRouteTargetSettings = LlmRouteTargetSettings(
        provider="google", model="gemini-3.5-flash-lite", thinking="minimal"
    )
    schema_micro_repair: bool = True
    progress_heartbeat_seconds: float = Field(default=15.0, ge=0)
    debug_dir: Path = Path("output/debug/llm_invalid")

    @model_validator(mode="after")
    def _enforce_openrouter_free_only(self) -> "LlmSettings":
        if not self.openrouter_free_only:
            return self
        targets = [target for route in self.routing.values() for target in route]
        if self.repair_route is not None:
            targets.append(self.repair_route)
        paid_openrouter = [
            target.model
            for target in targets
            if target.provider == "openrouter" and not target.model.endswith(":free")
        ]
        if paid_openrouter:
            raise ValueError(
                "OpenRouter free-only mode rejects non-:free models: "
                + ", ".join(sorted(set(paid_openrouter)))
            )
        return self


class AcceptanceSettings(BaseModel):
    rows: int = 12503
    unique_record_ids: int = 12503
    corporate_clusters: int = 11798
    resolved_clusters: int = 575
    resolved_rows: int = 1263
    unique_resolved_jobs_urls: int = 510


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_AGENT_",
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    database_url: str = "sqlite:///data/research_agent.db"
    log_level: str = "INFO"
    scanner: ScannerSettings = ScannerSettings()
    llm: LlmSettings = LlmSettings()
    master_acceptance: AcceptanceSettings = AcceptanceSettings()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return loaded


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    yaml_values = load_yaml(DEFAULT_SETTINGS_PATH)
    environment_values = AppSettings()
    for field_name in environment_values.model_fields_set:
        value = getattr(environment_values, field_name)
        if field_name in {"scanner", "llm"}:
            nested_values = dict(yaml_values.get(field_name) or {})
            nested_values.update(
                {
                    nested_name: getattr(value, nested_name)
                    for nested_name in value.model_fields_set
                }
            )
            yaml_values[field_name] = nested_values
        else:
            yaml_values[field_name] = value
    return AppSettings(**yaml_values)
