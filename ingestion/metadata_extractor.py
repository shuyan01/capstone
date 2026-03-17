"""
ingestion/metadata_extractor.py

Structured resume metadata extraction with a hybrid strategy:
- heuristic extraction for fast baseline coverage
- optional LLM enrichment for higher-quality structured fields
- local cache to avoid repeating LLM calls for unchanged resumes
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
METADATA_MODEL = os.getenv("METADATA_MODEL", os.getenv("AGENT_MODEL", "gpt-4o-mini"))
METADATA_EXTRACTION_MODE = os.getenv("METADATA_EXTRACTION_MODE", "hybrid").strip().lower()
METADATA_TEXT_CHARS = int(os.getenv("METADATA_TEXT_CHARS", "2600"))
METADATA_CACHE_PATH = Path(
    os.getenv("METADATA_CACHE_PATH", "./data/processed/metadata_cache.json")
)

_CACHE_LOADED = False
_METADATA_CACHE: dict[str, dict] = {}


EDUCATION_PATTERNS = [
    r"\bb\.?tech\b",
    r"\bb\.?e\b",
    r"\bm\.?tech\b",
    r"\bm\.?e\b",
    r"\bbsc\b",
    r"\bmsc\b",
    r"\bbca\b",
    r"\bmca\b",
    r"\bmba\b",
    r"\bbachelor(?:'s)?\b",
    r"\bmaster(?:'s)?\b",
    r"\bph\.?d\b",
    r"\bdiploma\b",
    r"\bcomputer science\b",
    r"\binformation technology\b",
    r"\belectronics\b",
    r"\bmechanical\b",
    r"\bcivil\b",
]

LOCATION_PATTERNS = [
    "bangalore", "bengaluru", "chennai", "hyderabad", "pune", "mumbai",
    "delhi", "noida", "gurgaon", "gurugram", "kolkata", "coimbatore",
    "remote", "onsite", "india", "usa", "singapore", "dubai", "london",
    "new york", "san francisco",
]

INDUSTRY_PATTERNS = [
    "banking", "finance", "fintech", "healthcare", "insurance",
    "telecom", "retail", "ecommerce", "manufacturing", "automotive",
    "aviation", "education", "edtech", "hospitality", "consulting",
    "saas", "cloud", "media", "pharma", "logistics", "supply chain",
]

JOB_TITLE_PATTERNS = [
    r"\bsoftware engineer\b",
    r"\bbackend engineer\b",
    r"\bfrontend engineer\b",
    r"\bfull stack developer\b",
    r"\bdata scientist\b",
    r"\bdata analyst\b",
    r"\bmachine learning engineer\b",
    r"\bdevops engineer\b",
    r"\bsite reliability engineer\b",
    r"\btechnical lead\b",
    r"\bproduct manager\b",
    r"\bbusiness development manager\b",
    r"\bpartnerships lead\b",
    r"\bsales manager\b",
]

YEAR_PATTERNS = [
    r"(\d{1,2})\s*\+?\s*(?:years|year|yrs|yr)\b",
    r"experience\s*(?:of)?\s*(\d{1,2})\s*\+?\s*(?:years|year|yrs|yr)\b",
]

SECTION_PATTERNS = {
    "summary": r"(summary|profile|objective|about me)",
    "experience": r"(experience|work experience|employment history|professional experience)",
    "education": r"(education|academic background|qualification)",
    "skills": r"(skills|technical skills|core competencies)",
}


def _load_cache() -> None:
    """Loads metadata cache from disk once."""
    global _CACHE_LOADED, _METADATA_CACHE
    if _CACHE_LOADED:
        return
    if METADATA_CACHE_PATH.exists():
        try:
            _METADATA_CACHE = json.loads(METADATA_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _METADATA_CACHE = {}
    _CACHE_LOADED = True


def _save_cache() -> None:
    """Writes metadata cache to disk."""
    METADATA_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_CACHE_PATH.write_text(
        json.dumps(_METADATA_CACHE, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def _cache_key(text: str, category: str) -> str:
    """Builds a stable hash key for resume metadata caching."""
    payload = f"{category}\n{text}".encode("utf-8", errors="ignore")
    return hashlib.sha1(payload).hexdigest()


def _extract_matches(text: str, patterns: list[str], *, regex: bool = False) -> list[str]:
    matches: list[str] = []
    lowered = text.lower()

    for pattern in patterns:
        if regex:
            for match in re.finditer(pattern, lowered, flags=re.IGNORECASE):
                value = match.group(0).strip()
                canonical = value.replace(".", "").strip()
                if canonical and canonical not in matches:
                    matches.append(canonical)
        else:
            if pattern in lowered and pattern not in matches:
                matches.append(pattern)

    return matches[:6]


def estimate_explicit_years(text: str) -> int:
    """Returns the largest explicit years-of-experience mention in resume text."""
    lowered = text.lower()
    matches: list[int] = []
    for pattern in YEAR_PATTERNS:
        matches.extend(int(m) for m in re.findall(pattern, lowered, flags=re.IGNORECASE))
    return max(matches) if matches else 0


def extract_focus_text(text: str, max_chars: int = METADATA_TEXT_CHARS) -> str:
    """Keeps the most metadata-rich portions of a resume for LLM extraction."""
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized

    snippets = [normalized[:900]]
    lowered = normalized.lower()
    for pattern in SECTION_PATTERNS.values():
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if not match:
            continue
        start = max(0, match.start() - 40)
        end = min(len(normalized), start + 700)
        snippets.append(normalized[start:end])

    focus = " ".join(snippets)
    return focus[:max_chars]


def normalize_metadata(metadata: dict | None) -> dict:
    """Normalizes metadata payload into a consistent shape."""
    metadata = metadata or {}

    def unique_list(values: list[str] | None, limit: int = 6) -> list[str]:
        normalized = []
        seen = set()
        for value in values or []:
            cleaned = str(value).strip()
            lowered = cleaned.lower()
            if cleaned and lowered not in seen:
                seen.add(lowered)
                normalized.append(cleaned)
            if len(normalized) >= limit:
                break
        return normalized

    explicit_years = metadata.get("explicit_years", 0)
    try:
        explicit_years = int(explicit_years or 0)
    except Exception:
        explicit_years = 0

    return {
        "education_tags": unique_list(metadata.get("education_tags")),
        "location_tags": unique_list(metadata.get("location_tags")),
        "industry_tags": unique_list(metadata.get("industry_tags")),
        "job_titles": unique_list(metadata.get("job_titles")),
        "degree_subjects": unique_list(metadata.get("degree_subjects")),
        "education_level": str(metadata.get("education_level", "")).strip().lower(),
        "explicit_years": explicit_years,
    }


def merge_metadata(primary: dict, secondary: dict) -> dict:
    """Merges metadata with primary taking precedence for scalar confidence."""
    merged = normalize_metadata(secondary)
    primary = normalize_metadata(primary)

    for key in ("education_tags", "location_tags", "industry_tags", "job_titles", "degree_subjects"):
        merged[key] = normalize_metadata({
            key: primary.get(key, []) + merged.get(key, [])
        })[key]

    merged["education_level"] = primary.get("education_level") or merged.get("education_level", "")
    merged["explicit_years"] = max(primary.get("explicit_years", 0), merged.get("explicit_years", 0))
    return merged


def extract_heuristic_metadata(text: str, category: str = "") -> dict:
    """Extracts lightweight metadata without any network dependency."""
    education = _extract_matches(text, EDUCATION_PATTERNS, regex=True)
    locations = _extract_matches(text, LOCATION_PATTERNS, regex=False)
    industries = _extract_matches(text, INDUSTRY_PATTERNS, regex=False)
    job_titles = _extract_matches(text, JOB_TITLE_PATTERNS, regex=True)

    degree_subjects = []
    for subject in ("computer science", "information technology", "electronics", "mechanical", "civil"):
        if subject in text.lower() and subject not in degree_subjects:
            degree_subjects.append(subject)

    education_level = ""
    lowered = text.lower()
    if re.search(r"\bph\.?d\b|\bdoctorate\b", lowered):
        education_level = "doctorate"
    elif re.search(r"\bmaster(?:'s)?\b|\bm\.?tech\b|\bm\.?e\b|\bmba\b|\bmca\b|\bmsc\b", lowered):
        education_level = "masters"
    elif re.search(r"\bbachelor(?:'s)?\b|\bb\.?tech\b|\bb\.?e\b|\bbsc\b|\bbca\b", lowered):
        education_level = "bachelors"
    elif "diploma" in lowered:
        education_level = "diploma"

    category_lower = category.lower()
    if "bank" in category_lower and "banking" not in industries:
        industries.append("banking")
    if "health" in category_lower and "healthcare" not in industries:
        industries.append("healthcare")
    if "business" in category_lower and "business development manager" not in job_titles:
        job_titles.append("business development manager")

    return normalize_metadata({
        "education_tags": education,
        "location_tags": locations,
        "industry_tags": industries,
        "job_titles": job_titles,
        "degree_subjects": degree_subjects,
        "education_level": education_level,
        "explicit_years": estimate_explicit_years(text),
    })


def llm_extract_metadata(text: str, category: str, heuristic_metadata: dict) -> dict | None:
    """Uses OpenAI to enrich structured metadata from the resume text."""
    if METADATA_EXTRACTION_MODE == "heuristic" or not OPENAI_API_KEY or OpenAI is None:
        return None

    focus_text = extract_focus_text(text)
    client = OpenAI(api_key=OPENAI_API_KEY)
    system_prompt = (
        "You extract structured resume metadata. "
        "Return only valid JSON with keys: "
        "education_tags, location_tags, industry_tags, job_titles, degree_subjects, "
        "education_level, explicit_years. "
        "Use short phrases. Do not invent facts."
    )
    user_prompt = (
        f"Resume category: {category or 'unknown'}\n"
        f"Heuristic seed metadata: {json.dumps(heuristic_metadata, ensure_ascii=True)}\n"
        f"Resume text:\n{focus_text}"
    )

    try:
        response = client.chat.completions.create(
            model=METADATA_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return normalize_metadata(parsed)
    except Exception as exc:
        print(f"[MetadataExtractor] LLM metadata extraction failed: {exc}")
        return None


def extract_resume_metadata(text: str, category: str = "") -> dict:
    """Extracts structured metadata with cache, LLM enrichment, and fallback."""
    heuristic_metadata = extract_heuristic_metadata(text, category)
    if METADATA_EXTRACTION_MODE == "heuristic":
        return heuristic_metadata

    _load_cache()
    key = _cache_key(text, category)
    cached = _METADATA_CACHE.get(key)
    if cached:
        return normalize_metadata(cached)

    llm_metadata = llm_extract_metadata(text, category, heuristic_metadata)
    final_metadata = merge_metadata(llm_metadata or {}, heuristic_metadata)
    _METADATA_CACHE[key] = final_metadata
    _save_cache()
    return final_metadata
