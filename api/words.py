"""Words over time: how an article's vocabulary shifted (MariaDB system-versioned history).

For one article, every sentence that ever lived (sentence_life FOR SYSTEM_TIME ALL) is split into
words. We compare deleted sentences (ghosts) with surviving ones using the "Fightin' Words"
weighted log-odds with an informative Dirichlet prior (Monroe, Colaresi & Quinn 2008):
  - stopped saying: words most over-represented in deleted sentences
  - kept saying:    words most over-represented in sentences that survive today
For the top words we also count, year by year, how many sentences alive at the end of that year
used them (per 100 sentences), so you can see a term fade out or take over.

Finnish inflects heavily, so words are grouped by their first 7 letters (vapaussota, vapaussodan,
vapaussodassa -> "vapauss"); the most common full form is shown. Results are cached in MariaDB
(word_shift, system-versioned). English meanings by Gemma when FEATHERLESS_API_KEY is set.
"""
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from common import connect

router = APIRouter()

STEM = 7
MIN_COUNT = 3
TOP = 12
ALIVE_AFTER = datetime(2030, 1, 1)
_WORD = re.compile(r"[a-zåäöšž]{4,}", re.I)
STOP = set("""
ja että joka jotka joita jonka jota jossa joissa joiden jolla joilla jolle joille jolloin jonne josta joista
myös sekä mutta kuin vaan vain koska vaikka kunnes ennen jälkeen aikana välillä lisäksi kuitenkin mukaan muun muassa
noin yli alle olla oli olivat ollut olleet ovat olisi olisivat ollessa olleen oleva olevat olevan
tämä tämän tätä tässä tästä tähän nämä näiden niitä niiden niistä niihin siitä sitä sille siihen sen
hän hänen häntä häneen heidän heitä heille hänet itse oman omat omien heillä hänellä
kun jos niin sitten vielä enää jopa aina usein paljon vähän myöhemmin aiemmin samana samaan saman
vuonna vuoden vuosina vuosien vuoteen vuosi vuotta luvulla luvun alussa lopussa aikaan aikoina
kaikki kaikkien useita useat monet monia muita muiden muut toinen toisen toiset ensimmäinen ensimmäisen
mitä mikä missä mistä mihin miten miksi kuka keitä kenen jokin jotain joku kukaan mikään
eikä eivät eikä ei ole eikä olla tulee tuli tulivat voi voidaan voitiin pitää piti saattoi kuitenkaan
teoks teoksessa teoksen teos toim toimittanut sivu sivut sivulla isbn wsoy otava gummerus tammi kustannus kustannusosakeyhtiö
helsinki julkaisu julkaistu painos verkkoversio viitattu luettu arkistoitu alkuperäisestä lähde lähteet viite
sanottu sanoi sanotaan todettu todetaan mainittu mainitaan esimerkiksi erityisesti lähinnä yleensä
""".split())


def _stem(w):
    w = w.lower()
    return w[:STEM] if len(w) > STEM else w


STOP_STEMS = {_stem(w) for w in STOP if len(w) >= STEM}


def _rows(page_id):
    con, cur = connect()
    try:
        cur.execute("SELECT s.text_fi, l.row_start, l.row_end, l.kind FROM sentence_life FOR SYSTEM_TIME ALL AS l "
                    "JOIN sentence s ON s.hash = l.hash WHERE l.page_id = ?", (page_id,))
        rows = cur.fetchall()
        cur.execute("SELECT title_fi, first_edit FROM article WHERE page_id = ?", (page_id,))
        art = cur.fetchone()
    finally:
        con.close()
    return rows, art


def _tokens(text):
    out, forms = set(), {}
    for w in _WORD.findall(text or ""):
        lw = w.lower()
        st = _stem(lw)
        if lw in STOP or st in STOP_STEMS:
            continue
        out.add(st)
        forms.setdefault(st, lw)
    return out, forms


def compute(page_id):
    rows, art = _rows(page_id)
    if not rows:
        raise HTTPException(409, "Open the article first, so its history is loaded")
    title, first_edit = art if art else (None, None)

    lives = []                     # (stems, born, died_or_None, ghost?, text)
    surface = defaultdict(Counter)
    for text, born, died, kind in rows:
        stems, forms = _tokens(text)
        alive = died is None or died > ALIVE_AFTER
        ghost = (not alive) and kind in ("erased", "rewritten")
        for st, f in forms.items():
            surface[st][f] += 1
        lives.append((stems, born, None if alive else died, ghost, alive, text))

    g, s = Counter(), Counter()
    for stems, _, _, ghost, alive, _ in lives:
        if ghost:
            g.update(stems)
        elif alive:
            s.update(stems)
    n_g, n_s = sum(g.values()), sum(s.values())
    if n_g < 50 or n_s < 50:
        raise HTTPException(422, "Too little history in this article to compare its vocabulary")

    # Fightin' Words: weighted log-odds, informative Dirichlet prior from the pooled counts
    vocab = set(g) | set(s)
    alpha = {w: 0.01 + 0.05 * (g[w] + s[w]) for w in vocab}
    a0 = sum(alpha.values())
    scored = []
    for w in vocab:
        yg, ys, a = g[w], s[w], alpha[w]
        if yg + ys < MIN_COUNT:
            continue
        d = math.log((yg + a) / (n_g + a0 - yg - a)) - math.log((ys + a) / (n_s + a0 - ys - a))
        z = d / math.sqrt(1 / (yg + a) + 1 / (ys + a))
        scored.append((z, w))
    scored.sort()
    died_words = [w for z, w in reversed(scored) if g[w] >= 5 and z > 1.96][:TOP]
    kept_words = [w for z, w in scored if s[w] >= 8 and z < -1.96][:TOP]
    z_of = {w: z for z, w in scored}

    # years each word was in use, and an example deleted sentence
    first_year, last_year, example = {}, {}, {}
    for stems, born, died, ghost, alive, text in lives:
        for w in stems:
            if w not in z_of:
                continue
            first_year[w] = min(first_year.get(w, 9999), born.year)
            ly = 2026 if alive else died.year
            last_year[w] = max(last_year.get(w, 0), ly)
            if ghost and (w not in example or len(text) < len(example[w])) and 40 <= len(text) <= 260:
                example[w] = text

    # year-by-year use (per 100 sentences alive at the end of each year)
    y0 = max((first_edit.year if first_edit else 2002), 2002)
    years = list(range(y0, 2027))
    track = died_words[:6] + kept_words[:6]
    series = {w: [] for w in track}
    alive_counts = []
    for y in years:
        end = datetime(y, 12, 31, 23, 59)
        alive_now = [stems for stems, born, died, _, _, _ in lives if born <= end and (died is None or died > end)]
        alive_counts.append(len(alive_now))
        for w in track:
            k = sum(1 for st in alive_now if w in st)
            series[w].append(round(100 * k / len(alive_now), 2) if alive_now else 0)

    def word(w):
        return {"stem": w, "word": surface[w].most_common(1)[0][0], "in_deleted": g[w], "in_surviving": s[w],
                "z": round(z_of[w], 2), "first_year": first_year.get(w), "last_year": last_year.get(w),
                "example_deleted": example.get(w)}

    report = {
        "page_id": page_id, "title": title,
        "stopped_saying": [word(w) for w in died_words],
        "kept_saying": [word(w) for w in kept_words],
        "years": years, "sentences_alive": alive_counts,
        "series": {w: series[w] for w in track},
        "deleted_sentences": sum(1 for x in lives if x[3]), "surviving_sentences": sum(1 for x in lives if x[4]),
        "method": "Fightin' Words weighted log-odds with an informative Dirichlet prior (Monroe, Colaresi & Quinn 2008); "
                  "words grouped by their first 7 letters",
        "computed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    try:
        from languages import english_meanings
        words = [x["word"] for x in report["stopped_saying"] + report["kept_saying"]]
        en = english_meanings(words)
        for x in report["stopped_saying"] + report["kept_saying"]:
            x["word_en"] = en.get(x["word"])
        report["translated_by"] = "Gemma" if en else None
    except Exception:
        report["translated_by"] = None
    return report


_DDL = """CREATE TABLE IF NOT EXISTS word_shift (
  page_id     INT UNSIGNED NOT NULL PRIMARY KEY,
  report      JSON NOT NULL,
  computed_at DATETIME NOT NULL
) WITH SYSTEM VERSIONING"""


@router.get("/api/articles/{page_id}/words")
def words(page_id: int, refresh: int = 0):
    """Words over time for one article (cached in MariaDB unless refresh=1)."""
    con, cur = connect()
    try:
        cur.execute(_DDL)
        if not refresh:
            cur.execute("SELECT report FROM word_shift WHERE page_id = ?", (page_id,))
            row = cur.fetchone()
            if row:
                rep = json.loads(row[0]) if isinstance(row[0], (str, bytes)) else row[0]
                rep["cached"] = True
                return rep
    finally:
        con.close()
    report = compute(page_id)
    try:
        con, cur = connect()
        try:
            cur.execute("INSERT INTO word_shift (page_id, report, computed_at) VALUES (?, ?, UTC_TIMESTAMP()) "
                        "ON DUPLICATE KEY UPDATE report = VALUES(report), computed_at = VALUES(computed_at)",
                        (page_id, json.dumps(report, ensure_ascii=False)))
            con.commit()
        finally:
            con.close()
    except Exception:
        pass
    report["cached"] = False
    return report


@router.get("/api/articles/{page_id}/words/track")
def track_word(page_id: int, word: str):
    """Year-by-year use of any word (or its first 7 letters) in this article, per 100 sentences."""
    rows, art = _rows(page_id)
    if not rows:
        raise HTTPException(409, "Open the article first")
    st = _stem(word.strip())
    y0 = max((art[1].year if art and art[1] else 2002), 2002)
    years = list(range(y0, 2027))
    lives = [(_tokens(t)[0], b, None if (d is None or d > ALIVE_AFTER) else d) for t, b, d, _ in rows]
    out = []
    for y in years:
        end = datetime(y, 12, 31, 23, 59)
        alive_now = [stems for stems, b, d in lives if b <= end and (d is None or d > end)]
        k = sum(1 for s_ in alive_now if st in s_)
        out.append(round(100 * k / len(alive_now), 2) if alive_now else 0)
    return {"word": word, "stem": st, "years": years, "series": out}
