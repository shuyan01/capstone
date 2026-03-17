"""
guardrails/resume_validator.py

Responsible for:
- Validating resume data after parsing
- Ensuring each resume has the minimum required fields
- Flagging resumes that are too short or malformed
- Providing a validation report for the ingestion pipeline

Usage:
    from guardrails.resume_validator import validate_resume, validate_all_resumes
    result = validate_resume(resume_dict)
    report = validate_all_resumes(resumes_list)
"""

import re
from dotenv import load_dotenv

load_dotenv()


# -----------------------------------------
# Constants
# -----------------------------------------

MIN_RESUME_LENGTH   = 100    # minimum characters for resume text
MAX_RESUME_LENGTH   = 50000  # maximum characters (sanity check)
REQUIRED_FIELDS     = ["id", "category", "resume_text", "source"]
VALID_SOURCES       = ["csv", "pdf"]
VALID_CATEGORIES    = [
    "INFORMATION-TECHNOLOGY", "BUSINESS-DEVELOPMENT", "ADVOCATE",
    "CHEF", "FINANCE", "ENGINEERING", "ACCOUNTANT", "FITNESS",
    "AVIATION", "SALES", "HEALTHCARE", "CONSULTANT", "BANKING",
    "CONSTRUCTION", "PUBLIC-RELATIONS", "HR", "DESIGNER", "ARTS",
    "TEACHER", "APPAREL", "DIGITAL-MEDIA", "AGRICULTURE",
    "AUTOMOBILE", "BPO", "UNKNOWN",   # UNKNOWN allowed for PDFs without category
]


# -----------------------------------------
# Single Resume Validator
# -----------------------------------------

def validate_resume(resume: dict) -> dict:
    """
    Validates a single resume dict from the parser.

    Args:
        resume: A resume dict with keys: id, category, resume_text, source

    Returns:
        Dict with keys:
        {
            "valid":    True / False,
            "resume_id": "resume_csv_0001",
            "errors":   ["list of error messages"] (empty if valid)
        }
    """
    errors = []
    resume_id = resume.get("id", "unknown")

    # ── Check required fields exist ─────────
    for field in REQUIRED_FIELDS:
        if field not in resume or resume[field] is None:
            errors.append(f"Missing required field: '{field}'")

    if errors:
        return {"valid": False, "resume_id": resume_id, "errors": errors}

    # ── Validate resume text ─────────────────
    text = resume.get("resume_text", "")

    if not isinstance(text, str):
        errors.append("resume_text must be a string.")
    elif len(text.strip()) < MIN_RESUME_LENGTH:
        errors.append(
            f"resume_text too short: {len(text.strip())} chars "
            f"(minimum {MIN_RESUME_LENGTH})."
        )
    elif len(text.strip()) > MAX_RESUME_LENGTH:
        errors.append(
            f"resume_text too long: {len(text.strip())} chars "
            f"(maximum {MAX_RESUME_LENGTH})."
        )

    # ── Validate category ────────────────────
    category = str(resume.get("category", "")).strip().upper()
    if not category:
        errors.append("category cannot be empty.")
    elif category not in VALID_CATEGORIES:
        # Allow unknown categories with a warning (not an error)
        pass   # flexible — dataset may have custom categories

    # ── Validate source ──────────────────────
    source = resume.get("source", "")
    if source not in VALID_SOURCES:
        errors.append(
            f"Invalid source: '{source}'. Must be one of {VALID_SOURCES}."
        )

    # ── Validate ID format ───────────────────
    rid = resume.get("id", "")
    if not re.match(r"^resume_(csv|pdf)_\d+$", rid):
        errors.append(
            f"Invalid ID format: '{rid}'. "
            f"Expected format: resume_csv_0001 or resume_pdf_0001."
        )

    if errors:
        return {"valid": False, "resume_id": resume_id, "errors": errors}

    return {"valid": True, "resume_id": resume_id, "errors": []}


# -----------------------------------------
# Bias Detection
# -----------------------------------------

# Patterns for demographic markers that should not influence hiring decisions.
# Detection is for recruiter awareness only — does NOT block the candidate.
_BIAS_PATTERNS = [
    (re.compile(r"\b(date of birth|dob|born in|age\s*[:\-]\s*\d+|\d+\s*years?\s*old)\b", re.I), "age_disclosure"),
    (re.compile(r"\b(gender\s*[:\-]|sex\s*[:\-]|male|female)\b", re.I),                         "gender_mention"),
    (re.compile(r"\b(nationality\s*[:\-]|citizen of|native of|country of origin)\b", re.I),      "nationality_mention"),
    (re.compile(r"\b(married|single|divorced|widowed|marital status)\b", re.I),                  "marital_status"),
    (re.compile(r"\b(religion\s*[:\-]|christian|muslim|hindu|jewish|sikh|buddhist)\b", re.I),    "religion_mention"),
    (re.compile(r"\b(caste\s*[:\-]|tribe\s*[:\-]|ethnicity\s*[:\-])\b", re.I),                  "ethnicity_mention"),
    (re.compile(r"passport[\s\-]?size[\s\-]?photo|photograph enclosed|photo attached", re.I),    "photo_included"),
]


def check_resume_bias(text: str) -> dict:
    """
    Scans resume text for demographic markers that should not influence
    hiring decisions (age, gender, religion, marital status, etc.).

    This is a guardrail for recruiter awareness only — it does NOT block
    or penalise candidates. Flagged resumes may warrant blind review.

    Args:
        text: Raw resume text string.

    Returns:
        {"flags": list[str], "count": int}
        where each flag is a short label like "age_disclosure".
    """
    flags = []
    for pattern, label in _BIAS_PATTERNS:
        if pattern.search(text):
            flags.append(label)
    return {"flags": flags, "count": len(flags)}


# -----------------------------------------
# Batch Validator
# -----------------------------------------

def validate_all_resumes(resumes: list[dict]) -> dict:
    """
    Validates all resumes and returns a summary report.

    Args:
        resumes: List of resume dicts from parser.load_all_resumes()

    Returns:
        Dict with keys:
        {
            "total":         4966,
            "valid":         4960,
            "invalid":       6,
            "invalid_ids":   ["resume_csv_0123", ...],
            "error_details": [{"resume_id": ..., "errors": [...]}, ...]
        }
    """
    valid_count   = 0
    invalid_count = 0
    invalid_ids   = []
    error_details = []

    for resume in resumes:
        result = validate_resume(resume)

        if result["valid"]:
            valid_count += 1
        else:
            invalid_count += 1
            invalid_ids.append(result["resume_id"])
            error_details.append({
                "resume_id": result["resume_id"],
                "errors":    result["errors"],
            })

    report = {
        "total":         len(resumes),
        "valid":         valid_count,
        "invalid":       invalid_count,
        "invalid_ids":   invalid_ids,
        "error_details": error_details,
    }

    print(f"\n[ResumeValidator] Validation report:")
    print(f"  Total:   {report['total']}")
    print(f"  Valid:   {report['valid']}")
    print(f"  Invalid: {report['invalid']}")

    if error_details:
        print(f"\n  First 3 invalid resumes:")
        for detail in error_details[:3]:
            print(f"    {detail['resume_id']}: {detail['errors']}")

    return report


# -----------------------------------------
# Quick Test
# Run: python guardrails/resume_validator.py
# -----------------------------------------

if __name__ == "__main__":
    import sys, os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from ingestion.parser import load_all_resumes

    print("── Resume Validator Tests ──\n")

    # Test individual cases
    test_resumes = [
        # Valid resume
        {
            "id": "resume_csv_0001",
            "category": "INFORMATION-TECHNOLOGY",
            "resume_text": "Python developer with 5 years experience in FastAPI and PostgreSQL. " * 5,
            "source": "csv",
        },
        # Invalid — missing field
        {
            "id": "resume_csv_0002",
            "category": "ENGINEERING",
            "source": "csv",
        },
        # Invalid — text too short
        {
            "id": "resume_csv_0003",
            "category": "HR",
            "resume_text": "Short text.",
            "source": "csv",
        },
        # Invalid — bad source
        {
            "id": "resume_csv_0004",
            "category": "SALES",
            "resume_text": "Sales professional with 10 years experience in B2B sales. " * 5,
            "source": "excel",
        },
    ]

    for resume in test_resumes:
        result = validate_resume(resume)
        status = "✓ VALID" if result["valid"] else "✗ INVALID"
        print(f"{status}: {result['resume_id']}")
        if not result["valid"]:
            for err in result["errors"]:
                print(f"  - {err}")
        print()

    # Validate all real resumes
    print("\n── Validating all loaded resumes ──")
    resumes = load_all_resumes(
        csv_path   = "data/raw/Resume.csv",
        pdf_folder = "data/raw/pdfs",
    )
    validate_all_resumes(resumes)