# Ghosts of Wikipedia

**What Wikipedia forgot, and who made it forget.** Wikipedia keeps every sentence anyone ever wrote, but only shows the survivors. We bring back the deleted ones as ghosts, show how each one died, and flag removals that look coordinated.

Built at Junction 2026 for MariaDB's *Wikipedia Through Time* challenge, on MariaDB's dataset M: 862,076 versions of 19,742 Finnish history articles (2002 – 1 Oct 2026). Starting point and credit: MariaDB's [Wikipedia Time Machine](https://github.com/MariaDB/mariadb-system-versioning-wikipedia) and [datasets](https://github.com/MariaDB/mariadb-wikipedia-datasets).

## Run it

MariaDB 12.3 on port 3306 (native install, or `docker compose up -d --wait`), database/user/password `ghosts`. Then:

```powershell
copy .env.example .env
python -m pip install --user -r requirements.txt

python pipeline/download.py                      # dataset M, 16 Parquet files, 315 MB
python pipeline/revisions.py                     # all 862,076 revisions (no text) -> revision, article
python pipeline/lives.py --pages 1150 250972 1291614 640247 11834   # the 1918 war and its sister articles
python pipeline/moves.py                         # sentences that moved to another article
python pipeline/stats.py                         # half-life of a sentence, % deleted -> data/stats.json
python -m uvicorn api.main:app --port 8000       # http://localhost:8000/docs

cd web && npm install && npm run dev             # http://localhost:5173 (proxies /api to :8000)
```

Rebuild the sentence tables from scratch: add `--reset` to `lives.py`. All 50 hero articles: `lives.py --heroes --workers 4`.

## How it works

1. **revision**: every version's metadata. A version whose `sha1` equals an earlier, non-parent version is a revert (46,972 of them).
2. **lives.py**: each version's wikitext is stripped (`mwparserfromhell`; reference sections skipped), split into sentences and hashed. Diffing consecutive versions gives each sentence's births and deaths. Versions a revert undid within 24 h are skipped, so vandalism and page blanking don't create fake ghosts. Each death is classified against the sentences added in the same edit: **typo** (similarity ≥ 0.9), **rewritten** (0.6–0.9, with "reincarnated as"), **erased** (< 0.6), **reverted**.
3. **sentence_life** is `WITH SYSTEM VERSIONING`. Dead lives are written as history rows with Wikipedia's real times (`system_versioning_insert_history`), so `FOR SYSTEM_TIME AS OF` shows any day and `FOR SYSTEM_TIME ALL` shows every ghost.
4. **moves.py**: a sentence removed from one article but alive in another is "moved", not a ghost (e.g. the 1918 article's names section, moved out on 5 Nov 2006).
5. **sentence_event** gives each sentence the years it talks about (an application-time `PERIOD`), next to when Wikipedia said it: event time vs edit time.
6. **sentence_vec** holds EmbeddingGemma vectors with a `VECTOR INDEX`; ghost search is one query: vector search, then time travel over the dead.

## MariaDB features used
System-versioned tables · `system_versioning_insert_history` · `FOR SYSTEM_TIME AS OF / ALL` · application-time periods · `VECTOR(768)` + `VECTOR INDEX` + `VEC_DISTANCE_COSINE` · JSON columns. *(Numbers and timings: fill in after the runs.)*

## Folders

| Folder | What | Owner |
| --- | --- | --- |
| `db/`, `pipeline/`, `api/` | schema, data pipeline, FastAPI | Person 1 — Data + MariaDB |
| `web/`, `mock/` | React + Vite frontend, mock JSON in the API shapes | Person 2 — Experience |
| `ai/` | EmbeddingGemma, Gemma/Gemini translations + biography, coordination score | Person 3 — Intelligence + story |
| `deploy/` | Modal app serving `api/` + `web/dist` | Shared |
| `docs/` | build doc, pitch, video script, Codex log | everyone |

## Licence and credit
Wikipedia text: CC BY-SA 4.0, credit Wikipedia and its authors; every result links to its revision. Hero article list from MariaDB's time-machine demo (MIT).
