"""ai/embed_modal.py - EmbeddingGemma on a Modal GPU.

Turns sentences into 768-number vectors so ghosts can be searched by meaning.

  Test on the sample file (no database needed):
      modal run embed_modal.py --file sentences_fi.txt

  Fill sentence_vec in MariaDB (needs DB_URL in the repo .env and `pip install pymysql`):
      modal run embed_modal.py --db --page 1150     # one article first
      modal run embed_modal.py --db                 # every sentence not embedded yet

  Put the search endpoint online for Person 1's API:
      modal deploy embed_modal.py
    It prints a URL. POST {"q": "some claim"} to it and it returns {"embedding": [...768 numbers...]}.

Needs the Modal secret created earlier:  modal secret create huggingface HF_TOKEN=hf_...
"""
import json
import math
import os
from pathlib import Path

import modal

MODEL_ID = "google/embeddinggemma-300m"
# GPUs need a payment method or credits on the Modal account. Until then this runs on CPU,
# which is fine for this small model. Change to "T4" once the account allows GPUs.
GPU = None
DIM = 768
CHUNK = 256  # sentences sent to the GPU per call

app = modal.App("ghosts-embed")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", index_url="https://download.pytorch.org/whl/cpu" if GPU is None else None)
    .pip_install("sentence-transformers>=5.1.0", "fastapi[standard]")
)
# The model is downloaded once into this volume, then reused on every start.
cache = modal.Volume.from_name("ghosts-hf-cache", create_if_missing=True)


@app.cls(
    image=image,
    gpu=GPU,
    cpu=4.0,
    secrets=[modal.Secret.from_name("huggingface")],
    volumes={"/cache": cache},
    scaledown_window=300,   # stay warm 5 minutes after the last call
    timeout=900,
    # min_containers=1,     # switch on before the demo so search never cold-starts
)
class Embedder:
    @modal.enter()
    def load(self):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(MODEL_ID, cache_folder="/cache")

    @modal.method()
    def documents(self, texts: list) -> list:
        """Embed sentences that will be searched (the Finnish sentences)."""
        vecs = self.model.encode_document(texts, batch_size=64, normalize_embeddings=True)
        return vecs.tolist()

    @modal.method()
    def query(self, text: str) -> list:
        """Embed what a user typed into the search box."""
        return self.model.encode_query(text, normalize_embeddings=True).tolist()

    @modal.fastapi_endpoint(method="POST")
    def search_vector(self, body: dict):
        """Web endpoint for the API: {"q": "..."} -> {"embedding": [...], "dim": 768}."""
        q = str(body.get("q", "")).strip()
        if not q:
            return {"error": "send JSON like {\"q\": \"your search text\"}"}
        vec = self.model.encode_query(q, normalize_embeddings=True).tolist()
        return {"embedding": vec, "dim": len(vec)}


def embed_all(texts: list) -> list:
    """Send texts to the GPU in chunks; returns one vector per text, same order."""
    embedder = Embedder()
    out = []
    for i in range(0, len(texts), CHUNK):
        out.extend(embedder.documents.remote(texts[i:i + CHUNK]))
        print(f"  embedded {min(i + CHUNK, len(texts))}/{len(texts)}")
    return out


def run_file(path: str) -> None:
    lines = [l.strip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    vecs = embed_all(lines)
    print(f"{len(vecs)} vectors, {len(vecs[0])} numbers each (expected {DIM})")

    # Small demo of ghost search: an English question against Finnish sentences.
    question = "what did people use to call the war of 1918?"
    qv = Embedder().query.remote(question)
    scored = sorted(((sum(a * b for a, b in zip(qv, v)), s) for v, s in zip(vecs, lines)), reverse=True)
    print(f"\nSearch test: {question!r}")
    for score, sentence in scored[:3]:
        print(f"  {score:.2f}  {sentence}")
    norm = math.sqrt(sum(x * x for x in vecs[0]))
    print(f"\n(vector length {norm:.2f}; 1.00 means cosine distance works as expected)")


def run_db(page: int) -> None:
    # Person 1's shared connection: reads DB_URL from the repo's .env; works with pymysql alone.
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
    from common import connect

    conn, cur = connect()
    if page:
        cur.execute(
            "SELECT DISTINCT s.hash, s.text_fi FROM sentence s "
            "JOIN sentence_life FOR SYSTEM_TIME ALL AS l ON l.hash = s.hash "
            "LEFT JOIN sentence_vec v ON v.hash = s.hash "
            "WHERE l.page_id = ? AND v.hash IS NULL", (page,))
    else:
        cur.execute(
            "SELECT s.hash, s.text_fi FROM sentence s "
            "LEFT JOIN sentence_vec v ON v.hash = s.hash WHERE v.hash IS NULL")
    rows = cur.fetchall()
    print(f"{len(rows)} sentences to embed")
    embedder = Embedder()
    for i in range(0, len(rows), CHUNK):
        part = rows[i:i + CHUNK]
        vecs = embedder.documents.remote([fi for _, fi in part])
        cur.executemany(
            "INSERT IGNORE INTO sentence_vec (hash, emb) VALUES (?, VEC_FromText(?))",
            [(bytes(h), json.dumps(v)) for (h, _), v in zip(part, vecs)])
        conn.commit()  # saved chunk by chunk, so a crash loses nothing
        print(f"  stored {min(i + CHUNK, len(rows))}/{len(rows)}")
    conn.close()
    print("sentence_vec updated")


@app.local_entrypoint()
def main(file: str = "", db: bool = False, page: int = 0):
    if db:
        run_db(page)
    elif file:
        run_file(file)
    else:
        print("Use --file sentences_fi.txt  or  --db [--page 1150]")
