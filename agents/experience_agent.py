"""
agents/experience_agent.py

Responsible for:
- Analyzing a candidate's years of experience
- Evaluating career progression and seniority level
- Scoring how well the experience level matches the job requirements
- Returning an experience fit score (0.0 to 1.0) with explanation

Model: gpt-4o-mini
"""

import os
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()


# ─────────────────────────────────────────
# Model Setup
# ─────────────────────────────────────────

AGENT_MODEL = os.getenv("AGENT_MODEL", "gpt-4o-mini")

llm = ChatOpenAI(
    model=AGENT_MODEL,
    temperature=0,
    max_tokens=500,
)


# ─────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────

EXPERIENCE_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior recruiter analyzing a candidate's work experience.

Analyze the resume text and return ONLY a JSON object in this exact format (no extra text):
{{
    "total_years": 5,
    "seniority_level": "mid",
    "relevant_roles": ["Software Engineer at Google", "Backend Developer at Startup"],
    "career_progression": "steady",
    "score": 0.75,
    "explanation": "One sentence summarizing the experience fit."
}}

Rules for each field:
- total_years: estimated total years of professional experience (integer)
- seniority_level: one of "entry", "junior", "mid", "senior", "lead", "executive"
- relevant_roles: list of job titles that are relevant to the required role (max 3)
- career_progression: one of "rapid", "steady", "lateral", "unclear"
- score: 0.0 to 1.0 — how well the experience matches the job requirement
- explanation: one concise sentence

Scoring guide:
- 1.0 = perfect match (right seniority, directly relevant roles)
- 0.75 = good match (close seniority, related domain)
- 0.5 = partial match (some relevant experience)
- 0.25 = weak match (different domain, wrong seniority)
- 0.0 = no relevant experience"""),

    ("human", """Job requirement:
{job_query}

Candidate resume text:
{resume_text}""")
])


# ─────────────────────────────────────────
# Helper: safe JSON parse
# ─────────────────────────────────────────

def parse_json_response(response_text: str) -> dict:
    """Safely parses a JSON string from the LLM response."""
    text = response_text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
        raise


# ─────────────────────────────────────────
# Experience Agent
# ─────────────────────────────────────────

def score_experience(job_query: str, candidate: dict) -> dict:
    """
    Scores how well a candidate's experience matches the job requirements.

    Args:
        job_query:  The recruiter's job description
        candidate:  A candidate dict from hybrid_retriever.hybrid_search()

    Returns:
        Dict with keys:
        {
            "resume_id":          "resume_csv_0042",
            "agent":              "experience",
            "score":              0.75,
            "total_years":        5,
            "seniority_level":    "mid",
            "relevant_roles":     ["Software Engineer", "Backend Developer"],
            "career_progression": "steady",
            "explanation":        "Candidate has 5 years of relevant backend experience..."
        }
    """
    chain    = EXPERIENCE_ANALYSIS_PROMPT | llm
    response = chain.invoke({
        "job_query":   job_query,
        "resume_text": candidate["text"],
    })

    try:
        result = parse_json_response(response.content)
    except Exception:
        result = {
            "total_years":        0,
            "seniority_level":    "unclear",
            "relevant_roles":     [],
            "career_progression": "unclear",
            "score":              0.0,
            "explanation":        "Could not parse experience analysis response.",
        }

    return {
        "resume_id":          candidate["resume_id"],
        "agent":              "experience",
        "score":              float(result.get("score",              0.0)),
        "total_years":        int(result.get("total_years",          0)),
        "seniority_level":    result.get("seniority_level",          "unclear"),
        "relevant_roles":     result.get("relevant_roles",           []),
        "career_progression": result.get("career_progression",       "unclear"),
        "explanation":        result.get("explanation",              ""),
    }


def run_experience_agent(
    job_query: str,
    candidates: list[dict],
) -> list[dict]:
    """
    Runs experience evaluation on all candidates.

    Args:
        job_query:   The recruiter's job description
        candidates:  List of candidate dicts from hybrid_retriever

    Returns:
        List of experience result dicts, one per candidate
    """
    results = []

    for i, candidate in enumerate(candidates):
        print(f"[ExperienceAgent] Scoring candidate {i+1}/{len(candidates)}: "
              f"{candidate['resume_id']}")

        result = score_experience(job_query, candidate)
        results.append(result)
        print(f"  Score: {result['score']:.2f} | "
              f"Seniority: {result['seniority_level']} | "
              f"Years: {result['total_years']}")

    return results


# ─────────────────────────────────────────
# Quick Test
# Run: python agents/experience_agent.py
# ─────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from ingestion.parser           import load_all_resumes
    from ingestion.chunker          import chunk_all_resumes
    from retrieval.hybrid_retriever import hybrid_search

    print("Loading data...")
    resumes = load_all_resumes(
        csv_path   = "data/raw/Resume.csv",
        pdf_folder = "data/raw/pdfs",
    )
    chunks = chunk_all_resumes(resumes)

    job_query  = "Senior Python backend engineer with FastAPI and PostgreSQL experience"
    candidates = hybrid_search(job_query, top_k=3, chunks=chunks)

    print(f"\nRunning experience evaluation on {len(candidates)} candidates...")
    print("=" * 60)

    results = run_experience_agent(job_query, candidates)

    print("\n── Experience Evaluation Results ──")
    for r in results:
        print(f"\nResume:      {r['resume_id']}")
        print(f"Score:       {r['score']:.2f}")
        print(f"Years:       {r['total_years']}")
        print(f"Seniority:   {r['seniority_level']}")
        print(f"Progression: {r['career_progression']}")
        print(f"Roles:       {r['relevant_roles']}")
        print(f"Note:        {r['explanation']}")