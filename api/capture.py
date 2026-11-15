"""Dev-only: save page captures for the demo video into data/captures/.

Accepts a JPEG/PNG body only from this machine itself (127.0.0.1 with no proxy headers), so it is
inert behind Caddy/Hostinger. Delete this file and its two lines in main.py after the video.
"""
import os
import re

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "captures")


@router.post("/api/_capture/{name}", include_in_schema=False)
async def capture(name: str, request: Request):
    local = request.client and request.client.host in ("127.0.0.1", "::1")
    proxied = any(h in request.headers for h in ("x-forwarded-for", "x-real-ip", "forwarded"))
    if not local or proxied:
        raise HTTPException(404)
    if not re.fullmatch(r"[a-z0-9_-]{1,40}\.(jpg|png)", name):
        raise HTTPException(400, "bad name")
    body = await request.body()
    if len(body) > 15_000_000:
        raise HTTPException(413)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "wb") as f:
        f.write(body)
    return {"saved": name, "bytes": len(body)}
