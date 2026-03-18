# AI Resume Intelligence and Candidate Matching System

This project matches recruiter-written job descriptions to resumes using hybrid retrieval, a multi-agent evaluation pipeline, and explainable ranking output.

## Features

- Hybrid candidate retrieval with ChromaDB semantic search and BM25 keyword search, fused via Reciprocal Rank Fusion (RRF), then cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`)
- LLM query expansion (gpt-4o-mini) before retrieval for better recall
- Resume Summarizer: GPT-4o-mini condenses each resume into a structured digest with persistent disk cache (zero cost on repeat queries)
- Resume Parsing Agent: heuristic section detection and demographic bias flagging with zero LLM cost
- Multi-agent evaluation pipeline (LangGraph 6 nodes) for skills, experience, technical depth, and culture fit
- Post-agent gating so one strong dimension does not hide a critical weak dimension
- Dynamic weight profiles (technical / analytics / management / general) auto-selected from job query
- Recruiter filters for category, required skills, years of experience, education, industry, and location
- Recruiter feedback loop with analytics, interview scheduling, and handoff notes
- Input guardrails: bias language and off-topic queries blocked with HTTP 400 (not a crash)
- LangSmith tracing: every pipeline node traced with token count and latency
- FastAPI service with Swagger docs
- React front end for search and candidate review
- Evaluation suite with DeepEval metrics (AnswerRelevancy + GEval LLM-as-Judge) and a lightweight benchmark runner

## Project Structure

```text
ai_resume_matching_system/
├── agents/         # Multi-agent orchestration and scoring agents
├── api/            # FastAPI app, routes, schemas
├── docs/           # Architecture diagram and supporting assets
├── evaluation/     # DeepEval tests and performance benchmark
├── frontend/       # React + Vite recruiter UI
├── guardrails/     # Input and resume validation
├── ingestion/      # Parsing, chunking, embedding
├── retrieval/      # Vector search, BM25, hybrid retrieval
└── scoring/        # Aggregation and explanation logic
```

## Setup

### 1. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Create `.env` in the project root.

```env
OPENAI_API_KEY=your_key_here
EMBEDDING_MODEL=text-embedding-3-small
AGENT_MODEL=gpt-4o-mini
JUDGE_MODEL=gpt-4o
CHROMA_PERSIST_DIR=./chroma_db
CHROMA_COLLECTION_NAME=resumes
TOP_K_FINAL=5
TOP_K_RETRIEVAL=20
VECTOR_SEARCH_WEIGHT=0.6
BM25_SEARCH_WEIGHT=0.4
GATING_CONFIG_PATH=./config/gating_thresholds.json
FORCE_BM25_ONLY=false
METADATA_EXTRACTION_MODE=heuristic

# Resume Summarizer
SUMMARIZER_ENABLED=true
MAX_RESUME_TEXT_CHARS=3000
MAX_CULTURE_TEXT_CHARS=1500
SUMMARIZER_WORKERS=4

# LangSmith tracing (optional)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key_here
LANGCHAIN_PROJECT=ai-resume-matching
```

### 3. Add datasets

Expected local paths:

- `data/raw/Resume.csv`
- `data/raw/pdfs/`

Primary dataset in the requirement brief:

- `https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset`

### 4. Ingest and index resumes

```bash
python ingestion/embedder.py
```

This pipeline:

1. Loads resumes from CSV and PDF
2. Cleans and validates records
3. Chunks long resumes by section (500-char chunks, 50-char overlap, section-aware)
4. Extracts structured metadata with heuristic mode (zero LLM cost)
5. Generates embeddings with `text-embedding-3-small` (1536-dim)
6. Stores vectors in ChromaDB and builds BM25 index on disk
7. Optionally pre-generate resume summaries: `python ingestion/summarizer.py`

If you enable new metadata extraction settings, re-run ingestion with a fresh index
so the enriched metadata is written into ChromaDB.

## Running the API

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Useful endpoints:

- `GET /health`
- `GET /categories`
- `POST /match`
- `GET /resume/{resume_id}`
- `POST /feedback`
- `GET /analytics`
- `POST /schedule`
- `GET /schedule/{resume_id}`
- `POST /handoff`
- `GET /handoff/{resume_id}`
- Swagger docs: `http://localhost:8000/docs`

## Running the Front End

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to the FastAPI backend on port `8000`.
The dedicated recruiter analytics dashboard is available at `/analytics`.

## Example Query

```text
Information Assurance professional with Risk Management Framework (RMF), Active Directory design, and enterprise platform experience. Project management skills required.
```

For best results, keep queries focused (2-3 sentences). Longer queries cause the skill agent to extract more required skills, increasing the chance of a gate penalty.

Optional advanced filters supported by `POST /match`:

- `filter_category`
- `required_skills`
- `min_years`
- `education_keywords`
- `industry_keywords`
- `location_keywords`

Post-agent gating thresholds are loaded from:

- `config/gating_thresholds.json`

You can also override the file path with:

- `GATING_CONFIG_PATH`

## Example Ranked Output

```json
{
  "job_query": "Python backend engineer with FastAPI and PostgreSQL experience",
  "total_found": 3,
  "candidates": [
    {
      "rank": 1,
      "resume_id": "resume_csv_0123",
      "category": "INFORMATION-TECHNOLOGY",
      "composite_score": 0.812,
      "scores": {
        "skill_score": 0.91,
        "experience_score": 0.74,
        "technical_score": 0.79,
        "culture_score": 0.72
      },
      "matched_skills": ["Python", "FastAPI", "PostgreSQL"],
      "missing_skills": ["Docker"],
      "partial_matches": [],
      "seniority_level": "mid",
      "total_years": 5,
      "tech_stack": ["Python", "FastAPI", "PostgreSQL", "Docker"],
      "soft_skills": ["communication", "collaboration"],
      "explanation": "Matched skills: Python, FastAPI, PostgreSQL. 5 years of experience, mid-level. Tech stack: Python, FastAPI, PostgreSQL, Docker. Soft skills: communication, collaboration. Strong overall match."
    }
  ]
}
```

## Design Notes

Trade-offs implemented in the codebase:

- Embedding model: OpenAI embeddings for strong semantic coverage with low integration overhead
- Chunking strategy: section-aware chunking with recursive fallback for long resumes
- Retrieval: hybrid semantic + BM25 search to recover both contextual and exact-skill matches
- Offline retrieval fallback: set `FORCE_BM25_ONLY=true` to skip semantic retrieval and run BM25-only candidate retrieval in restricted environments
- Reranking: RRF (Reciprocal Rank Fusion, k=60) merges semantic and BM25 ranked lists, then a cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) reranks candidates; falls back to heuristic if `sentence-transformers` is unavailable
- Agent orchestration: LangGraph 6-node pipeline (retrieve → parse → enrich → summarize → evaluate → aggregate) keeps stages modular
- Post-agent screening: query-aware score thresholds penalize or filter candidates with critically low skill, technical, experience, or culture subscores
- Bias mitigation: demographic and biased-hiring phrases are blocked at input-validation time
- Token optimization: resume summarizer compresses text before agent evaluation; shorter culture-fit context (MAX_CULTURE_TEXT_CHARS) and reusable skill extraction further reduce cost
- LLM-as-Judge: DeepEval GEval metric evaluates the quality of generated candidate explanations (enabled with `RUN_LLM_JUDGE=1`)

## Evaluation

DeepEval suite:

```bash
python evaluation/deepeval_tests.py
```

Performance benchmark:

```bash
python evaluation/benchmark.py
```

Gating analysis probe:

```bash
python evaluation/gating_probe.py
python evaluation/gating_probe.py "Python backend engineer with FastAPI"
```

Benchmark summary reports:

- average latency per query
- total time for the benchmark set
- candidates processed per second

## Recruiter Workflow Extensions

- Feedback loop: recruiters can mark a recommendation as helpful or not helpful
- Analytics: the UI sidebar shows aggregate recruiter feedback trends
- Interview scheduling: candidate detail page supports interview round scheduling
- Handoff notes: recruiters can send candidate context to hiring managers from the same detail page

## Deliverables

- Architecture diagram: `docs/architecture_diagram.svg` and `docs/architecture_v2.pdf`
- Full executable microservice: FastAPI backend + React front end
- Explainable ranking output with per-agent score breakdown
- Evaluation suite and benchmark script
