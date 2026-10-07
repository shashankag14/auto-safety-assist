"""
RAGAS regression gate: compare a scores run against a committed baseline.

Two commands:

  baseline  Build evals/baseline.json from several scores files of the SAME
            pipeline (fresh samples each run, scored with --no-cache). The
            spread between those runs is how much scores move with no code
            change, so each metric's tolerance is derived from it instead of guessed.

  check     Compare one scores file (default: the newest) against the baseline.
            Exits 1 if any gated metric's mean drops more than its tolerance
            below the baseline, if any judge call failed, or if the run was
            scored with a different judge/metric setup than the baseline.

answer_relevancy is reported but not gated: it generates questions from the
answer and compares embeddings, so it swings on answer style, not quality.

Run from the repo root:
    uv run python -m evals.compare_ragas baseline evals/results/ragas_scores_<a>.json <b>.json <c>.json
    uv run python -m evals.compare_ragas check
    uv run python -m evals.compare_ragas check evals/results/ragas_scores_<timestamp>.json
"""

import argparse
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
BASELINE_PATH = Path(__file__).parent / "baseline.json"

GATED_METRICS = ("faithfulness", "factual_correctness", "context_precision", "context_recall")
REPORT_ONLY_METRICS = ("answer_relevancy",)

# tolerance = max(MIN_TOLERANCE, STDEV_MULTIPLIER * stdev across baseline runs)
MIN_TOLERANCE = 0.03
STDEV_MULTIPLIER = 2

# scores are only comparable when these match between baseline and run
COMPARABILITY_KEYS = ("ragas_version", "judge_model", "embedding_model", "factual_correctness_mode")


def load_scores(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_scores_file() -> Path:
    files = sorted(RESULTS_DIR.glob("ragas_scores_*.json"))
    if not files:
        sys.exit("No scores found in evals/results/ - run evals.eval_ragas first")
    return files[-1]


def comparability(run: dict) -> dict:
    return {key: run["run_metadata"].get(key) for key in COMPARABILITY_KEYS}


def generator_setup(run: dict) -> dict:
    samples_meta = run["run_metadata"]["samples_run_metadata"]
    return {key: samples_meta.get(key) for key in ("generator_model", "generator_temperature", "retriever_top_k")}


def build_baseline(paths: list[Path]) -> None:
    if len(paths) < 2:
        sys.exit("A baseline needs at least 2 runs to measure run-to-run variation (3+ recommended)")

    runs = [load_scores(p) for p in paths]

    setups = {json.dumps(comparability(r), sort_keys=True) for r in runs}
    if len(setups) > 1:
        sys.exit(f"Runs were scored with different setups and can't be combined: {setups}")

    # cached runs replay the first judge verdict, so their spread understates the noise CI will see
    cached = [p.name for p, r in zip(paths, runs, strict=True) if r["run_metadata"].get("judge_cache") is not False]
    if cached:
        sys.exit(f"Baseline runs must be scored with --no-cache; these weren't: {cached}")

    generators = {json.dumps(generator_setup(r), sort_keys=True) for r in runs}
    if len(generators) > 1:
        sys.exit(f"Runs used different generator settings and can't be combined: {generators}")

    metrics = {}
    for name in GATED_METRICS + REPORT_ONLY_METRICS:
        means = [r["summary"].get(name, {}).get("mean") for r in runs]
        if any(m is None for m in means):
            sys.exit(f"Metric '{name}' is missing from at least one run - rescore with the current eval_ragas.py")

        stdev = statistics.stdev(means)
        metrics[name] = {
            "mean": round(statistics.mean(means), 3),
            "stdev": round(stdev, 3),
            "min": round(min(means), 3),
            "max": round(max(means), 3),
            "tolerance": round(max(MIN_TOLERANCE, STDEV_MULTIPLIER * stdev), 3),
            "gated": name in GATED_METRICS,
        }

    baseline = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "setup": comparability(runs[0]),
        "generator": generator_setup(runs[0]),
        "num_samples": runs[0]["run_metadata"]["num_scored"],
        "source_runs": [p.name for p in paths],
        "metrics": metrics,
    }
    BASELINE_PATH.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")

    print(f"Baseline from {len(runs)} runs written to {BASELINE_PATH}\n")
    print(f"{'metric':<22}{'mean':>8}{'stdev':>8}{'min':>8}{'max':>8}{'tolerance':>11}")
    for name, m in metrics.items():
        gate = "" if m["gated"] else "  (report only)"
        print(f"{name:<22}{m['mean']:>8.3f}{m['stdev']:>8.3f}{m['min']:>8.3f}{m['max']:>8.3f}{m['tolerance']:>11.3f}{gate}")


def check(path: Path) -> int:
    if not BASELINE_PATH.exists():
        sys.exit(f"No baseline at {BASELINE_PATH} - create one with the 'baseline' command")

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    run = load_scores(path)
    problems = []

    if comparability(run) != baseline["setup"]:
        problems.append(f"setup differs from baseline: run={comparability(run)} baseline={baseline['setup']}")

    print(f"Checking {path.name} against baseline ({', '.join(baseline['source_runs'])})\n")
    print(f"{'metric':<22}{'baseline':>10}{'run':>8}{'delta':>8}{'allowed':>9}  result")

    for name, base in baseline["metrics"].items():
        summary = run["summary"].get(name)
        if summary is None or summary["mean"] is None:
            problems.append(f"{name}: missing from run")
            print(f"{name:<22}{base['mean']:>10.3f}{'-':>8}{'-':>8}{-base['tolerance']:>9.3f}  MISSING")
            continue

        if summary["failed"]:
            problems.append(f"{name}: {summary['failed']} judge call(s) failed, so the mean is unreliable")

        delta = summary["mean"] - base["mean"]
        regressed = delta < -base["tolerance"]
        if regressed and base["gated"]:
            result = "FAIL"
            problems.append(
                f"{name}: {summary['mean']:.3f} is {-delta:.3f} below baseline (allowed {base['tolerance']:.3f})"
            )
        elif regressed:
            result = "below (not gated)"
        else:
            result = "ok"
        row = f"{name:<22}{base['mean']:>10.3f}{summary['mean']:>8.3f}{delta:>+8.3f}{-base['tolerance']:>9.3f}"
        print(f"{row}  {result}")

    if problems:
        print(f"\nRegression gate FAILED ({len(problems)}):")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("\nRegression gate passed")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    baseline_cmd = commands.add_parser("baseline", help="build evals/baseline.json from several scores files")
    baseline_cmd.add_argument("scores_files", nargs="+", type=Path)

    check_cmd = commands.add_parser("check", help="compare a scores file against the baseline")
    check_cmd.add_argument("scores_file", nargs="?", type=Path)

    args = parser.parse_args()
    if args.command == "baseline":
        build_baseline(args.scores_files)
    else:
        sys.exit(check(args.scores_file or latest_scores_file()))


if __name__ == "__main__":
    main()
