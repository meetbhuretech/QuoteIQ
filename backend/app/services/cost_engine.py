"""Deterministic quotation math.

Rates and prices are inputs. This module does not read the database and does not
call a machine-learning model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def money(value: float) -> float:
    return round(float(value) + 0.0, 2)


@dataclass(frozen=True)
class CostInput:
    quantity: int
    volume_cm3: float | None
    density_g_cm3: float | None
    unit_price_per_kg: float | None
    stock_fill_ratio: float
    scrap_allowance_pct: float
    machine_hours_per_piece: float | None
    machine_hourly_rate: float | None
    setup_hours: float | None
    setup_hourly_rate: float | None
    finishing_required: bool | None
    finishing_hourly_rate: float | None
    finishing_hours: float | None
    tooling_cost: float
    labor_hourly_rate: float
    overhead_pct: float
    packaging_cost: float
    shipping_cost: float
    profit_margin_pct: float
    hours_per_day: float
    shipping_days: int


@dataclass
class CostLine:
    code: str
    label: str
    amount: float | None
    formula: str
    inputs: dict
    complete: bool


@dataclass
class CostResult:
    lines: list[CostLine] = field(default_factory=list)
    total: float | None = None
    total_complete: bool = False
    assumptions: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    production_hours: float | None = None
    lead_time_days: float | None = None
    material_cost: float | None = None
    machining_cost: float | None = None
    setup_cost: float | None = None
    finishing_cost: float | None = None
    additional_cost: float | None = None
    profit_amount: float | None = None


def _line(code: str, label: str, amount: float | None, formula: str, inputs: dict, complete: bool) -> CostLine:
    return CostLine(
        code=code,
        label=label,
        amount=None if amount is None else money(amount),
        formula=formula,
        inputs=inputs,
        complete=complete,
    )


def calculate_cost(inp: CostInput) -> CostResult:
    """Price one batch from confirmed inputs and organization rates.

    Material mass uses bounding-box volume times the configured stock fill ratio.
    That is an envelope assumption, not a net-shape solid. Setup is charged once
    per batch. Machine time is per piece.
    """

    result = CostResult()
    result.assumptions = [
        "Material mass uses bounding-box volume × stock fill ratio. It is not a net-shape weight.",
        "Setup cost is charged once per batch. Machining hours are per piece and then multiplied by quantity.",
        "Labor is separate from the machine hourly rate. A labor rate of zero means labor is already inside the machine rate.",
        "Overhead is a percentage of the direct subtotal. Profit is a percentage of direct subtotal plus overhead.",
        "This total is a deterministic calculation. It is not a machine-learning prediction.",
    ]
    if inp.quantity < 1:
        result.missing.append("quantity")

    weight = None
    if inp.volume_cm3 is not None and inp.density_g_cm3 is not None and inp.stock_fill_ratio > 0 and inp.quantity >= 1:
        weight = inp.volume_cm3 * inp.stock_fill_ratio * inp.density_g_cm3 / 1000.0 * inp.quantity
    else:
        result.missing.append("material_weight")

    material = None
    if weight is not None and inp.unit_price_per_kg is not None:
        material = weight * inp.unit_price_per_kg
    elif "material_weight" not in result.missing:
        result.missing.append("material_price")
    result.material_cost = None if material is None else money(material)
    result.lines.append(
        _line(
            "material",
            "Material",
            material,
            "bounding_box_volume_cm3 × stock_fill_ratio × density_g_per_cm3 / 1000 × quantity × price_per_kg",
            {
                "volume_cm3": inp.volume_cm3,
                "stock_fill_ratio": inp.stock_fill_ratio,
                "density_g_cm3": inp.density_g_cm3,
                "quantity": inp.quantity,
                "unit_price_per_kg": inp.unit_price_per_kg,
                "weight_kg": None if weight is None else round(weight, 4),
            },
            material is not None,
        )
    )

    scrap = None if material is None else material * inp.scrap_allowance_pct / 100.0
    result.lines.append(
        _line(
            "scrap",
            "Scrap allowance",
            scrap,
            "material_cost × scrap_allowance_pct / 100",
            {"scrap_allowance_pct": inp.scrap_allowance_pct},
            scrap is not None,
        )
    )

    machining = None
    if inp.machine_hours_per_piece is not None and inp.machine_hourly_rate is not None and inp.quantity >= 1:
        machining = inp.machine_hours_per_piece * inp.quantity * inp.machine_hourly_rate
    else:
        result.missing.append("machining_hours_or_rate")
    result.machining_cost = None if machining is None else money(machining)
    result.lines.append(
        _line(
            "machining",
            "Machining",
            machining,
            "machine_hours_per_piece × quantity × machine_hourly_rate",
            {
                "machine_hours_per_piece": inp.machine_hours_per_piece,
                "quantity": inp.quantity,
                "machine_hourly_rate": inp.machine_hourly_rate,
            },
            machining is not None,
        )
    )

    setup = None
    if inp.setup_hours is not None and inp.setup_hourly_rate is not None:
        setup = inp.setup_hours * inp.setup_hourly_rate
    else:
        result.missing.append("setup_hours_or_rate")
    result.setup_cost = None if setup is None else money(setup)
    result.lines.append(
        _line(
            "setup",
            "Setup",
            setup,
            "setup_hours × setup_hourly_rate",
            {"setup_hours": inp.setup_hours, "setup_hourly_rate": inp.setup_hourly_rate},
            setup is not None,
        )
    )

    finishing = None
    if inp.finishing_required is False:
        finishing = 0.0
    elif inp.finishing_required is True and inp.finishing_hours is not None and inp.finishing_hourly_rate is not None:
        finishing = inp.finishing_hours * inp.finishing_hourly_rate
    else:
        result.missing.append("finishing")
    result.finishing_cost = None if finishing is None else money(finishing)
    result.lines.append(
        _line(
            "finishing",
            "Finishing",
            finishing,
            "0 when finishing is not required; otherwise finishing_hours × finishing_hourly_rate",
            {
                "finishing_required": inp.finishing_required,
                "finishing_hours": inp.finishing_hours,
                "finishing_hourly_rate": inp.finishing_hourly_rate,
            },
            finishing is not None,
        )
    )

    if inp.finishing_required is False:
        finish_hours = 0.0
    elif inp.finishing_required is True and inp.finishing_hours is not None:
        finish_hours = inp.finishing_hours
    else:
        finish_hours = None
    hours = None
    if (
        inp.setup_hours is not None
        and inp.machine_hours_per_piece is not None
        and inp.quantity >= 1
        and finish_hours is not None
    ):
        hours = inp.setup_hours + (inp.machine_hours_per_piece * inp.quantity) + finish_hours
    result.production_hours = None if hours is None else round(hours, 3)

    labor = None
    if inp.labor_hourly_rate == 0 and hours is not None:
        labor = 0.0
    elif inp.labor_hourly_rate > 0 and hours is not None:
        labor = hours * inp.labor_hourly_rate
    elif inp.labor_hourly_rate > 0:
        result.missing.append("production_hours_for_labor")
    else:
        labor = 0.0 if hours is not None or inp.labor_hourly_rate == 0 else None
    result.lines.append(
        _line(
            "labor",
            "Labor",
            labor,
            "production_hours × labor_hourly_rate",
            {"production_hours": result.production_hours, "labor_hourly_rate": inp.labor_hourly_rate},
            labor is not None,
        )
    )

    for code, label, amount in (
        ("tooling", "Tooling", inp.tooling_cost),
        ("packaging", "Packaging", inp.packaging_cost),
        ("shipping", "Shipping", inp.shipping_cost),
    ):
        result.lines.append(_line(code, label, amount, f"organization setting {code}_cost", {code: amount}, True))

    direct_parts = [material, scrap, machining, setup, finishing, labor, inp.tooling_cost, inp.packaging_cost, inp.shipping_cost]
    direct_complete = all(part is not None for part in direct_parts)
    direct = sum(direct_parts) if direct_complete else None
    additional = None
    if scrap is not None and labor is not None:
        additional = scrap + labor + inp.tooling_cost + inp.packaging_cost + inp.shipping_cost
    result.additional_cost = None if additional is None else money(additional)

    overhead = None if direct is None else direct * inp.overhead_pct / 100.0
    result.lines.append(
        _line(
            "overhead",
            "Overhead",
            overhead,
            "direct_subtotal × overhead_pct / 100",
            {"overhead_pct": inp.overhead_pct},
            overhead is not None,
        )
    )
    profit = None if direct is None or overhead is None else (direct + overhead) * inp.profit_margin_pct / 100.0
    result.profit_amount = None if profit is None else money(profit)
    result.lines.append(
        _line(
            "profit",
            "Profit margin",
            profit,
            "(direct_subtotal + overhead) × profit_margin_pct / 100",
            {"profit_margin_pct": inp.profit_margin_pct},
            profit is not None,
        )
    )
    if direct is not None and overhead is not None and profit is not None:
        result.total = money(direct + overhead + profit)
        result.total_complete = True
    else:
        result.total = None
        result.total_complete = False

    if result.production_hours is not None and inp.hours_per_day > 0:
        result.lead_time_days = math.ceil(result.production_hours / inp.hours_per_day) + inp.shipping_days
        result.assumptions.append(
            "Deterministic lead time is production hours divided by hours per day, rounded up, plus shipping days. It is not the lead-time model."
        )
    else:
        result.missing.append("lead_time_inputs")
    return result
