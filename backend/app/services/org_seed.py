"""Sample manufacturing catalog copied into each new organization.

Prices and rates live in the database. They are sample starting values, not
model constants, and administrators are expected to replace them.
"""

from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Machine, MachineRate, ManufacturingProcess, Material, MaterialPrice, OrganizationCostSettings

SAMPLE_NOTE = "Sample value created with the organization. Replace it with a supplier or shop rate before commercial use."

MATERIALS = [
    ("Aluminium 6061", "aluminium", 2.70, 4.80),
    ("Aluminium 7075", "aluminium", 2.81, 6.40),
    ("Mild Steel", "mild_steel", 7.85, 1.70),
    ("Stainless Steel 304", "stainless_steel", 8.00, 5.40),
    ("Stainless Steel 316", "stainless_steel", 8.00, 6.90),
    ("Brass", "brass", 8.50, 7.20),
    ("Copper", "copper", 8.96, 9.10),
]

PROCESSES = [
    ("Milling", "milling", "CNC milling. Confirm the actual setup before quoting.", 85, 95),
    ("Turning", "turning", "CNC turning. A cylindrical feature does not by itself prove this is the process.", 78, 90),
    ("Drilling", "drilling", "Drilling and related holemaking. Circle geometry is only a candidate.", 80, 70),
    ("Finishing", "finishing", "Basic finishing. Confirm the required finish before applying this rate.", 65, 40),
]


def seed_organization(db: Session, organization_id: UUID, actor_id: UUID | None) -> None:
    today = date.today()
    for name, category, density, price in MATERIALS:
        material = Material(
            organization_id=organization_id,
            name=name,
            category=category,
            density=density,
            availability="unknown",
            notes=SAMPLE_NOTE,
        )
        db.add(material)
        db.flush()
        db.add(
            MaterialPrice(
                organization_id=organization_id,
                material_id=material.id,
                unit_price=price,
                currency="USD",
                supplier="Sample supplier",
                effective_date=today,
                notes=SAMPLE_NOTE,
                created_by=actor_id,
            )
        )
    for name, category, description, hourly, setup in PROCESSES:
        process = ManufacturingProcess(
            organization_id=organization_id,
            name=name,
            category=category,
            description=description,
        )
        db.add(process)
        db.flush()
        db.add(
            MachineRate(
                organization_id=organization_id,
                process_id=process.id,
                hourly_rate=hourly,
                setup_hourly_rate=setup,
                currency="USD",
                effective_date=today,
                notes=SAMPLE_NOTE,
            )
        )
    for name, category in (("3-Axis VMC", "milling"), ("CNC Lathe", "turning")):
        db.add(Machine(organization_id=organization_id, name=name, category=category, notes=SAMPLE_NOTE, is_active=True))
    db.add(
        OrganizationCostSettings(
            organization_id=organization_id,
            currency="USD",
            scrap_allowance_pct=5,
            tooling_cost=0,
            labor_hourly_rate=0,
            overhead_pct=15,
            packaging_cost=0,
            shipping_cost=0,
            profit_margin_pct=12,
            default_setup_hours=1,
            hours_per_day=8,
            shipping_days=2,
            stock_fill_ratio=1,
            default_validity_days=30,
        )
    )
