"""Authentication, tenancy, quotation flow, and model promotion."""

from pathlib import Path

import fitz

from app.services.model_registry import evaluate_gates


def test_registration_login_and_organization_isolation(client):
    from tests.conftest import auth

    headers, _ = auth(client)
    other, _ = auth(client, email="bea@example.com", organization="Bea Metals", name="Bea Sales")
    created = client.post("/api/v1/customers", headers=headers, json={"name": "Northwind", "company": "Northwind Components"})
    assert created.status_code == 201
    customer_id = created.json()["id"]
    hidden = client.get(f"/api/v1/customers/{customer_id}", headers=other)
    assert hidden.status_code == 404
    listing = client.get("/api/v1/customers", headers=other)
    assert listing.json()["total"] == 0
    weak = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "short", "full_name": "Weak User", "organization_name": "Weak Org"},
    )
    assert weak.status_code == 422
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["role"] == "org_admin"
    assert me.json()["organization"]["name"] == "Ada CNC"


def test_dashboard_is_empty_until_real_records_exist(client):
    from tests.conftest import auth

    headers, _ = auth(client)
    dashboard = client.get("/api/v1/dashboard", headers=headers).json()
    assert dashboard["total_quotation_requests"] == 0
    assert dashboard["estimation_accuracy_mape"] is None
    assert dashboard["approval_rate"] is None
    assert dashboard["monthly_volume"] == []
    assert dashboard["accuracy_scope"] == "verified_operational_jobs_only"


def test_drawing_to_approved_quotation_uses_fallback_without_a_model(client, tmp_path: Path):
    from tests.conftest import auth

    headers, _ = auth(client)
    customer = client.post("/api/v1/customers", headers=headers, json={"name": "Helix", "company": "Helix Automotive"}).json()
    quotation = client.post("/api/v1/quotations", headers=headers, json={"customer_id": customer["id"], "notes": "Prototype bracket"}).json()
    pdf_path = tmp_path / "bracket.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(
        fitz.Rect(40, 40, 500, 400),
        "PART NAME: BRACKET\nDRAWING NUMBER: BR-100\nMATERIAL: ALUMINIUM 6061\nUNITS: MM\nQTY: 12\n120 x 80 x 25\nDIA 10\n±0.1\nNOTE: DEBURR EDGES",
    )
    document.save(pdf_path)
    document.close()
    with pdf_path.open("rb") as handle:
        uploaded = client.post(
            "/api/v1/drawings/upload",
            headers=headers,
            files={"file": ("bracket.pdf", handle, "application/pdf")},
            data={"quotation_id": quotation["quotation"]["id"], "customer_id": customer["id"]},
        )
    assert uploaded.status_code == 201, uploaded.text
    drawing_id = uploaded.json()["id"]
    detail = client.get(f"/api/v1/drawings/{drawing_id}", headers=headers).json()
    assert detail["drawing"]["status"] == "awaiting_verification"
    spec = detail["specification"]
    assert spec["material"] == "Aluminium 6061"
    assert spec["length"] == 120
    assert any(item["method"] == "human_entry" or item["confidence"] <= 0.8 for item in detail["evidence"])
    materials = client.get("/api/v1/materials", headers=headers).json()
    material_id = next(item["material"]["id"] for item in materials if item["material"]["name"] == "Aluminium 6061")
    blocked = client.post("/api/v1/estimation", headers=headers, json={"drawing_id": drawing_id})
    assert blocked.status_code == 422
    verified = client.patch(
        f"/api/v1/analysis/{spec['id']}/verify",
        headers=headers,
        json={
            "material_id": material_id,
            "units": "mm",
            "length": 120,
            "width": 80,
            "height": 25,
            "quantity": 12,
            "confirmed_process": "milling",
            "confirmed_machine_category": "milling",
            "confirmed_machine_hours": 0.4,
            "confirmed_setup_hours": 1,
            "confirmed_hole_count": 4,
            "confirmed_feature_count": 6,
            "finishing_required": False,
            "mark_verified": True,
            "note": "Confirmed title block and overall size.",
        },
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verification_status"] == "verified"
    estimation = client.post("/api/v1/estimation", headers=headers, json={"drawing_id": drawing_id})
    assert estimation.status_code == 201, estimation.text
    body = estimation.json()["estimation"]
    assert body["ml_is_prediction"] is False
    assert "not machine-learning" in body["disclaimer"].lower() or "no active model" in body["disclaimer"].lower()
    assert body["deterministic_complete"] is True
    assert any(component["kind"] == "deterministic" and component["code"] == "material" for component in estimation.json()["components"])
    assert not any(component["kind"] == "ml" for component in estimation.json()["components"])
    quote = client.get(f"/api/v1/quotations/{quotation['quotation']['id']}", headers=headers).json()
    assert quote["quotation"]["status"] == "awaiting_review"
    assert quote["items"][0]["total"] == body["deterministic_total"]
    approved = client.post(f"/api/v1/quotations/{quotation['quotation']['id']}/approve", headers=headers, json={"comment": "Checked the breakdown."})
    assert approved.status_code == 200, approved.text
    assert approved.json()["quotation"]["status"] == "approved"
    pdf = client.get(f"/api/v1/quotations/{quotation['quotation']['id']}/pdf", headers=headers)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert b"REVIEW COPY" not in pdf.content


def test_sales_user_cannot_promote_a_model(client):
    from tests.conftest import auth

    headers, _ = auth(client)
    created = client.post(
        "/api/v1/organizations/members",
        headers=headers,
        json={"email": "sam@example.com", "full_name": "Sam Sales", "password": "sales-pass-1", "role": "sales_manager"},
    )
    assert created.status_code == 201, created.text
    login = client.post("/api/v1/auth/login", json={"email": "sam@example.com", "password": "sales-pass-1"})
    sales_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    denied = client.post("/api/v1/ml/models/import-local", headers=sales_headers)
    assert denied.status_code == 403


def test_gates_reject_small_or_weak_models():
    passed, reasons = evaluate_gates({"total_cost": {"r2": 0.2, "mape": 10, "mape_defined": True}}, 1000)
    assert passed is False
    assert reasons
    passed, reasons = evaluate_gates({"total_cost": {"r2": 0.8, "mape": 12, "mape_defined": True}}, 80)
    assert passed is False


def test_synthetic_model_can_be_activated_only_with_acknowledgement(client):
    from tests.conftest import auth

    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2] / "ml"))
    from quoteiq_ml.train import train

    metadata = train(families=130, rows_per_family=4, estimators=40)
    assert metadata["data_origin"] == "synthetic_dev"
    assert metadata["production_ready"] is False
    assert metadata["metrics"]["total_cost"]["r2"] >= 0.5
    headers, _ = auth(client, email="ml@example.com", organization="Model Shop", name="Mina Learning")
    imported = client.post("/api/v1/ml/models/import-local", headers=headers)
    assert imported.status_code == 200, imported.text
    model = imported.json()
    assert model["is_synthetic_training"] is True
    assert model["production_ready"] is False
    assert model["stage"] == "candidate"
    blocked = client.post(f"/api/v1/ml/models/{model['id']}/promote", headers=headers, json={"acknowledge_limitations": False})
    assert blocked.status_code == 422
    promoted = client.post(f"/api/v1/ml/models/{model['id']}/promote", headers=headers, json={"acknowledge_limitations": True})
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["stage"] == "active"
    assert promoted.json()["production_ready"] is False
    active = client.get("/api/v1/ml/models/active", headers=headers).json()
    assert active["health"]["ok"] is True
    experiments = client.get("/api/v1/ml/experiments", headers=headers).json()
    assert experiments["experiments"]
    assert experiments["experiments"][0]["source"] == "local_file"


def test_dag_files_do_not_auto_promote():
    dag_dir = Path(__file__).resolve().parents[2] / "pipelines" / "dags"
    sources = {path.name: path.read_text() for path in dag_dir.glob("*.py")}
    expected = {
        "data_validation.py": "quoteiq_data_validation",
        "feature_engineering.py": "quoteiq_feature_engineering",
        "model_training.py": "quoteiq_model_training",
        "model_evaluation.py": "quoteiq_model_evaluation",
        "model_registration.py": "quoteiq_model_registration",
        "scheduled_retraining.py": "quoteiq_scheduled_retraining",
        "model_deployment_approval.py": "quoteiq_model_deployment_approval",
    }
    for name, dag_id in expected.items():
        assert dag_id in sources[name]
    assert "does not promote" in sources["model_deployment_approval.py"]
