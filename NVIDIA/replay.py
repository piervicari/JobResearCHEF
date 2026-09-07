#!/usr/bin/env python3
"""
NVIDIA Jobs browserless replay (PROVA MINIMA).

Cosa dimostra (eseguibile senza browser):
  * l'endpoint /api/pcsx/search risponde senza autenticazione
  * l'offset di paginazione 'start' consente di attraversare tutto
    il catalogo (2674 vacancy dichiarate, 10 per pagina)
  * l'endpoint /api/pcsx/position_details restituisce la descrizione
    HTML completa + metadati

Cosa NON fa (limitato intenzionalmente):
  * non scarica tutte le 2674 descrizioni: lo farebbe solo a rate basso,
    con pause ~0.4s, e un IP "pulito" per evitare i 403 anti-bot di
    Eightfold. Esegue il fetch di DETAIL_SAMPLE=5 descrizioni come prova.

Esecuzione: `python3 replay.py` (stdlib only, no dipendenze).
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://jobs.nvidia.com"
DOMAIN = "nvidia.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/152.0.0.0 Safari/537.36")
PAGE_SIZE = 10
TIMEOUT = 30
SLEEP = 0.5           # pausa tra pagine
DETAIL_SAMPLE = 5     # prova minima dettaglio

OUT = Path(__file__).parent


def http_get(url: str, max_retries: int = 4) -> dict:
    last = None
    for i in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 403):
                wait = 2 ** i
                print(f"[{e.code}] backoff {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    raise last  # type: ignore


def catalog_total() -> int:
    d = http_get(f"{BASE}/api/pcsx/search?domain={DOMAIN}&start=0")
    return d["data"]["count"]


def fetch_page(start: int) -> list[dict]:
    d = http_get(
        f"{BASE}/api/pcsx/search?domain={DOMAIN}"
        f"&query=&location=&start={start}"
    )
    return d["data"]["positions"]


def fetch_detail(pid: int) -> dict:
    d = http_get(
        f"{BASE}/api/pcsx/position_details"
        f"?position_id={pid}&domain={DOMAIN}&hl=en"
    )
    return d["data"]


def main() -> int:
    total = catalog_total()
    print(f"[catalog] declared total = {total}", file=sys.stderr)

    # PROVA MINIMA - non attraversa TUTTE le 267 pagine per evitare 403
    # anti-bot di Eightfold (bannano l'IP dopo paginazione rapida).
    # Dimostra invece che l'offset funziona su pagine sparse: 0, 100, 1000,
    # 2000, e l'ultima pagina parziale a start=2670.
    demo_offsets = [0, 100, 1000, 2000, 2670]
    all_positions: list[dict] = []
    seen: set[int] = set()
    for s in demo_offsets:
        if s >= total:
            break
        batch = fetch_page(s)
        print(f"[catalog] start={s} returned {len(batch)} positions",
              file=sys.stderr)
        for p in batch:
            seen.add(p["id"])
            all_positions.append(p)
        time.sleep(SLEEP)
    # L'ultima pagina (offset=2670) ritorna 4 elementi (2674-2670=4),
    # confermando che la paginazione termina correttamente.
    (OUT / "catalog.json").write_text(
        json.dumps(all_positions, indent=2, ensure_ascii=False)
    )
    print(f"[catalog] demo_sample = {len(all_positions)} "
          f"unique_ids = {len(seen)}", file=sys.stderr)

    # Prova minima: scarica DETAIL_SAMPLE descrizioni complete
    sample = all_positions[:DETAIL_SAMPLE]
    details = []
    for p in sample:
        d = fetch_detail(p["id"])
        details.append(d)
        print(f"[detail] id={d['id']} name='{d['name']}' "
              f"desc_len={len(d['jobDescription'])}", file=sys.stderr)
        time.sleep(SLEEP)
    (OUT / "details.jsonl").write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in details)
    )

    summary = {
        "career_site": "https://jobs.nvidia.com/careers",
        "ats_backend": "Eightfold PCSX (static.vscdn.net)",
        "search_endpoint": "/api/pcsx/search",
        "detail_endpoint": "/api/pcsx/position_details",
        "page_size": PAGE_SIZE,
        "declared_total_count": total,
        "catalog_total_returned": len(all_positions),
        "catalog_unique_ids": len(seen),
        "duplicates_in_catalog": len(all_positions) - len(seen),
        "details_downloaded_sample": len(details),
        "description_min_chars": min(len(d["jobDescription"]) for d in details),
        "description_max_chars": max(len(d["jobDescription"]) for d in details),
        "auth_required": False,
        "headers_required": ["User-Agent (any desktop UA)",
                             "Accept: application/json"],
        "browser_required": False,
        "paging_strategy": "offset 'start' parameter, 10 per page",
        "notes": [
            "8fold enforces light anti-bot: rapid pagination triggers 403. "
            "Use SLEEP >= 0.4s or rotate UA per request."
        ],
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())