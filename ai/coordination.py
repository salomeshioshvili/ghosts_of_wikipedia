"""ai/coordination.py - how unusually in sync were the accounts behind a removal?

For every edit that removed text, look at the other accounts removing text from the same
article within 12 hours, and measure five behaviours of that group:

    Timing    how close together their removals were
    Accounts  how many distinct accounts took part, against how many the article's normal
              activity at that time would explain (five editors on a busy day is normal)
    Dormancy  share of them that had been silent for a year or more
    New       share of them first seen in these articles in the last 30 days
    Overlap   share of them that also removed text from the same other articles within a week

Being in sync alone is not suspicious (two people can edit the same morning by chance), so
the group's raw value is  in-sync (timing, accounts)  x  unusual accounts (dormancy, new,
overlap): it is zero unless both are present. The score (0-100) is the percentile of that value
against every other group of accounts that removed text together in the 19,742 articles. It measures behaviour, never intent,
and never names anyone. Anonymous editors (IPs, temporary accounts) count as one member,
"anonymous", and are never profiled. Bots and reverts are left out: bots edit in sync by
design, and undoing vandalism is not a removal.

Runs from dataset M's Parquet files (no database needed), from the repo root:
    python ai/coordination.py              # score every removal, test on planted rings,
                                           # show the top groups on 1150
    python ai/coordination.py --db         # also write scores for every ghost into the
                                           # `coordination` table (needs Person 1's DB)
Writes data/coordination_eval.json (results for the README) and data/cache/coordination_revs.json.
"""
import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import parquet_m  # noqa: E402  (Person 1's reader; also loads the repo .env)

WINDOW = pd.Timedelta(hours=12)       # removals this close on the same article form a group
MONTH = pd.Timedelta(days=30)
WEEK = pd.Timedelta(days=7)
DAY = pd.Timedelta(days=1)
YEAR = pd.Timedelta(days=365)
MIN_REMOVED = 20                      # bytes; smaller cuts are typo-level
HIGH = 95                             # score at or above this counts as "flagged" (0.4% of ordinary groups)
ANON = "anonymous"
BOT = re.compile(r"bot\b|bot$|^bot", re.I)
REVERT_SUMMARY = re.compile(r"kumottiin|kumosi|palautettiin|hylättiin|\brv\b|\brvv\b|undid|revert|reverted",
                            re.I)
FEATURES = ["timing", "accounts", "dormancy", "new", "overlap"]
CACHE = ROOT / "data" / "cache" / "coordination_revs.json"
EVAL = ROOT / "data" / "coordination_eval.json"


# ---------- data ----------

def load_revisions() -> pd.DataFrame:
    cols = ["page_id", "rev_id", "parent_id", "timestamp", "user", "anonymous", "comment", "sha1", "bytes"]
    t = pa.concat_tables([pq.ParquetFile(p).read(columns=cols) for p in parquet_m.files()])
    if t.num_rows == 0:
        raise SystemExit("no Parquet files in data/m: run python pipeline/download.py first")
    df = t.to_pandas()
    df["ts"] = df["timestamp"].dt.tz_convert(None) if df["timestamp"].dt.tz is not None else df["timestamp"]
    df = df.drop(columns="timestamp").sort_values(["page_id", "ts", "rev_id"]).reset_index(drop=True)
    df["delta"] = df.groupby("page_id")["bytes"].diff()
    # a revert = text identical to an earlier, non-parent version of the same page (build doc rule)
    first = df.groupby(["page_id", "sha1"])["rev_id"].transform("first")
    df["is_revert"] = (first != df["rev_id"]) & (first != df["parent_id"])
    df["is_revert"] |= df["comment"].fillna("").str.contains(REVERT_SUMMARY)
    df["member"] = np.where(df["anonymous"], ANON, df["user"].fillna(ANON))
    df["is_bot"] = df["user"].fillna("").str.contains(BOT) & ~df["anonymous"]
    return df


def removals(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["delta"] <= -MIN_REMOVED) & ~df["is_revert"] & ~df["is_bot"]]


class History:
    """Per-account edit times (dormancy, newness) and removal pages (overlap)."""

    def __init__(self, df: pd.DataFrame):
        reg = df[~df["anonymous"]].sort_values("ts")
        self.times = {u: g["ts"].to_numpy() for u, g in reg.groupby("user", sort=False)}
        rem = removals(reg).sort_values("ts")
        self.rtimes, self.rpages = {}, {}
        for user, g in rem.groupby("user", sort=False):
            self.rtimes[user] = g["ts"].to_numpy()
            self.rpages[user] = g["page_id"].to_numpy()

    def dormant(self, user, t) -> bool:
        """Silent for a year or more before t (and not brand new)."""
        ts = self.times.get(user)
        if ts is None:
            return False
        i = np.searchsorted(ts, np.datetime64(t - WINDOW))
        return i > 0 and (t - WINDOW) - pd.Timestamp(ts[i - 1]) >= YEAR

    def new(self, user, t) -> bool:
        """First seen in these articles within the 30 days before t."""
        ts = self.times.get(user)
        return ts is not None and pd.Timestamp(ts[0]) >= t - MONTH

    def other_pages(self, user, t, page) -> set:
        """Other articles this account removed text from within a week of t."""
        ts = self.rtimes.get(user)
        if ts is None:
            return set()
        lo, hi = np.searchsorted(ts, [np.datetime64(t - WEEK), np.datetime64(t + WEEK)])
        return set(self.rpages[user][lo:hi].tolist()) - {page}


# ---------- features and score ----------

def group_features(members: list, times: list, t, page, hist: History, expected: float = 0.0) -> dict:
    """members: distinct accounts in the group (ANON at most once). times: their removal times.
    expected: distinct removers per day this article normally saw at that time."""
    k = len(members)
    reg = [m for m in members if m != ANON]
    if k < 2:
        return dict(timing=0.0, accounts=0.0, dormancy=0.0, new=0.0, overlap=0.0, expected=expected,
                    k=k, spread_h=0.0, n_dormant=0, n_new=0, n_overlap=0, shared_pages=0, n_reg=len(reg))
    spread_h = (max(times) - min(times)).total_seconds() / 3600
    n_dormant = sum(hist.dormant(m, t) for m in reg)
    n_new = sum(hist.new(m, t) for m in reg)
    pages = {m: hist.other_pages(m, t, page) for m in reg}
    shared = set()
    n_overlap = 0
    for m in reg:
        others = set().union(*(pages[o] for o in reg if o != m)) if len(reg) > 1 else set()
        common = pages[m] & others
        if common:
            n_overlap += 1
            shared |= common
    denom = max(len(reg), 1)
    quiet = 1 / (1 + expected)            # 1 on a quiet article, near 0 on a very busy one
    return dict(timing=(1 - min(spread_h, 12) / 12) * quiet,
                accounts=min((k - 1) / (k - 1 + expected), 1.0), expected=expected,
                dormancy=n_dormant / denom, new=n_new / denom, overlap=n_overlap / denom,
                k=k, spread_h=spread_h, n_dormant=n_dormant, n_new=n_new, n_overlap=n_overlap,
                shared_pages=len(shared), n_reg=len(reg))


SYNC = ["timing", "accounts"]
TRAITS = ["dormancy", "new", "overlap"]


def raw(f: dict) -> float:
    sync = sum(f[x] for x in SYNC) / len(SYNC)
    traits = sum(f[x] for x in TRAITS) / len(TRAITS)
    return sync * traits


def evidence(f: dict, score: int, n_groups: int) -> list:
    if f["k"] < 2:
        return [{"label": "Accounts", "value": "one account",
                 "explain": "No other account removed text from this article within 12 hours, "
                            "so there is no group to measure."}]
    anon = " (anonymous editors counted as one)" if f["k"] > f["n_reg"] else ""
    sp = f["spread_h"]
    spread = f"{round(sp * 60)} minutes" if sp < 1 else f"{sp:.1f} hours"
    reg = max(f["n_reg"], 1)
    ev = [
        {"label": "Accounts", "value": f"{f['k']} accounts{anon}",
         "explain": "Distinct accounts that removed text from this article within 12 hours of each other."},
        {"label": "Timing", "value": f"all within {spread}",
         "explain": "Time between the first and last removal in the group. Ordinary editing is spread out."},
        {"label": "Activity", "value": f"normally {f['expected']:.1f} removers a day here",
         "explain": "How many accounts usually removed text from this article per day that month. "
                    "A group on a busy article is less unusual than the same group on a quiet one."},
    ]
    if f["n_reg"]:
        ev.append({"label": "Dormancy", "value": f"{f['n_dormant']} of {reg} silent 1+ year",
                   "explain": "Accounts that had made no edit in these articles for a year or more beforehand."})
        ev.append({"label": "New", "value": f"{f['n_new']} of {reg} first seen within 30 days",
                   "explain": "Accounts whose first edit in these articles came less than a month earlier."})
        ev.append({"label": "Overlap", "value": f"{f['n_overlap']} of {reg} also cut {f['shared_pages']} other articles",
                   "explain": "Accounts that also removed text from the same other articles within a week."})
    ev.append({"label": "Baseline", "value": f"higher than {score}% of {n_groups:,} groups",
               "explain": "How in sync they were, times how unusual the accounts were, compared with every "
                          "group of accounts that removed text together in the 19,742 articles. "
                          "Zero when the accounts look ordinary, however close the timing."})
    return ev


def score_all(df: pd.DataFrame, hist: History):
    """Features for every removal edit; returns (DataFrame of removals, sorted raw scores of groups)."""
    rem = removals(df)
    out = []
    for page, g in rem.groupby("page_id", sort=False):
        ts = g["ts"].tolist()
        members = g["member"].tolist()
        tarr = g["ts"].to_numpy()
        lo = hi = 0
        for i, t in enumerate(ts):
            # the article's normal pace: removals per day in the 30 days around, outside this window
            a, b = np.searchsorted(tarr, [np.datetime64(t - 15 * DAY), np.datetime64(t + 15 * DAY)])
            while ts[lo] < t - WINDOW:
                lo += 1
            while hi < len(ts) and ts[hi] <= t + WINDOW:
                hi += 1
            first_time = {}
            for j in range(lo, hi):
                first_time.setdefault(members[j], ts[j])
            expected = ((b - a) - (hi - lo)) / 29
            f = group_features(list(first_time), list(first_time.values()), t, page, hist, expected)
            out.append({"rev_id": int(g["rev_id"].iat[i]), "page_id": int(page), "ts": t, **f})
    feats = pd.DataFrame(out)
    feats["raw"] = feats[SYNC].mean(axis=1) * feats[TRAITS].mean(axis=1)
    groups = np.sort(feats.loc[feats["k"] >= 2, "raw"].to_numpy())
    return feats, groups


def percentile(groups: np.ndarray, value: float) -> int:
    return int(round(100 * np.searchsorted(groups, value, side="left") / max(len(groups), 1)))


# ---------- testing on planted rings and random groups ----------

def planted_ring(rng: random.Random, level: str) -> dict:
    """A synthetic ring, clearly fake, built to test the score. Never written to the database."""
    k = rng.randint(3, 5) if level == "obvious" else rng.randint(2, 3)
    spread = rng.uniform(0.1, 2) if level == "obvious" else rng.uniform(1, 8)
    sneaky = rng.random() < 0.5
    share = (lambda: rng.uniform(0.6, 1.0)) if level == "obvious" else (lambda: rng.uniform(0.0, 0.6))
    expected = rng.uniform(0, 0.3) if level == "obvious" else rng.uniform(0.2, 1.5)
    f = dict(timing=(1 - min(spread, 12) / 12) / (1 + expected), accounts=(k - 1) / (k - 1 + expected),
             dormancy=share() if sneaky else 0.0, new=0.0 if sneaky else share(), overlap=share())
    return f


def random_groups(df, feats, hist, rng, n=500):
    """Ordinary removers from different times, put together as if they acted at once."""
    singles = feats[(feats["k"] == 1)]
    pool = df.set_index("rev_id").loc[singles["rev_id"], ["member", "page_id", "ts"]].reset_index()
    pool = pool[pool["member"] != ANON]
    by_page = {p: g["ts"].to_numpy() for p, g in removals(df).groupby("page_id")}

    def pace(page, t):
        a, b = np.searchsorted(by_page[page], [np.datetime64(t - 15 * DAY), np.datetime64(t + 15 * DAY)])
        return (b - a - 1) / 29

    out = []
    for _ in range(n):
        pick = pool.sample(rng.randint(2, 4), random_state=rng.randint(0, 10 ** 9))
        if pick["member"].nunique() < len(pick):
            continue
        anchor = pick.iloc[0]
        times = [anchor["ts"] + pd.Timedelta(hours=rng.uniform(0, 12)) for _ in range(len(pick))]
        # each member judged at the time of their own real edit, then placed in one window
        f = group_features(pick["member"].tolist(), times, anchor["ts"], anchor["page_id"], hist,
                           expected=pace(anchor["page_id"], anchor["ts"]))
        out.append(f)
    return out


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="store_true", help="write scores for every ghost into the coordination table")
    ap.add_argument("--page", type=int, default=1150, help="article to show the top groups for")
    args = ap.parse_args()

    t0 = time.time()
    df = load_revisions()
    hist = History(df)
    print(f"{len(df):,} revisions loaded in {time.time() - t0:.0f}s")
    feats, groups = score_all(df, hist)
    feats["score"] = [percentile(groups, r) if k >= 2 else 0 for r, k in zip(feats["raw"], feats["k"])]
    print(f"{len(feats):,} removals scored, {len(groups):,} of them in a group of 2+ accounts "
          f"({time.time() - t0:.0f}s)")

    rng = random.Random(1918)
    results = {}
    for level in ("obvious", "subtle"):
        scores = [percentile(groups, raw(planted_ring(rng, level))) for _ in range(500)]
        results[f"planted_{level}_caught"] = round(sum(s >= HIGH for s in scores) / len(scores), 3)
    rand = random_groups(df, feats, hist, rng)
    rand_scores = [percentile(groups, raw(f)) for f in rand]
    results["random_groups_flagged"] = round(sum(s >= HIGH for s in rand_scores) / max(len(rand_scores), 1), 3)

    example = planted_ring(random.Random(7), "obvious")
    ex_f = dict(example, k=4, spread_h=0.6, n_reg=4, n_dormant=3, n_new=0, n_overlap=4, shared_pages=3, expected=0.1)
    ex_f.update(timing=(1 - 0.6 / 12) / 1.1, accounts=3 / 3.1, dormancy=0.75, new=0.0, overlap=1.0)
    ex_score = percentile(groups, raw(ex_f))
    summary = {
        "flag_threshold": HIGH,
        "removals_scored": int(len(feats)),
        "groups_of_2_plus": int(len(groups)),
        "share_of_removals_in_groups": round(len(groups) / len(feats), 3),
        **results,
        "method": "percentile of (in-sync: timing, accounts vs the article's normal pace) x "
                  "(unusual accounts: dormancy, new, shared removals elsewhere) among all groups of 2+ "
                  "accounts removing text from the same article within 12 hours; bots and reverts excluded",
        "planted_example": {"label": "PLANTED TEST RING - not real editors",
                            "score": ex_score, "evidence": evidence(ex_f, ex_score, len(groups))},
    }
    EVAL.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nPlanted rings caught (score >= {HIGH}): obvious {results['planted_obvious_caught']:.0%}, "
          f"subtle {results['planted_subtle_caught']:.0%}")
    print(f"Random groups of ordinary editors flagged: {results['random_groups_flagged']:.1%}")
    print(f"wrote {EVAL.relative_to(ROOT)}")

    grp = feats[feats["k"] >= 2]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({str(r.rev_id): {"score": int(r.score), "evidence": evidence(r._asdict(), int(r.score), len(groups))}
                                 for r in grp.itertuples()}, ensure_ascii=False), encoding="utf-8")

    top = grp[grp["page_id"] == args.page].sort_values("score", ascending=False).head(5)
    print(f"\nMost in-sync removals on page {args.page}:")
    for r in top.itertuples():
        chips = "; ".join(e["value"] for e in evidence(r._asdict(), int(r.score), len(groups)))
        print(f"  {r.ts:%Y-%m-%d %H:%M}  rev {r.rev_id}  score {r.score:>3}  {chips}")

    if args.db:
        write_db(feats, groups)


def write_db(feats: pd.DataFrame, groups: np.ndarray):
    from common import batched_executemany, connect

    con, cur = connect()
    cur.execute("SELECT page_id, HEX(hash), died_rev FROM sentence_life FOR SYSTEM_TIME ALL "
                "WHERE died_rev IS NOT NULL AND kind IN ('erased', 'rewritten')")
    ghosts = cur.fetchall()
    by_rev = feats.set_index("rev_id")
    rows = []
    for page, hash_hex, died_rev in ghosts:
        if died_rev in by_rev.index:
            r = by_rev.loc[died_rev]
            f = r.to_dict()
            score = int(r["score"])
        else:  # the removal was a revert or a bot edit, or too small to score
            f, score = dict(k=1), 0
        rows.append((page, hash_hex, died_rev, score, json.dumps(evidence(f, score, len(groups)), ensure_ascii=False)))
    batched_executemany(cur, "INSERT INTO coordination (page_id, hash, died_rev, score, evidence) "
                             "VALUES (?, UNHEX(?), ?, ?, ?) ON DUPLICATE KEY UPDATE "
                             "score = VALUES(score), evidence = VALUES(evidence)", rows)
    con.commit()
    print(f"coordination table: {len(rows):,} ghosts scored")


if __name__ == "__main__":
    main()
