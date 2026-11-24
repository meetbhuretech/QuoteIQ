"""Celery entrypoint for drawing analysis. Training does not run here."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery = Celery("quoteiq", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="UTC")


@celery.task(name="quoteiq.process_drawing")
def process_drawing_task(drawing_id: str) -> None:
    from app.services.pipeline import process_drawing

    process_drawing(drawing_id)
