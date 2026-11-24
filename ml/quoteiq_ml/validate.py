"""Dataset checks that run before training."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quoteiq_ml.spec import FEATURE_COLUMNS, SYNTHETIC_ORIGIN, TARGETS

ROOT = Path(__file__).resolve().parents[1]


def validate(path: Path | None = None) -> dict:
    dataset = path or (ROOT / "datasets" / "synthetic_dev.csv")
    frame = pd.read_csv(dataset)
    problems = []
    for column in [*FEATURE_COLUMNS, *TARGETS, "family_id", "data_origin"]:
        if column not in frame.columns:
            problems.append(f"Missing column {column}")
        elif frame[column].isna().any():
            problems.append(f"Null values in {column}")
    if "data_origin" in frame.columns and set(frame["data_origin"].unique()) != {SYNTHETIC_ORIGIN}:
        problems.append("Dataset origin is not exclusively synthetic_dev.")
    if "unit_price" in frame.columns or "price_per_kg" in frame.columns:
        problems.append("A price column would leak into training. Remove it.")
    report = {"ok": not problems, "rows": int(len(frame)), "problems": problems, "origin": SYNTHETIC_ORIGIN}
    destination = ROOT / "artifacts"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "data_validation.json").write_text(json.dumps(report, indent=2))
    if problems:
        raise SystemExit("Data validation failed: " + "; ".join(problems))
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
