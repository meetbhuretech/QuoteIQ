"""Synthetic development jobs.

GENERATOR_PRICE and the rate tables below exist only to label this dataset.
Inference and the cost engine must not import this module.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from quoteiq_ml.spec import FEATURE_COLUMNS, SYNTHETIC_ORIGIN, WARNING

GENERATOR_PRICE = {
    "aluminium": 4.6,
    "mild_steel": 1.8,
    "stainless_steel": 5.8,
    "brass": 7.1,
    "copper": 9.2,
}
DENSITY = {
    "aluminium": 2.70,
    "mild_steel": 7.85,
    "stainless_steel": 8.00,
    "brass": 8.50,
    "copper": 8.96,
}
MACHINE_RATE = {"milling": 85.0, "turning": 78.0, "drilling": 80.0, "finishing": 65.0}
SETUP_RATE = {"milling": 95.0, "turning": 90.0, "drilling": 70.0, "finishing": 40.0}
SETUP_COMPLEXITY = {"milling": 3, "turning": 2, "drilling": 1, "finishing": 2}
REMOVAL = {"milling": 0.012, "turning": 0.009, "drilling": 0.004, "finishing": 0.003}


def generate(rows_per_family: int = 4, families: int = 800, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    materials = list(GENERATOR_PRICE)
    processes = list(MACHINE_RATE)
    quantities = np.array([1, 10, 25, 100])
    records = []
    for family in range(families):
        material = materials[int(rng.integers(0, len(materials)))]
        process = processes[int(rng.integers(0, len(processes)))]
        length = float(rng.uniform(20, 400))
        width = float(rng.uniform(10, 250))
        height = float(rng.uniform(5, 120))
        fill = float(rng.uniform(0.35, 1.0))
        holes = int(rng.integers(0, 12))
        feature_count = int(rng.integers(1, 16))
        tolerance_count = int(rng.integers(0, 5))
        finishing = int(rng.integers(0, 2))
        volume = (length / 10) * (width / 10) * (height / 10) * fill
        surface = 2 * ((length / 10) * (width / 10) + (length / 10) * (height / 10) + (width / 10) * (height / 10))
        complexity = min(10.0, 1 + 0.15 * feature_count + 0.2 * holes + 0.25 * tolerance_count)
        setup_complexity = SETUP_COMPLEXITY[process]
        density = DENSITY[material]
        machine_hours = max(0.05, REMOVAL[process] * (volume ** 0.65) * (1 + 0.04 * holes) * (complexity / 3))
        setup_hours = 0.35 * setup_complexity
        finishing_hours = 0.15 * complexity if finishing else 0.0
        for quantity in quantities[:rows_per_family]:
            noise = lambda: max(0.4, float(rng.normal(1.0, 0.12)))
            weight = volume * density / 1000.0 * int(quantity)
            material_cost = weight * GENERATOR_PRICE[material] * noise()
            machining_cost = machine_hours * int(quantity) * MACHINE_RATE[process] * noise()
            setup_cost = setup_hours * SETUP_RATE[process] * noise()
            finishing_cost = finishing_hours * MACHINE_RATE["finishing"] * (noise() if finishing else 1)
            production_hours = setup_hours + machine_hours * int(quantity) + finishing_hours
            total_cost = material_cost + machining_cost + setup_cost + finishing_cost
            lead_time = max(1.0, production_hours / 8.0 + 2 + float(rng.normal(0, 0.4)))
            records.append(
                {
                    "family_id": f"family-{family:04d}",
                    "data_origin": SYNTHETIC_ORIGIN,
                    "generation_note": WARNING,
                    "density": density,
                    "volume_cm3": volume,
                    "length_mm": length,
                    "width_mm": width,
                    "height_mm": height,
                    "surface_area_cm2": surface,
                    "hole_count": holes,
                    "feature_count": feature_count,
                    "geometric_complexity": complexity,
                    "quantity": int(quantity),
                    "setup_complexity": setup_complexity,
                    "finishing_required": finishing,
                    "material_category": material,
                    "manufacturing_process": process,
                    "machine_category": process,
                    "material_cost": material_cost,
                    "machining_cost": machining_cost,
                    "setup_cost": setup_cost,
                    "finishing_cost": finishing_cost,
                    "total_cost": total_cost,
                    "production_hours": production_hours,
                    "lead_time_days": lead_time,
                }
            )
    frame = pd.DataFrame.from_records(records)
    missing = [column for column in FEATURE_COLUMNS if column not in frame.columns]
    if missing:
        raise RuntimeError(f"Generator dropped feature columns: {missing}")
    return frame


if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[1] / "datasets" / "synthetic_dev.csv"
    generated = write_dataset(destination)
    print(f"Wrote {len(generated)} rows labelled {SYNTHETIC_ORIGIN} to {destination}")


def write_dataset(path: Path, **kwargs) -> pd.DataFrame:
    frame = generate(**kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame
