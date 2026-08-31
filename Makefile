.PHONY: help install test lint type-check clean check all

help:
	@echo "Enterprise Data Solutions - Phase 1 MVP"
	@echo ""
	@echo "Available targets:"
	@echo "  make install       Install dependencies"
	@echo "  make test          Run pytest with coverage"
	@echo "  make lint          Run flake8 linter"
	@echo "  make type-check    Run mypy type checking"
	@echo "  make check         Run all checks (lint + type + test)"
	@echo "  make clean         Remove __pycache__ and .pytest_cache"
	@echo "  make help          Show this help message"

install:
	pip install -q pytest pytest-cov flake8 mypy pyyaml types-pyyaml

test:
	pytest tests/ --cov=src --cov-report=term-missing --cov-report=html -v

lint:
	flake8 src/ tests/ --max-line-length=100 --ignore=E203,W503

type-check:
	mypy src/ --ignore-missing-imports --no-error-summary

check: lint type-check test
	@echo ""
	@echo "✅ All checks passed!"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name .coverage -delete 2>/dev/null || true
	rm -rf htmlcov/ 2>/dev/null || true
	@echo "✅ Cleaned up"

.DEFAULT_GOAL := help
