"""
retrieval/reranker.py

Optional cross-encoder reranking for hybrid retrieval results.

Behavior:
- If sentence-transformers and torch are available, use a Hugging Face
  CrossEncoder model for reranking query/resume pairs.
- Otherwise, fall back to a deterministic heuristic reranker so the
  retrieval pipeline remains executable in constrained environments.
"""

from __future__ import annotations

import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()


CROSS_ENCODER_MODEL = os.getenv(
    "CROSS_ENCODER_MODEL",
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
)
RERANK_TEXT_CHARS = int(os.getenv("RERANK_TEXT_CHARS", "2200"))

_cross_encoder: Any = None
_cross_encoder_error: str | None = None


def _normalize_text(text: str, max_chars: int = RERANK_TEXT_CHARS) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) > max_chars:
        return cleaned[:max_chars] + "..."
    return cleaned


def _tokenize_query(query: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9\+\#\.]+", query.lower())
    stopwords = {
        "the", "and", "with", "for", "who", "that", "have", "has", "will",
        "from", "into", "role", "need", "looking", "someone", "experience",
        "skills", "skill", "candidate", "developer", "engineer",
    }
    return [token for token in tokens if len(token) > 1 and token not in stopwords]


def _load_cross_encoder():
    """Loads the cross-encoder lazily if optional dependencies exist."""
    global _cross_encoder, _cross_encoder_error

    if _cross_encoder is not None or _cross_encoder_error is not None:
        return _cross_encoder

    try:
        from sentence_transformers import CrossEncoder  # type: ignore

        _cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL)
        return _cross_encoder
    except Exception as exc:  # pragma: no cover - env dependent
        _cross_encoder_error = str(exc)
        return None


def reranker_backend() -> str:
    """Returns the active reranking backend."""
    return "cross_encoder" if _load_cross_encoder() is not None else "heuristic"


def _heuristic_score(query: str, candidate: dict) -> float:
    """
    Lightweight fallback scoring when a cross-encoder model is unavailable.
    Combines lexical overlap, metadata alignment, and pre-retrieval RRF score.
    """
    text = _normalize_text(candidate.get("rerank_text", candidate.get("text", ""))).lower()
    tokens = _tokenize_query(query)
    if not tokens:
        return float(candidate.get("rrf_score", 0.0))

    overlap = sum(1 for token in tokens if token in text)
    overlap_score = overlap / max(len(tokens), 1)

    category = str(candidate.get("category", "")).lower()
    industry_tags = [tag.lower() for tag in candidate.get("industry_tags", [])]
    metadata_bonus = 0.0
    for token in tokens:
        if token in category or token in industry_tags:
            metadata_bonus += 0.03

    base_score = float(candidate.get("rrf_score", 0.0))
    return round((0.70 * overlap_score) + (0.20 * base_score) + metadata_bonus, 6)


def rerank_candidates(query: str, candidates: list[dict]) -> list[dict]:
    """Reranks retrieved candidates using cross-encoder or a fallback heuristic."""
    if not candidates:
        return []

    model = _load_cross_encoder()
    reranked = [candidate.copy() for candidate in candidates]

    if model is not None:  # pragma: no cover - env dependent
        pairs = [
            [query, _normalize_text(candidate.get("rerank_text", candidate.get("text", "")))]
            for candidate in reranked
        ]
        scores = model.predict(pairs)
        for candidate, score in zip(reranked, scores):
            candidate["rerank_score"] = round(float(score), 6)
            candidate["rerank_backend"] = "cross_encoder"
    else:
        for candidate in reranked:
            candidate["rerank_score"] = _heuristic_score(query, candidate)
            candidate["rerank_backend"] = "heuristic"

    reranked.sort(key=lambda item: -item.get("rerank_score", 0.0))
    return reranked
