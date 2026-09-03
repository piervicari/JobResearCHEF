"""Labeled, offline taxonomy benchmark and deterministic quality metrics."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from research_agent.pipeline.filter import VacancyFilter
from research_agent.sources.base import RawJob

VALID_STATUSES = {"INCLUDE", "REVIEW", "EXCLUDE"}


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    title: str
    description: str
    location: str
    country: str | None
    employment_type: str | None
    workplace_type: str | None
    expected_cyber: str
    expected_seniority: str
    expected_geography: str
    expected_status: str
    notes: str


@dataclass(frozen=True)
class DimensionMetrics:
    cases: int
    correct: int
    accuracy: float
    include_precision: float
    include_recall: float
    confusion: dict[str, dict[str, int]]


@dataclass(frozen=True)
class BenchmarkMismatch:
    case_id: str
    dimension: str
    expected: str
    actual: str


@dataclass(frozen=True)
class BenchmarkReport:
    generated_at: str
    dataset: str
    cases: int
    dimensions: dict[str, DimensionMetrics]
    mismatches: tuple[BenchmarkMismatch, ...]
    minimum_component_accuracy: float
    minimum_final_accuracy: float
    passed: bool


def load_benchmark(path: Path) -> tuple[BenchmarkCase, ...]:
    """Load and strictly validate a benchmark CSV."""

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {field.name for field in BenchmarkCase.__dataclass_fields__.values()}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Benchmark is missing columns: {', '.join(sorted(missing))}")
        cases: list[BenchmarkCase] = []
        seen_ids: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            case_id = row["case_id"].strip()
            if not case_id or case_id in seen_ids:
                raise ValueError(f"Invalid or duplicate case_id at row {row_number}: {case_id!r}")
            seen_ids.add(case_id)
            expected = {
                field: row[field].strip().upper()
                for field in (
                    "expected_cyber",
                    "expected_seniority",
                    "expected_geography",
                    "expected_status",
                )
            }
            invalid = {
                field: value
                for field, value in expected.items()
                if value not in VALID_STATUSES
            }
            if invalid:
                raise ValueError(f"Invalid expected status at row {row_number}: {invalid}")
            if not row["title"].strip():
                raise ValueError(f"Benchmark title is empty at row {row_number}")
            cases.append(
                BenchmarkCase(
                    case_id=case_id,
                    title=row["title"].strip(),
                    description=row["description"].strip(),
                    location=row["location"].strip(),
                    country=_optional(row["country"]),
                    employment_type=_optional(row["employment_type"]),
                    workplace_type=_optional(row["workplace_type"]),
                    expected_cyber=expected["expected_cyber"],
                    expected_seniority=expected["expected_seniority"],
                    expected_geography=expected["expected_geography"],
                    expected_status=expected["expected_status"],
                    notes=row["notes"].strip(),
                )
            )
    if not cases:
        raise ValueError("Benchmark must contain at least one case")
    return tuple(cases)


def evaluate_benchmark(
    path: Path,
    *,
    vacancy_filter: VacancyFilter | None = None,
    minimum_component_accuracy: float = 0.95,
    minimum_final_accuracy: float = 0.95,
) -> BenchmarkReport:
    """Evaluate the labeled dataset and apply explicit quality gates."""

    if not 0 <= minimum_component_accuracy <= 1 or not 0 <= minimum_final_accuracy <= 1:
        raise ValueError("Benchmark accuracy thresholds must be between 0 and 1")
    cases = load_benchmark(path)
    vacancy_filter = vacancy_filter or VacancyFilter()
    expected_by_dimension: dict[str, list[str]] = {
        name: [] for name in ("cyber", "seniority", "geography", "final")
    }
    actual_by_dimension: dict[str, list[str]] = {
        name: [] for name in expected_by_dimension
    }
    mismatches: list[BenchmarkMismatch] = []
    for case in cases:
        result = vacancy_filter.evaluate(
            RawJob(
                source="taxonomy_benchmark",
                source_job_id=case.case_id,
                source_url=f"benchmark://{case.case_id}",
                apply_url=f"benchmark://{case.case_id}",
                title=case.title,
                description=case.description,
                location=case.location,
                country=case.country,
                employment_type=case.employment_type,
                workplace_type=case.workplace_type,
            )
        )
        pairs = {
            "cyber": (case.expected_cyber, result.cyber.status),
            "seniority": (case.expected_seniority, result.seniority.status),
            "geography": (case.expected_geography, result.geography.status),
            "final": (case.expected_status, result.status),
        }
        for dimension, (expected, actual) in pairs.items():
            expected_by_dimension[dimension].append(expected)
            actual_by_dimension[dimension].append(actual)
            if expected != actual:
                mismatches.append(
                    BenchmarkMismatch(
                        case_id=case.case_id,
                        dimension=dimension,
                        expected=expected,
                        actual=actual,
                    )
                )

    dimensions = {
        name: _metrics(expected_by_dimension[name], actual_by_dimension[name])
        for name in expected_by_dimension
    }
    component_passed = all(
        dimensions[name].accuracy >= minimum_component_accuracy
        for name in ("cyber", "seniority", "geography")
    )
    passed = component_passed and dimensions["final"].accuracy >= minimum_final_accuracy
    return BenchmarkReport(
        generated_at=datetime.now(UTC).isoformat(),
        dataset=str(path.resolve()),
        cases=len(cases),
        dimensions=dimensions,
        mismatches=tuple(mismatches),
        minimum_component_accuracy=minimum_component_accuracy,
        minimum_final_accuracy=minimum_final_accuracy,
        passed=passed,
    )


def render_benchmark_markdown(report: BenchmarkReport) -> str:
    lines = [
        "# Taxonomy benchmark",
        "",
        f"- Result: **{'PASS' if report.passed else 'FAIL'}**",
        f"- Generated at: `{report.generated_at}`",
        f"- Dataset: `{report.dataset}`",
        f"- Cases: {report.cases}",
        "",
        "| Dimension | Correct | Accuracy | INCLUDE precision | INCLUDE recall |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, metrics in report.dimensions.items():
        lines.append(
            f"| {name} | {metrics.correct}/{metrics.cases} | {metrics.accuracy:.1%} | "
            f"{metrics.include_precision:.1%} | {metrics.include_recall:.1%} |"
        )
    lines.extend(
        [
            "",
            f"Component accuracy gate: {report.minimum_component_accuracy:.1%}",
            f"Final accuracy gate: {report.minimum_final_accuracy:.1%}",
            "",
            "## Mismatches",
            "",
        ]
    )
    if not report.mismatches:
        lines.append("None.")
    else:
        lines.extend(
            [
                "| Case | Dimension | Expected | Actual |",
                "|---|---|---|---|",
                *(
                    f"| {item.case_id} | {item.dimension} | {item.expected} | {item.actual} |"
                    for item in report.mismatches
                ),
            ]
        )
    return "\n".join(lines) + "\n"


def write_benchmark_json(report: BenchmarkReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _optional(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _metrics(expected: list[str], actual: list[str]) -> DimensionMetrics:
    labels = ("INCLUDE", "REVIEW", "EXCLUDE")
    confusion = {
        expected_label: {
            actual_label: sum(
                exp == expected_label and act == actual_label
                for exp, act in zip(expected, actual, strict=True)
            )
            for actual_label in labels
        }
        for expected_label in labels
    }
    correct = sum(exp == act for exp, act in zip(expected, actual, strict=True))
    true_positive = confusion["INCLUDE"]["INCLUDE"]
    false_positive = sum(
        confusion[label]["INCLUDE"] for label in labels if label != "INCLUDE"
    )
    false_negative = sum(
        confusion["INCLUDE"][label] for label in labels if label != "INCLUDE"
    )
    return DimensionMetrics(
        cases=len(expected),
        correct=correct,
        accuracy=correct / len(expected),
        include_precision=_safe_divide(true_positive, true_positive + false_positive),
        include_recall=_safe_divide(true_positive, true_positive + false_negative),
        confusion=confusion,
    )


def _safe_divide(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0
