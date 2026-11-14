# Ghosts of Wikipedia

**What Wikipedia forgot, and who made it forget.** Wikipedia keeps every sentence anyone ever wrote, but only shows the survivors. We bring back the deleted ones as ghosts, show how each one died, and flag removals that look coordinated.

Built at Junction 2026 for MariaDB's *Wikipedia Through Time* challenge, on MariaDB's dataset M: 862,076 versions of 19,742 Finnish history articles (2002 – 1 Oct 2026). Starting point and credit: MariaDB's [Wikipedia Time Machine](https://github.com/MariaDB/mariadb-system-versioning-wikipedia) and [datasets](https://github.com/MariaDB/mariadb-wikipedia-datasets).

## Run it

**See [RUNNING.md](RUNNING.md)**: a 2-minute frontend-only look, the full app with MariaDB, and the AI extras.
Short version (MariaDB 12.3 on port 3306, database/user/password `ghosts`):

```powershell
copy .env.example .env
python -m pip install --user -r requirements.txt
python pipeline/download.py                       # dataset M, 315 MB
python pipeline/revisions.py                      # revision + article tables
python -m uvicorn api.main:app --reload --port 8000
cd web; npm install; npm run dev                  # http://localhost:5173
```

Articles are processed the first time they are opened. To prepare the demo set up front:
`python pipeline/lives.py --heroes --workers 4`, then `moves.py` and `stats.py`.

## What you can do

- **Search any of the 19,742 articles** by title; open one to see its deleted sentences ("ghosts") in place.
- **Death certificate** per ghost: born, died, who removed it and why, earlier lives, what it came back as. Plus a **tombstone**.
- **Time slider / Play**: the article as it stood on any day, 2003–2026.
- **Life story**: Gemma's biography of the article; each chapter jumps the timeline there.
- **Same story, every language**: what up to 12 Wikipedias call a topic, every rename and whether it was undone, locks, revert rates, with neutral conflict signals.
- **Meaning search** over deleted sentences (EmbeddingGemma + MariaDB vectors) and a **coordination score** per removal.

## How it works

1. **revision**: every version's metadata. A version whose `sha1` equals an earlier, non-parent version is a revert (46,972 of them).
2. **lives.py**: each version's wikitext is stripped (`mwparserfromhell`; reference sections skipped), split into sentences and hashed. Diffing consecutive versions gives each sentence's births and deaths. Versions a revert undid within 24 h are skipped, so vandalism and page blanking don't create fake ghosts. Each death is classified against the sentences added in the same edit: **typo** (similarity ≥ 0.9), **rewritten** (0.6–0.9, with "reincarnated as"), **erased** (< 0.6), **reverted**.
3. **sentence_life** is `WITH SYSTEM VERSIONING`. Dead lives are written as history rows with Wikipedia's real times (`system_versioning_insert_history`), so `FOR SYSTEM_TIME AS OF` shows any day and `FOR SYSTEM_TIME ALL` shows every ghost.
4. **moves.py**: a sentence removed from one article but alive in another is "moved", not a ghost (e.g. the 1918 article's names section, moved out on 5 Nov 2006).
5. **sentence_event** gives each sentence the years it talks about (an application-time `PERIOD`), next to when Wikipedia said it: event time vs edit time.
6. **sentence_vec** holds EmbeddingGemma vectors with a `VECTOR INDEX`; ghost search is one query: vector search, then time travel over the dead.

## MariaDB features used
System-versioned tables (`sentence_life`, and `lang_compare`, which keeps every cross-language snapshot) · `system_versioning_insert_history` · `FOR SYSTEM_TIME AS OF / ALL` · application-time periods · `VECTOR(768)` + `VECTOR INDEX` + `VEC_DISTANCE_COSINE` · JSON columns. *(Numbers and timings: fill in after the runs.)*

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
