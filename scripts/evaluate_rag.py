"""
RAGAS Evaluation Script for the RAG Microservice Platform.

Runs a test dataset through the live RAG pipeline (via API Gateway),
collects answers + retrieved contexts, then evaluates quality using
RAGAS metrics: Faithfulness, Answer Relevancy, Context Precision,
and Context Recall.

Usage:
    # Make sure the platform is running (make up)
    python scripts/evaluate_rag.py

    # With custom options
    python scripts/evaluate_rag.py \
        --api-url http://localhost:8000 \
        --api-key default-api-key-change-me \
        --dataset scripts/eval_dataset.json \
        --output scripts/eval_results.json
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_API_KEY = "default-api-key-change-me"
DEFAULT_DATASET = Path(__file__).parent / "eval_dataset.json"
DEFAULT_OUTPUT = Path(__file__).parent / "eval_results.json"


# ---------------------------------------------------------------------------
# Step 1 — Query the RAG pipeline for every test question
# ---------------------------------------------------------------------------
async def query_rag_pipeline(
    client: httpx.AsyncClient,
    api_url: str,
    api_key: str,
    question: str,
    tenant_id: str = "default",
    top_k: int = 5,
) -> dict:
    """Call the RAG API and return the answer + retrieved contexts."""
    response = await client.post(
        f"{api_url}/api/v1/query",
        headers={"X-API-Key": api_key},
        json={
            "question": question,
            "tenant_id": tenant_id,
            "top_k": top_k,
            "rerank": True,
            "stream": False,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()


async def collect_rag_results(
    api_url: str,
    api_key: str,
    dataset: list[dict],
) -> list[dict]:
    """Run every question through the pipeline and collect results."""
    results = []

    async with httpx.AsyncClient() as client:
        for i, item in enumerate(dataset):
            question = item["question"]
            ground_truth = item["ground_truth"]

            logger.info(
                "[%d/%d] Querying: '%s'",
                i + 1,
                len(dataset),
                question[:80],
            )

            try:
                rag_result = await query_rag_pipeline(client, api_url, api_key, question)

                # Extract contexts from retrieved chunks
                contexts = [
                    chunk.get("content", "")
                    for chunk in rag_result.get("retrieved_chunks", [])
                ]

                results.append(
                    {
                        "question": question,
                        "answer": rag_result.get("answer", ""),
                        "contexts": contexts,
                        "ground_truth": ground_truth,
                    }
                )
            except httpx.HTTPStatusError as e:
                logger.error("HTTP error for question %d: %s", i + 1, e)
                results.append(
                    {
                        "question": question,
                        "answer": "",
                        "contexts": [],
                        "ground_truth": ground_truth,
                    }
                )
            except Exception as e:
                logger.error("Unexpected error for question %d: %s", i + 1, e)
                results.append(
                    {
                        "question": question,
                        "answer": "",
                        "contexts": [],
                        "ground_truth": ground_truth,
                    }
                )

    return results


# ---------------------------------------------------------------------------
# Step 2 — Evaluate with RAGAS
# ---------------------------------------------------------------------------
def run_ragas_evaluation(results: list[dict]) -> dict:
    """Evaluate the collected results using RAGAS metrics."""
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError:
        logger.error(
            "Required packages not installed. Run:\n"
            "  pip install ragas datasets"
        )
        sys.exit(1)

    # Build a HuggingFace Dataset from collected results
    eval_data = {
        "question": [r["question"] for r in results],
        "answer": [r["answer"] for r in results],
        "contexts": [r["contexts"] for r in results],
        "ground_truth": [r["ground_truth"] for r in results],
    }
    dataset = Dataset.from_dict(eval_data)

    logger.info("Running RAGAS evaluation on %d samples...", len(dataset))

    ragas_result = evaluate(
        dataset=dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
    )

    return ragas_result


# ---------------------------------------------------------------------------
# Step 3 — Report & save
# ---------------------------------------------------------------------------
def save_results(ragas_result, output_path: Path, raw_results: list[dict]) -> None:
    """Print the evaluation report and save to JSON."""
    scores = ragas_result.to_pandas().to_dict()

    # Extract average scores
    avg_scores = {}
    metric_names = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    for metric in metric_names:
        if metric in scores:
            values = list(scores[metric].values())
            avg_scores[metric] = round(sum(values) / len(values), 4) if values else 0.0

    # Print report
    print("\n" + "=" * 60)
    print("  RAGAS Evaluation Report")
    print("=" * 60)
    for metric, score in avg_scores.items():
        bar = "█" * int(score * 30) + "░" * (30 - int(score * 30))
        print(f"  {metric:<25} {bar}  {score:.4f}")
    print("=" * 60)

    overall = sum(avg_scores.values()) / len(avg_scores) if avg_scores else 0.0
    print(f"  {'OVERALL SCORE':<25} {'':>30}  {overall:.4f}")
    print("=" * 60 + "\n")

    # Save full results to JSON
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "num_samples": len(raw_results),
        "average_scores": avg_scores,
        "overall_score": round(overall, 4),
        "per_sample": [],
    }

    df = ragas_result.to_pandas()
    for i, row in df.iterrows():
        sample = {
            "question": row.get("question", ""),
            "answer": row.get("answer", ""),
            "ground_truth": raw_results[i]["ground_truth"] if i < len(raw_results) else "",
        }
        for metric in metric_names:
            if metric in row:
                sample[metric] = round(float(row[metric]), 4)
        output["per_sample"].append(sample)

    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    logger.info("Results saved to %s", output_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAGAS Evaluation for RAG Platform")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="API Gateway URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key for authentication")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Path to eval dataset JSON")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to save results JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Load dataset
    if not args.dataset.exists():
        logger.error("Dataset file not found: %s", args.dataset)
        sys.exit(1)

    with open(args.dataset) as f:
        dataset = json.load(f)

    logger.info("Loaded %d test samples from %s", len(dataset), args.dataset)

    # Step 1: Collect RAG results
    logger.info("Querying RAG pipeline at %s ...", args.api_url)
    start = time.perf_counter()
    raw_results = asyncio.run(collect_rag_results(args.api_url, args.api_key, dataset))
    query_time = time.perf_counter() - start
    logger.info("All queries completed in %.2fs", query_time)

    # Check if we got any valid answers
    valid = [r for r in raw_results if r["answer"]]
    if not valid:
        logger.error(
            "No valid answers received from the pipeline. "
            "Make sure the platform is running (make up) and documents are ingested."
        )
        sys.exit(1)

    logger.info("Received %d/%d valid answers", len(valid), len(raw_results))

    # Step 2: RAGAS evaluation
    ragas_result = run_ragas_evaluation(raw_results)

    # Step 3: Report & save
    save_results(ragas_result, args.output, raw_results)


if __name__ == "__main__":
    main()
