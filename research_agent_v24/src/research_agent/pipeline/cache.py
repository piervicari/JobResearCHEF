"""Small gzip-compressed conditional HTTP cache."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class CacheEntry:
    url: str
    final_url: str
    status_code: int
    headers: dict[str, str]
    content: bytes
    stored_at: datetime

    @property
    def conditional_headers(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if etag := self.headers.get("etag"):
            result["If-None-Match"] = etag
        if modified := self.headers.get("last-modified"):
            result["If-Modified-Since"] = modified
        return result


class FileResponseCache:
    """Stores public response bodies and only a safe subset of response headers."""

    _SAFE_HEADERS = {"etag", "last-modified", "content-type", "cache-control"}

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _path(self, url: str) -> Path:
        return self.directory / f"{self._key(url)}.json.gz"

    def get(self, url: str) -> CacheEntry | None:
        path = self._path(url)
        if not path.is_file():
            return None
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
            if payload["url"] != url:
                return None
            return CacheEntry(
                url=payload["url"],
                final_url=payload["final_url"],
                status_code=int(payload["status_code"]),
                headers={str(k): str(v) for k, v in payload["headers"].items()},
                content=base64.b64decode(payload["content_base64"]),
                stored_at=datetime.fromisoformat(payload["stored_at"]),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def store(
        self,
        *,
        url: str,
        final_url: str,
        status_code: int,
        headers: dict[str, str],
        content: bytes,
    ) -> CacheEntry:
        self.directory.mkdir(parents=True, exist_ok=True)
        safe_headers = {
            key.lower(): value
            for key, value in headers.items()
            if key.lower() in self._SAFE_HEADERS
        }
        entry = CacheEntry(
            url=url,
            final_url=final_url,
            status_code=status_code,
            headers=safe_headers,
            content=content,
            stored_at=datetime.now(UTC),
        )
        payload = {
            "url": entry.url,
            "final_url": entry.final_url,
            "status_code": entry.status_code,
            "headers": entry.headers,
            "content_base64": base64.b64encode(entry.content).decode("ascii"),
            "stored_at": entry.stored_at.isoformat(),
        }
        path = self._path(url)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with gzip.open(temporary, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        temporary.replace(path)
        return entry

