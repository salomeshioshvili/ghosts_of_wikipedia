"""ai/translate.py - Finnish -> English with Gemma 4 on Featherless.

Two ways to run it:

  File mode (works now, no database needed):
      python translate.py --file sentences_fi.txt
    Reads one Finnish sentence per line, writes translations.json.

  Database mode (once Person 1 has filled the `sentence` table):
      python translate.py --db --page 1150      # one article first
      python translate.py --db                  # everything still untranslated
    Fills sentence.text_en where it is NULL.

Every translation is cached in translations_cache.json by sentence hash,
so nothing is ever translated twice, even across runs and modes.

"""
import argparse
import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.featherless.ai/v1/chat/completions"
API_KEY = os.environ.get("FEATHERLESS_API_KEY", "")
MODEL = os.environ.get("TRANSLATE_MODEL", "google/gemma-4-31B-it")
BATCH = 20          # sentences per request
WORKERS = int(os.environ.get("TRANSLATE_WORKERS", "2"))  # parallel requests; plan units / 2
CACHE_PATH = Path("translations_cache.json")

# The names of the 1918 war are the whole point of the demo: they must stay
# distinguishable in English, so each keeps its Finnish word in brackets.
SYSTEM = """You translate sentences from Finnish Wikipedia history articles into English.

Rules:
- Translate faithfully and neutrally. Do not add, drop, soften or explain anything.
- Keep names of people and places as they are.
- The names of the 1918 war must stay distinguishable. Always use exactly:
  sisällissota -> "Civil War (sisällissota)"
  vapaussota -> "War of Freedom (vapaussota)"
  kansalaissota -> "Citizens' War (kansalaissota)"
  luokkasota -> "Class War (luokkasota)"
  punakapina -> "Red Rebellion (punakapina)"
  veljessota -> "War of Brothers (veljessota)"
  vallankumous -> "Revolution (vallankumous)"
- If a sentence is a fragment or leftover markup, translate what is there.

You receive a JSON array of objects {"i": number, "fi": text}.
Reply with ONLY a JSON array of objects {"i": number, "en": text}, one per input, same numbers."""

_cache_lock = threading.Lock()


def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(CACHE_PATH)


def chat(messages: list, max_tokens: int = 4000) -> str:
    """One call to Featherless, retrying on rate limits and server errors."""
    for attempt in range(6):
        try:
            r = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={"model": MODEL, "messages": messages,
                      "temperature": 0, "max_tokens": max_tokens},
                timeout=180,
            )
        except requests.RequestException as e:
            print(f"  network error ({e}); retrying")
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        if r.status_code in (429, 500, 502, 503, 504):
            print(f"  HTTP {r.status_code}; waiting {2 ** attempt}s")
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    raise RuntimeError("Featherless kept failing after 6 attempts")


def parse_array(reply: str) -> list:
    """Pull the JSON array out of the reply, even if the model wrapped it in text."""
    start, end = reply.find("["), reply.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array in reply")
    return json.loads(reply[start:end + 1])


def translate_one(text_fi: str) -> str:
    reply = chat([{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": json.dumps([{"i": 0, "fi": text_fi}], ensure_ascii=False)}],
                 max_tokens=1000)
    try:
        return str(parse_array(reply)[0]["en"]).strip()
    except Exception:
        return reply.strip()


def translate_batch(items: list) -> dict:
    """items: [(hash, text_fi)] -> {hash: text_en}. Falls back to one-by-one if the batch reply is bad."""
    payload = [{"i": i, "fi": fi} for i, (_, fi) in enumerate(items)]
    try:
        reply = chat([{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
        rows = parse_array(reply)
        by_i = {int(row["i"]): str(row["en"]).strip() for row in rows}
        if set(by_i) != set(range(len(items))) or not all(by_i.values()):
            raise ValueError("reply does not cover every sentence")
        return {h: by_i[i] for i, (h, _) in enumerate(items)}
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        print(f"  batch reply unusable ({e}); translating these {len(items)} one by one")
        return {h: translate_one(fi) for h, fi in items}


def translate_all(items: list, on_batch=None) -> dict:
    """items: [(hash, text_fi)]. Returns {hash: text_en} for all of them, using the cache."""
    cache = load_cache()
    todo = [(h, fi) for h, fi in items if h not in cache]
    todo = list(dict(todo).items())  # drop duplicate hashes
    print(f"{len(items)} sentences, {len(items) - len(todo)} already cached, {len(todo)} to translate")
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    started, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(translate_batch, b) for b in batches]
        for fut in as_completed(futures):
            result = fut.result()
            with _cache_lock:
                cache.update(result)
                save_cache(cache)
            if on_batch:
                on_batch(result)
            done += len(result)
            rate = done / max(time.time() - started, 0.1)
            print(f"  {done}/{len(todo)}  ({rate:.1f} sentences/s)")
    return {h: cache[h] for h, _ in items if h in cache}


# ---------- file mode ----------

def run_file(path: str) -> None:
    lines = [re.sub(r"\s+", " ", l).strip() for l in Path(path).read_text(encoding="utf-8").splitlines()]
    lines = [l for l in lines if l]
    items = [(sha1_hex(l), l) for l in lines]
    out = translate_all(items)
    result = [{"hash": h, "text_fi": fi, "text_en": out.get(h)} for h, fi in items]
    Path("translations.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote translations.json")
    for row in result[:5]:
        print(f"\nFI: {row['text_fi']}\nEN: {row['text_en']}")


# ---------- database mode ----------

def connect():
    import mariadb  # only needed for --db
    u = urlparse(os.environ["DB_URL"])
    return mariadb.connect(host=u.hostname, port=u.port or 3306, user=u.username,
                           password=u.password or "", database=u.path.lstrip("/"))


def run_db(page_id) -> None:
    conn = connect()
    cur = conn.cursor()
    if page_id:
        cur.execute(
            "SELECT DISTINCT s.hash, s.text_fi FROM sentence s "
            "JOIN sentence_life FOR SYSTEM_TIME ALL AS l ON l.hash = s.hash "
            "WHERE l.page_id = ? AND s.text_en IS NULL", (page_id,))
    else:
        cur.execute("SELECT hash, text_fi FROM sentence WHERE text_en IS NULL")
    rows = [(bytes(h).hex(), fi) for h, fi in cur.fetchall()]
    write_lock = threading.Lock()

    def write(result: dict) -> None:
        with write_lock:
            cur.executemany("UPDATE sentence SET text_en = ? WHERE hash = ?",
                            [(en, bytes.fromhex(h)) for h, en in result.items()])
            conn.commit()

    cache = load_cache()
    cached = {h: cache[h] for h, _ in rows if h in cache}
    if cached:
        write(cached)  # translated in an earlier run or in file mode
    translate_all(rows, on_batch=write)
    conn.close()
    print("sentence.text_en updated")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="text file with one Finnish sentence per line")
    ap.add_argument("--db", action="store_true", help="fill sentence.text_en in MariaDB")
    ap.add_argument("--page", type=int, help="with --db: only this page_id (e.g. 1150)")
    args = ap.parse_args()
    if not API_KEY:
        raise SystemExit("FEATHERLESS_API_KEY is missing from .env")
    if args.db:
        run_db(args.page)
    elif args.file:
        run_file(args.file)
    else:
        ap.print_help()
