"""
Score the retriever against evals/golden_dataset.json.

Calls the retriever's real HTTP API rather than importing the service
in-process. This is because retriever.py connects to Postgres at the container-internal
host/port (POSTGRES_HOST=postgres, port 5432), which isn't reachable that way
from this host process. Postgres is only reachable from the host via the
docker-compose port mapping (127.0.0.1:5433 -> 5432), so hitting the
already-running container's HTTP API sidesteps the mismatch entirely.

Requires:
    docker-compose up -d postgres retriever

Run from the repo root:
    uv run python -m evals.eval_retriever
"""

import json
import math
from dataclasses import replace
from pathlib import Path

import httpx
from loguru import logger

from src.common.config import get_postgres_config, get_retriever_config
from src.common.db import get_connection

DATASET_PATH = Path(__file__).parent / "golden_dataset.json"

retriever_cfg = get_retriever_config()
RETRIEVE_URL = f"http://{retriever_cfg.host}:{retriever_cfg.port}/retrieve"

# .env's POSTGRES_PORT (5432) is what the containers use amongst themselves;
# from the host, Postgres is only exposed at the docker-compose port mapping.
HOST_POSTGRES_PORT = "5433"


def load_examples() -> list[dict]:
    data = json.loads(DATASET_PATH.read_text())
    # general_question examples have empty `relevant`
    return [ex for ex in data["examples"] if ex["relevant"]]


def load_key_lookup() -> dict[tuple[str, int], object]:
    """Map (source, Postgres SERIAL id) -> NHTSA natural key, so retriever
    results can be compared against the golden dataset's natural-key `relevant`."""
    cfg = replace(get_postgres_config(), port=HOST_POSTGRES_PORT)
    lookup = {}
    with get_connection(cfg) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, nhtsa_campaign_number FROM vehicle_recalls")
        for row_id, campaign_number in cur.fetchall():
            lookup[("recall", row_id)] = campaign_number

        cur.execute("SELECT id, odi_number FROM vehicle_complaints")
        for row_id, odi_number in cur.fetchall():
            lookup[("complaint", row_id)] = odi_number
    return lookup


def retrieve(query: str) -> list[dict]:
    response = httpx.post(RETRIEVE_URL, json={"query": query}, timeout=30)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json()["candidates"]

def compute_reciprocal_rank(retrieved_results: list[tuple], golden: dict[tuple, int]) -> float:
    reciprocal_rank = 0.0
    for rank, rk in enumerate(retrieved_results, start=1):
        if rk in golden:
            reciprocal_rank = 1 / rank
            break
    return reciprocal_rank

def compute_mrr(results: list[dict]) -> float:
    return sum(r["reciprocal_rank"] for r in results) / len(results)


def compute_dcg(grades: list[int]) -> float:
    return sum(grade / math.log2(rank + 1) for rank, grade in enumerate(grades, start=1))


def compute_ndcg(returned_grades: list[int], ideal_grades: list[int]) -> float:
    """NDCG@k using linear (not exponential) gain -- fine for the small integer
    grades here (recall=2, complaint=1). ideal_grades is the golden grades sorted
    descending, i.e. the best possible ranking to normalize against."""
    idcg = compute_dcg(ideal_grades)
    return compute_dcg(returned_grades) / idcg if idcg else 0.0


def compute_mean_ndcg(results: list[dict]) -> float:
    return sum(r["ndcg"] for r in results) / len(results)


def score_example(ex: dict, candidates: list[dict], key_lookup: dict) -> dict:
    golden = {(r["source"], r["key"]): r["grade"] for r in ex["relevant"]}
    returned = [(c["source"], key_lookup.get((c["source"], c["id"]))) for c in candidates]

    # compute reciprocal rank
    reciprocal_rank = compute_reciprocal_rank(returned, golden)

    # compute precision and recall
    hits = {rk for rk in returned if rk in golden}
    precision = len(hits) / len(returned) if returned else 0.0
    recall = len(hits) / len(golden) if golden else 0.0

    # Credit a golden item only on its first (highest-ranked) occurrence -- a recall is
    # stored as 3 chunks (summary/remedy/consequence) sharing one campaign number, so the
    # same golden item can otherwise appear more than once in `returned` and inflate DCG
    # past IDCG, which assumes each golden item contributes gain exactly once.
    returned_grades = []
    already_credited = set()
    for rk in returned:
        if rk in golden and rk not in already_credited:
            returned_grades.append(golden[rk])
            already_credited.add(rk)
        else:
            returned_grades.append(0)
    ideal_grades = sorted(golden.values(), reverse=True)
    ndcg = compute_ndcg(returned_grades, ideal_grades)

    return {
        "id": ex["id"],
        "query": ex["query"],
        "golden": golden,
        "returned": returned,
        "precision": precision,
        "recall": recall,
        "reciprocal_rank": reciprocal_rank,
        "ndcg": ndcg,
    }


def print_report(results: list[dict]) -> None:
    n = len(results)

    mean_precision = sum(r["precision"] for r in results) / n

    mean_recall = sum(r["recall"] for r in results) / n

    mrr = compute_mrr(results)
    mean_ndcg = compute_mean_ndcg(results)

    print(f"\nEvaluated {n} queries (top_k={retriever_cfg.top_k})\n")
    print(f"Mean Precision@k: {mean_precision:.2f}")
    print(f"Mean Recall@k:    {mean_recall:.2f}")
    print(f"MRR:              {mrr:.2f}")
    print(f"Mean NDCG@k:      {mean_ndcg:.2f}")

    misses = [r for r in results if r["recall"] < 1.0]
    if misses:
        print(f"\nQueries that missed at least one relevant item ({len(misses)}):")
        for r in misses:
            print(f"  [{r['id']}] recall={r['recall']:.2f} | {r['query']}")
            print(f"      golden:   {sorted(r['golden'])}")
            print(f"      returned: {r['returned']}")
    else:
        print("\nNo misses -- every golden-relevant item was retrieved.")


def main() -> None:
    examples = load_examples()
    key_lookup = load_key_lookup()
    results = []

    for ex in examples:
        candidates = retrieve(ex["query"])
        result = score_example(ex, candidates, key_lookup)
        results.append(result)
        logger.info(
            f"[{ex['id']}] precision={result['precision']:.2f} recall={result['recall']:.2f} ndcg={result['ndcg']:.2f}"
        )

    print_report(results)


if __name__ == "__main__":
    main()
