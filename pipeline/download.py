"""Download dataset M (History of Finland, every version): 16 Parquet files, 315 MB.

    python pipeline/download.py

From https://github.com/MariaDB/mariadb-wikipedia-datasets/releases/tag/m-2026-10
Safe to run again: finished files are kept and checked against SHA256SUMS.
"""
import hashlib, os, sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_M

RELEASE = "https://github.com/MariaDB/mariadb-wikipedia-datasets/releases/download/m-2026-10"
os.makedirs(DATA_M, exist_ok=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


sums = {}
r = requests.get(f"{RELEASE}/SHA256SUMS", timeout=60)
r.raise_for_status()
for line in r.text.splitlines():
    if line.strip():
        digest, name = line.split(maxsplit=1)
        sums[name.strip().lstrip("*")] = digest

wanted = sorted(n for n in sums if n.endswith(".parquet"))
print(f"{len(wanted)} files to fetch", flush=True)
for name in wanted:
    path = os.path.join(DATA_M, name)
    if os.path.exists(path) and sha256(path) == sums[name]:
        print(f"  {name}: already here", flush=True)
        continue
    with requests.get(f"{RELEASE}/{name}", stream=True, timeout=60) as resp:
        resp.raise_for_status()
        with open(path + ".part", "wb") as f:
            for chunk in resp.iter_content(1 << 20):
                f.write(chunk)
    os.replace(path + ".part", path)
    ok = sha256(path) == sums[name]
    print(f"  {name}: {'ok' if ok else 'CHECKSUM MISMATCH - delete it and run again'}", flush=True)
print("Done:", DATA_M)
