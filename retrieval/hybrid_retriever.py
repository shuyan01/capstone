"""
retrieval/hybrid_retriever.py

Responsible for:
- Query expansion using LLM (Direction A)
- Auto category inference when not specified (Direction C)
- Combining semantic search (ChromaDB) and keyword search (BM25)
- Using Reciprocal Rank Fusion (RRF) to merge and re-rank results
- Deduplicating candidates (removes CSV/PDF duplicates of same resume)
- Returning a clean, ranked list of unique candidates

Improvements:
  A. Query expansion   — LLM expands query with related keywords
  B. Larger top_k      — retrieves more candidates before filtering
  C. Category inference — auto-detects category from query
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from retrieval.advanced_filters import (
    filter_candidates,
    group_resume_metadata,
    group_resume_texts,
    has_active_advanced_filters,
)
from retrieval.vector_store   import semantic_search
from retrieval.keyword_search import keyword_search, get_or_build_bm25_index
from retrieval.reranker       import rerank_candidates, reranker_backend
from ingestion.parser         import load_all_resumes
from ingestion.chunker        import chunk_all_resumes

load_dotenv()


# -----------------------------------------
# Config  (reads from .env)
# -----------------------------------------

TOP_K_RETRIEVAL = int(os.getenv("TOP_K_RETRIEVAL",    "20"))
TOP_K_FINAL     = int(os.getenv("TOP_K_FINAL",        "5"))
VECTOR_WEIGHT   = float(os.getenv("VECTOR_SEARCH_WEIGHT", "0.6"))
BM25_WEIGHT     = float(os.getenv("BM25_SEARCH_WEIGHT",   "0.4"))
RRF_K           = 60
FORCE_BM25_ONLY = os.getenv("FORCE_BM25_ONLY", "false").strip().lower() == "true"

QUERY_MODEL = os.getenv("QUERY_MODEL", "gpt-4o-mini")

AVAILABLE_CATEGORIES = [
    "INFORMATION-TECHNOLOGY", "ENGINEERING", "BUSINESS-DEVELOPMENT",
    "FINANCE", "HEALTHCARE", "CONSULTANT", "BANKING", "HR", "DESIGNER",
    "SALES", "ADVOCATE", "CHEF", "FITNESS", "AVIATION", "CONSTRUCTION",
    "PUBLIC-RELATIONS", "TEACHER", "APPAREL", "DIGITAL-MEDIA",
    "AGRICULTURE", "AUTOMOBILE", "ARTS", "ACCOUNTANT", "BPO",
]


# -----------------------------------------
# Shared LLM (gpt-4o-mini, used for both
# query expansion and category inference)
# -----------------------------------------

_llm = ChatOpenAI(
    model=QUERY_MODEL,
    temperature=0,
    max_tokens=200,
)


# -----------------------------------------
# Direction A — Query Expansion
# -----------------------------------------

QUERY_EXPANSION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a recruiting assistant.
Expand the given job query into a richer set of keywords for resume search.
Return ONLY a single line of space-separated keywords. No explanation, no bullets, no JSON.
Include: job titles, technologies, skills, tools, synonyms, and related terms."""),
    ("human", "Job query: {query}")
])


def expand_query(query: str) -> str:
    """
    Uses gpt-4o-mini to expand the query with related keywords.
    Falls back to original query if expansion fails.

    Example:
        Input:  "Python ML engineer"
        Output: "Python machine learning engineer scikit-learn TensorFlow
                 PyTorch data science model training neural network NLP
                 deep learning AI artificial intelligence"
    """
    try:
        chain    = QUERY_EXPANSION_PROMPT | _llm
        response = chain.invoke({"query": query})
        expanded = response.content.strip()
        print(f"[QueryExpansion] Original: '{query}'")
        print(f"[QueryExpansion] Expanded: '{expanded[:120]}...'")
        return expanded
    except Exception as e:
        print(f"[QueryExpansion] Failed, using original: {e}")
        return query


# -----------------------------------------
# Direction C — Category Inference
# -----------------------------------------

CATEGORY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a recruiting assistant.
Given a job query, return the single most relevant job category from this list:
{categories}

Return ONLY the category name exactly as written above. Nothing else."""),
    ("human", "Job query: {query}")
])


def infer_category(query: str) -> str | None:
    """
    Uses gpt-4o-mini to infer the most relevant job category from the query.
    Returns None if inference fails or result is not in the known category list.
    """
    try:
        chain    = CATEGORY_PROMPT | _llm
        response = chain.invoke({
            "query":      query,
            "categories": ", ".join(AVAILABLE_CATEGORIES),
        })
        category = response.content.strip().upper()

        if category in AVAILABLE_CATEGORIES:
            print(f"[CategoryInference] Inferred: '{category}'")
            return category
        else:
            print(f"[CategoryInference] Could not match '{category}' — searching all categories")
            return None
    except Exception as e:
        print(f"[CategoryInference] Failed: {e}")
        return None


# -----------------------------------------
# BM25 Index — loaded once at module level
# -----------------------------------------

_bm25_index  = None
_bm25_chunks = None


def _get_bm25(chunks: list[dict] = None):
    """
    Lazy-loads the BM25 index.
    On first call, builds or loads the index from disk.
    On subsequent calls, returns the cached index.
    """
    global _bm25_index, _bm25_chunks

    if _bm25_index is None:
        if chunks is None:
            raise ValueError(
                "BM25 index not loaded yet. "
                "Pass chunks on first call to initialise."
            )
        _bm25_index, _bm25_chunks = get_or_build_bm25_index(chunks)

    return _bm25_index, _bm25_chunks


# -----------------------------------------
# Reciprocal Rank Fusion (RRF)
# -----------------------------------------

def reciprocal_rank_fusion(
    result_lists: list[list[dict]],
    weights: list[float],
    k: int = RRF_K,
) -> list[dict]:
    """
    Merges multiple ranked result lists into one using RRF.

    Formula: RRF_score = sum(weight * 1 / (k + rank)) across all lists
    """
    rrf_scores = {}
    result_map = {}

    for result_list, weight in zip(result_lists, weights):
        for rank, result in enumerate(result_list):
            rid          = result["resume_id"]
            contribution = weight * (1.0 / (k + rank + 1))

            if rid in rrf_scores:
                rrf_scores[rid] += contribution
            else:
                rrf_scores[rid] = contribution
                result_map[rid] = result

    sorted_ids = sorted(rrf_scores.keys(), key=lambda rid: -rrf_scores[rid])

    merged = []
    for rid in sorted_ids:
        result             = result_map[rid].copy()
        result["rrf_score"] = round(rrf_scores[rid], 6)
        merged.append(result)

    return merged


# -----------------------------------------
# Deduplication (removes CSV/PDF duplicates)
# -----------------------------------------

def deduplicate_cross_source(results: list[dict]) -> list[dict]:
    """
    Removes duplicate candidates that appear as both CSV and PDF versions.

    resume_csv_0042 and resume_pdf_0042 are the same person.
    Keeps whichever has the higher RRF score.
    """
    seen_indices = {}

    for result in results:
        rid   = result["resume_id"]
        parts = rid.split("_")
        index = parts[-1] if parts else rid

        if index not in seen_indices:
            seen_indices[index] = result
        else:
            existing_score = seen_indices[index].get("rrf_score", 0)
            new_score      = result.get("rrf_score", 0)
            if new_score > existing_score:
                seen_indices[index] = result

    deduped = sorted(seen_indices.values(), key=lambda x: -x.get("rrf_score", 0))
    return deduped


def attach_resume_context(candidates: list[dict], chunks: list[dict] | None) -> list[dict]:
    """
    Attaches full resume text and merged metadata for reranking and downstream filters.
    """
    if not chunks:
        return candidates

    resume_texts = group_resume_texts(chunks)
    resume_metadata = group_resume_metadata(chunks)
    enriched = []

    for candidate in candidates:
        resume_id = candidate.get("resume_id", "")
        merged = candidate.copy()
        if resume_id in resume_texts:
            merged["rerank_text"] = resume_texts[resume_id]
        if resume_id in resume_metadata:
            merged.update(resume_metadata[resume_id])
        enriched.append(merged)

    return enriched


def normalize_single_source_results(
    results: list[dict],
    score_field: str = "score",
) -> list[dict]:
    """Converts a single retrieval source into the common downstream shape."""
    normalized = []
    for result in results:
        merged = result.copy()
        merged["rrf_score"] = round(float(result.get(score_field, 0.0)), 6)
        normalized.append(merged)
    return normalized


# -----------------------------------------
# Main Hybrid Search Function
# -----------------------------------------

def hybrid_search(
    query: str,
    top_k: int = TOP_K_FINAL,
    filter_category: str = None,
    advanced_filters: dict | None = None,
    chunks: list[dict] = None,
) -> list[dict]:
    """
    Main entry point for candidate retrieval.

    Improvements applied:
    - Direction A: query expanded with LLM before searching
    - Direction B: retrieves top_k * 6 (min 50) candidates before filtering
    - Direction C: auto-infers category from query if not provided

    Args:
        query:           Natural language job description
        top_k:           Number of final candidates to return
        filter_category: Optional job category filter (overrides auto-inference)
        chunks:          Required on first call to build BM25 index

    Returns:
        List of up to top_k candidate dicts with rrf_score
    """

    # Direction B — larger retrieval pool for better coverage
    retrieval_k = max(top_k * 6, 50)

    # Direction A — expand query with related keywords
    expanded_query = expand_query(query)

    # Direction C — auto-infer category if not provided by user
    effective_category = filter_category
    if not effective_category:
        effective_category = infer_category(query)

    # ── BM25 keyword search (uses expanded query) ────
    print(f"[Hybrid] Running BM25 keyword search...")
    bm25, bm25_chunks = _get_bm25(chunks)
    bm25_results = keyword_search(
        query=expanded_query,
        bm25=bm25,
        chunks=bm25_chunks,
        top_k=retrieval_k,
        filter_category=effective_category,
    )

    semantic_results: list[dict] = []
    semantic_available = False

    if FORCE_BM25_ONLY:
        print("[Hybrid] FORCE_BM25_ONLY enabled — skipping semantic search.")
    else:
        print(f"[Hybrid] Running semantic search (top_k={retrieval_k}, "
              f"category={effective_category or 'all'})...")
        try:
            semantic_results = semantic_search(
                query=expanded_query,
                top_k=retrieval_k,
                filter_category=effective_category,
            )
            semantic_available = True
        except Exception as exc:
            print(f"[Hybrid] Semantic search unavailable, falling back to BM25-only mode: {exc}")

    # ── Reciprocal Rank Fusion / fallback ─────────────
    if semantic_available and semantic_results:
        print(f"[Hybrid] Merging with RRF "
              f"(vector={VECTOR_WEIGHT}, bm25={BM25_WEIGHT})...")
        merged = reciprocal_rank_fusion(
            result_lists=[semantic_results, bm25_results],
            weights=[VECTOR_WEIGHT, BM25_WEIGHT],
        )
    else:
        print("[Hybrid] Using BM25-only retrieval results.")
        merged = normalize_single_source_results(bm25_results)

    # ── Deduplicate CSV/PDF copies ────────────────────
    print(f"[Hybrid] Deduplicating candidates...")
    deduped = deduplicate_cross_source(merged)

    print(f"[Hybrid] Preparing candidates for reranking...")
    deduped = attach_resume_context(deduped, chunks)

    print(f"[Hybrid] Reranking candidates using {reranker_backend()} backend...")
    deduped = rerank_candidates(query, deduped)

    if has_active_advanced_filters(advanced_filters):
        print(f"[Hybrid] Applying advanced recruiter filters...")
        before_count = len(deduped)
        deduped = filter_candidates(deduped, advanced_filters, chunks)
        print(f"[Hybrid] Advanced filters kept {len(deduped)}/{before_count} candidates.")

    # ── Return top_k final candidates ─────────────────
    final = deduped[:top_k]
    print(f"[Hybrid] Done — returning {len(final)} candidates.\n")
    return final


# -----------------------------------------
# Quick Test
# Run: python retrieval/hybrid_retriever.py
# -----------------------------------------

if __name__ == "__main__":
    from ingestion.parser  import load_all_resumes
    from ingestion.chunker import chunk_all_resumes

    print("Loading resumes and building BM25 index...")
    resumes = load_all_resumes(
        csv_path   = "data/raw/Resume.csv",
        pdf_folder = "data/raw/pdfs",
    )
    chunks = chunk_all_resumes(resumes)

    test_queries = [
        "Python backend engineer with FastAPI and PostgreSQL experience",
        "Data scientist with machine learning and deep learning skills",
        "Java full stack developer with Spring Boot and MySQL",
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: '{query}'")
        print(f"{'='*60}")

        candidates = hybrid_search(
            query=query,
            top_k=5,
            chunks=chunks,
        )

        for i, c in enumerate(candidates):
            print(f"\n  Rank {i+1}: {c['resume_id']}")
            print(f"  Category:  {c['category']}")
            print(f"  RRF Score: {c['rrf_score']}")
            print(f"  Preview:   {c['text'][:120]}...")
