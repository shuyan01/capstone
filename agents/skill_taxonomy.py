"""
agents/skill_taxonomy.py

Canonical skill aliases and lightweight role-family helpers used by
the skill matching agent.
"""

from __future__ import annotations


ROLE_FAMILY_KEYWORDS = {
    "backend_cloud": (
        "backend", "api", "microservice", "cloud", "platform",
        "fastapi", "django", "flask", "spring", "java", "python",
    ),
    "devops": (
        "devops", "sre", "infrastructure", "kubernetes", "docker",
        "ci/cd", "pipeline", "terraform", "aws", "helm",
    ),
    "ml": (
        "machine learning", "ml", "mlops", "ai", "deep learning",
        "tensorflow", "pytorch", "model deployment", "inference",
    ),
    "business_development": (
        "business development", "partnership", "partnerships", "growth",
        "b2b", "saas", "enterprise", "client acquisition", "alliances",
    ),
}


SKILL_TAXONOMY = {
    "Python": {
        "aliases": {"python", "python 3", "python 3.x", "py"},
        "related": {"django", "flask", "fastapi"},
    },
    "FastAPI": {
        "aliases": {"fastapi", "fast api"},
        "related": {"flask", "django", "rest api", "microservices"},
    },
    "Cloud Deployment": {
        "aliases": {
            "cloud deployment", "cloud infrastructure", "cloud platform",
            "aws", "azure", "gcp", "ec2", "s3", "eks", "ecs",
            "docker", "kubernetes", "terraform",
        },
        "related": {"helm", "ansible", "cloudformation", "deployment pipelines"},
    },
    "AWS": {
        "aliases": {"aws", "amazon web services", "ec2", "s3", "lambda", "eks"},
        "related": {"azure", "gcp", "cloud deployment"},
    },
    "Docker": {
        "aliases": {"docker", "containerization", "containers"},
        "related": {"kubernetes", "container orchestration"},
    },
    "Kubernetes": {
        "aliases": {"kubernetes", "k8s", "eks", "aks", "gke", "helm"},
        "related": {"docker", "container orchestration"},
    },
    "CI/CD": {
        "aliases": {
            "ci/cd", "continuous integration", "continuous delivery",
            "continuous deployment", "jenkins", "github actions",
            "gitlab ci", "circleci", "argocd", "deployment pipelines",
        },
        "related": {"deployment pipelines", "release automation"},
    },
    "Machine Learning": {
        "aliases": {
            "machine learning", "ml", "deep learning", "artificial intelligence",
            "ai", "scikit-learn", "xgboost", "neural network",
            "tensorflow", "pytorch", "keras",
        },
        "related": {"tensorflow", "pytorch", "model deployment", "mlops"},
    },
    "TensorFlow": {
        "aliases": {"tensorflow", "keras"},
        "related": {"pytorch", "machine learning"},
    },
    "PyTorch": {
        "aliases": {"pytorch", "torch"},
        "related": {"tensorflow", "machine learning"},
    },
    "Model Deployment": {
        "aliases": {
            "model deployment", "model serving", "inference", "inference service",
            "mlops", "sagemaker", "torchserve", "triton", "deployment pipelines",
        },
        "related": {"kubeflow", "mlflow", "airflow"},
    },
    "Business Development": {
        "aliases": {
            "business development", "bd", "growth", "new business",
            "enterprise sales", "lead generation",
        },
        "related": {"strategic partnerships", "client acquisition", "b2b"},
    },
    "Strategic Partnerships": {
        "aliases": {
            "strategic partnerships", "partnerships", "alliances",
            "channel partners", "partner ecosystem",
        },
        "related": {"business development", "market expansion"},
    },
    "Client Acquisition": {
        "aliases": {
            "client acquisition", "customer acquisition", "pipeline generation",
            "enterprise client acquisition", "account acquisition",
        },
        "related": {"business development", "b2b", "saas"},
    },
    "B2B": {
        "aliases": {"b2b", "enterprise", "enterprise sales"},
        "related": {"saas", "client acquisition"},
    },
    "SaaS": {
        "aliases": {"saas", "software as a service"},
        "related": {"b2b", "enterprise"},
    },
}


def infer_role_family(job_query: str) -> str:
    """Infers a coarse role family used to prioritize relevant aliases."""
    query = (job_query or "").lower()
    best_family = "general"
    best_hits = 0

    for family, keywords in ROLE_FAMILY_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in query)
        if hits > best_hits:
            best_family = family
            best_hits = hits

    return best_family


def normalize_skill_name(skill: str) -> str:
    """Maps a free-form skill string to a canonical skill label when possible."""
    cleaned = (skill or "").strip()
    lowered = cleaned.lower()
    if not lowered:
        return cleaned

    for canonical, config in SKILL_TAXONOMY.items():
        if lowered == canonical.lower() or lowered in config["aliases"]:
            return canonical

    if "client acquisition" in lowered:
        return "Client Acquisition"
    if "partnership" in lowered:
        return "Strategic Partnerships"
    if "business development" in lowered or lowered == "growth":
        return "Business Development"
    if "ci/cd" in lowered or "continuous integration" in lowered or "continuous delivery" in lowered:
        return "CI/CD"
    if "pipeline" in lowered and "deploy" in lowered:
        return "CI/CD"
    if "machine learning" in lowered or lowered in {"ml", "ai", "mlops"} or "deep learning" in lowered:
        return "Machine Learning"
    if "deployment" in lowered and "model" in lowered:
        return "Model Deployment"
    if "deployment" in lowered and "cloud" in lowered:
        return "Cloud Deployment"

    return cleaned


def normalize_skill_list(skills: list[str]) -> list[str]:
    """Normalizes a list of skills while preserving order and uniqueness."""
    normalized = []
    seen = set()
    for skill in skills or []:
        canonical = normalize_skill_name(skill)
        key = canonical.lower()
        if key and key not in seen:
            seen.add(key)
            normalized.append(canonical)
    return normalized


def build_skill_guidance(skills: list[str]) -> list[str]:
    """Builds recruiter-facing alias hints to improve LLM matching consistency."""
    guidance = []
    for skill in skills:
        config = SKILL_TAXONOMY.get(skill)
        if not config:
            continue
        aliases = sorted(config["aliases"])
        guidance.append(f"{skill}: aliases include {', '.join(aliases[:6])}")
    return guidance


def classify_resume_skill_evidence(skills: list[str], resume_text: str) -> dict[str, list[str]]:
    """Finds deterministic matched and partial skills from resume text."""
    text = (resume_text or "").lower()
    matched = []
    partial = []

    for skill in skills:
        config = SKILL_TAXONOMY.get(skill)
        if not config:
            if skill.lower() in text:
                matched.append(skill)
            continue

        if any(alias in text for alias in config["aliases"] | {skill.lower()}):
            matched.append(skill)
        elif any(alias in text for alias in config["related"]):
            partial.append(skill)

    return {
        "matched_skills": matched,
        "partial_matches": partial,
    }
