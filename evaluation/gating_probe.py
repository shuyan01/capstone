"""
evaluation/gating_probe.py

Inspect how post-agent gating affects ranking results for a set of recruiter queries.

Run:
    python evaluation/gating_probe.py
    python evaluation/gating_probe.py "Python backend engineer with FastAPI"
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from agents.orchestrator import run_pipeline
from ingestion.chunker import chunk_all_resumes
from ingestion.parser import load_all_resumes

load_dotenv()


DEFAULT_PROBE_QUERIES = [
    "Python backend engineer with FastAPI and PostgreSQL experience",
    "Data analyst with SQL, Excel, and reporting experience",
    "Engineering manager with delivery ownership and stakeholder communication",
]


def load_chunks() -> list[dict]:
    """Loads and chunks resumes once for all probe runs."""
    resumes = load_all_resumes(
        csv_path="data/raw/Resume.csv",
        pdf_folder="data/raw/pdfs",
    )
    return chunk_all_resumes(resumes)


def format_reason_list(reasons: list[str]) -> str:
    """Formats gating reasons for console output."""
    if not reasons:
        return "none"
    return "; ".join(reasons[:3])


def run_probe(queries: list[str], top_k: int = 8) -> None:
    """Runs the pipeline with gating-failure visibility enabled."""
    chunks = load_chunks()

    print("=" * 72)
    print("Resume Matching System - Gating Probe")
    print("=" * 72)

    for index, query in enumerate(queries, start=1):
        print(f"\n[{index}/{len(queries)}] Query: {query}")
        results = run_pipeline(
            job_query=query,
            top_k=top_k,
            chunks=chunks,
            include_gating_failures=True,
        )

        passed = [candidate for candidate in results if candidate.get("gating_passed")]
        failed = [candidate for candidate in results if not candidate.get("gating_passed")]
        profile = results[0].get("screening_profile", "general") if results else "general"

        print(f"Profile: {profile}")
        print(
            f"Returned: {len(results)} | Passed: {len(passed)} | Failed: {len(failed)}"
        )

        if not results:
            print("No candidates returned.")
            continue

        print("Top candidates:")
        for candidate in results[: min(len(results), 5)]:
            status = "PASS" if candidate.get("gating_passed") else "FAIL"
            raw_score = candidate.get("raw_composite_score", 0.0)
            final_score = candidate.get("composite_score", 0.0)
            penalty = candidate.get("gating_penalty", 0.0)
            reasons = format_reason_list(candidate.get("gating_reasons", []))
            print(
                f"  {candidate['resume_id']}: {status} | "
                f"raw={raw_score:.3f} -> final={final_score:.3f} | "
                f"penalty={penalty:.3f} | reasons={reasons}"
            )

        if failed:
            print("Failed candidates:")
            for candidate in failed[: min(len(failed), 3)]:
                reasons = format_reason_list(candidate.get("gating_reasons", []))
                print(f"  {candidate['resume_id']}: {reasons}")


if __name__ == "__main__":
    probe_queries = sys.argv[1:] or DEFAULT_PROBE_QUERIES
    run_probe(probe_queries)
