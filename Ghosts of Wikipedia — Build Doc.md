# Ghosts of Wikipedia — Build Doc

Nov 14, 2026 · @Sivafamily

## Overview

We are building **Ghosts of Wikipedia**: a web app that brings back every sentence Wikipedia deleted, shows how each one died, and flags removals that look coordinated. Demo article: the Finnish Civil War of 1918 (*Suomen sisällissota*, page 1150).

- **One line:** "What Wikipedia forgot, and who made it forget."
- **Sticky line:** "Wikipedia only shows you the survivors. We show you the ghosts."
- **Comparison people already know:** "The Wayback Machine shows old snapshots. We show what was erased."
- **The story:** a historian's grandmother called it the *freedom war* (vapaussota); today everyone says *civil war* (sisällissota). Wikipedia shows one name and no sign it ever changed. We show the change, who made it and when.
- **Who it's for:** historians and academics first (the rep who works with historians called it important), then students, journalists and Wikipedia patrollers.

**Where we stand against the field.** MariaDB already published a demo, the [Wikipedia Time Machine](https://github.com/MariaDB/mariadb-system-versioning-wikipedia): an article as it was on any date, an edit timeline with reverts in red, two dates compared. Many teams will start from it. An article slider is therefore the baseline, not our novelty. Our novelty is the sentence: each sentence's whole life, ghosts you can hunt, search over dead sentences by meaning, a death certificate per ghost, and a coordination score with evidence. We credit their demo as our starting point.

**Decided:** main challenge MariaDB "Wikipedia Through Time"; side prizes Gemini, Gemma, Modal, Codex. Context.dev, AfterQuery and the parked Isobar idea are out.

## MVP scope

The MVP is P0 + P1: the 1918 article with its ghosts visible, playable over time, huntable, searchable and explained, all in English. Everything else waits until that works end to end.

| Priority | Feature | What the user sees | Done by |
| --- | --- | --- | --- |
| P0 | Load and replay | Nothing yet: every sentence of the 1918 article and \~50 neighbours has its lifespan in MariaDB | 21:00 |
| P0 | Ghost layer + slider | Deleted sentences reappear in place, faded, with who removed them, when and the edit summary; slider shows the article on any date | 21:00 |
| P0 | Time-lapse | Press play: 20 years in 20 seconds; sentences fade in, ghosts rise, contested ones flicker | 21:00 |
| P0 | English translations | Every Finnish sentence on screen has an English line under it | 21:00 |
| P1 | Ghost hunt | "17 ghosts haunt this article"; haunted spots glow; click to catch; rare ghosts glow amber | 01:00 |
| P1 | Death certificate | Catching a ghost opens its card: born, died, by whom, why, earlier lives, reincarnated as | 01:00 |
| P1 | Ghost search | Type any claim, get the dead sentences closest in meaning | 01:00 |
| P1 | Article biography | "Tell me this article's story": a 60-second narrated time-lapse written by Gemini | 01:00 |
| P2 | Coordination score | 0–100 on each removal, with evidence chips that explain it | 04:00 |
| P2 | Zoom-out number | One headline figure across all 19,742 articles (half-life of a sentence, or % deleted) | 04:00 |
| P2 | Tombstone + QR | Share card for a caught ghost; QR on the last slide | 04:00 |
| P2 | Deploy | Public URL on Modal, kept warm | 04:00 |

**Stretch, only after P2:** voice for the biography; live ghost watch on Wikipedia's live edit stream (e.g. an F1 page); one contested article outside the dataset (Russia–Ukraine or Sri Lanka), shown neutrally; Hostinger as a second main challenge.

**Cut:** Context.dev, forum scraping, Haunted AI, death row, Morgue Awards, Séance, obituary voice, edit-war replay.

**Rules:** we judge behaviour, never whether text sounds AI-written; we show uncertainty; jokes and tombstones never name people; anonymous editors (IPs, temporary accounts) are never shown as suspects.

## The frontend experience

It should feel like a quiet séance in an archive: a beautiful reading page, with the dead text glowing faintly underneath. Calm, dark, slow and readable; the ghosts are the only thing that moves.

**Look (same system as the pitch deck)**

- Colours: ink background `#0D1117`, panels `#141A23`, bone text `#ECE6D8`, muted text `#AEB8C5`, ghost cyan `#8FE3D8`, ember amber `#E9A23B` (rare ghosts, contested, high scores), paper `#EDE6D6` with ink `#1E1B16` and rust `#A3410F` for certificates.
- Type: Cormorant Garamond for titles and article text, Inter for UI and translations, JetBrains Mono for dates, ids and numbers.
- Ghosts: cyan italic text at about 40% opacity with a soft glow, in the exact place the sentence used to stand. Living text stays bone. Never red; nothing flashes faster than once a second.

**Screens**

1. **Home.** One big question: "What did Wikipedia forget?" with a search box (ghost search). Below it, three haunted articles as cards (1918 war, Winter War, Mannerheim) with their ghost counts, and one global line: "862,076 versions · N ghosts · 19,742 articles".
2. **Article.** A reading column like a good book. Title in Finnish with the English underneath. A "Ghosts" toggle and the counter "17 ghosts haunt this article · 3 caught". A thin timeline pinned to the bottom: a sparkline of edits and deaths over 20 years, a draggable date, and a play button. A slim right rail marks where the ghosts sit, like a scrollbar map.
3. **Catch → certificate.** Clicking a ghost makes it turn solid with a short shimmer, then a paper certificate slides in from the right: the sentence (Finnish + English), its lives on a small timeline, who removed it and the edit summary, "reincarnated as" with the closest living sentence, and the coordination score with evidence chips. Buttons: "Show me when" (jumps the slider) and "Make a tombstone".
4. **Biography mode.** "Tell me this article's story" goes full screen: the time-lapse plays while Gemini's narration appears as large captions, one chapter per turning point (about 60 seconds).
5. **Search results.** Ghosts ranked by meaning, each with its article, the date it died and a match score; click opens its certificate in context.
6. **Tombstone.** A gravestone card: the sentence as the name, born–died years, epitaph = the edit summary that killed it, no usernames. Download as an image or share a link.
7. **Phone (from the QR).** One article, tap ghosts, make a tombstone. Nothing else.

**Motion:** ghosts drift up 8–12 px as they fade (700 ms); new sentences rise in; contested sentences pulse slowly; the certificate slides in over 300 ms. A "reduce motion" setting turns all of it off. Language toggle FI / EN / both, default both.

## Architecture and tech

Python turns dataset M into sentence lives inside MariaDB; FastAPI on Modal serves them to a React app; EmbeddingGemma and Gemini add meaning and English.

&#91;embedded content: architecture · data in, ghosts out\]

Everything meets in MariaDB: the pipeline writes the lives, the AI pieces add vectors, translations and scores, and the API only reads.

| Piece | Tech | Why |
| --- | --- | --- |
| Database | MariaDB 12.3 (`mariadb:lts` in Docker): system versioning, `system_versioning_insert_history`, `VECTOR(768)` + vector index | The core of the product; MariaDB's own demo loaded real edit times this way |
| Pipeline | Python 3.11, pyarrow, mwparserfromhell, difflib, hashlib | Reads the Parquet files, strips wikitext, diffs versions |
| Embeddings | EmbeddingGemma (768 numbers, multilingual) via sentence-transformers on a Modal GPU | Finnish and English in one space; the Gemma prize |
| Language | Gemini API: a fast model for translations, the strongest for the biography | Makes the history readable for anyone; the Gemini prize |
| Coordination | Python + pandas over `revision` | Explainable in one sentence, no black box |
| API | FastAPI + the `mariadb` Python connector | Small and fast to write |
| Frontend | React + Vite + TypeScript, Framer Motion (ghost motion), D3 (timeline), html-to-image + qrcode.react (tombstones) | Fast to build, smooth motion |
| Hosting | A Modal web endpoint serves the API and the built frontend, one container kept warm; MariaDB on a small cloud server or a Modal container with a Volume | One public URL, no cold start on stage |
| Build tools | Codex for scaffolding and review | The Codex prize |

## Data, pipeline and schema

We use MariaDB's dataset M: 862,076 versions of 19,742 Finnish history articles (2002 to 1 Oct 2026), 16 Parquet files, 315 MB, from the [`m-2026-10` release](https://github.com/MariaDB/mariadb-wikipedia-datasets/releases/tag/m-2026-10). Every version has `page_id, title, rev_id, parent_id, timestamp, user, anonymous, comment, minor, sha1, bytes, text`. So editor names and edit summaries exist, and the coordination score runs on real data.

Three facts that shape the build: the text is raw wikitext (strip markup before splitting); 19% of versions are anonymous (an IP, or since 2025 a temporary account like `~2026-33532-4`); the same `sha1` as an earlier, non-parent version means a revert.

**Pipeline (Person 1)**

1. Download the 16 Parquet files. Load **all 862,076 revisions without text** into `revision` (fast; it powers the coordination score and global numbers).
2. Pick the hero set: Suomen sisällissota (1150) plus the 50 articles in the MariaDB demo's [`data/articles.tsv`](https://github.com/MariaDB/mariadb-system-versioning-wikipedia/blob/main/data/articles.tsv) (Talvisota 1256, Jatkosota 440, Lapin sota 6816, Mannerheim 6021 and more).
3. For each hero version, oldest first: strip wikitext with `mwparserfromhell` (drop templates, refs, tables, files, categories), split into sentences (regex on `. ! ?` plus a Finnish abbreviation list: esim., mm., n., jne., ks., vrt.), normalise whitespace and quotes, SHA-1 each sentence.
4. Diff each version against the one before: sentences that appear are born, sentences that disappear die. Record the section heading, the sentence before it (`prev_hash`) and its position. Classify each death against the sentences added in the same version with `difflib`: **typo** (similarity ≥ 0.9, hidden from the hunt), **rewritten** (0.6–0.9, shown with "reincarnated as"), **erased** (< 0.6, a real ghost), **reverted** (died in a revert after living < 24 h: vandalism cleanup).
5. Insert every lifespan with `system_versioning_insert_history` and explicit `row_start` / `row_end` (copy the pattern from the demo's `load.py`; batch by size, the packet limit is 16 MB).
6. Embed every unique sentence with EmbeddingGemma on Modal into `sentence_vec`.
7. Translate on-screen sentences with Gemini into `sentence.text_en` (cache; never translate twice).
8. Precompute \~240 keyframes per hero article for the time-lapse (ordered sentence hashes per frame) into `article_frame`.
9. Global numbers: survival curve over all lifespans (half-life of a sentence) and % of sentences ever written that are now dead.
10. Scale run after the MVP: steps 3–6 on all 19,742 articles, parallel by page on Modal; record the timings for the pitch.

**Schema**

```sql
CREATE TABLE revision (
  rev_id    INT UNSIGNED PRIMARY KEY,
  page_id   INT UNSIGNED NOT NULL,
  parent_id INT UNSIGNED,
  ts        DATETIME(6) NOT NULL,
  user      VARCHAR(255),
  anonymous BOOL NOT NULL,
  comment   TEXT,
  minor     BOOL NOT NULL,
  sha1      CHAR(31),
  bytes     INT UNSIGNED,
  is_revert BOOL NOT NULL DEFAULT 0,
  KEY (page_id, ts), KEY (user, ts)
) CHARACTER SET utf8mb4;

CREATE TABLE sentence (                 -- one row per unique sentence text
  hash    BINARY(20) PRIMARY KEY,       -- SHA-1 of the normalised Finnish text
  text_fi TEXT NOT NULL,
  text_en TEXT                          -- Gemini translation, filled lazily
) CHARACTER SET utf8mb4;

CREATE TABLE sentence_vec (
  hash BINARY(20) PRIMARY KEY,
  emb  VECTOR(768) NOT NULL,            -- EmbeddingGemma
  VECTOR INDEX (emb) M=16 DISTANCE=cosine
);

CREATE TABLE sentence_life (            -- every life of every sentence on every page
  page_id        INT UNSIGNED NOT NULL,
  hash           BINARY(20) NOT NULL,
  section        VARCHAR(255),
  prev_hash      BINARY(20),            -- the sentence before it: where the ghost is drawn
  pos            INT UNSIGNED,          -- position (now, or when it died)
  born_rev       INT UNSIGNED NOT NULL,
  died_rev       INT UNSIGNED,          -- NULL while alive
  kind           ENUM('alive','erased','rewritten','typo','reverted') NOT NULL,
  successor_hash BINARY(20),            -- reincarnated as
  row_start TIMESTAMP(6) GENERATED ALWAYS AS ROW START INVISIBLE,
  row_end   TIMESTAMP(6) GENERATED ALWAYS AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end),
  PRIMARY KEY (page_id, hash),
  KEY start_key (page_id, row_start)    -- the demo found AS OF on old dates needs this
) CHARACTER SET utf8mb4 WITH SYSTEM VERSIONING;

CREATE TABLE article_frame (            -- precomputed keyframes for the time-lapse
  page_id INT UNSIGNED, ts DATETIME(6), rev_id INT UNSIGNED, hashes JSON,
  PRIMARY KEY (page_id, ts)
);
```

**Key queries**

```sql
-- The article on any date
SELECT l.hash, s.text_fi, s.text_en, l.section, l.pos
FROM sentence_life FOR SYSTEM_TIME AS OF TIMESTAMP '2012-03-01' AS l
JOIN sentence s USING (hash)
WHERE l.page_id = 1150 ORDER BY l.pos;

-- Every ghost of an article, with who removed it and why
SELECT l.hash, s.text_fi, s.text_en, l.row_start AS born, l.row_end AS died,
       l.kind, r.user, r.anonymous, r.comment
FROM sentence_life FOR SYSTEM_TIME ALL AS l
JOIN sentence s USING (hash)
JOIN revision r ON r.rev_id = l.died_rev
WHERE l.page_id = 1150 AND l.kind IN ('erased', 'rewritten');

-- The one query: time travel + vector search over dead sentences
WITH near AS (
  SELECT hash, VEC_DISTANCE_COSINE(emb, VEC_FromText(?)) AS d
  FROM sentence_vec ORDER BY d LIMIT 200      -- uses the vector index
)
SELECT l.page_id, s.text_fi, s.text_en, l.row_end AS died, near.d
FROM near
JOIN sentence s USING (hash)
JOIN sentence_life FOR SYSTEM_TIME ALL AS l USING (hash)
WHERE l.kind IN ('erased', 'rewritten')
ORDER BY near.d LIMIT 10;
```

Check before relying on it: whether current rows can be inserted with `row_start` only under `system_versioning_insert_history` (otherwise insert them normally after the history), and that the vector index is used inside the `WITH` (run `EXPLAIN`).

## API contract

Agree these shapes at 17:30 and freeze them; Person 2 builds on fake JSON in `mock/` with exactly these fields until the real API is up. All dates are ISO 8601 UTC; `hash` is hex; every `text_fi` has a `text_en` (may be `null` until translated).

| Endpoint | Returns | Owner |
| --- | --- | --- |
| `GET /api/articles?featured=1` | Article cards for the home page | Person 1 |
| `GET /api/articles/{page_id}?as_of=` | The article on a date, with its ghosts placed | Person 1 |
| `GET /api/articles/{page_id}/timeline` | Keyframes + sentence dictionary for the time-lapse and sparkline | Person 1 |
| `GET /api/ghosts/{page_id}/{hash}` | One ghost's death certificate | Person 1 + 3 |
| `GET /api/search?q=` | Dead sentences closest in meaning | Person 1 |
| `GET /api/articles/{page_id}/biography` | Gemini's story of the article, in chapters | Person 3 |
| `GET /api/stats` | Global numbers and timings | Person 1 |

```json
// GET /api/articles?featured=1
[{ "page_id": 1150, "title_fi": "Suomen sisällissota", "title_en": "Finnish Civil War",
   "ghost_count": 17, "versions": 0, "first_edit": "2003-01-01T00:00:00Z", "last_edit": "2026-09-30T00:00:00Z" }]

// GET /api/articles/1150?as_of=2012-03-01T00:00:00Z
{ "page_id": 1150, "title_fi": "Suomen sisällissota", "title_en": "Finnish Civil War", "as_of": "2012-03-01T00:00:00Z",
  "ghost_count": 17,
  "sentences": [{ "hash": "ab12", "text_fi": "…", "text_en": "…", "section": "Nimitys", "pos": 3, "born": "2006-05-02T00:00:00Z" }],
  "ghosts": [{ "hash": "cd34", "text_fi": "…", "text_en": "…", "section": "Nimitys", "after_hash": "ab12",
                "born": "2005-02-01T00:00:00Z", "died": "2009-11-12T00:00:00Z", "kind": "erased",
                "lives": 3, "rarity": "rare", "coordination_score": 82 }] }

// GET /api/articles/1150/timeline
{ "page_id": 1150,
  "frames": [{ "ts": "2005-02-01T00:00:00Z", "rev_id": 123, "hashes": ["ab12", "cd34"], "edits": 4, "deaths": 1 }],
  "sentences": { "ab12": { "text_fi": "…", "text_en": "…", "born": "…", "died": null, "contested": false } } }

// GET /api/ghosts/1150/cd34
{ "hash": "cd34", "page_id": 1150, "text_fi": "…", "text_en": "…", "kind": "erased", "rarity": "rare",
  "lives": [{ "born": "…", "born_rev": 1, "died": "…", "died_rev": 2,
              "removed_by": { "user": "…", "anonymous": false }, "edit_summary": "…", "revert": false }],
  "reincarnated_as": { "hash": "ef56", "text_fi": "…", "text_en": "…", "similarity": 0.84 },
  "coordination": { "score": 82, "evidence": [
      { "label": "Dormancy", "value": "3 accounts silent 2+ years", "explain": "…" },
      { "label": "Timing", "value": "all within 6 hours", "explain": "…" } ] },
  "links": { "born": "https://fi.wikipedia.org/?oldid=1", "died": "https://fi.wikipedia.org/?oldid=2" } }

// GET /api/search?q=what+Wikipedia+used+to+call+the+war+of+1918
[{ "page_id": 1150, "title_en": "Finnish Civil War", "hash": "cd34", "text_fi": "…", "text_en": "…",
   "died": "…", "similarity": 0.81 }]

// GET /api/articles/1150/biography
{ "page_id": 1150, "chapters": [{ "ts": "…", "caption_en": "…", "rev_ids": [1, 2] }], "audio_url": null }

// GET /api/stats
{ "articles": 19742, "versions": 862076, "sentences": 0, "ghosts": 0,
  "half_life_years": 0, "pct_deleted": 0,
  "timings_ms": { "as_of": 0, "ghosts": 0, "search": 0 } }
```

The zeros and "…" are placeholders for the mock files, not real numbers. Never show `user` for anonymous editors: send `"user": null` when `anonymous` is true.

## Repo setup

One repo, one folder per person, so the three of you rarely touch the same files.

```text
ghosts-of-wikipedia/
  README.md              # what it is, one-command run, MariaDB features used, scoring algorithm
  docker-compose.yml     # mariadb:lts (12.3.x: system versioning + VECTOR)
  .env.example           # DB_URL, GEMINI_API_KEY, MODAL_TOKEN_ID, MODAL_TOKEN_SECRET
  db/schema.sql          # tables from the Data section                         (Person 1)
  pipeline/              #                                                       (Person 1)
    download.py          # the 16 Parquet files of dataset M
    revisions.py         # all 862,076 revisions, no text -> revision
    sentences.py         # wikitext -> sentences -> lifespans (diff + classify)
    load.py              # system_versioning_insert_history, batched by size
    frames.py            # time-lapse keyframes
    stats.py             # half-life, % deleted, timings
  ai/                    #                                                       (Person 3)
    embed_modal.py       # EmbeddingGemma on a Modal GPU -> sentence_vec
    translate.py         # Gemini, cached into sentence.text_en
    biography.py         # Gemini: article history -> chapters
    coordination.py      # coordination score + evidence
  api/                   # FastAPI: endpoints from the API contract             (Person 1)
    main.py  queries.py
  web/                   # React + Vite + TypeScript                            (Person 2)
    src/pages/  Home.tsx  Article.tsx  Search.tsx  Tombstone.tsx
    src/components/  GhostLayer  TimeSlider  Timelapse  GhostCard  Certificate
                     EvidenceChips  BiographyPlayer  TombstoneCard
  mock/                  # JSON fixtures in the exact API shapes                (Person 2)
  deploy/modal_app.py    # serves api/ + the built web/ at one public URL
  docs/                  # pitch deck link, video script, Codex log, screenshots
```

**Getting started (everyone, 15 minutes)**

1. `git clone` the team repo; create the folders above with an empty `README.md` in each.
2. `docker compose up -d` (MariaDB on port 3306, database `ghosts`), then `mariadb ghosts < db/schema.sql`.
3. `python -m venv .venv && pip install pyarrow mwparserfromhell mariadb fastapi uvicorn google-genai modal sentence-transformers pandas`.
4. `cd web && npm create vite@latest . -- --template react-ts && npm i framer-motion d3 html-to-image qrcode.react`.
5. Copy `.env.example` to `.env` and fill the keys; never commit `.env`.

**Git rules:** each person works on their own branch and merges to `main` at every checkpoint (21:00, 01:00, 04:00). `main` must always run. Commit small and often. Use Codex for at least the scaffolding and one review, and save screenshots in `docs/codex/` for the Codex prize.

## Who does what

Three owners, three folders, one shared contract. Nobody waits on anybody: Person 2 builds on mock JSON, Person 3 builds on the revision table as soon as it exists.

**Person 1 — Data + MariaDB** (strongest at SQL and Python)

*First hour:* MariaDB running in Docker, schema loaded, dataset M downloaded, all revisions loaded into `revision`.

- [ ] Docker MariaDB + `db/schema.sql`
- [ ] All 862,076 revisions into `revision` (no text), reverts marked by `sha1`
- [ ] Wikitext → sentences → lifespans for article 1150, then the 50 hero articles
- [ ] Load lifespans with `system_versioning_insert_history`
- [ ] Time-lapse keyframes
- [ ] FastAPI endpoints in the contract, against real data
- [ ] Vector index + search query (embeddings come from Person 3)
- [ ] Half-life and % deleted; timings on small, medium and large
- [ ] Scale run on all 19,742 articles on Modal
- [ ] MariaDB section of the README: features used, numbers

**Person 2 — Experience** (frontend)

*First hour:* Vite app running, the article page rendering `mock/article_1150.json` with ghosts in place.

- [ ] Mock JSON files in the exact contract shapes
- [ ] Home page with search and the three haunted articles
- [ ] Article page: reading column, ghost layer, FI/EN toggle
- [ ] Timeline bar: sparkline, draggable date, play button; the time-lapse animation
- [ ] Ghost hunt: counter, glowing spots, catch animation, right-rail map
- [ ] Certificate drawer with lives, "reincarnated as", evidence chips
- [ ] Biography player (captions over the time-lapse)
- [ ] Tombstone card + download + QR; phone layout
- [ ] Switch from mock to the real API; deploy on Modal with Person 1

**Person 3 — Intelligence + story**

*First hour:* Gemini and Modal keys working; EmbeddingGemma embedding 1,000 test sentences on a Modal GPU.

- [ ] Embeddings for all hero sentences → `sentence_vec`
- [ ] Gemini translations into `sentence.text_en`, cached
- [ ] Coordination score over `revision`: features, baseline from random editor groups, evidence text
- [ ] One clearly labelled planted ring, and catch / false-flag rates on planted rings for the README
- [ ] Gemini biography for article 1150 (chapters with dates and revision ids)
- [ ] From 04:00: real numbers into the pitch deck, the 2-minute video, README, partner forms
- [ ] Ask the historian rep if we may tell his grandmother story

**Coordination score in one sentence (for judges):** we measure how much more in sync a group of accounts is than normal editors on the same pages — timing, how long they were dormant, account age, page overlap and removing the same sentences — and the score is the percentile against random groups of editors from those articles. Anonymous editors are scored as a group, never named.

**I (Claude) can write for you:** the sentence pipeline and loader, the SQL and FastAPI endpoints, the mock JSON files, the coordination score, the Gemini prompts, and the deck and video script once the data is in.

## Timeline

We submit at 09:00 Sunday, an hour before the 10:00 deadline. Each checkpoint is a gate: if it isn't met, cut scope from the next block instead of sliding the time.

1. **17:00–17:30 — Setup.** Repo, Docker MariaDB, keys, dataset M downloading.
2. **17:30 — Contract sync (15 min).** Freeze the API shapes; Person 2 writes the mock files.
3. **21:00 — Gate 1, the spine.** The 1918 article loads from MariaDB with its ghosts in place, the slider moves through time and play runs the time-lapse, in English. If this slips, everything after it shrinks.
4. **01:00 — Gate 2, the MVP.** Hunt, certificate, ghost search and the biography text work on real data. Merge to `main`.
5. **04:00 — Gate 3, live.** Coordination score with evidence, the headline number, tombstones and QR, deployed on Modal at a public URL.
6. **04:00–07:00 — Story.** Real numbers into the deck, print the death certificates, record the 2-minute video, README and partner notes.
7. **07:00–09:00 — Rehearse three times, warm up the servers, submit.**

Sleep in two-hour shifts after 01:00, one person at a time; never leave a gate without an owner awake.

## Pitch and video

One story, one article, start to finish: we follow the war of 1918 and never present a feature list. The current [pitch deck](https://claude.ai/artifact/HPABWxCoQPhYSdZosVwW3m) gets rebuilt around this story at 04:00 with real data.

| Time | Beat | On screen |
| --- | --- | --- |
| 0:00 | A grandmother called it the *freedom war*; today it's the *civil war*. Wikipedia shows one name, no sign it changed. | Three names, two fading into ghosts |
| 0:20 | "The Wayback Machine shows old snapshots. We show what was erased." | Title |
| 0:30 | Press play: 20 years of the article; ghosts rise as the name changes | Live app, time-lapse |
| 0:55 | "This article has N ghosts." Catch the naming ghost; its certificate, in English | Live app, hunt + certificate |
| 1:30 | One removal scores high; the evidence chips say why, in one sentence | Live app, certificate |
| 1:55 | Gemini tells the article's story | Live app, biography mode |
| 2:20 | Zoom out: one number across all 19,742 articles; the one query; dataset sizes and speed | Slide |
| 2:35 | For historians, students, journalists; works on any contested topic | Slide |
| 2:50 | "Wikipedia shows you the survivors. We show you the ghosts." QR: catch your own ghost | Slide + QR |

**2-minute video:** the same story, mostly screen recording: hook (0:00–0:12), Wayback line (0:12–0:20), time-lapse (0:20–0:42), hunt + certificate (0:42–1:22), coordination (1:22–1:42), one query + numbers (1:42–1:54), close + URL (1:54–2:00). Record the voiceover separately, add captions, cut every loading pause.

**Hand out** printed death certificates of the hero ghosts during the pitch; let a judge type their own claim if time allows.

## Partners and submission

Each partner gets one clear job that the demo visibly depends on.

| Partner | Its job in the product | Prize | Submit |
| --- | --- | --- | --- |
| MariaDB (main challenge) | System versioning holds every sentence's life; VECTOR finds ghosts by meaning; one query does both | €1,000 + UpCloud credits + certifications, feature on mariadb.org | Features used + numbers in the README |
| Gemini | Makes history readable for anyone: the narrated biography and all translations | €4,000 + $1,000 Google Cloud credits per member / €2,000 / €1,000 | Why Gemini matters: accessible, interactive storytelling |
| Gemma | EmbeddingGemma reads every sentence in bulk, as an open model on Modal | €1,000 each to 3 teams | What the open model does at scale, and why open |
| Modal | Hosts the live app; runs the embedding and scale jobs | $2,000 + $3,000 credits | The live URL |
| Codex | Used to scaffold and review code | $10,000 / $5,000 / $2,500 API credits | Screenshots + a short log |
| Hostinger (only if two main challenges are allowed) | A public coordination-score API on their servers | €2,000 / €1,000 | Live URL on Hostinger |
| Nemotron (only if an agent loop is really used) | Investigates suspicious removals with tool calls | 2× RTX 5080 | Model, job, why, how outputs improved |

**Before 09:00**

- [ ] Junction platform: project, repo link, video, every challenge ticked
- [ ] README: one-command run, MariaDB features, the coordination algorithm, planted-ring results, dataset credit (CC BY-SA 4.0, Wikipedia)
- [ ] Live URL works on a phone; QR tested
- [ ] Gemini and Gemma explanations written
- [ ] Codex screenshots in `docs/codex/`
- [ ] Printed certificates ready

## Wikipedia only remembers 24 years

The MariaDB rep's concern: 1918 is over a century old, but Finnish Wikipedia's history only starts in 2002, so the names his grandmother used never appear in our data. We turn that limit into the point, and add one feature that separates the two kinds of time.

1. **Say exactly what we show.** We don't claim to show what Finns believed in 1950. We show what Wikipedia erased between 2002 and today. That matters because Wikipedia is now where most people, and every AI model, learn history. Pitch line: "Wikipedia is only 24 years old, but it's where the next hundred years will learn history." The timeline is labelled "Wikipedia's memory: 2002 → today".
2. **Event time vs edit time (MariaDB, both kinds of period).** Each sentence gets the years it talks about, pulled from the years it mentions ("1918", "1939–1940"), next to when Wikipedia said it. Event time lives in a `sentence_event` table with an application-time `PERIOD FOR event_time`; edit time is the system versioning we already have. That answers "what did Wikipedia say about 1918, as of 2010?" in one query, and gives a picture of which past Wikipedia keeps rewriting: event year across, edit year down. Every ghost card shows a tag like "talks about 1918".
3. **Show the old argument arriving.** The article's first versions (2002–2006) are the bridge: if early editors wrote the older names and later editors changed them, the century-old debate is replayed inside the edit history. Person 1 checks this first in article 1150; if it isn't there, we don't claim it.
4. **Optional, only after P2: the century before Wikipedia.** The National Library's digitised newspapers ([digi.kansalliskirjasto.fi](https://digi.kansalliskirjasto.fi)) show search hits per year, freely mainly up to 1939. Hand-count hits for *vapaussota*, *kansalaissota* and *sisällissota* per year and draw them before Wikipedia's own line. Label it hand-collected and OCR-based.

```sql
CREATE TABLE sentence_event (
  hash       BINARY(20) PRIMARY KEY,
  event_from DATE NOT NULL,          -- first year the sentence mentions
  event_to   DATE NOT NULL,          -- last year it mentions, + 1 year
  PERIOD FOR event_time (event_from, event_to)
);
-- What Wikipedia said about 1918, as of 2010
SELECT s.text_en
FROM sentence_life FOR SYSTEM_TIME AS OF TIMESTAMP '2010-01-01' AS l
JOIN sentence_event e USING (hash) JOIN sentence s USING (hash)
WHERE l.page_id = 1150 AND e.event_from <= '1918-12-31' AND e.event_to > '1918-01-01';
```

## Risks and open questions

The biggest risk is the sentence pipeline: messy wikitext makes noisy ghosts. Get article 1150 clean by 21:00 before scaling anything.

| Risk | Fallback |
| --- | --- |
| Wikitext stripping leaves junk (templates, refs, tables) | Tune on article 1150 only; hide ghosts under 30 characters or with markup left in them |
| Too many trivial ghosts (typos, reformatting) | The `typo` class hides them; the hunt shows only `erased` and `rewritten` |
| The 1918 naming change isn't visible in the data | Pick the hero sentence from the article with the most erased sentences (Talvisota, Mannerheim) |
| No real coordinated removals in Finnish history | Say so on stage; show the score on one clearly labelled planted ring and the honest numbers |
| Vector index not used in the joined query | Search `sentence_vec` first (top 200), then join, as in the key query |
| Scale run on all 19,742 articles doesn't finish | Show timings for what finished; the MVP works on the 51 hero articles |
| Live demo breaks or Modal cold-starts | Pre-warm, keep min containers at 1; fallback slides and the recorded video |

**Open questions**

- [ ] Can one project enter two main challenges (MariaDB + Hostinger)? Ask the info desk.
- [ ] Is the live Wikipedia API allowed (needed only for stretch goals)?
- [ ] Where does MariaDB run for the live demo: a small cloud server, or a Modal container with a Volume? Decide by 18:00.
- [ ] May we tell the historian rep's grandmother story on stage?
