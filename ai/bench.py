"""bench.py - why is translation slow? Times the same 8-sentence request on two Gemma models.

Run from the ghosts-ai folder:   python bench.py
"""
import json
import time
from pathlib import Path

import requests

from translate import API_KEY, API_URL, SYSTEM

MODELS = ["google/gemma-4-31B-it", "google/gemma-4-26B-A4B-it"]

lines = [l.strip() for l in Path("sentences_fi.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
payload = json.dumps([{"i": i, "fi": fi} for i, fi in enumerate(lines)], ensure_ascii=False)

for model in MODELS:
    print(f"\n=== {model} ===")
    for run in (1, 2):  # second run shows the speed once the model is loaded
        t0 = time.time()
        r = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"model": model, "temperature": 0, "max_tokens": 4000,
                  "messages": [{"role": "system", "content": SYSTEM},
                               {"role": "user", "content": payload}]},
            timeout=300,
        )
        secs = time.time() - t0
        if r.status_code != 200:
            print(f"run {run}: HTTP {r.status_code} after {secs:.0f}s: {r.text[:200]}")
            continue
        body = r.json()
        msg = body["choices"][0]["message"]
        print(f"run {run}: {secs:.0f}s  usage={body.get('usage')}")
        print(f"        message fields: {sorted(msg.keys())}")
        print(f"        reply starts: {(msg.get('content') or '')[:120]!r}")
