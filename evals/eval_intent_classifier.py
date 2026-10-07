"""
Evaluate intent classifier against evals/golden_dataset.json.

NOTE: Uses the real OpenAI model via the classifier's own FastAPI app (in-process,
no server needed)
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from loguru import logger

from src.services.intent_classifier.classifier import classifier_api
from src.services.intent_classifier.schemas import Intent

DATASET_PATH = Path(__file__).parent / "golden_dataset.json"
INTENTS = [i.value for i in Intent]
# the classifier returns a null intent when it can't parse the model output
UNPARSED = "unparsed"
PRED_LABELS = [*INTENTS, UNPARSED]

client = TestClient(classifier_api)


def load_examples() -> list[dict]:
    data = json.loads(DATASET_PATH.read_text())
    return data["examples"]


def predict(query: str) -> str:
    response = client.post("/classify", json={"query": query})
    response.raise_for_status()
    return response.json()["intent"] or UNPARSED


def confusion_matrix(results: list[dict]) -> dict[str, dict[str, int]]:
    matrix = {gold: dict.fromkeys(PRED_LABELS, 0) for gold in INTENTS}
    for r in results:
        matrix[r["gold"]][r["pred"]] += 1
    return matrix


def per_class_metrics(matrix: dict[str, dict[str, int]]) -> dict[str, dict[str, float]]:
    metrics = {}
    for c in INTENTS:
        tp = matrix[c][c]
        fp = sum(matrix[g][c] for g in INTENTS if g != c)
        # an unparsed prediction is a miss (FN) for the gold intent, not a false positive for any intent
        fn = sum(matrix[c][p] for p in PRED_LABELS if p != c)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        metrics[c] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    return metrics


def print_report(results: list[dict], matrix: dict[str, dict[str, int]], metrics: dict[str, dict[str, float]]) -> None:
    correct = sum(r["correct"] for r in results)
    total = len(results)

    unparsed = sum(r["pred"] == UNPARSED for r in results)

    print(f"\nAccuracy: {correct}/{total} ({correct / total:.1%})")
    print(f"Unparsed: {unparsed}/{total}\n")

    print(f"{'intent':<20}{'precision':>10}{'recall':>10}{'f1':>10}{'support':>10}")
    for c in INTENTS:
        m = metrics[c]
        print(f"{c:<20}{m['precision']:>10.2f}{m['recall']:>10.2f}{m['f1']:>10.2f}{m['support']:>10}")

    print("\nConfusion matrix (rows = gold, cols = predicted):")
    header = " " * 20 + "".join(f"{c:>20}" for c in PRED_LABELS)
    print(header)
    for gold in INTENTS:
        row = "".join(f"{matrix[gold][pred]:>20}" for pred in PRED_LABELS)
        print(f"{gold:<20}{row}")

    mispredictions = [r for r in results if not r["correct"]]
    if mispredictions:
        print(f"\nMispredictions ({len(mispredictions)}):")
        for r in mispredictions:
            print(f"  [{r['id']}] gold={r['gold']} pred={r['pred']} | {r['query']}")
    else:
        print("\nNo mispredictions.")


def main() -> None:
    examples = load_examples()
    results = []

    # iterate over each example in the golden dataset
    for ex in examples:
        pred = predict(ex["query"])
        results.append({
            "id": ex["id"],
            "query": ex["query"],
            "gold": ex["intent"],
            "pred": pred,
            "correct": pred == ex["intent"],
        })
        logger.info(f"[{ex['id']}] gold={ex['intent']} pred={pred}")

    matrix = confusion_matrix(results)
    metrics = per_class_metrics(matrix)
    print_report(results, matrix, metrics)


if __name__ == "__main__":
    main()
