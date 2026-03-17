# AI Resume Intelligence and Candidate Matching System

This project matches recruiter-written job descriptions to resumes using hybrid retrieval, a multi-agent evaluation pipeline, and explainable ranking output.

## Features

- Hybrid candidate retrieval with ChromaDB semantic search and BM25 keyword search
- Optional cross-encoder reranking with heuristic fallback when model dependencies are unavailable
- Multi-agent evaluation for skills, experience, technical depth, and culture fit
- Post-agent gating so one strong dimension does not hide a critical weak dimension
- Recruiter filters for category, required skills, years of experience, education, industry, and location
- Recruiter feedback loop with analytics, interview scheduling, and handoff notes
- FastAPI service with Swagger docs
- React front end for search and candidate review
- Evaluation suite with DeepEval metrics and a lightweight benchmark runner

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
METADATA_EXTRACTION_MODE=hybrid
METADATA_MODEL=gpt-4o-mini
METADATA_CACHE_PATH=./data/processed/metadata_cache.json
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
3. Chunks long resumes by section
4. Extracts structured metadata with heuristic + cached LLM enrichment
5. Generates embeddings
6. Stores vectors in ChromaDB and BM25 index on disk

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
We are looking for a Python backend engineer with FastAPI, PostgreSQL, and Docker experience who can collaborate with product and client teams.
```

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
- Reranking: cross-encoder hook is wired into retrieval, but falls back to a deterministic heuristic in environments without local model dependencies
- Agent orchestration: LangGraph pipeline keeps retrieval, evaluation, and ranking stages modular
- Post-agent screening: query-aware score thresholds penalize or filter candidates with critically low skill, technical, experience, or culture subscores
- Bias mitigation: demographic and biased-hiring phrases are blocked at input-validation time
- Token optimization: shorter culture-fit context and reusable skill extraction reduce LLM cost

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

- Architecture diagram: `docs/architecture_diagram.svg`
- Full executable microservice: FastAPI backend + React front end
- Explainable ranking output with per-agent score breakdown
- Evaluation suite and benchmark script
