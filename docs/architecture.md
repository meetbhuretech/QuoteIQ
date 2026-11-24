# Architecture

QuoteIQ is a monorepo with four planes. They share PostgreSQL and object storage. Training code is not imported by the API.

| Plane | Code | Responsibility |
|---|---|---|
| Experience | `frontend/` | Next.js workspace. Calls the API only. |
| Application | `backend/app/api`, `backend/app/services` | Auth, tenancy, quotations, cost engine, audit. |
| Intelligence | `backend/app/services/processors.py`, `inference.py`, `workers/` | Drawing processors and model scoring. |
| Learning | `ml/quoteiq_ml`, `pipelines/dags` | Synthetic data, training, evaluation, Airflow. |

Route handlers validate input and call a service. Cost formulas live in `cost_engine.py` and receive prices as arguments. `inference.py` loads joblib pipelines and does not import `quoteiq_ml.train` or the generator.

## Tenancy

`organization_id` is on every tenant table. The organization on a normal request comes from the membership stored for the JWT subject. A body field cannot select another tenant. Super admins must pass `X-Organization-Id`. Roles are organization admin, manufacturing engineer, sales manager, and quotation reviewer. Organization admins can perform every organization action.

## Drawing path

Upload stores the file, commits a `drawings` row, and returns. A Celery worker, or an in-process thread when `PROCESS_INLINE=true`, runs validation, preprocessing, OCR or DXF reading, geometry, features, specification, and confidence. The job then waits. Estimation is a later, explicit call after an engineer verifies required fields.

PDF text is read with PyMuPDF. A value whose block sits in the lower-right of the page is tagged as a title-block candidate. DXF uses ezdxf for entities, extents, and text. Circles are counted as candidates, not as drilled holes. Images are thresholded with OpenCV and passed to Tesseract when the binary exists. If OCR is unavailable, the specification stays empty and says so.

Automatic confidence is capped at 0.8. Verification writes a separate evidence row with method `human_entry`. Editing a verified specification clears verification until it is marked again.

## Money and models

The commercial total is deterministic:

- material = bounding-box volume × stock fill ratio × density × quantity × database unit price
- scrap, machining, setup, finishing, labor, tooling, packaging, shipping, overhead, and profit follow the organization settings
- machine hours and setup hours come from the engineer, not from a silent geometry rule

The model, when an active version exists and the feature row is complete, predicts cost components, hours, and lead time. Those rows are stored with `kind=ml`. The quotation line total remains the deterministic total. A missing or unhealthy model stores a fallback reason and does not emit ML components.

Feature columns are listed once in `backend/app/domain/constants.py` and `ml/quoteiq_ml/spec.py`. Unit price is not a feature. Training splits by `family_id` so quantity variants of one generated part do not cross the holdout. Regressors fit `log1p` of each target because part cost spans several orders of magnitude. Saved pipelines still emit the log value; scoring applies `expm1` and clips at zero. MAE, RMSE, R², and MAPE in `metadata.json` are on that original scale.

## Models

Training writes artifacts and `metadata.json`. Import creates a candidate for the current organization. Promotion checks row count, holdout R², and MAPE when MAPE is defined, then requires a person. Synthetic training can be activated only after acknowledgement and stays `production_ready=false`. Rollback points the active stage at an older registered version.

Airflow orchestrates dataset validation, feature generation, training, evaluation, registration, a weekly retrain, and a deployment DAG that does not promote. Evidently writes a drift report when it is installed. The report text separates distribution shift from holdout error.

## Storage and operations

`Storage` is local disk or S3-compatible object storage, keyed by organization id. Prometheus scrapes `/metrics`. Grafana is provisioned in the mlops Compose profile. Secrets stay in the environment.
