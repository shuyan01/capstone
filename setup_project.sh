#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# AI Resume Matching System — Project Scaffold Script
# Run this from inside: /Users/suyan/Prodapt FDE Traning/Capstone/ai_resume_matching_system
# Usage: bash setup_project.sh
# ─────────────────────────────────────────────────────────────────

echo "Setting up AI Resume Matching System project structure..."

# ── Directories ────────────────────────────
mkdir -p data/raw
mkdir -p data/processed
mkdir -p ingestion
mkdir -p retrieval
mkdir -p agents
mkdir -p scoring
mkdir -p api
mkdir -p evaluation
mkdir -p guardrails
mkdir -p chroma_db

# ── Ingestion module ───────────────────────
touch ingestion/__init__.py
touch ingestion/parser.py
touch ingestion/chunker.py
touch ingestion/embedder.py

# ── Retrieval module ───────────────────────
touch retrieval/__init__.py
touch retrieval/vector_store.py
touch retrieval/keyword_search.py
touch retrieval/hybrid_retriever.py

# ── Agents module ──────────────────────────
touch agents/__init__.py
touch agents/orchestrator.py
touch agents/skill_matching_agent.py
touch agents/experience_agent.py
touch agents/technical_agent.py
touch agents/culture_fit_agent.py

# ── Scoring module ─────────────────────────
touch scoring/__init__.py
touch scoring/aggregator.py
touch scoring/explainer.py

# ── API module ─────────────────────────────
touch api/__init__.py
touch api/main.py
touch api/routes.py
touch api/schemas.py

# ── Evaluation module ──────────────────────
touch evaluation/__init__.py
touch evaluation/deepeval_tests.py

# ── Guardrails module ──────────────────────
touch guardrails/__init__.py
touch guardrails/input_validator.py
touch guardrails/resume_validator.py

# ── Root files ─────────────────────────────
touch README.md

echo ""
echo "✓ Project structure created successfully!"
echo ""
echo "Next steps:"
echo "  1. Activate your virtual environment:"
echo "     source capstone/bin/activate"
echo ""
echo "  2. Install dependencies:"
echo "     pip install -r requirements.txt"
echo ""
echo "  3. Set up your environment file:"
echo "     cp .env.template .env"
echo "     # Then open .env and add your OPENAI_API_KEY"
echo ""
echo "  4. Download the Kaggle dataset into data/raw/"
echo "     https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset"
