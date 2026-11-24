FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr libglib2.0-0 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend /app
COPY ml /opt/quoteiq/ml
ENV PYTHONPATH=/app:/opt/quoteiq/ml
ENV MODEL_ARTIFACT_DIR=/opt/quoteiq/ml/artifacts
ENV STORAGE_DIR=/app/storage
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
