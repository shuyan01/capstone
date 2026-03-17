"""
api/schemas.py

Pydantic models for all API request and response bodies.
FastAPI uses these to automatically validate inputs and
generate the Swagger UI documentation at /docs.
"""

from pydantic import BaseModel, Field
from typing import Optional


# -----------------------------------------
# Request Models
# -----------------------------------------

class MatchRequest(BaseModel):
    """
    Request body for POST /match
    Recruiter submits a natural language job description.
    """
    job_query: str = Field(
        ...,
        min_length=20,
        max_length=2000,
        description="Natural language job description from the recruiter",
        example="We are looking for a Python backend engineer with FastAPI and PostgreSQL experience.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of top candidates to return (1-20)",
    )
    filter_category: Optional[str] = Field(
        default=None,
        description="Optional job category filter e.g. INFORMATION-TECHNOLOGY, ENGINEERING",
        example="INFORMATION-TECHNOLOGY",
    )
    required_skills: Optional[list[str]] = Field(
        default=None,
        description="Optional hard filters for skills that must appear in the resume text",
        example=["Python", "FastAPI"],
    )
    min_years: Optional[int] = Field(
        default=None,
        ge=0,
        le=50,
        description="Optional minimum explicit years-of-experience filter",
        example=3,
    )
    education_keywords: Optional[list[str]] = Field(
        default=None,
        description="Optional education keywords to filter by, e.g. B.Tech, MBA, Computer Science",
        example=["Computer Science", "B.Tech"],
    )
    industry_keywords: Optional[list[str]] = Field(
        default=None,
        description="Optional industry/domain keywords to filter by",
        example=["banking", "fintech"],
    )
    location_keywords: Optional[list[str]] = Field(
        default=None,
        description="Optional location keywords to filter by",
        example=["Bangalore", "Chennai"],
    )


# -----------------------------------------
# Response Models
# -----------------------------------------

class ScoreBreakdown(BaseModel):
    """Individual agent scores for a candidate."""
    skill_score:      float = Field(description="Skill match score (0.0 to 1.0)")
    experience_score: float = Field(description="Experience fit score (0.0 to 1.0)")
    technical_score:  float = Field(description="Technical depth score (0.0 to 1.0)")
    culture_score:    float = Field(description="Culture fit score (0.0 to 1.0)")


class CandidateResult(BaseModel):
    """A single ranked candidate result."""
    rank:             int   = Field(description="Rank position (1 = best match)")
    resume_id:        str   = Field(description="Unique resume identifier")
    category:         str   = Field(description="Job category from dataset")
    raw_composite_score: float = Field(description="Weighted score before post-agent gating penalties")
    composite_score:  float = Field(description="Weighted composite score (0.0 to 1.0)")
    scores:           ScoreBreakdown
    matched_skills:   list[str] = Field(description="Skills found in the resume")
    missing_skills:   list[str] = Field(description="Required skills not found")
    partial_matches:  list[str] = Field(description="Related/transferable skills")
    seniority_level:  str       = Field(description="Estimated seniority level")
    total_years:      int       = Field(description="Estimated years of experience")
    tech_stack:       list[str] = Field(description="Technologies identified in resume")
    soft_skills:      list[str] = Field(description="Soft skills identified")
    education_tags:   list[str] = Field(description="Extracted education-related keywords")
    location_tags:    list[str] = Field(description="Extracted location-related keywords")
    industry_tags:    list[str] = Field(description="Extracted industry/domain keywords")
    job_titles:       list[str] = Field(description="Structured role titles extracted from the resume")
    degree_subjects:  list[str] = Field(description="Structured degree subjects extracted from the resume")
    education_level:  str       = Field(description="Highest education level inferred from the resume")
    explicit_years:   int       = Field(description="Largest explicit years-of-experience mention found in the resume")
    screening_profile: str      = Field(description="Threshold profile inferred from the job query")
    gating_passed:    bool      = Field(description="Whether the candidate passed post-agent minimum thresholds")
    gating_penalty:   float     = Field(description="Penalty applied because one or more dimensions fell below threshold")
    gating_reasons:   list[str] = Field(description="Why the candidate was penalized or filtered during screening")
    explanation:      str       = Field(description="Human-readable explanation of the ranking")
    bias_flags:       list[str] = Field(default_factory=list, description="Demographic markers detected in the resume (awareness only, does not affect scoring)")


class MatchResponse(BaseModel):
    """Response body for POST /match"""
    job_query:              str                  = Field(description="The original job query")
    total_found:            int                  = Field(description="Number of candidates returned")
    elapsed_seconds:        float                = Field(description="Wall-clock time for the pipeline in seconds")
    throughput:             float                = Field(description="Candidates evaluated per second")
    estimated_tokens_used:  int                  = Field(description="Estimated OpenAI input tokens consumed (chars/4 heuristic). Enable LangSmith for exact counts.")
    candidates:             list[CandidateResult]


class HealthResponse(BaseModel):
    """Response body for GET /health"""
    status:          str = Field(description="API health status")
    chroma_chunks:   int = Field(description="Total resume chunks in ChromaDB")
    model_agent:     str = Field(description="Model used for agents")
    model_judge:     str = Field(description="Model used for LLM-as-judge")
    model_embedding: str = Field(description="Embedding model")


class CategoriesResponse(BaseModel):
    """Response body for GET /categories"""
    categories: list[str] = Field(description="List of all available job categories")


class ErrorResponse(BaseModel):
    """Standard error response body."""
    error:   str = Field(description="Error type")
    message: str = Field(description="Detailed error message")


class FeedbackRequest(BaseModel):
    """Request body for recruiter feedback submission."""
    resume_id: str = Field(description="Resume identifier")
    job_query: str = Field(description="Job description used during evaluation")
    feedback_label: str = Field(description="positive or negative", examples=["positive"])
    notes: Optional[str] = Field(default=None, description="Optional recruiter notes")
    rank_position: Optional[int] = Field(default=None, ge=1, description="Rank position shown to recruiter")
    composite_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Composite score at feedback time")


class FeedbackResponse(BaseModel):
    """Stored recruiter feedback response."""
    id: int
    resume_id: str
    job_query: str
    feedback_label: str
    notes: str
    rank_position: Optional[int]
    composite_score: Optional[float]


class FeedbackAnalyticsItem(BaseModel):
    """Simple label/count tuple for analytics cards."""
    resume_id: Optional[str] = None
    job_query: Optional[str] = None
    feedback_count: Optional[int] = None
    usage_count: Optional[int] = None


class TrendPoint(BaseModel):
    bucket: str
    positive_feedback: int = 0
    negative_feedback: int = 0
    total_feedback: int = 0


class ScheduleAnalyticsItem(BaseModel):
    interview_round: str
    total_count: int
    scheduled_count: int


class HandoffAnalyticsItem(BaseModel):
    recipient_role: str
    total_count: int


class RecentFeedbackItem(BaseModel):
    id: int
    resume_id: str
    job_query: str
    feedback_label: str
    notes: Optional[str] = None
    rank_position: Optional[int] = None
    composite_score: Optional[float] = None
    created_at: str


class AnalyticsResponse(BaseModel):
    """Dashboard analytics response."""
    total_feedback: int
    positive_feedback: int
    negative_feedback: int
    positive_rate: float
    avg_composite_score: float
    top_resumes: list[FeedbackAnalyticsItem]
    common_queries: list[FeedbackAnalyticsItem]
    feedback_trend: list[TrendPoint]
    interviews_summary: list[ScheduleAnalyticsItem]
    handoff_summary: list[HandoffAnalyticsItem]
    recent_feedback: list[RecentFeedbackItem]


class ScheduleInterviewRequest(BaseModel):
    resume_id: str
    job_query: str
    interview_round: str = Field(description="e.g. recruiter_screen, technical_round, manager_round")
    scheduled_for: str = Field(description="ISO-like date time string chosen by the recruiter")
    interviewer_name: str
    meeting_link: Optional[str] = None


class ScheduleInterviewResponse(BaseModel):
    id: int
    resume_id: str
    job_query: str
    interview_round: str
    scheduled_for: str
    interviewer_name: str
    meeting_link: str
    status: str


class HandoffNoteRequest(BaseModel):
    resume_id: str
    job_query: str
    sender_role: str
    recipient_role: str
    note: str = Field(min_length=5, max_length=2000)


class HandoffNoteResponse(BaseModel):
    id: int
    resume_id: str
    job_query: str
    sender_role: str
    recipient_role: str
    note: str


class HandoffTimelineItem(BaseModel):
    id: int
    resume_id: str
    job_query: str
    sender_role: str
    recipient_role: str
    note: str
    created_at: str
