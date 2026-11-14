"""Headline numbers for the pitch, written to data/stats.json (the API's /api/stats reads it).

    python pipeline/stats.py

- half_life_years: the age by which half of all sentences ever written have died (Kaplan-Meier,
  so sentences still alive count correctly), excluding typo fixes and reverted vandalism.
- pct_deleted: share of all sentence lives that have ended.
- per-article half-life for the hero articles.
"""
import json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, connect, hero_pages

END_OF_DATA = datetime(2026, 10, 1)


def half_life(durations):
    """durations: [(years, died: bool)]. Kaplan-Meier median survival, in years (None if > data)."""
    durations.sort()
    at_risk, survival = len(durations), 1.0
    for years, died in durations:
        if died:
            survival *= (at_risk - 1) / at_risk
            if survival <= 0.5:
                return round(years, 1)
        at_risk -= 1
    return None


def main():
    con, cur = connect()
    cur.execute("""SELECT page_id, row_start, row_end, died_rev IS NOT NULL
                   FROM sentence_life FOR SYSTEM_TIME ALL WHERE kind NOT IN ('typo', 'reverted')""")
    every, per_page = [], {}
    for page_id, start, end, died in cur.fetchall():
        stop = end if died else END_OF_DATA
        d = ((stop - start).total_seconds() / (365.25 * 86400), bool(died))
        every.append(d)
        per_page.setdefault(page_id, []).append(d)
    out = {"lives": len(every),
           "pct_deleted": round(100 * sum(d for _, d in every) / max(len(every), 1), 1),
           "half_life_years": half_life(list(every)),
           "per_article": {}}
    cur.execute("SELECT page_id, title_fi FROM article")
    titles = dict(cur.fetchall())
    for page in hero_pages():
        if page in per_page:
            out["per_article"][titles.get(page, str(page))] = half_life(per_page[page])
    path = os.path.join(ROOT, "data", "stats.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
