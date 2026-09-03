"""Deterministic vacancy text normalization."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass

from selectolax.parser import HTMLParser

from research_agent.filters.common import normalize_text
from research_agent.sources.base import RawJob


def html_to_text(value: str) -> str:
    if not value:
        return ""
    decoded = html.unescape(value)
    if "<" in decoded and ">" in decoded:
        decoded = HTMLParser(decoded).text(separator=" ")
        decoded = html.unescape(decoded)
    return " ".join(decoded.split())


def display_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", html_to_text(value))
    return " ".join(normalized.split())


def normalize_title(value: str) -> str:
    return normalize_text(display_text(value))


def normalize_location(value: str) -> str:
    parts = [normalize_text(part) for part in re.split(r"\s*\|\s*", value) if part.strip()]
    return " | ".join(sorted(dict.fromkeys(parts)))


@dataclass(frozen=True)
class NormalizedJob:
    raw: RawJob
    title: str
    normalized_title: str
    location: str
    normalized_location: str
    description: str


def normalize_job(job: RawJob) -> NormalizedJob:
    title = display_text(job.title)
    location = display_text(job.location)
    return NormalizedJob(
        raw=job,
        title=title,
        normalized_title=normalize_title(title),
        location=location,
        normalized_location=normalize_location(location),
        description=html_to_text(job.description),
    )

