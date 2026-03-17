"""
scoring/aggregator.py

Responsible for:
- Combining scores from all four agents into a weighted composite score
- Applying post-agent gating to avoid weak candidates surfacing on one strong dimension
- Generating a human-readable explanation for each candidate's ranking
- Returning a final sorted list of ranked candidates
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

from scoring.explainer import generate_explanation

load_dotenv()


# -----------------------------------------
# Score Weights
# -----------------------------------------

WEIGHTS = {
    "skill":      0.40,
    "experience": 0.25,
    "technical":  0.20,
    "culture":    0.15,
}

DEFAULT_PROFILE_RULES = {
    "technical": {
        "keywords": (
            "backend", "frontend", "full stack", "developer", "engineer",
            "microservice", "cloud", "api", "fastapi", "react", "java",
            "spring", "python", "devops", "aws", "kubernetes",
        ),
        "minimums": {
            "skill": 0.40,
            "experience": 0.20,
            "technical": 0.35,
            "culture": 0.15,
        },
        "hard_dimensions": {"skill", "technical"},
    },
    "analytics": {
        "keywords": (
            "analyst", "analytics", "data", "sql", "reporting", "dashboard",
            "power bi", "tableau", "excel", "business intelligence",
        ),
        "minimums": {
            "skill": 0.35,
            "experience": 0.20,
            "technical": 0.25,
            "culture": 0.15,
        },
        "hard_dimensions": {"skill"},
    },
    "management": {
        "keywords": (
            "manager", "lead", "director", "stakeholder", "delivery",
            "people management", "program", "project", "consultant",
        ),
        "minimums": {
            "skill": 0.30,
            "experience": 0.35,
            "technical": 0.10,
            "culture": 0.30,
        },
        "hard_dimensions": {"experience", "culture"},
    },
    "general": {
        "keywords": (),
        "minimums": {
            "skill": 0.35,
            "experience": 0.20,
            "technical": 0.20,
            "culture": 0.15,
        },
        "hard_dimensions": {"skill"},
    },
}

DEFAULT_GATING_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "gating_thresholds.json"
)


def normalize_profile_rules(profile_rules: dict) -> dict:
    """Normalizes JSON-loaded gating rules into the internal structure."""
    normalized = {}
    for profile_name, config in profile_rules.items():
        normalized[profile_name] = {
            "keywords": tuple(config.get("keywords", [])),
            "minimums": {
                "skill": float(config.get("minimums", {}).get("skill", 0.35)),
                "experience": float(config.get("minimums", {}).get("experience", 0.20)),
                "technical": float(config.get("minimums", {}).get("technical", 0.20)),
                "culture": float(config.get("minimums", {}).get("culture", 0.15)),
            },
            "hard_dimensions": set(config.get("hard_dimensions", [])),
        }
    return normalized


def load_profile_rules() -> dict:
    """Loads gating thresholds from config file, falling back to defaults."""
    config_path = Path(
        os.getenv("GATING_CONFIG_PATH", str(DEFAULT_GATING_CONFIG_PATH))
    )

    if not config_path.exists():
        print(f"[Aggregator] Gating config not found at {config_path}; using defaults.")
        return normalize_profile_rules(DEFAULT_PROFILE_RULES)

    try:
        with config_path.open("r", encoding="utf-8") as file:
            loaded = json.load(file)
        if not isinstance(loaded, dict) or "profiles" not in loaded:
            raise ValueError("expected a top-level 'profiles' object")
        profile_rules = normalize_profile_rules(loaded["profiles"])
        if "general" not in profile_rules:
            raise ValueError("missing required 'general' profile")
        print(f"[Aggregator] Loaded gating config from {config_path}")
        return profile_rules
    except Exception as exc:
        print(f"[Aggregator] Failed to load gating config from {config_path}: {exc}")
        print("[Aggregator] Falling back to default gating thresholds.")
        return normalize_profile_rules(DEFAULT_PROFILE_RULES)


PROFILE_RULES = load_profile_rules()


def infer_role_profile(job_query: str) -> str:
    """Infers which threshold profile to apply for the recruiter query."""
    query = (job_query or "").strip().lower()
    if not query:
        return "general"

    best_profile = "general"
    best_hits = 0
    for profile_name, config in PROFILE_RULES.items():
        if profile_name == "general":
            continue
        hits = sum(1 for keyword in config["keywords"] if keyword in query)
        if hits > best_hits:
            best_profile = profile_name
            best_hits = hits

    return best_profile


def compute_raw_composite_score(
    skill_score: float,
    experience_score: float,
    technical_score: float,
    culture_score: float,
) -> float:
    """Returns the weighted score before any gating adjustments."""
    return round(
        WEIGHTS["skill"] * skill_score +
        WEIGHTS["experience"] * experience_score +
        WEIGHTS["technical"] * technical_score +
        WEIGHTS["culture"] * culture_score,
        4,
    )


def evaluate_candidate_gate(
    profile_name: str,
    skill_score: float,
    experience_score: float,
    technical_score: float,
    culture_score: float,
    matched_skills: list[str],
    missing_skills: list[str],
) -> dict:
    """
    Applies minimum-dimension screening after all agents have scored the candidate.

    The goal is to stop one strong dimension from masking a very weak critical one.
    """
    config = PROFILE_RULES.get(profile_name, PROFILE_RULES["general"])
    minimums = config["minimums"]
    hard_dimensions = config["hard_dimensions"]

    score_map = {
        "skill": skill_score,
        "experience": experience_score,
        "technical": technical_score,
        "culture": culture_score,
    }
    label_map = {
        "skill": "skill alignment",
        "experience": "experience fit",
        "technical": "technical depth",
        "culture": "culture fit",
    }

    reasons: list[str] = []
    penalty = 0.0
    hard_fail = False

    for dimension, threshold in minimums.items():
        actual = score_map[dimension]
        if actual >= threshold:
            continue

        gap = threshold - actual
        reasons.append(
            f"{label_map[dimension]} below threshold ({actual:.2f} < {threshold:.2f})"
        )
        penalty += min(0.18, round(gap * 0.65, 4))

        hard_floor = max(0.12, threshold - 0.18)
        if dimension in hard_dimensions and actual < hard_floor:
            hard_fail = True

    required_skill_count = len(matched_skills) + len(missing_skills)
    if required_skill_count >= 2:
        missing_ratio = len(missing_skills) / required_skill_count
        if missing_ratio >= 0.5:
            reasons.append(
                f"missing too many required skills ({len(missing_skills)}/{required_skill_count})"
            )
            penalty += 0.08
            if len(matched_skills) == 0 and profile_name in {"technical", "analytics"}:
                hard_fail = True

    if hard_fail:
        penalty += 0.15

    return {
        "profile_name": profile_name,
        "gating_passed": not hard_fail,
        "gating_reasons": reasons,
        "gating_penalty": round(min(penalty, 0.45), 4),
        "minimums": minimums,
    }


# -----------------------------------------
# Score Aggregator
# -----------------------------------------

def aggregate_candidate_scores(
    candidates:         list[dict],
    skill_results:      list[dict],
    experience_results: list[dict],
    technical_results:  list[dict],
    culture_results:    list[dict],
    job_query:          str = "",
    include_gating_failures: bool = False,
) -> list[dict]:
    """
    Combines all four agent scores into a single ranked list.

    Args:
        candidates:         List of candidate dicts from hybrid_retriever
        skill_results:      List of dicts from skill_matching_agent
        experience_results: List of dicts from experience_agent
        technical_results:  List of dicts from technical_agent
        culture_results:    List of dicts from culture_fit_agent

    Returns:
        Sorted list of candidate dicts with composite scores,
        ordered by composite_score descending (best match first)
    """

    # Index results by resume_id for O(1) lookup
    skill_map      = {r["resume_id"]: r for r in skill_results}
    experience_map = {r["resume_id"]: r for r in experience_results}
    technical_map  = {r["resume_id"]: r for r in technical_results}
    culture_map    = {r["resume_id"]: r for r in culture_results}
    profile_name   = infer_role_profile(job_query)

    ranked = []

    for candidate in candidates:
        rid = candidate["resume_id"]

        # Fetch each agent result (default to 0.0 if missing)
        skill_r      = skill_map.get(rid,      {"score": 0.0})
        experience_r = experience_map.get(rid, {"score": 0.0})
        technical_r  = technical_map.get(rid,  {"score": 0.0})
        culture_r    = culture_map.get(rid,    {"score": 0.0})

        skill_score      = float(skill_r.get("score",      0.0))
        experience_score = float(experience_r.get("score", 0.0))
        technical_score  = float(technical_r.get("score",  0.0))
        culture_score    = float(culture_r.get("score",    0.0))

        matched_skills = skill_r.get("matched_skills", [])
        missing_skills = skill_r.get("missing_skills", [])
        partial_matches = skill_r.get("partial_matches", [])

        raw_composite_score = compute_raw_composite_score(
            skill_score=skill_score,
            experience_score=experience_score,
            technical_score=technical_score,
            culture_score=culture_score,
        )
        gate_result = evaluate_candidate_gate(
            profile_name=profile_name,
            skill_score=skill_score,
            experience_score=experience_score,
            technical_score=technical_score,
            culture_score=culture_score,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
        )
        composite_score = max(
            0.0,
            round(raw_composite_score - gate_result["gating_penalty"], 4),
        )

        # Generate explanation
        explanation = generate_explanation(
            skill_result=skill_r,
            experience_result=experience_r,
            technical_result=technical_r,
            culture_result=culture_r,
            composite_score=composite_score,
        )
        if gate_result["gating_reasons"]:
            explanation = (
                f"{explanation} Screening note: "
                f"{'; '.join(gate_result['gating_reasons'][:2])}."
            )

        ranked.append({
            # Identity
            "resume_id":       rid,
            "category":        candidate.get("category", ""),
            "source":          candidate.get("source",   ""),

            # Composite score
            "raw_composite_score": raw_composite_score,
            "composite_score": composite_score,

            # Individual agent scores
            "skill_score":      skill_score,
            "experience_score": experience_score,
            "technical_score":  technical_score,
            "culture_score":    culture_score,

            # Score breakdown details
            "matched_skills":   matched_skills,
            "missing_skills":   missing_skills,
            "partial_matches":  partial_matches,
            "seniority_level":  experience_r.get("seniority_level", ""),
            "total_years":      experience_r.get("total_years",     0),
            "tech_stack":       technical_r.get("tech_stack",       []),
            "complexity_level": technical_r.get("complexity_level", ""),
            "soft_skills":      culture_r.get("soft_skills",        []),
            "education_tags":   candidate.get("education_tags",     []),
            "location_tags":    candidate.get("location_tags",      []),
            "industry_tags":    candidate.get("industry_tags",      []),
            "job_titles":       candidate.get("job_titles",         []),
            "degree_subjects":  candidate.get("degree_subjects",    []),
            "education_level":  candidate.get("education_level",    ""),
            "explicit_years":   candidate.get("explicit_years",     0),
            "screening_profile": gate_result["profile_name"],
            "gating_passed": gate_result["gating_passed"],
            "gating_penalty": gate_result["gating_penalty"],
            "gating_reasons": gate_result["gating_reasons"],
            "applied_thresholds": gate_result["minimums"],

            # Human-readable explanation
            "explanation": explanation,

            # Score weights used (for auditability)
            "score_weights": WEIGHTS,
        })

    passing_ranked = [candidate for candidate in ranked if candidate["gating_passed"]]
    if passing_ranked and not include_gating_failures:
        ranked = passing_ranked

    # Sort by composite score descending
    ranked.sort(key=lambda x: -x["composite_score"])

    # Add rank position (1-indexed)
    for i, r in enumerate(ranked):
        r["rank"] = i + 1

    print(f"[Aggregator] Scored and ranked {len(ranked)} candidates.")
    for r in ranked:
        print(f"  Rank {r['rank']}: {r['resume_id']} | "
              f"composite={r['composite_score']:.3f} "
              f"(raw={r['raw_composite_score']:.3f}, "
              f"skill={r['skill_score']:.2f}, "
              f"exp={r['experience_score']:.2f}, "
              f"tech={r['technical_score']:.2f}, "
              f"culture={r['culture_score']:.2f}, "
              f"gate={'pass' if r['gating_passed'] else 'fail'})")

    return ranked
