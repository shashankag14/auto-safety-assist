"""
Data snapshot ID for evals.

Evals run on a copy of the NHTSA data fetched from S3 bucket (source of truth) and
kept in a fixture folder as a local copy so scores only change when code or models change.
Every run records the snapshot ID.

The ID is a hash of the parsed JSON, not the raw bytes, so Windows (CRLF) and
Linux (LF) checkouts of the same data get the same ID.

Run from the repo root:
    uv run python -m evals.snapshot             # print the ID of data/ to be used by CI pipeline
    uv run python -m evals.snapshot --refresh   # copy data/ into the fixture
"""

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

DATA_DIR = Path(__file__).parents[1] / "data"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "nhtsa_snapshot"
FILES = ("recalls.json", "complaints.json")


def snapshot_id(data_dir: Path = DATA_DIR) -> str:
    digest = hashlib.sha256()
    for name in FILES:
        records = json.loads((data_dir / name).read_text(encoding="utf-8"))
        digest.update(json.dumps(records, sort_keys=True).encode())
    return f"sha256:{digest.hexdigest()[:16]}"


def refresh_fixture() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(DATA_DIR / name, FIXTURE_DIR / name)

    manifest = {"snapshot_id": snapshot_id(FIXTURE_DIR), "created_at": datetime.now(UTC).isoformat(timespec="seconds")}
    (FIXTURE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Fixture is now {manifest['snapshot_id']}")
    print("If the ID changed: re-check the golden labels and rebuild evals/baseline.json before committing.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="copy data/ into the eval fixture")
    if parser.parse_args().refresh:
        refresh_fixture()
    else:
        print(snapshot_id())


if __name__ == "__main__":
    main()
