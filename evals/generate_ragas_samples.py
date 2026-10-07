"""
Generate the RAGAS samples for the golden dataset.

For every retrieval example in evals/golden_dataset.json, runs the real
two-stage pipeline -- retrieve() then generate() --
and saves what the generator saw and said. Scoring is a separate step that
loads this file, so the metrics can be rerun or changed without paying for
new answers, and every score can be traced back to the exact answers it judged.

Sample fields use RAGAS names (user_input, retrieved_contexts, response,
reference) so they can be passed straight to each metric's ascore().

Requires:
    - docker-compose up -d postgres retriever
    - a real OPENAI_API_KEY in .env

Run from the repo root:
    uv run python -m evals.generate_ragas_samples
"""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from evals.eval_response_generator import generate, load_examples, retrieve
from src.common.config import get_default_openai_model, get_response_generator_config, get_retriever_config
from src.services.response_generator.generator import Candidates, build_context

RESULTS_DIR = Path(__file__).parent / "results"


def git_commit() -> str:
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    return f"{sha}-dirty" if dirty else sha


def build_sample(ex: dict) -> dict:
    candidates = retrieve(ex["query"])

    # one context string per candidate, formatted exactly as the generator sees it,
    # so the judge can check citation IDs in the answer against the context
    retrieved_contexts = [build_context([Candidates(**c)]) for c in candidates]
    response = generate(ex["query"], candidates) if candidates else None

    return {
        "id": ex["id"],
        "intent": ex["intent"],
        "vehicle_tag": ex["vehicle_tag"],
        "user_input": ex["query"],
        "retrieved_contexts": retrieved_contexts,
        "retrieved_context_ids": [str(c["external_id"]) for c in candidates],
        "cosine_sims": [c["cosine_sim"] for c in candidates],
        "response": response,
        "reference": ex["reference_answer"],
        "reference_context_ids": [str(rel["key"]) for rel in ex["relevant"]],
    }


def main() -> None:
    examples = load_examples()
    started_at = datetime.now(UTC)

    samples = []
    for ex in examples:
        sample = build_sample(ex)
        samples.append(sample)
        answered = sample["response"] is not None
        logger.info(f"[{ex['id']}] contexts={len(sample['retrieved_contexts'])} answered={answered}")

    run = {
        "run_metadata": {
            "created_at": started_at.isoformat(timespec="seconds"),
            "git_commit": git_commit(),
            "generator_model": get_default_openai_model().value,
            "generator_temperature": get_response_generator_config().temperature,
            "retriever_top_k": get_retriever_config().top_k,
            "num_samples": len(samples),
            "num_unanswered": sum(s["response"] is None for s in samples),
        },
        "samples": samples,
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"ragas_samples_{started_at:%Y%m%dT%H%M%SZ}.json"
    out_path.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info(f"Saved {len(samples)} samples to {out_path}")


if __name__ == "__main__":
    main()
