"""
Score the response generator against evals/golden_dataset.json.

Chains the real two-stage pipeline: retrieve() over HTTP (needs the running
retriever + postgres containers), then generate_response() via TestClient.
Using the retriever's real output as context (not a hand-picked
golden context) tests what the generator actually sees in production.

Scores two independent things for every answer:
  - faithfulness: LLM-as-judge call asking whether every claim in the
    answer is supported by the context it was given (to catche hallucination).
  - gold_answer_contains: a simple deterministic substring check against the
    golden dataset's expected keywords/citations (catches incompleteness).

Requires:
    - docker-compose up -d postgres retriever
    - a real OPENAI_API_KEY in .env

Run from the repo root:
    uv run python -m evals.eval_response_generator
"""

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from loguru import logger
from openai import OpenAI
from pydantic import BaseModel

from src.common.config import get_response_generator_config, get_retriever_config
from src.services.response_generator.generator import Candidates, build_context, generator_api

DATASET_PATH = Path(__file__).parent / "golden_dataset.json"

retriever_cfg = get_retriever_config()
RETRIEVE_URL = f"http://{retriever_cfg.host}:{retriever_cfg.port}/retrieve"

generator_client = TestClient(generator_api)

response_generator_cfg = get_response_generator_config()
judge_client = OpenAI(api_key=response_generator_cfg.openai_api_key)
JUDGE_MODEL = "gpt-4o-mini"

JUDGE_INSTRUCTIONS = """You are a strict fact-checking judge for a vehicle safety assistant.
You will be given CONTEXT (retrieved NHTSA recall/complaint excerpts) and an ANSWER generated
from that context. Determine whether the answer is fully faithful to the context: every factual
claim, especially citation numbers and root causes, must be directly supported by the context.
Do not penalize reasonable paraphrasing - only flag claims that introduce information, numbers,
or conclusions that are not present in the context. List each unsupported claim verbatim from the
answer; return an empty list if the answer is fully faithful.
"""


class FaithfulnessJudgement(BaseModel):
    faithful: bool
    unsupported_claims: list[str]


def load_examples() -> list[dict]:
    data = json.loads(DATASET_PATH.read_text())
    # general_question examples never reach retrieval/generation
    return [ex for ex in data["examples"] if ex["relevant"]]


def retrieve(query: str) -> list[dict]:
    response = httpx.post(RETRIEVE_URL, json={"query": query}, timeout=30)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json()["candidates"]


def generate(query: str, candidates: list[dict]) -> str:
    response = generator_client.post("/generate", json={"query": query, "candidates": candidates})
    response.raise_for_status()
    return response.json()["response"]


def judge_faithfulness(context: str, answer: str) -> FaithfulnessJudgement:
    response = judge_client.responses.parse(
        model=JUDGE_MODEL,
        instructions=JUDGE_INSTRUCTIONS,
        input=f"CONTEXT:\n{context}\n\nANSWER:\n{answer}",
        text_format=FaithfulnessJudgement,
    )
    return response.output_parsed


def check_gold_answer_contains(answer: str, expected: list[str]) -> list[str]:
    """Returns the expected substrings NOT found in the answer (case-insensitive)."""
    answer_lower = answer.lower()
    return [e for e in expected if e.lower() not in answer_lower]


def score_example(ex: dict) -> dict:
    raw_candidates = retrieve(ex["query"])
    if not raw_candidates:
        return {"id": ex["id"], "query": ex["query"], "answer": None, "faithful": False,
                "unsupported_claims": ["no candidates retrieved"], "missing_keywords": ex["gold_answer_contains"]}

    candidate_models = [Candidates(**c) for c in raw_candidates]
    context = build_context(candidate_models)
    answer = generate(ex["query"], raw_candidates)

    judgement = judge_faithfulness(context, answer)
    missing_keywords = check_gold_answer_contains(answer, ex["gold_answer_contains"])

    return {
        "id": ex["id"],
        "query": ex["query"],
        "answer": answer,
        "faithful": judgement.faithful,
        "unsupported_claims": judgement.unsupported_claims,
        "missing_keywords": missing_keywords,
    }


def print_report(results: list[dict]) -> None:
    n = len(results)
    faithful_count = sum(r["faithful"] for r in results)
    fully_covered_count = sum(not r["missing_keywords"] for r in results)

    print(f"\nEvaluated {n} queries\n")
    print(f"Faithfulness:          {faithful_count}/{n} ({faithful_count / n:.1%})")
    print(f"Gold keywords covered: {fully_covered_count}/{n} ({fully_covered_count / n:.1%})")

    unfaithful = [r for r in results if not r["faithful"]]
    if unfaithful:
        print(f"\nUnfaithful answers ({len(unfaithful)}):")
        for r in unfaithful:
            print(f"  [{r['id']}] {r['query']}")
            print(f"      answer:             {r['answer']}")
            print(f"      unsupported claims: {r['unsupported_claims']}")

    incomplete = [r for r in results if r["missing_keywords"]]
    if incomplete:
        print(f"\nAnswers missing expected keywords/citations ({len(incomplete)}):")
        for r in incomplete:
            print(f"  [{r['id']}] missing={r['missing_keywords']} | {r['query']}")


def main() -> None:
    examples = load_examples()
    results = []

    for ex in examples:
        result = score_example(ex)
        results.append(result)
        logger.info(f"[{ex['id']}] faithful={result['faithful']} missing={result['missing_keywords']}")

    print_report(results)


if __name__ == "__main__":
    main()
