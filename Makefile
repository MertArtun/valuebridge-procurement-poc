.PHONY: install lint test verify evals check run-mockdesk run-app demo docker-smoke clean

install:
	python -m pip install -e '.[dev]'

lint:
	ruff check .

test:
	pytest -q

verify:
	python scripts/verify.py

evals:
	python scripts/run_evals.py

check: lint test verify evals

run-mockdesk:
	uvicorn mockdesk.main:app --reload --port 8001

run-app:
	MOCKDESK_URL=http://127.0.0.1:8001 uvicorn app.main:app --reload --port 8000

demo:
	bash scripts/demo.sh

docker-smoke:
	docker compose up -d --build
	bash scripts/demo.sh || { docker compose down -v; exit 1; }
	bash scripts/demo.sh || { docker compose down -v; exit 1; }
	docker compose down -v

clean:
	rm -rf .pytest_cache .ruff_cache runtime/*.db reports/*.json __pycache__ app/__pycache__ mockdesk/__pycache__ tests/__pycache__
