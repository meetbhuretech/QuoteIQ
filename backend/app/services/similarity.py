"""Comparable-job retrieval from engineered features.

Similarity is a scaled numeric distance plus a category bonus. It is not an
embedding model and it does not claim two parts share a process.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models import ManufacturingJob

KEYS = [
    "volume_cm3",
    "length_mm",
    "width_mm",
    "height_mm",
    "hole_count",
    "feature_count",
    "density",
    "quantity",
    "geometric_complexity",
]


def search_jobs(db: Session, organization_id: UUID, query: str | None, material: str | None, process: str | None) -> list[ManufacturingJob]:
    rows = db.query(ManufacturingJob).filter(ManufacturingJob.organization_id == organization_id).all()
    needle = (query or "").lower()
    results = []
    for job in rows:
        if needle and needle not in f"{job.part_name or ''} {job.drawing_number or ''} {job.material_name or ''}".lower():
            continue
        if material and (job.material_category or "").lower() != material.lower() and (job.material_name or "").lower() != material.lower():
            continue
        if process and (job.process or "").lower() != process.lower():
            continue
        results.append(job)
    return results


def similar_jobs(db: Session, job: ManufacturingJob, limit: int = 5) -> list[dict]:
    source = _vector(job)
    if source is None:
        return []
    scored = []
    others = (
        db.query(ManufacturingJob)
        .filter(ManufacturingJob.organization_id == job.organization_id, ManufacturingJob.id != job.id)
        .all()
    )
    for other in others:
        candidate = _vector(other)
        if candidate is None:
            continue
        scored.append({"job": other, "score": _score(source, candidate, job, other)})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


def cluster_jobs(db: Session, organization_id: UUID) -> dict:
    jobs = db.query(ManufacturingJob).filter(ManufacturingJob.organization_id == organization_id).all()
    usable = [(job, _vector(job)) for job in jobs]
    usable = [(job, vector) for job, vector in usable if vector is not None]
    if len(usable) < 8:
        return {
            "available": False,
            "reason": "At least 8 jobs with complete feature vectors are required before clustering.",
            "clusters": [],
        }
    try:
        import numpy as np
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
    except Exception as exc:
        return {"available": False, "reason": f"Clustering library unavailable: {exc}", "clusters": []}
    matrix = StandardScaler().fit_transform(np.array([vector[0] for _, vector in usable], dtype=float))
    count = min(4, max(2, len(usable) // 3))
    labels = KMeans(n_clusters=count, n_init=10, random_state=42).fit_predict(matrix)
    grouped: dict[int, list] = {}
    for (job, _), label in zip(usable, labels):
        grouped.setdefault(int(label), []).append(
            {"id": job.id, "part_name": job.part_name, "material": job.material_name, "data_origin": job.data_origin}
        )
    return {
        "available": True,
        "reason": "Clusters describe feature similarity only. They are not process families.",
        "clusters": [{"cluster": key, "jobs": value} for key, value in sorted(grouped.items())],
    }


def _vector(job: ManufacturingJob):
    raw = job.feature_vector or {}
    if any(raw.get(key) is None for key in KEYS):
        return None
    return [float(raw[key]) for key in KEYS], raw.get("material_category"), raw.get("manufacturing_process")


def _score(source, candidate, left: ManufacturingJob, right: ManufacturingJob) -> float:
    distances = [abs(a - b) / max(abs(a), abs(b), 1.0) for a, b in zip(source[0], candidate[0])]
    score = 1 - (sum(distances) / len(distances))
    if source[1] and source[1] == candidate[1]:
        score += 0.05
    if source[2] and source[2] == candidate[2]:
        score += 0.05
    return round(min(score, 1.0), 4)
