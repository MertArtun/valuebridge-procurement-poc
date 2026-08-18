.PHONY: install test verify evals lint run-mockdesk run-app demo clean

install:
	python -m pip install -e '.[dev]'

test:
	pytest -q

verify:
	python scripts/verify.py

evals:
	python scripts/run_evals.py

lint:
	ruff check .

run-mockdesk:
	uvicorn mockdesk.main:app --reload --port 8001

run-app:
	MOCKDESK_URL=http://127.0.0.1:8001 uvicorn app.main:app --reload --port 8000

demo:
	bash scripts/demo.sh

clean:
	rm -rf .pytest_cache .ruff_cache runtime/*.db __pycache__ app/__pycache__ mockdesk/__pycache__ tests/__pycache__
