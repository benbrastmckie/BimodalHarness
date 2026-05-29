# Research Report: Task 2 — Initialize Python Project Structure
- **Task**: 2 - Initialize Python project structure for BimodalHarness training harness
- **Started**: 2026-05-29T00:00:00Z
- **Completed**: 2026-05-29T00:15:00Z
- **Effort**: S
- **Sources/Inputs**:
  - `/home/benjamin/Projects/Logos/ModelChecker/code/pyproject.toml` — sibling Python project
  - `/home/benjamin/Projects/BimodalLogic/.github/workflows/ci.yml` — sibling Lean CI patterns
  - PyPI live version queries (torch, z3-solver, numpy, wandb, ruff, mypy, pytest, datasets, lean-interact)
  - Web: Python Packaging User Guide (pyproject.toml/hatchling best practices)
  - Web: PyTorch installation docs (2026)
- **Artifacts**: specs/002_initialize_python_project_structure/reports/01_python-project-setup.md

---

## Executive Summary

The BimodalHarness training harness should use a `src/` layout with `hatchling` as the build backend, organized around a `bimodal_harness` top-level package. Dependencies split into core (torch, numpy, z3-solver), optional groups (`lean`, `gpu`, `dev`). Code quality toolchain: ruff 0.15.x for linting/formatting, mypy 2.x in gradual mode. Testing via pytest 9.x with custom markers for GPU and Lean-dependent tests. CI via GitHub Actions with CPU/lint jobs always running and GPU jobs gated behind manual trigger or `[gpu-ci]` commit annotation (matching the pattern in BimodalLogic).

---

## Context & Scope

BimodalHarness is a new repository implementing an AlphaZero-style proof search engine for bimodal logic. It bridges:
- Python (PyTorch neural networks, Z3 countermodel generation, training loop)
- Lean 4 (formal proof verification via `lean-interact`)
- HuggingFace datasets (training data storage/streaming)
- Weights & Biases (experiment tracking)

The sibling ModelChecker project uses `setuptools` with `src/` layout and `z3-solver`. BimodalHarness should modernize to `hatchling` and add PyTorch, HuggingFace, and Lean bridge dependencies.

---

## Findings

### Package Versions (confirmed from live PyPI, May 2026)

| Package | Latest | Notes |
|---------|--------|-------|
| `torch` | 2.12.0 | System has 2.11.0 installed |
| `numpy` | 2.4.6 | System has 2.4.4 |
| `z3-solver` | 4.16.0.0 | ModelChecker uses >=4.8.0 |
| `lean-interact` | 0.11.3 | Python-Lean bridge |
| `datasets` | 4.8.5 | HuggingFace datasets |
| `wandb` | 0.27.0 | Experiment tracking |
| `ruff` | 0.15.15 | Linter + formatter |
| `mypy` | 2.1.0 | Type checker (2.0 released May 2026) |
| `pytest` | 9.0.3 | System has 9.0.2 |

### Project Structure (recommended src/ layout)

```
BimodalHarness/
├── pyproject.toml              # Build system, deps, tool config
├── README.md
├── .github/
│   └── workflows/
│       ├── ci.yml              # Lint + test (CPU, always)
│       └── gpu-ci.yml          # GPU training tests (manual/tagged)
├── src/
│   └── bimodal_harness/
│       ├── __init__.py
│       ├── config.py           # Dataclass-based experiment config
│       ├── data/
│       │   ├── __init__.py
│       │   ├── schema.py       # Formula/proof data structures
│       │   ├── ingestion.py    # Static data loading
│       │   └── export.py       # Training data export pipeline
│       ├── models/
│       │   ├── __init__.py
│       │   ├── policy.py       # Policy network (tactic predictor)
│       │   └── value.py        # Value network (proof progress)
│       ├── search/
│       │   ├── __init__.py
│       │   ├── mcts.py         # AND/OR MCTS with PUCT
│       │   └── best_first.py   # Best-first search with neural guidance
│       ├── training/
│       │   ├── __init__.py
│       │   ├── loop.py         # Expert iteration training loop
│       │   └── online.py       # Online training from MCTS trees
│       ├── evaluation/
│       │   ├── __init__.py
│       │   └── benchmark.py    # Evaluation benchmark suite
│       ├── lean/
│       │   ├── __init__.py
│       │   └── bridge.py       # lean-interact interface
│       └── z3/
│           ├── __init__.py
│           ├── countermodel.py # Z3 countermodel generator
│           └── encoding.py     # Countermodel → tensor encoding
├── tests/
│   ├── conftest.py             # Shared fixtures, GPU marker skip logic
│   ├── test_data/
│   ├── test_models/
│   ├── test_search/
│   ├── test_training/
│   └── test_z3/
├── scripts/
│   ├── train.py                # Entry point for training runs
│   └── evaluate.py             # Entry point for evaluation
└── notebooks/                  # Exploratory analysis
```

### Build System: hatchling

Hatchling is the modern PyPA-endorsed build backend. Unlike setuptools, it auto-discovers packages under `src/` with minimal config:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/bimodal_harness"]
```

### Dependency Groups

Three optional groups beyond core:
- **`dev`**: ruff, mypy, pytest, pytest-cov, pytest-xdist — local development
- **`lean`**: lean-interact — Lean proof bridge (heavier, requires elan)
- **`gpu`**: torch with CUDA index URL — GPU training (torch without CUDA is in core)

Note: torch CPU version goes in core so the package is importable in CI without GPU. The `gpu` optional group pins CUDA wheel index.

### Ruff Configuration (ML projects)

Key rule selections for ML/research code:
- `E`, `F` — pyflakes + pycodestyle (always)
- `I` — isort (import sorting)
- `UP` — pyupgrade (modernize syntax)
- `B` — flake8-bugbear (common bugs)
- `ANN` — type annotation enforcement (gradual)

Exclusions for ML: `ANN101` (self annotation), `ANN102` (cls annotation), `COM812` (trailing comma conflicts with formatter).

### mypy Configuration (gradual mode)

For a new ML project, start with `ignore_missing_imports = true` and `warn_return_any = false`. Gradually tighten. Key settings:
- `python_version = "3.11"` (minimum target)
- `ignore_missing_imports = true` (torch stubs are incomplete)
- `check_untyped_defs = true` (check bodies even without annotations)
- `warn_unused_ignores = true` (clean up spurious `# type: ignore`)

### pytest Configuration

Adopt the markers pattern from ModelChecker (countermodel/theorem/performance), plus:
- `gpu`: marks tests requiring CUDA
- `lean`: marks tests requiring lean-interact and elan
- `slow`: marks tests with >5s runtime

CI skips `gpu` and `lean` markers by default. The `conftest.py` handles auto-skip via `pytest.ini_options.addopts = "-m 'not gpu and not lean'"`.

### GitHub Actions CI Pattern

BimodalLogic CI uses a selective trigger:
```yaml
if: |
  github.event_name == 'workflow_dispatch' ||
  github.event_name == 'pull_request' ||
  contains(github.event.head_commit.message, '[ci]')
```

BimodalHarness should adopt the same pattern for the standard CI job, plus a separate `gpu-ci.yml` triggered by `[gpu-ci]` in commit message or manual dispatch.

The main CI job matrix should run:
1. `ruff check src/ tests/` — linting
2. `ruff format --check src/ tests/` — formatting
3. `mypy src/` — type checking
4. `pytest -m "not gpu and not lean"` — unit tests (CPU only)

Python version matrix: 3.11, 3.12 (3.10 is PyTorch minimum but 3.11 is practical floor for new projects).

---

## Decisions

1. **Build backend**: hatchling (not setuptools like ModelChecker) — more modern, less config, PyPA-endorsed.
2. **Python minimum**: 3.11 — avoids 3.10 edge cases, PyTorch 2.12 supports 3.11+.
3. **torch in core, CUDA optional**: CPU torch in `[project.dependencies]`; GPU extras declare CUDA wheel index. This keeps CI cheap.
4. **lean-interact as optional**: `[lean]` extra group, not core — Lean bridge is heavyweight and requires elan/toolchain.
5. **Single `src/bimodal_harness` package**: All sub-domains as subpackages (data, models, search, training, evaluation, lean, z3).
6. **mypy gradual mode**: Start with `ignore_missing_imports = true`, tighten incrementally per subpackage.
7. **CI trigger strategy**: Match BimodalLogic's `[ci]` commit annotation pattern plus PR trigger.

---

## Recommendations

### pyproject.toml skeleton

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "bimodal-harness"
version = "0.1.0"
description = "AlphaZero-style proof search training harness for bimodal logic"
authors = [{ name = "Benjamin Brast-McKie", email = "benbrastmckie@gmail.com" }]
license = { text = "GPL-3.0-or-later" }
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "torch>=2.12.0",
    "numpy>=2.4.0",
    "z3-solver>=4.16.0.0",
    "datasets>=4.8.0",
    "wandb>=0.27.0",
]

[project.optional-dependencies]
lean = [
    "lean-interact>=0.11.0",
]
gpu = [
    # Install with: pip install -e ".[gpu]" --extra-index-url https://download.pytorch.org/whl/cu128
    "torch>=2.12.0",
]
dev = [
    "pytest>=9.0.0",
    "pytest-cov>=6.0.0",
    "pytest-xdist>=3.0.0",
    "ruff>=0.15.0",
    "mypy>=2.1.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/bimodal_harness"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
python_files = "test_*.py"
python_classes = "Test*"
addopts = "--durations=10 -v --import-mode=importlib -m 'not gpu and not lean'"
markers = [
    "gpu: requires CUDA GPU",
    "lean: requires lean-interact and elan toolchain",
    "slow: test runtime > 5 seconds",
]

[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
check_untyped_defs = true
warn_unused_ignores = true
warn_redundant_casts = true
```

### GitHub Actions (.github/workflows/ci.yml)

```yaml
name: CI
on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]
  workflow_dispatch:

jobs:
  lint-and-test:
    name: Lint and Test (CPU)
    runs-on: ubuntu-latest
    if: |
      github.event_name == 'workflow_dispatch' ||
      github.event_name == 'pull_request' ||
      contains(github.event.head_commit.message, '[ci]')
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: "pip"
      - run: pip install -e ".[dev]"
      - run: ruff check src/ tests/
      - run: ruff format --check src/ tests/
      - run: mypy src/
      - run: pytest -m "not gpu and not lean"
```

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| torch CUDA/CPU version conflict | Medium | High | Separate `[gpu]` optional group; document install with `--extra-index-url` |
| lean-interact requires specific elan toolchain version | Medium | Medium | Pin in `[lean]` extras; document required Lean version in README |
| mypy 2.x parallel checking incompatible with torch stubs | Low | Low | Use `ignore_missing_imports = true`; add `# type: ignore` for torch-typed modules |
| numpy 2.x breaking changes from 1.x | Low | Low | Pin `>=2.4.0`; z3-solver and torch already support numpy 2.x |
| GPU CI costs on GitHub Actions | High | Medium | GPU CI in separate workflow, triggered only by `[gpu-ci]` annotation |

---

## Appendix

### Sibling Project Reference (ModelChecker)

`/home/benjamin/Projects/Logos/ModelChecker/code/pyproject.toml` uses:
- `setuptools>=42` with `wheel` (older pattern)
- `src/` layout via `[tool.setuptools.package-dir]`
- `z3-solver>=4.8.0`, `networkx>=2.0` as core deps
- `pytest` config with custom markers (countermodel, theorem, performance)
- `filterwarnings` to suppress z3 pkg_resources deprecation

BimodalHarness should carry forward the z3 filterwarning suppression and the custom marker pattern.

### BimodalLogic CI Reference

`.github/workflows/ci.yml` in BimodalLogic uses:
- `leanprover/lean-action@v1` with `use-mathlib-cache: true`
- Selective trigger via commit message `[ci]` annotation
- `workflow_dispatch` for manual runs

This selective trigger pattern is directly applicable to BimodalHarness Python CI.
