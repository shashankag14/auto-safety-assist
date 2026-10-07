"""
Score saved RAGAS samples.

Loads a samples file written by evals/generate_ragas_samples.py and scores
every answered sample with five RAGAS metrics:
  - faithfulness:        is every claim in the answer supported by the context? (generator)
  - answer_relevancy:    does the answer address the question? (generator)
  - factual_correctness: does the answer contain the facts in the reference answer? (generator)
  - context_precision:   are the useful contexts ranked near the top? (retriever)
  - context_recall:      does the context contain what the reference answer needs? (retriever)

Faithfulness and relevancy never look at the reference, so a confident answer that
misreads its context (e.g. "there is no coolant pump recall" when the recall was
retrieved) can score 1.0 on both. factual_correctness compares against the reference
to catch that. It runs in recall mode (share of reference claims the answer covers)
so answers citing extra, correct documents aren't penalized; unsupported extra
claims are faithfulness's job.

Scoring never calls the pipeline, so judges/metrics can be changed and rerun
against the exact same answers. Judge LLM and embedding calls are cached on
disk (.cache/ragas), so rescoring an unchanged sample costs nothing.

Requires:
    - a real OPENAI_API_KEY in .env
    - the eval dependency group: uv sync --group eval

Run from the repo root (defaults to the newest samples file in evals/results/):
    uv run --group eval python -m evals.eval_ragas
    uv run --group eval python -m evals.eval_ragas evals/results/ragas_samples_<timestamp>.json
"""

import asyncio
import json
import statistics
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from loguru import logger
from openai import AsyncOpenAI
from ragas.cache import DiskCacheBackend
from ragas.embeddings.base import embedding_factory
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecisionWithReference,
    ContextRecall,
    FactualCorrectness,
    Faithfulness,
)

from src.common.config import get_response_generator_config

RESULTS_DIR = Path(__file__).parent / "results"
CACHE_DIR = Path(__file__).parents[1] / ".cache" / "ragas"

JUDGE_MODEL = "gpt-4.1-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
MAX_CONCURRENT_SCORES = 8
WEAK_SCORE_THRESHOLD = 0.5
FACTUAL_CORRECTNESS_MODE = "recall"

# sample fields each metric's ascore() takes
METRIC_INPUTS = {
    "faithfulness": ("user_input", "response", "retrieved_contexts"),
    "answer_relevancy": ("user_input", "response"),
    "factual_correctness": ("response", "reference"),
    "context_precision": ("user_input", "reference", "retrieved_contexts"),
    "context_recall": ("user_input", "retrieved_contexts", "reference"),
}


def build_metrics() -> dict:
    # create a single AsyncOpenAI client to share across all metrics, so we don't hit the rate limit
    client = AsyncOpenAI(api_key=get_response_generator_config().openai_api_key)

    # create a cache backend so repeated calls to the same judge/embedding don't cost money
    cache = DiskCacheBackend(cache_dir=str(CACHE_DIR))

    # create a judge LLM and an embedding model for the metrics to use
    judge = llm_factory(JUDGE_MODEL, client=client, cache=cache, temperature=0)
    embeddings = embedding_factory("openai", EMBEDDING_MODEL, client=client, cache=cache)

    return {
        "faithfulness": Faithfulness(llm=judge),
        "answer_relevancy": AnswerRelevancy(llm=judge, embeddings=embeddings),
        "factual_correctness": FactualCorrectness(llm=judge, mode=FACTUAL_CORRECTNESS_MODE),
        "context_precision": ContextPrecisionWithReference(llm=judge),
        "context_recall": ContextRecall(llm=judge),
    }


def latest_samples_file() -> Path:
    files = sorted(RESULTS_DIR.glob("ragas_samples_*.json"))
    if not files:
        sys.exit("No samples found in evals/results/ - run evals.generate_ragas_samples first")
    return files[-1]


async def score_one(metric, name: str, sample: dict, semaphore: asyncio.Semaphore) -> tuple[float | None, str | None]:
    """Returns (score, error). A failed judge call is recorded, not raised, so one bad sample can't sink the run."""
    kwargs = {field: sample[field] for field in METRIC_INPUTS[name]}
    async with semaphore:
        try:
            result = await metric.ascore(**kwargs)
            return float(result.value), None
        except Exception as e:
            logger.warning(f"[{sample['id']}] {name} failed: {e}")
            return None, f"{type(e).__name__}: {e}"


async def score_samples(samples: list[dict], metrics: dict) -> list[dict]:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCORES)
    answered = [s for s in samples if s["response"] is not None]

    jobs = [(s, name) for s in answered for name in metrics]
    outcomes = await asyncio.gather(*(score_one(metrics[name], name, s, semaphore) for s, name in jobs))

    scores = {s["id"]: {"id": s["id"], "user_input": s["user_input"], "scores": {}, "errors": {}} for s in answered}
    for (s, name), (value, error) in zip(jobs, outcomes, strict=True):
        scores[s["id"]]["scores"][name] = value
        if error:
            scores[s["id"]]["errors"][name] = error
    return list(scores.values())


def summarize(results: list[dict]) -> dict:
    summary = {}
    for name in METRIC_INPUTS:
        values = [r["scores"][name] for r in results if r["scores"].get(name) is not None]
        summary[name] = {
            "mean": round(statistics.mean(values), 3) if values else None,
            "scored": len(values),
            "failed": len(results) - len(values),
        }
    return summary


def print_report(samples_path: Path, num_skipped: int, results: list[dict], summary: dict) -> None:
    print(f"\nScored {len(results)} samples from {samples_path.name}")
    if num_skipped:
        print(f"Skipped {num_skipped} unanswered samples (no retrieved context)")

    print(f"\n{'metric':<20}{'mean':>8}{'scored':>8}{'failed':>8}")
    for name, s in summary.items():
        mean = f"{s['mean']:.3f}" if s["mean"] is not None else "-"
        print(f"{name:<20}{mean:>8}{s['scored']:>8}{s['failed']:>8}")

    print(f"\n{'id':<8}" + "".join(f"{name[:12]:>14}" for name in METRIC_INPUTS))
    for r in results:
        cells = [f"{r['scores'][n]:>14.2f}" if r["scores"][n] is not None else f"{'err':>14}" for n in METRIC_INPUTS]
        print(f"{r['id']:<8}{''.join(cells)}")

    weak = [r for r in results if any(v is not None and v < WEAK_SCORE_THRESHOLD for v in r["scores"].values())]
    if weak:
        print(f"\nSamples scoring below {WEAK_SCORE_THRESHOLD} on any metric ({len(weak)}):")
        for r in weak:
            low = {n: round(v, 2) for n, v in r["scores"].items() if v is not None and v < WEAK_SCORE_THRESHOLD}
            print(f"  [{r['id']}] {low} | {r['user_input']}")


def main() -> None:
    logger.info(
        f"Running RAGAS scoring with judge={JUDGE_MODEL} embedding={EMBEDDING_MODEL} "
        f"max_concurrent={MAX_CONCURRENT_SCORES}"
    )

    samples_path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_samples_file()
    logger.debug(f"Loading dataset samples from {samples_path}")
    run = json.loads(samples_path.read_text(encoding="utf-8"))
    samples = run["samples"]

    logger.debug(f"Scoring {len(samples)} samples from {samples_path.name} (skipping unanswered)...")
    started_at = datetime.now(UTC)
    results = asyncio.run(score_samples(samples, build_metrics()))
    summary = summarize(results)
    num_skipped = len(samples) - len(results)

    print_report(samples_path, num_skipped, results, summary)

    scores_run = {
        "run_metadata": {
            "created_at": started_at.isoformat(timespec="seconds"),
            "samples_file": samples_path.name,
            "samples_run_metadata": run["run_metadata"],
            "ragas_version": version("ragas"),
            "judge_model": JUDGE_MODEL,
            "embedding_model": EMBEDDING_MODEL,
            "factual_correctness_mode": FACTUAL_CORRECTNESS_MODE,
            "num_scored": len(results),
            "num_skipped": num_skipped,
        },
        "summary": summary,
        "results": results,
    }
    out_path = RESULTS_DIR / f"ragas_scores_{started_at:%Y%m%dT%H%M%SZ}.json"
    out_path.write_text(json.dumps(scores_run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.success(f"Saved scores to {out_path}")


if __name__ == "__main__":
    main()
