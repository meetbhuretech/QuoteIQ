"""Feature construction shared by training and inference.

The column order lives in one place. Unit price is intentionally absent so model
code cannot treat a supplier price as a learned feature.
"""

from __future__ import annotations

from app.domain.constants import FEATURE_COLUMNS, SETUP_COMPLEXITY


def to_millimetres(value: float, units: str) -> float | None:
    if units == "mm":
        return value
    if units == "in":
        return value * 25.4
    return None


def bounding_volume_cm3(length_mm: float, width_mm: float, height_mm: float, fill_ratio: float) -> float:
    return (length_mm / 10.0) * (width_mm / 10.0) * (height_mm / 10.0) * fill_ratio


def bounding_surface_cm2(length_mm: float, width_mm: float, height_mm: float) -> float:
    length_cm = length_mm / 10.0
    width_cm = width_mm / 10.0
    height_cm = height_mm / 10.0
    return 2.0 * (length_cm * width_cm + length_cm * height_cm + width_cm * height_cm)


def geometric_complexity(hole_count: int, feature_count: int, tolerance_count: int) -> float:
    score = 1.0 + 0.15 * feature_count + 0.2 * hole_count + 0.25 * tolerance_count
    return round(min(10.0, score), 4)


def build_features(
    *,
    material_category: str | None,
    density: float | None,
    units: str | None,
    length: float | None,
    width: float | None,
    height: float | None,
    quantity: int | None,
    process: str | None,
    machine_category: str | None,
    hole_count: int | None,
    feature_count: int | None,
    tolerance_count: int,
    finishing_required: bool | None,
    setup_complexity: int | None,
    volume_cm3: float | None,
    stock_fill_ratio: float,
) -> tuple[dict | None, list[str], list[str]]:
    """Return a feature row, missing fields, and assumptions.

    Nothing is imputed. A missing confirmation blocks the feature row.
    """

    missing: list[str] = []
    assumptions: list[str] = []
    if not material_category:
        missing.append("material_category")
    if density is None:
        missing.append("density")
    if units not in {"mm", "in"}:
        missing.append("units")
    if length is None or width is None or height is None:
        missing.append("bounding_box_dimensions")
    if quantity is None or quantity < 1:
        missing.append("quantity")
    if process not in SETUP_COMPLEXITY:
        missing.append("manufacturing_process")
    if not machine_category:
        missing.append("machine_category")
    if hole_count is None:
        missing.append("hole_count")
    if feature_count is None:
        missing.append("feature_count")
    if finishing_required is None:
        missing.append("finishing_required")
    if missing:
        return None, missing, assumptions

    length_mm = to_millimetres(length, units)
    width_mm = to_millimetres(width, units)
    height_mm = to_millimetres(height, units)
    if length_mm is None or width_mm is None or height_mm is None:
        return None, ["units"], assumptions

    if volume_cm3 is None:
        volume = bounding_volume_cm3(length_mm, width_mm, height_mm, stock_fill_ratio)
        assumptions.append(
            "volume_cm3 is the bounding box times the organization stock fill ratio, not a measured solid volume."
        )
    else:
        volume = volume_cm3
        assumptions.append("volume_cm3 is the engineer-confirmed volume.")

    surface = bounding_surface_cm2(length_mm, width_mm, height_mm)
    assumptions.append(
        "surface_area_cm2 is the bounding-box surface computed from confirmed dimensions, not a CAD surface area."
    )
    complexity_value = setup_complexity if setup_complexity is not None else SETUP_COMPLEXITY[process]
    if setup_complexity is None:
        assumptions.append(
            f"setup_complexity defaulted to {complexity_value} from the confirmed process map. An engineer can override it."
        )

    features = {
        "density": float(density),
        "volume_cm3": float(volume),
        "length_mm": float(length_mm),
        "width_mm": float(width_mm),
        "height_mm": float(height_mm),
        "surface_area_cm2": float(surface),
        "hole_count": int(hole_count),
        "feature_count": int(feature_count),
        "geometric_complexity": geometric_complexity(int(hole_count), int(feature_count), tolerance_count),
        "quantity": int(quantity),
        "setup_complexity": int(complexity_value),
        "finishing_required": 1 if finishing_required else 0,
        "material_category": material_category,
        "manufacturing_process": process,
        "machine_category": machine_category,
    }
    ordered = {column: features[column] for column in FEATURE_COLUMNS}
    return ordered, [], assumptions
