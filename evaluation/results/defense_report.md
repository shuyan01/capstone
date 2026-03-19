# AI Resume Matching System — Evaluation Defense Report

**Run date:** 2026-03-19 07:35:03  
**Test suite:** DeepEval (rule-based + LLM-as-Judge)  
**Overall result: 10 / 10 tests passed ✓**

---

## Overview

This report provides quantitative evidence across **three defense dimensions** to
support the claim that GPT-4o-mini's evaluations inside the pipeline are accurate,
reliable, and production-grade.

| # | Defense Dimension | Result |
|---|---|---|
| 1 | GEval — LLM-as-Judge (GPT-4o judges GPT-4o-mini) | **PASS — mean 0.882 / 1.0** |
| 2 | AnswerRelevancy — Cross-domain output relevance | **PASS — 4 / 4 queries ≥ 0.5** |
| 3 | Benchmark Runner — End-to-end latency & throughput | **PASS — avg 54.8 s / query** |

---

## Dimension 1 — GEval: LLM-as-Judge

**What it tests:** GPT-4o (the judge) independently scores each explanation that
GPT-4o-mini (the candidate model) generated for a top-ranked resume. Four criteria
are evaluated per explanation:
1. Relevance to the job query
2. Specific skill / experience references grounded in the resume
3. Factual consistency with the numeric candidate scores
4. Clear and professional tone

**Setup:**
- Judge model: `gpt-4o` (via DeepEval default)
- Candidate model: `gpt-4o-mini`
- Threshold: 0.5 (scale 0.0 – 1.0)
- Domains tested: IT / Chef / Finance (3 independent queries)

**Results:**

| Domain | Query | Candidate | Composite Score | GEval Score | Status |
|--------|-------|-----------|-----------------|-------------|--------|
| IT | Java full stack developer with Spring Boot and MySQL | resume_csv_0297 | 0.846 | **0.902** | ✓ PASS |
| Chef | Chef with international cuisine and kitchen management | resume_pdf_0609 | 0.446 | **0.884** | ✓ PASS |
| Finance | Financial analyst with Excel modeling and budgeting | resume_pdf_1638 | 0.746 | **0.861** | ✓ PASS |
| | | | **Mean →** | **0.882** | |

**Judge's reasoning (verbatim — GPT-4o critique of GPT-4o-mini output):**

> **IT domain:** "The explanation directly addresses the job query by matching the
> candidate's skills (Java, Spring Boot, MySQL) and experience (5 years, mid-level)
> to the requirements. It references specific skills and relevant roles, and mentions
> a notable project (Test Automation Framework for WebTix), supporting the factual
> basis with candidate scores. The explanation is clear and maintains a professional
> tone."

> **Chef domain:** "The explanation directly addresses the job query by identifying
> the required skills (international cuisine and kitchen management), explicitly noting
> that only kitchen management is matched and international cuisine is missing. It
> references specific experience (15 years, senior-level) and relevant roles, and
> mentions soft skills. The explanation is factually supported by the candidate scores.
> The tone is clear and professional."

> **Finance domain:** "The explanation directly addresses the job query by matching
> the candidate's skills and experience to the requirements of a financial analyst.
> It references specific skills (Financial Analysis, Excel, Budgeting), relevant
> roles, years of experience, and soft skills. The mention of 'Missing: Modeling'
> shows attention to detail and factual support. The explanation is clear and
> professional."

**Defense talking point:**
> *"We do not blindly rely on GPT-4o-mini. The system runs a two-tier evaluation:
> GPT-4o-mini generates the explanations; GPT-4o independently judges them via
> DeepEval GEval. Across three unrelated job domains, GPT-4o gave a mean score of
> 0.882 out of 1.0, confirming that GPT-4o-mini's structured outputs meet
> production-quality standards with high consistency across domains."*

---

## Dimension 2 — AnswerRelevancy: Cross-Domain Output Relevance

**What it tests:** DeepEval `AnswerRelevancyMetric` (backed by GPT-4o) measures
whether the top candidate explanation is topically on-point for the job query.
Four domains are tested (IT / Chef / Finance / HR) to demonstrate cross-domain
robustness — a single-domain result could be coincidence; four passing results
indicate consistent relevance.

**Threshold:** ≥ 0.5 per query (all must pass)

**Results:**

| Domain | Query | Candidate | Relevancy Score | Status |
|--------|-------|-----------|-----------------|--------|
| IT | Java full stack developer with Spring Boot and MySQL | resume_csv_0297 | **0.875** | ✓ PASS |
| Chef | Chef with culinary arts and kitchen management experience | resume_csv_1423 | **0.833** | ✓ PASS |
| Finance | Financial analyst with Excel modeling and budgeting | resume_pdf_1638 | **1.000** | ✓ PASS |
| HR | HR manager with talent acquisition and employee relations | resume_csv_0105 | **0.714** | ✓ PASS |
| | | **Mean →** | **0.856** | |

**GPT-4o relevancy judgements (verbatim):**

> **IT (0.875):** "The answer included information about soft skills, which are not
> directly relevant to the technical requirements of a Java full stack developer.
> However, the main content still addressed the core technical stack requested,
> keeping the score relatively high."

> **Chef (0.833):** "While most of the answer focused on culinary arts and kitchen
> management, there was an irrelevant mention of technical depth score. This unrelated
> detail prevented a higher score, but the main content was still largely relevant."

> **Finance (1.000):** "The answer is fully relevant and directly addresses the
> input with no irrelevant statements."

> **HR (0.714):** "The answer addresses some relevant aspects, but includes
> subjective match assessments and technical depth that are not directly related
> to HR management, talent acquisition, or employee relations."

**Defense talking point:**
> *"Using DeepEval's AnswerRelevancyMetric — where GPT-4o independently rates
> relevance — GPT-4o-mini's explanations scored a mean of 0.856 across four
> unrelated job domains. Every query cleared the 0.5 threshold. This shows that
> after query expansion and structured summarization, the model consistently
> captures the core requirements of the JD and returns highly relevant results."*

---

## Dimension 3 — Benchmark Runner: End-to-End Latency & Throughput

**What it tests:** Wall-clock time for the complete 6-node LangGraph pipeline,
measured across 3 representative queries. Each pipeline run includes:
- Vector (ChromaDB) + BM25 hybrid retrieval
- RRF fusion (k=60)
- Cross-encoder reranking (ms-marco-MiniLM-L-6-v2)
- 4 LLM agent calls per candidate: Skill / Experience / Technical / Culture Fit
- Score aggregation and ranking

**Configuration:** top_k = 5 candidates per query (= 20 LLM agent calls per query)

**Results:**

| Domain | Query | Latency (s) | Candidates | Throughput (c/s) |
|--------|-------|-------------|------------|------------------|
| IT | Java full stack developer with Spring Boot and MySQL | 47.22 | 5 | 0.1059 |
| Chef | Chef with international cuisine and kitchen management | 50.42 | 5 | 0.0992 |
| Finance | Financial analyst with Excel modeling and budgeting | 66.66 | 5 | 0.0750 |

**Summary:**

| Metric | Value |
|--------|-------|
| Average query latency | **54.8 s** |
| Minimum latency | 47.2 s |
| Maximum latency | 66.7 s |
| Total candidates processed | 15 (3 queries × 5) |
| Overall throughput | **0.091 candidates / second** |
| Pass threshold (avg latency) | ≤ 300 s ✓ |

**Defense talking point:**
> *"Our benchmark shows an average end-to-end latency of 54.8 seconds per query.
> This includes 20 individual GPT-4o-mini API calls (4 agents × 5 candidates),
> cross-encoder reranking over 4,966 resumes, and score aggregation. For the
> intended use case — an HR team screening candidates for a role — a sub-60-second
> turnaround per search is well within acceptable bounds. Throughput is 0.091
> candidates/second across domains."*

---

## Supporting Test Results (All Other Suites)

The following rule-based tests provide additional corroboration that the pipeline
behaves correctly end-to-end, independent of any LLM evaluation:

| Test Suite | What It Checks | Result |
|------------|----------------|--------|
| Skill Coverage | Top candidate matches ≥1 required skill | **3/3 queries passed — skill_score = 1.0 on all** |
| Experience Fit | Top candidates meet minimum years of experience | **3/3 queries passed** |
| Ranking Quality | Results sorted by composite score (descending) | **3/3 queries sorted correctly** |
| Diversity | Two different queries return ≤20% overlapping candidates | **0% overlap (0 shared IDs)** |
| Guardrails (invalid) | Rejects empty / vague / biased / harmful queries | **5/5 blocked** |
| Guardrails (valid) | Does not block legitimate job queries | **3/3 accepted** |
| Culture Match | Soft-skill queries surface candidates with culture signal | **2/2 queries: culture_score = 0.72** |

---

*Source data: `evaluation/results/2026-03-19_07-35-03.json`*  
*Test framework: [DeepEval](https://docs.confident-ai.com/) v1.x*  
*Pipeline: LangGraph 6-node, ChromaDB + BM25 + RRF + Cross-Encoder*
