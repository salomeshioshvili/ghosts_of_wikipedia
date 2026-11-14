# ai/
Person 3.

- `embed.py`: EmbeddingGemma on Modal. Must expose `embed_query(text) -> list[float]` (768 floats) for /api/search, and fill `sentence_vec`.
- `translate.py`: Gemini, fills `sentence.text_en` (cache, never twice).
- `biography.py`: Gemini, writes `data/biography/<page_id>.json` in the API contract shape.
- `coordination.py`: fills the `coordination` table (score 0-100 + evidence JSON).
