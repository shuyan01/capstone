"""
agents/orchestrator.py

Responsible for:
- Defining the LangGraph multi-agent evaluation graph
- Fetching full resume text for each candidate (all chunks combined)
- Running all four agents in parallel for each candidate
- Collecting all agent scores into a unified state
- Passing results to the scoring aggregator

Token Optimization:
- MAX_RESUME_TEXT_CHARS caps resume text sent to agents (reduces token usage)
- Required skills extracted ONCE and reused across all candidates
- Culture fit agent (gpt-4o) only receives summary text, not full resume

Graph structure:
    START
      |
      v
  [retrieve_candidates]     -- hybrid search
      |
      v
  [parse_candidates]        -- Resume Parsing Agent (heuristic; section detection + bias flags)
      |
      v
  [enrich_candidates]       -- fetch full resume text from all chunks
      |
      v
  [summarize_candidates]    -- GPT-4o-mini structured summary (with disk cache)
      |
      v
  [evaluate_candidates]     -- runs all 4 specialist agents per candidate
      |
      v
  [aggregate_scores]        -- weighted composite score
      |
      v
    END
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import TypedDict
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END

from retrieval.hybrid_retriever       import hybrid_search
from agents.resume_parsing_agent      import run_resume_parsing_agent
from ingestion.summarizer             import batch_summarize
from agents.skill_matching_agent      import run_skill_matching_agent
from agents.experience_agent          import run_experience_agent
from agents.technical_agent           import run_technical_agent
from agents.culture_fit_agent         import run_culture_fit_agent
from scoring.aggregator               import aggregate_candidate_scores

load_dotenv()

# ── LangSmith tracing ───────────────────────────────
# Supports both the legacy LANGCHAIN_TRACING_V2 env var and the newer
# LANGSMITH_TRACING var so that either .env naming convention works.
# LangGraph traces every node automatically: real token counts,
# per-node latency, and full run history appear in the LangSmith dashboard.
_tracing_on = (
    os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    or os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
)
if _tracing_on:
    # langsmith SDK reads LANGSMITH_API_KEY or LANGCHAIN_API_KEY
    if os.getenv("LANGSMITH_API_KEY") and not os.getenv("LANGCHAIN_API_KEY"):
        os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    _project = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT", "ai-resume-matching")
    os.environ["LANGCHAIN_PROJECT"] = _project
    print(f"[LangSmith] Tracing enabled — project: '{_project}'")


# -----------------------------------------
# Config
# -----------------------------------------

TOP_K_FINAL = int(os.getenv("TOP_K_FINAL", "5"))

# Token optimization — cap how much text each agent sees
# Skills/Experience/Technical agents: need full context
MAX_RESUME_TEXT_CHARS = int(os.getenv("MAX_RESUME_TEXT_CHARS", "3000"))

# Culture fit agent uses gpt-4o (expensive) — give it less text
# It only needs to assess soft skills, not technical details
MAX_CULTURE_TEXT_CHARS = int(os.getenv("MAX_CULTURE_TEXT_CHARS", "1500"))


# -----------------------------------------
# Graph State
# -----------------------------------------

class PipelineState(TypedDict):
    job_query:          str
    top_k:              int
    filter_category:    str | None
    advanced_filters:   dict | None
    include_gating_failures: bool
    candidates:         list[dict]
    skill_results:      list[dict]
    experience_results: list[dict]
    technical_results:  list[dict]
    culture_results:    list[dict]
    final_rankings:     list[dict]


# -----------------------------------------
# Helper: build full resume text from chunks
# -----------------------------------------

def build_full_resume_texts(
    candidates:  list[dict],
    all_chunks:  list[dict],
    max_chars:   int = MAX_RESUME_TEXT_CHARS,
) -> list[dict]:
    """
    For each candidate, find ALL chunks belonging to that resume_id,
    concatenate them, and truncate to max_chars.

    Token optimization: max_chars limits how much text goes to each agent.
    """
    # Group all chunks by resume_id for O(1) lookup
    chunks_by_resume: dict[str, list[str]] = {}
    for chunk in all_chunks:
        rid = chunk["resume_id"]
        if rid not in chunks_by_resume:
            chunks_by_resume[rid] = []
        chunks_by_resume[rid].append(chunk["text"])

    enriched = []
    for candidate in candidates:
        rid       = candidate["resume_id"]
        all_texts = chunks_by_resume.get(rid, [candidate["text"]])
        full_text = " ".join(all_texts)

        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + "..."

        enriched.append({**candidate, "text": full_text})

    return enriched


def build_culture_fit_texts(candidates: list[dict]) -> list[dict]:
    """
    For culture fit agent (gpt-4o), use shorter text to reduce cost.
    Extracts only the summary/soft-skill relevant portions.

    Token optimization: gpt-4o costs ~10x more than gpt-4o-mini,
    so we give it less text to reduce cost while preserving quality.
    """
    trimmed = []
    for candidate in candidates:
        text = candidate["text"]
        if len(text) > MAX_CULTURE_TEXT_CHARS:
            text = text[:MAX_CULTURE_TEXT_CHARS] + "..."
        trimmed.append({**candidate, "text": text})
    return trimmed


# -----------------------------------------
# Node 2: Parse Candidates (Resume Parsing Agent)
# -----------------------------------------

def parse_candidates(state: PipelineState) -> PipelineState:
    """
    Resume Parsing Agent — heuristic structural extraction.
    Detects resume sections, estimates structural richness,
    and flags demographic bias markers for recruiter awareness.
    No LLM call — zero token cost.
    """
    print(f"\n[Orchestrator] Step 2/5 — Resume Parsing Agent (heuristic)...")

    candidates = state["candidates"]
    if not candidates:
        return state

    parsed = run_resume_parsing_agent(candidates)

    sections_total = sum(len(c.get("parsed_sections", [])) for c in parsed)
    bias_flagged   = sum(1 for c in parsed if c.get("bias_flags"))
    print(f"  Parsed {len(parsed)} resumes — "
          f"{sections_total} total sections detected, "
          f"{bias_flagged} with demographic marker(s)")

    return {**state, "candidates": parsed}


# -----------------------------------------
# Node 4: Summarize Candidates
# -----------------------------------------

def summarize_candidates(state: PipelineState) -> PipelineState:
    """
    Condenses each candidate's full resume text into a structured,
    information-dense summary via GPT-4o-mini.

    Benefits over naive truncation:
    - Preserves ALL key signals (skills, roles, certs, projects)
      regardless of where they appear in the original document.
    - Structured format (SKILLS / EXPERIENCE / EDUCATION / …)
      makes downstream agents more reliable.
    - Persistent disk cache: LLM called only once per unique resume;
      every subsequent query is served instantly at zero LLM cost.
    """
    print(f"\n[Orchestrator] Step 4/6 — Summarizing resumes (GPT-4o-mini + disk cache)...")
    candidates = state["candidates"]
    if not candidates:
        return state

    summarized = batch_summarize(candidates)
    return {**state, "candidates": summarized}


# -----------------------------------------
# Node 5: Evaluate Candidates
# -----------------------------------------

def evaluate_candidates(state: PipelineState) -> PipelineState:
    """
    Runs all four specialist agents on every retrieved candidate.

    Token optimization:
    - Skills/Experience/Technical use full text (MAX_RESUME_TEXT_CHARS)
    - Culture fit uses shorter text (MAX_CULTURE_TEXT_CHARS) to reduce gpt-4o cost
    - Required skills extracted ONCE by skill agent, reused across all candidates
    """
    print(f"\n[Orchestrator] Step 5/6 — Running agent evaluations...")
    print(f"  Token budget: {MAX_RESUME_TEXT_CHARS} chars/candidate (technical agents), "
          f"{MAX_CULTURE_TEXT_CHARS} chars/candidate (culture agent)")

    job_query  = state["job_query"]
    candidates = state["candidates"]

    if not candidates:
        print("  No candidates to evaluate.")
        return {
            **state,
            "skill_results":      [],
            "experience_results": [],
            "technical_results":  [],
            "culture_results":    [],
        }

    # ── Agent 1: Skill Matching ─────────────────────────────
    print(f"\n  [1/4] Skill Matching Agent (gpt-4o-mini)...")
    skill_results = run_skill_matching_agent(job_query, candidates)

    # ── Agent 2: Experience Evaluation ──────────────────────
    print(f"\n  [2/4] Experience Agent (gpt-4o-mini)...")
    experience_results = run_experience_agent(job_query, candidates)

    # ── Agent 3: Technical Depth ─────────────────────────────
    print(f"\n  [3/4] Technical Agent (gpt-4o-mini)...")
    technical_results = run_technical_agent(job_query, candidates)

    # ── Agent 4: Culture Fit — uses shorter text to save tokens ──
    print(f"\n  [4/4] Culture Fit Agent (gpt-4o, trimmed text)...")
    culture_candidates = build_culture_fit_texts(candidates)
    culture_results    = run_culture_fit_agent(job_query, culture_candidates)

    return {
        **state,
        "skill_results":      skill_results,
        "experience_results": experience_results,
        "technical_results":  technical_results,
        "culture_results":    culture_results,
    }


# -----------------------------------------
# Node 6: Aggregate Scores
# -----------------------------------------

def aggregate_scores(state: PipelineState) -> PipelineState:
    """Combines all four agent scores into a weighted composite score."""
    print(f"\n[Orchestrator] Step 6/6 — Aggregating scores...")

    final_rankings = aggregate_candidate_scores(
        candidates=state["candidates"],
        skill_results=state["skill_results"],
        experience_results=state["experience_results"],
        technical_results=state["technical_results"],
        culture_results=state["culture_results"],
        job_query=state["job_query"],
        include_gating_failures=state.get("include_gating_failures", False),
    )

    return {**state, "final_rankings": final_rankings}


# -----------------------------------------
# Node 5 is aggregate_scores — already named
# Build the LangGraph
# -----------------------------------------

def build_graph(chunks: list[dict] | None = None) -> StateGraph:
    """Constructs and compiles the LangGraph evaluation pipeline.

    chunks is captured in closures for retrieve/enrich nodes so it never
    enters the graph state — this keeps LangSmith trace payloads small.
    """
    _chunks = chunks or []

    def _retrieve_candidates(state: PipelineState) -> PipelineState:
        """Runs hybrid search to retrieve top-k candidate resumes."""
        print(f"\n[Orchestrator] Step 1/5 — Retrieving candidates...")
        print(f"  Query: '{state['job_query']}'")
        candidates = hybrid_search(
            query=state["job_query"],
            top_k=state.get("top_k", TOP_K_FINAL),
            filter_category=state.get("filter_category"),
            advanced_filters=state.get("advanced_filters"),
            chunks=_chunks,
        )
        print(f"  Retrieved {len(candidates)} candidates.")
        return {**state, "candidates": candidates}

    def _enrich_candidates(state: PipelineState) -> PipelineState:
        """Replaces each candidate's single chunk text with full resume text."""
        print(f"\n[Orchestrator] Step 3/5 — Enriching candidates with full resume text...")
        if not _chunks:
            print("  No chunks available — agents will use single chunk text.")
            return state
        enriched = build_full_resume_texts(
            state["candidates"],
            _chunks,
            max_chars=MAX_RESUME_TEXT_CHARS,
        )
        total_chars = sum(len(c["text"]) for c in enriched)
        print(f"  Enriched {len(enriched)} candidates "
              f"(total chars: {total_chars:,}, "
              f"avg: {total_chars // max(len(enriched), 1):,})")
        return {**state, "candidates": enriched}

    graph = StateGraph(PipelineState)

    graph.add_node("retrieve_candidates",  _retrieve_candidates)
    graph.add_node("parse_candidates",     parse_candidates)
    graph.add_node("enrich_candidates",    _enrich_candidates)
    graph.add_node("summarize_candidates", summarize_candidates)
    graph.add_node("evaluate_candidates",  evaluate_candidates)
    graph.add_node("aggregate_scores",     aggregate_scores)

    graph.add_edge(START,                   "retrieve_candidates")
    graph.add_edge("retrieve_candidates",   "parse_candidates")
    graph.add_edge("parse_candidates",      "enrich_candidates")
    graph.add_edge("enrich_candidates",     "summarize_candidates")
    graph.add_edge("summarize_candidates",  "evaluate_candidates")
    graph.add_edge("evaluate_candidates",   "aggregate_scores")
    graph.add_edge("aggregate_scores",      END)

    return graph.compile()


# -----------------------------------------
# Main Entry Point
# -----------------------------------------

def run_pipeline(
    job_query:       str,
    top_k:           int = TOP_K_FINAL,
    filter_category: str = None,
    advanced_filters: dict | None = None,
    chunks:          list[dict] = None,
    include_gating_failures: bool = False,
) -> list[dict]:
    """
    Runs the full multi-agent evaluation pipeline for a given job query.

    Token optimization summary:
    - Technical agents (gpt-4o-mini): up to 3000 chars per candidate
    - Culture agent (gpt-4o):         up to 1500 chars per candidate
    - Skills extracted once, reused across all candidates
    - Estimated tokens per request (5 candidates):
        ~25,000 input tokens + ~2,500 output tokens

    Args:
        job_query:       Natural language job description from recruiter
        top_k:           Number of final ranked candidates to return
        filter_category: Optional job category filter
        chunks:          Pre-loaded chunks (avoids reloading on repeated calls)

    Returns:
        List of ranked candidate dicts with composite scores and explanations
    """
    pipeline = build_graph(chunks or [])

    initial_state: PipelineState = {
        "job_query":          job_query,
        "top_k":              top_k,
        "filter_category":    filter_category,
        "advanced_filters":   advanced_filters or {},
        "include_gating_failures": include_gating_failures,
        "candidates":         [],
        "skill_results":      [],
        "experience_results": [],
        "technical_results":  [],
        "culture_results":    [],
        "final_rankings":     [],
    }

    print(f"\n{'='*60}")
    print(f"Pipeline started")
    print(f"Query: '{job_query}'")
    print(f"{'='*60}")

    final_state    = pipeline.invoke(initial_state)
    final_rankings = final_state["final_rankings"]

    print(f"\n{'='*60}")
    print(f"Pipeline complete — {len(final_rankings)} candidates ranked")
    print(f"{'='*60}\n")

    return final_rankings


# -----------------------------------------
# Quick Test
# Run: python agents/orchestrator.py
# -----------------------------------------

if __name__ == "__main__":
    from ingestion.parser  import load_all_resumes
    from ingestion.chunker import chunk_all_resumes

    print("Loading data...")
    resumes = load_all_resumes(
        csv_path   = "data/raw/Resume.csv",
        pdf_folder = "data/raw/pdfs",
    )
    chunks = chunk_all_resumes(resumes)

    job_query = "Java full stack developer with Spring Boot and MySQL"

    results = run_pipeline(
        job_query=job_query,
        top_k=3,
        chunks=chunks,
    )

    print("\n── Final Ranked Candidates ──")
    for i, r in enumerate(results):
        print(f"\nRank {i+1}: {r['resume_id']}")
        print(f"  Composite Score:  {r['composite_score']:.2f}")
        print(f"  Skill Score:      {r['skill_score']:.2f}")
        print(f"  Experience Score: {r['experience_score']:.2f}")
        print(f"  Technical Score:  {r['technical_score']:.2f}")
        print(f"  Culture Score:    {r['culture_score']:.2f}")
        print(f"  Explanation:      {r['explanation']}")
