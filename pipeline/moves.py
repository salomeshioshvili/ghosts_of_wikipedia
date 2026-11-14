"""Find sentences that didn't die but MOVED: removed from one page while the same sentence
lives on another page (e.g. the 1918 article's "Sodan nimet" section, cut out on 5 Nov 2006 into
the article Suomen sisällissodan nimet). Run after lives.py, whenever new pages are loaded:

    python pipeline/moves.py

A removal counts as a move when the identical sentence was alive on another page from at most
30 days after the removal, and still alive one day before it. Recomputes each article's ghost count
without the moved sentences.
"""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import apply_schema, connect


def main():
    t0 = time.time()
    con, cur = connect()
    apply_schema(cur)
    cur.execute("DELETE FROM sentence_move")
    cur.execute("""
        INSERT IGNORE INTO sentence_move (page_id, hash, died_rev, to_page_id)
        SELECT d.page_id, d.hash, d.died_rev, MIN(o.page_id)
        FROM sentence_life FOR SYSTEM_TIME ALL AS d
        JOIN sentence_life FOR SYSTEM_TIME ALL AS o
          ON o.hash = d.hash AND o.page_id <> d.page_id
         AND o.row_start <= d.row_end + INTERVAL 30 DAY
         AND o.row_end   >= d.row_end - INTERVAL 1 DAY
        WHERE d.died_rev IS NOT NULL AND d.kind IN ('erased', 'rewritten')
        GROUP BY d.page_id, d.hash, d.died_rev""")
    cur.execute("SELECT COUNT(*) FROM sentence_move")
    moved = cur.fetchone()[0]
    cur.execute("""
        UPDATE article a SET ghost_count = (
          SELECT COUNT(DISTINCT l.hash) FROM sentence_life FOR SYSTEM_TIME ALL AS l
          WHERE l.page_id = a.page_id AND l.kind IN ('erased', 'rewritten')
            AND NOT EXISTS (SELECT 1 FROM sentence_move m
                            WHERE m.page_id = l.page_id AND m.hash = l.hash AND m.died_rev = l.died_rev))
        WHERE a.page_id IN (SELECT DISTINCT page_id FROM article_frame)""")
    con.commit()
    print(f"{moved:,} removals were moves to another article ({time.time() - t0:.1f} s)")


if __name__ == "__main__":
    main()
