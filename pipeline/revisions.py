"""Load every revision of dataset M, WITHOUT text, into `revision`, and one row per page into `article`.

    python pipeline/revisions.py            # ~862,076 rows; a few minutes

Also marks reverts: a version whose sha1 equals an earlier version that is not its parent.
Creates the tables from db/schema.sql if they do not exist yet.
"""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import apply_schema, batched_executemany, connect
from parquet_m import naive_utc, read_all

COLUMNS = ["page_id", "title", "rev_id", "parent_id", "timestamp", "user", "anonymous",
           "comment", "minor", "sha1", "bytes"]


def mark_reverts(versions):
    """versions: list of dicts sorted oldest first (one page). Sets v['is_revert']."""
    seen = {}
    for i, v in enumerate(versions):
        earlier = seen.get(v["sha1"])
        v["is_revert"] = bool(v["sha1"]) and earlier is not None and earlier < i - 1
        if v["sha1"] and v["sha1"] not in seen:
            seen[v["sha1"]] = i
    return versions


def main():
    t0 = time.time()
    rows = list(read_all(COLUMNS))
    print(f"read {len(rows):,} revisions in {time.time() - t0:.0f} s", flush=True)

    pages = {}
    for r in rows:
        r["timestamp"] = naive_utc(r["timestamp"])
        pages.setdefault(r["page_id"], []).append(r)

    revision_rows, article_rows = [], []
    for page_id, versions in pages.items():
        versions.sort(key=lambda v: (v["timestamp"], v["rev_id"]))
        mark_reverts(versions)
        for v in versions:
            revision_rows.append((v["rev_id"], page_id, v["parent_id"], v["timestamp"], v["user"],
                                  bool(v["anonymous"]), v["comment"], bool(v["minor"]), v["sha1"],
                                  v["bytes"], v["is_revert"]))
        article_rows.append((page_id, versions[-1]["title"], len(versions),
                             versions[0]["timestamp"], versions[-1]["timestamp"]))

    con, cur = connect()
    apply_schema(cur)
    batched_executemany(cur, """INSERT IGNORE INTO revision (rev_id, page_id, parent_id, ts, user,
        anonymous, comment, minor, sha1, bytes, is_revert) VALUES (?,?,?,?,?,?,?,?,?,?,?)""", revision_rows)
    batched_executemany(cur, """INSERT INTO article (page_id, title_fi, versions, first_edit, last_edit)
        VALUES (?,?,?,?,?) ON DUPLICATE KEY UPDATE title_fi=VALUES(title_fi), versions=VALUES(versions),
        first_edit=VALUES(first_edit), last_edit=VALUES(last_edit)""", article_rows)
    con.commit()
    reverts = sum(r[-1] for r in revision_rows)
    print(f"loaded {len(revision_rows):,} revisions of {len(article_rows):,} articles "
          f"({reverts:,} reverts) in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
