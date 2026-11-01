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
# `make events`: which event log to read and how many of the newest entries to show.
EVENTS ?= backend/shieldmate-events.db
N ?= 50

.PHONY: help install start dev fresh clean-slate build test smoke e2e reset status events clean

help: ## List the targets
	@grep -hE '^[a-z0-9_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

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

clean-slate: ## Fresh start for a presentation: delete the DB and the event log, then start (server must be stopped)
	./start.sh --clean-slate

build: ## Build the frontend (frontend/dist, served by FastAPI)
	cd frontend && npm run build

test: ## Run the backend tests (pytest) and the frontend unit tests (vitest)
	cd backend && .venv/bin/python -m pytest -q $(ARGS)
	cd frontend && npm test

smoke: build ## Boot the built stack on a spare port and check the API and the frontend together
	bash scripts/smoke.sh

e2e: ## Playwright demo-story tests; needs `ACTIONS=1 make start` running (they press Reset)
	cd frontend && npx playwright test

reset: ## Reset the running demo to its starting state (POST /api/demo/reset)
	curl -fsS -X POST $(API)/api/demo/reset
	@echo

status: ## Show the running backend's /api/status
	curl -fsS $(API)/api/status
	@echo

events: ## Show the newest event-log entries, oldest first (N=50, EVENTS=backend/shieldmate-events.db)
	@test -f $(EVENTS) || { echo "No event log at $(EVENTS) yet: start the backend first."; exit 1; }
	@$(PY) -c 'import sqlite3, sys; \
	rows = sqlite3.connect(sys.argv[1]).execute("SELECT id, ts, epoch, type, actor_staff_id, subject_type, subject_id, session_id, data FROM events ORDER BY id DESC LIMIT ?", (int(sys.argv[2]),)).fetchall(); \
	[print(*("-" if v is None else v for v in r), sep="  ") for r in reversed(rows)]' $(EVENTS) $(N)

clean: ## Delete the built frontend (frontend/dist); keeps node_modules, the venv and the DB
	rm -rf frontend/dist
