# Deployment

## Local stack

```bash
cp .env.example .env
# Set JWT_SECRET, POSTGRES_PASSWORD, AIRFLOW_PASSWORD, and GRAFANA_ADMIN_PASSWORD.
docker compose up --build
```

The API listens on port 8000 and the web app on port 3000. Alembic runs before Uvicorn. Drawing jobs run in the `worker` service.

```bash
docker compose --profile mlops up --build
```

| Service | Port | Notes |
|---|---|---|
| MLflow | 5000 | SQLite backend in a volume. Development tracking. |
| Airflow | 8080 | LocalExecutor. DAGs are paused on creation. |
| Prometheus | 9090 | Scrapes the API `/metrics` endpoint. |
| Grafana | 3001 | Admin password from the environment. |

Do not expose the default passwords. The Compose file is a local and staging starting point, not a locked-down production network.

## Production notes

- Set `ENVIRONMENT=production`. The API refuses to boot when `JWT_SECRET` is still the sample value.
- Use `STORAGE_BACKEND=s3` with `S3_ENDPOINT_URL`, `S3_BUCKET`, and credentials. Keys are prefixed by organization id.
- Run PostgreSQL and Redis as managed services. Keep the API and the Celery worker on separate processes that share the same storage.
- Put the web app behind TLS. `NEXT_PUBLIC_API_URL` must be the public API origin because the browser calls it directly.
- Build images from `backend/Dockerfile` and `frontend/Dockerfile`. The frontend container in Compose runs the development server so local edits reload. For production, run `npm run build` and `npm start`.
- Train with `PYTHONPATH=ml python -m quoteiq_ml.train`, evaluate, and register a candidate. Promotion stays an authenticated API call by an organization admin.
- Do not auto-promote from Airflow. The deployment DAG only records that a person must approve.
- Synthetic artifacts can be activated for a demo. `production_ready` remains false. Replace them with a model trained on verified jobs, with actual costs, before treating estimates as factory accuracy.
- Back up PostgreSQL and the object store. Model artifacts should be versioned next to the MLflow or local artifact directory recorded on `model_versions.artifact_path`.

## CI

`.github/workflows/ci.yml` installs Python 3.12 and runs pytest, installs the frontend and runs lint plus Vitest, and builds the API and web images.
