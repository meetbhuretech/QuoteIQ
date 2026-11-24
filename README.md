# QuoteIQ

QuoteIQ is a multi-tenant quotation workspace for CNC and industrial manufacturers. Engineers upload a drawing, review what was actually extracted, confirm the process and hours, and price the job from their own rates. A machine-learning estimate is advisory and is stored separately from that calculation.

## What is real

- Organizations, roles, and JWT authentication. One organization cannot read another's data.
- Drawing intake for PDF, DXF, PNG, and JPEG, with asynchronous processing.
- PDF text and title-block evidence, DXF entity geometry, and image preprocessing plus OCR when Tesseract is installed.
- Extracted values keep a source, location, method, and confidence. Missing values stay empty.
- A deterministic cost engine uses organization material prices and machine rates.
- An XGBoost training pipeline with linear and histogram-gradient baselines, a family-based holdout, MLflow logging when a tracking URI is set, and SHAP or gain importance at scoring time.
- Human verification, approval, PDF export, audit history, and historical-job comparison.
- Model import, quality gates, explicit promotion, and rollback. Synthetic models cannot be marked production-ready.

## What is not real

The training set shipped by the generator is synthetic. Its metrics describe that generator. The product says so on the model, the estimate, and the ML screens. There is no claim that a drawing parser recovers every manufacturing specification.

If no model is active, the quotation still prices from the cost engine. That fallback is labelled and is not stored as a prediction.

## Local API and web

Requirements: Python 3.12, Node.js 22, and a PostgreSQL database. Docker Compose is the full stack.

```bash
cp .env.example .env
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
# point DATABASE_URL at PostgreSQL, then:
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000, create an organization, and sign in. Sample material prices and machine rates are database rows created with the organization. Replace them in Materials and Settings before using the numbers commercially.

Set `PROCESS_INLINE=true` when you are not running the Celery worker. Compose sets it to false and runs `worker`.

## Training

From the repository root, with the backend virtualenv:

```bash
PYTHONPATH=ml backend/.venv/bin/python -m quoteiq_ml.train
PYTHONPATH=ml backend/.venv/bin/python -m quoteiq_ml.evaluate
PYTHONPATH=ml backend/.venv/bin/python -m quoteiq_ml.register
```

`register` writes a candidate manifest. It does not activate the model. In the app, an organization admin imports the local artifact and promotes it. Synthetic promotion asks for an acknowledgement and leaves `production_ready` false.

Set `MLFLOW_TRACKING_URI` before training if you want the run in MLflow. Without it, metrics are written to `ml/artifacts/experiments.json`.

DVC pipeline definition: `ml/dvc.yaml`. Dataset notes: `ml/datasets/README.md`.

## Docker

```bash
docker compose up --build
```

That starts the web app, API, worker, PostgreSQL, and Redis.

```bash
docker compose --profile mlops up --build
```

That also starts MLflow, Airflow, Prometheus, and Grafana. Change the default passwords in `.env` first. Airflow DAGs validate, train, evaluate, and register a candidate. The deployment DAG stops for a person. It does not promote a model.

## Tests

```bash
cd backend && .venv/bin/pytest
cd frontend && npm test
```

## Further reading

- [Architecture](docs/architecture.md)
- [API](docs/api.md)
- [Deployment](docs/deployment.md)
