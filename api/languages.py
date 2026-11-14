"""Same story, every language.

For one Wikipedia article, ask each language edition (live, via the MediaWiki API):
  - what it calls the topic now (title + first sentence),
  - every other name that redirects to it,
  - every time the title was renamed, and whether a rename was undone,
  - how often the page was locked (protection log),
  - how many of its last 500 edits were reverted.
From that we raise neutral "conflict signals". They measure editing behaviour; they
never say which name is right.

Reports are cached in MariaDB in a system-versioned table (lang_compare), so every
refresh is kept: FOR SYSTEM_TIME ALL shows how the world's names for a topic changed.
Gemma (via Featherless, if FEATHERLESS_API_KEY is set) adds English meanings.
"""
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Body, HTTPException, Query

from common import connect  # pipeline/common.py (main.py puts it on sys.path and loads .env)

router = APIRouter()

UA = {"User-Agent": "GhostsOfWikipedia/0.1 (https://github.com/salomeshioshvili/ghosts_of_wikipedia; Junction 2026 hackathon)"}
_WIKI_SLOTS = threading.Semaphore(16)      # be polite: at most 16 Wikipedia requests in flight
_STATS = {"requests": 0, "retries": 0, "slowest": 0.0, "waited": 0.0}
_STATS_LOCK = threading.Lock()
_KEY_LOCKS: dict = {}
_KEY_LOCKS_GUARD = threading.Lock()
# Shown first when available; the article's own language is always included.
PRIORITY = ["en", "fi", "sv", "ru", "uk", "de", "pl", "be", "et", "fr", "es", "it", "zh", "ja", "ar", "he", "tr"]
MAX_LANGS = 12
MAX_NAME_CHECKS = 10          # most move logs we read per language
REVERT_TAGS = {"mw-reverted", "mw-undo", "mw-rollback", "mw-manual-revert"}
CACHE_HOURS = 24

_DDL = """CREATE TABLE IF NOT EXISTS lang_compare (
  query_key  VARCHAR(400) NOT NULL PRIMARY KEY,   -- '<lang>:<title>'
  report     JSON NOT NULL,
  fetched_at DATETIME NOT NULL
) WITH SYSTEM VERSIONING"""


# ---------- MediaWiki ----------

class WikiError(RuntimeError):
    pass


def _make_session():
    # One shared pool of keep-alive connections for every thread and every comparison:
    # opening a new TLS connection per request was most of the time (2-6 s each on Windows).
    from requests.adapters import HTTPAdapter
    sess = requests.Session()
    sess.headers.update(UA)
    sess.trust_env = False   # skip Windows proxy lookups, which can cost seconds per request
    adapter = HTTPAdapter(pool_connections=40, pool_maxsize=16)
    sess.mount("https://", adapter)
    return sess


_SESSION = _make_session()


def _session():
    return _SESSION


def wapi(lang, **params):
    """One MediaWiki API call. Raises WikiError with Wikipedia's own message when it refuses."""
    last = "no response"
    for attempt in range(4):
        try:
            t_wait = time.time()
            with _WIKI_SLOTS:
                t0 = time.time()
                r = _session().get(f"https://{lang}.wikipedia.org/w/api.php",
                                   params={"format": "json", "formatversion": 2, "maxlag": 5, **params},
                                   timeout=20)
            with _STATS_LOCK:
                _STATS["requests"] += 1
                _STATS["waited"] += t0 - t_wait
                _STATS["slowest"] = max(_STATS["slowest"], time.time() - t0)
        except requests.RequestException as e:
            last = f"network error: {e}"
            time.sleep(1 + attempt)
            continue
        if r.status_code in (429, 503):
            with _STATS_LOCK:
                _STATS["retries"] += 1
            last = f"HTTP {r.status_code} (rate limited)"
            time.sleep(float(r.headers.get("Retry-After", 1 + 2 * attempt)))
            continue
        if r.status_code != 200:
            raise WikiError(f"HTTP {r.status_code} from {lang}.wikipedia.org: {r.text[:150]}")
        data = r.json()
        err = data.get("error")
        if err:
            if err.get("code") == "maxlag":
                with _STATS_LOCK:
                    _STATS["retries"] += 1
                last = "Wikipedia busy (maxlag)"
                time.sleep(1 + attempt)
                continue
            raise WikiError(f"{lang}.wikipedia.org: {err.get('code')}: {err.get('info', '')[:150]}")
        if "query" not in data and params.get("action") == "query":
            raise WikiError(f"{lang}.wikipedia.org returned no data: {str(data)[:150]}")
        return data
    raise WikiError(f"{lang}.wikipedia.org: gave up after retries ({last})")


def editions(lang, title):
    """{lang: {title, name, autonym}} for every language edition of the article."""
    data = wapi(lang, action="query", prop="langlinks", titles=title, redirects=1,
                lllimit="max", llprop="langname|autonym", llinlanguagecode="en")
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        raise HTTPException(404, f"No article called “{title}” on {lang}.wikipedia.org")
    page = pages[0]
    out = {lang: {"title": page["title"], "name": None, "autonym": None}}
    for l in page.get("langlinks", []):
        out[l["lang"]] = {"title": l["title"], "name": l.get("langname"), "autonym": l.get("autonym")}
    return out


def pick_languages(source, available, wanted=None):
    if wanted:
        return [l for l in wanted if l in available][:MAX_LANGS] or [source]
    ordered = [source] + [l for l in PRIORITY if l in available and l != source]
    ordered += sorted(l for l in available if l not in ordered)
    return ordered[:MAX_LANGS]


def edition_report(lang, title):
    """Everything we measure for one language edition."""
    title_in = title
    with ThreadPoolExecutor(3) as pool:
        f_base = pool.submit(wapi, lang, action="query", titles=title, redirects=1,
                             prop="redirects|revisions|extracts|info", rdlimit="max",
                             rvlimit=500, rvprop="timestamp|tags", exintro=1, explaintext=1, exchars=320)
        f_prot = pool.submit(wapi, lang, action="query", list="logevents", letype="protect",
                             letitle=title, lelimit=100)
        f_move = pool.submit(wapi, lang, action="query", list="logevents", letype="move",
                             letitle=title, lelimit=50)
        base, prot, first_moves = f_base.result(), f_prot.result(), f_move.result()
    page = base["query"]["pages"][0]
    title = page["title"]
    names = [r["title"] for r in page.get("redirects", [])]
    revs = page.get("revisions", [])
    reverted = sum(1 for r in revs if REVERT_TAGS & set(r.get("tags", [])))

    protects = prot["query"]["logevents"] if page["title"] == title_in else \
        wapi(lang, action="query", list="logevents", letype="protect", letitle=page["title"], lelimit=100)["query"]["logevents"]

    # Renames: every move is logged under the title it moved *from*. Start with the current title
    # and a few old names (old titles survive as redirects), then follow the titles it was moved to,
    # so a rename that was undone is always found. Bounded to MAX_NAME_CHECKS lookups.
    known = {title, *names}
    renames, seen, checked = [], set(), set()
    queue = [title] + names[:4]

    def move_log(t):
        if t == title and t == title_in:
            return first_moves["query"]["logevents"]
        return wapi(lang, action="query", list="logevents", letype="move", letitle=t, lelimit=50)["query"]["logevents"]

    with ThreadPoolExecutor(4) as pool:
        while queue and len(checked) < MAX_NAME_CHECKS:
            batch = [t for t in dict.fromkeys(queue) if t not in checked][: MAX_NAME_CHECKS - len(checked)]
            queue = []
            checked.update(batch)
            for events in pool.map(move_log, batch):
                for e in events:
                    target = (e.get("params") or {}).get("target_title")
                    key = (e["timestamp"], e["title"], target)
                    if target in known and key not in seen:
                        seen.add(key)
                        renames.append({"ts": e["timestamp"], "from": e["title"], "to": target,
                                        "reason": e.get("comment") or None})
                        if target not in checked:
                            queue.append(target)
    renames.sort(key=lambda m: m["ts"])

    # A rename is "undone" when the page later moves straight back; that move is its reversal.
    for i, m in enumerate(renames):
        if m.get("reverses"):
            continue
        back = next((n for n in renames[i + 1:]
                     if n["from"] == m["to"] and n["to"] == m["from"] and not n.get("reverses")), None)
        if back:
            back["reverses"] = True
            m["undone_after_hours"] = round((_dt(back["ts"]) - _dt(m["ts"])).total_seconds() / 3600, 2)

    return {
        "lang": lang,
        "title": title,
        "url": f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}",
        "first_sentence": (page.get("extract") or "").strip() or None,
        "names": names,
        "renames": renames,
        "locks": len(protects),
        "recent": {"edits": len(revs), "reverted": reverted,
                   "since": revs[-1]["timestamp"] if revs else None},
    }


def _dt(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ---------- conflict signals ----------

def signals(rep):
    """Neutral, explainable flags for one edition (behaviour, never a verdict on a name)."""
    out = []
    undone = [m for m in rep["renames"] if "undone_after_hours" in m]
    if undone:
        fastest = min(m["undone_after_hours"] for m in undone)
        out.append({"kind": "naming_fight", "label": f"{len(undone)} rename(s) undone",
                    "explain": f"The title was changed and changed back; fastest reversal after {_hours(fastest)}."})
    burst = _burst(rep["renames"])
    if burst:
        out.append({"kind": "rename_burst", "label": f"{burst['count']} renames in {_hours(burst['hours'])}",
                    "explain": "Several title changes in a short window."})
    npov = [m for m in rep["renames"] if m["reason"] and re.search(r"npov|neutral|pov\b|neutraal|нейтрал", m["reason"], re.I)]
    if npov:
        out.append({"kind": "neutrality_claim", "label": "renamed citing neutrality",
                    "explain": f"{len(npov)} rename reason(s) mention the neutral-point-of-view rule."})
    if rep["locks"] >= 2:
        out.append({"kind": "locked", "label": f"locked {rep['locks']}×",
                    "explain": "Administrators restricted editing (protection log entries)."})
    r = rep["recent"]
    if r["edits"] >= 50 and r["reverted"] / r["edits"] >= 0.1:
        out.append({"kind": "revert_heavy", "label": f"{round(100 * r['reverted'] / r['edits'])}% of recent edits reverted",
                    "explain": f"{r['reverted']} of the last {r['edits']} edits were undone or rolled back."})
    if len(rep["names"]) >= 10:
        out.append({"kind": "many_names", "label": f"{len(rep['names'])} other names",
                    "explain": "Many alternative titles redirect here."})
    return out


def _burst(renames, window_h=48):
    best = None
    for i in range(len(renames)):
        j = i
        while j + 1 < len(renames) and (_dt(renames[j + 1]["ts"]) - _dt(renames[i]["ts"])).total_seconds() <= window_h * 3600:
            j += 1
        n = j - i + 1
        if n >= 3 and (not best or n > best["count"]):
            best = {"count": n, "hours": round((_dt(renames[j]["ts"]) - _dt(renames[i]["ts"])).total_seconds() / 3600, 1)}
    return best


def _hours(h):
    if h < 1:
        return f"{max(1, round(h * 60))} min"
    if h < 48:
        return f"{round(h)} h"
    return f"{round(h / 24)} days"


# ---------- Gemma: English meanings ----------

def english_meanings(texts):
    """{text: english} via Gemma on Featherless; empty if no key or the call fails."""
    key = os.environ.get("FEATHERLESS_API_KEY")
    texts = [t for t in dict.fromkeys(texts) if t]
    if not key or not texts:
        return {}
    payload = [{"i": i, "text": t} for i, t in enumerate(texts)]
    prompt = ("Translate each Wikipedia title, sentence or edit reason into English, literally and neutrally. "
              "Keep loaded words loaded (e.g. 'special military operation', 'invasion', 'assault'); do not explain or soften. "
              "Reply with ONLY a JSON array of {\"i\": number, \"en\": text}.")
    try:
        r = requests.post("https://api.featherless.ai/v1/chat/completions",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": os.environ.get("TRANSLATE_MODEL", "google/gemma-4-31B-it"),
                                "temperature": 0, "max_tokens": 4000,
                                "messages": [{"role": "system", "content": prompt},
                                             {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]},
                          timeout=90)
        r.raise_for_status()
        reply = r.json()["choices"][0]["message"]["content"]
        rows = json.loads(reply[reply.find("["): reply.rfind("]") + 1])
        return {texts[x["i"]]: x["en"] for x in rows if isinstance(x, dict) and x.get("i") is not None and x["i"] < len(texts)}
    except Exception:
        return {}


# ---------- cache (MariaDB, system-versioned) ----------

def _cache_get(key):
    con, cur = connect()
    try:
        cur.execute(_DDL)
        cur.execute("SELECT report, fetched_at FROM lang_compare WHERE query_key = ?", (key,))
        row = cur.fetchone()
        if not row:
            return None
        report = json.loads(row[0]) if isinstance(row[0], (str, bytes)) else row[0]
        return report, row[1]
    finally:
        con.close()


def _cache_put(key, report):
    con, cur = connect()
    try:
        cur.execute(_DDL)
        cur.execute("INSERT INTO lang_compare (query_key, report, fetched_at) VALUES (?, ?, UTC_TIMESTAMP()) "
                    "ON DUPLICATE KEY UPDATE report = VALUES(report), fetched_at = VALUES(fetched_at)",
                    (key, json.dumps(report, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()


# ---------- endpoints ----------

@router.get("/api/languages")
def compare(title: str = Query(..., min_length=1), lang: str = "fi", langs: str | None = None, refresh: int = 0):
    """Compare one article across language editions. `langs=en,ru,uk` to choose; default picks up to 12."""
    lang = lang.strip().lower()
    if not re.fullmatch(r"[a-z][a-z-]{1,11}", lang):
        raise HTTPException(400, "lang must be a Wikipedia language code like fi, en, sv")
    key = f"{lang}:{title.strip()}" + (f"|{langs}" if langs else "")

    if not refresh:
        try:
            hit = _cache_get(key)
        except Exception:
            hit = None
        if hit and datetime.now(timezone.utc).replace(tzinfo=None) - hit[1] < timedelta(hours=CACHE_HOURS):
            report = hit[0]
            report["cached"] = True
            return report

    with _KEY_LOCKS_GUARD:
        lock = _KEY_LOCKS.setdefault(key, threading.Lock())
    with lock:
        if not refresh:   # another request may have just built it
            try:
                hit = _cache_get(key)
            except Exception:
                hit = None
            if hit and datetime.now(timezone.utc).replace(tzinfo=None) - hit[1] < timedelta(seconds=60):
                hit[0]["cached"] = True
                return hit[0]
        return _build(key, lang, title, langs)


def _build(key, lang, title, langs):
    started = time.time()
    with _STATS_LOCK:
        _STATS.update(requests=0, retries=0, slowest=0.0, waited=0.0)
    available = editions(lang, title.strip())
    t_editions = time.time() - started
    chosen = pick_languages(lang, available, [l.strip() for l in langs.split(",")] if langs else None)
    with ThreadPoolExecutor(len(chosen)) as pool:      # every language at once; _WIKI_SLOTS caps requests
        reports = list(pool.map(lambda l: _safe_report(l, available[l]["title"]), chosen))

    for r in reports:
        info = available.get(r["lang"], {})
        r["language"] = info.get("name") or r["lang"]
        r["autonym"] = info.get("autonym")
        if "error" not in r:
            r["signals"] = signals(r)

    ok = [r for r in reports if "error" not in r]
    report = {
        "query": {"lang": lang, "title": available[lang]["title"]},
        "languages_available": len(available),
        "editions": sorted(reports, key=lambda r: (r["lang"] != lang, -len(r.get("signals", [])))),
        "summary": {
            "renames": sum(len(r["renames"]) for r in ok),
            "renames_undone": sum(1 for r in ok for m in r["renames"] if "undone_after_hours" in m),
            "locks": sum(r["locks"] for r in ok),
            "names": sum(len(r["names"]) for r in ok),
            "editions_with_signals": sum(1 for r in ok if r["signals"]),
        },
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "seconds": round(time.time() - started, 1),
        "timing": {"langlinks_s": round(t_editions, 2), "wiki_requests": _STATS["requests"],
                   "retries": _STATS["retries"], "slowest_request_s": round(_STATS["slowest"], 2),
                   "queued_s_total": round(_STATS["waited"], 1)},
        "translated_by": None,
        "cached": False,
    }
    try:
        _cache_put(key, report)
    except Exception:
        pass   # the comparison still works without the database
    return report


@router.get("/api/languages/saved")
def saved(title: str, lang: str = "fi", max_age_hours: float = CACHE_HOURS):
    """The latest stored comparison from MariaDB, if it is fresh enough (else 404)."""
    hit = _cache_get(f"{lang.strip().lower()}:{title.strip()}")
    if not hit or datetime.now(timezone.utc).replace(tzinfo=None) - hit[1] > timedelta(hours=max_age_hours):
        raise HTTPException(404, "no fresh comparison stored")
    report = hit[0]
    report["cached"] = True
    return report


@router.post("/api/languages/save")
def save(payload: dict = Body(...)):
    """Store a comparison the browser computed (same shape as GET /api/languages).
    Each save is a new row version: SELECT ... FOR SYSTEM_TIME ALL keeps every snapshot."""
    title, lang, report = payload.get("title"), payload.get("lang"), payload.get("report")
    if not isinstance(title, str) or not isinstance(lang, str) or not isinstance(report, dict):
        raise HTTPException(400, "need title, lang and report")
    eds = report.get("editions")
    if not isinstance(eds, list) or not all(isinstance(e, dict) and isinstance(e.get("lang"), str) for e in eds):
        raise HTTPException(400, "report.editions must be a list of editions")
    if len(json.dumps(report)) > 3_000_000:
        raise HTTPException(413, "report too large")
    report["cached"] = False
    key = f"{lang.strip().lower()}:{title.strip()}"
    # Carry over English meanings we already have for the same texts (no second Gemma wait).
    try:
        old = _cache_get(key)
    except Exception:
        old = None
    if old and old[0].get("translated_by"):
        known = {}
        for e in old[0].get("editions", []):
            known[e.get("title")] = e.get("title_en")
            known[e.get("first_sentence")] = e.get("first_sentence_en")
            for m in e.get("renames", []):
                known[m.get("reason")] = m.get("reason_en")
        known = {k: v for k, v in known.items() if k and v}
        needed = _texts_to_translate(report)
        _apply_meanings(report, known)
        if not all(t in known for t in needed):
            report["translated_by"] = None      # some new text: let /meanings fill the rest
    _cache_put(key, report)
    return {"saved": True, "translated_by": report.get("translated_by")}


@router.get("/api/languages/meanings")
def meanings(title: str, lang: str = "fi", langs: str | None = None):
    """Second step: Gemma's English meanings for titles, first sentences and rename reasons."""
    key = f"{lang.strip().lower()}:{title.strip()}" + (f"|{langs}" if langs else "")
    with _KEY_LOCKS_GUARD:
        lock = _KEY_LOCKS.setdefault("meanings|" + key, threading.Lock())
    with lock:                         # one Gemma call per topic at a time
        hit = _cache_get(key)
        if not hit:
            raise HTTPException(404, "compare first")
        report = hit[0]
        if report.get("translated_by"):
            return report
        found = english_meanings(_texts_to_translate(report))
        if not found:
            return report              # no key, or Gemma failed: the page keeps the originals
        # Gemma is slow; a newer comparison may have been saved meanwhile. Apply the meanings
        # to whatever is newest now instead of overwriting it with the report we started from.
        latest = (_cache_get(key) or (report, None))[0]
        _apply_meanings(latest, found)
        _cache_put(key, latest)
        return latest


def _texts_to_translate(report):
    eds = [e for e in report.get("editions", []) if "error" not in e]
    return ([e["title"] for e in eds if e["lang"] != "en"]
            + [e["first_sentence"] for e in eds if e.get("first_sentence") and e["lang"] != "en"]
            + [m["reason"] for e in eds for m in e.get("renames", []) if m.get("reason")])


def _apply_meanings(report, found):
    for e in report.get("editions", []):
        if "error" in e:
            continue
        e["title_en"] = found.get(e["title"])
        e["first_sentence_en"] = found.get(e.get("first_sentence"))
        for m in e.get("renames", []):
            m["reason_en"] = found.get(m["reason"]) if m.get("reason") else None
    report["translated_by"] = "Gemma"


def _safe_report(lang, title):
    try:
        return edition_report(lang, title)
    except Exception as e:
        return {"lang": lang, "title": title, "error": str(e)[:200], "names": [], "renames": [], "locks": 0,
                "recent": {"edits": 0, "reverted": 0, "since": None}}


@router.get("/api/languages/history")
def history(title: str, lang: str = "fi"):
    """Every stored snapshot of a comparison (MariaDB system versioning): how the names changed over time."""
    con, cur = connect()
    try:
        cur.execute(_DDL)
        cur.execute("SELECT fetched_at, JSON_EXTRACT(report, '$.editions') FROM lang_compare "
                    "FOR SYSTEM_TIME ALL WHERE query_key = ? ORDER BY fetched_at", (f"{lang}:{title.strip()}",))
        out = []
        for fetched_at, editions_json in cur.fetchall():
            eds = json.loads(editions_json) if editions_json else []
            out.append({"fetched_at": fetched_at.isoformat() + "Z",
                        "titles": {e["lang"]: e.get("title") for e in eds}})
        return out
    finally:
        con.close()
