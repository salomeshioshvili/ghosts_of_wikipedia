"""ai/embed.py - what the API's /api/search imports: embed_query(text) -> 768 floats.

It calls the EmbeddingGemma endpoint that `modal deploy embed_modal.py` puts online,
so the API itself needs only `requests`, not Modal or the model.

.env (repo root):  EMBED_URL=https://<workspace>--ghosts-embed-embedder-search-vector.modal.run

Quick test:  python ai/embed.py "what was the war of 1918 called"
"""
import os
from functools import lru_cache
from pathlib import Path

import requests


def _load_env():
    """Read EMBED_URL from the repo-root .env if it isn't already set."""
    env = Path(__file__).resolve().parent.parent / ".env"
    if "EMBED_URL" not in os.environ and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("EMBED_URL="):
                os.environ["EMBED_URL"] = line.split("=", 1)[1].strip()


@lru_cache(maxsize=512)  # the same search twice costs nothing
def embed_query(text: str) -> list:
    _load_env()
    url = os.environ.get("EMBED_URL")
    if not url:
        raise RuntimeError("EMBED_URL is missing from .env (run `modal deploy ai/embed_modal.py` to get it)")
    # Generous timeout: the first call after a quiet period starts the container.
    r = requests.post(url, json={"q": text}, timeout=120)
    r.raise_for_status()
    body = r.json()
    if "embedding" not in body:
        raise RuntimeError(f"embedding endpoint said: {body}")
    return body["embedding"]


if __name__ == "__main__":
    import sys

    vec = embed_query(" ".join(sys.argv[1:]) or "freedom war")
    print(f"{len(vec)} numbers, first three: {vec[:3]}")
