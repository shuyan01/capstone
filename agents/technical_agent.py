"""
agents/technical_agent.py

Responsible for:
- Estimating the depth of a candidate's technical expertise
- Evaluating complexity of projects and technologies used
- Scoring technical proficiency (0.0 to 1.0) with explanation

Model: gpt-4o-mini
"""

import os
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()


# -----------------------------------------
# Model Setup
# -----------------------------------------

AGENT_MODEL = os.getenv("AGENT_MODEL", "gpt-4o-mini")

llm = ChatOpenAI(
    model=AGENT_MODEL,
    temperature=0,
    max_tokens=500,
)


# -----------------------------------------
# Prompt
# -----------------------------------------

TECHNICAL_DEPTH_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior technical interviewer evaluating a candidate's technical depth.

Analyze the resume and return ONLY a JSON object in this exact format (no extra text):
{{
    "tech_stack": ["Python", "FastAPI", "Docker"],
    "complexity_level": "intermediate",
    "notable_projects": ["Built REST API serving 10k users"],
    "score": 0.70,
    "explanation": "One sentence summarizing the technical depth assessment."
}}

STRICT RULES for tech_stack:
- Only list technologies EXPLICITLY mentioned by name in the resume text
- Do NOT infer or guess technologies from job titles or industry alone
- Do NOT include a technology unless you can find it written in the resume
- Valid examples of explicit mentions:
  * "Python" matches "Python", "Python 3", "Python 3.x", "python programming"
  * "AWS" matches "Amazon Web Services", "AWS S3", "EC2", "AWS Lambda"
  * "cloud" matches "cloud infrastructure", "cloud deployment", "Azure", "GCP"
- Invalid examples (do NOT include these):
  * Job title is "IT Manager" → do NOT include "Python" unless Python is written
  * Resume mentions "Supply Chain" → do NOT include "SAP" unless SAP is written
  * Resume mentions "data" → do NOT include "SQL" unless SQL is written

Rules for other fields:
- complexity_level: one of "basic", "intermediate", "advanced", "expert"
  based only on evidence in the resume
- notable_projects: technically impressive achievements explicitly described (max 3)
  empty list if none found
- score: 0.0 to 1.0 — how well the explicitly mentioned tech matches job requirements
  * 1.0 = all required technologies explicitly present and used in complex ways
  * 0.75 = most required technologies explicitly present
  * 0.5 = some required technologies explicitly present
  * 0.25 = few related technologies present
  * 0.0 = none of the required technologies mentioned
- explanation: one honest sentence based only on what is written"""),

    ("human", """Job requirement:
{job_query}

Candidate resume text:
{resume_text}""")
])


# -----------------------------------------
# Helper: safe JSON parse
# -----------------------------------------

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


# -----------------------------------------
# Technical Agent
# -----------------------------------------

def score_technical_depth(job_query: str, candidate: dict) -> dict:
    """
    Scores the technical depth of a candidate relative to the job requirements.
    Only considers technologies explicitly mentioned in the resume.

    Args:
        job_query:  The recruiter's job description
        candidate:  A candidate dict from hybrid_retriever.hybrid_search()

    Returns:
        Dict with keys:
        {
            "resume_id":        "resume_csv_0042",
            "agent":            "technical",
            "score":            0.70,
            "tech_stack":       ["Python", "FastAPI", "Docker"],
            "complexity_level": "intermediate",
            "notable_projects": ["Built REST API serving 10k users"],
            "explanation":      "Candidate explicitly mentions Python and FastAPI..."
        }
    """
    chain    = TECHNICAL_DEPTH_PROMPT | llm
    response = chain.invoke({
        "job_query":   job_query,
        "resume_text": candidate["text"],
    })

    try:
        result = parse_json_response(response.content)
    except Exception:
        result = {
            "tech_stack":       [],
            "complexity_level": "basic",
            "notable_projects": [],
            "score":            0.0,
            "explanation":      "Could not parse technical depth response.",
        }

    return {
        "resume_id":        candidate["resume_id"],
        "agent":            "technical",
        "score":            float(result.get("score",             0.0)),
        "tech_stack":       result.get("tech_stack",              []),
        "complexity_level": result.get("complexity_level",        "basic"),
        "notable_projects": result.get("notable_projects",        []),
        "explanation":      result.get("explanation",             ""),
    }


def run_technical_agent(
    job_query: str,
    candidates: list[dict],
) -> list[dict]:
    """
    Runs technical depth evaluation on all candidates.

    Args:
        job_query:   The recruiter's job description
        candidates:  List of candidate dicts from hybrid_retriever

    Returns:
        List of technical evaluation result dicts, one per candidate
    """
    results = []

    for i, candidate in enumerate(candidates):
        print(f"[TechnicalAgent] Scoring candidate {i+1}/{len(candidates)}: "
              f"{candidate['resume_id']}")

        result = score_technical_depth(job_query, candidate)
        results.append(result)
        print(f"  Score: {result['score']:.2f} | "
              f"Level: {result['complexity_level']} | "
              f"Stack: {result['tech_stack'][:3]}")

    return results


# -----------------------------------------
# Quick Test
# Run: python agents/technical_agent.py
# -----------------------------------------

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

    job_query  = "Python backend engineer with FastAPI and PostgreSQL experience"
    candidates = hybrid_search(job_query, top_k=3, chunks=chunks)

    print(f"\nRunning technical evaluation on {len(candidates)} candidates...")
    print("=" * 60)

    results = run_technical_agent(job_query, candidates)

    print("\n── Technical Evaluation Results ──")
    for r in results:
        print(f"\nResume:    {r['resume_id']}")
        print(f"Score:     {r['score']:.2f}")
        print(f"Level:     {r['complexity_level']}")
        print(f"Stack:     {r['tech_stack']}")
        print(f"Projects:  {r['notable_projects']}")
        print(f"Note:      {r['explanation']}")