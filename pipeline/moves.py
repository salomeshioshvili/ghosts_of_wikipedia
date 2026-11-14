"""Find sentences that didn't die but MOVED: removed from one page while the same sentence
lives on another page (e.g. the 1918 article's "Sodan nimet" section, cut out on 5 Nov 2006 into
the article Suomen sisällissodan nimet). Run after lives.py, whenever new pages are loaded:

    python pipeline/moves.py

A removal counts as a move when the identical sentence was alive on another page from at most
30 days after the removal, and still alive one day before it. Recomputes ghost counts without the
moved sentences (and without ghosts that lived under a week). The API calls find_moves(cur, page_id)
when it loads a single article on demand.
"""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import apply_schema, connect


def find_moves(cur, page_id=None):
    """Fill sentence_move for every page, or only for moves from/to one page. Returns moves found."""
    only = "AND (d.page_id = ? OR o.page_id = ?)" if page_id else ""
    params = (page_id, page_id) if page_id else ()
    if page_id:
        cur.execute("DELETE FROM sentence_move WHERE page_id = ? OR to_page_id = ?", params)
    else:
        cur.execute("DELETE FROM sentence_move")
    cur.execute(f"""
        INSERT IGNORE INTO sentence_move (page_id, hash, died_rev, to_page_id)
        SELECT d.page_id, d.hash, d.died_rev, MIN(o.page_id)
        FROM sentence_life FOR SYSTEM_TIME ALL AS d
        JOIN sentence_life FOR SYSTEM_TIME ALL AS o
          ON o.hash = d.hash AND o.page_id <> d.page_id
         AND o.row_start <= d.row_end + INTERVAL 30 DAY
         AND o.row_end   >= d.row_end - INTERVAL 1 DAY
        WHERE d.died_rev IS NOT NULL AND d.kind IN ('erased', 'rewritten') {only}
        GROUP BY d.page_id, d.hash, d.died_rev""", params)
    which = ("a.page_id = ? OR a.page_id IN (SELECT page_id FROM sentence_move WHERE to_page_id = ?)" if page_id
             else "a.page_id IN (SELECT DISTINCT page_id FROM article_frame)")
    cur.execute(f"""
        UPDATE article a SET ghost_count = (
          SELECT COUNT(DISTINCT l.hash) FROM sentence_life FOR SYSTEM_TIME ALL AS l
          WHERE l.page_id = a.page_id AND l.kind IN ('erased', 'rewritten')
            AND TIMESTAMPDIFF(DAY, l.row_start, l.row_end) >= 7
            AND NOT EXISTS (SELECT 1 FROM sentence_move m
                            WHERE m.page_id = l.page_id AND m.hash = l.hash AND m.died_rev = l.died_rev))
        WHERE {which}""", params)
    cur.execute("SELECT COUNT(*) FROM sentence_move" + (" WHERE page_id = ? OR to_page_id = ?" if page_id else ""),
                params)
    return cur.fetchone()[0]


def main():
    t0 = time.time()
    con, cur = connect()
    apply_schema(cur)
    cur.execute("ALTER TABLE sentence_life ADD INDEX IF NOT EXISTS hash_key (hash)")   # tables made before the index
    moved = find_moves(cur)
    con.commit()
    print(f"{moved:,} removals were moves to another article ({time.time() - t0:.1f} s)")


if __name__ == "__main__":
    main()
