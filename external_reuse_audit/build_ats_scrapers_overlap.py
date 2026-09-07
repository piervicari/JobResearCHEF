#!/usr/bin/env python3
"""Build offline overlap: canonical JobResearCHEF company universe x ats-scrapers registry.

OFFLINE. No network. Stdlib only (csv, json, re, urllib.parse for hostname
splitting only -- no request is ever built or sent). Deterministic: all
outputs sorted; reruns produce byte-identical CSVs.

Inputs (explicit paths, read-only, never modified):
  --universe : canonical master company universe CSV (v1_12)
  --ats-dir  : local ats-scrapers/ats-companies checkout
  --commit   : provider commit SHA (recorded in output, not probed)
Outputs:
  --out-candidates : all HIGH_CONFIDENCE + CANDIDATE rows
  --out-high       : HIGH_CONFIDENCE rows only
  --out-stats      : JSON stats (stdout summary + file)

Matching principle: conservative. HIGH_CONFIDENCE requires domain/URL
evidence. Name equality alone is CANDIDATE at best. Nothing here is a
binding: verified=false, verified_at=null on every row.
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from urllib.parse import urlsplit  # hostname parsing only, no I/O

PROVIDER = "ats-scrapers"

# --- Offline support map (from repo inspection, no probing) ---
# Legacy adapters: research_agent/sources/ats/*.py
#   ashby, avature, google_careers, greenhouse, lever, oracle, phenom,
#   radancy, smartrecruiters, successfactors, workday
# Declarative v0.1 specs: runtime/sources/{mercedes=beesite, nvidia/eightfold}
LEGACY_ATS = {
    "ashby", "avature", "google", "greenhouse", "lever", "oracle",
    "phenom", "radancy", "smartrecruiters", "successfactors", "workday",
}
DECLARATIVE_ATS = {"eightfold", "beesite"}


def support_of(ats_family):
    a = (ats_family or "").lower()
    leg = a in LEGACY_ATS
    dec = a in DECLARATIVE_ATS
    if leg and dec:
        return "BOTH"
    if leg:
        return "LEGACY_SUPPORTED"
    if dec:
        return "DECLARATIVE_SUPPORTED"
    return "UNSUPPORTED"


def norm_name(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def hostname(u):
    u = (u or "").strip()
    if not u:
        return ""
    if "://" not in u:
        u = "https://" + u
    try:
        h = (urlsplit(u).hostname or "").lower()
    except Exception:
        return ""
    if h.startswith("www."):
        h = h[4:]
    return h


def norm_url(u):
    u = (u or "").strip().rstrip("/")
    if not u:
        return ""
    if "://" not in u:
        u = "https://" + u
    try:
        p = urlsplit(u)
    except Exception:
        return ""
    h = (p.hostname or "").lower()
    if h.startswith("www."):
        h = h[4:]
    out = "%s://%s%s" % (p.scheme or "https", h, (p.path or "").rstrip("/"))
    if p.query:
        out += "?" + p.query
    return out


def root_label(domain):
    # first DNS label: 'acme' for acme.com / acme.wd5... handled by caller
    return (domain or "").split(".")[0]


# Public-suffix-aware-ish eTLD+1: company token of a corporate domain.
# jobs.netflix.com -> netflix (NOT jobs). amp.com.au -> amp.
SUFFIX2 = {
    "com.au", "net.au", "org.au", "edu.au",
    "co.uk", "org.uk", "me.uk", "ltd.uk",
    "co.jp", "ne.jp", "or.jp",
    "com.br", "com.mx", "com.ar", "com.co",
    "co.in", "co.nz", "co.za", "com.sg", "com.hk", "com.tw",
    "co.kr", "co.il", "com.tr", "co.th", "com.my", "com.ph",
}

# First host labels that NEVER identify a company (job-board paths,
# vendor instance pools, generic career subdomains).
GENERIC_SUBDOMAINS = {
    "jobs", "job", "career", "careers", "careersite", "jobsite",
    "jobsearch", "careersearch", "hiring", "hr", "talent", "talents",
    "apply", "application", "applications", "applicant", "applicants",
    "candidate", "candidates", "join", "work", "people", "team", "teams",
    "board", "boards", "search", "vacancies", "vacancy", "offers",
    "employment", "myjobs", "external", "cv", "resume", "staffing",
    "workwithus", "joinus",
}
GENERIC_SUB_RE = re.compile(r"^(career\d+|wd\d+|wdc\d+|ec\d*)$")


def company_token(domain):
    """Registrable-domain first label ('acme' for jobs.acme.com / acme.com.au)."""
    labels = (domain or "").split(".")
    labels = [l for l in labels if l]
    if not labels:
        return ""
    if len(labels) >= 3 and ".".join(labels[-2:]) in SUFFIX2:
        return labels[-3]
    if len(labels) >= 2:
        return labels[-2]
    return labels[0]


def norm_slug(s):
    s = (s or "").strip().lower().split("/")[0]
    return re.sub(r"[^a-z0-9]", "", s)


def names_compatible(n_int, n_ext):
    # one contains the other (on normalized forms), min length guard
    if not n_int or not n_ext:
        return False
    if len(n_int) < 4 or len(n_ext) < 4:
        return n_int == n_ext
    return (n_int in n_ext) or (n_ext in n_int)


def load_universe(path):
    companies = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rec_id = (row.get("Record ID") or "").strip()
            employer = (row.get("Employer") or "").strip()
            canonical = (row.get("Canonical Employer") or "").strip()
            parent = (row.get("Parent Group") or "").strip()
            web = (row.get("Resolved Corporate Website") or "").strip() or (
                row.get("Corporate Website") or ""
            ).strip()
            domain = hostname(web)
            portals = set()
            for k in (
                "Resolved Jobs Search URL",
                "Resolved Careers Landing URL",
                "Careers URL",
            ):
                u = norm_url(row.get(k, ""))
                if u:
                    portals.add(u)
            name_keys = {
                n
                for n in (
                    norm_name(employer),
                    norm_name(canonical),
                    norm_name(parent),
                )
                if n
            }
            companies.append(
                {
                    "id": rec_id,
                    "name": employer,
                    "canonical": canonical,
                    "parent": parent,
                    "domain": domain,
                    "geo": (row.get("Discovery Geography") or "").strip(),
                    "portals": portals,
                    "name_keys": name_keys,
                    "main_name_key": norm_name(employer),
                }
            )
    companies.sort(key=lambda c: c["id"])
    return companies


def load_external(ats_dir):
    import glob
    import os

    rows = []
    files = sorted(glob.glob(os.path.join(ats_dir, "*.csv")))
    for path in files:
        ats = os.path.basename(path)[:-4].lower()
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fields = [c.strip() for c in (reader.fieldnames or [])]
            for r in reader:
                if not r:
                    continue
                get = lambda c: (r.get(c) or "").strip()  # noqa: E731
                if "slug" in fields:
                    slug, url, nm = get("slug"), get("url"), get("name")
                    extra = get("domain") if "domain" in fields else (
                        get("company_name") if "company_name" in fields else ""
                    )
                elif fields == ["name", "url"]:  # keka
                    nm, url = get("name"), get("url")
                    slug = root_label(hostname(url))
                    extra = ""
                elif "company_code" in fields:  # phenom
                    url, nm = get("url"), get("name")
                    slug = get("company_code")
                    extra = ""
                else:
                    continue
                if not url:
                    continue
                rows.append(
                    {
                        "ats": ats,
                        "name": nm,
                        "name_key": norm_name(nm),
                        "slug": slug,
                        "url": norm_url(url),
                        "host": hostname(url),
                        "extra": extra,
                    }
                )
    rows.sort(key=lambda r: (r["ats"], r["slug"], r["url"]))
    return rows, [os.path.basename(p) for p in files]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", required=True)
    ap.add_argument("--ats-dir", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--out-candidates", required=True)
    ap.add_argument("--out-high", required=True)
    ap.add_argument("--out-stats", required=True)
    a = ap.parse_args()

    companies = load_universe(a.universe)
    ext_rows, ext_files = load_external(a.ats_dir)

    ext_by_url = defaultdict(list)
    ext_by_name = defaultdict(list)
    ext_by_slug_tok = defaultdict(list)
    ext_by_host_tok = defaultdict(list)
    ext_eightfold = []
    for e in ext_rows:
        ext_by_url[e["url"]].append(e)
        if e["name_key"]:
            ext_by_name[e["name_key"]].append(e)
        st = norm_slug(e["slug"])
        if st:
            e["_slug_tok"] = st
            ext_by_slug_tok[st].append(e)
        ht = root_label(e["host"])
        if ht and ht not in GENERIC_SUBDOMAINS and not GENERIC_SUB_RE.match(ht):
            e["_host_tok"] = ht
            ext_by_host_tok[ht].append(e)
        if e["ats"] == "eightfold" and e["extra"]:
            ext_eightfold.append(e)

    # ambiguity: external normalized names matching >1 internal company
    name_hits = defaultdict(set)
    for c in companies:
        for nk in c["name_keys"]:
            for e in ext_by_name.get(nk, []):
                name_hits[(nk, e["ats"], e["slug"], e["url"])].add(c["id"])

    out = []  # candidate rows (HIGH + CANDIDATE)
    rejected = 0
    generic_rejected = 0
    multi_name_rejected = 0

    for c in companies:
        seen = set()  # (ats,slug,url,class) dedupe
        cid = c["id"]
        dom = c["domain"]
        dom_label = root_label(dom)

        def emit(e, klass, basis, reason):
            key = (e["ats"], e["slug"], e["url"], klass)
            if key in seen:
                return
            seen.add(key)
            out.append(
                {
                    "internal_company_id": cid,
                    "internal_company_name": c["name"],
                    "internal_domain": dom,
                    "internal_country": c["geo"],
                    "external_provider": PROVIDER,
                    "external_provider_commit": a.commit,
                    "external_ats_family": e["ats"],
                    "external_company_name": e["name"],
                    "external_slug": e["slug"],
                    "external_url": e["url"],
                    "match_class": klass,
                    "match_basis": basis,
                    "confidence_reason": reason,
                    "verified": "false",
                    "verified_at": "",
                    "jrc_support": support_of(e["ats"]),
                }
            )

        # 1) URL_EXACT -> HIGH (decisive, our own resolved portal == board URL)
        for p in sorted(c["portals"]):
            for e in ext_by_url.get(p, []):
                emit(
                    e, "HIGH_CONFIDENCE", "URL_EXACT",
                    "internal resolved portal URL equals external board URL",
                )

        # 2) eightfold `domain` column == internal domain -> HIGH
        if dom:
            for e in ext_eightfold:
                if (e["extra"] or "").lower() == dom:
                    emit(
                        e, "HIGH_CONFIDENCE", "DOMAIN_EXACT",
                        "eightfold registry domain equals internal corporate domain",
                    )

        # 3) board slug / host-token vs internal company token.
        # Internal token is the registrable-domain label (jobs.netflix.com
        # -> netflix). Path-board slugs (ashby/lever/gem) carry the company
        # token in `slug`; subdomain boards (workday/bamboohr/SF) in the
        # first host label. Generic first labels (jobs, career5, ...) prove
        # nothing and are excluded.
        itok = company_token(dom)
        if itok:
            cands = {}
            for e in ext_by_slug_tok.get(itok, []):
                if e["host"] != dom:
                    cands[id(e)] = e
            for e in ext_by_host_tok.get(itok, []):
                if e["host"] != dom:
                    cands[id(e)] = e
            for e in sorted(cands.values(),
                            key=lambda x: (x["ats"], x["slug"], x["url"])):
                if names_compatible(c["main_name_key"], e["name_key"]):
                    emit(
                        e, "HIGH_CONFIDENCE", "SLUG_PLUS_NAME",
                        "board slug/host token equals domain company token"
                        " + compatible names",
                    )
                else:
                    emit(
                        e, "CANDIDATE", "SLUG",
                        "board slug/host token equals domain company token"
                        " but names differ; inspect",
                    )

        # 4) NAME_EXACT without domain evidence -> CANDIDATE (or rejected)
        for nk in sorted(c["name_keys"]):
            for e in ext_by_name.get(nk, []):
                k = (e["ats"], e["slug"], e["url"], "HIGH_CONFIDENCE")
                if (e["ats"], e["slug"], e["url"], "HIGH_CONFIDENCE") in seen or (
                    e["ats"], e["slug"], e["url"], "CANDIDATE") in seen:
                    continue
                if len(nk) <= 2:
                    rejected += 1
                    generic_rejected += 1
                    continue
                if len(name_hits[(nk, e["ats"], e["slug"], e["url"])]) > 1:
                    rejected += 1
                    multi_name_rejected += 1
                    continue
                emit(
                    e, "CANDIDATE", "NAME_EXACT",
                    "exact normalized name match, no domain evidence; inspect",
                )

    out.sort(
        key=lambda r: (
            r["internal_company_id"],
            r["external_ats_family"],
            r["external_slug"],
            r["external_url"],
        )
    )

    # multiplicity per company
    per_company = defaultdict(list)
    for r in out:
        per_company[r["internal_company_id"]].append(r)
    for cid, lst in per_company.items():
        mult = (
            "SINGLE_SOURCE_CANDIDATE" if len(lst) == 1
            else "MULTI_SOURCE_CANDIDATE"
        )
        for r in lst:
            r["source_multiplicity"] = mult

    high = [r for r in out if r["match_class"] == "HIGH_CONFIDENCE"]
    high_ids = {r["internal_company_id"] for r in high}
    cand_only_ids = {
        r["internal_company_id"] for r in out
    } - high_ids

    fields = [
        "internal_company_id", "internal_company_name", "internal_domain",
        "internal_country", "external_provider", "external_provider_commit",
        "external_ats_family", "external_company_name", "external_slug",
        "external_url", "match_class", "match_basis", "confidence_reason",
        "verified", "verified_at", "jrc_support", "source_multiplicity",
    ]
    with open(a.out_candidates, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    with open(a.out_high, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(high)

    from collections import Counter
    ats_high = Counter()
    ats_cand = Counter()
    for r in high:
        ats_high[r["external_ats_family"]] += 1
    for r in out:
        if r["match_class"] == "CANDIDATE":
            ats_cand[r["external_ats_family"]] += 1
    multi = sum(1 for v in per_company.values() if len(v) > 1)
    multi_ats = sum(
        1 for v in per_company.values()
        if len({r["external_ats_family"] for r in v}) > 1
    )
    multi_tenant = sum(
        1 for v in per_company.values()
        if len({(r["external_ats_family"], r["external_slug"]) for r in v})
        > len({r["external_ats_family"] for r in v})
    )
    n = len(companies)
    stats = {
        "universe_rows": n,
        "external_files": len(ext_files),
        "external_rows": len(ext_rows),
        "high_companies": len(high_ids),
        "candidate_only_companies": len(cand_only_ids),
        "no_match_companies": n - len(high_ids) - len(cand_only_ids),
        "high_rows": len(high),
        "candidate_rows": len(out) - len(high),
        "rejected_pairs": rejected,
        "rejected_generic_name": generic_rejected,
        "rejected_multi_internal_match": multi_name_rejected,
        "multi_source_companies": multi,
        "multi_ats_companies": multi_ats,
        "multi_tenant_same_ats": multi_tenant,
        "ats_high_companies": dict(sorted(ats_high.items())),
        "ats_candidate_rows": dict(sorted(ats_cand.items())),
    }
    with open(a.out_stats, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, sort_keys=True)
    print(json.dumps(stats, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
