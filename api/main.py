"""Ghosts of Wikipedia API: the endpoints of the API contract in the build doc.

    uvicorn api.main:app --reload --port 8000        (run from the repo root)

Rules: all times UTC ISO 8601; hashes are hex; never return `user` for anonymous editors.
"""
import json, os, sys, time
from datetime import datetime
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import connect  # noqa: E402

app = FastAPI(title="Ghosts of Wikipedia")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FEATURED = (1150, 1256, 6021)            # 1918 war, Winter War, Mannerheim
GHOST_KINDS = ("erased", "rewritten")


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def alive_end(t):
    """A current row's row_end is the far future: report it as None (still alive)."""
    return None if t is None or t.year >= 2038 else t


def as_of_param(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(400, "as_of must be ISO 8601, e.g. 2012-03-01T00:00:00Z")


def rows(sql, params=()):
    con, cur = connect()
    try:
        cur.execute(sql, params)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    finally:
        con.close()


def who(user, anonymous):
    return {"user": None if anonymous else user, "anonymous": bool(anonymous)}


def event_tag(y0, y1):
    """'talks about 1918' / 'talks about 1918–1920' from the sentence's event years."""
    if not y0:
        return None
    return f"talks about {y0}" if not y1 or y1 == y0 else f"talks about {y0}–{y1}"


@app.get("/api/articles")
def articles(featured: int = 0, limit: int = 12):
    if featured:
        marks = ",".join("?" * len(FEATURED))
        found = rows(f"SELECT * FROM article WHERE page_id IN ({marks})", FEATURED)
    else:
        found = rows("SELECT * FROM article ORDER BY ghost_count DESC LIMIT ?", (limit,))
    return [{"page_id": a["page_id"], "title_fi": a["title_fi"], "title_en": a["title_en"],
             "ghost_count": a["ghost_count"], "versions": a["versions"],
             "first_edit": iso(a["first_edit"]), "last_edit": iso(a["last_edit"])} for a in found]


@app.get("/api/articles/{page_id}")
def article(page_id: int, as_of: str | None = None, min_days: int = 7):
    """min_days: hide ghosts that lived less than this (edit churn, not history)."""
    when = as_of_param(as_of) or datetime.utcnow()
    meta = rows("SELECT * FROM article WHERE page_id = ?", (page_id,))
    if not meta:
        raise HTTPException(404, "unknown page_id")
    stamp = when.strftime("%Y-%m-%d %H:%M:%S.%f")
    living = rows(f"""SELECT HEX(l.hash) AS hash, s.text_fi, s.text_en, l.section, l.pos, l.row_start AS born
        FROM sentence_life FOR SYSTEM_TIME AS OF TIMESTAMP '{stamp}' AS l JOIN sentence s USING (hash)
        WHERE l.page_id = ? ORDER BY l.pos""", (page_id,))
    alive_now = {r["hash"] for r in living}
    dead = rows(f"""SELECT HEX(l.hash) AS hash, s.text_fi, s.text_en, l.section, HEX(l.prev_hash) AS after_hash,
            l.row_start AS born, l.row_end AS died, l.kind,
            (SELECT COUNT(*) FROM sentence_life FOR SYSTEM_TIME ALL x
              WHERE x.page_id = l.page_id AND x.hash = l.hash) AS lives,
            (SELECT MAX(c.score) FROM coordination c WHERE c.page_id = l.page_id AND c.hash = l.hash) AS score,
            m.to_page_id AS moved_to, ma.title_fi AS moved_title,
            YEAR(e.event_from) AS y0, YEAR(e.event_to) - 1 AS y1
        FROM sentence_life FOR SYSTEM_TIME ALL AS l JOIN sentence s USING (hash)
        LEFT JOIN sentence_move m ON m.page_id = l.page_id AND m.hash = l.hash AND m.died_rev = l.died_rev
        LEFT JOIN article ma ON ma.page_id = m.to_page_id
        LEFT JOIN sentence_event e ON e.hash = l.hash
        WHERE l.page_id = ? AND l.kind IN ('erased', 'rewritten') AND l.row_end <= TIMESTAMP '{stamp}'
        ORDER BY l.row_end DESC""", (page_id,))
    ghosts, seen = [], set()
    for g in dead:                                      # one ghost per sentence: its latest death
        if g["hash"] in alive_now or g["hash"] in seen:
            continue
        seen.add(g["hash"])
        if (g["died"] - g["born"]).days < min_days:
            continue
        rare = (g["lives"] or 0) >= 3 or (g["score"] or 0) >= 70
        moved = {"page_id": g["moved_to"], "title_fi": g["moved_title"]} if g["moved_to"] else None
        ghosts.append({"hash": g["hash"].lower(), "text_fi": g["text_fi"], "text_en": g["text_en"],
                       "section": g["section"], "after_hash": (g["after_hash"] or "").lower() or None,
                       "born": iso(g["born"]), "died": iso(g["died"]), "kind": "moved" if moved else g["kind"],
                       "moved_to": moved, "lives": g["lives"], "rarity": "rare" if rare else "common",
                       "coordination_score": g["score"], "event_tag": event_tag(g["y0"], g["y1"])})
    m = meta[0]
    return {"page_id": page_id, "title_fi": m["title_fi"], "title_en": m["title_en"], "as_of": iso(when),
            "ghost_count": sum(1 for g in ghosts if g["kind"] != "moved"),
            "sentences": [{"hash": r["hash"].lower(), "text_fi": r["text_fi"], "text_en": r["text_en"],
                           "section": r["section"], "pos": r["pos"], "born": iso(r["born"])} for r in living],
            "ghosts": ghosts}


@app.get("/api/articles/{page_id}/timeline")
def timeline(page_id: int):
    frames = rows("SELECT ts, rev_id, hashes, edits, deaths FROM article_frame WHERE page_id = ? ORDER BY ts",
                  (page_id,))
    if not frames:
        raise HTTPException(404, "no timeline for this page yet")
    info = rows("""SELECT HEX(l.hash) AS hash, s.text_fi, s.text_en, MIN(l.row_start) AS born,
            MAX(l.row_end) AS died, COUNT(*) AS lives
        FROM sentence_life FOR SYSTEM_TIME ALL AS l JOIN sentence s USING (hash)
        WHERE l.page_id = ? GROUP BY l.hash, s.text_fi, s.text_en""", (page_id,))
    return {"page_id": page_id,
            "frames": [{"ts": iso(f["ts"]), "rev_id": f["rev_id"], "hashes": json.loads(f["hashes"]),
                        "edits": f["edits"], "deaths": f["deaths"]} for f in frames],
            "sentences": {i["hash"].lower(): {"text_fi": i["text_fi"], "text_en": i["text_en"],
                                              "born": iso(i["born"]), "died": iso(alive_end(i["died"])),
                                              "contested": i["lives"] >= 3} for i in info}}


@app.get("/api/ghosts/{page_id}/{hash_hex}")
def ghost(page_id: int, hash_hex: str):
    lives = rows("""SELECT l.row_start AS born, l.born_rev, l.row_end AS died, l.died_rev, l.kind,
            HEX(l.successor_hash) AS successor, l.similarity,
            rb.user AS born_user, rb.anonymous AS born_anon,
            rd.user AS died_user, rd.anonymous AS died_anon, rd.comment, rd.is_revert,
            m.to_page_id AS moved_to, ma.title_fi AS moved_title
        FROM sentence_life FOR SYSTEM_TIME ALL AS l
        LEFT JOIN revision rb ON rb.rev_id = l.born_rev
        LEFT JOIN revision rd ON rd.rev_id = l.died_rev
        LEFT JOIN sentence_move m ON m.page_id = l.page_id AND m.hash = l.hash AND m.died_rev = l.died_rev
        LEFT JOIN article ma ON ma.page_id = m.to_page_id
        WHERE l.page_id = ? AND l.hash = UNHEX(?) ORDER BY l.row_start""", (page_id, hash_hex))
    if not lives:
        raise HTTPException(404, "unknown ghost")
    text = rows("SELECT text_fi, text_en FROM sentence WHERE hash = UNHEX(?)", (hash_hex,))[0]
    event = rows("SELECT YEAR(event_from) AS y0, YEAR(event_to) - 1 AS y1 FROM sentence_event WHERE hash = UNHEX(?)",
                 (hash_hex,))
    last_dead = next((l for l in reversed(lives) if l["died_rev"]), None)
    reincarnated = None
    if last_dead and last_dead["successor"]:
        succ = rows("SELECT HEX(hash) AS hash, text_fi, text_en FROM sentence WHERE hash = UNHEX(?)",
                    (last_dead["successor"],))
        if succ:
            reincarnated = {"hash": succ[0]["hash"].lower(), "text_fi": succ[0]["text_fi"],
                            "text_en": succ[0]["text_en"], "similarity": round(last_dead["similarity"], 2)}
    coord = rows("SELECT score, evidence FROM coordination WHERE page_id = ? AND hash = UNHEX(?) ORDER BY score DESC",
                 (page_id, hash_hex))
    return {"hash": hash_hex.lower(), "page_id": page_id, "text_fi": text["text_fi"], "text_en": text["text_en"],
            "kind": last_dead["kind"] if last_dead else "alive",
            "talks_about": [event[0]["y0"], event[0]["y1"]] if event else None,
            "event_tag": event_tag(event[0]["y0"], event[0]["y1"]) if event else None,
            "rarity": "rare" if len(lives) >= 3 or (coord and coord[0]["score"] >= 70) else "common",
            "lives": [{"born": iso(l["born"]), "born_rev": l["born_rev"], "born_by": who(l["born_user"], l["born_anon"]),
                       "died": iso(alive_end(l["died"])), "died_rev": l["died_rev"],
                       "removed_by": who(l["died_user"], l["died_anon"]) if l["died_rev"] else None,
                       "edit_summary": l["comment"], "revert": bool(l["is_revert"]),
                       "moved_to": {"page_id": l["moved_to"], "title_fi": l["moved_title"]} if l["moved_to"] else None}
                      for l in lives],
            "reincarnated_as": reincarnated,
            "coordination": ({"score": coord[0]["score"], "evidence": json.loads(coord[0]["evidence"])}
                             if coord else {"score": None, "evidence": []}),   # frontend expects an object
            "links": {"born": f"https://fi.wikipedia.org/?oldid={lives[0]['born_rev']}",
                      "died": f"https://fi.wikipedia.org/?oldid={last_dead['died_rev']}" if last_dead else None}}


@app.get("/api/search")
def search(q: str = Query(..., min_length=2), limit: int = 10):
    try:
        sys.path.insert(0, os.path.join(ROOT, "ai"))
        from embed import embed_query          # Person 3: returns a list of 768 floats
    except ImportError:
        raise HTTPException(501, "search needs ai/embed.py (Person 3)")
    vector = json.dumps(embed_query(q))
    found = rows("""WITH near AS (
            SELECT hash, VEC_DISTANCE_COSINE(emb, VEC_FromText(?)) AS d FROM sentence_vec ORDER BY d LIMIT 200)
        SELECT l.page_id, a.title_fi, a.title_en, HEX(near.hash) AS hash, s.text_fi, s.text_en,
               MAX(l.row_end) AS died, MIN(near.d) AS d
        FROM near JOIN sentence s USING (hash)
        JOIN sentence_life FOR SYSTEM_TIME ALL AS l USING (hash)
        JOIN article a ON a.page_id = l.page_id
        WHERE l.kind IN ('erased', 'rewritten')
        GROUP BY l.page_id, a.title_fi, a.title_en, near.hash, s.text_fi, s.text_en
        ORDER BY d LIMIT ?""", (vector, limit))
    return [{"page_id": f["page_id"], "title_fi": f["title_fi"], "title_en": f["title_en"],
             "hash": f["hash"].lower(), "text_fi": f["text_fi"], "text_en": f["text_en"],
             "died": iso(f["died"]), "similarity": round(1 - f["d"], 3)} for f in found]


@app.get("/api/articles/{page_id}/biography")
def biography(page_id: int):
    path = os.path.join(ROOT, "data", "biography", f"{page_id}.json")   # written by ai/biography.py (Person 3)
    if not os.path.exists(path):
        raise HTTPException(404, "no biography for this page yet")
    return json.load(open(path, encoding="utf-8"))


@lru_cache(maxsize=1)
def _counts():
    c = rows("""SELECT (SELECT COUNT(*) FROM article) AS articles, (SELECT COUNT(*) FROM revision) AS versions,
                       (SELECT COUNT(*) FROM sentence) AS sentences""")[0]
    g = rows("""SELECT SUM(kind IN ('erased','rewritten')) AS ghosts, COUNT(*) AS lives,
                       SUM(died_rev IS NOT NULL) AS dead FROM sentence_life FOR SYSTEM_TIME ALL""")[0]
    return {**c, "ghosts": int(g["ghosts"] or 0),
            "pct_deleted": round(100 * float(g["dead"] or 0) / max(int(g["lives"] or 1), 1), 1)}


@app.get("/api/stats")
def stats():
    timings = {}
    for name, fn in (("as_of", lambda: article(1150, "2012-03-01T00:00:00Z")),
                     ("timeline", lambda: timeline(1150))):
        t0 = time.perf_counter()
        try:
            fn()
            timings[name] = round((time.perf_counter() - t0) * 1000, 1)
        except HTTPException:
            timings[name] = None
    extra = {}
    path = os.path.join(ROOT, "data", "stats.json")      # written by pipeline/stats.py
    if os.path.exists(path):
        extra = json.load(open(path, encoding="utf-8"))
    return {**_counts(), "half_life_years": extra.get("half_life_years"),
            "half_life_by_article": extra.get("per_article"), "timings_ms": timings}


web_dist = os.path.join(ROOT, "web", "dist")
if os.path.isdir(web_dist):                     # serve the built frontend at /
    app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
