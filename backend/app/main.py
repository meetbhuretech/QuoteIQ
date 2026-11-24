"""QuoteIQ HTTP application."""

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text

from app.api.v1 import router
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import engine

REQUESTS = Counter("quoteiq_http_requests_total", "HTTP requests", ["method", "status"])
LATENCY = Histogram("quoteiq_http_request_seconds", "HTTP request latency")


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(
        title="QuoteIQ",
        version="0.1.0",
        description="Manufacturing quotation platform. Model output is advisory and synthetic results are labelled.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def observe(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id", uuid4().hex)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            REQUESTS.labels(request.method, "500").inc()
            raise
        response.headers["X-Request-Id"] = request_id
        LATENCY.observe(time.perf_counter() - started)
        REQUESTS.labels(request.method, str(response.status_code)).inc()
        return response

    @app.exception_handler(AppError)
    async def app_error(_, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code})

    @app.get("/health")
    def health():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(router)
    return app


app = create_app()
