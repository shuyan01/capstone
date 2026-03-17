"""
retrieval/keyword_search.py

Responsible for:
- Building a BM25 index over all resume chunks
- Searching for resume chunks that contain exact keywords
- Complementing semantic search (catches exact skill/tool names)
- Returning ranked results in the same format as vector_store.py

Why BM25?
- Semantic search can miss exact terms like "FastAPI", "PostgreSQL", "React"
- BM25 is great at exact keyword matching
- Combining both gives better overall results (hybrid search)

Usage:
    from retrieval.keyword_search import build_bm25_index, keyword_search
    index = build_bm25_index(chunks)
    results = keyword_search("FastAPI PostgreSQL", index, chunks)
"""

import os
import pickle
from pathlib import Path

from rank_bm25 import BM25Okapi
from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────
# Config
# ─────────────────────────────────────────

TOP_K_RETRIEVAL = int(os.getenv("TOP_K_RETRIEVAL", "20"))

# Path to save/load the BM25 index on disk
# So we don't have to rebuild it every time
BM25_INDEX_PATH = "./chroma_db/bm25_index.pkl"


# ─────────────────────────────────────────
# Tokenizer
# ─────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """
    Simple whitespace + lowercase tokenizer for BM25.
    Splits text into individual words for keyword matching.

    Example:
        "FastAPI Python Developer" -> ["fastapi", "python", "developer"]
    """
    return text.lower().split()


# ─────────────────────────────────────────
# Build BM25 Index
# ─────────────────────────────────────────

def build_bm25_index(chunks: list[dict], save: bool = True) -> BM25Okapi:
    """
    Builds a BM25 index from all resume chunks.

    This only needs to be done once — the index is saved to disk
    and can be loaded quickly on subsequent runs.

    Args:
        chunks: List of chunk dicts from chunker.chunk_all_resumes()
        save:   If True, saves the index to BM25_INDEX_PATH

    Returns:
        A BM25Okapi index object
    """
    print(f"[BM25] Building index from {len(chunks)} chunks...")

    # Tokenize each chunk's text
    tokenized_corpus = [tokenize(chunk["text"]) for chunk in chunks]

    # Build the BM25 index
    bm25 = BM25Okapi(tokenized_corpus)

    # Save to disk for reuse
    if save:
        Path(BM25_INDEX_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(BM25_INDEX_PATH, "wb") as f:
            pickle.dump({"bm25": bm25, "chunks": chunks}, f)
        print(f"[BM25] Index saved to: {BM25_INDEX_PATH}")

    print(f"[BM25] Index built successfully.")
    return bm25


def load_bm25_index() -> tuple[BM25Okapi, list[dict]]:
    """
    Loads a previously saved BM25 index from disk.

    Returns:
        Tuple of (bm25_index, chunks_list)

    Raises:
        FileNotFoundError if the index hasn't been built yet
    """
    if not Path(BM25_INDEX_PATH).exists():
        raise FileNotFoundError(
            f"BM25 index not found at: {BM25_INDEX_PATH}\n"
            f"Please call build_bm25_index(chunks) first."
        )

    print(f"[BM25] Loading index from: {BM25_INDEX_PATH}")
    with open(BM25_INDEX_PATH, "rb") as f:
        data = pickle.load(f)

    print(f"[BM25] Index loaded — {len(data['chunks'])} chunks.")
    return data["bm25"], data["chunks"]


def get_or_build_bm25_index(chunks: list[dict]) -> tuple[BM25Okapi, list[dict]]:
    """
    Loads the BM25 index from disk if it exists,
    otherwise builds and saves it.

    This is the recommended function to call in your pipeline —
    it handles both first-run and subsequent runs automatically.

    Args:
        chunks: List of all chunks (used only if index needs to be built)

    Returns:
        Tuple of (bm25_index, chunks_list)
    """
    if Path(BM25_INDEX_PATH).exists():
        return load_bm25_index()
    else:
        bm25 = build_bm25_index(chunks, save=True)
        return bm25, chunks


# ─────────────────────────────────────────
# Keyword Search
# ─────────────────────────────────────────

def keyword_search(
    query: str,
    bm25: BM25Okapi,
    chunks: list[dict],
    top_k: int = TOP_K_RETRIEVAL,
    filter_category: str = None,
    filter_source: str = None,
) -> list[dict]:
    """
    Searches the BM25 index for chunks containing the query keywords.

    Args:
        query:           Natural language job query
        bm25:            BM25 index from build_bm25_index()
        chunks:          The same chunks list used to build the index
        top_k:           Number of results to return
        filter_category: Optional — filter by job category
        filter_source:   Optional — "csv" or "pdf"

    Returns:
        List of result dicts in the same format as vector_store.semantic_search():
        {
            "chunk_id":  "...",
            "resume_id": "...",
            "category":  "...",
            "source":    "...",
            "section":   "...",
            "text":      "...",
            "score":     0.75    # normalized BM25 score (0 to 1)
        }
    """
    # Tokenize query
    tokenized_query = tokenize(query)

    # Get BM25 scores for all chunks
    scores = bm25.get_scores(tokenized_query)

    # Apply optional filters by only scoring relevant chunks
    filtered_indices = []
    for i, chunk in enumerate(chunks):
        if filter_category and chunk["category"].upper() != filter_category.upper():
            continue
        if filter_source and chunk["source"] != filter_source:
            continue
        filtered_indices.append(i)

    # If no filter, use all indices
    if not filter_category and not filter_source:
        filtered_indices = list(range(len(chunks)))

    # Sort filtered indices by score descending
    sorted_indices = sorted(filtered_indices, key=lambda i: scores[i], reverse=True)
    top_indices = sorted_indices[:top_k]

    # Normalize scores to 0-1 range
    max_score = scores[top_indices[0]] if top_indices else 1.0
    if max_score == 0:
        max_score = 1.0  # avoid division by zero

    results = []
    for i in top_indices:
        chunk = chunks[i]
        normalized_score = round(float(scores[i]) / max_score, 4)

        results.append({
            "chunk_id":  chunk["chunk_id"],
            "resume_id": chunk["resume_id"],
            "category":  chunk["category"],
            "source":    chunk["source"],
            "section":   chunk["section"],
            "education_tags": chunk.get("education_tags", []),
            "location_tags": chunk.get("location_tags", []),
            "industry_tags": chunk.get("industry_tags", []),
            "job_titles": chunk.get("job_titles", []),
            "degree_subjects": chunk.get("degree_subjects", []),
            "education_level": chunk.get("education_level", ""),
            "explicit_years": int(chunk.get("explicit_years", 0)),
            "text":      chunk["text"],
            "score":     normalized_score,
        })

    return results


# ─────────────────────────────────────────
# Quick Test
# Run: python retrieval/keyword_search.py
# ─────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from ingestion.parser  import load_all_resumes
    from ingestion.chunker import chunk_all_resumes

    # Load and chunk all resumes
    print("Loading resumes...")
    resumes = load_all_resumes(
        csv_path   = "data/raw/Resume.csv",
        pdf_folder = "data/raw/pdfs",
    )
    chunks = chunk_all_resumes(resumes)

    # Build or load BM25 index
    bm25, chunks = get_or_build_bm25_index(chunks)

    # Test search
    test_query = "python backend engineer FastAPI PostgreSQL"
    print(f"\nQuery: '{test_query}'")
    print("=" * 60)

    results = keyword_search(test_query, bm25, chunks, top_k=10)

    print(f"Top 10 BM25 results:")
    for i, r in enumerate(results):
        print(f"  {i+1}. [{r['score']:.3f}] {r['resume_id']} | "
              f"{r['category']} | {r['section']}")
        print(f"      {r['text'][:100]}...")
