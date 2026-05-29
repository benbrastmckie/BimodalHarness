# BimodalHarness Makefile
# Provides data sync, validation, and development convenience targets.

.PHONY: help sync-data validate-data install install-dev test lint typecheck clean

# Default source path for BimodalLogic exports (override with make BIMODAL_LOGIC_PATH=...)
BIMODAL_LOGIC_PATH ?= ../BimodalLogic
BIMODAL_LOGIC_DATA := $(BIMODAL_LOGIC_PATH)/data
LOCAL_DATA := ./data/bimodal

PYTHON := python3
PYTEST := pytest
RUFF := ruff
MYPY := mypy

help: ## Show this help message
	@echo "BimodalHarness development targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Data targets
# ---------------------------------------------------------------------------

sync-data: ## Sync JSONL exports from BimodalLogic to data/bimodal/
	@echo "Syncing data from $(BIMODAL_LOGIC_DATA) -> $(LOCAL_DATA)"
	@if [ ! -d "$(BIMODAL_LOGIC_DATA)" ]; then \
		echo "WARNING: BimodalLogic data directory not found at $(BIMODAL_LOGIC_DATA)"; \
		echo "  Set BIMODAL_LOGIC_PATH to your BimodalLogic checkout, e.g.:"; \
		echo "  make sync-data BIMODAL_LOGIC_PATH=/home/user/Projects/BimodalLogic"; \
		exit 0; \
	fi
	@mkdir -p $(LOCAL_DATA)
	rsync -av --include='*.jsonl' --include='*.parquet' --exclude='*' \
		$(BIMODAL_LOGIC_DATA)/ $(LOCAL_DATA)/
	@echo "Sync complete. Update data/VERSION with BimodalLogic commit hash."

validate-data: ## Validate JSONL files against the LabeledFormula schema
	@echo "Validating data files..."
	@$(PYTHON) -c "\
import sys, pathlib, json; \
from bimodal_harness.data import load_jsonl, LabeledFormula; \
data_dir = pathlib.Path('data'); \
files = list(data_dir.glob('**/*.jsonl')); \
if not files: \
    print('No .jsonl files found in data/'); \
    sys.exit(0); \
errors = 0; \
for f in files: \
    count = 0; \
    try: \
        for record in load_jsonl(f): \
            count += 1; \
        print(f'  OK  {f} ({count} records)') \
    except Exception as e: \
        print(f'  ERR {f}: {e}'); \
        errors += 1; \
if errors: \
    print(f'Validation failed: {errors} file(s) with errors'); \
    sys.exit(1); \
else: \
    print(f'All {len(files)} file(s) valid')"

# ---------------------------------------------------------------------------
# Development targets
# ---------------------------------------------------------------------------

install: ## Install package dependencies (no dev extras)
	pip install -e .

install-dev: ## Install package with development dependencies
	pip install -e ".[dev]"

test: ## Run the test suite
	$(PYTEST) tests/ -v

test-fast: ## Run tests excluding slow/gpu/lean tests
	$(PYTEST) tests/ -v -m "not slow and not gpu and not lean"

lint: ## Run ruff linter
	$(RUFF) check src/ tests/

format: ## Run ruff formatter
	$(RUFF) format src/ tests/

typecheck: ## Run mypy type checker
	$(MYPY) src/bimodal_harness/

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/
