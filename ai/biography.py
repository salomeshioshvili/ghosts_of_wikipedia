"""ai/biography.py - "Tell me this article's story": the turning points of an article's life,
narrated by Gemma, saved where the API reads it (data/biography/<page_id>.json).

Reads dataset M's Parquet files directly, so it needs no database:
    python pipeline/download.py                      # once, 315 MB, from the repo root

Then, from the repo root:
    python ai/biography.py --page 1150 --dry-run     # show the turning points found (free, no Gemma)
    python ai/biography.py --page 1150               # narrate them with Gemma and save the JSON

How it works: Python finds the facts (dates, revision ids, sizes, what changed); Gemma only
writes the captions. Dates and revision ids in the output always come from the data, never
from the model. Editor names never reach the model or the output.

.env (repo root): FEATHERLESS_API_KEY=...   optional BIO_MODEL=google/gemma-4-31B-it
"""
import argparse
import collections
import json
import os
import re
import sys
import time
from datetime import timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import parquet_m  # noqa: E402  (Person 1's Parquet reader; also loads the repo .env)

API_URL = "https://api.featherless.ai/v1/chat/completions"
MODEL = os.environ.get("BIO_MODEL", "google/gemma-4-31B-it")  # one call, so the bigger model is fine
OUT_DIR = ROOT / "data" / "biography"

# Names of the 1918 war, grouped by family (word stems cover Finnish case endings).
# A "naming fight" swaps one family for another in a heading, or adds a contested one.
NAME_FAMILIES = {
    "vapaussota (War of Freedom)": ("vapaussot", "vapaussod"),
    "sisällissota (Civil War)": ("sisällissot", "sisällissod"),
    "kansalaissota (Citizens' War)": ("kansalaissot", "kansalaissod"),
    "luokkasota (Class War)": ("luokkasot", "luokkasod"),
    "punakapina (Red Rebellion)": ("punakapin",),
    "veljessota (War of Brothers)": ("veljessot", "veljessod"),
    "vallankumous (Revolution)": ("vallankumou",),
}
CONTESTED = {"vapaussota (War of Freedom)", "luokkasota (Class War)", "punakapina (Red Rebellion)"}
NAME_TERMS = [stem for stems in NAME_FAMILIES.values() for stem in stems]
HEADING = re.compile(r"^==+\s*([^=\n].*?)\s*==+\s*$", re.M)
DAY = timedelta(days=1)


# ---------- reading the history ----------

def load_versions(page_id: int) -> list:
    cols = ["rev_id", "parent_id", "timestamp", "anonymous", "comment", "sha1", "bytes", "text", "title"]
    rows = list(parquet_m.read_page(page_id, cols))
    if not rows:
        raise SystemExit(f"page {page_id} not found in data/m (did you run pipeline/download.py?)")
    rows.sort(key=lambda r: (r["timestamp"], r["rev_id"]))
    first_seen = {}
    for r in rows:
        r["ts"] = parquet_m.naive_utc(r["timestamp"])
        r["bytes"] = r["bytes"] or 0
        r["headings"] = set(HEADING.findall(r["text"] or ""))
        # same text as an earlier, non-parent version = a revert (the build doc's rule)
        r["is_revert"] = r["sha1"] in first_seen and first_seen[r["sha1"]] != r["parent_id"]
        first_seen.setdefault(r["sha1"], r["rev_id"])
    return rows


def clean_summary(comment) -> str:
    """Edit summary without user names, IPs or wiki links to user pages."""
    c = comment or ""
    c = re.sub(r"\[\[(?:[^\]|]*(?:Contributions|Muokkaukset|User|Käyttäjä|Keskustelu)[^\]]*)\]\]", "[an editor]", c)
    c = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "[an editor]", c)
    c = re.sub(r"~\d{4}-\d+-\d+", "[an editor]", c)            # temporary accounts
    c = re.sub(r"/\*\s*(.*?)\s*\*/", r"section «\1»:", c)
    return re.sub(r"\s+", " ", c).strip()[:160]


def lead_sentence(text: str) -> str:
    t = re.sub(r"\{\{[^{}]*\}\}", "", text or "")
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"<ref[^>]*>.*?</ref>|<[^>]+>|'''|''", "", t, flags=re.S)
    t = t.strip().split("\n")[0]
    # end of sentence: a full stop after a letter, followed by a capital (not "4. joulukuuta")
    return re.split(r"(?<=[a-zåäö)][.!?])\s+(?=[A-ZÅÄÖ])", t)[0][:300]


def families(s) -> set:
    s = (s or "").lower()
    return {f for f, stems in NAME_FAMILIES.items() if any(st in s for st in stems)}


def closest(heading: str, candidates: set):
    """The removed heading this new one most likely replaced (or None)."""
    import difflib
    best = difflib.get_close_matches(heading, list(candidates), n=1, cutoff=0.4)
    return best[0] if best else None


def is_name_fight(new: str, old) -> bool:
    gained = families(new) - families(old)
    if not gained:
        return False
    return bool(families(old)) or bool(gained & CONTESTED)   # a swap, or a contested name added


# ---------- finding the turning points ----------

def restored_within(rows, i, hours=48) -> bool:
    """Was the text before version i brought back soon after it?"""
    before = rows[i - 1]
    for r in rows[i + 1:]:
        if r["ts"] - rows[i]["ts"] > timedelta(hours=hours):
            return False
        if r["sha1"] == before["sha1"] or r["bytes"] >= 0.9 * before["bytes"]:
            return True
    return False


def find_events(rows: list) -> list:
    ev = []

    def add(kind, at, rev_ids, **facts):
        ev.append({"kind": kind, "ts": at, "rev_ids": rev_ids, "facts": facts})

    first = rows[0]
    add("birth", first["ts"], [first["rev_id"]],
        size_bytes=first["bytes"], first_sentence_fi=lead_sentence(first["text"]))

    # A section about the war's names appears: the naming debate enters the article.
    for r in rows:
        naming = sorted(h for h in r["headings"] if re.search(r"\bnim(i|e|it)", h.lower()))
        if naming:
            add("naming_section", r["ts"], [r["rev_id"]], heading_fi=naming[0],
                names_mentioned=sorted(families(r["text"])))
            break

    # The busiest month: when the article grew up.
    months = collections.Counter(r["ts"].strftime("%Y-%m") for r in rows)
    month, n = months.most_common(1)[0]
    in_month = [r for r in rows if r["ts"].strftime("%Y-%m") == month]
    idx = rows.index(in_month[0])
    add("growth_spurt", in_month[0]["ts"], [in_month[0]["rev_id"], in_month[-1]["rev_id"]],
        month=month, edits_that_month=n,
        size_before=rows[idx - 1]["bytes"] if idx else 0, size_after=in_month[-1]["bytes"])

    # Naming fights: a heading with a war name appears and is gone again within two days.
    episodes = []
    for i in range(1, len(rows)):
        added = rows[i]["headings"] - rows[i - 1]["headings"]
        removed = rows[i - 1]["headings"] - rows[i]["headings"]
        pairs = [(closest(h, removed), h) for h in added]
        pairs = [(old, new) for old, new in pairs if is_name_fight(new, old)]
        if not pairs:
            continue
        fight = [new for _, new in pairs]
        undone = next((r for r in rows[i + 1:i + 200]
                       if r["ts"] - rows[i]["ts"] <= 2 * DAY and not (set(fight) & r["headings"])), None)
        if undone is None:
            continue
        if episodes and rows[i]["ts"] - episodes[-1]["end"] < timedelta(hours=3):
            ep = episodes[-1]
            ep["renamed"] += pairs
            ep["end"], ep["undone"] = rows[i]["ts"], undone
            ep["revs"].append(rows[i]["rev_id"])
        else:
            episodes.append({"start": rows[i]["ts"], "end": rows[i]["ts"], "undone": undone,
                             "revs": [rows[i]["rev_id"]], "anonymous": rows[i]["anonymous"],
                             "renamed": pairs})
    for ep in episodes:
        u = ep["undone"]
        add("naming_fight", ep["start"], ep["revs"] + [u["rev_id"]],
            headings_changed=[{"from_fi": a, "to_fi": b} for a, b in ep["renamed"]],
            names_involved=sorted(set().union(*(families(a) | families(b) for a, b in ep["renamed"]))),
            by="an anonymous editor" if ep["anonymous"] else "a registered editor",
            undone_after_minutes=round((u["ts"] - ep["start"]).total_seconds() / 60),
            undo_summary=clean_summary(u["comment"]))

    # Vandalism the article survived: more than half of it wiped, then restored within two days.
    wipes = [i for i in range(1, len(rows))
             if rows[i - 1]["bytes"] > 2000 and rows[i]["bytes"] < 0.5 * rows[i - 1]["bytes"]
             and restored_within(rows, i)]
    if wipes:
        big = max(wipes, key=lambda i: rows[i - 1]["bytes"] - rows[i]["bytes"])
        add("wiped_and_restored", rows[big]["ts"], [rows[big]["rev_id"]],
            times_wiped_and_restored=len(wipes), largest_wipe_bytes=rows[big - 1]["bytes"] - rows[big]["bytes"],
            years=sorted({rows[i]["ts"].year for i in wipes}))

    # Big cuts that stayed: someone removed a lot and nobody brought it back.
    cuts = [i for i in range(1, len(rows))
            if rows[i - 1]["bytes"] - rows[i]["bytes"] > 5000 and not rows[i]["is_revert"]
            and not restored_within(rows, i, hours=24 * 30)]
    for i in sorted(cuts, key=lambda i: rows[i]["bytes"] - rows[i - 1]["bytes"])[:2]:
        add("lasting_cut", rows[i]["ts"], [rows[i]["rev_id"]],
            bytes_removed=rows[i - 1]["bytes"] - rows[i]["bytes"],
            edit_summary_fi=clean_summary(rows[i]["comment"]) or "(no summary)",
            by="an anonymous editor" if rows[i]["anonymous"] else "a registered editor")

    last = rows[-1]
    add("today", last["ts"], [last["rev_id"]],
        versions=len(rows), size_bytes=last["bytes"],
        reverts=sum(r["is_revert"] for r in rows),
        share_anonymous_edits=round(sum(r["anonymous"] for r in rows) / len(rows), 2),
        first_sentence_fi=lead_sentence(last["text"]))

    ev.sort(key=lambda e: e["ts"])
    return ev


# ---------- narration ----------

SYSTEM = """You narrate the life story of a Finnish Wikipedia article for a 60-second time-lapse.
You receive its turning points as JSON: dates, sizes and what changed. Write one caption per
turning point, in BOTH Finnish and English.

Rules:
- One or two short sentences per caption, at most 30 words. Calm documentary tone, present tense.
- Use only the facts given. Do not invent numbers, motives or people.
- Never name or describe individual editors. "An editor" / "eräs muokkaaja" is enough.
- Be neutral about the war: report what changed, do not take sides on names or events.
- For English: translate Finnish headings you quote and keep the Finnish word in brackets,
  e.g. "War of Freedom (vapaussota)". For Finnish captions, use the Finnish names naturally.
- Sizes are in bytes; say "characters" / "merkkiä" and round them (about 10,000 characters).

Reply with ONLY a JSON array:
[{"i": number, "caption_fi": text, "caption_en": text}, ...], one per turning point."""


def narrate(title: str, events: list) -> list:
    """Returns list of {"caption_fi", "caption_en"} aligned with events."""
    key = os.environ.get("FEATHERLESS_API_KEY", "")
    if not key:
        raise SystemExit("FEATHERLESS_API_KEY is missing from the repo .env")
    payload = {"article_fi": title, "turning_points": [
        {"i": i, "date": e["ts"].strftime("%Y-%m-%d"), "kind": e["kind"], **e["facts"]}
        for i, e in enumerate(events)]}
    for attempt in range(5):
        r = requests.post(API_URL, headers={"Authorization": f"Bearer {key}"}, timeout=300, json={
            "model": MODEL, "temperature": 0.3, "max_tokens": 4000,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}]})
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        reply = r.json()["choices"][0]["message"]["content"]
        rows = json.loads(reply[reply.find("["):reply.rfind("]") + 1])
        captions = {
            int(x["i"]): {
                "caption_fi": str(x["caption_fi"]).strip(),
                "caption_en": str(x["caption_en"]).strip(),
            }
            for x in rows
            if x.get("caption_fi") and x.get("caption_en")
        }
        if set(captions) == set(range(len(events))):
            return [captions[i] for i in range(len(events))]
        print("  reply missed some turning points; asking again")
    raise SystemExit("Gemma did not return a caption for every turning point")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", type=int, default=1150)
    ap.add_argument("--dry-run", action="store_true", help="only print the turning points")
    args = ap.parse_args()

    rows = load_versions(args.page)
    events = find_events(rows)
    print(f"{rows[-1]['title']}: {len(rows)} versions, {len(events)} turning points")
    for i, e in enumerate(events):
        print(f"  {i}. {e['ts']:%Y-%m-%d}  {e['kind']:<20} {json.dumps(e['facts'], ensure_ascii=False)[:150]}")
    if args.dry_run:
        return

    captions = narrate(rows[-1]["title"], events)
    out = {"page_id": args.page,
           "chapters": [{"ts": e["ts"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "caption_fi": c["caption_fi"], "caption_en": c["caption_en"],
                         "rev_ids": e["rev_ids"]}
                        for e, c in zip(events, captions)],
           "audio_url": None}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{args.page}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {path}\n")
    for ch in out["chapters"]:
        print(f"{ch['ts'][:10]}  FI: {ch['caption_fi']}\n            EN: {ch['caption_en']}")


if __name__ == "__main__":
    main()
