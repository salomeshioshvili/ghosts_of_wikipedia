"""Live now: our history meets today's Wikipedia (Context.dev scrape).

Dataset M is a snapshot: it ends at each article's last edit in the dump. This endpoint reads the
article as it is *right now* on fi.wikipedia.org through Context.dev's scrape API, cuts it into
sentences exactly like the pipeline does (pipeline/textify.py), and compares it with the
sentences alive at the end of our history:
  - unchanged: same sentence (same hash, or near-identical wording)
  - rewritten: a close match with different wording (before -> after)
  - gone:      alive in our snapshot, missing today  -> ghosts born after the dataset ended
  - new:       on the live page, not in our snapshot

Each check is stored in MariaDB in `live_check`, a system-versioned table, so every visit keeps a
dated record of how the live article drifted from the snapshot.

Needs CONTEXT_DEV_API_KEY in .env. Endpoint used: GET https://api.context.dev/v1/web/scrape/markdown
"""
import difflib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests
from fastapi import APIRouter, HTTPException

from common import connect
from textify import SKIP_SECTIONS, keep, normalise, sentence_hash, split_sentences

router = APIRouter()

SCRAPE = "https://api.context.dev/v1/web/scrape/markdown"
CACHE_MINUTES = 60
SAME = 0.9          # this similar = the same sentence (punctuation, a link, a space)
REWRITTEN = 0.6     # between REWRITTEN and SAME = reworded

_DDL = """CREATE TABLE IF NOT EXISTS live_check (
  page_id    INT UNSIGNED NOT NULL PRIMARY KEY,
  report     JSON         NOT NULL,
  fetched_at DATETIME     NOT NULL
) WITH SYSTEM VERSIONING"""


# ---------- Context.dev ----------

def scrape_markdown(url, key):
    params = {"url": url, "useMainContentOnly": "true", "includeLinks": "false",
              "includeImages": "false", "maxAgeMs": "600000", "timeoutMS": "45000"}
    last = ""
    for attempt in range(3):
        try:
            r = requests.get(SCRAPE, params=params, timeout=60, headers={"Authorization": f"Bearer {key}"})
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
        data = data.get("data", data)
        md = data.get("markdown")
        if isinstance(md, dict):
            md = md.get("markdown")
        if not md:
            raise HTTPException(502, "Context.dev returned no text for this page")
        return md
    raise HTTPException(502, f"Context.dev unreachable ({last})")


# ---------- markdown -> sentences (same rules as the pipeline) ----------

_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_REF = re.compile(r"\[(?:\d+|[a-zå-ö]|huom\.? ?\d+|note \d+)\]", re.I)
_EMPH = re.compile(r"(\*\*|__|\*|_|`)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def markdown_sentences(md):
    out, para, skipping, section = [], [], False, ""

    def flush():
        if para and not skipping:
            text = " ".join(para)
            for s in split_sentences(text):
                s = normalise(s)
                if keep(s):
                    out.append((section, s))
        para.clear()

    for raw in md.splitlines():
        line = raw.strip()
        h = _HEADING.match(line)
        if h:
            flush()
            section = _clean(h.group(2))
            skipping = bool(SKIP_SECTIONS.match(section.lower()))
            continue
        if not line or line.startswith(("|", "---", "```")) or re.fullmatch(r"[-=*_\s]{3,}", line):
            flush()
            continue
        line = re.sub(r"^([*+-]|\d+\.)\s+", "", line)     # list markers
        line = line.lstrip("> ").strip()
        cleaned = _clean(line)
        if cleaned:
            para.append(cleaned)
    flush()
    return out


def _clean(text):
    text = _IMG.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _REF.sub("", text)
    text = text.replace("\\", "")
    text = _EMPH.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------- compare ----------

def _key(s):
    return normalise(s).casefold()


def compare(alive, live):
    """alive: [(hash_hex, text_fi, text_en, section)], live: [(section, text)]."""
    live_by_hash = {}
    for section, text in live:
        live_by_hash.setdefault(sentence_hash(text).hex(), (section, text))

    unchanged, rest_alive = [], []
    for a in alive:
        (unchanged if a[0].lower() in live_by_hash else rest_alive).append(a)
    matched_live = {h for h in live_by_hash if h in {a[0].lower() for a in unchanged}}
    rest_live = [(h, sec, t) for h, (sec, t) in live_by_hash.items() if h not in matched_live]

    # candidates by shared long words, so we only compare sentences that could be related
    index = {}
    for i, (_, _, t) in enumerate(rest_live):
        for w in set(re.findall(r"\w{6,}", _key(t))):
            index.setdefault(w, set()).add(i)

    used, rewritten, gone, near_same = set(), [], [], 0
    for a in rest_alive:
        ka = _key(a[1])
        cands = set()
        for w in set(re.findall(r"\w{6,}", ka)):
            cands |= index.get(w, set())
        best, best_i = 0.0, None
        for i in cands - used:
            sm = difflib.SequenceMatcher(None, ka, _key(rest_live[i][2]), autojunk=False)
            if sm.real_quick_ratio() < REWRITTEN or sm.quick_ratio() < REWRITTEN:
                continue
            r = sm.ratio()
            if r > best:
                best, best_i = r, i
        if best_i is not None and best >= SAME:
            used.add(best_i)
            near_same += 1
        elif best_i is not None and best >= REWRITTEN:
            used.add(best_i)
            rewritten.append({"hash": a[0].lower(), "before": a[1], "before_en": a[2],
                              "after": rest_live[best_i][2], "similarity": round(best, 2), "section": a[3]})
        else:
            gone.append({"hash": a[0].lower(), "text_fi": a[1], "text_en": a[2], "section": a[3]})
    new = [{"text_fi": t, "section": sec} for i, (_, sec, t) in enumerate(rest_live) if i not in used]
    return len(unchanged) + near_same, rewritten, gone, new


# ---------- storage ----------

def _cached(page_id):
    con, cur = connect()
    try:
        cur.execute(_DDL)
        cur.execute("SELECT report, fetched_at FROM live_check WHERE page_id = ?", (page_id,))
        row = cur.fetchone()
        if not row:
            return None
        report = json.loads(row[0]) if isinstance(row[0], (str, bytes)) else row[0]
        return report, row[1]
    finally:
        con.close()


def _store(page_id, report):
    con, cur = connect()
    try:
        cur.execute(_DDL)
        cur.execute("INSERT INTO live_check (page_id, report, fetched_at) VALUES (?, ?, UTC_TIMESTAMP()) "
                    "ON DUPLICATE KEY UPDATE report = VALUES(report), fetched_at = VALUES(fetched_at)",
                    (page_id, json.dumps(report, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()


# ---------- endpoints ----------

@router.get("/api/articles/{page_id}/live")
def live_now(page_id: int, refresh: int = 0):
    """Today's live article vs the end of our history: what died, changed or appeared since."""
    if not refresh:
        try:
            hit = _cached(page_id)
        except Exception:
            hit = None
        if hit and datetime.now(timezone.utc).replace(tzinfo=None) - hit[1] < timedelta(minutes=CACHE_MINUTES):
            hit[0]["cached"] = True
            return hit[0]

    key = os.environ.get("CONTEXT_DEV_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Live mode is off: add CONTEXT_DEV_API_KEY to .env")

    con, cur = connect()
    try:
        cur.execute("SELECT title_fi, last_edit FROM article WHERE page_id = ?", (page_id,))
        art = cur.fetchone()
        if not art:
            raise HTTPException(404, "unknown page_id")
        cur.execute("SELECT HEX(l.hash), s.text_fi, s.text_en, l.section FROM sentence_life AS l "
                    "JOIN sentence s ON s.hash = l.hash WHERE l.page_id = ? ORDER BY l.pos", (page_id,))
        alive = cur.fetchall()
    finally:
        con.close()
    if not alive:
        raise HTTPException(409, "Open the article first, so its history is loaded")

    title, snapshot = art
    url = "https://fi.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
    t0 = time.time()
    live = markdown_sentences(scrape_markdown(url, key))
    if len(live) < 3:
        raise HTTPException(502, "Couldn't read today's article text")
    same, rewritten, gone, new = compare(alive, live)

    report = {
        "page_id": page_id, "title": title, "url": url,
        "snapshot": snapshot.isoformat() + "Z" if snapshot else None,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "counts": {"in_snapshot": len(alive), "live_now": len(live), "unchanged": same,
                   "rewritten": len(rewritten), "gone": len(gone), "new": len(new)},
        "match_quality": round(same / max(len(alive), 1), 2),
        "gone": gone[:60], "rewritten": rewritten[:40], "new": new[:60],
        "source": "Context.dev scrape (GET /v1/web/scrape/markdown)",
        "seconds": round(time.time() - t0, 1), "cached": False,
    }
    try:
        _store(page_id, report)
    except Exception:
        pass
    return report


@router.get("/api/articles/{page_id}/live/history")
def live_history(page_id: int):
    """Every stored live check (MariaDB system versioning): the live article's drift, dated."""
    con, cur = connect()
    try:
        cur.execute(_DDL)
        cur.execute("SELECT fetched_at, JSON_EXTRACT(report, '$.counts') FROM live_check "
                    "FOR SYSTEM_TIME ALL WHERE page_id = ? ORDER BY fetched_at", (page_id,))
        return [{"fetched_at": f.isoformat() + "Z", "counts": json.loads(c) if c else None}
                for f, c in cur.fetchall()]
    finally:
        con.close()
