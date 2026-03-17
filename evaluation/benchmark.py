"""
evaluation/benchmark.py

Simple performance benchmark for the resume matching pipeline.

Run:
    python evaluation/benchmark.py
"""

import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from agents.orchestrator import run_pipeline
from ingestion.chunker import chunk_all_resumes
from ingestion.parser import load_all_resumes

load_dotenv()


BENCHMARK_QUERIES = [
    "Python backend engineer with FastAPI and PostgreSQL experience",
    "Java full stack developer with Spring Boot and MySQL",
    "Data analyst with SQL, Excel, and reporting experience",
    "IT consultant with ERP and project management background",
]


def load_chunks() -> list[dict]:
    """Loads and chunks resumes once for all benchmark iterations."""
    resumes = load_all_resumes(
        csv_path="data/raw/Resume.csv",
        pdf_folder="data/raw/pdfs",
    )
    return chunk_all_resumes(resumes)


def run_benchmark() -> dict:
    """Measures latency and throughput in candidates per second."""
    chunks = load_chunks()

    total_queries = len(BENCHMARK_QUERIES)
    total_candidates = 0
    latencies = []

    print("=" * 60)
    print("Resume Matching System - Performance Benchmark")
    print("=" * 60)

    for idx, query in enumerate(BENCHMARK_QUERIES, start=1):
        print(f"\n[{idx}/{total_queries}] Query: {query}")
        started = time.perf_counter()
        results = run_pipeline(query, top_k=5, chunks=chunks)
        latency = time.perf_counter() - started

        total_candidates += len(results)
        latencies.append(latency)
        print(f"Latency: {latency:.2f}s | Candidates returned: {len(results)}")

    total_time = sum(latencies)
    avg_latency = total_time / max(total_queries, 1)
    candidates_per_second = total_candidates / total_time if total_time else 0.0

    summary = {
        "queries_run": total_queries,
        "total_candidates": total_candidates,
        "total_time_seconds": round(total_time, 2),
        "avg_latency_seconds": round(avg_latency, 2),
        "candidates_per_second": round(candidates_per_second, 2),
    }

    print("\n" + "=" * 60)
    print("Benchmark Summary")
    print("=" * 60)
    for key, value in summary.items():
        print(f"{key}: {value}")

    return summary


if __name__ == "__main__":
    run_benchmark()
