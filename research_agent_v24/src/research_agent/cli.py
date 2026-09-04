"""Manual CLI entry point for the local-first MVP."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from research_agent.ai.job_analyzer import (
    OpenAICompatibleJobAnalyzer,
    analyze_pending_jobs,
    preview_pending_jobs,
    preview_semantic_cleanup_candidates,
    requeue_semantic_cleanup_candidates,
)
from research_agent.ai.job_triage import (
    RoutedJobTriageAnalyzer,
    preview_pending_triage,
    triage_pending_jobs,
)
from research_agent.company.aliases import import_company_aliases, propose_company_aliases
from research_agent.company.importer import import_master
from research_agent.company.registry_changes import (
    apply_registry_changes,
    export_synchronized_master,
    render_registry_change_report,
    write_registry_change_json,
)
from research_agent.company.tier_s_operational_sources import (
    build_resolution_summary,
    reconcile_clusters,
    render_resolution_queues_csv,
    render_terminal_summary,
    sync_operational_sources,
    write_resolution_summary_json,
    write_unmatched_csv,
)
from research_agent.config import PROJECT_ROOT, get_settings, load_yaml
from research_agent.db.backup import (
    apply_backup_retention,
    backup_sqlite_database,
    plan_backup_retention,
)
from research_agent.db.migrations import create_schema
from research_agent.db.models import JobAiAnalysis, Portal, SourceJob
from research_agent.db.recovery import render_recovery_report, restore_and_verify_sqlite_backup
from research_agent.db.session import create_db_engine
from research_agent.logging import configure_logging
from research_agent.pipeline.gates import ScanGatePolicy, assess_scan_gate
from research_agent.pipeline.discovery import persist_scan_discoveries
from research_agent.pipeline.detail_enrichment import (
    enrich_official_html_details,
    select_detail_candidates,
)
from research_agent.pipeline.pilot import prepare_pilot_database
from research_agent.pipeline.scanner import load_portal_targets, scan_portals
from research_agent.pipeline.v2_migration import prepare_legacy_source_jobs_for_v2
from research_agent.sources.ats.registry import default_adapter_registry
from research_agent.sources.linkedin.importer import ingest_linkedin_csv
from research_agent.secrets import bootstrap_persistent_env

app = typer.Typer(
    name="research-agent",
    help="Local-first cybersecurity junior/internship job research agent.",
    no_args_is_help=True,
)

DEFAULT_MASTER_PATH = (
    PROJECT_ROOT
    / "data"
    / "company_universe"
    / "master_company_universe_v1_12_stripe_greenhouse.csv"
)
DEFAULT_BENCHMARK_PATH = PROJECT_ROOT / "data" / "benchmarks" / "taxonomy_v1.csv"


DEFAULT_PILOT_COHORT_PATH = PROJECT_ROOT / "data" / "pilot" / "p0_pilot_cohort_v0_1.yaml"
DEFAULT_PILOT_DB_PATH = PROJECT_ROOT / "data" / "pilot" / "research_agent_pilot.db"


@app.command("bootstrap-secrets")
def bootstrap_secrets_command(
    force: Annotated[
        bool, typer.Option("--force", help="Replace the persistent secrets file explicitly."),
    ] = False,
) -> None:
    """Install API keys once into ~/.config/research-agent/.env without printing them."""

    result = bootstrap_persistent_env(force=force)
    if result.already_present:
        typer.echo(f"persistent_env: {result.destination}")
        typer.echo("status: already_configured")
        typer.echo("secrets_printed: false")
        return
    if result.installed:
        typer.echo(f"persistent_env: {result.destination}")
        typer.echo(f"copied_from: {result.source}")
        typer.echo("status: installed")
        typer.echo("permissions: 600-best-effort")
        typer.echo("secrets_printed: false")
        return
    typer.echo(f"persistent_env: {result.destination}")
    typer.echo("status: no_existing_env_found", err=True)
    typer.echo(
        "Create this file once with GEMINI_API_KEY and OPENROUTER_API_KEY; future ZIPs load it automatically.",
        err=True,
    )
    raise typer.Exit(code=2)


def _engine(database_url: str | None = None):
    settings = get_settings()
    configure_logging(settings.log_level)
    configured = database_url or settings.database_url
    url = make_url(configured)
    if (
        url.get_backend_name() == "sqlite"
        and url.database
        and url.database != ":memory:"
        and not Path(url.database).is_absolute()
    ):
        configured = str(url.set(database=str((PROJECT_ROOT / url.database).resolve())))
    return create_db_engine(configured)


@app.command("init-db")
def init_db(
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Create the SQLite schema without importing data."""

    engine = _engine(database_url)
    create_schema(engine)
    typer.echo(f"Database schema ready: {engine.url.render_as_string(hide_password=True)}")


@app.command("import-master")
def import_master_command(
    master_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)] = DEFAULT_MASTER_PATH,
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Import the authoritative master and build the deduplicated Portal Registry."""

    result = import_master(_engine(database_url), master_path)
    action = "already present" if result.already_imported else "imported"
    typer.echo(f"Master {action}; batch={result.import_batch_id} sha256={result.source_sha256}")
    for metric, value in asdict(result.metrics).items():
        typer.echo(f"{metric}: {value}")


@app.command("apply-registry-changes")
def apply_registry_changes_command(
    change_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    source_version: Annotated[
        str, typer.Option(help="Version label recorded on the immutable change batch.")
    ],
    master_output: Annotated[
        Path, typer.Option(help="New synchronized master path; must not already exist.")
    ],
    report: Annotated[
        Path | None, typer.Option(help="Optional Markdown audit report output.")
    ] = None,
    json_report: Annotated[
        Path | None, typer.Option(help="Optional machine-readable audit report output.")
    ] = None,
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Apply a versioned ADD/UPDATE/RETIRE registry artifact and export a new master."""

    engine = _engine(database_url)
    result = apply_registry_changes(
        engine,
        change_path,
        source_version=source_version,
    )
    output = export_synchronized_master(engine, master_output)
    rendered = render_registry_change_report(result, change_path)
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(rendered, encoding="utf-8")
    if json_report is not None:
        write_registry_change_json(result, json_report)
    typer.echo(rendered)
    typer.echo(f"synchronized_master: {output}")


@app.command("apply-runtime-registry-changes")
def apply_runtime_registry_changes_command(
    change_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    source_version: Annotated[
        str, typer.Option(help="Version label recorded on the immutable change batch.")
    ],
    database_url: Annotated[
        str | None, typer.Option(help="Runtime database to patch idempotently.")
    ] = None,
) -> None:
    """Apply reviewed registry corrections without exporting another master CSV."""

    engine = _engine(database_url)
    result = apply_registry_changes(engine, change_path, source_version=source_version)
    typer.echo(render_registry_change_report(result, change_path))
    typer.echo(
        "runtime_registry_change: "
        + ("already_applied" if result.already_applied else "applied")
    )


@app.command("sync-tier-s-operational-sources")
def sync_tier_s_operational_sources_command(
    registry_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            help="Structured operational source registry CSV (data/target_employers/tier_s_operational_sources_v1.csv).",
        ),
    ],
    unmatched_output: Annotated[
        Path,
        typer.Option(help="Where to write the unmatched-employers CSV."),
    ],
    queues_output: Annotated[
        Path,
        typer.Option(help="Where to write the resolution queues CSV (sorted by resolution_path)."),
    ],
    summary_output: Annotated[
        Path,
        typer.Option(help="Where to write the machine-readable resolution summary JSON."),
    ],
    source_version: Annotated[
        str, typer.Option(help="Version label recorded on the immutable sync batch.")
    ] = "tier_s_v1",
    skip_sync: Annotated[
        bool,
        typer.Option(help="Only reconcile and emit queues/summary; do not mutate the DB."),
    ] = False,
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Translate the Tier-S research ledger into runtime Portal / ClusterPortalMapping state.

    The sync is additive, idempotent and offline. Existing operational sources are
    never disabled or deleted; the same operational URL deduplicates against the
    existing `Portal` table; `SourceJob` and `JobAiAnalysis` rows are not touched.
    """

    engine = _engine(database_url)
    from research_agent.company.tier_s_operational_sources import read_registry

    rows = read_registry(registry_path)
    cluster_mapping, unmatched, _ = reconcile_clusters(engine, rows)
    write_unmatched_csv(unmatched, unmatched_output)
    summary = build_resolution_summary(rows, cluster_mapping=cluster_mapping)
    render_resolution_queues_csv(
        sorted(rows, key=lambda r: (r.resolution_path, r.cohort, r.employer_name, r.source_key)),
        queues_output,
    )
    write_resolution_summary_json(summary, summary_output)
    if not skip_sync:
        report = sync_operational_sources(
            engine,
            registry_path,
            cluster_mapping=cluster_mapping,
            source_version=source_version,
        )
        typer.echo(
            "tier_s_sync: "
            + ("already_applied" if report.already_applied else "applied")
            + f" batch={report.import_batch_id} "
            f"created_portals={report.created_portals} reused_portals={report.reused_portals} "
            f"created_mappings={report.created_mappings} updated_mappings={report.updated_mappings}"
        )
    typer.echo(render_terminal_summary(summary))
    typer.echo(f"unmatched_csv: {unmatched_output}")
    typer.echo(f"queues_csv: {queues_output}")
    typer.echo(f"summary_json: {summary_output}")


@app.command("import-company-aliases")
def import_company_aliases_command(
    alias_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    source_version: Annotated[
        str, typer.Option(help="Version label for this immutable alias artifact.")
    ],
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Import reviewed PROPOSED/VERIFIED company aliases with provenance."""

    result = import_company_aliases(
        _engine(database_url), alias_path, source_version=source_version
    )
    typer.echo(
        f"company_aliases: {'already imported' if result.already_imported else 'imported'} "
        f"batch={result.import_batch_id} rows={result.rows} created={result.created} "
        f"promoted={result.promoted} sha256={result.source_sha256}"
    )


@app.command("propose-company-aliases")
def propose_company_aliases_command(
    raw_company: Annotated[str, typer.Argument(help="External company name to compare.")],
    threshold: Annotated[
        float, typer.Option(min=0.0, max=1.0, help="Minimum similarity score.")
    ] = 0.72,
    limit: Annotated[int, typer.Option(min=1, max=20)] = 5,
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Suggest fuzzy company candidates without writing aliases or mappings."""

    proposals = propose_company_aliases(
        _engine(database_url), raw_company, threshold=threshold, limit=limit
    )
    if not proposals:
        typer.echo("No candidates above threshold.")
        return
    for proposal in proposals:
        typer.echo(
            f"{proposal.score:.3f}\t{proposal.corporate_cluster_id}\t"
            f"{proposal.representative_company}\t{proposal.matched_name_source}:"
            f"{proposal.matched_name}"
        )


@app.command("adapter-coverage")
def adapter_coverage_command(
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Show current Portal Registry routing without making network requests."""

    engine = _engine(database_url)
    registry = default_adapter_registry()
    targets = load_portal_targets(engine)
    counts = Counter(
        (adapter.name if (adapter := registry.select(target)) else "unsupported")
        for target in targets
    )
    typer.echo(f"active_portals: {len(targets)}")
    for adapter, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        typer.echo(f"{adapter}: {count}")





@app.command("backup-db")
def backup_db_command(
    output: Annotated[
        Path | None, typer.Option(help="Exact output path; must not already exist.")
    ] = None,
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Create an online, integrity-checked backup of the local SQLite database."""

    result = backup_sqlite_database(
        _engine(database_url),
        destination=output,
        backup_directory=PROJECT_ROOT / "data" / "backups",
    )
    typer.echo(
        f"backup: {result.path} bytes={result.size_bytes} "
        f"sha256={result.sha256} integrity={result.integrity_check}"
    )


@app.command("prune-backups")
def prune_backups_command(
    keep_last: Annotated[
        int, typer.Option(min=1, help="Always retain at least this many newest backups.")
    ] = 3,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Delete files in the displayed plan; default is dry-run."),
    ] = False,
) -> None:
    """Inspect or apply deterministic local SQLite backup retention."""

    plan = plan_backup_retention(PROJECT_ROOT / "data" / "backups", keep_last=keep_last)
    typer.echo(f"retained_backups: {len(plan.retained)}")
    typer.echo(f"deletable_backups: {len(plan.deletable)}")
    typer.echo(f"orphan_sidecars: {len(plan.orphan_sidecars)}")
    typer.echo(f"reclaimable_bytes: {plan.reclaimable_bytes}")
    for path in (*plan.deletable, *plan.orphan_sidecars):
        typer.echo(f"candidate: {path}")
    if not apply:
        typer.echo("dry_run: true; pass --apply after reviewing the exact paths")
        return
    result = apply_backup_retention(plan)
    typer.echo(f"deleted_files: {len(result.deleted)}")
    typer.echo(f"reclaimed_bytes: {result.reclaimed_bytes}")


@app.command("verify-recovery")
def verify_recovery_command(
    backup: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="Integrity-checked SQLite backup.")
    ],
    destination: Annotated[
        Path, typer.Option(help="New restore path; existing files are never overwritten.")
    ],
    report: Annotated[
        Path | None, typer.Option(help="Optional Markdown recovery evidence output.")
    ] = None,
) -> None:
    """Restore a backup to a separate path and verify checksum, integrity and row counts."""

    result = restore_and_verify_sqlite_backup(backup, destination)
    rendered = render_recovery_report(result)
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(rendered, encoding="utf-8")
    typer.echo(rendered)


@app.command("prepare-pilot-db")
def prepare_pilot_db_command(
    destination: Annotated[
        Path, typer.Option(help="Disposable clean DB for the end-to-end P0 pilot."),
    ] = DEFAULT_PILOT_DB_PATH,
    replace: Annotated[
        bool, typer.Option("--replace", help="Replace an existing pilot DB explicitly."),
    ] = False,
) -> None:
    """Copy registry/company data but clear legacy job/run state; zero external requests."""

    try:
        result = prepare_pilot_database(_engine(), destination, replace=replace)
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo("PILOT DB PREP — zero external requests")
    typer.echo(f"pilot_db: {result.path}")
    typer.echo(f"integrity_check: {result.integrity_check}")
    typer.echo(f"source_jobs: {result.source_jobs}")
    typer.echo(f"canonical_jobs: {result.canonical_jobs}")
    typer.echo(f"scan_runs: {result.scan_runs}")


def _pilot_cohort(path: Path = DEFAULT_PILOT_COHORT_PATH) -> list[dict]:
    data = load_yaml(path)
    rows = data.get("portals") or []
    if not isinstance(rows, list) or not rows:
        raise typer.BadParameter(f"pilot cohort has no portals: {path}")
    return rows


@app.command("scan-pilot")
def scan_pilot_command(
    portal_ids: Annotated[
        list[int] | None,
        typer.Option("--portal-id", help="Optional pilot portal ID; repeat up to 5 times."),
    ] = None,
    database_url: Annotated[
        str, typer.Option(help="Disposable pilot DB URL; production DB is rejected."),
    ] = "sqlite:///data/pilot/research_agent_pilot.db",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print targets/budgets without network access."),
    ] = False,
) -> None:
    """Persist a tiny low-impact cohort as PENDING_AI, stopping on access/block signals."""

    configured = portal_ids or [int(row["portal_id"]) for row in _pilot_cohort()]
    unique_portal_ids = list(dict.fromkeys(configured))
    if not unique_portal_ids or len(unique_portal_ids) > 5:
        raise typer.BadParameter("scan-pilot requires between 1 and 5 unique portals")

    settings = get_settings()
    engine = _engine(database_url)
    production_engine = _engine()
    if engine.url.render_as_string(hide_password=False) == production_engine.url.render_as_string(
        hide_password=False
    ):
        raise typer.BadParameter("scan-pilot refuses to run against the configured production DB")
    if engine.dialect.name != "sqlite" or not engine.url.database or not Path(engine.url.database).is_file():
        raise typer.BadParameter(
            "pilot DB missing; run `research-agent prepare-pilot-db --replace` first"
        )

    pilot = settings.scanner.model_copy(
        update={
            "global_concurrency": 1,
            "per_domain_concurrency": 1,
            "per_domain_min_interval_seconds": 10.0,
            "max_retries": 0,
            "jitter_seconds": 0.0,
            "max_requests_per_host_per_run": 3,
            "max_requests_per_run": 3,
            "max_pages_per_portal": 1,
            "max_jobs_per_portal": 10,
            "bulk_catalog_max_jobs_per_portal": 2000,
            "host_cooldown_hours": 72.0,
            "run_timeout_seconds": min(settings.scanner.run_timeout_seconds, 300.0),
        }
    )
    cache_directory = PROJECT_ROOT / "data" / "cache" / "http_pilot"

    targets = load_portal_targets(engine, portal_ids=set(unique_portal_ids))
    by_id = {target.portal_id: target for target in targets}
    if dry_run:
        typer.echo("P0 PILOT DRY RUN — zero network and zero LLM requests")
        typer.echo(
            "budget: concurrency=1 requests<=3/portal pages<=1 html_jobs<=10/portal "
            "bulk_catalog_records<=2000 retries=0 wait=10s"
        )
        for portal_id in unique_portal_ids:
            target = by_id.get(portal_id)
            if target is None:
                typer.echo(f"portal_id={portal_id}: NOT FOUND OR NOT SCAN-ENABLED", err=True)
                continue
            typer.echo(
                f"portal_id={portal_id} host={target.host} url={target.jobs_search_url} "
                f"ats={','.join(target.ats_families) or 'unknown'}"
            )
        return

    total_requests = 0
    total_jobs = 0
    total_new = 0
    stop_reason: str | None = None
    for index, portal_id in enumerate(unique_portal_ids, start=1):
        target = by_id.get(portal_id)
        if target is None:
            typer.echo(f"pilot_portal_{index}: {portal_id} SKIPPED target unavailable", err=True)
            continue
        typer.echo(f"pilot_portal_{index}/{len(unique_portal_ids)}: {portal_id} host={target.host}")
        scan = asyncio.run(
            scan_portals(
                engine,
                default_adapter_registry(),
                pilot,
                portal_ids={portal_id},
                allow_all=False,
                ignore_cooldowns=False,
                cache_directory=cache_directory,
                run_source="p0_low_impact_pilot",
            )
        )
        total_requests += scan.request_count
        total_jobs += scan.jobs_discovered
        result = scan.portal_results[0]
        discovery_state = (
            "JOBS_FOUND"
            if scan.jobs_discovered > 0
            else ("EMPTY_COMPLETE" if result.complete_snapshot else "EMPTY_INCOMPLETE")
        )
        typer.echo(
            "result: "
            f"status={result.status} http={result.final_http_status} "
            f"requests={scan.request_count} retries={scan.retry_count} "
            f"jobs={scan.jobs_discovered} adapter={result.adapter} discovery={discovery_state}"
        )
        if result.final_http_status in {401, 403, 429} or result.error_type in {
            "AccessChallengeError",
            "RobotsDisallowed",
        }:
            stop_reason = result.error_type or f"HTTP {result.final_http_status}"
            typer.echo(f"PILOT STOP: access/block signal detected: {stop_reason}", err=True)
            break

        gate = assess_scan_gate(
            scan,
            ScanGatePolicy(
                max_failure_rate=0.0,
                max_retry_rate=0.0,
                max_http_429=0,
                max_unexpected_empty_complete=0,
            ),
        )
        if gate.passed:
            persisted = persist_scan_discoveries(
                engine,
                scan,
                closure_missed_successful_runs=settings.scanner.closure_missed_successful_runs,
            )
            total_new += persisted.new_source_jobs
            typer.echo(
                f"persisted: new={persisted.new_source_jobs} updated={persisted.updated_source_jobs} "
                f"pending_ai={persisted.pending_ai}"
            )
        else:
            typer.echo("persisted: SKIPPED because cohort gate failed", err=True)

        if index < len(unique_portal_ids):
            time.sleep(10.0)

    typer.echo(f"pilot_total_requests: {total_requests}")
    typer.echo(f"pilot_total_jobs_observed: {total_jobs}")
    typer.echo(f"pilot_total_new_source_jobs: {total_new}")
    typer.echo("semantic_processing: NOT_RUN_BY_SCAN_PILOT")
    if stop_reason is not None:
        raise typer.Exit(code=3)


@app.command("enrich-details")
def enrich_details_command(
    database_url: Annotated[
        str, typer.Option(help="Database containing AI-classified SourceJob rows."),
    ] = "sqlite:///data/pilot/research_agent_pilot.db",
    limit: Annotated[
        int, typer.Option(min=1, max=20, help="Maximum detail pages to fetch this run."),
    ] = 5,
    min_description_chars: Annotated[
        int, typer.Option(min=0, help="Only enrich jobs with shorter effective descriptions."),
    ] = 500,
    max_jobs_per_host: Annotated[
        int, typer.Option(min=1, max=5, help="Safety cap for detail pages fetched from one host per run."),
    ] = 2,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show exact candidate URLs; zero network requests."),
    ] = False,
) -> None:
    """Selectively enrich CYBER/NEEDS_MORE_DETAIL generic jobs from official detail pages."""

    engine = _engine(database_url)
    if engine.dialect.name != "sqlite" or not engine.url.database or not Path(engine.url.database).is_file():
        raise typer.BadParameter("detail enrichment currently requires an existing file-backed SQLite DB")
    candidates = select_detail_candidates(
        engine,
        limit=limit,
        min_description_chars=min_description_chars,
        max_jobs_per_host=max_jobs_per_host,
    )
    if dry_run:
        typer.echo("DETAIL ENRICHMENT DRY RUN — zero network and zero LLM requests")
        typer.echo(
            f"selected_jobs: {len(candidates)} limit={limit} min_description_chars={min_description_chars} "
            f"max_jobs_per_host={max_jobs_per_host}"
        )
        typer.echo(
            "policy: official_html only; same-host detail URLs; CYBER first; then NEEDS_MORE_DETAIL; "
            "bounded per-host detail fetches"
        )
        for item in candidates:
            typer.echo(
                f"job_id={item.job_id} status={item.ai_status} company={item.company!r} "
                f"title={item.title!r} description_chars={item.description_chars} url={item.source_url}"
            )
        return

    settings = get_settings()

    def progress(event: dict) -> None:
        kind = event.get("event")
        candidate = event.get("candidate")
        if kind == "detail_start":
            typer.echo(
                f"DETAIL START {event.get('index')}/{event.get('count')} "
                f"job_id={candidate.job_id} status={candidate.ai_status} "
                f"company={candidate.company!r} title={candidate.title!r}"
            )
        elif kind == "detail_result":
            typer.echo(
                f"DETAIL RESULT job_id={candidate.job_id} status={event.get('status')} "
                f"description_chars={event.get('description_chars')} "
                f"parser={event.get('parser')} location={event.get('detail_location')!r}"
            )
        elif kind == "detail_error":
            typer.echo(
                f"DETAIL ERROR job_id={candidate.job_id} error={event.get('error')}", err=True
            )

    cache_directory = PROJECT_ROOT / "data" / "cache" / "http_detail"
    summary = asyncio.run(
        enrich_official_html_details(
            engine,
            settings.scanner,
            limit=limit,
            min_description_chars=min_description_chars,
            max_jobs_per_host=max_jobs_per_host,
            inter_job_wait_seconds=10.0,
            cache_directory=cache_directory,
            progress_callback=progress,
        )
    )
    for key, value in asdict(summary).items():
        typer.echo(f"{key}: {value}")




@app.command("scan-discover")
def scan_discover_command(
    portal_ids: Annotated[
        list[int] | None,
        typer.Option("--portal-id", help="Portal ID to scan; repeat for multiple portals."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="Scan at most N registry portals in stable order."),
    ] = None,
    include_disabled: Annotated[
        bool,
        typer.Option(
            "--include-disabled",
            help=(
                "Probe a portal even when its scan_enabled flag is False. "
                "Requires an explicit --portal-id; cannot be combined with --limit. "
                "Does not modify the database."
            ),
        ),
    ] = False,
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
    backup: Annotated[
        bool,
        typer.Option("--backup/--no-backup", help="Backup SQLite before network activity."),
    ] = True,
) -> None:
    """V2 scan: persist raw discoveries as PENDING_AI without semantic filtering."""

    if not portal_ids and limit is None:
        raise typer.BadParameter("select --portal-id or --limit; V2 discovery has no --all shortcut")
    if include_disabled and not portal_ids:
        raise typer.BadParameter("--include-disabled requires at least one --portal-id")
    if include_disabled and limit is not None:
        raise typer.BadParameter("--include-disabled cannot be combined with --limit")
    settings = get_settings()
    engine = _engine(database_url)
    if backup:
        backup_result = backup_sqlite_database(
            engine, backup_directory=PROJECT_ROOT / "data" / "backups"
        )
        typer.echo(f"pre_scan_backup: {backup_result.path}")

    cache_directory = settings.scanner.cache_directory
    if not cache_directory.is_absolute():
        cache_directory = PROJECT_ROOT / cache_directory
    scan = asyncio.run(
        scan_portals(
            engine,
            default_adapter_registry(),
            settings.scanner,
            portal_ids=set(portal_ids) if portal_ids else None,
            limit=limit,
            allow_all=False,
            include_disabled=include_disabled,
            cache_directory=cache_directory,
            run_source="official_portals_v2_discovery",
        )
    )
    gate = assess_scan_gate(
        scan,
        ScanGatePolicy(
            max_failure_rate=settings.scanner.gate_max_failure_rate,
            max_retry_rate=settings.scanner.gate_max_retry_rate,
            max_http_429=settings.scanner.gate_max_http_429,
            max_unexpected_empty_complete=settings.scanner.gate_max_unexpected_empty_complete,
        ),
    )
    typer.echo("scan")
    for metric, value in asdict(scan).items():
        if metric != "portal_results":
            typer.echo(f"{metric}: {value}")
    if not gate.passed:
        typer.echo("discovery_persistence: SKIPPED; inspect the cohort first", err=True)
        raise typer.Exit(code=2)
    persisted = persist_scan_discoveries(
        engine,
        scan,
        closure_missed_successful_runs=settings.scanner.closure_missed_successful_runs,
    )
    typer.echo("discovery_persistence")
    for metric, value in asdict(persisted).items():
        typer.echo(f"{metric}: {value}")


@app.command("prepare-v2-source-jobs")
def prepare_v2_source_jobs_command(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Report changes without writing them."),
    ] = False,
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Offline backfill/convert legacy source jobs for V2; zero external requests."""

    summary = prepare_legacy_source_jobs_for_v2(_engine(database_url), dry_run=dry_run)
    typer.echo("external_requests: 0")
    for metric, value in asdict(summary).items():
        typer.echo(f"{metric}: {value}")


@app.command("llm-preflight")
def llm_preflight_command(
    route: Annotated[
        str, typer.Option(help="Configured LLM route/task to inspect.")
    ] = "job_analysis",
) -> None:
    """Check local LLM credentials/configuration without making any external request."""

    import os

    settings = get_settings().llm
    if route not in settings.routing:
        raise typer.BadParameter(f"Unknown LLM route {route!r}; available={sorted(settings.routing)}")
    google_present = bool(
        os.getenv(settings.google_api_key_env, "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
    )
    openrouter_present = bool(os.getenv(settings.openrouter_api_key_env, "").strip())
    typer.echo("LLM PREFLIGHT — zero external requests")
    typer.echo(f"google_key_present: {str(google_present).lower()}")
    typer.echo(f"openrouter_key_present: {str(openrouter_present).lower()}")
    typer.echo(f"route: {route}")
    typer.echo(f"difficulty: {settings.task_difficulty.get(route, 'unspecified')}")
    typer.echo("fallback_chain:")
    for index, target in enumerate(settings.routing[route], start=1):
        typer.echo(
            f"  {index}. {target.provider}/{target.model} thinking={target.thinking} "
            f"transient_retries={target.transient_retries} "
            f"timeout={target.request_timeout_seconds or settings.request_timeout_seconds}s "
            f"output={target.structured_output}"
        )
    if not google_present and not openrouter_present:
        raise typer.Exit(code=2)


@app.command("triage-pending")
def triage_pending_command(
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="Maximum PENDING_AI jobs to triage this run."),
    ] = None,
    batch_size: Annotated[
        int | None,
        typer.Option(min=1, max=200, help="Compact triage jobs per LLM request."),
    ] = None,
    portal_ids: Annotated[
        list[int] | None,
        typer.Option("--portal-id", help="Optional portal filter; repeat as needed."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview call count; zero LLM requests."),
    ] = False,
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL."),
    ] = None,
) -> None:
    """High-recall cheap triage before full JobAnalyzer; zero career-site requests."""

    settings = get_settings()
    llm_settings = settings.llm
    route = "job_light_classification"
    effective_limit = limit or llm_settings.triage_max_jobs_per_run
    effective_batch = batch_size or llm_settings.triage_batch_size
    engine = _engine(database_url)
    rows = preview_pending_triage(engine, limit=effective_limit, portal_ids=(set(portal_ids) if portal_ids else None))

    typer.echo("AI TRIAGE DRY RUN — zero career-site requests" if dry_run else (
        f"AI TRIAGE LIVE — selected_jobs={len(rows)} batch_size={effective_batch}; "
        "career-site requests=0"
    ))
    typer.echo(f"selected_jobs: {len(rows)}")
    typer.echo(f"batch_size: {effective_batch}")
    typer.echo(f"planned_requests: {(len(rows) + effective_batch - 1) // effective_batch}")
    typer.echo("policy: high recall; only clearly NON_CYBER jobs leave the full-analysis queue")
    typer.echo("fallback_chain:")
    for index, target in enumerate(llm_settings.routing[route], start=1):
        typer.echo(
            f"  {index}. {target.provider}/{target.model} thinking={target.thinking} "
            f"transient_retries={target.transient_retries} "
            f"timeout={target.request_timeout_seconds or llm_settings.request_timeout_seconds}s "
            f"output={target.structured_output}"
        )
    for row in rows[:10]:
        typer.echo(
            f"job_id={row.job_id} company={row.company!r} title={row.title!r} "
            f"location={row.location!r} snippet_chars={len(row.description_snippet)} "
            f"metadata={row.metadata!r}"
        )
    if len(rows) > 10:
        typer.echo(f"... {len(rows) - 10} more selected jobs")
    if dry_run or not rows:
        return

    from datetime import datetime

    def stamp() -> str:
        return datetime.now().strftime("%H:%M:%S")

    def routing_progress(event: dict) -> None:
        kind = event.get("event")
        if kind == "attempt_start":
            typer.echo(
                f"[{stamp()}] TRIAGE LLM START provider={event.get('provider')} "
                f"model={event.get('model')} attempt={event.get('same_target_attempt')} "
                f"timeout={event.get('timeout_seconds')}s", err=True
            )
        elif kind == "attempt_waiting":
            typer.echo(
                f"[{stamp()}] TRIAGE LLM WAIT model={event.get('model')} "
                f"elapsed={event.get('elapsed_seconds')}s timeout={event.get('timeout_seconds')}s",
                err=True,
            )
        elif kind == "attempt_result":
            typer.echo(
                f"[{stamp()}] TRIAGE LLM RESULT provider={event.get('provider')} "
                f"model={event.get('model')} status={event.get('status')} "
                f"latency={event.get('latency_seconds')}s http={event.get('http_status', '')} "
                f"error={event.get('error', '')}", err=True
            )
        elif kind == "retry_wait":
            typer.echo(
                f"[{stamp()}] TRIAGE RETRY-WAIT model={event.get('model')} "
                f"wait={event.get('wait_seconds')}s http={event.get('http_status')}", err=True
            )
        elif kind == "repair_start":
            typer.echo(
                f"[{stamp()}] TRIAGE JSON-REPAIR START provider={event.get('provider')} "
                f"model={event.get('model')}", err=True
            )
        elif kind == "repair_result":
            typer.echo(
                f"[{stamp()}] TRIAGE JSON-REPAIR RESULT status={event.get('status')} "
                f"model={event.get('model')}", err=True
            )

    def batch_progress(event: dict) -> None:
        if event.get("event") == "batch_start":
            typer.echo(
                f"[{stamp()}] TRIAGE BATCH {event.get('batch_index')}/{event.get('batch_count')} "
                f"START jobs={event.get('jobs')}", err=True
            )
        elif event.get("event") == "batch_success":
            typer.echo(
                f"[{stamp()}] TRIAGE BATCH {event.get('batch_index')} SUCCESS "
                f"jobs={event.get('jobs')} model={event.get('model')}", err=True
            )
        elif event.get("event") == "batch_failed":
            typer.echo(
                f"[{stamp()}] TRIAGE BATCH {event.get('batch_index')} FAILED "
                f"error={event.get('error')}", err=True
            )

    analyzer = RoutedJobTriageAnalyzer(
        llm_settings, route_name=route, event_callback=routing_progress
    )
    summary = triage_pending_jobs(
        engine, analyzer, limit=effective_limit, batch_size=effective_batch,
        progress_callback=batch_progress,
        portal_ids=(set(portal_ids) if portal_ids else None),
    )
    for metric, value in asdict(summary).items():
        typer.echo(f"{metric}: {value}")
    typer.echo("routing_telemetry:")
    for attempt in analyzer.router.routing_attempts:
        typer.echo(
            "  "
            f"provider={attempt.get('provider')} model={attempt.get('model')} "
            f"status={attempt.get('status')} fallback_index={attempt.get('fallback_index')} "
            f"same_attempt={attempt.get('same_target_attempt')} "
            f"http={attempt.get('http_status')} wait={attempt.get('wait_seconds')} "
            f"error={attempt.get('error', '')!r}"
        )
    if summary.api_failures > 0:
        raise typer.Exit(code=2)


@app.command("analyze-pending")
def analyze_pending_command(
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="Maximum pending source jobs to analyze this run."),
    ] = None,
    batch_size: Annotated[
        int | None,
        typer.Option(min=1, max=50, help="Jobs per LLM request; benchmark before increasing."),
    ] = None,
    portal_ids: Annotated[
        list[int] | None,
        typer.Option("--portal-id", help="Optional portal filter; repeat as needed."),
    ] = None,
    route: Annotated[
        str,
        typer.Option(help="Configured LLM route/task. Default keeps the full fallback chain."),
    ] = "job_analysis",
    model: Annotated[
        str | None,
        typer.Option(
            help="Emergency single-model override. This DISABLES fallback routing for this run."
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview queue/batches; make zero LLM requests."),
    ] = False,
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Analyze locally queued PENDING_AI jobs; never performs career-site requests."""

    settings = get_settings()
    llm_settings = settings.llm
    if route not in llm_settings.routing:
        raise typer.BadParameter(
            f"Unknown LLM route {route!r}; available={sorted(llm_settings.routing)}"
        )
    if model is not None:
        from research_agent.config import LlmRouteTargetSettings

        provider = "google" if model.startswith("gemini-") else "openrouter"
        llm_settings = llm_settings.model_copy(
            update={
                "routing": {
                    **llm_settings.routing,
                    route: [
                        LlmRouteTargetSettings(
                            provider=provider, model=model, thinking="medium"
                        )
                    ],
                }
            }
        )
    effective_limit = limit or llm_settings.max_jobs_per_run
    effective_batch = batch_size or llm_settings.batch_size
    engine = _engine(database_url)
    preflight_rows = preview_pending_jobs(engine, limit=effective_limit, portal_ids=(set(portal_ids) if portal_ids else None))
    missing_company = sum(1 for row in preflight_rows if not row.company.strip())

    if dry_run:
        rows = preflight_rows
        typer.echo("AI DRY RUN — zero LLM requests and zero career-site requests")
        typer.echo(f"selected_jobs: {len(rows)}")
        if not rows:
            typer.echo(
                "NOTICE: no PENDING_AI jobs selected. If this is a fresh extracted package, "
                "run `research-agent prepare-canary-db --replace` before canary analysis."
            )
        typer.echo(f"batch_size: {effective_batch}")
        typer.echo(f"planned_requests: {(len(rows) + effective_batch - 1) // effective_batch}")
        typer.echo(f"missing_company: {missing_company}")
        if missing_company:
            typer.echo(
                "WARNING: legacy jobs still miss company identity; run "
                "`research-agent prepare-v2-source-jobs` before any live LLM call",
                err=True,
            )
        typer.echo(f"route: {route}")
        typer.echo(f"difficulty: {llm_settings.task_difficulty.get(route, 'unspecified')}")
        typer.echo("fallback_chain:")
        for index, target in enumerate(llm_settings.routing[route], start=1):
            typer.echo(
                f"  {index}. {target.provider}/{target.model} thinking={target.thinking} "
                f"transient_retries={target.transient_retries} "
                f"timeout={
                    target.request_timeout_seconds or llm_settings.request_timeout_seconds
                }s output={target.structured_output}"
            )
        if model is not None:
            typer.echo("WARNING: --model override disables fallback routing for this run")
        for row in rows[:10]:
            typer.echo(
                f"job_id={row.job_id} company={row.company!r} title={row.title!r} "
                f"location={row.location!r} description_chars={len(row.description)}"
            )
        if len(rows) > 10:
            typer.echo(f"... {len(rows) - 10} more selected jobs")
        return

    if missing_company:
        raise typer.BadParameter(
            f"{missing_company} selected PENDING_AI jobs have no company identity; "
            "run `research-agent prepare-v2-source-jobs` first. No LLM request was made."
        )
    if not preflight_rows:
        typer.echo(
            "AI LIVE RUN — selected_jobs=0; no LLM request made. "
            "If this is a fresh extracted package, run "
            "`research-agent prepare-canary-db --replace` first.",
            err=True,
        )
        return

    from datetime import datetime

    def _stamp() -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _routing_progress(event: dict) -> None:
        kind = event.get("event")
        if kind == "attempt_start":
            typer.echo(
                f"[{_stamp()}] LLM START provider={event.get('provider')} "
                f"model={event.get('model')} thinking={event.get('thinking')} "
                f"fallback={event.get('fallback_index')} "
                f"attempt={event.get('same_target_attempt')} "
                f"timeout={event.get('timeout_seconds')}s",
                err=True,
            )
        elif kind == "attempt_waiting":
            typer.echo(
                f"[{_stamp()}] LLM WAIT provider={event.get('provider')} "
                f"model={event.get('model')} elapsed={event.get('elapsed_seconds')}s "
                f"timeout={event.get('timeout_seconds')}s",
                err=True,
            )
        elif kind == "attempt_result":
            typer.echo(
                f"[{_stamp()}] LLM RESULT provider={event.get('provider')} "
                f"model={event.get('model')} status={event.get('status')} "
                f"latency={event.get('latency_seconds')}s "
                f"http={event.get('http_status', '')} "
                f"error={event.get('error', '')}",
                err=True,
            )
        elif kind == "retry_wait":
            typer.echo(
                f"[{_stamp()}] LLM RETRY-WAIT model={event.get('model')} "
                f"wait={event.get('wait_seconds')}s http={event.get('http_status')} "
                f"error={event.get('error', '')}",
                err=True,
            )
        elif kind == "repair_start":
            typer.echo(
                f"[{_stamp()}] LLM JSON-REPAIR START provider={event.get('provider')} "
                f"model={event.get('model')} timeout={event.get('timeout_seconds')}s",
                err=True,
            )
        elif kind == "repair_result":
            typer.echo(
                f"[{_stamp()}] LLM JSON-REPAIR RESULT provider={event.get('provider')} "
                f"model={event.get('model')} status={event.get('status')} "
                f"error={event.get('error', '')}",
                err=True,
            )

    def _batch_progress(event: dict) -> None:
        kind = event.get("event")
        if kind == "batch_start":
            typer.echo(
                f"[{_stamp()}] BATCH {event.get('batch_index')}/{event.get('batch_count')} "
                f"START jobs={event.get('jobs')} ids={event.get('job_ids')}",
                err=True,
            )
        elif kind == "batch_success":
            typer.echo(
                f"[{_stamp()}] BATCH {event.get('batch_index')} SUCCESS "
                f"jobs={event.get('jobs')} model={event.get('model')}",
                err=True,
            )
        elif kind == "batch_failed":
            typer.echo(
                f"[{_stamp()}] BATCH {event.get('batch_index')} FAILED "
                f"error={event.get('error')}",
                err=True,
            )

    typer.echo(
        f"AI LIVE RUN — selected_jobs={len(preflight_rows)} batch_size={effective_batch} "
        f"route={route}; career-site requests=0",
        err=True,
    )
    analyzer = OpenAICompatibleJobAnalyzer(
        llm_settings, route_name=route, event_callback=_routing_progress
    )
    summary = analyze_pending_jobs(
        engine,
        analyzer,
        limit=effective_limit,
        batch_size=effective_batch,
        progress_callback=_batch_progress,
        portal_ids=(set(portal_ids) if portal_ids else None),
    )
    for metric, value in asdict(summary).items():
        typer.echo(f"{metric}: {value}")
    typer.echo("routing_telemetry:")
    attempts = analyzer.router.routing_attempts
    if not attempts:
        typer.echo("  none")
    for attempt in attempts:
        typer.echo(
            "  "
            f"provider={attempt.get('provider')} model={attempt.get('model')} "
            f"thinking={attempt.get('thinking')} status={attempt.get('status')} "
            f"fallback_index={attempt.get('fallback_index')} "
            f"same_attempt={attempt.get('same_target_attempt')} "
            f"http={attempt.get('http_status')} "
            f"wait={attempt.get('wait_seconds')} "
            f"error={attempt.get('error', '')!r}"
        )
    # A partial/failed AI run must not look successful to shell automation.
    # Jobs remain durable PENDING_AI, but callers need a non-zero exit code so
    # reports/CI can distinguish "queue preserved" from "analysis completed".
    if summary.api_failures > 0:
        raise typer.Exit(code=2)


@app.command("requeue-semantic-cleanup")
def requeue_semantic_cleanup_command(
    limit: Annotated[
        int,
        typer.Option(min=1, max=500, help="Maximum inconsistent rows to requeue."),
    ] = 100,
    min_description_chars: Annotated[
        int,
        typer.Option(
            min=1,
            help="Minimum effective description length that requires a binary decision.",
        ),
    ] = 1000,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview rows only; make zero DB changes."),
    ] = False,
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Requeue fully-described NEEDS_MORE_DETAIL rows; zero network/LLM requests."""

    engine = _engine(database_url)
    candidates = preview_semantic_cleanup_candidates(
        engine,
        limit=limit,
        min_description_chars=min_description_chars,
    )
    typer.echo("AI SEMANTIC CLEANUP — zero network and zero LLM requests")
    typer.echo(
        f"selected_jobs: {len(candidates)} limit={limit} "
        f"min_description_chars={min_description_chars}"
    )
    typer.echo(
        "policy: only NEEDS_MORE_DETAIL rows that already contain a substantive "
        "description are considered inconsistent with the current binary-decision contract"
    )
    for item in candidates:
        typer.echo(
            f"job_id={item.job_id} company={item.company!r} title={item.title!r} "
            f"description_chars={item.description_chars} status={item.current_status}"
        )
    if dry_run:
        typer.echo("requeued_jobs: 0 (dry-run)")
        return
    summary = requeue_semantic_cleanup_candidates(
        engine,
        limit=limit,
        min_description_chars=min_description_chars,
    )
    typer.echo(f"requeued_jobs: {summary.requeued_jobs}")


@app.command("show-portal-jobs")
def show_portal_jobs_command(
    portal_id: Annotated[int, typer.Option("--portal-id", min=1)],
    limit: Annotated[int, typer.Option(min=1, max=2000)] = 500,
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Show current SourceJobs/statuses for one portal; zero external requests."""

    engine = _engine(database_url)
    with Session(engine) as session:
        portal = session.get(Portal, portal_id)
        if portal is None:
            raise typer.BadParameter(f"unknown portal_id={portal_id}")
        rows = session.scalars(
            select(SourceJob)
            .where(SourceJob.portal_id == portal_id, SourceJob.is_active.is_(True))
            .order_by(SourceJob.id)
            .limit(limit)
        ).all()
    counts = Counter(row.ai_status for row in rows)
    typer.echo("PORTAL JOBS — local database only; zero external requests")
    typer.echo(
        f"portal_id={portal_id} host={portal.host} url={portal.jobs_search_url} "
        f"ats={portal.ats_families_json}"
    )
    typer.echo(f"rows: {len(rows)}")
    typer.echo(f"status_counts: {dict(sorted(counts.items()))}")
    for row in rows:
        typer.echo(
            f"job_id={row.id} status={row.ai_status} "
            f"title={(row.detail_title or row.raw_title)!r} "
            f"location={(row.detail_location or row.raw_location)!r} "
            f"description_chars={len(row.detail_description or row.raw_description or '')} "
            f"source_url={row.detail_url or row.source_url}"
        )


@app.command("show-ai-results")
def show_ai_results_command(
    limit: Annotated[
        int, typer.Option(min=1, max=200, help="Maximum latest AI analyses to display.")
    ] = 20,
    full: Annotated[
        bool,
        typer.Option("--full", help="Include extracted experience, skills, degree, certifications and reason."),
    ] = False,
    status: Annotated[
        str | None,
        typer.Option(help="Optional SourceJob AI status filter: CYBER, NON_CYBER, NEEDS_MORE_DETAIL."),
    ] = None,
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Display latest structured AI results with source job context; zero external requests."""

    engine = _engine(database_url)
    normalized_status = status.strip().upper() if status else None
    allowed_statuses = {"CYBER", "NON_CYBER", "NEEDS_MORE_DETAIL"}
    if normalized_status and normalized_status not in allowed_statuses:
        raise typer.BadParameter(f"status must be one of {sorted(allowed_statuses)}")
    with Session(engine) as session:
        latest_ids = (
            select(func.max(JobAiAnalysis.id).label("latest_id"))
            .group_by(JobAiAnalysis.source_job_row_id)
            .subquery()
        )
        statement = (
            select(JobAiAnalysis, SourceJob)
            .join(latest_ids, JobAiAnalysis.id == latest_ids.c.latest_id)
            .join(SourceJob, SourceJob.id == JobAiAnalysis.source_job_row_id)
            .order_by(JobAiAnalysis.id.desc())
        )
        if normalized_status:
            statement = statement.where(SourceJob.ai_status == normalized_status)
        rows = session.execute(statement.limit(limit)).all()
    typer.echo("AI RESULTS — local database only; zero external requests")
    typer.echo(f"rows: {len(rows)}")
    for analysis, job in reversed(rows):
        import json

        payload = json.loads(analysis.analysis_json)
        role_family = payload.get("role_family")
        seniority = payload.get("seniority")
        specializations = payload.get("specializations") or []
        typer.echo(
            f"job_id={job.id} company={(job.resolved_company_name or job.raw_company)!r} "
            f"title={(job.detail_title or job.raw_title)!r} ai_status={job.ai_status} "
            f"cyber={analysis.is_cybersecurity} needs_detail={analysis.needs_more_detail} "
            f"role_family={role_family!r} seniority={seniority!r} "
            f"specializations={specializations!r} model={analysis.model!r} "
            f"detail_chars={len(job.detail_description or '')} source_chars={len(job.raw_description or '')}"
        )
        if full:
            typer.echo(
                f"  years_experience_min={payload.get('years_experience_min')!r} "
                f"years_experience_max={payload.get('years_experience_max')!r}"
            )
            typer.echo(f"  skills_required={(payload.get('skills_required') or [])!r}")
            typer.echo(f"  skills_preferred={(payload.get('skills_preferred') or [])!r}")
            typer.echo(f"  degree_requirement={payload.get('degree_requirement')!r}")
            typer.echo(f"  certifications={(payload.get('certifications') or [])!r}")
            typer.echo(f"  short_reason={payload.get('short_reason')!r}")


@app.command("ingest-linkedin-csv")
def ingest_linkedin_csv_command(
    csv_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    database_url: Annotated[
        str | None, typer.Option(help="Override the configured database URL.")
    ] = None,
) -> None:
    """Ingest user-supplied public LinkedIn jobs without scraping LinkedIn."""

    settings = get_settings()
    result = ingest_linkedin_csv(
        _engine(database_url),
        csv_path,
        closure_missed_successful_runs=settings.scanner.closure_missed_successful_runs,
    )
    typer.echo(
        f"LinkedIn CSV {'already imported' if result.already_imported else 'imported'}; "
        f"batch={result.import_batch_id} run={result.scan_run_id} rows={result.rows}"
    )
    if result.processing is not None:
        for metric, value in asdict(result.processing).items():
            typer.echo(f"{metric}: {value}")


if __name__ == "__main__":
    app()
