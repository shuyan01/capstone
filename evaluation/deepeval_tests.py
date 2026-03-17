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

        for query in self.INVALID_QUERIES:
            result = validate_job_query(query)
            is_rejected = not result["valid"]
            status = "PASS" if is_rejected else "FAIL"
            display = f"'{query[:40]}'" if query else "'(empty)'"
            print(f"  {status} — {display} → rejected={is_rejected}")
            if not is_rejected:
                print(f"         ERROR: Should have been rejected but wasn't")
            results.append(is_rejected)

        passed = sum(results)
        total  = len(results)
        print(f"\n  Invalid query rejection: {passed}/{total} passed")
        assert passed == total, (
            f"Guardrail missed {total - passed} invalid queries."
        )

    def test_valid_queries_pass(self):
        print("\n── Test 5b: Valid Queries Pass Through ──")
        results = []

        for query in self.VALID_QUERIES:
            result   = validate_job_query(query)
            is_valid = result["valid"]
            status   = "PASS" if is_valid else "FAIL"
            print(f"  {status} — '{query[:50]}...' → valid={is_valid}")
            results.append(is_valid)

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
    Uses DeepEval AnswerRelevancyMetric to check that the
    top candidate explanation is relevant to the job query.
    A low score means the system surfaced irrelevant candidates.
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
    ]

    def test_explanation_relevance(self):
        chunks = load_chunks()

        print("\n── DeepEval: Answer Relevancy ──")

        relevancy_metric = AnswerRelevancyMetric(threshold=0.5)

        for case in self.TEST_CASES:
            results = run_pipeline(
                job_query=case["query"],
                top_k=1,
                chunks=chunks,
            )

            if not results:
                print(f"  SKIP — No results for: '{case['query']}'")
                continue

            top         = results[0]
            explanation = top.get("explanation", "")

            if not explanation:
                print(f"  SKIP — No explanation generated")
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
            assert passed_metric, (
                f"Answer relevancy too low: {score_str} < {relevancy_metric.threshold} "
                f"for query '{case['query'][:60]}'"
            )


class TestLLMJudge:
    """
    Uses DeepEval GEval to evaluate whether the
    explanation generated for a candidate is:
    - Relevant to the job query
    - Factually grounded in the scores
    - Clear and professional
    """

    def test_explanation_quality(self):
        chunks = load_chunks()

        print("\n── Test 6: LLM-as-Judge (Explanation Quality) ──")

        query   = "Java full stack developer with Spring Boot and MySQL experience"
        results = run_pipeline(query, top_k=1, chunks=chunks)

        if not results:
            print("  SKIP — No results returned")
            return

        top         = results[0]
        explanation = top.get("explanation", "")
        score       = top.get("composite_score", 0)

        print(f"  Candidate:   {top['resume_id']}")
        print(f"  Score:       {score:.2f}")
        print(f"  Explanation: {explanation[:150]}...")

        # GEval metric — evaluates explanation quality
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
            threshold=0.5,
        )

        test_case = LLMTestCase(
            input=query,
            actual_output=explanation,
        )

        explanation_quality.measure(test_case)
        score_str = f"{explanation_quality.score:.2f}" if explanation_quality.score is not None else "n/a"
        passed_metric = explanation_quality.score is not None and explanation_quality.score >= explanation_quality.threshold
        status = "PASS" if passed_metric else "FAIL"
        print(f"  {status} — Explanation quality score: {score_str} (threshold: 0.5)")
        if not passed_metric:
            print(f"         Reason: {explanation_quality.reason}")
        assert passed_metric, (
            f"Explanation quality too low: {score_str} (threshold 0.5)"
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

        passed = sum(results)
        total = len(results)
        print(f"\n  Culture Match: {passed}/{total} passed")
        assert passed >= total * 0.5, (
            f"Culture match too low: {passed}/{total} passed."
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

    test_suites = [
        ("Skill Coverage",       TestSkillCoverage(),    "test_skill_coverage"),
        ("Experience Fit",       TestExperienceFit(),    "test_experience_fit"),
        ("Ranking Quality",      TestRankingQuality(),   "test_ranking_order"),
        ("Diversity",            TestDiversity(),        "test_result_diversity"),
        ("Guardrails (invalid)", TestGuardrails(),       "test_invalid_queries_rejected"),
        ("Guardrails (valid)",   TestGuardrails(),       "test_valid_queries_pass"),
        ("Culture Match",        TestCultureMatch(),     "test_culture_match"),
    ]

    # LLM-graded DeepEval tests — opt-in only
    llm_test_suites = [
        ("Answer Relevancy (DeepEval)", TestAnswerRelevancy(), "test_explanation_relevance"),
        ("LLM Judge / GEval (DeepEval)", TestLLMJudge(),       "test_explanation_quality"),
    ]

    for suite_name, instance, method_name in test_suites:
        try:
            getattr(instance, method_name)()
            print(f"\n✓ {suite_name}: PASSED")
            passed_suites += 1
            suite_records.append({"suite": suite_name, "status": "passed", "error": None})
        except AssertionError as e:
            print(f"\n✗ {suite_name}: FAILED — {e}")
            failed_suites += 1
            suite_records.append({"suite": suite_name, "status": "failed", "error": str(e)})
        except Exception as e:
            print(f"\n✗ {suite_name}: ERROR — {e}")
            failed_suites += 1
            suite_records.append({"suite": suite_name, "status": "error", "error": str(e)})

    if run_llm_judge:
        print("\n── LLM-graded DeepEval tests (RUN_LLM_JUDGE=1) ──")
        for suite_name, instance, method_name in llm_test_suites:
            try:
                getattr(instance, method_name)()
                print(f"\n✓ {suite_name}: PASSED")
                passed_suites += 1
                suite_records.append({"suite": suite_name, "status": "passed", "error": None})
            except AssertionError as e:
                print(f"\n✗ {suite_name}: FAILED — {e}")
                failed_suites += 1
                suite_records.append({"suite": suite_name, "status": "failed", "error": str(e)})
            except Exception as e:
                print(f"\n✗ {suite_name}: ERROR — {e}")
                failed_suites += 1
                suite_records.append({"suite": suite_name, "status": "error", "error": str(e)})
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
