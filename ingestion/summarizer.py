"""
ingestion/summarizer.py

Resume Summarizer — condenses long resumes into structured, information-dense
summaries using GPT-4o-mini, with persistent disk caching.

Why:
  Raw resume text routinely exceeds the MAX_RESUME_TEXT_CHARS budget.
  Naive truncation drops everything past the cutoff — losing certifications,
  projects, and skills listed at the bottom.  A targeted GPT-4o-mini summary
  compresses the full resume to ≤ MAX_RESUME_TEXT_CHARS while preserving ALL
  key signals that downstream specialist agents need.

Caching strategy:
  - Cache file: data/processed/resume_summaries_cache.pkl
  - Cache key:  f"{resume_id}:{md5(text)[:8]}"
    • Same resume → instant cache hit (0 LLM cost)
    • Resume text changes → new fingerprint → fresh summary
  - On first run, all candidates are summarized in parallel threads.
  - Cost estimate: ~$0.0003 per new resume (GPT-4o-mini pricing).
    For 2 500 resumes: ≈ $0.75 one-time.
    Per query after that: $0 (all cache hits).

Integration point:
  Called from orchestrator.py as the "summarize_candidates" node,
  which runs AFTER enrich_candidates (full text assembled) and
  BEFORE evaluate_candidates (agents consume the text).

Environment variables:
  SUMMARY_CACHE_PATH   Path to the pickle cache            (default: data/processed/resume_summaries_cache.pkl)
  MAX_RESUME_TEXT_CHARS  Target char budget after summary   (default: 3000, shared with orchestrator)
  SUMMARIZER_WORKERS   Parallel thread count               (default: 4)
  SUMMARIZER_ENABLED   Set to "false" to disable (falls back to truncation)
"""

import os
import pickle
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


# -----------------------------------------
# Config
# -----------------------------------------

SUMMARY_CACHE_PATH   = os.getenv("SUMMARY_CACHE_PATH",    "data/processed/resume_summaries_cache.pkl")
MAX_SUMMARY_CHARS    = int(os.getenv("MAX_RESUME_TEXT_CHARS", "3000"))
SUMMARIZER_WORKERS   = int(os.getenv("SUMMARIZER_WORKERS", "4"))
SUMMARIZER_ENABLED   = os.getenv("SUMMARIZER_ENABLED", "true").lower() != "false"

# Safety cap on how much raw text we send to GPT-4o-mini for summarization.
# ~8 000 chars ≈ 2 000 tokens — well within the model's context window.
_MAX_INPUT_CHARS = 8_000

# -----------------------------------------
# OpenAI client (lazy singleton)
# -----------------------------------------

_client: OpenAI | None = None
_client_lock = threading.Lock()


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


# -----------------------------------------
# Disk cache helpers
# -----------------------------------------

_cache_lock = threading.Lock()


def _load_cache() -> dict:
    if os.path.exists(SUMMARY_CACHE_PATH):
        with open(SUMMARY_CACHE_PATH, "rb") as f:
            return pickle.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(SUMMARY_CACHE_PATH), exist_ok=True)
    with open(SUMMARY_CACHE_PATH, "wb") as f:
        pickle.dump(cache, f)


def _fingerprint(text: str) -> str:
    """Short MD5 of text — used to detect if the source resume changed."""
    return hashlib.md5(text.encode()).hexdigest()[:8]


# -----------------------------------------
# Summarization prompt
# -----------------------------------------

_SYSTEM_PROMPT = (
    "You are a professional resume analyst. "
    "Extract and condense key information from the resume below into a structured, "
    "information-dense summary. Be concise but do NOT omit important technical "
    "skills, job titles, companies, or measurable achievements."
)

_USER_PROMPT_TEMPLATE = """\
Summarize the resume below in at most {max_chars} characters.

Use this exact format (skip sections that are absent):
SUMMARY: <1–2 sentence career overview>
SKILLS: <comma-separated list of technical skills, tools, languages, frameworks>
EXPERIENCE: <Title @ Company (years) — key responsibilities/achievements; repeat for each role>
EDUCATION: <Degree, Institution, Year>
CERTIFICATIONS: <list>
PROJECTS: <project name — brief description; repeat>
ACHIEVEMENTS: <quantified accomplishments>

RESUME:
{text}

STRUCTURED SUMMARY:"""


# -----------------------------------------
# Core summarization function
# -----------------------------------------

def _summarize_one(resume_id: str, full_text: str, cache: dict) -> tuple[str, str]:
    """
    Summarizes a single resume.  Returns (resume_id, summary_text).
    Reads from cache if available; otherwise calls GPT-4o-mini and updates cache.
    Thread-safe.
    """
    key = f"{resume_id}:{_fingerprint(full_text)}"

    # Check cache under lock (cheap)
    with _cache_lock:
        if key in cache:
            return resume_id, cache[key]

    # If already short enough, no LLM needed
    if len(full_text) <= MAX_SUMMARY_CHARS:
        with _cache_lock:
            cache[key] = full_text
        return resume_id, full_text

    # Call GPT-4o-mini
    prompt_text = full_text[:_MAX_INPUT_CHARS]
    try:
        response = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": _USER_PROMPT_TEMPLATE.format(
                    max_chars=MAX_SUMMARY_CHARS,
                    text=prompt_text,
                )},
            ],
            max_tokens=700,
            temperature=0.0,
        )
        summary = response.choices[0].message.content.strip()
    except Exception as exc:
        print(f"  [Summarizer] Warning: GPT-4o-mini failed for {resume_id}: {exc}")
        # Graceful fallback — truncate so the pipeline never stalls
        summary = full_text[:MAX_SUMMARY_CHARS] + "..."

    with _cache_lock:
        cache[key] = summary

    return resume_id, summary


# -----------------------------------------
# Batch summarize (public API)
# -----------------------------------------

def batch_summarize(candidates: list[dict]) -> list[dict]:
    """
    Summarizes the 'text' field of each candidate using GPT-4o-mini.

    - Candidates whose text is already ≤ MAX_SUMMARY_CHARS pass through unchanged.
    - Cache hits are served instantly (no LLM call).
    - New summaries are generated in parallel (SUMMARIZER_WORKERS threads).
    - The updated cache is flushed to disk once after all workers finish.

    Args:
        candidates:  List of candidate dicts, each with at least 'text' and 'resume_id'.

    Returns:
        List of candidate dicts with 'text' replaced by the structured summary.
    """
    if not SUMMARIZER_ENABLED:
        # Disabled — fall back to simple truncation (old behaviour)
        results = []
        for c in candidates:
            text = c.get("text", "")
            if len(text) > MAX_SUMMARY_CHARS:
                text = text[:MAX_SUMMARY_CHARS] + "..."
            results.append({**c, "text": text})
        return results

    cache = _load_cache()

    # Quick pass: identify how many actually need LLM calls
    needs_llm = [
        c for c in candidates
        if len(c.get("text", "")) > MAX_SUMMARY_CHARS
        and f"{c['resume_id']}:{_fingerprint(c.get('text', ''))}" not in cache
    ]

    # Map resume_id → summary (populated below)
    summaries: dict[str, str] = {}
    cache_hits = 0
    llm_calls  = len(needs_llm)

    if llm_calls == 0:
        # All cache hits or short-enough texts — no LLM needed
        for c in candidates:
            text = c.get("text", "")
            key  = f"{c['resume_id']}:{_fingerprint(text)}"
            if key in cache:
                summaries[c["resume_id"]] = cache[key]
                cache_hits += 1
            else:
                summaries[c["resume_id"]] = text
        print(f"  [Summarizer] {cache_hits}/{len(candidates)} cache hits — 0 LLM calls")
    else:
        # Run summarization in parallel threads
        print(f"  [Summarizer] {len(candidates) - llm_calls} cache hits, "
              f"{llm_calls} new summaries via GPT-4o-mini "
              f"({SUMMARIZER_WORKERS} workers)...")

        with ThreadPoolExecutor(max_workers=SUMMARIZER_WORKERS) as pool:
            futures = {
                pool.submit(_summarize_one, c["resume_id"], c.get("text", ""), cache): c
                for c in candidates
            }
            for future in as_completed(futures):
                rid, summary = future.result()
                summaries[rid] = summary

        # Flush updated cache to disk once
        _save_cache(cache)
        print(f"  [Summarizer] Cache saved → {SUMMARY_CACHE_PATH}")

    # Rebuild candidate list with summarized text
    return [{**c, "text": summaries.get(c["resume_id"], c.get("text", ""))}
            for c in candidates]
