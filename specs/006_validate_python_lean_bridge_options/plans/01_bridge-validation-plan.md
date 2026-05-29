# Implementation Plan: Validate Python-Lean Bridge Options

- **Task**: 6 - Validate Python-Lean bridge options
- **Status**: [IMPLEMENTING]
- **Effort**: 4 hours
- **Dependencies**: Task 2 (Python project structure)
- **Research Inputs**: specs/006_validate_python_lean_bridge_options/reports/01_bridge-validation.md
- **Artifacts**: plans/01_bridge-validation-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: python
- **Lean Intent**: false

## Overview

Implement the Python-Lean bridge using lean-interact v0.11.3, the only viable candidate identified by research. LeanDojo-v2 was rejected as overkill (full training framework, GPU required) and PyPantograph was rejected due to a hard version-pinning blocker with Lean v4.27.0-rc1. The plan focuses on four phases: installing and verifying lean-interact, implementing a `LeanBridge` wrapper class in the existing `bridge.py` stub, writing validation tests that exercise the REPL and subprocess paths, and producing latency benchmarks to close this critical risk gate.

### Research Integration

Key findings from the bridge validation research report (01_bridge-validation.md):
- **lean-interact v0.11.3** explicitly supports Lean v4.8.0-rc1 through v4.30.0-rc2, covering v4.27.0-rc1
- Already declared in `pyproject.toml` under `[project.optional-dependencies] lean`
- `LocalProject` API loads BimodalLogic without lakefile modifications
- `ProofStep` tactic interface matches expert iteration needs (Task 15+)
- `AutoLeanServer` provides crash recovery for long training loops
- BimodalLogic does not expose a single "ProofChecker" module; relevant API is distributed across `Decidability`, `ProofSearch.Core`, `DatasetGenerator`, and `DatasetValidator`
- Two-path architecture recommended: subprocess for batch work, REPL for interactive loops

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Install lean-interact and verify it connects to BimodalLogic (Lean v4.27.0-rc1)
- Implement `LeanBridge` wrapper class with `label_formula`, `apply_tactic`, and lifecycle management
- Write pytest tests (marked `@pytest.mark.lean`) validating both REPL and subprocess paths
- Produce cold/warm startup and per-operation latency benchmarks
- Close the critical risk gate: confirm Python can send commands to Lean and receive structured responses

**Non-Goals**:
- Connection pooling for parallel training workers (Task 15+ scope)
- Full expert iteration loop integration (Task 16 scope)
- LeanDojo or PyPantograph integration (rejected by research)
- Modifying BimodalLogic lakefile or Lean source code
- GPU-dependent operations

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| BimodalLogic `.lake/build/` is stale or missing | H | L | Run `lake build` as a prerequisite check in Phase 1; document as a setup requirement |
| lean-interact REPL download slow on first run | M | M | Phase 1 smoke test triggers the one-time download; subsequent phases use cached REPL |
| REPL crashes on malformed tactic input | M | M | Use `AutoLeanServer` for crash recovery; wrap tactic calls in try/except |
| Mathlib import latency exceeds benchmark window | L | M | Measure separately; use `PickleEnvironment` for warm-start in later tasks |
| BimodalLogic path hardcoded or environment-dependent | M | L | Use environment variable `BIMODAL_LOGIC_PATH` with sensible default; document in config |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1 | -- |
| 2 | 2 | 1 |
| 3 | 3 | 2 |
| 4 | 4 | 3 |

Phases within the same wave can execute in parallel.

---

### Phase 1: Install lean-interact and Smoke Test [COMPLETED]

**Goal**: Verify lean-interact v0.11.3 installs cleanly and can connect to BimodalLogic via the Lean REPL.

**Tasks**:
- [ ] Install lean-interact: `pip install -e ".[lean]"` and verify import succeeds
- [ ] Verify BimodalLogic build cache exists at the configured path (run `lake build` if needed)
- [ ] Add `BIMODAL_LOGIC_PATH` configuration to `src/bimodal_harness/config.py` with environment variable override and default path
- [ ] Write a minimal Python script that instantiates `LocalProject`, creates `LeanREPLConfig` and `LeanServer`, and runs `Command(cmd="#check @id")` to confirm REPL connectivity
- [ ] Verify the REPL can import BimodalLogic modules: `Command(cmd="import Bimodal.Syntax.Formula")`

**Timing**: 1 hour

**Depends on**: none

**Files to modify**:
- `src/bimodal_harness/config.py` - Add `BIMODAL_LOGIC_PATH` and lean bridge configuration constants

**Verification**:
- `python -c "from lean_interact import LocalProject, LeanServer"` succeeds
- REPL returns a response (not an error) for `#check @id` in BimodalLogic context
- BimodalLogic module import succeeds in REPL session

---

### Phase 2: Implement LeanBridge Wrapper Class [COMPLETED]

**Goal**: Flesh out `bridge.py` with a `LeanBridge` class providing the core API for downstream tasks (Task 9, 13, 15+).

**Tasks**:
- [ ] Implement `LeanBridge` class in `src/bimodal_harness/lean/bridge.py` with:
  - `__init__(self, project_path: str | None = None, auto_recover: bool = True)` - Creates `LocalProject`, `LeanREPLConfig`, and `AutoLeanServer` (or `LeanServer`)
  - `start() -> None` - Initializes the REPL session and imports core BimodalLogic modules
  - `stop() -> None` - Tears down the REPL process cleanly
  - Context manager protocol (`__enter__`, `__exit__`) for safe lifecycle management
  - `run_command(cmd: str) -> CommandResponse` - Execute arbitrary Lean command
  - `label_formula(formula: str) -> LabelResult` - Send formula to `labelFormula` via `#eval`
  - `apply_tactic(proof_state: int, tactic: str) -> TacticResult` - Send `ProofStep` and return goals/status
  - `run_subprocess(args: list[str]) -> SubprocessResult` - Wrapper for `lake exe` commands (dataset_generator, dataset_validator)
- [ ] Define result dataclasses: `CommandResponse`, `LabelResult`, `TacticResult`, `SubprocessResult` with typed fields
- [ ] Implement error handling: catch REPL errors, timeout handling, malformed input recovery
- [ ] Update `src/bimodal_harness/lean/__init__.py` with public exports

**Timing**: 1.5 hours

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/lean/bridge.py` - Main implementation (currently empty stub)
- `src/bimodal_harness/lean/__init__.py` - Export `LeanBridge` and result types

**Verification**:
- `from bimodal_harness.lean import LeanBridge` succeeds
- Type checking passes: `mypy src/bimodal_harness/lean/`
- Linting passes: `ruff check src/bimodal_harness/lean/`

---

### Phase 3: Write Validation Tests [NOT STARTED]

**Goal**: Create a comprehensive test suite (marked `@pytest.mark.lean`) that validates both REPL and subprocess paths against live BimodalLogic.

**Tasks**:
- [ ] Create `tests/test_lean/` directory with `__init__.py` and `conftest.py` (lean-specific fixtures)
- [ ] Create `tests/test_lean/test_bridge.py` with tests:
  - `test_lean_bridge_connects` - Instantiates LeanBridge, verifies REPL is alive
  - `test_import_bimodal_syntax` - Runs `import Bimodal.Syntax.Formula` via bridge
  - `test_check_formula_type` - Runs `#check Bimodal.Syntax.Formula.atom_s` and verifies response
  - `test_eval_formula_prettyprint` - Runs `#eval (Bimodal.Syntax.Formula.atom_s "p").prettyPrint` and verifies output
  - `test_label_formula` - Calls `bridge.label_formula(...)` with a simple formula
  - `test_apply_tactic` - Calls `bridge.apply_tactic(...)` with a known-valid tactic step
  - `test_subprocess_dataset_generator` - Calls `bridge.run_subprocess(["dataset_generator", "--help"])` and verifies output
  - `test_bridge_context_manager` - Verifies `with LeanBridge() as bridge:` lifecycle
  - `test_bridge_error_recovery` - Sends malformed input, verifies AutoLeanServer recovers
- [ ] Add lean-specific fixtures in `tests/test_lean/conftest.py`:
  - `lean_bridge` fixture (session-scoped) that creates and tears down a single LeanBridge
  - Skip logic if lean-interact is not installed or BimodalLogic path is invalid

**Timing**: 1 hour

**Depends on**: 2

**Files to modify**:
- `tests/test_lean/__init__.py` - New file
- `tests/test_lean/conftest.py` - Lean test fixtures
- `tests/test_lean/test_bridge.py` - Bridge validation tests

**Verification**:
- `pytest tests/test_lean/ -m lean -v` runs all tests (some may require `--run-lean` flag)
- All tests pass against live BimodalLogic REPL
- Default `pytest` (without `-m lean`) skips these tests cleanly

---

### Phase 4: Latency Benchmarks and Risk Gate Report [NOT STARTED]

**Goal**: Measure cold/warm startup and per-operation latencies to produce the benchmarks required by the task description. Update the task summary with pass/fail risk gate verdict.

**Tasks**:
- [ ] Create `tests/test_lean/test_benchmarks.py` with benchmark tests (marked `@pytest.mark.lean` and `@pytest.mark.slow`):
  - `test_benchmark_cold_start` - Measure `LeanBridge()` instantiation from cold state
  - `test_benchmark_warm_start` - Measure `LeanBridge()` when REPL cache is warm
  - `test_benchmark_import_mathlib` - Measure time to import a Mathlib-dependent BimodalLogic module
  - `test_benchmark_eval_formula` - Measure per-formula `#eval` latency (10 iterations, report mean/std)
  - `test_benchmark_tactic_step` - Measure per-tactic `ProofStep` latency (10 iterations)
  - `test_benchmark_subprocess` - Measure `lake exe dataset_generator` invocation time
- [ ] Each benchmark test records timing data and prints results to stdout
- [ ] Write implementation summary to `specs/006_validate_python_lean_bridge_options/summaries/01_bridge-validation-summary.md` containing:
  - Benchmark results table (operation, cold, warm, per-call)
  - Risk gate verdict: PASS or FAIL with justification
  - Comparison against research latency estimates
  - Recommendations for downstream tasks (9, 13, 15)

**Timing**: 0.5 hours

**Depends on**: 3

**Files to modify**:
- `tests/test_lean/test_benchmarks.py` - Latency benchmark tests

**Verification**:
- `pytest tests/test_lean/test_benchmarks.py -m "lean and slow" -v -s` runs and reports latencies
- Summary file exists with benchmark table and risk gate verdict
- Latencies are within expected ranges from research (REPL call < 500ms, tactic < 100ms)

## Testing & Validation

- [ ] `pip install -e ".[lean]"` completes without errors
- [ ] `python -c "from bimodal_harness.lean import LeanBridge"` succeeds
- [ ] `mypy src/bimodal_harness/lean/` passes with no errors
- [ ] `ruff check src/bimodal_harness/lean/` passes with no warnings
- [ ] `pytest tests/test_lean/ -m lean -v` -- all validation tests pass
- [ ] `pytest tests/test_lean/test_benchmarks.py -m "lean and slow" -v -s` -- benchmarks complete with latencies recorded
- [ ] Default `pytest` (without lean marker) skips all lean tests cleanly
- [ ] Risk gate verdict documented in summary

## Artifacts & Outputs

- `src/bimodal_harness/config.py` - Updated with BIMODAL_LOGIC_PATH configuration
- `src/bimodal_harness/lean/bridge.py` - LeanBridge class implementation
- `src/bimodal_harness/lean/__init__.py` - Updated exports
- `tests/test_lean/__init__.py` - New test package
- `tests/test_lean/conftest.py` - Lean test fixtures
- `tests/test_lean/test_bridge.py` - Bridge validation tests
- `tests/test_lean/test_benchmarks.py` - Latency benchmark tests
- `specs/006_validate_python_lean_bridge_options/summaries/01_bridge-validation-summary.md` - Risk gate report

## Rollback/Contingency

If lean-interact REPL integration proves unstable:
1. Fall back to subprocess-only path (`lake exe dataset_generator` / `dataset_validator`)
2. Implement `LeanBridge` with subprocess methods only, disable REPL-dependent tests
3. Document the limitation for downstream tasks that require interactive REPL (Task 13, 15)
4. If subprocess path also fails, escalate: this is a critical risk gate and blocks Tasks 9 and 13

If BimodalLogic build is broken or path is inaccessible:
1. Skip Lean-dependent tests with clear skip messages
2. Document the dependency in the summary as a prerequisite for CI
