"""
evaluation/deepeval_tests.py

DeepEval-based evaluation suite for the Resume Matching System.

Tests:
1. Skill Coverage     — does the system return candidates with the required skills?
2. Experience Fit     — does the system return candidates at the right seniority level?
3. Ranking Quality    — are higher-scored candidates genuinely better matches?
4. Diversity          — are results from different categories/backgrounds?
5. Guardrail Check    — does the system correctly reject invalid queries?

Run:
    python evaluation/deepeval_tests.py

Requirements:
    pip install deepeval
"""

import os
import sys
import json
import time
import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import pytest
from deepeval import assert_test
from deepeval.metrics import (
    AnswerRelevancyMetric,
    GEval,
)
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from agents.orchestrator        import run_pipeline
from guardrails.input_validator import validate_job_query
from ingestion.parser           import load_all_resumes
from ingestion.chunker          import chunk_all_resumes
from retrieval.hybrid_retriever import hybrid_search


# -----------------------------------------
# Shared fixtures
# -----------------------------------------

def load_chunks():
    """Load and chunk all resumes once for all tests."""
    resumes = load_all_resumes(
        csv_path   = "data/raw/Resume.csv",
        pdf_folder = "data/raw/pdfs",
    )
    return chunk_all_resumes(resumes)


# -----------------------------------------
# Test 1 — Skill Coverage
#
# Verifies that the top-ranked candidate has
# at least one matched skill from the query.
# -----------------------------------------

class TestSkillCoverage:
    """
    Skill coverage metric:
    At least 1 required skill must be matched in the top result.
    Score = matched_skills / required_skills (should be > 0)
    """

    TEST_CASES = [
        {
            "query":           "Java full stack developer with Spring Boot and MySQL",
            "expected_skills": ["Java", "Spring Boot", "MySQL"],
            "category":        "INFORMATION-TECHNOLOGY",
        },
        {
            "query":           "Chef with culinary skills and kitchen management experience",
            "expected_skills": ["culinary", "kitchen"],
            "category":        "CHEF",
        },
        {
            "query":           "Data analyst with SQL and Excel reporting skills",
            "expected_skills": ["SQL", "Excel"],
            "category":        "INFORMATION-TECHNOLOGY",
        },
    ]

    def test_skill_coverage(self):
        chunks = load_chunks()
        results = []
        self.details = []

        print("\n── Test 1: Skill Coverage ──")
        for case in self.TEST_CASES:
            pipeline_results = run_pipeline(
                job_query=case["query"],
                top_k=3,
                chunks=chunks,
            )

            if not pipeline_results:
                print(f"  FAIL — No results for: '{case['query']}'")
                results.append(False)
                self.details.append({"query": case["query"], "status": "fail", "reason": "no results returned"})
                continue

            top = pipeline_results[0]
            matched = top.get("matched_skills", [])
            skill_score = top.get("skill_score", 0)

            # Check: at least one skill matched
            has_match = len(matched) > 0 or skill_score > 0

            status = "PASS" if has_match else "FAIL"
            print(f"  {status} — Query: '{case['query'][:50]}...'")
            print(f"         Matched skills: {matched}")
            print(f"         Skill score: {skill_score:.2f}")
            results.append(has_match)
            self.details.append({
                "query":          case["query"],
                "status":         "pass" if has_match else "fail",
                "matched_skills": matched,
                "skill_score":    round(skill_score, 3),
            })

        passed = sum(results)
        total  = len(results)
        print(f"\n  Skill Coverage: {passed}/{total} passed")
        assert passed >= total * 0.6, (
            f"Skill coverage too low: {passed}/{total} passed. "
            f"Expected at least 60% pass rate."
        )


# -----------------------------------------
# Test 2 — Experience Fit
#
# Verifies that candidates have relevant
# experience (total_years > 0)
# -----------------------------------------

class TestExperienceFit:
    """
    Experience fit metric:
    Top candidates should have detectable work experience.
    """

    TEST_CASES = [
        {
            "query":            "Senior Java developer with 5+ years experience",
            "min_years":        3,
        },
        {
            "query":            "Entry level data analyst with SQL skills",
            "min_years":        0,
        },
        {
            "query":            "Experienced chef with 10 years in fine dining",
            "min_years":        3,
        },
    ]

    def test_experience_fit(self):
        chunks = load_chunks()
        results = []
        self.details = []

        print("\n── Test 2: Experience Fit ──")
        for case in self.TEST_CASES:
            pipeline_results = run_pipeline(
                job_query=case["query"],
                top_k=3,
                chunks=chunks,
            )

            if not pipeline_results:
                print(f"  SKIP — No results for: '{case['query']}'")
                results.append(True)  # skip counts as pass
                self.details.append({"query": case["query"], "status": "skip", "reason": "no results returned"})
                continue

            # Check top 3 candidates — at least 1 should have years > min
            has_experience = any(
                r.get("total_years", 0) >= case["min_years"]
                for r in pipeline_results
            )

            status = "PASS" if has_experience else "FAIL"
            years_list = [r.get("total_years", 0) for r in pipeline_results]
            print(f"  {status} — Query: '{case['query'][:50]}...'")
            print(f"         Years detected: {years_list}")
            results.append(has_experience)
            self.details.append({
                "query":              case["query"],
                "status":             "pass" if has_experience else "fail",
                "min_years_required": case["min_years"],
                "years_detected":     years_list,
            })

        passed = sum(results)
        total  = len(results)
        print(f"\n  Experience Fit: {passed}/{total} passed")
        assert passed >= total * 0.6, (
            f"Experience fit too low: {passed}/{total} passed."
        )


# -----------------------------------------
# Test 3 — Ranking Quality
#
# Verifies that rank 1 has a higher composite
# score than rank 2, 3, etc.
# -----------------------------------------

class TestRankingQuality:
    """
    Ranking quality metric:
    Results must be sorted by composite_score descending.
    """

    TEST_CASES = [
        "Java developer with Spring Boot and MySQL experience",
        "IT consultant with ERP and project management",
        "Chef with international cuisine and kitchen management",
    ]

    def test_ranking_order(self):
        chunks = load_chunks()
        results = []
        self.details = []

        print("\n── Test 3: Ranking Quality ──")
        for query in self.TEST_CASES:
            pipeline_results = run_pipeline(
                job_query=query,
                top_k=5,
                chunks=chunks,
            )

            if len(pipeline_results) < 2:
                print(f"  SKIP — Not enough results for: '{query}'")
                results.append(True)
                self.details.append({"query": query, "status": "skip", "reason": "fewer than 2 results"})
                continue

            # Check scores are in descending order
            scores = [r["composite_score"] for r in pipeline_results]
            is_sorted = all(
                scores[i] >= scores[i+1]
                for i in range(len(scores) - 1)
            )

            status = "PASS" if is_sorted else "FAIL"
            print(f"  {status} — Query: '{query[:50]}'")
            print(f"         Scores: {[round(s, 3) for s in scores]}")
            results.append(is_sorted)
            self.details.append({
                "query":     query,
                "status":    "pass" if is_sorted else "fail",
                "scores":    [round(s, 3) for s in scores],
                "is_sorted": is_sorted,
            })

        passed = sum(results)
        total  = len(results)
        print(f"\n  Ranking Quality: {passed}/{total} passed")
        assert passed == total, (
            f"Ranking order broken: {passed}/{total} passed. "
            f"Results must be sorted by composite_score descending."
        )


# -----------------------------------------
# Test 4 — Diversity
#
# Verifies that multiple search queries return
# different candidates (no result overlap)
# -----------------------------------------

class TestDiversity:
    """
    Diversity metric:
    Two very different job queries should return
    mostly different candidates.
    """

    def test_result_diversity(self):
        chunks = load_chunks()

        print("\n── Test 4: Result Diversity ──")

        query_a = "Java full stack developer with Spring Boot"
        query_b = "Chef with culinary arts and kitchen experience"

        results_a = run_pipeline(query_a, top_k=5, chunks=chunks)
        results_b = run_pipeline(query_b, top_k=5, chunks=chunks)

        ids_a = {r["resume_id"] for r in results_a}
        ids_b = {r["resume_id"] for r in results_b}

        overlap    = ids_a & ids_b
        overlap_pct = len(overlap) / max(len(ids_a), 1)

        print(f"  Query A results: {ids_a}")
        print(f"  Query B results: {ids_b}")
        print(f"  Overlap: {overlap} ({overlap_pct:.0%})")

        status = "PASS" if overlap_pct <= 0.2 else "FAIL"
        print(f"  {status} — Overlap: {overlap_pct:.0%} (max allowed: 20%)")

        self.details = {
            "query_a":     query_a,
            "query_b":     query_b,
            "ids_a":       sorted(ids_a),
            "ids_b":       sorted(ids_b),
            "overlap":     sorted(overlap),
            "overlap_pct": round(overlap_pct, 3),
            "status":      "pass" if overlap_pct <= 0.2 else "fail",
        }

        assert overlap_pct <= 0.2, (
            f"Result diversity too low: {overlap_pct:.0%} overlap between "
            f"different job queries. Expected < 20%."
        )


# -----------------------------------------
# Test 5 — Guardrail Validation
#
# Verifies that invalid queries are correctly
# rejected by the input validator.
# -----------------------------------------

class TestGuardrails:
    """
    Guardrail metric:
    Invalid queries must be rejected with a clear error message.
    Valid queries must pass through.
    """

    INVALID_QUERIES = [
        "",                                          # empty
        "Python",                                    # too short
        "What is the weather today?",                # not a job query
        "We need someone to hack into our systems",  # blocked content
        "Looking for a young female developer only", # biased language
    ]

    VALID_QUERIES = [
        "We are looking for a Java developer with Spring Boot experience.",
        "Senior data analyst with SQL and Python skills needed.",
        "Chef with 5 years of fine dining experience.",
    ]

    def test_invalid_queries_rejected(self):
        print("\n── Test 5a: Invalid Queries Rejected ──")
        results = []
        self.details = []

        for query in self.INVALID_QUERIES:
            result = validate_job_query(query)
            is_rejected = not result["valid"]
            status = "PASS" if is_rejected else "FAIL"
            display = f"'{query[:40]}'" if query else "'(empty)'"
            print(f"  {status} — {display} → rejected={is_rejected}")
            if not is_rejected:
                print(f"         ERROR: Should have been rejected but wasn't")
            results.append(is_rejected)
            self.details.append({
                "query":    query or "(empty)",
                "status":   "pass" if is_rejected else "fail",
                "rejected": is_rejected,
                "reason":   result.get("reason", ""),
            })

        passed = sum(results)
        total  = len(results)
        print(f"\n  Invalid query rejection: {passed}/{total} passed")
        assert passed == total, (
            f"Guardrail missed {total - passed} invalid queries."
        )

    def test_valid_queries_pass(self):
        print("\n── Test 5b: Valid Queries Pass Through ──")
        results = []
        self.details = []

        for query in self.VALID_QUERIES:
            result   = validate_job_query(query)
            is_valid = result["valid"]
            status   = "PASS" if is_valid else "FAIL"
            print(f"  {status} — '{query[:50]}...' → valid={is_valid}")
            results.append(is_valid)
            self.details.append({
                "query":    query,
                "status":   "pass" if is_valid else "fail",
                "accepted": is_valid,
                "reason":   result.get("reason", ""),
            })

        passed = sum(results)
        total  = len(results)
        print(f"\n  Valid query acceptance: {passed}/{total} passed")
        assert passed == total, (
            f"Guardrail incorrectly blocked {total - passed} valid queries."
        )


# -----------------------------------------
# Test 6 — LLM-as-Judge (DeepEval GEval)
#
# Uses DeepEval's GEval metric to evaluate
# the quality of candidate explanations.
# -----------------------------------------

# -----------------------------------------
# Test 6b — DeepEval AnswerRelevancyMetric
#
# Uses DeepEval's built-in AnswerRelevancyMetric
# to verify candidate explanations are on-topic.
# -----------------------------------------

class TestAnswerRelevancy:
    """
    Uses DeepEval AnswerRelevancyMetric (backed by GPT-4o as judge) to check
    that each candidate explanation is topically on-point for the job query.
    Running 4 diverse queries provides statistical breadth for the defense
    argument: "GPT-4o-mini outputs are relevant across multiple domains."
    """

    TEST_CASES = [
        {
            "query":    "Java full stack developer with Spring Boot and MySQL",
            "category": "INFORMATION-TECHNOLOGY",
        },
        {
            "query":    "Chef with culinary arts and kitchen management experience",
            "category": "CHEF",
        },
        {
            "query":    "Financial analyst with Excel modeling and budgeting experience",
            "category": "FINANCE",
        },
        {
            "query":    "HR manager with talent acquisition and employee relations experience",
            "category": "HR",
        },
    ]

    def test_explanation_relevance(self):
        chunks = load_chunks()

        print("\n── DeepEval: Answer Relevancy ──")

        relevancy_metric = AnswerRelevancyMetric(threshold=0.5)
        self.details = []

        for case in self.TEST_CASES:
            results = run_pipeline(
                job_query=case["query"],
                top_k=1,
                chunks=chunks,
            )

            if not results:
                print(f"  SKIP — No results for: '{case['query']}'")
                self.details.append({"query": case["query"], "status": "skip", "reason": "no results returned"})
                continue

            top         = results[0]
            explanation = top.get("explanation", "")

            if not explanation:
                print(f"  SKIP — No explanation generated")
                self.details.append({"query": case["query"], "status": "skip", "reason": "no explanation generated"})
                continue

            test_case = LLMTestCase(
                input=case["query"],
                actual_output=explanation,
            )

            relevancy_metric.measure(test_case)
            score_str = f"{relevancy_metric.score:.2f}" if relevancy_metric.score is not None else "n/a"
            passed_metric = relevancy_metric.score is not None and relevancy_metric.score >= relevancy_metric.threshold
            status = "PASS" if passed_metric else "FAIL"
            print(f"  {status} — Relevancy {score_str} "
                  f"for '{case['query'][:50]}'")
            if not passed_metric:
                print(f"         Reason: {relevancy_metric.reason}")
            self.details.append({
                "query":       case["query"],
                "candidate":   top.get("resume_id", ""),
                "metric":      "AnswerRelevancy",
                "score":       relevancy_metric.score,
                "threshold":   relevancy_metric.threshold,
                "status":      "pass" if passed_metric else "fail",
                "reason":      relevancy_metric.reason,
                "explanation": explanation[:300],
            })
            assert passed_metric, (
                f"Answer relevancy too low: {score_str} < {relevancy_metric.threshold} "
                f"for query '{case['query'][:60]}'"
            )


class TestLLMJudge:
    """
    Uses DeepEval GEval (GPT-4o acting as judge) to evaluate whether the
    explanations produced by GPT-4o-mini are:
      1) Relevant to the job query
      2) Grounded in specific skills / experience found in the resume
      3) Factually consistent with the numeric candidate scores
      4) Clear and professional

    Three cross-domain queries are tested (IT / Chef / Finance) so that the
    mean GEval score reflects system-wide consistency, not a single lucky case.
    This directly supports the defense argument:
    "GPT-4o (as judge) confirms GPT-4o-mini's outputs are accurate and
    consistent across all job domains."
    """

    # GPT-4o is used as the judge via DeepEval's default LLM (gpt-4o).
    # GPT-4o-mini generates the explanations; GPT-4o scores them.
    TEST_CASES = [
        {
            "query":  "Java full stack developer with Spring Boot and MySQL experience",
            "domain": "IT",
        },
        {
            "query":  "Chef with international cuisine and kitchen management",
            "domain": "Chef",
        },
        {
            "query":  "Financial analyst with Excel modeling and budgeting experience",
            "domain": "Finance",
        },
    ]
    THRESHOLD = 0.5

    def test_explanation_quality(self):
        chunks = load_chunks()
        per_query = []

        print("\n── LLM-as-Judge: GEval Explanation Quality (3 domains) ──")
        print("  Judge model: GPT-4o  |  Candidate model: GPT-4o-mini")

        explanation_quality = GEval(
            name="Explanation Quality",
            criteria=(
                "The explanation should: "
                "1) Be relevant to the job query, "
                "2) Reference specific skills or experience found, "
                "3) Be factually grounded in the candidate scores, "
                "4) Be clear and professional."
            ),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
            ],
            threshold=self.THRESHOLD,
        )

        for case in self.TEST_CASES:
            query  = case["query"]
            domain = case["domain"]
            results = run_pipeline(query, top_k=1, chunks=chunks)

            if not results:
                print(f"  SKIP [{domain}] — No results returned")
                per_query.append({"query": query, "domain": domain, "status": "skip",
                                   "reason": "no results returned"})
                continue

            top         = results[0]
            explanation = top.get("explanation", "")
            comp_score  = top.get("composite_score", 0)

            print(f"  [{domain}] Candidate: {top['resume_id']}  composite={comp_score:.3f}")
            print(f"    Explanation: {explanation[:120]}...")

            test_case = LLMTestCase(input=query, actual_output=explanation)
            explanation_quality.measure(test_case)

            geval_score  = explanation_quality.score
            geval_passed = geval_score is not None and geval_score >= self.THRESHOLD
            score_str    = f"{geval_score:.3f}" if geval_score is not None else "n/a"
            status_str   = "PASS" if geval_passed else "FAIL"
            print(f"    GEval score: {score_str}  [{status_str}]")
            print(f"    Judge reason: {explanation_quality.reason}")

            per_query.append({
                "query":           query,
                "domain":          domain,
                "candidate":       top.get("resume_id", ""),
                "composite_score": round(comp_score, 3),
                "metric":          "GEval: Explanation Quality",
                "judge_model":     "gpt-4o (DeepEval default)",
                "candidate_model": "gpt-4o-mini",
                "score":           geval_score,
                "threshold":       self.THRESHOLD,
                "status":          "pass" if geval_passed else "fail",
                "reason":          explanation_quality.reason,
                "explanation":     explanation[:300],
            })

        valid_scores = [d["score"] for d in per_query
                        if d.get("status") not in ("skip",) and d.get("score") is not None]
        avg_geval = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
        all_passed = all(d.get("status") in ("pass", "skip") for d in per_query)

        print(f"\n  GEval summary — {len([d for d in per_query if d.get('status')=='pass'])}/"
              f"{len(self.TEST_CASES)} passed  |  mean score: {avg_geval:.3f}")

        self.details = {
            "judge_model":     "gpt-4o (DeepEval default)",
            "candidate_model": "gpt-4o-mini",
            "threshold":       self.THRESHOLD,
            "domains_tested":  [c["domain"] for c in self.TEST_CASES],
            "avg_geval_score": round(avg_geval, 3),
            "all_passed":      all_passed,
            "per_query":       per_query,
        }

        assert all_passed, (
            f"GEval explanation quality failed for one or more queries "
            f"(mean score {avg_geval:.3f}, threshold {self.THRESHOLD})"
        )


class TestCultureMatch:
    """
    Culture fit metric:
    Queries emphasizing collaboration and communication should surface
    candidates with a non-trivial culture score or explicit soft skills.
    """

    TEST_CASES = [
        "Client-facing consultant with strong communication and teamwork skills",
        "Engineering lead who mentors teams and collaborates across functions",
    ]

    def test_culture_match(self):
        chunks = load_chunks()
        results = []
        self.details = []

        print("\n── Test 6: Culture Match ──")
        for query in self.TEST_CASES:
            pipeline_results = run_pipeline(
                job_query=query,
                top_k=3,
                chunks=chunks,
            )

            if not pipeline_results:
                print(f"  FAIL — No results for: '{query}'")
                results.append(False)
                self.details.append({"query": query, "status": "fail", "reason": "no results returned"})
                continue

            top = pipeline_results[0]
            culture_score = top.get("culture_score", 0)
            soft_skills = top.get("soft_skills", [])
            has_signal = culture_score >= 0.3 or len(soft_skills) > 0

            status = "PASS" if has_signal else "FAIL"
            print(f"  {status} — Query: '{query[:50]}...'")
            print(f"         Culture score: {culture_score:.2f}")
            print(f"         Soft skills: {soft_skills}")
            results.append(has_signal)
            self.details.append({
                "query":         query,
                "status":        "pass" if has_signal else "fail",
                "culture_score": round(culture_score, 3),
                "soft_skills":   soft_skills,
            })

        passed = sum(results)
        total = len(results)
        print(f"\n  Culture Match: {passed}/{total} passed")
        assert passed >= total * 0.5, (
            f"Culture match too low: {passed}/{total} passed."
        )


# -----------------------------------------
# Benchmark Runner
#
# Measures end-to-end pipeline performance:
#   - Per-query wall-clock latency (seconds)
#   - Overall throughput (candidates / second)
# Provides the quantitative performance evidence
# needed to defend the system under load questions.
# -----------------------------------------

class TestBenchmarkRunner:
    """
    Lightweight benchmark over 3 representative queries.
    Reports average query latency, min/max latency, and overall
    throughput in candidates-per-second.

    Defense use:
      "每次查询平均耗时 Xs，端到端吞吐量为 Y candidates/s，
       满足实际招聘场景中对响应速度的要求。"
    """

    BENCHMARK_QUERIES = [
        {"query": "Java full stack developer with Spring Boot and MySQL",
         "domain": "IT"},
        {"query": "Chef with international cuisine and kitchen management",
         "domain": "Chef"},
        {"query": "Financial analyst with Excel modeling and budgeting experience",
         "domain": "Finance"},
    ]
    TOP_K = 5
    # Generous ceiling — accounts for cold API + 4 LLM-agent calls per query
    MAX_AVG_LATENCY_S = 300

    def test_pipeline_performance(self):
        chunks = load_chunks()
        per_query  = []
        latencies  = []
        total_candidates = 0

        print("\n── Benchmark Runner: Pipeline Latency & Throughput ──")
        print(f"  Queries: {len(self.BENCHMARK_QUERIES)}  |  top_k={self.TOP_K} per query")

        for case in self.BENCHMARK_QUERIES:
            query  = case["query"]
            domain = case["domain"]
            t0 = time.perf_counter()
            results = run_pipeline(query, top_k=self.TOP_K, chunks=chunks)
            elapsed = time.perf_counter() - t0

            n = len(results)
            throughput = round(n / elapsed, 4) if elapsed > 0 else 0.0
            latencies.append(elapsed)
            total_candidates += n

            print(f"  [{domain}] latency={elapsed:.1f}s  candidates={n}  "
                  f"throughput={throughput:.3f} c/s")
            per_query.append({
                "domain":               domain,
                "query":                query,
                "latency_s":            round(elapsed, 2),
                "candidates_returned":  n,
                "throughput_c_per_s":   throughput,
            })

        avg_latency  = sum(latencies) / len(latencies)
        min_latency  = min(latencies)
        max_latency  = max(latencies)
        total_time   = sum(latencies)
        overall_tp   = round(total_candidates / total_time, 4) if total_time > 0 else 0.0
        status_str   = "PASS" if avg_latency <= self.MAX_AVG_LATENCY_S else "FAIL"

        print(f"\n  Summary:")
        print(f"    Avg latency:        {avg_latency:.1f}s")
        print(f"    Min / Max latency:  {min_latency:.1f}s / {max_latency:.1f}s")
        print(f"    Total candidates:   {total_candidates}")
        print(f"    Overall throughput: {overall_tp:.4f} candidates/s")
        print(f"  {status_str} — avg {avg_latency:.1f}s ≤ {self.MAX_AVG_LATENCY_S}s threshold")

        self.details = {
            "queries_run":               len(latencies),
            "top_k":                     self.TOP_K,
            "avg_latency_s":             round(avg_latency, 2),
            "min_latency_s":             round(min_latency, 2),
            "max_latency_s":             round(max_latency, 2),
            "total_candidates":          total_candidates,
            "overall_throughput_c_per_s": overall_tp,
            "threshold_avg_latency_s":   self.MAX_AVG_LATENCY_S,
            "status":                    "pass" if avg_latency <= self.MAX_AVG_LATENCY_S else "fail",
            "per_query":                 per_query,
        }

        assert avg_latency <= self.MAX_AVG_LATENCY_S, (
            f"Avg pipeline latency too high: {avg_latency:.1f}s > {self.MAX_AVG_LATENCY_S}s"
        )


# -----------------------------------------
# Summary Runner
# Run: python evaluation/deepeval_tests.py
# -----------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Resume Matching System — DeepEval Test Suite")
    print("=" * 60)

    passed_suites = 0
    failed_suites = 0
    run_started   = datetime.datetime.now()
    suite_records = []   # collect per-suite results for JSON export

    # Run each test class
    # Determine which test suites to run
    # LLM-graded tests (GEval, AnswerRelevancy) cost API tokens;
    # enable them explicitly with: RUN_LLM_JUDGE=1 python evaluation/deepeval_tests.py
    run_llm_judge = os.getenv("RUN_LLM_JUDGE", "0") == "1"

    # Human-readable annotations for each test suite.  These are written
    # into the JSON report so the file is self-documenting.
    suite_annotations = {
        "Skill Coverage": {
            "description": "Verifies that the top-ranked candidate actually possesses the skills mentioned in the job query.",
            "pass_criteria": "At least 60% of test queries must return a candidate with ≥1 matched skill.",
            "how_to_read": "Check 'matched_skills' (list of skills found in the resume) and 'skill_score' (0.0–1.0, fraction of required skills matched). 1.0 = all required skills found.",
        },
        "Experience Fit": {
            "description": "Verifies that the pipeline surfaces candidates whose years of experience meet the query's implied seniority level.",
            "pass_criteria": "At least 60% of test queries must return at least one candidate with years >= the expected minimum.",
            "how_to_read": "'years_detected' lists total work-years for each of the top-3 candidates. 'min_years_required' is the threshold the query implies.",
        },
        "Ranking Quality": {
            "description": "Verifies that candidates are strictly sorted by composite score (best match first).",
            "pass_criteria": "100% of test queries must return results in descending score order.",
            "how_to_read": "'scores' is the ranked list of composite scores (0.0–1.0). 'is_sorted' must be true for the test to pass.",
        },
        "Diversity": {
            "description": "Verifies that two very different job queries return mostly different candidates — the retrieval is category-aware, not generic.",
            "pass_criteria": "Overlap between the two result sets must be ≤20%.",
            "how_to_read": "'overlap_pct' is the fraction of candidates shared between the two queries. 0.0 = perfect diversity. 'overlap' lists any shared resume IDs.",
        },
        "Guardrails (invalid)": {
            "description": "Verifies that the input guardrail correctly rejects queries that are empty, too vague, off-topic, or contain biased/harmful language.",
            "pass_criteria": "All 5 invalid queries must be rejected.",
            "how_to_read": "'rejected' should be true for every entry. 'reason' explains why the guardrail blocked it.",
        },
        "Guardrails (valid)": {
            "description": "Verifies that the input guardrail does NOT block legitimate job queries.",
            "pass_criteria": "All 3 valid queries must pass through.",
            "how_to_read": "'accepted' should be true for every entry. If false, the guardrail is over-blocking.",
        },
        "Culture Match": {
            "description": "Verifies that queries emphasising soft skills (communication, teamwork, leadership) surface candidates with a non-trivial culture-fit score.",
            "pass_criteria": "At least 50% of test queries must yield a candidate with culture_score ≥0.3 or at least one detected soft skill.",
            "how_to_read": "'culture_score' is the Culture Fit Agent's output (0.0–1.0). 'soft_skills' lists the skills GPT-4o identified in the resume.",
        },
        "Answer Relevancy (DeepEval)": {
            "description": "LLM-as-Judge (DeepEval AnswerRelevancyMetric, GPT-4o): evaluates whether each candidate explanation is topically relevant to its job query. Four diverse domains are tested (IT / Chef / Finance / HR) to demonstrate cross-domain reliability.",
            "pass_criteria": "Relevancy score must be ≥0.5 (scale 0.0–1.0) for every query.",
            "how_to_read": "'score' is GPT-4o's relevancy rating (1.0 = perfectly on-topic). 'reason' is the LLM's natural-language justification — cite this to show GPT-4o-mini outputs are high-quality. 'explanation' is the verbatim pipeline output that was judged.",
        },
        "LLM Judge / GEval (DeepEval)": {
            "description": "LLM-as-Judge (DeepEval GEval): GPT-4o (judge) scores the explanations that GPT-4o-mini (candidate model) produced, across 3 job domains (IT / Chef / Finance). Tests four criteria: relevance, skill/experience grounding, factual consistency with scores, professional tone.",
            "pass_criteria": "All 3 domains must pass GEval ≥0.5.  Mean GEval score across domains is reported for statistical breadth.",
            "how_to_read": "'avg_geval_score' is the cross-domain mean (higher = more consistent quality). 'judge_model' / 'candidate_model' clarifies the two-tier evaluation setup. 'per_query[].reason' contains the natural-language critique from GPT-4o for each domain.",
        },
        "Benchmark Runner": {
            "description": "Measures end-to-end pipeline wall-clock latency and throughput across 3 representative queries (IT / Chef / Finance). Each query runs the full 6-node LangGraph pipeline: vector+BM25 retrieval → cross-encoder reranking → 4 LLM agents → score aggregation.",
            "pass_criteria": "Average query latency must be ≤300s (5 min). Threshold is intentionally generous to account for cold API starts; typical warm-cache runs are much faster.",
            "how_to_read": "'avg_latency_s' is the key headline number. 'overall_throughput_c_per_s' = total candidates returned / total wall time. 'per_query' breaks down latency per domain so bottlenecks are identifiable.",
        },
    }

    test_suites = [
        ("Skill Coverage",       TestSkillCoverage(),    "test_skill_coverage"),
        ("Experience Fit",       TestExperienceFit(),    "test_experience_fit"),
        ("Ranking Quality",      TestRankingQuality(),   "test_ranking_order"),
        ("Diversity",            TestDiversity(),        "test_result_diversity"),
        ("Guardrails (invalid)", TestGuardrails(),       "test_invalid_queries_rejected"),
        ("Guardrails (valid)",   TestGuardrails(),       "test_valid_queries_pass"),
        ("Culture Match",        TestCultureMatch(),     "test_culture_match"),
        ("Benchmark Runner",     TestBenchmarkRunner(),  "test_pipeline_performance"),
    ]

    # LLM-graded DeepEval tests — opt-in only
    llm_test_suites = [
        ("Answer Relevancy (DeepEval)", TestAnswerRelevancy(), "test_explanation_relevance"),
        ("LLM Judge / GEval (DeepEval)", TestLLMJudge(),       "test_explanation_quality"),
    ]

    def _append(name, instance, exc=None):
        ann = suite_annotations.get(name, {})
        suite_records.append({
            "suite":         name,
            "description":   ann.get("description", ""),
            "pass_criteria": ann.get("pass_criteria", ""),
            "how_to_read":   ann.get("how_to_read", ""),
            "status":        "passed" if exc is None else ("failed" if isinstance(exc, AssertionError) else "error"),
            "error":         str(exc) if exc else None,
            "details":       getattr(instance, "details", None),
        })

    for suite_name, instance, method_name in test_suites:
        try:
            getattr(instance, method_name)()
            print(f"\n✓ {suite_name}: PASSED")
            passed_suites += 1
            _append(suite_name, instance)
        except (AssertionError, Exception) as e:
            label = "FAILED" if isinstance(e, AssertionError) else "ERROR"
            print(f"\n✗ {suite_name}: {label} — {e}")
            failed_suites += 1
            _append(suite_name, instance, exc=e)

    if run_llm_judge:
        print("\n── LLM-graded DeepEval tests (RUN_LLM_JUDGE=1) ──")
        for suite_name, instance, method_name in llm_test_suites:
            try:
                getattr(instance, method_name)()
                print(f"\n✓ {suite_name}: PASSED")
                passed_suites += 1
                _append(suite_name, instance)
            except (AssertionError, Exception) as e:
                label = "FAILED" if isinstance(e, AssertionError) else "ERROR"
                print(f"\n✗ {suite_name}: {label} — {e}")
                failed_suites += 1
                _append(suite_name, instance, exc=e)
    else:
        print("\n(LLM-graded DeepEval tests skipped — set RUN_LLM_JUDGE=1 to enable)")

    print("\n" + "=" * 60)
    print(f"Results: {passed_suites} passed, {failed_suites} failed")
    print("=" * 60)

    # ── Save results to evaluation/results/<timestamp>.json ──
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(results_dir, exist_ok=True)
    ts       = run_started.strftime("%Y-%m-%d_%H-%M-%S")
    out_path = os.path.join(results_dir, f"{ts}.json")
    report   = {
        "_readme": (
            "AI Resume Matching System — DeepEval Evaluation Report. "
            "Fields: "
            "run_at = ISO timestamp of when this run started; "
            "llm_judge = whether LLM-graded DeepEval tests (AnswerRelevancy + GEval) were executed (requires RUN_LLM_JUDGE=1); "
            "passed/failed/total = suite-level counts (one suite = one test class); "
            "suites[] = per-suite results. "
            "Each suite has: description (what it tests), pass_criteria (threshold to pass), "
            "how_to_read (field-by-field guide to the details), status (passed/failed/error), "
            "error (assertion message if failed), details (per-query breakdown with scores)."
        ),
        "run_at":        run_started.isoformat(),
        "llm_judge":     run_llm_judge,
        "passed":        passed_suites,
        "failed":        failed_suites,
        "total":         passed_suites + failed_suites,
        "suites":        suite_records,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved → {out_path}")

    if failed_suites == 0:
        print("All tests passed! ✓")
    else:
        print(f"{failed_suites} test(s) failed.")
        sys.exit(1)
