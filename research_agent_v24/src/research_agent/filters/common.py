"""Shared text normalization and filter result types."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def contains_term(normalized_text: str, term: str) -> bool:
    normalized_term = normalize_text(term)
    if not normalized_term:
        return False
    return f" {normalized_term} " in f" {normalized_text} "


@dataclass(frozen=True)
class FilterResult:
    status: str
    reason: str
    matched_terms: tuple[str, ...] = ()
    category: str | None = None

