"""Shared domain constants."""

ROLES = (
    "org_admin",
    "manufacturing_engineer",
    "sales_manager",
    "quotation_reviewer",
)

PROCESSES = ("milling", "turning", "drilling", "finishing")

DRAWING_STAGES = (
    "received",
    "validating",
    "preprocessing",
    "ocr",
    "geometry",
    "features",
    "specifications",
    "confidence",
    "awaiting_verification",
    "estimated",
    "failed",
)

QUOTATION_STATUSES = (
    "draft",
    "processing",
    "awaiting_review",
    "approved",
    "sent",
    "accepted",
    "rejected",
    "expired",
)

STATUS_TRANSITIONS = {
    "draft": {"processing", "awaiting_review", "rejected"},
    "processing": {"awaiting_review", "draft", "rejected"},
    "awaiting_review": {"approved", "rejected", "draft"},
    "approved": {"sent", "expired", "awaiting_review"},
    "sent": {"accepted", "rejected", "expired"},
    "rejected": {"draft", "awaiting_review"},
    "accepted": set(),
    "expired": {"draft"},
}

SETUP_COMPLEXITY = {"milling": 3, "turning": 2, "drilling": 1, "finishing": 2}

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

COST_TARGETS = [
    "material_cost",
    "machining_cost",
    "setup_cost",
    "finishing_cost",
    "total_cost",
    "production_hours",
]
LEAD_TIME_TARGET = "lead_time_days"

SYNTHETIC_ORIGIN = "synthetic_dev"
SYNTHETIC_LIMITATION = (
    "Trained only on synthetic development data. Metrics describe that generator, "
    "not verified factory accuracy. Do not present these estimates as production-certified."
)
