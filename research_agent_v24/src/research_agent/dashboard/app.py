"""Streamlit dashboard for jobs, coverage and scanner health."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy.engine import make_url

from research_agent.config import PROJECT_ROOT, get_settings
from research_agent.dashboard.queries import (
    adapter_coverage_rows,
    ai_cyber_job_rows,
    ai_v2_summary,
    coverage_summary,
    discovery_coverage_rows,
    high_value_unresolved_rows,
    job_activity_summary,
    job_breakdown_rows,
    job_rows,
    job_summary,
    latest_filter_counts,
    portal_rows,
    review_queue_rows,
    scan_run_rows,
    sector_coverage_rows,
    source_job_rows,
)
from research_agent.db.migrations import create_schema
from research_agent.db.session import create_db_engine


def _database_url() -> str:
    configured = os.getenv("RESEARCH_AGENT_DATABASE_URL", get_settings().database_url)
    url = make_url(configured)
    if (
        url.get_backend_name() == "sqlite"
        and url.database
        and url.database != ":memory:"
        and not Path(url.database).is_absolute()
    ):
        return str(url.set(database=str((PROJECT_ROOT / url.database).resolve())))
    return configured


@st.cache_resource
def _engine():
    engine = create_db_engine(_database_url())
    create_schema(engine)
    return engine


def main() -> None:
    st.set_page_config(page_title="RESEARCH AGENT - PIER", layout="wide")
    st.title("RESEARCH AGENT - PIER")
    st.caption("Local-first cybersecurity junior & internship research dashboard")
    st.caption(f"Database: `{_database_url()}`")
    if st.button("Refresh data"):
        st.rerun()
    engine = _engine()

    jobs_metrics = job_summary(engine)
    ai_metrics = ai_v2_summary(engine)
    coverage = coverage_summary(engine)
    st.subheader("AI-first cyber pipeline")
    ai_top = st.columns(4)
    ai_top[0].metric("Cyber active", ai_metrics["cyber"])
    ai_top[1].metric("Pending AI", ai_metrics["pending"])
    ai_top[2].metric("Needs detail", ai_metrics["needs_detail"])
    ai_top[3].metric("Non-cyber classified", ai_metrics["non_cyber"])

    top = st.columns(7)
    top[0].metric("Active jobs", jobs_metrics.active_jobs)
    top[1].metric("Included", jobs_metrics.included_active_jobs)
    top[2].metric("Needs review", jobs_metrics.review_jobs)
    top[3].metric("Resolved clusters", f"{coverage.resolved_clusters:,}")
    top[4].metric("Scannable portals", f"{coverage.scannable_portals:,}")
    top[5].metric("Healthy portals", coverage.healthy_portals)
    top[6].metric("Broken portals", coverage.broken_portals)

    ai_tab, review_tab, jobs_tab, health_tab, coverage_tab, runs_tab = st.tabs(
        ["AI Cyber V2", "Legacy review", "Legacy jobs", "Portal health", "Coverage", "Runs"]
    )
    with ai_tab:
        _render_ai_cyber(engine)
    with review_tab:
        _render_review_queue(engine)
    with jobs_tab:
        _render_jobs(engine, jobs_metrics)
    with health_tab:
        _render_health(engine)
    with coverage_tab:
        _render_coverage(engine, coverage)
    with runs_tab:
        _render_runs(engine)



def _render_ai_cyber(engine) -> None:
    st.subheader("AI-classified cybersecurity jobs")
    st.caption(
        "V2 product view: all seniorities are retained. Semantic fields come from JobAnalyzer; "
        "raw source title/location/URLs remain authoritative."
    )
    frame = pd.DataFrame(ai_cyber_job_rows(engine))
    if frame.empty:
        st.info("No active CYBER SourceJobs have been classified yet.")
        return

    filters = st.columns(4)
    companies = filters[0].multiselect("Company", sorted(frame["company"].dropna().unique()))
    seniorities = filters[1].multiselect(
        "Seniority", sorted(frame["seniority"].dropna().unique())
    )
    families = filters[2].multiselect(
        "Role family", sorted(frame["role_family"].dropna().unique())
    )
    keyword = filters[3].text_input("Search", placeholder="AppSec, IAM, Python…")

    filtered = frame
    if companies:
        filtered = filtered[filtered["company"].isin(companies)]
    if seniorities:
        filtered = filtered[filtered["seniority"].isin(seniorities)]
    if families:
        filtered = filtered[filtered["role_family"].isin(families)]
    if keyword:
        searchable = (
            filtered[[
                "title", "company", "role_family", "specializations",
                "skills_required", "skills_preferred", "location"
            ]]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
        )
        filtered = filtered[searchable.str.contains(keyword, case=False, regex=False)]

    st.dataframe(
        filtered,
        hide_index=True,
        width="stretch",
        column_config={
            "apply_url": st.column_config.LinkColumn("Apply"),
            "source_url": st.column_config.LinkColumn("Source"),
        },
    )

def _render_review_queue(engine) -> None:
    st.subheader("Actionable review queue")
    st.caption(
        "Every row includes the unresolved filter/company reason and whether lifecycle evidence is "
        "complete enough to support automatic closure."
    )
    frame = pd.DataFrame(review_queue_rows(engine))
    if frame.empty:
        st.success("No active jobs currently require review.")
        return
    signals = st.text_input(
        "Filter ambiguity signals", placeholder="geography, seniority, company…"
    )
    if signals:
        frame = frame[
            frame["ambiguity_signals"].str.contains(signals, case=False, na=False)
        ]
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        column_config={"apply_url": st.column_config.LinkColumn("Apply")},
    )


def _render_jobs(engine, metrics) -> None:
    activity = job_activity_summary(engine)
    activity_columns = st.columns(5)
    activity_columns[0].metric("Active jobs", metrics.active_jobs)
    activity_columns[1].metric("New in latest run", activity.new_jobs_latest_run)
    activity_columns[2].metric("New today", activity.new_jobs_today)
    activity_columns[3].metric(
        f"New in {activity.period_days} days", activity.new_jobs_period
    )
    activity_columns[4].metric("Closed jobs", metrics.closed_jobs)

    source_columns = st.columns(3)
    source_columns[0].metric("Official only", metrics.official_only)
    source_columns[1].metric("LinkedIn only", metrics.linkedin_only)
    source_columns[2].metric("Found on both", metrics.found_on_both)

    analytics = pd.DataFrame(job_breakdown_rows(engine))
    if not analytics.empty:
        st.subheader("Active job analytics")
        dimension = st.selectbox(
            "Breakdown",
            ["Country", "Company", "Cyber category", "Seniority", "Workplace", "Source"],
        )
        selected_breakdown = analytics[analytics["dimension"] == dimension]
        chart_rows = selected_breakdown.head(25).set_index("value")[["active_jobs"]]
        st.bar_chart(chart_rows)
        st.dataframe(selected_breakdown, hide_index=True, width="stretch")

    frame = pd.DataFrame(job_rows(engine))
    if frame.empty:
        st.info("No target or review jobs have been persisted yet.")
        latest = pd.DataFrame(latest_filter_counts(engine))
        if not latest.empty:
            st.write("Latest scan filter outcomes")
            st.dataframe(latest, hide_index=True, width="stretch")
        return

    keyword = st.text_input(
        "Search title, company or cyber category", placeholder="security, internship, bank…"
    )
    filter_columns = st.columns(6)
    country = filter_columns[0].multiselect(
        "Country", sorted(frame["country"].dropna().unique())
    )
    company = filter_columns[1].multiselect(
        "Company", sorted(frame["company"].dropna().unique())
    )
    category = filter_columns[2].multiselect(
        "Cyber category", sorted(frame["cyber_category"].dropna().unique())
    )
    seniority = filter_columns[3].multiselect(
        "Seniority", sorted(frame["seniority"].dropna().unique())
    )
    workplace = filter_columns[4].multiselect(
        "Workplace", sorted(frame["workplace_type"].dropna().unique())
    )
    source_options = sorted(
        {
            item.strip()
            for value in frame["sources"].dropna()
            for item in str(value).split(",")
            if item.strip()
        }
    )
    source = filter_columns[5].multiselect(
        "Source", source_options
    )
    secondary_filters = st.columns(3)
    status = secondary_filters[0].multiselect(
        "State", sorted(frame["filter_status"].dropna().unique())
    )
    lifecycle = secondary_filters[1].selectbox(
        "Lifecycle", ["Active", "All", "Expired"]
    )
    discovered_days = secondary_filters[2].number_input(
        "Discovered in last N days (0 = all)", min_value=0, max_value=3650, value=0
    )

    filtered = frame
    for column, selected in (
        ("country", country),
        ("company", company),
        ("cyber_category", category),
        ("seniority", seniority),
        ("workplace_type", workplace),
        ("filter_status", status),
    ):
        if selected:
            filtered = filtered[filtered[column].isin(selected)]
    if source:
        selected_sources = set(source)
        filtered = filtered[
            filtered["sources"].apply(
                lambda value: bool(
                    selected_sources
                    & {item.strip() for item in str(value).split(",") if item.strip()}
                )
            )
        ]
    if keyword:
        searchable = (
            filtered[["title", "company", "cyber_category"]]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
        )
        filtered = filtered[searchable.str.contains(keyword, case=False, regex=False)]
    if lifecycle == "Active":
        filtered = filtered[filtered["active"]]
    elif lifecycle == "Expired":
        filtered = filtered[~filtered["active"]]
    if discovered_days:
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=int(discovered_days))
        discovered = pd.to_datetime(filtered["first_seen_at"], utc=True, errors="coerce")
        filtered = filtered[discovered >= cutoff]
    st.dataframe(
        filtered,
        hide_index=True,
        width="stretch",
        column_config={"apply_url": st.column_config.LinkColumn("Apply")},
    )
    st.subheader("Source-level lifecycle evidence")
    st.caption(
        "Incomplete sources can discover jobs but cannot close them. Manual imports and generic "
        "HTML remain incomplete by design."
    )
    sources = pd.DataFrame(source_job_rows(engine))
    if not sources.empty:
        st.dataframe(
            sources,
            hide_index=True,
            width="stretch",
            column_config={"apply_url": st.column_config.LinkColumn("Apply")},
        )


def _render_coverage(engine, coverage) -> None:
    rows = st.columns(4)
    rows[0].metric("Master rows", f"{coverage.master_rows:,}")
    rows[1].metric("Corporate clusters", f"{coverage.corporate_clusters:,}")
    rows[2].metric("Resolved", f"{coverage.resolved_clusters:,}")
    rows[3].metric("Unresolved", f"{coverage.unresolved_clusters:,}")
    portal_metrics = st.columns(5)
    portal_metrics[0].metric("Unique portals", coverage.unique_portals)
    portal_metrics[1].metric("Ever scanned", coverage.scanned_portals)
    portal_metrics[2].metric("Scannable", coverage.scannable_portals)
    portal_metrics[3].metric("Suspended", coverage.suspended_portals)
    portal_metrics[4].metric("Stale route", coverage.stale_portals)
    health_metrics = st.columns(4)
    health_metrics[0].metric("Healthy", coverage.healthy_portals)
    health_metrics[1].metric("Degraded", coverage.degraded_portals)
    health_metrics[2].metric("Broken", coverage.broken_portals)
    health_metrics[3].metric("Unknown health", coverage.unknown_portals)
    st.subheader("Coverage by adapter")
    st.dataframe(
        pd.DataFrame(adapter_coverage_rows(engine)), hide_index=True, width="stretch"
    )
    st.subheader("Portal Registry")
    st.dataframe(pd.DataFrame(portal_rows(engine)), hide_index=True, width="stretch")
    st.subheader("Discovery coverage (not vacancy geography)")
    st.caption(
        "These values describe how companies entered the master. Vacancy geography is filtered "
        "separately at job level."
    )
    st.dataframe(
        pd.DataFrame(discovery_coverage_rows(engine)),
        hide_index=True,
        width="stretch",
    )
    st.subheader("Coverage by sector")
    st.dataframe(
        pd.DataFrame(sector_coverage_rows(engine)), hide_index=True, width="stretch"
    )
    st.subheader("High-value unresolved clusters")
    st.caption("Deterministic shortlist for reviewed portal-resolution work; no network is used.")
    st.dataframe(
        pd.DataFrame(high_value_unresolved_rows(engine)), hide_index=True, width="stretch"
    )


def _render_health(engine) -> None:
    portals = pd.DataFrame(portal_rows(engine))
    if portals.empty:
        st.info("No portals are registered.")
        return
    filters = st.columns(3)
    issues = filters[0].multiselect(
        "Issue category", sorted(portals["issue_category"].dropna().unique())
    )
    access = filters[1].multiselect(
        "Access state", sorted(portals["access_state"].dropna().unique())
    )
    adapters = filters[2].multiselect(
        "Adapter", sorted(portals["latest_adapter"].dropna().unique())
    )
    for column, selected in (
        ("issue_category", issues),
        ("access_state", access),
        ("latest_adapter", adapters),
    ):
        if selected:
            portals = portals[portals[column].isin(selected)]
    st.dataframe(
        portals,
        hide_index=True,
        width="stretch",
        column_config={"jobs_url": st.column_config.LinkColumn("Jobs URL")},
    )


def _render_runs(engine) -> None:
    runs = pd.DataFrame(scan_run_rows(engine))
    if runs.empty:
        st.info("No scanner runs recorded yet.")
        return
    latest = runs.iloc[0]
    latest_metrics = st.columns(6)
    latest_metrics[0].metric("Latest run", int(latest["run_id"]))
    latest_metrics[1].metric("Duration (s)", latest["duration_seconds"])
    latest_metrics[2].metric("Requests", int(latest["requests"]))
    latest_metrics[3].metric("Failed domains", int(latest["failed_domains"]))
    latest_metrics[4].metric("Parser failures", int(latest["parser_failures"]))
    latest_metrics[5].metric(
        "Empty anomalies", int(latest["unexpected_empty_complete"])
    )
    st.dataframe(runs, hide_index=True, width="stretch")
    numeric = [
        "requests",
        "retries",
        "http_2xx",
        "http_3xx",
        "http_4xx",
        "http_5xx",
        "http_429",
        "failed_domains",
        "parser_failures",
        "unexpected_empty_complete",
        "jobs_discovered",
        "new_jobs",
        "updated_jobs",
        "closed_jobs",
    ]
    st.line_chart(runs.sort_values("run_id").set_index("run_id")[numeric])


if __name__ == "__main__":
    main()
