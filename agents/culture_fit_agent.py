"""
agents/culture_fit_agent.py

Responsible for:
- Evaluating a candidate's soft skills and communication style
- Assessing indicators of teamwork, adaptability, and professionalism
- Scoring culture fit (0.0 to 1.0) with explanation

Model: gpt-4o (LLM-as-judge — requires higher reasoning for soft skill nuance)
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

# Culture fit uses gpt-4o (judge model) — better at nuanced soft skill assessment
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-4o")

llm = ChatOpenAI(
    model=JUDGE_MODEL,
    temperature=0,
    max_tokens=600,
)


# ─────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────

CULTURE_FIT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an experienced hiring manager evaluating candidate culture fit
and soft skills based on their resume.

Analyze the resume text and return ONLY a JSON object in this exact format (no extra text):
{{
    "communication_indicators": ["clear writing", "client-facing experience"],
    "teamwork_indicators": ["cross-functional collaboration", "mentoring junior staff"],
    "adaptability_indicators": ["worked across multiple domains"],
    "professionalism_score": 0.80,
    "soft_skills": ["leadership", "communication", "problem-solving"],
    "score": 0.72,
    "explanation": "One sentence summarizing the culture fit assessment."
}}

Rules:
- communication_indicators: phrases or evidence from resume showing communication ability (max 3)
- teamwork_indicators: evidence of collaboration or team contributions (max 3)
- adaptability_indicators: evidence of flexibility or learning new things (max 3)
- professionalism_score: 0.0 to 1.0 — clarity and quality of the resume itself
- soft_skills: inferred soft skills from the resume (max 5)
- score: 0.0 to 1.0 — overall culture fit signal from the resume
- explanation: one concise sentence

Scoring guide:
- 1.0 = strong evidence of leadership, communication, teamwork, adaptability
- 0.75 = good soft skill indicators across multiple dimensions
- 0.5 = some soft skill evidence but limited depth
- 0.25 = minimal soft skill signals in resume
- 0.0 = no soft skill evidence

Note: Base your assessment ONLY on what is written in the resume.
Do not make assumptions beyond what is stated."""),

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
# Culture Fit Agent
# ─────────────────────────────────────────

def score_culture_fit(job_query: str, candidate: dict) -> dict:
    """
    Scores a candidate's culture fit based on soft skill signals in their resume.

    Args:
        job_query:  The recruiter's job description
        candidate:  A candidate dict from hybrid_retriever.hybrid_search()

    Returns:
        Dict with keys:
        {
            "resume_id":                 "resume_csv_0042",
            "agent":                     "culture_fit",
            "score":                     0.72,
            "communication_indicators":  ["clear writing", "client-facing"],
            "teamwork_indicators":       ["cross-functional collaboration"],
            "adaptability_indicators":   ["multiple domain experience"],
            "professionalism_score":     0.80,
            "soft_skills":               ["leadership", "communication"],
            "explanation":               "Candidate shows strong communication..."
        }
    """
    chain    = CULTURE_FIT_PROMPT | llm
    response = chain.invoke({
        "job_query":   job_query,
        "resume_text": candidate["text"],
    })

    try:
        result = parse_json_response(response.content)
    except Exception:
        result = {
            "communication_indicators": [],
            "teamwork_indicators":      [],
            "adaptability_indicators":  [],
            "professionalism_score":    0.0,
            "soft_skills":              [],
            "score":                    0.0,
            "explanation":              "Could not parse culture fit response.",
        }

    return {
        "resume_id":                candidate["resume_id"],
        "agent":                    "culture_fit",
        "score":                    float(result.get("score",                    0.0)),
        "communication_indicators": result.get("communication_indicators",       []),
        "teamwork_indicators":      result.get("teamwork_indicators",            []),
        "adaptability_indicators":  result.get("adaptability_indicators",        []),
        "professionalism_score":    float(result.get("professionalism_score",    0.0)),
        "soft_skills":              result.get("soft_skills",                    []),
        "explanation":              result.get("explanation",                    ""),
    }


def run_culture_fit_agent(
    job_query: str,
    candidates: list[dict],
) -> list[dict]:
    """
    Runs culture fit evaluation on all candidates.

    Args:
        job_query:   The recruiter's job description
        candidates:  List of candidate dicts from hybrid_retriever

    Returns:
        List of culture fit result dicts, one per candidate
    """
    results = []

    for i, candidate in enumerate(candidates):
        print(f"[CultureFitAgent] Scoring candidate {i+1}/{len(candidates)}: "
              f"{candidate['resume_id']}")

        result = score_culture_fit(job_query, candidate)
        results.append(result)
        print(f"  Score: {result['score']:.2f} | "
              f"Soft skills: {result['soft_skills'][:3]}")

    return results


# ─────────────────────────────────────────
# Quick Test
# Run: python agents/culture_fit_agent.py
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

    job_query  = "Python backend engineer with FastAPI and PostgreSQL experience"
    candidates = hybrid_search(job_query, top_k=3, chunks=chunks)

    print(f"\nRunning culture fit evaluation on {len(candidates)} candidates...")
    print("=" * 60)

    results = run_culture_fit_agent(job_query, candidates)

    print("\n── Culture Fit Results ──")
    for r in results:
        print(f"\nResume:           {r['resume_id']}")
        print(f"Score:            {r['score']:.2f}")
        print(f"Professionalism:  {r['professionalism_score']:.2f}")
        print(f"Soft skills:      {r['soft_skills']}")
        print(f"Communication:    {r['communication_indicators']}")
        print(f"Teamwork:         {r['teamwork_indicators']}")
        print(f"Note:             {r['explanation']}")