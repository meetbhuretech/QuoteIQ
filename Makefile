.PHONY: test train api web

test:
	cd backend && .venv/bin/pytest

train:
	PYTHONPATH=ml backend/.venv/bin/python -m quoteiq_ml.train

api:
	cd backend && .venv/bin/uvicorn app.main:app --reload

web:
	cd frontend && npm run dev
