"""Feature contract for training. Keep this list identical to the backend contract."""

FEATURE_COLUMNS = [
    "density",
    "volume_cm3",
    "length_mm",
    "width_mm",
    "height_mm",
    "surface_area_cm2",
    "hole_count",
    "feature_count",
    "geometric_complexity",
    "quantity",
    "setup_complexity",
    "finishing_required",
    "material_category",
    "manufacturing_process",
    "machine_category",
]

CATEGORICAL_FEATURES = ["material_category", "manufacturing_process", "machine_category"]
NUMERIC_FEATURES = [column for column in FEATURE_COLUMNS if column not in CATEGORICAL_FEATURES]

TARGETS = [
    "material_cost",
    "machining_cost",
    "setup_cost",
    "finishing_cost",
    "total_cost",
    "production_hours",
    "lead_time_days",
]

SYNTHETIC_ORIGIN = "synthetic_dev"
WARNING = (
    "SYNTHETIC DEVELOPMENT DATA. Generated from a documented formula plus noise. "
    "These rows are not factory jobs and must not be described as verified manufacturing accuracy."
)
