"""
api/main.py

FastAPI application entry point.

To run the API server:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

Then open:
    http://localhost:8000/docs   -- Swagger UI (interactive API docs)
    http://localhost:8000/redoc  -- ReDoc API docs
"""

import os
import pickle
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from api.routes import router, set_chunks
from analytics.feedback_store     import initialize_feedback_store
from ingestion.parser           import load_all_resumes
from ingestion.chunker          import chunk_all_resumes
from retrieval.keyword_search   import get_or_build_bm25_index

load_dotenv()


# -----------------------------------------
# Chunks disk cache  (avoids re-parsing on every startup / --reload)
# -----------------------------------------

_CSV_PATH        = Path("data/raw/Resume.csv")
_PDF_FOLDER      = Path("data/raw/pdfs")
_CHUNKS_CACHE    = Path("data/processed/chunks_cache.pkl")


def _source_fingerprint() -> str:
    """A lightweight fingerprint of source data — mtime of CSV + PDF count."""
    csv_mtime  = f"{_CSV_PATH.stat().st_mtime:.0f}"  if _CSV_PATH.exists()    else "0"
    pdf_count  = str(len(list(_PDF_FOLDER.rglob("*.pdf")))) if _PDF_FOLDER.exists() else "0"
    return f"{csv_mtime}-{pdf_count}"


def _load_chunks_cache() -> list[dict] | None:
    if not _CHUNKS_CACHE.exists():
        return None
    try:
        with open(_CHUNKS_CACHE, "rb") as f:
            data = pickle.load(f)
        if data.get("fingerprint") != _source_fingerprint():
            print("[Startup] Source data changed — cache invalidated.")
            return None
        print(f"[Startup] Loaded {len(data['chunks']):,} chunks from cache (skipping re-parse).")
        return data["chunks"]
    except Exception as exc:
        print(f"[Startup] Cache load failed ({exc}) — will re-parse.")
        return None


def _save_chunks_cache(chunks: list[dict]) -> None:
    _CHUNKS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(_CHUNKS_CACHE, "wb") as f:
        pickle.dump({"fingerprint": _source_fingerprint(), "chunks": chunks}, f)
    print(f"[Startup] Chunks cache saved → {_CHUNKS_CACHE}")


# -----------------------------------------
# Startup: preload all data once
# so every request can use it immediately
# -----------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once when the API server starts.
    Loads and caches:
    - All resume chunks  (from disk cache when possible)
    - BM25 index (from disk or freshly built)

    This avoids reloading data on every request or --reload restart.
    """
    print("\n[Startup] Loading resumes and BM25 index...")
    initialize_feedback_store()

    chunks = _load_chunks_cache()
    if chunks is None:
        resumes = load_all_resumes(
            csv_path   = "data/raw/Resume.csv",
            pdf_folder = "data/raw/pdfs",
        )
        chunks = chunk_all_resumes(resumes)
        _save_chunks_cache(chunks)

    # Build or load BM25 index from disk
    get_or_build_bm25_index(chunks)

    # Pass chunks to routes so hybrid_search can use them
    set_chunks(chunks)

    print(f"[Startup] Ready — {len(chunks):,} chunks loaded.\n")

    yield  # API is now running and serving requests

    # Cleanup on shutdown (nothing needed here)
    print("\n[Shutdown] API shutting down.")


# -----------------------------------------
# App Setup
# -----------------------------------------

app = FastAPI(
    title="AI Resume Intelligence & Candidate Matching System",
    description=(
        "An AI-powered system that matches job descriptions to candidate resumes "
        "using hybrid retrieval (semantic + BM25) and a multi-agent evaluation pipeline.\n\n"
        "## How it works\n"
        "1. Submit a natural language job description to **POST /match**\n"
        "2. The system retrieves top candidates using hybrid search\n"
        "3. Four specialist agents evaluate each candidate\n"
        "4. Returns ranked candidates with explainable composite scores\n\n"
        "## Agents\n"
        "- **Skill Matching Agent** — evaluates skill coverage (gpt-4o-mini)\n"
        "- **Experience Agent** — evaluates career progression (gpt-4o-mini)\n"
        "- **Technical Agent** — evaluates technical depth (gpt-4o-mini)\n"
        "- **Culture Fit Agent** — evaluates soft skills as LLM-judge (gpt-4o)\n"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# -----------------------------------------
# CORS Middleware
# -----------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------
# Include Routes
# -----------------------------------------

app.include_router(router, prefix="")


# -----------------------------------------
# Root endpoint
# -----------------------------------------

@app.get("/", include_in_schema=False)
def root():
    return {
        "message": "AI Resume Matching System API",
        "docs":    "http://localhost:8000/docs",
        "health":  "http://localhost:8000/health",
    }
