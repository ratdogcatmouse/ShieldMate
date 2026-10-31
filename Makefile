# ShieldMate: shortcuts for running and testing the backend and frontend together.
# Run `make` (or `make help`) to list the targets. Everything runs from this folder.

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Call the project venv by path; a bare `python3` on PATH may be a different venv.
PY  := backend/.venv/bin/python
# Where `make reset` and `make status` look. Override with `make reset API=http://192.168.x.x:8000`.
API ?= http://localhost:8000
# Extra pytest arguments, e.g. `make test ARGS="tests/unit/test_filter.py -k name"`.
ARGS ?=

.PHONY: help install start dev fresh build test smoke e2e reset status clean

help: ## List the targets
	@grep -hE '^[a-z0-9_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  \033[36m%-8s\033[0m %s\n", $$1, $$2}'

install: ## Create backend/.venv, install backend requirements and frontend packages
	@test -x $(PY) || (command -v python3.12 >/dev/null && python3.12 -m venv backend/.venv) || python3 -m venv backend/.venv
	$(PY) -m pip install -r backend/requirements.txt
	cd frontend && npm ci

start: ## Build the frontend and serve app + API from FastAPI on :8000 (the demo setup)
	./start.sh

dev: ## uvicorn on :8000 + Vite dev server on :5173 with hot reload (Ctrl-C stops both)
	./start.sh dev

fresh: ## Like `start`, but delete the SQLite database first
	./start.sh --fresh

build: ## Build the frontend against the real API (VITE_API_MODE=http, not the fixture mock)
	cd frontend && VITE_API_MODE=http npm run build

test: ## Run the backend test suite (pytest)
	cd backend && .venv/bin/python -m pytest -q $(ARGS)

smoke: build ## Boot the built stack on a spare port and check the API and the frontend together
	bash scripts/smoke.sh

e2e: ## Run the Playwright browser tests (needs the stack running; frontend/e2e is still empty)
	cd frontend && npx playwright test

reset: ## Reset the running demo to its starting state (POST /api/demo/reset)
	curl -fsS -X POST $(API)/api/demo/reset
	@echo

status: ## Show the running backend's /api/status
	curl -fsS $(API)/api/status
	@echo

clean: ## Delete the built frontend (frontend/dist); keeps node_modules, the venv and the DB
	rm -rf frontend/dist
