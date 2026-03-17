"""
agents/skill_matching_agent.py

Responsible for:
- Extracting required skills from the job query
- Extracting skills mentioned in the candidate's resume chunks
- Scoring how well the candidate's skills match the job requirements
- Returning a skill coverage score (0.0 to 1.0) with explanation

Model: gpt-4o-mini (fast, cost-effective for structured extraction)
"""

import os
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from agents.skill_taxonomy import (
    build_skill_guidance,
    classify_resume_skill_evidence,
    infer_role_family,
    normalize_skill_list,
    normalize_skill_name,
)

load_dotenv()


# -----------------------------------------
# Model Setup
# -----------------------------------------

AGENT_MODEL = os.getenv("AGENT_MODEL", "gpt-4o-mini")

llm = ChatOpenAI(
    model=AGENT_MODEL,
    temperature=0,
    max_tokens=600,
)


# -----------------------------------------
# Prompts
# -----------------------------------------

SKILL_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a technical recruiter assistant.
Your job is to extract required skills from a job description.

Return ONLY a JSON object in this exact format (no extra text):
{{
    "required_skills": ["skill1", "skill2", "skill3"],
    "nice_to_have_skills": ["skill4", "skill5"]
}}

Rules:
- required_skills: skills explicitly required or strongly implied
- nice_to_have_skills: skills mentioned as optional or preferred
- Keep skill names concise (e.g. "Python", "FastAPI", "PostgreSQL")
- Include both technical and soft skills
- Maximum 15 skills per category"""),

    ("human", "Job description:\n{job_query}")
])


SKILL_MATCHING_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a technical recruiter evaluating a candidate's skills.

Compare the candidate's resume text against the required skills.
Return ONLY a JSON object in this exact format (no extra text):
{{
    "matched_skills": ["skill1", "skill2"],
    "missing_skills": ["skill3"],
    "partial_matches": ["skill4"],
    "score": 0.75,
    "explanation": "One sentence explaining the score."
}}

IMPORTANT MATCHING RULES — be generous and use semantic understanding:
- matched_skills: skills clearly present in the resume (exact OR equivalent)
  * "Python" matches "Python 3", "Python 3.x", "Python programming", "py"
  * "cloud experience" matches "AWS", "Azure", "GCP", "cloud infrastructure", "EC2", "S3"
  * "PostgreSQL" matches "Postgres", "PostgreSQL database", "psycopg2"
  * "FastAPI" matches "Fast API", "fastapi framework"
  * "machine learning" matches "ML", "scikit-learn", "TensorFlow", "deep learning models"
  * "backend" matches "server-side", "REST API", "microservices", "backend development"
  * If the technology stack in resume clearly implies a skill, count it as matched
- partial_matches: related or transferable skills
  * "MySQL" or "SQL Server" when "PostgreSQL" is required
  * "Flask" or "Django" when "FastAPI" is required
  * "Java Spring" when "backend engineer" is required
- missing_skills: skills with NO evidence or related technology in resume
- score: fraction of required_skills that are matched (matched / total required)
  * If 2 out of 3 required skills matched: score = 0.67
  * If all matched: score = 1.0
  * Partial matches count as 0.5 of a full match

Be generous — the goal is to surface good candidates, not eliminate them."""),

    ("human", """Role family: {role_family}
Required skills: {required_skills}
Nice to have: {nice_to_have_skills}
Skill alias guidance:
{skill_guidance}

Candidate resume text:
{resume_text}""")
])


# -----------------------------------------
# Helper: safe JSON parse
# -----------------------------------------

def parse_json_response(response_text: str) -> dict:
    """
    Safely parses a JSON string from the LLM response.
    Handles cases where the model adds extra text around the JSON.
    """
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
# Skill Matching Agent
# -----------------------------------------

def extract_required_skills(job_query: str) -> dict:
    """
    Uses gpt-4o-mini to extract required skills from the job description.

    Args:
        job_query: Natural language job description

    Returns:
        Dict with keys: required_skills, nice_to_have_skills
    """
    chain    = SKILL_EXTRACTION_PROMPT | llm
    response = chain.invoke({"job_query": job_query})

    try:
        parsed = parse_json_response(response.content)
    except Exception:
        parsed = {
            "required_skills":    [],
            "nice_to_have_skills": [],
        }

    return {
        "required_skills": normalize_skill_list(parsed.get("required_skills", [])),
        "nice_to_have_skills": normalize_skill_list(parsed.get("nice_to_have_skills", [])),
        "role_family": infer_role_family(job_query),
    }


def merge_skill_match_results(required_skills: list[str], resume_text: str, llm_result: dict) -> dict:
    """Combines LLM output with deterministic alias-based matching."""
    llm_matched = normalize_skill_list(llm_result.get("matched_skills", []))
    llm_partial = normalize_skill_list(llm_result.get("partial_matches", []))
    heuristic = classify_resume_skill_evidence(required_skills, resume_text)

    matched_set = {normalize_skill_name(skill) for skill in llm_matched}
    matched_set.update(heuristic["matched_skills"])

    partial_set = {normalize_skill_name(skill) for skill in llm_partial}
    partial_set.update(heuristic["partial_matches"])
    partial_set -= matched_set

    matched = [skill for skill in required_skills if skill in matched_set]
    partial = [skill for skill in required_skills if skill in partial_set]
    missing = [skill for skill in required_skills if skill not in matched_set and skill not in partial_set]

    score = 0.0
    if required_skills:
        score = round((len(matched) + 0.5 * len(partial)) / len(required_skills), 2)

    explanation = llm_result.get("explanation", "")
    if heuristic["matched_skills"] or heuristic["partial_matches"]:
        explanation = (
            f"{explanation} Alias-aware matching normalized skills across equivalent terms."
        ).strip()

    return {
        "matched_skills": matched,
        "partial_matches": partial,
        "missing_skills": missing,
        "score": score,
        "explanation": explanation,
    }


def score_skill_match(
    job_query: str,
    candidate: dict,
    required_skills: dict = None,
) -> dict:
    """
    Scores how well a candidate's skills match the job requirements.

    Args:
        job_query:        The recruiter's job description
        candidate:        A candidate dict from hybrid_retriever.hybrid_search()
        required_skills:  Pre-extracted skills dict (optional)

    Returns:
        Dict with skill match scores and details
    """
    if required_skills is None:
        required_skills = extract_required_skills(job_query)

    req_skills  = required_skills.get("required_skills",    [])
    nice_skills = required_skills.get("nice_to_have_skills", [])
    role_family = required_skills.get("role_family", infer_role_family(job_query))
    skill_guidance = build_skill_guidance(req_skills)

    chain    = SKILL_MATCHING_PROMPT | llm
    response = chain.invoke({
        "role_family":         role_family,
        "required_skills":     req_skills,
        "nice_to_have_skills": nice_skills,
        "skill_guidance":      "\n".join(skill_guidance) or "No extra alias guidance.",
        "resume_text":         candidate["text"],
    })

    try:
        result = parse_json_response(response.content)
    except Exception:
        result = {
            "matched_skills":  [],
            "missing_skills":  req_skills,
            "partial_matches": [],
            "score":           0.0,
            "explanation":     "Could not parse skill matching response.",
        }

    result = merge_skill_match_results(req_skills, candidate["text"], result)

    return {
        "resume_id":       candidate["resume_id"],
        "agent":           "skill_matching",
        "score":           float(result.get("score", 0.0)),
        "matched_skills":  result.get("matched_skills",  []),
        "missing_skills":  result.get("missing_skills",  []),
        "partial_matches": result.get("partial_matches", []),
        "explanation":     result.get("explanation",     ""),
    }


def run_skill_matching_agent(
    job_query: str,
    candidates: list[dict],
) -> list[dict]:
    """
    Runs skill matching evaluation on all candidates.

    Args:
        job_query:   The recruiter's job description
        candidates:  List of candidate dicts from hybrid_retriever

    Returns:
        List of skill match result dicts, one per candidate
    """
    print(f"[SkillAgent] Extracting required skills from job query...")
    required_skills = extract_required_skills(job_query)
    print(f"[SkillAgent] Required skills: {required_skills.get('required_skills', [])}")
    print(f"[SkillAgent] Role family: {required_skills.get('role_family', 'general')}")

    results = []
    for i, candidate in enumerate(candidates):
        print(f"[SkillAgent] Scoring candidate {i+1}/{len(candidates)}: "
              f"{candidate['resume_id']}")

        result = score_skill_match(job_query, candidate, required_skills)
        results.append(result)
        print(f"  Score: {result['score']:.2f} | "
              f"Matched: {result['matched_skills'][:3]}")

    return results


# -----------------------------------------
# Quick Test
# Run: python agents/skill_matching_agent.py
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

    print(f"\nRunning skill matching on {len(candidates)} candidates...")
    print("=" * 60)

    results = run_skill_matching_agent(job_query, candidates)

    print("\n── Skill Matching Results ──")
    for r in results:
        print(f"\nResume:   {r['resume_id']}")
        print(f"Score:    {r['score']:.2f}")
        print(f"Matched:  {r['matched_skills']}")
        print(f"Missing:  {r['missing_skills']}")
        print(f"Partial:  {r['partial_matches']}")
        print(f"Note:     {r['explanation']}")
