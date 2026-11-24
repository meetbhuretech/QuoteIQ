"""Deterministic cost math."""

from app.services.cost_engine import CostInput, calculate_cost


def _sample(**overrides) -> CostInput:
    values = dict(
        quantity=10,
        volume_cm3=100,
        density_g_cm3=2.7,
        unit_price_per_kg=5,
        stock_fill_ratio=1,
        scrap_allowance_pct=5,
        machine_hours_per_piece=0.5,
        machine_hourly_rate=80,
        setup_hours=1,
        setup_hourly_rate=90,
        finishing_required=False,
        finishing_hourly_rate=None,
        finishing_hours=None,
        tooling_cost=0,
        labor_hourly_rate=0,
        overhead_pct=15,
        packaging_cost=0,
        shipping_cost=0,
        profit_margin_pct=12,
        hours_per_day=8,
        shipping_days=2,
    )
    values.update(overrides)
    return CostInput(**values)


def test_complete_batch_matches_the_published_formula():
    result = calculate_cost(_sample())
    assert result.total_complete is True
    assert result.material_cost == 13.5
    assert result.machining_cost == 400
    assert result.setup_cost == 90
    assert result.finishing_cost == 0
    assert result.total == 649.38
    assert result.production_hours == 6
    assert result.lead_time_days == 3
    assert any("not a machine-learning prediction" in note for note in result.assumptions)


def test_missing_hours_do_not_invent_a_total():
    result = calculate_cost(_sample(machine_hours_per_piece=None))
    assert result.total is None
    assert result.total_complete is False
    assert "machining_hours_or_rate" in result.missing


def test_finishing_requires_hours_when_requested():
    result = calculate_cost(_sample(finishing_required=True, finishing_hourly_rate=65, finishing_hours=None))
    assert result.finishing_cost is None
    assert result.total_complete is False
