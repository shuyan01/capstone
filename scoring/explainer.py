"""
scoring/explainer.py

Standalone explanation helpers for ranked candidate output.
"""


def generate_explanation(
    skill_result: dict,
    experience_result: dict,
    technical_result: dict,
    culture_result: dict,
    composite_score: float,
) -> str:
    """Builds a concise recruiter-facing explanation."""
    parts = []

    matched = skill_result.get("matched_skills", [])
    missing = skill_result.get("missing_skills", [])
    partial = skill_result.get("partial_matches", [])
    if matched:
        parts.append(f"Matched skills: {', '.join(matched[:3])}.")
    if partial:
        parts.append(f"Related skills: {', '.join(partial[:2])}.")
    if missing:
        parts.append(f"Missing: {', '.join(missing[:2])}.")

    years = experience_result.get("total_years", 0)
    seniority = experience_result.get("seniority_level", "unclear")
    roles = experience_result.get("relevant_roles", [])
    if years > 0:
        parts.append(f"{years} years of experience, {seniority}-level.")
    if roles:
        parts.append(f"Relevant roles: {', '.join(roles[:2])}.")

    stack = technical_result.get("tech_stack", [])
    projects = technical_result.get("notable_projects", [])
    if stack:
        parts.append(f"Tech stack: {', '.join(stack[:4])}.")
    if projects:
        parts.append(f"Notable: {projects[0][:80]}.")

    soft_skills = culture_result.get("soft_skills", [])
    if soft_skills:
        parts.append(f"Soft skills: {', '.join(soft_skills[:3])}.")

    if composite_score >= 0.70:
        verdict = "Strong overall match."
    elif composite_score >= 0.50:
        verdict = "Moderate match worth considering."
    elif composite_score >= 0.30:
        verdict = "Partial match with some relevant signals."
    else:
        verdict = "Weak match with limited alignment."

    parts.append(verdict)
    return " ".join(parts)
