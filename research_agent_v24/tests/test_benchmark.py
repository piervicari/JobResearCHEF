import csv
from pathlib import Path

import pytest

from research_agent.benchmark import evaluate_benchmark, load_benchmark
from research_agent.config import PROJECT_ROOT

BENCHMARK_PATH = PROJECT_ROOT / "data" / "benchmarks" / "taxonomy_v1.csv"


def test_taxonomy_benchmark_meets_quality_gate() -> None:
    report = evaluate_benchmark(BENCHMARK_PATH)

    assert report.cases >= 200
    assert report.passed
    assert report.dimensions["final"].accuracy >= 0.95
    assert report.dimensions["final"].include_precision >= 0.95
    assert report.dimensions["final"].include_recall >= 0.95


def test_expanded_benchmark_preserves_anchors_and_has_stratified_provenance() -> None:
    cases = load_benchmark(BENCHMARK_PATH)
    assert [case.case_id for case in cases[:46]] == [f"B{number:03d}" for number in range(1, 47)]

    adapters: set[str] = set()
    strata: set[str] = set()
    for case in cases[46:]:
        tags = dict(
            part.strip().split("=", 1)
            for part in case.notes.split(";")
            if "=" in part
        )
        assert {"adapter", "stratum", "provenance", "rationale"} <= tags.keys()
        assert all(tags[key].strip() for key in tags)
        adapters.add(tags["adapter"])
        strata.add(tags["stratum"])

    assert adapters == {
        "ashby",
        "avature",
        "greenhouse",
        "lever",
        "official_html",
        "oracle",
        "phenom",
        "smartrecruiters",
        "successfactors",
        "workday",
    }
    assert len(strata) >= 20


def test_benchmark_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    target = tmp_path / "duplicate.csv"
    with BENCHMARK_PATH.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
        fieldnames = list(rows[0])
    rows[1]["case_id"] = rows[0]["case_id"]
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows[:2])

    with pytest.raises(ValueError, match="duplicate case_id"):
        load_benchmark(target)
