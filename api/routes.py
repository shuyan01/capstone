"""
api/routes.py

All API endpoint definitions.
Endpoints:
    GET  /health        -- check API + ChromaDB status
    GET  /categories    -- list all available job categories
    POST /match         -- main endpoint: submit job query, get ranked candidates
"""

import os
import time
from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv

from api.schemas import (
    MatchRequest,
    MatchResponse,
    CandidateResult,
    ScoreBreakdown,
    HealthResponse,
    CategoriesResponse,
    ErrorResponse,
    FeedbackRequest,
    FeedbackResponse,
    AnalyticsResponse,
    ScheduleInterviewRequest,
    ScheduleInterviewResponse,
    HandoffNoteRequest,
    HandoffNoteResponse,
    HandoffTimelineItem,
)
from analytics.feedback_store      import (
    create_handoff_note,
    create_interview_schedule,
    get_feedback_analytics,
    list_handoff_notes,
    list_interview_schedule,
    save_feedback,
)
from agents.orchestrator          import run_pipeline
from ingestion.embedder           import get_chroma_collection
from guardrails.input_validator   import validate_job_query

load_dotenv()

router = APIRouter()

# Preloaded chunks — set once at startup by main.py
_chunks: list[dict] = []

def set_chunks(chunks: list[dict]) -> None:
    """Called once at startup by main.py to cache the chunks."""
    global _chunks
    _chunks = chunks
    print(f"[Routes] Chunks registered: {len(_chunks)}")


# All 24 categories from the dataset
AVAILABLE_CATEGORIES = [
    "INFORMATION-TECHNOLOGY", "BUSINESS-DEVELOPMENT", "ADVOCATE",
    "CHEF", "FINANCE", "ENGINEERING", "ACCOUNTANT", "FITNESS",
    "AVIATION", "SALES", "HEALTHCARE", "CONSULTANT", "BANKING",
    "CONSTRUCTION", "PUBLIC-RELATIONS", "HR", "DESIGNER", "ARTS",
    "TEACHER", "APPAREL", "DIGITAL-MEDIA", "AGRICULTURE",
    "AUTOMOBILE", "BPO",
]


# -----------------------------------------
# GET /health
# -----------------------------------------

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check if the API and ChromaDB are running correctly.",
)
def health_check():
    """Returns the current status of the API and vector store."""
    try:
        collection   = get_chroma_collection()
        chroma_count = collection.count()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ChromaDB unavailable: {e}")

    return HealthResponse(
        status="ok",
        chroma_chunks=chroma_count,
        model_agent=os.getenv("AGENT_MODEL",     "gpt-4o-mini"),
        model_judge=os.getenv("JUDGE_MODEL",     "gpt-4o"),
        model_embedding=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
    )


# -----------------------------------------
# GET /categories
# -----------------------------------------

@router.get(
    "/categories",
    response_model=CategoriesResponse,
    summary="List job categories",
    description="Returns all available job categories for filtering.",
)
def list_categories():
    """Returns all job categories available in the dataset."""
    return CategoriesResponse(categories=sorted(AVAILABLE_CATEGORIES))


# -----------------------------------------
# POST /match
# -----------------------------------------

@router.post(
    "/match",
    response_model=MatchResponse,
    summary="Match candidates to a job description",
    description=(
        "Submit a natural language job description and receive "
        "a ranked list of candidates with explainable scores."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid job query"},
        500: {"model": ErrorResponse, "description": "Pipeline error"},
    },
)
def match_candidates(request: MatchRequest):
    """
    Main endpoint — runs the full multi-agent evaluation pipeline.

    **Example job queries:**
    - "Python backend engineer with FastAPI and PostgreSQL experience"
    - "Data scientist with machine learning and deep learning skills"
    - "Frontend developer with React and TypeScript experience"
    """

    # Run input guardrail validation
    validation = validate_job_query(request.job_query)
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation["error"])

    if request.filter_category:
        if request.filter_category.upper() not in AVAILABLE_CATEGORIES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid category: '{request.filter_category}'. "
                    f"Use GET /categories to see valid options."
                ),
            )

    try:
        advanced_filters = {
            "required_skills": request.required_skills,
            "min_years": request.min_years,
            "education_keywords": request.education_keywords,
            "industry_keywords": request.industry_keywords,
            "location_keywords": request.location_keywords,
        }
        _t0 = time.time()
        raw_results = run_pipeline(
            job_query=request.job_query,
            top_k=request.top_k,
            filter_category=request.filter_category,
            advanced_filters=advanced_filters,
            chunks=_chunks,          # pass preloaded chunks
        )
        _elapsed = round(time.time() - _t0, 3)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")

    candidates = []
    for r in raw_results:
        candidates.append(CandidateResult(
            rank=r.get("rank", 0),
            resume_id=r.get("resume_id", ""),
            category=r.get("category", ""),
            raw_composite_score=round(r.get("raw_composite_score", 0.0), 3),
            composite_score=round(r.get("composite_score", 0.0), 3),
            scores=ScoreBreakdown(
                skill_score=round(r.get("skill_score",      0.0), 3),
                experience_score=round(r.get("experience_score", 0.0), 3),
                technical_score=round(r.get("technical_score",  0.0), 3),
                culture_score=round(r.get("culture_score",    0.0), 3),
            ),
            matched_skills=r.get("matched_skills",  []),
            missing_skills=r.get("missing_skills",  []),
            partial_matches=r.get("partial_matches", []),
            seniority_level=r.get("seniority_level", ""),
            total_years=r.get("total_years", 0),
            tech_stack=r.get("tech_stack",   []),
            soft_skills=r.get("soft_skills", []),
            education_tags=r.get("education_tags", []),
            location_tags=r.get("location_tags", []),
            industry_tags=r.get("industry_tags", []),
            job_titles=r.get("job_titles", []),
            degree_subjects=r.get("degree_subjects", []),
            education_level=r.get("education_level", ""),
            explicit_years=r.get("explicit_years", 0),
            screening_profile=r.get("screening_profile", "general"),
            gating_passed=r.get("gating_passed", True),
            gating_penalty=round(r.get("gating_penalty", 0.0), 3),
            gating_reasons=r.get("gating_reasons", []),
            explanation=r.get("explanation", ""),
            bias_flags=r.get("bias_flags", []),
        ))

    _throughput = round(len(candidates) / _elapsed, 2) if _elapsed > 0 else 0.0

    # Estimate token usage: 3 technical agents × 3000 chars + 1 culture agent × 1500 chars
    # per candidate, divided by 4 (chars-per-token heuristic), plus ~300 tokens overhead/call.
    _MAX_TECH_CHARS    = 3000
    _MAX_CULTURE_CHARS = 1500
    _n = len(raw_results)
    _estimated_tokens = (
        (3 * _MAX_TECH_CHARS + _MAX_CULTURE_CHARS) * _n // 4  # resume text
        + 300 * 4 * _n                                         # prompt overhead
        + 200                                                   # skill extraction
    )

    return MatchResponse(
        job_query=request.job_query,
        total_found=len(candidates),
        elapsed_seconds=_elapsed,
        throughput=_throughput,
        estimated_tokens_used=_estimated_tokens,
        candidates=candidates,
    )

@router.get(
    "/resume/{resume_id}",
    summary="Get full resume text",
    description="Returns the full resume text by combining all chunks for a given resume_id.",
)
def get_resume_text(resume_id: str):
    """
    Fetches all chunks belonging to the given resume_id from ChromaDB
    and returns the combined full resume text.
    """
    try:
        collection = get_chroma_collection()
        results = collection.get(
            where={"resume_id": {"$eq": resume_id}},
            include=["documents", "metadatas"],
        )
        if not results["ids"]:
            raise HTTPException(status_code=404, detail=f"Resume not found: {resume_id}")

        chunks = sorted(
            zip(results["ids"], results["documents"], results["metadatas"]),
            key=lambda x: x[0]
        )

        full_text = "\n\n".join(doc for _, doc, _ in chunks)
        category = chunks[0][2].get("category", "") if chunks else ""

        return {
            "resume_id":   resume_id,
            "category":    category,
            "full_text":   full_text,
            "chunk_count": len(chunks),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching resume: {str(e)}")


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    summary="Capture recruiter feedback",
    description="Stores recruiter feedback about whether a recommended candidate was useful.",
)
def submit_feedback(request: FeedbackRequest):
    """Stores recruiter feedback for later analysis."""
    feedback_label = request.feedback_label.strip().lower()
    if feedback_label not in {"positive", "negative"}:
        raise HTTPException(
            status_code=400,
            detail="feedback_label must be 'positive' or 'negative'.",
        )

    record = save_feedback(
        resume_id=request.resume_id,
        job_query=request.job_query,
        feedback_label=feedback_label,
        notes=request.notes,
        rank_position=request.rank_position,
        composite_score=request.composite_score,
    )
    return FeedbackResponse(**record)


@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    summary="Recruiter feedback analytics",
    description="Returns simple dashboard analytics derived from recruiter feedback.",
)
def get_analytics():
    """Returns aggregate recruiter feedback analytics."""
    return AnalyticsResponse(**get_feedback_analytics())


@router.post(
    "/schedule",
    response_model=ScheduleInterviewResponse,
    summary="Schedule candidate interview",
    description="Creates an interview schedule record for a selected candidate.",
)
def schedule_interview(request: ScheduleInterviewRequest):
    """Creates an interview schedule entry."""
    record = create_interview_schedule(
        resume_id=request.resume_id,
        job_query=request.job_query,
        interview_round=request.interview_round,
        scheduled_for=request.scheduled_for,
        interviewer_name=request.interviewer_name,
        meeting_link=request.meeting_link,
    )
    return ScheduleInterviewResponse(**record)


@router.get(
    "/schedule",
    response_model=list[ScheduleInterviewResponse],
    summary="List all scheduled interviews",
)
def get_all_schedules():
    """Returns all interview schedule records."""
    return [ScheduleInterviewResponse(**item) for item in list_interview_schedule()]


@router.get(
    "/schedule/{resume_id}",
    response_model=list[ScheduleInterviewResponse],
    summary="List scheduled interviews for a candidate",
)
def get_schedule(resume_id: str):
    """Returns scheduled interviews for one candidate."""
    return [ScheduleInterviewResponse(**item) for item in list_interview_schedule(resume_id=resume_id)]


@router.post(
    "/handoff",
    response_model=HandoffNoteResponse,
    summary="Create recruiter-to-manager handoff note",
)
def create_handoff(request: HandoffNoteRequest):
    """Stores a handoff note for candidate review."""
    record = create_handoff_note(
        resume_id=request.resume_id,
        job_query=request.job_query,
        sender_role=request.sender_role,
        recipient_role=request.recipient_role,
        note=request.note,
    )
    return HandoffNoteResponse(**record)


@router.get(
    "/handoffs",
    response_model=list[HandoffTimelineItem],
    summary="List all handoff notes",
)
def get_all_handoffs():
    """Returns all handoff notes across all candidates."""
    return [HandoffTimelineItem(**item) for item in list_handoff_notes()]


@router.get(
    "/handoff/{resume_id}",
    response_model=list[HandoffTimelineItem],
    summary="List handoff notes for a candidate",
)
def get_handoffs(resume_id: str):
    """Returns recruiter and hiring-manager handoff notes for a candidate."""
    return [HandoffTimelineItem(**item) for item in list_handoff_notes(resume_id=resume_id)]
