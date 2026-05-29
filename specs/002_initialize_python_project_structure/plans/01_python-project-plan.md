# Implementation Plan: Task #2

- **Task**: 2 - Initialize Python project structure
- **Status**: [IMPLEMENTING]
- **Effort**: 3 hours
- **Dependencies**: None
- **Research Inputs**: specs/002_initialize_python_project_structure/reports/01_python-project-setup.md
- **Artifacts**: plans/01_python-project-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: python
- **Lean Intent**: false

## Overview

Set up the foundational Python project structure for BimodalHarness, an AlphaZero-style proof search training harness for bimodal logic. This includes pyproject.toml with hatchling build backend, src/bimodal_harness/ package layout with all subpackage stubs, dev toolchain configuration (ruff, mypy, pytest), and GitHub Actions CI pipeline. The definition of done is: `pip install -e ".[dev]"` succeeds, `ruff check src/` passes, `mypy src/` passes, `pytest` discovers and runs a smoke test, and CI lint-and-test job completes on push.

### Research Integration

Key findings from research report 01_python-project-setup.md integrated into this plan:
- **Build backend**: hatchling (PyPA-endorsed, minimal config, auto-discovery under src/)
- **Package layout**: src/bimodal_harness/ with subpackages: data, models, search, training, evaluation, lean, z3
- **Dependency strategy**: torch CPU in core deps for CI importability; CUDA via `[gpu]` optional group; lean-interact via `[lean]` optional group
- **Version pins**: torch>=2.12.0, numpy>=2.4.0, z3-solver>=4.16.0.0, ruff>=0.15.0, mypy>=2.1.0, pytest>=9.0.0
- **Ruff rules**: E, F, I, UP, B with E501 ignored (formatter handles line length)
- **mypy**: gradual mode with ignore_missing_imports=true, check_untyped_defs=true
- **pytest markers**: gpu, lean, slow with default addopts excluding gpu and lean
- **CI pattern**: Match BimodalLogic selective trigger (`[ci]` annotation, PR, workflow_dispatch)

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Create pyproject.toml with hatchling build system and all dependency groups (core, dev, lean, gpu)
- Establish src/bimodal_harness/ package with all subpackage directories and __init__.py stubs
- Configure ruff linting, ruff formatting, mypy type checking, and pytest with custom markers
- Create GitHub Actions CI workflow for lint + CPU test matrix (Python 3.11, 3.12)
- Create test infrastructure with conftest.py, a passing smoke test, and marker skip logic
- Create script entry points (scripts/train.py, scripts/evaluate.py) as stubs

**Non-Goals**:
- Implementing any business logic (models, search, training, data processing)
- Setting up GPU CI workflow (gpu-ci.yml) -- deferred to a later task when GPU tests exist
- Publishing to PyPI or configuring release workflows
- Setting up pre-commit hooks or git hooks
- Creating Jupyter notebook infrastructure

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| torch CPU install exceeds CI time/memory limits | M | L | Pin minimum version, use pip cache in CI, CPU-only wheel |
| hatchling src/ layout discovery misconfiguration | H | L | Explicitly set `packages = ["src/bimodal_harness"]` in hatch config |
| mypy failures on torch stubs in CI | M | M | Use `ignore_missing_imports = true`; validate locally before CI |
| ruff version drift between local and CI | L | L | Pin `>=0.15.0` floor; CI installs from `[dev]` extras |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1 | -- |
| 2 | 2, 3 | 1 |
| 3 | 4 | 2, 3 |

Phases within the same wave can execute in parallel.

---

### Phase 1: Create pyproject.toml and Package Skeleton [COMPLETED]

**Goal**: Establish the build system configuration and directory structure so that `pip install -e .` succeeds and the package is importable.

**Tasks**:
- [ ] Create `pyproject.toml` with hatchling build-system, project metadata (name, version, description, authors, license, requires-python), and core dependencies (torch, numpy, z3-solver, datasets, wandb)
- [ ] Add optional dependency groups: `[dev]` (pytest, pytest-cov, pytest-xdist, ruff, mypy), `[lean]` (lean-interact), `[gpu]` (torch with CUDA index URL comment)
- [ ] Configure `[tool.hatch.build.targets.wheel]` with `packages = ["src/bimodal_harness"]`
- [ ] Create `src/bimodal_harness/__init__.py` with version string
- [ ] Create subpackage directories with `__init__.py` stubs: data/, models/, search/, training/, evaluation/, lean/, z3/
- [ ] Create placeholder module files in each subpackage (config.py, schema.py, ingestion.py, export.py, policy.py, value.py, mcts.py, best_first.py, loop.py, online.py, benchmark.py, bridge.py, countermodel.py, encoding.py) with docstrings only
- [ ] Create `scripts/train.py` and `scripts/evaluate.py` as stub entry points
- [ ] Verify `pip install -e .` succeeds and `python -c "import bimodal_harness"` works

**Timing**: 1 hour

**Depends on**: none

**Files to modify**:
- `pyproject.toml` - create (build system, deps, tool config)
- `src/bimodal_harness/__init__.py` - create (package root)
- `src/bimodal_harness/config.py` - create (stub)
- `src/bimodal_harness/data/__init__.py` - create
- `src/bimodal_harness/data/schema.py` - create (stub)
- `src/bimodal_harness/data/ingestion.py` - create (stub)
- `src/bimodal_harness/data/export.py` - create (stub)
- `src/bimodal_harness/models/__init__.py` - create
- `src/bimodal_harness/models/policy.py` - create (stub)
- `src/bimodal_harness/models/value.py` - create (stub)
- `src/bimodal_harness/search/__init__.py` - create
- `src/bimodal_harness/search/mcts.py` - create (stub)
- `src/bimodal_harness/search/best_first.py` - create (stub)
- `src/bimodal_harness/training/__init__.py` - create
- `src/bimodal_harness/training/loop.py` - create (stub)
- `src/bimodal_harness/training/online.py` - create (stub)
- `src/bimodal_harness/evaluation/__init__.py` - create
- `src/bimodal_harness/evaluation/benchmark.py` - create (stub)
- `src/bimodal_harness/lean/__init__.py` - create
- `src/bimodal_harness/lean/bridge.py` - create (stub)
- `src/bimodal_harness/z3/__init__.py` - create
- `src/bimodal_harness/z3/countermodel.py` - create (stub)
- `src/bimodal_harness/z3/encoding.py` - create (stub)
- `scripts/train.py` - create (stub)
- `scripts/evaluate.py` - create (stub)

**Verification**:
- `pip install -e .` exits 0
- `python -c "import bimodal_harness; print(bimodal_harness.__version__)"` prints version
- `python -c "from bimodal_harness.data import schema"` succeeds

---

### Phase 2: Configure Code Quality Toolchain [COMPLETED]

**Goal**: Set up ruff linting/formatting, mypy type checking configuration in pyproject.toml so that quality checks pass on the stub codebase.

**Tasks**:
- [ ] Add `[tool.ruff]` configuration: target-version py311, line-length 100, src = ["src"]
- [ ] Add `[tool.ruff.lint]` with select = ["E", "F", "I", "UP", "B"] and ignore = ["E501"]
- [ ] Add `[tool.ruff.format]` with quote-style double, indent-style space
- [ ] Add `[tool.mypy]` configuration: python_version 3.11, ignore_missing_imports true, check_untyped_defs true, warn_unused_ignores true, warn_redundant_casts true
- [ ] Run `ruff check src/ tests/` and fix any violations in stub files
- [ ] Run `ruff format --check src/ tests/` and fix any formatting issues
- [ ] Run `mypy src/` and fix any type errors in stub files

**Timing**: 30 minutes

**Depends on**: 1

**Files to modify**:
- `pyproject.toml` - add [tool.ruff], [tool.ruff.lint], [tool.ruff.format], [tool.mypy] sections

**Verification**:
- `ruff check src/` exits 0 with no violations
- `ruff format --check src/` exits 0
- `mypy src/` exits 0 (or only expected warnings)

---

### Phase 3: Set Up Test Infrastructure [COMPLETED]

**Goal**: Create pytest configuration, conftest.py with fixture support and marker skip logic, and a passing smoke test that validates the package is importable and structured correctly.

**Tasks**:
- [ ] Add `[tool.pytest.ini_options]` to pyproject.toml: testpaths, pythonpath, python_files, addopts (with marker exclusions), markers (gpu, lean, slow)
- [ ] Create `tests/conftest.py` with shared fixtures, GPU marker auto-skip logic, and z3 pkg_resources filterwarning suppression
- [ ] Create `tests/__init__.py` (empty)
- [ ] Create `tests/test_smoke.py` with basic import tests: package importable, version string exists, all subpackages importable
- [ ] Create test subdirectory stubs: tests/test_data/, tests/test_models/, tests/test_search/, tests/test_training/, tests/test_z3/ with __init__.py files
- [ ] Run `pytest` and verify the smoke test passes

**Timing**: 45 minutes

**Depends on**: 1

**Files to modify**:
- `pyproject.toml` - add [tool.pytest.ini_options] section
- `tests/__init__.py` - create
- `tests/conftest.py` - create (fixtures, markers, filterwarnings)
- `tests/test_smoke.py` - create (import smoke tests)
- `tests/test_data/__init__.py` - create
- `tests/test_models/__init__.py` - create
- `tests/test_search/__init__.py` - create
- `tests/test_training/__init__.py` - create
- `tests/test_z3/__init__.py` - create

**Verification**:
- `pytest` discovers and runs smoke tests
- All smoke tests pass (exit code 0)
- `pytest --collect-only` shows test_smoke.py tests and correct marker registrations

---

### Phase 4: Create GitHub Actions CI Workflow [NOT STARTED]

**Goal**: Create the CI pipeline that runs linting, type checking, and CPU-only tests on push/PR to main, matching the BimodalLogic selective trigger pattern.

**Tasks**:
- [ ] Create `.github/workflows/` directory
- [ ] Create `.github/workflows/ci.yml` with lint-and-test job: checkout, setup-python (matrix 3.11, 3.12), pip cache, install dev extras, ruff check, ruff format --check, mypy, pytest
- [ ] Add selective trigger: workflow_dispatch, pull_request on main, push on main with `[ci]` commit annotation check
- [ ] Verify YAML syntax is valid (e.g., via `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` or manual inspection)

**Timing**: 30 minutes

**Depends on**: 2, 3

**Files to modify**:
- `.github/workflows/ci.yml` - create (lint + test CI pipeline)

**Verification**:
- YAML is syntactically valid
- Workflow references correct Python versions and install commands
- Trigger conditions match design (push main, PR main, workflow_dispatch, `[ci]` annotation)
- All four CI steps are present: ruff check, ruff format --check, mypy, pytest

---

## Testing & Validation

- [ ] `pip install -e ".[dev]"` completes without errors
- [ ] `python -c "import bimodal_harness"` succeeds
- [ ] `ruff check src/ tests/` reports zero violations
- [ ] `ruff format --check src/ tests/` reports zero reformats needed
- [ ] `mypy src/` passes without errors
- [ ] `pytest` discovers and passes all smoke tests
- [ ] `.github/workflows/ci.yml` is valid YAML with correct structure
- [ ] All subpackages (data, models, search, training, evaluation, lean, z3) are importable

## Artifacts & Outputs

- `pyproject.toml` - Build system, dependencies, tool configuration
- `src/bimodal_harness/` - Package root with 7 subpackages and 14 stub modules
- `tests/` - Test directory with conftest.py, smoke tests, and 5 test subdirectories
- `scripts/` - Entry point stubs (train.py, evaluate.py)
- `.github/workflows/ci.yml` - CI pipeline configuration
- `specs/002_initialize_python_project_structure/plans/01_python-project-plan.md` - This plan

## Rollback/Contingency

All changes in this task create new files from scratch (no existing files are modified). Rollback is straightforward:
- Remove `pyproject.toml`, `src/`, `tests/`, `scripts/`, `.github/` directories
- No database migrations, external state, or irreversible side effects
- If hatchling proves problematic, switch to setuptools by changing `[build-system]` and adding `[tool.setuptools.package-dir]` configuration (research report includes sibling project reference)
