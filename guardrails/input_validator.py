"""
guardrails/input_validator.py

Responsible for:
- Validating recruiter job queries before they enter the pipeline
- Rejecting empty, too short, or nonsensical inputs
- Detecting and rejecting potentially harmful or off-topic queries
- Returning clear error messages to help recruiters fix their input

Usage:
    from guardrails.input_validator import validate_job_query
    result = validate_job_query("Python backend engineer with FastAPI experience")
    if not result["valid"]:
        print(result["error"])
"""

import re
import os
from dotenv import load_dotenv

load_dotenv()


# -----------------------------------------
# Constants
# -----------------------------------------

MIN_QUERY_LENGTH = 20       # characters
MAX_QUERY_LENGTH = 2000     # characters

# Keywords that suggest a valid job description
JOB_RELATED_KEYWORDS = [
    "engineer", "developer", "manager", "analyst", "designer",
    "consultant", "architect", "specialist", "coordinator", "lead",
    "senior", "junior", "experience", "skills", "looking for",
    "hiring", "role", "position", "team", "work", "background",
    "python", "java", "data", "cloud", "frontend", "backend",
    "fullstack", "machine learning", "devops", "sql", "aws",
]

# Patterns that suggest harmful or off-topic content
BLOCKED_PATTERNS = [
    r"\b(hack|exploit|malware|virus|injection)\b",
    r"\b(password|credential|secret|token)\b",
    r"(https?://|www\.)\S+",   # URLs not expected in job queries
]

BIAS_PATTERNS = [
    r"\b(male only|female only|men only|women only)\b",
    r"\b(young|below\s+\d{2}|under\s+\d{2}|age\s+\d{2})\b",
    r"\b(single|married)\b",
    r"\b(christian|muslim|hindu|sikh|jewish)\b",
    r"\b(native english speaker|mother tongue|english only candidate)\b",
]


# -----------------------------------------
# Validation Functions
# -----------------------------------------

def check_length(query: str) -> dict:
    """Check if the query meets length requirements."""
    if not query or not query.strip():
        return {"valid": False, "error": "Job query cannot be empty."}

    if len(query.strip()) < MIN_QUERY_LENGTH:
        return {
            "valid": False,
            "error": (
                f"Job query is too short ({len(query.strip())} characters). "
                f"Please provide at least {MIN_QUERY_LENGTH} characters "
                f"describing the role requirements."
            ),
        }

    if len(query.strip()) > MAX_QUERY_LENGTH:
        return {
            "valid": False,
            "error": (
                f"Job query is too long ({len(query.strip())} characters). "
                f"Please limit to {MAX_QUERY_LENGTH} characters."
            ),
        }

    return {"valid": True}


def check_relevance(query: str) -> dict:
    """
    Check if the query looks like a legitimate job description.
    Uses simple keyword matching — not LLM-based (fast and free).
    """
    query_lower = query.lower()

    matched = [kw for kw in JOB_RELATED_KEYWORDS if kw in query_lower]

    if len(matched) == 0:
        return {
            "valid": False,
            "error": (
                "The query does not appear to be a job description. "
                "Please describe the role, required skills, or experience level. "
                "Example: 'We are looking for a Python backend engineer with "
                "FastAPI and PostgreSQL experience.'"
            ),
        }

    return {"valid": True, "matched_keywords": matched}


def check_blocked_content(query: str) -> dict:
    """Check for potentially harmful or off-topic content."""
    query_lower = query.lower()

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, query_lower):
            return {
                "valid": False,
                "error": (
                    "The query contains content that is not allowed. "
                    "Please provide a plain job description without URLs "
                    "or sensitive terms."
                ),
            }

    return {"valid": True}


def check_bias_sensitive_content(query: str) -> dict:
    """Rejects demographic or biased hiring instructions."""
    query_lower = query.lower()

    for pattern in BIAS_PATTERNS:
        if re.search(pattern, query_lower):
            return {
                "valid": False,
                "error": (
                    "The job query contains demographic or biased hiring language. "
                    "Please describe job-related skills, experience, and responsibilities only."
                ),
            }

    return {"valid": True}


# -----------------------------------------
# Main Validator
# -----------------------------------------

def validate_job_query(query: str) -> dict:
    """
    Validates a recruiter's job query before it enters the pipeline.

    Runs three checks in order:
    1. Length check (too short / too long)
    2. Relevance check (looks like a real job description)
    3. Blocked content check (no harmful patterns)

    Args:
        query: The recruiter's natural language job description

    Returns:
        Dict with keys:
        {
            "valid":   True / False,
            "error":   "Error message if invalid" (only present if invalid),
            "query":   "Cleaned query string" (only present if valid)
        }
    """
    # Clean whitespace
    cleaned = query.strip()

    # Run checks in order — stop at first failure
    length_check = check_length(cleaned)
    if not length_check["valid"]:
        return length_check

    blocked_check = check_blocked_content(cleaned)
    if not blocked_check["valid"]:
        return blocked_check

    bias_check = check_bias_sensitive_content(cleaned)
    if not bias_check["valid"]:
        return bias_check

    relevance_check = check_relevance(cleaned)
    if not relevance_check["valid"]:
        return relevance_check

    return {
        "valid": True,
        "query": cleaned,
        "matched_keywords": relevance_check.get("matched_keywords", []),
    }


# -----------------------------------------
# Quick Test
# Run: python guardrails/input_validator.py
# -----------------------------------------

if __name__ == "__main__":
    test_cases = [
        # Valid queries
        "We are looking for a Python backend engineer with FastAPI and PostgreSQL experience.",
        "Senior data scientist with machine learning and deep learning background needed.",

        # Invalid — too short
        "Python dev",

        # Invalid — not a job description
        "What is the weather today?",

        # Invalid — blocked content
        "We need someone to hack into our competitor's database.",

        # Invalid — empty
        "",
    ]

    print("── Input Validator Tests ──\n")
    for query in test_cases:
        result = validate_job_query(query)
        status = "✓ VALID" if result["valid"] else "✗ INVALID"
        print(f"{status}: '{query[:60]}...' " if len(query) > 60 else f"{status}: '{query}'")
        if not result["valid"]:
            print(f"  Reason: {result['error']}")
        print()
