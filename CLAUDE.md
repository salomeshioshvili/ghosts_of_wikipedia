# Ghosts of Wikipedia: context for coding agents

Hackathon project (Junction 2026, deadline Sun 10:00, submit 09:00). Main challenge: MariaDB "Wikipedia Through Time". Read `README.md` and `Ghosts of Wikipedia — Build Doc.md` for the full plan.

## What we build
A web app over MariaDB's dataset M (862,076 versions of 19,742 Finnish history articles) that shows deleted sentences as ghosts in place, a time slider + time-lapse, a ghost hunt, a death certificate per ghost, ghost search by meaning, a Gemini-narrated article biography, and a coordination score with evidence. Demo article: Suomen sisällissota, page_id 1150.

## Conventions (follow these)
- All times are UTC. Every DB connection runs `SET time_zone = '+00:00'` (`pipeline/common.connect`).
- MariaDB Python connector uses `?` placeholders. `FOR SYSTEM_TIME AS OF TIMESTAMP ?` refuses bound params: format the timestamp into the SQL from a parsed `datetime` only.
- Hashes are 20-byte SHA-1 (`BINARY(20)`) in the DB and lowercase hex in the API.
- History rows go in with `SET system_versioning_insert_history = 1` and explicit `row_start`/`row_end`; current rows with `row_start` only. Batch inserts by size (`batched_executemany`), the packet limit is 64 MB in our docker-compose.
- Never return or display `user` when `anonymous` is true. Never call an editor a bad actor: the coordination score measures behaviour, with evidence.
- The API shapes are frozen in the build doc's "API contract"; change them only with the whole team.
- Keep it simple: scripts over frameworks, one file per job, no ORMs.

## Commands
- DB: `docker compose up -d --wait` (port 3307, user/pass/db `ghosts`)
- Pipeline: `python pipeline/download.py`, `revisions.py`, `lives.py --pages 1150`, `stats.py`
- API: `uvicorn api.main:app --reload --port 8000`
- Logic test without a DB: `lives.lives_of(versions, reverts, parse=...)` takes any parser.
