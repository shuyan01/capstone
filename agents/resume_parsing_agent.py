"""
agents/resume_parsing_agent.py

Resume Parsing Agent — Stage 1 of the multi-agent evaluation pipeline.

Responsibility:
- Detect major resume sections (Experience, Education, Skills, etc.)
- Compute a lightweight structural richness score
- Identify demographic bias markers for recruiter awareness
- Attach structured metadata to each candidate dict for downstream agents

This is a heuristic agent (zero LLM cost) that runs before the specialist
agents so the pipeline formally implements all 5 required stages:

    Resume Parsing → Skill Matching → Experience → Technical → Culture Fit
"""

import re
from guardrails.resume_validator import check_resume_bias


# -----------------------------------------
# Section Detection
# -----------------------------------------

_SECTION_PATTERNS = {
    "summary":        re.compile(r"\b(summary|objective|profile|about me|career goal)\b", re.I),
    "experience":     re.compile(r"\b(experience|employment|work history|career history|professional background)\b", re.I),
    "education":      re.compile(r"\b(education|qualification|academic background|degree|university|college)\b", re.I),
    "skills":         re.compile(r"\b(skills|technologies|competencies|expertise|technical proficiencies)\b", re.I),
    "projects":       re.compile(r"\b(projects|portfolio|key projects|notable projects)\b", re.I),
    "certifications": re.compile(r"\b(certifications?|certificates?|training|courses?|licenses?)\b", re.I),
    "awards":         re.compile(r"\b(awards?|achievements?|honors?|recognition|accomplishments?)\b", re.I),
    "languages":      re.compile(r"\b(languages?|linguistic|fluent in|spoken languages?)\b", re.I),
}


def _detect_sections(text: str) -> list[str]:
    """Returns section names whose header keywords appear in the text."""
    return [name for name, pat in _SECTION_PATTERNS.items() if pat.search(text)]


def _structural_richness(sections: list[str]) -> float:
    """
    Heuristic richness score based on detected sections.
    A resume with more structured sections is easier for agents to parse.
    Score range: 0.0 – 1.0
    """
    # Weight: core sections matter more
    weights = {
        "experience":     0.30,
        "skills":         0.25,
        "education":      0.20,
        "summary":        0.10,
        "certifications": 0.05,
        "projects":       0.05,
        "awards":         0.03,
        "languages":      0.02,
    }
    return round(sum(weights.get(s, 0) for s in sections), 3)


# -----------------------------------------
# Main Agent Function
# -----------------------------------------

def run_resume_parsing_agent(candidates: list[dict]) -> list[dict]:
    """
    Parses each candidate's resume text and attaches structural metadata.

    Adds to each candidate dict:
    - parsed_sections  (list[str])  : detected section names
    - structural_score (float)      : richness score 0–1
    - word_count       (int)        : approximate word count
    - bias_flags       (list[str])  : demographic markers found (recruiter awareness)

    Args:
        candidates: List of candidate dicts with at least 'text'.

    Returns:
        List of enriched candidate dicts (original keys preserved).
    """
    enriched = []
    for candidate in candidates:
        text = candidate.get("text", "")

        sections      = _detect_sections(text)
        richness      = _structural_richness(sections)
        word_count    = len(text.split())
        bias_report   = check_resume_bias(text)

        enriched.append({
            **candidate,
            "parsed_sections":  sections,
            "structural_score": richness,
            "word_count":       word_count,
            "bias_flags":       bias_report["flags"],
        })

    return enriched
