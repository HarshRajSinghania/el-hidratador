.PHONY: help install dev test lint format typecheck coverage check build clean docs serve docker-build docker-run

PYTHON ?= python3
PACKAGE := el_hidratador

help: ## Show the available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install the package
	$(PYTHON) -m pip install .

dev: ## Install the package with development extras
	$(PYTHON) -m pip install -e ".[dev]"

test: ## Run the test suite
	$(PYTHON) -m unittest discover -s tests -v

lint: ## Lint the package
	ruff check $(PACKAGE)/ tests/

format: ## Format the package
	ruff format $(PACKAGE)/ tests/

format-check: ## Verify formatting without writing
	ruff format --check $(PACKAGE)/ tests/

typecheck: ## Run the type checker
	mypy $(PACKAGE)/

coverage: ## Run the test suite with a coverage report
	$(PYTHON) -m coverage run -m unittest discover -s tests
	$(PYTHON) -m coverage report --show-missing

check: lint format-check typecheck test ## Run every check the CI runs

build: ## Build the sdist and the wheel
	$(PYTHON) -m pip install --upgrade build
	$(PYTHON) -m build

clean: ## Remove build and test artifacts
	rm -rf build dist .coverage htmlcov .pytest_cache .mypy_cache .ruff_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '*.egg-info' -type d -prune -exec rm -rf {} +

docs: ## Build the documentation site
	mkdocs build --strict

serve: ## Serve the documentation site locally
	mkdocs serve

docker-build: ## Build the container image
	docker build -t el-hidratador:local .

docker-run: ## Run the container image
	docker run --rm el-hidratador:local --help
