SHELL := /bin/bash

VENV := backend/.venv
UVICORN := $(VENV)/bin/uvicorn

RUN_DIR := .run
BACKEND_PID := $(RUN_DIR)/backend.pid
FRONTEND_PID := $(RUN_DIR)/frontend.pid
BACKEND_LOG := $(RUN_DIR)/backend.log
FRONTEND_LOG := $(RUN_DIR)/frontend.log

.PHONY: up down install install-backend install-frontend test test-backend test-frontend clean

## Start backend (venv) + frontend together, detached; logs go to .run/
up: | $(RUN_DIR)
	@set -m; \
	if [ -f $(BACKEND_PID) ] && kill -0 $$(cat $(BACKEND_PID)) 2>/dev/null; then \
		echo "Backend already running (PID $$(cat $(BACKEND_PID)))"; \
	else \
		$(UVICORN) app.main:app --reload --app-dir backend > $(BACKEND_LOG) 2>&1 & \
		echo $$! > $(BACKEND_PID); \
		echo "Backend started (PID $$(cat $(BACKEND_PID))) -> http://localhost:8000"; \
	fi; \
	if [ -f $(FRONTEND_PID) ] && kill -0 $$(cat $(FRONTEND_PID)) 2>/dev/null; then \
		echo "Frontend already running (PID $$(cat $(FRONTEND_PID)))"; \
	else \
		(cd frontend && npm run dev) > $(FRONTEND_LOG) 2>&1 & \
		echo $$! > $(FRONTEND_PID); \
		echo "Frontend started (PID $$(cat $(FRONTEND_PID))) -> http://localhost:5173"; \
	fi; \
	echo "Logs: tail -f $(BACKEND_LOG) $(FRONTEND_LOG)  |  make down to stop"

## Stop everything started by `make up`
down:
	@for f in $(BACKEND_PID) $(FRONTEND_PID); do \
		if [ -f $$f ]; then \
			pid=$$(cat $$f); \
			if kill -0 $$pid 2>/dev/null; then \
				kill -TERM -$$pid 2>/dev/null || kill -TERM $$pid 2>/dev/null; \
				echo "Stopped PID $$pid"; \
			fi; \
			rm -f $$f; \
		fi; \
	done

$(RUN_DIR):
	@mkdir -p $@

## Set up both environments
install: install-backend install-frontend

install-backend:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r backend/requirements.txt

install-frontend:
	cd frontend && npm install

## Run test suites
test: test-backend test-frontend

test-backend:
	$(VENV)/bin/pytest backend/tests

test-frontend:
	cd frontend && npm run test

clean:
	rm -rf $(VENV) frontend/node_modules $(RUN_DIR)
