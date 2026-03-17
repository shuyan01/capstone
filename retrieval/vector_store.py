"""
retrieval/vector_store.py

Responsible for:
- Connecting to the existing ChromaDB collection
- Embedding a recruiter's job query using OpenAI
- Searching for semantically similar resume chunks
- Supporting optional metadata filters (category, source, section)
- Returning a deduplicated list of top matching candidates

Usage:
    from retrieval.vector_store import semantic_search
    results = semantic_search("python backend engineer with FastAPI experience")
"""

import os
from dotenv import load_dotenv

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

load_dotenv()


# ─────────────────────────────────────────
# Config  (reads from .env)
# ─────────────────────────────────────────

OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL",        "text-embedding-3-small")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR",     "./chroma_db")
COLLECTION_NAME    = os.getenv("CHROMA_COLLECTION_NAME", "resumes")
TOP_K_RETRIEVAL    = int(os.getenv("TOP_K_RETRIEVAL",    "20"))


# ─────────────────────────────────────────
# ChromaDB Collection (reuse from embedder)
# ─────────────────────────────────────────

def get_collection():
    """
    Loads the existing ChromaDB collection from disk.
    Raises an error if the collection does not exist yet
    (i.e. embedder.py has not been run).
    """
    embedding_fn = OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY,
        model_name=EMBEDDING_MODEL,
    )

    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    if collection.count() == 0:
        raise RuntimeError(
            "ChromaDB collection is empty. "
            "Please run 'python ingestion/embedder.py' first to ingest resumes."
        )

    return collection


# ─────────────────────────────────────────
# Semantic Search
# ─────────────────────────────────────────

def semantic_search(
    query: str,
    top_k: int = TOP_K_RETRIEVAL,
    filter_category: str = None,
    filter_source: str = None,
) -> list[dict]:
    """
    Searches ChromaDB for resume chunks that are semantically
    similar to the given job query.

    Args:
        query:           Natural language job description or query
        top_k:           Number of chunks to retrieve
        filter_category: Optional — filter by job category
                         e.g. "DATA SCIENCE", "ENGINEERING"
        filter_source:   Optional — filter by source
                         "csv" or "pdf"

    Returns:
        List of result dicts, each containing:
        {
            "chunk_id":  "resume_csv_0042_chunk_03",
            "resume_id": "resume_csv_0042",
            "category":  "DATA SCIENCE",
            "source":    "csv",
            "section":   "skills",
            "text":      "chunk text...",
            "score":     0.87          # cosine similarity (higher = better)
        }
    """
    collection = get_collection()

    # ── Build optional metadata filter ─────
    # ChromaDB filter syntax uses $and / $eq operators
    where_filter = None

    if filter_category and filter_source:
        where_filter = {
            "$and": [
                {"category": {"$eq": filter_category.upper()}},
                {"source":   {"$eq": filter_source}},
            ]
        }
    elif filter_category:
        where_filter = {"category": {"$eq": filter_category.upper()}}
    elif filter_source:
        where_filter = {"source": {"$eq": filter_source}}

    # ── Run the query ───────────────────────
    query_params = {
        "query_texts": [query],
        "n_results":   top_k,
        "include":     ["documents", "metadatas", "distances"],
    }
    if where_filter:
        query_params["where"] = where_filter

    raw = collection.query(**query_params)

    # ── Parse results ───────────────────────
    results = []

    documents = raw["documents"][0]   # list of chunk texts
    metadatas = raw["metadatas"][0]   # list of metadata dicts
    distances = raw["distances"][0]   # cosine distances (lower = more similar)
    ids       = raw["ids"][0]         # chunk IDs

    for chunk_id, doc, meta, dist in zip(ids, documents, metadatas, distances):
        # Convert distance to similarity score (0 to 1, higher = better)
        score = round(1 - dist, 4)

        results.append({
            "chunk_id":  chunk_id,
            "resume_id": meta.get("resume_id", ""),
            "category":  meta.get("category",  ""),
            "source":    meta.get("source",    ""),
            "section":   meta.get("section",   ""),
            "education_tags": [t.strip() for t in meta.get("education_tags", "").split(",") if t.strip()],
            "location_tags": [t.strip() for t in meta.get("location_tags", "").split(",") if t.strip()],
            "industry_tags": [t.strip() for t in meta.get("industry_tags", "").split(",") if t.strip()],
            "job_titles": [t.strip() for t in meta.get("job_titles", "").split(",") if t.strip()],
            "degree_subjects": [t.strip() for t in meta.get("degree_subjects", "").split(",") if t.strip()],
            "education_level": meta.get("education_level", "").strip(),
            "explicit_years": int(meta.get("explicit_years", 0) or 0),
            "text":      doc,
            "score":     score,
        })

    return results


# ─────────────────────────────────────────
# Deduplicate by resume_id
# ─────────────────────────────────────────

def deduplicate_by_resume(chunks: list[dict]) -> list[dict]:
    """
    Multiple chunks from the same resume may be returned.
    This function keeps only the highest-scoring chunk per resume,
    returning one result per unique candidate.

    Args:
        chunks: Raw list of chunk results from semantic_search()

    Returns:
        Deduplicated list — one entry per unique resume_id,
        sorted by score descending
    """
    best_per_resume = {}

    for chunk in chunks:
        rid   = chunk["resume_id"]
        score = chunk["score"]

        if rid not in best_per_resume or score > best_per_resume[rid]["score"]:
            best_per_resume[rid] = chunk

    # Sort by score descending
    deduped = sorted(best_per_resume.values(), key=lambda x: -x["score"])
    return deduped


# ─────────────────────────────────────────
# Quick Test
# Run: python retrieval/vector_store.py
# ─────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    test_query = "python backend engineer with FastAPI and PostgreSQL experience"

    print(f"Query: '{test_query}'")
    print(f"{'='*60}")

    # ── Raw chunk results ───────────────────
    raw_results = semantic_search(test_query, top_k=10)
    print(f"\nRaw results (top 10 chunks):")
    for i, r in enumerate(raw_results):
        print(f"  {i+1}. [{r['score']:.3f}] {r['resume_id']} | "
              f"{r['category']} | {r['section']}")
        print(f"      {r['text'][:100]}...")

    # ── Deduplicated results ────────────────
    deduped = deduplicate_by_resume(raw_results)
    print(f"\nDeduplicated candidates ({len(deduped)} unique resumes):")
    for i, r in enumerate(deduped):
        print(f"  {i+1}. [{r['score']:.3f}] {r['resume_id']} | "
              f"{r['category']} | section: {r['section']}")
