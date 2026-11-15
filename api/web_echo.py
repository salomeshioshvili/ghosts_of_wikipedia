"""Does the web still say it?  (Context.dev live web search)

For one ghost (a sentence Wikipedia deleted), search the live web with Context.dev:
  1. the sentence's opening words as an exact phrase: pages that still carry the deleted wording
  2. if that finds little, the whole sentence as a natural-language search: pages on the same claim
Wikipedia itself is excluded; known Wikipedia copy sites are labelled as copies.

Each result is stored in MariaDB in `web_echo`, a system-versioned table, so every check is kept:
FOR SYSTEM_TIME ALL shows how a deleted sentence's echo on the web changes over time.

Needs CONTEXT_DEV_API_KEY in .env (free team credits: https://www.context.dev).
Endpoint used: POST https://api.context.dev/v1/web/search
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException

from common import connect

router = APIRouter()

API = "https://api.context.dev/v1/web/search"
EXCLUDE = ["wikipedia.org", "wikimedia.org", "wikidata.org"]
MIRRORS = ("wikiwand.com", "wiki2.org", "wikizero.com", "dbpedia.org", "wikimili.com", "alchetron.com",
           "everybodywiki.com", "wikibrief.org", "wiki.edu.vn", "wikiwix.com", "kiwix.org", "justapedia.org")
PHRASE_WORDS = 12

_DDL = """CREATE TABLE IF NOT EXISTS web_echo (
  page_id    INT UNSIGNED NOT NULL,
  hash       BINARY(20)   NOT NULL,
  report     JSON         NOT NULL,
  fetched_at DATETIME     NOT NULL,
  PRIMARY KEY (page_id, hash)
) WITH SYSTEM VERSIONING"""


def _search(query, key):
    body = {"query": query[:500], "numResults": 10, "excludeDomains": EXCLUDE, "timeoutMS": 25000}
    last = ""
    for attempt in range(3):
        try:
            r = requests.post(API, json=body, timeout=35,
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        except requests.RequestException as e:
            last = f"network error: {e}"
            time.sleep(1 + attempt)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            last = f"HTTP {r.status_code}"
            time.sleep(1 + 2 * attempt)
            continue
        if r.status_code in (401, 403):
            raise HTTPException(502, "Context.dev rejected the API key (check CONTEXT_DEV_API_KEY)")
        if r.status_code != 200:
            raise HTTPException(502, f"Context.dev error {r.status_code}: {r.text[:200]}")
        data = r.json()
        data = data.get("data", data)            # tolerate either envelope
        return data.get("results", []) or []
    raise HTTPException(502, f"Context.dev unreachable ({last})")


def _clean(results):
    out, seen = [], set()
    for x in results:
        url = x.get("url") or ""
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        if not url or url in seen or any(domain.endswith(d) for d in EXCLUDE):
            continue
        seen.add(url)
        out.append({"url": url, "domain": domain, "title": (x.get("title") or domain)[:200],
                    "description": (x.get("description") or "")[:300],
                    "relevance": x.get("relevance") or "low",
                    "wikipedia_copy": any(domain.endswith(m) for m in MIRRORS)})
    return out


def _phrase(text):
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    return " ".join(words[:PHRASE_WORDS])


def _verdict(exact, related):
    real = [x for x in exact if not x["wikipedia_copy"] and x["relevance"] in ("high", "medium")]
    copies = [x for x in exact if x["wikipedia_copy"]]
    if real:
        return "still_said", f"Wikipedia deleted it, but {len(real)} other page{'s' if len(real) != 1 else ''} still say it."
    if copies:
        return "only_copies", "Only copies of old Wikipedia still carry this wording."
    if related:
        return "only_related", "This exact wording is gone from the web; these pages discuss the same thing."
    return "gone", "Gone from the web too: this sentence survives only in Wikipedia's history."


def _store(page_id, hash_hex, report):
    con, cur = connect()
    try:
        cur.execute(_DDL)
        cur.execute("INSERT INTO web_echo (page_id, hash, report, fetched_at) VALUES (?, UNHEX(?), ?, UTC_TIMESTAMP()) "
                    "ON DUPLICATE KEY UPDATE report = VALUES(report), fetched_at = VALUES(fetched_at)",
                    (page_id, hash_hex, json.dumps(report, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()


def _cached(page_id, hash_hex):
    con, cur = connect()
    try:
        cur.execute(_DDL)
        cur.execute("SELECT report FROM web_echo WHERE page_id = ? AND hash = UNHEX(?)", (page_id, hash_hex))
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row[0]) if isinstance(row[0], (str, bytes)) else row[0]
    finally:
        con.close()


@router.get("/api/ghosts/{page_id}/{hash_hex}/web")
def web_echo(page_id: int, hash_hex: str, refresh: int = 0):
    """Does the web still say this deleted sentence? Cached in MariaDB unless refresh=1."""
    if not re.fullmatch(r"[0-9a-fA-F]{40}", hash_hex):
        raise HTTPException(400, "hash must be 40 hex characters")
    if not refresh:
        try:
            hit = _cached(page_id, hash_hex)
        except Exception:
            hit = None
        if hit:
            hit["cached"] = True
            return hit

    key = (os.environ.get("CONTEXT_DEV_API_KEY") or os.environ.get("CONTEXT_API_KEY") or "").strip()
    if not key:
        raise HTTPException(503, "Live web search is off: add CONTEXT_DEV_API_KEY to .env")

    con, cur = connect()
    try:
        cur.execute("SELECT text_fi FROM sentence WHERE hash = UNHEX(?)", (hash_hex,))
        row = cur.fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(404, "unknown sentence")
    text = row[0]

    t0 = time.time()
    phrase = _phrase(text)
    exact = _clean(_search(f'"{phrase}"', key))
    related = []
    if len([x for x in exact if not x["wikipedia_copy"]]) < 2:
        related = [x for x in _clean(_search(text, key)) if x["url"] not in {e["url"] for e in exact}][:5]
    status, verdict = _verdict(exact, related)
    report = {
        "page_id": page_id, "hash": hash_hex.lower(),
        "queries": {"exact_phrase": phrase, "related": text[:500] if related or len(exact) < 2 else None},
        "exact": exact[:6], "related": related,
        "status": status, "verdict": verdict,
        "source": "Context.dev web search (POST /v1/web/search)",
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "seconds": round(time.time() - t0, 1), "cached": False,
    }
    try:
        _store(page_id, hash_hex, report)
    except Exception:
        pass          # the answer still shows without the database
    return report


@router.get("/api/ghosts/{page_id}/{hash_hex}/web/history")
def web_echo_history(page_id: int, hash_hex: str):
    """Every stored check (MariaDB system versioning): how the deleted sentence's echo changed."""
    con, cur = connect()
    try:
        cur.execute(_DDL)
        cur.execute("SELECT fetched_at, JSON_VALUE(report, '$.status'), JSON_LENGTH(report, '$.exact') "
                    "FROM web_echo FOR SYSTEM_TIME ALL WHERE page_id = ? AND hash = UNHEX(?) ORDER BY fetched_at",
                    (page_id, hash_hex))
        return [{"fetched_at": f.isoformat() + "Z", "status": s, "exact_matches": n} for f, s, n in cur.fetchall()]
    finally:
        con.close()
