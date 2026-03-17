"""
retrieval/advanced_filters.py

Helpers for applying recruiter-specified structured filters on top of
hybrid retrieval results before the final candidate list is returned.
"""

from __future__ import annotations

import re


def normalize_filter_values(values: list[str] | None) -> list[str]:
    """Normalizes and removes empty filter values."""
    if not values:
        return []
    return [v.strip().lower() for v in values if isinstance(v, str) and v.strip()]


def normalize_advanced_filters(filters: dict | None) -> dict:
    """Returns a normalized advanced-filter payload."""
    normalized = {
        "required_skills": [],
        "education_keywords": [],
        "industry_keywords": [],
        "location_keywords": [],
        "min_years": None,
    }

    if not filters:
        return normalized

    normalized.update({
        "required_skills": normalize_filter_values(filters.get("required_skills")),
        "education_keywords": normalize_filter_values(filters.get("education_keywords")),
        "industry_keywords": normalize_filter_values(filters.get("industry_keywords")),
        "location_keywords": normalize_filter_values(filters.get("location_keywords")),
    })

    min_years = filters.get("min_years")
    normalized["min_years"] = int(min_years) if min_years is not None else None
    return normalized


def has_active_advanced_filters(filters: dict | None) -> bool:
    """Returns True when at least one advanced filter is populated."""
    normalized = normalize_advanced_filters(filters)
    return any([
        normalized["required_skills"],
        normalized["education_keywords"],
        normalized["industry_keywords"],
        normalized["location_keywords"],
        normalized["min_years"] is not None,
    ])


def group_resume_texts(chunks: list[dict] | None) -> dict[str, str]:
    """Builds one lowercased text blob per resume_id."""
    if not chunks:
        return {}

    grouped: dict[str, list[str]] = {}
    for chunk in chunks:
        resume_id = chunk.get("resume_id")
        text = chunk.get("text", "")
        if not resume_id:
            continue
        grouped.setdefault(resume_id, []).append(text)

    return {
        resume_id: " ".join(texts).lower()
        for resume_id, texts in grouped.items()
    }


def group_resume_metadata(chunks: list[dict] | None) -> dict[str, dict]:
    """Builds one aggregated metadata record per resume_id from chunk metadata."""
    if not chunks:
        return {}

    grouped: dict[str, dict] = {}
    for chunk in chunks:
        resume_id = chunk.get("resume_id")
        if not resume_id:
            continue

        if resume_id not in grouped:
            grouped[resume_id] = {
                "education_tags": [],
                "location_tags": [],
                "industry_tags": [],
                "job_titles": [],
                "degree_subjects": [],
                "education_level": str(chunk.get("education_level", "") or ""),
                "explicit_years": int(chunk.get("explicit_years", 0) or 0),
            }

        record = grouped[resume_id]
        for key in ("education_tags", "location_tags", "industry_tags", "job_titles", "degree_subjects"):
            for value in chunk.get(key, []):
                if value not in record[key]:
                    record[key].append(value)
        if not record.get("education_level") and chunk.get("education_level"):
            record["education_level"] = str(chunk.get("education_level"))
        record["explicit_years"] = max(
            int(record.get("explicit_years", 0) or 0),
            int(chunk.get("explicit_years", 0) or 0),
        )

    return grouped


def estimate_years_from_text(text: str) -> int:
    """
    Extracts the largest explicit years-of-experience mention from text.
    This is intentionally heuristic and only used for recruiter-side filtering.
    """
    if not text:
        return 0

    patterns = [
        r"(\d{1,2})\s*\+?\s*(?:years|year|yrs|yr)\b",
        r"experience\s*(?:of)?\s*(\d{1,2})\s*\+?\s*(?:years|year|yrs|yr)\b",
    ]

    matches: list[int] = []
    for pattern in patterns:
        matches.extend(int(m) for m in re.findall(pattern, text, flags=re.IGNORECASE))

    return max(matches) if matches else 0


def candidate_passes_filters(
    candidate: dict,
    filters: dict | None,
    resume_texts: dict[str, str] | None = None,
) -> bool:
    """Checks whether a candidate satisfies all configured advanced filters."""
    normalized = normalize_advanced_filters(filters)
    if not has_active_advanced_filters(normalized):
        return True

    resume_id = candidate.get("resume_id", "")
    source_text = ""
    if resume_texts and resume_id in resume_texts:
        source_text = resume_texts[resume_id]
    else:
        source_text = str(candidate.get("text", "")).lower()

    category = str(candidate.get("category", "")).lower()
    education_tags = [v.lower() for v in candidate.get("education_tags", [])]
    location_tags = [v.lower() for v in candidate.get("location_tags", [])]
    industry_tags = [v.lower() for v in candidate.get("industry_tags", [])]

    required_skills = normalized["required_skills"]
    if required_skills and not all(skill in source_text for skill in required_skills):
        return False

    education_keywords = normalized["education_keywords"]
    if education_keywords and not any(
        keyword in source_text or keyword in education_tags
        for keyword in education_keywords
    ):
        return False

    industry_keywords = normalized["industry_keywords"]
    if industry_keywords:
        industry_match = any(
            keyword in source_text or keyword in category or keyword in industry_tags
            for keyword in industry_keywords
        )
        if not industry_match:
            return False

    location_keywords = normalized["location_keywords"]
    if location_keywords and not any(
        keyword in source_text or keyword in location_tags
        for keyword in location_keywords
    ):
        return False

    min_years = normalized["min_years"]
    candidate_years = max(
        int(candidate.get("explicit_years", 0) or 0),
        estimate_years_from_text(source_text),
    )
    if min_years is not None and candidate_years < min_years:
        return False

    return True


def filter_candidates(
    candidates: list[dict],
    filters: dict | None,
    chunks: list[dict] | None = None,
) -> list[dict]:
    """Filters candidates using recruiter-provided structured filters."""
    normalized = normalize_advanced_filters(filters)
    if not has_active_advanced_filters(normalized):
        return candidates

    resume_texts = group_resume_texts(chunks)
    filtered = [
        candidate
        for candidate in candidates
        if candidate_passes_filters(candidate, normalized, resume_texts)
    ]
    return filtered
