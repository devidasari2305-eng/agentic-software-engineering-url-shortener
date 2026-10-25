.PHONY: install run test lint demo
install:
	python -m pip install -r requirements.txt
run:
	python -m uvicorn app.main:app --reload
test:
	python -m pytest -q
lint:
	python -m ruff check .
demo:
	python demo.py
