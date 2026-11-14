# Running Ghosts of Wikipedia

Three ways in, from 2 minutes to the full thing. Commands are PowerShell (Windows); Mac/Linux
differences are noted. Run everything from the repo root unless it says `cd web`.

| | What you get | Needs |
| --- | --- | --- |
| **A. Quick look** (2 min) | The site with the Finnish Civil War demo data, plus the live *Same story, every language* page | Node 20+ |
| **B. Full app** (20–30 min) | Any of the 19,742 articles, title search, real ghosts, certificates, time slider | Node, Python 3.11+, MariaDB 12.3 |
| **C. AI extras** | Meaning search, English translations, biographies, coordination scores | B + keys in `.env` |

---

## A. Quick look: frontend only, no database

```powershell
cd web
npm install
$env:VITE_USE_MOCK="1"; npm run dev        # Mac/Linux: VITE_USE_MOCK=1 npm run dev
```

Open http://localhost:5173. It uses the JSON in `mock/` (the Finnish Civil War article, page 1150).
**Same story, every language** still works for real, because your browser reads Wikipedia directly.
It just can't save snapshots without the API.

---

## B. Full app with real data

### 1. MariaDB 12.3 (port 3306, database/user/password all `ghosts`)

**Option 1: Docker** (easiest if you have it)
```powershell
docker compose up -d --wait
```

**Option 2: native install.** Install MariaDB 12.3 from https://mariadb.org/download (Windows MSI, port 3306;
Mac: `brew install mariadb`, then check `mariadb --version` says 11.7 or newer). Open HeidiSQL or
`mariadb -u root -p` and run:
```sql
CREATE DATABASE ghosts CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'ghosts'@'localhost' IDENTIFIED BY 'ghosts';
GRANT ALL PRIVILEGES ON ghosts.* TO 'ghosts'@'localhost';
FLUSH PRIVILEGES;
```

### 2. Python packages and settings

```powershell
copy .env.example .env                                  # Mac/Linux: cp .env.example .env
python -m pip install --user -r requirements.txt        # Mac/Linux: python3 -m pip install -r requirements.txt
```
Use `python -m pip` and `python -m uvicorn` rather than `pip` and `uvicorn`. On locked-down Windows
laptops the `.exe` launchers are often blocked or not on PATH.

### 3. Load the data (once)

```powershell
python pipeline/download.py        # dataset M: 16 Parquet files, 315 MB, checked against SHA256
python pipeline/revisions.py       # 862,076 revisions -> revision + article tables (~30 s)
```
That's all you need. **Articles are processed the first time someone opens them**, which takes
seconds to a minute for big ones, and then they're instant. To have the demo articles ready up front:
```powershell
python pipeline/lives.py --heroes --workers 4     # the 50 articles of MariaDB's demo (Civil War = 1150)
python pipeline/moves.py                          # sentences that moved to another article
python pipeline/stats.py                          # half-life numbers on the home page
```

**Shortcut: copy Adarsh's database instead of processing articles yourself.** He exports it with
```powershell
& "C:\Program Files\MariaDB 12.3\bin\mariadb-dump.exe" -u ghosts -pghosts --dump-history --result-file=ghosts.sql ghosts
```
(`--dump-history` matters: without it every ghost is lost, because ghosts are history rows.)
You import it with
```powershell
cmd /c "mariadb -u ghosts -pghosts ghosts < ghosts.sql"
```
You still want `download.py` so articles nobody has opened yet can load.

### 4. Start it (two terminals)

```powershell
# terminal 1: API, http://localhost:8000/docs lists every endpoint
python -m uvicorn api.main:app --reload --port 8000

# terminal 2: website, http://localhost:5173 (sends /api to port 8000)
cd web
npm install
npm run dev
```

**If port 8000 is "forbidden" (WinError 10013):** an old API is still running. Stop it:
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*uvicorn*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```
If that doesn't help, Windows has reserved the port: use `--port 8787` and change `8000` to `8787` in `web/vite.config.ts`.

---

## C. AI extras (keys go in `.env`, which is never committed)

| Feature | Setting in `.env` | Then run |
| --- | --- | --- |
| English translations (Gemma 4) | `FEATHERLESS_API_KEY=` | `python ai/translate.py --db --page 1150` |
| Biography / "life story" (Gemma) | `FEATHERLESS_API_KEY=` | `python ai/biography.py --page 1150` |
| Meaning search (EmbeddingGemma on Modal) | `EMBED_URL=` (ask Person 3) | `python -m modal run ai/embed_modal.py --db --page 1150` |
| Coordination score | — | `python ai/coordination.py --db` |
| English on *Same story, every language* | `FEATHERLESS_API_KEY=` | nothing: it happens on the page |

Without keys everything else still works: English mode falls back to Finnish, and meaning search
says it isn't switched on.

---

## What to try (2-minute tour)

1. **Home → "What did Wikipedia forget? Finnish Civil War."** Dashed boxes are deleted sentences ("ghosts").
   Click one for its death certificate: when it was born, who removed it and why, what it came back as.
   "Make a tombstone" gives you a shareable tombstone.
2. **Press Play** on the time bar to watch the article change from 2003 to 2026. Ghosts appear as
   they die. The **life story** panel above the text jumps the timeline to each turning point.
3. **Search** an article title, e.g. `sisällissota`. Articles marked "not summoned yet" get processed
   when you open them.
4. **Other languages** (button on any article, or the home page link): what each Wikipedia calls the
   topic, every rename and whether it was undone, locks and revert rates. Try *Russian invasion of
   Ukraine*. The Swedish card for the Civil War shows the 2008 naming fight (4 renames in 9 hours).

## Where things live

| | |
| --- | --- |
| `db/schema.sql` | every table (system-versioned `sentence_life`, `lang_compare`; `VECTOR` index) |
| `pipeline/` | download, revisions, sentence lives (`lives.py`), moves, stats |
| `api/main.py` | FastAPI: articles, ghosts, timeline, search, biography, stats |
| `api/languages.py` | *Same story, every language*: saving to MariaDB, Gemma meanings, history |
| `web/src/` | React frontend (`pages/`, `components/`, `lib/api.ts`, `lib/wikilang.ts`) |
| `ai/` | translation, biography, embeddings, coordination |
