"""Strict structured contract for semantic job analysis."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int
    is_cybersecurity: bool | None
    needs_more_detail: bool = False
    role_family: str | None = None
    specializations: list[str] = Field(default_factory=list)
    seniority: str | None = None
    years_experience_min: float | None = Field(default=None, ge=0)
    years_experience_max: float | None = Field(default=None, ge=0)
    skills_required: list[str] = Field(default_factory=list)
    skills_preferred: list[str] = Field(default_factory=list)
    degree_requirement: str | None = None
    certifications: list[str] = Field(default_factory=list)
    short_reason: str | None = None

    @model_validator(mode="after")
    def validate_semantics(self) -> "JobAnalysis":
        if self.is_cybersecurity is None and not self.needs_more_detail:
            raise ValueError("unknown cyber relevance requires needs_more_detail=true")
        if (
            self.years_experience_min is not None
            and self.years_experience_max is not None
            and self.years_experience_max < self.years_experience_min
        ):
            raise ValueError("years_experience_max cannot be below years_experience_min")
        return self


class JobAnalysisBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jobs: list[JobAnalysis]
