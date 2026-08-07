"""
Pull recalls + complaints from NHTSA's public API for a
fixed set of target vehicles, and cache them locally as JSON.
NHTSA API docs: https://www.nhtsa.gov/nhtsa-datasets-and-apis
"""

import requests
import time
import json

from pathlib import Path
from loguru import logger

from src.common.config import TARGET_VEHICLES


BASE_URL = "https://api.nhtsa.gov"
DATA_DIR = Path(__file__).parent.parent.parent / "data"


def fetch_recalls(make: str, model: str, model_year: int) -> list[dict]:
    """Fetch recalls for a single make/model/year

    API Syntax: api.nhtsa.gov/recalls/recallsByVehicle?make={MAKE}&model={MODEL}&modelYear={MODEL_YR}

    Confirmed field shape (2026-07-25): PascalCase keys — Summary (defect
    text), NHTSACampaignNumber (recall #), Manufacturer, Component, Consequence,
    Remedy, ModelYear/Make/Model.
    """
    url = f"{BASE_URL}/recalls/recallsByVehicle"

    params = {"make": make, "model": model, "modelYear": model_year}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()

    return resp.json().get("results", [])
 
 
def fetch_complaints(make: str, model: str, model_year: int) -> list[dict]:
    """Fetch complaints for a single make/model/year

    API Syntax: api.nhtsa.gov/complaints/complaintsByVehicle?make={MAKE}&model={MODEL}&modelYear={MODEL_YR}

    Confirmed field shape (2026-07-25): lowercase/camelCase keys — summary
    (free text), manufacturer, components, odiNumber, vin. NOTE: naming
    convention differs from recalls (Summary vs summary) — don't assume a
    shared key-casing scheme when writing the chunker.
    """
    url = f"{BASE_URL}/complaints/complaintsByVehicle"

    params = {"make": make, "model": model, "modelYear": model_year}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()

    return resp.json().get("results", [])


def ingest(vehicles: list[dict] = TARGET_VEHICLES) -> None:
    """Pull recalls + complaints for all target vehicles, save to data/, return a summary"""
    DATA_DIR.mkdir(exist_ok=True)

    all_recalls = []
    all_complaints = []
 
    for v in vehicles:
        tag = f"{v['make']}_{v['model']}_{v['modelYear']}".replace(" ", "-")
        logger.debug(f"Fetching {tag} ...")

        try:
            recalls = fetch_recalls(v["make"], v["model"], v["modelYear"])
            for r in recalls:
                r["vehicle_tag"] = tag
            all_recalls.extend(recalls)
        except:
            raise RuntimeError(f"Failed to fetch recalls for {tag}")

        time.sleep(0.5)  # be polite to a free public API — no documented rate limit, but don't hammer it

        try:
            complaints = fetch_complaints(v["make"], v["model"], v["modelYear"])
            for c in complaints:
                c["vehicle_tag"] = tag
            all_complaints.extend(complaints)
        except:
            raise RuntimeError(f"Failed to fetch complaints for {tag}")

        time.sleep(0.5)
 
    (DATA_DIR / "recalls.json").write_text(json.dumps(all_recalls, indent=2))
    (DATA_DIR / "complaints.json").write_text(json.dumps(all_complaints, indent=2))
 
    summary = {
        "vehicles_pulled": len(vehicles),
        "total_recalls": len(all_recalls),
        "total_complaints": len(all_complaints),
    }
    logger.debug(f"Done: {summary}")
 
 
if __name__ == "__main__":
    ingest()

