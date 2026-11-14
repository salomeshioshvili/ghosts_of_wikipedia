"""Turn every version of an article into sentence lives, and load them into MariaDB with
Wikipedia's real edit times (system_versioning_insert_history).

    python pipeline/lives.py --pages 1150          # the 1918 war first
    python pipeline/lives.py --heroes --workers 4  # the 50 hero articles
    python pipeline/lives.py --all --workers 8     # all 19,742 (or run it on Modal)
    python pipeline/lives.py --reset ...           # drop and recreate the sentence tables first

Per page:
 1. versions oldest first (sha1 + timestamp); versions that a revert undid within 24 h are skipped
    (vandalism and page blanking would otherwise create thousands of fake ghosts);
 2. each kept version -> sentences (textify.py) -> diff with the previous one: born / died;
 3. each death is classified against the sentences added in the same edit:
    typo (similarity >= 0.9) | rewritten (0.6-0.9) | erased (< 0.6) | reverted (died < 24 h old in a revert);
 4. dead lives go in as history rows (row_start, row_end); living sentences as current rows;
 5. ~240 keyframes for the time-lapse, event years per sentence, the article's ghost count.
"""
import argparse, difflib, json, os, sys, time
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool

import pyarrow.compute as pc
import pyarrow.dataset as ds

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_M, apply_schema, batched_executemany, connect, hero_pages
from textify import sentence_hash, sentences, years

REVERT_WINDOW = timedelta(hours=24)
FRAMES = 240
TYPO, REWRITE = 0.9, 0.6
MAX_COMPARE = 300           # a removed sentence is compared with at most this many added ones


def naive_utc(t):
    return t.astimezone(timezone.utc).replace(tzinfo=None) if t.tzinfo else t


# --- 1. Which versions to keep --------------------------------------------------------------------
def versions_to_keep(meta):
    """meta: [(timestamp, rev_id, sha1)] oldest first. Returns (kept rev_ids, revert rev_ids)."""
    first_seen, undone, reverts = {}, set(), set()
    for j, (ts, rev, sha1) in enumerate(meta):
        i = first_seen.get(sha1) if sha1 else None
        if i is not None and i < j - 1:                     # back to an older text: a revert
            reverts.add(rev)
            if ts - meta[i + 1][0] <= REVERT_WINDOW:        # what it undid lived < 24 h: skip it
                undone.update(r for _, r, _ in meta[i + 1:j])
        if sha1 and sha1 not in first_seen:
            first_seen[sha1] = j
    return {rev for _, rev, _ in meta if rev not in undone}, reverts


# --- 2-3. Lives from a stream of versions ---------------------------------------------------------
def classify(text, added):
    """Best match of a dead sentence among the sentences added in the same edit."""
    best, best_hash = 0.0, None
    for h, other in added[:MAX_COMPARE]:
        m = difflib.SequenceMatcher(None, text, other, autojunk=False)
        if m.real_quick_ratio() <= best or m.quick_ratio() <= best:
            continue
        r = m.ratio()
        if r > best:
            best, best_hash = r, h
    if best >= TYPO:
        return "typo", best_hash, best
    if best >= REWRITE:
        return "rewritten", best_hash, best
    return "erased", None, None


def lives_of(versions, reverts, parse=sentences):
    """versions: iterable of (timestamp, rev_id, wikitext), oldest first, timestamps strictly rising.
    Returns (lives, texts, frames_src): lives = list of dicts; texts = {hash: text}."""
    alive, order, lives, texts, snapshots = {}, [], [], {}, []
    for ts, rev, wikitext in versions:
        current, cur_order = {}, []
        for pos, (section, text) in enumerate(parse(wikitext or "")):
            h = sentence_hash(text)
            if h in current:                                # a repeated sentence: keep the first
                continue
            prev = cur_order[-1] if cur_order else None
            current[h] = {"section": section, "pos": len(cur_order), "prev": prev}
            cur_order.append(h)
            texts.setdefault(h, text)
        added = [(h, texts[h]) for h in cur_order if h not in alive]
        died_now = 0
        for h, life in alive.items():
            if h in current:
                life.update(current[h])                     # where it stands now
                continue
            kind, successor, sim = classify(texts[h], added)
            if rev in reverts and ts - life["born"] <= REVERT_WINDOW:
                kind = "reverted"
            lives.append({**life, "hash": h, "died": ts, "died_rev": rev, "kind": kind,
                          "successor": successor, "similarity": sim})
            died_now += 1
        alive = {h: alive.get(h) or {"hash": h, "born": ts, "born_rev": rev, **current[h]}
                 for h in cur_order}
        snapshots.append((ts, rev, cur_order, died_now))
    for h, life in alive.items():
        lives.append({**life, "hash": h, "died": None, "died_rev": None, "kind": "alive",
                      "successor": None, "similarity": None})
    return lives, texts, snapshots


def keyframes(snapshots, n=FRAMES):
    """Pick ~n snapshots evenly spread in time; count edits and deaths between them."""
    if not snapshots:
        return []
    t0, t1 = snapshots[0][0], snapshots[-1][0]
    step = (t1 - t0) / max(n - 1, 1)
    frames, target, edits, deaths = [], t0, 0, 0
    for k, (ts, rev, order, died) in enumerate(snapshots):
        edits, deaths = edits + 1, deaths + died
        last = k == len(snapshots) - 1
        if ts >= target or last:
            frames.append((ts, rev, order, edits, deaths))
            edits = deaths = 0
            while target <= ts:
                target += step if step else timedelta(days=1)
    return frames


# --- 4-5. One page end to end ---------------------------------------------------------------------
def read_versions(page_id):
    """(meta, iterator of (ts, rev, text)) for one page, from the Parquet files."""
    dataset = ds.dataset(DATA_M, format="parquet")
    where = pc.field("page_id") == page_id
    meta_table = dataset.to_table(columns=["timestamp", "rev_id", "sha1"], filter=where).to_pylist()
    meta = sorted((naive_utc(r["timestamp"]), r["rev_id"], r["sha1"]) for r in meta_table)
    for k in range(1, len(meta)):                           # strictly rising, 1 µs apart if needed
        if meta[k][0] <= meta[k - 1][0]:
            meta[k] = (meta[k - 1][0] + timedelta(microseconds=1),) + meta[k][1:]
    ts_of = {rev: ts for ts, rev, _ in meta}
    keep, reverts = versions_to_keep(meta)

    def stream():
        rows = []
        for batch in dataset.to_batches(columns=["rev_id", "text"], filter=where, batch_size=64):
            for r in batch.to_pylist():
                if r["rev_id"] in keep:
                    rows.append((ts_of[r["rev_id"]], r["rev_id"], r["text"]))
        rows.sort(key=lambda x: (x[0], x[1]))
        yield from rows
    return meta, reverts, stream()


def process_page(page_id):
    t0 = time.time()
    meta, reverts, versions = read_versions(page_id)
    if not meta:
        return page_id, 0, 0, 0.0
    lives, texts, snapshots = lives_of(versions, reverts)
    con, cur = connect()
    hexh = lambda h: h.hex() if h else None
    batched_executemany(cur, "INSERT IGNORE INTO sentence (hash, text_fi) VALUES (?, ?)",
                        [(h, t) for h, t in texts.items()])
    events = []
    for h, t in texts.items():
        ys = years(t)
        if ys:
            events.append((h, f"{ys[0]}-01-01", f"{ys[-1] + 1}-01-01"))
    batched_executemany(cur, "INSERT IGNORE INTO sentence_event (hash, event_from, event_to) VALUES (?,?,?)", events)

    cur.execute("SET system_versioning_insert_history = 1")
    cols = "page_id, hash, section, prev_hash, pos, born_rev, died_rev, kind, successor_hash, similarity, row_start"
    dead = [l for l in lives if l["died"] is not None and l["died"] > l["born"]]
    batched_executemany(cur, f"INSERT INTO sentence_life ({cols}, row_end) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        [(page_id, l["hash"], l["section"], l["prev"], l["pos"], l["born_rev"], l["died_rev"],
                          l["kind"], l["successor"], l["similarity"], l["born"], l["died"]) for l in dead])
    batched_executemany(cur, f"INSERT INTO sentence_life ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        [(page_id, l["hash"], l["section"], l["prev"], l["pos"], l["born_rev"], None,
                          "alive", None, None, l["born"]) for l in lives if l["died"] is None])
    cur.execute("SET system_versioning_insert_history = 0")

    batched_executemany(cur, """INSERT INTO article_frame (page_id, ts, rev_id, hashes, edits, deaths)
        VALUES (?,?,?,?,?,?) ON DUPLICATE KEY UPDATE hashes=VALUES(hashes)""",
                        [(page_id, ts, rev, json.dumps([hexh(h) for h in order]), e, d)
                         for ts, rev, order, e, d in keyframes(snapshots)])
    ghosts = sum(1 for l in dead if l["kind"] in ("erased", "rewritten"))
    cur.execute("UPDATE article SET ghost_count = ? WHERE page_id = ?", (ghosts, page_id))
    con.commit()
    con.close()
    return page_id, len(lives), ghosts, time.time() - t0


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pages", type=int, nargs="+")
    g.add_argument("--heroes", action="store_true")
    g.add_argument("--all", action="store_true")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--reset", action="store_true", help="drop and recreate the sentence tables first")
    args = p.parse_args()

    con, cur = connect()
    if args.reset:
        apply_schema(cur, drop=("sentence_life", "sentence", "sentence_event", "article_frame"))
    else:
        apply_schema(cur)
    if args.all:
        cur.execute("SELECT page_id FROM article ORDER BY versions DESC")
        pages = [r[0] for r in cur.fetchall()]
    else:
        pages = args.pages or hero_pages()
    cur.execute("SELECT DISTINCT page_id FROM article_frame")
    done = {r[0] for r in cur.fetchall()}
    con.close()
    todo = [pg for pg in pages if pg not in done]
    print(f"{len(todo)} pages to do ({len(pages) - len(todo)} already loaded)", flush=True)

    t0 = time.time()
    run = Pool(args.workers).imap_unordered if args.workers > 1 else map
    total_lives = total_ghosts = 0
    for k, (page_id, n_lives, n_ghosts, secs) in enumerate(run(process_page, todo), 1):
        total_lives, total_ghosts = total_lives + n_lives, total_ghosts + n_ghosts
        print(f"[{k}/{len(todo)}] page {page_id}: {n_lives:,} lives, {n_ghosts:,} ghosts, {secs:.1f} s", flush=True)
    print(f"Done: {total_lives:,} lives, {total_ghosts:,} ghosts in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
