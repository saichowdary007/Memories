SHELL := /bin/bash
ENV ?= .env
PYTHON := python3
UVICORN := uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

export $(shell [ -f $(ENV) ] && sed 's/=.*//' $(ENV))

.PHONY: install lint format format-check test test-unit test-integration up down seed logs mypy coverage clean backup restore

install:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt

lint:
	. .venv/bin/activate && ruff check .

format:
	. .venv/bin/activate && black . && ruff check --fix .

format-check:
	. .venv/bin/activate && black --check . && ruff check .

mypy:
	. .venv/bin/activate && mypy apps connectors core ui scripts

test:
	. .venv/bin/activate && pytest

test-unit:
	. .venv/bin/activate && pytest tests/unit

test-integration:
	. .venv/bin/activate && pytest tests/integration

coverage:
	. .venv/bin/activate && pytest --cov=apps --cov=connectors --cov=core --cov-report=term-missing

up:
	docker-compose --env-file $(ENV) up -d --build

down:
	docker-compose down

seed:
	. .venv/bin/activate && python scripts/seed_data.py

backup:
	bash scripts/backup.sh

restore:
	bash scripts/restore.sh

logs:
	docker-compose logs -f api worker

clean:
	rm -rf .venv __pycache__ */__pycache__ .pytest_cache
