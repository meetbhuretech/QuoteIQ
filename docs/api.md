# HTTP API

Interactive schemas are served at `/docs` when the API is running. All routes below are under `/api/v1` except health.

| Method | Path | Who |
|---|---|---|
| POST | `/auth/register` | Public. Creates a user, organization, and sample catalog. |
| POST | `/auth/login` | Public. Returns a bearer token. |
| POST | `/auth/logout` | Any user. Client discards the token. |
| GET | `/auth/me` | Any user. |
| GET | `/customers` | Any member. Pagination via `page` and `page_size`. |
| POST | `/customers` | Sales, engineer, or admin. |
| GET | `/customers/{id}` | Any member of that organization. Other organizations receive 404. |
| POST | `/drawings/upload` | Multipart `file`, optional `customer_id` and `quotation_id`. |
| GET | `/drawings/{id}` | Drawing, specification, and evidence. |
| GET | `/drawings/{id}/status` | Stage history. |
| GET | `/drawings/{id}/file` | Original file. |
| GET | `/drawings/{id}/preview` | Rendered preview when one exists. |
| POST | `/analysis/{drawing_id}` | Re-run processing. Engineer or admin. |
| GET | `/analysis/{specification_id}` | Specification and evidence. |
| PATCH | `/analysis/{specification_id}/verify` | Engineer corrections. `mark_verified` fails while required fields are missing. |
| POST | `/estimation` | Body `{ "drawing_id" }`. Requires a verified specification. |
| GET | `/estimation/{id}` | Deterministic components and any ML components. |
| POST | `/estimation/{id}/recalculate` | New estimation from the current specification. |
| POST | `/quotations` | Draft quotation. |
| GET | `/quotations` and `/quotations/{id}` | List and detail. |
| POST | `/quotations/{id}/approve` | Reviewer or admin. Blocked until every line is complete and verified. |
| POST | `/quotations/{id}/reject` | Comment required. |
| POST | `/quotations/{id}/send` | Only after approval. |
| POST | `/quotations/{id}/accept` | Creates operational jobs. Those jobs are not training candidates. |
| GET | `/quotations/{id}/pdf` | PDF. Unapproved quotes are watermarked as a review copy. |
| GET | `/quotations/{id}/history` | Audit and approval records. |
| GET/POST/PATCH | `/materials` | Catalog and price history. Price changes append a row. |
| GET/PUT | `/settings` | Cost settings. |
| POST | `/settings/rates` | Appends a process rate. |
| GET | `/jobs` | Search. |
| GET | `/jobs/clusters` | Feature clusters, or a reason when there are too few jobs. |
| GET | `/jobs/{id}/similar` | Scaled feature similarity. |
| POST | `/jobs/{id}/actuals` | Actual cost. Verification is explicit. |
| POST | `/jobs/{id}/training-candidate` | Admin only, and only after verification. |
| GET | `/ml/models` | Organization model versions. |
| GET | `/ml/models/active` | Active model and artifact health. |
| POST | `/ml/models/import-local` | Registers the on-disk candidate. |
| POST | `/ml/models/{id}/promote` | Gates plus `acknowledge_limitations` for synthetic models. |
| POST | `/ml/models/{id}/rollback` | Makes that version active. |
| GET | `/ml/experiments` | Local experiment file, plus MLflow when the tracking server answers. |
| GET | `/ml/metrics` | Active model metrics and the synthetic-data warning. |
| GET | `/dashboard` | Organization aggregates. Accuracy is null until verified jobs exist. |
| GET | `/health` | Database check. |
| GET | `/metrics` | Prometheus. |

Errors use `{ "detail": "...", "code": "..." }`.
