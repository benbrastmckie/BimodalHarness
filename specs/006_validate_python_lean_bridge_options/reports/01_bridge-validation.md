# Python-Lean Bridge Validation Report

**Task**: 6 — Validate Python-Lean bridge options (Critical Risk Gate)
**Date**: 2026-05-29
**Lean version under test**: `leanprover/lean4:v4.27.0-rc1`

---

## Executive Summary

**Recommended bridge: lean-interact v0.11.3 (CLEAR WINNER)**

lean-interact explicitly supports `v4.8.0-rc1` through `v4.30.0-rc2`, directly
covering `v4.27.0-rc1`. It provides a clean `LocalProject` API that can load
BimodalLogic without any lakefile modifications, has a `ProofStep` tactic
interface matching expert iteration needs, and is already declared as an
optional dependency in `pyproject.toml` (`lean = ["lean-interact>=0.11.0"]`).

LeanDojo-v2 and PyPantograph are not recommended for this project.

---

## 1. Lean Environment (BimodalLogic)

### 1.1 Toolchain

```
leanprover/lean4:v4.27.0-rc1
```

Elan toolchain `leanprover--lean4---v4.27.0-rc1` is already installed at
`~/.elan/toolchains/`.

### 1.2 lakefile.lean Summary

- Package: `Logos`
- Dependencies: `mathlib @ v4.27.0-rc1`, `plausible @ main`
- Main library target: `Bimodal` (srcDir: `Theories/`)
- Test target: `BimodalTest` (srcDir: `Tests/`)
- Executables: `dataset_generator`, `dataset_validator` (both with `supportInterpreter := true`)

### 1.3 API Surface for Expert Iteration

BimodalLogic does **not** expose a "ProofChecker" named module. The proof-relevant
API is distributed across:

- `Bimodal.Metalogic.Decidability.DecisionProcedure` — `decide` function
  (complete decision procedure for TM logic)
- `Bimodal.Automation.ProofSearch.Core` — `search`, `iddfs_search`, `bestFirst_search`
  (tactic-level proof search with pattern learning)
- `Bimodal.Automation.DatasetGenerator` — `labelFormula`, `labelBatch`
  (runs decision procedure, extracts `ProofTrace`)
- `Bimodal.Automation.DatasetValidator` — `runConformanceTests`, `runFeasibilityGate`
  (validation pipeline)

For expert iteration (Task 15+), the bridge needs to:
1. Send a formula string or AST into a Lean environment
2. Apply tactic steps (via the REPL or via `labelFormula` invocation)
3. Receive goal state or `LabeledFormula` records

The `dataset_generator` and `dataset_validator` executables (`lake exe`) are the
easiest entry point from Python via subprocess. A tighter REPL-based integration
is possible via lean-interact.

---

## 2. Bridge Candidate Analysis

### 2.1 lean-interact v0.11.3 (PRIMARY CANDIDATE)

**Verdict: COMPATIBLE — use this.**

#### Version Support
- PyPI latest: 0.11.3 (released May 14, 2026)
- Supported Lean range: `v4.8.0-rc1` through `v4.30.0-rc2`
- `v4.27.0-rc1` falls inside this range

#### Mechanism
lean-interact wraps the Lean REPL (`leanprover/repl`) via subprocess. It
maintains a forked REPL that backports features to older versions, ensuring
compatibility with v4.27 even as the REPL advances.

#### Python API
```python
from lean_interact import LocalProject, LeanREPLConfig, LeanServer
from lean_interact import Command, ProofStep

# Load BimodalLogic as a local project
project = LocalProject(directory="/path/to/BimodalLogic")
config = LeanREPLConfig(project=project)
server = LeanServer(config)

# Execute Lean code in project context
resp = server.run(Command(cmd='import Bimodal.Automation\n#check labelFormula'))

# Tactic-level interaction
resp = server.run(ProofStep(proof_state=0, tactic="modal_search"))
# Returns ProofStepResponse with:
#   .goals: List[str]  -- remaining goal strings
#   .proof_status: str -- "complete", "goals_remaining", "error"
#   .proof_state: int  -- new state ID for chaining
```

**Other key query types:**
- `FileCommand(path="file.lean")` — process a Lean file
- `PickleEnvironment` / `UnpickleEnvironment` — persist environment across sessions
- `PickleProofState` / `UnpickleProofState` — persist proof state
- `AutoLeanServer` — auto-recovers from REPL crashes (useful in training loops)

#### Project Loading Requirement
The project must be successfully built (`lake build`) before lean-interact can
use it. BimodalLogic is already built (`.lake/build/` exists). This is not a
blocking requirement.

#### Integration with pyproject.toml
lean-interact is already declared:
```toml
[project.optional-dependencies]
lean = [
  "lean-interact>=0.11.0",
]
```
Install with: `pip install -e ".[lean]"`

#### Latency Characteristics
- First `LeanREPLConfig` instantiation: slow (downloads/builds REPL, one-time)
- Subsequent `server.run()` calls: fast (REPL process already running)
- Mathlib import overhead: significant on first use, then cached
- `AutoLeanServer` adds crash recovery overhead but is recommended for long
  training loops where the REPL may crash on malformed tactics

#### Risks
- **None blocking**: v4.27.0-rc1 is within the supported range
- REPL crash possible on malformed input — mitigated by `AutoLeanServer`

---

### 2.2 LeanDojo-v2 (ALTERNATIVE — NOT RECOMMENDED)

**Verdict: WRONG TOOL for this use case.**

#### Summary
LeanDojo-v2 is a training/evaluation framework for full theorem-proving systems,
not a lightweight runtime bridge. It wraps PyPantograph internally for tactic
interaction and adds dataset management, HuggingFace fine-tuning, and
retrieval-augmented provers on top.

#### Version Support
- No explicit Lean version matrix documented
- Uses elan and respects project toolchains
- LeanCopilot (same ecosystem) has commits targeting v4.27, suggesting
  ecosystem-level compatibility — but not formally guaranteed for LeanDojo-v2

#### Requirements
- Python >= 3.11, CUDA GPU (for training/inference), Git >= 2.25
- Clones and traces Lean repos; requires `ExtractData.lean` instrumentation
- No lakefile modifications needed, but repo-tracing setup is heavyweight

#### Why Not
- Designed for offline repository tracing, not runtime REPL interaction
- GPU requirement is a CI/deployment burden for what should be a lightweight bridge
- Internally depends on PyPantograph (see below) which has its own version pinning issues
- Overkill: expert iteration only needs a REPL bridge, not a full training framework

---

### 2.3 PyPantograph (BACKUP — NOT RECOMMENDED)

**Verdict: VERSION PINNING IS A HARD BLOCKER.**

#### Summary
PyPantograph (Stanford Centaur lab) provides a machine-to-machine Lean 4
interface. It bundles its own Lean installation (Pantograph as a Lean library)
at a pinned version.

#### Version Pinning Problem
PyPantograph pins its own Lean toolchain in `src/` and `examples/lean-toolchain`.
When used with a Lean project that has a different toolchain (e.g., v4.27.0-rc1),
PyPantograph may fail to load `.olean` files from the project's toolchain, because
its embedded Lean binary differs from the project's.

An existing GitHub issue (#73 in the stanford-centaur/PyPantograph repo) documents
exactly this scenario: the REPL finds the correct Lean path but cannot locate
Mathlib's `.olean` files because the toolchain versions differ.

#### API
```python
# goal_tactic(goal, tactic) -> updated goal state
# check_track(file) -> conformity check
# Extraction of tactic invocation data
```

#### Why Not
- Version pin conflict with v4.27.0-rc1 is a hard blocker without patching
- Would require rebuilding Pantograph against v4.27.0-rc1 from source
- lean-interact solves the same problem more cleanly

---

## 3. Expert Iteration Integration Strategy

For Task 15+ (expert iteration, runtime proof checking), the recommended
integration pattern using lean-interact:

### 3.1 Two-Path Architecture

**Path A: Subprocess (simple, robust)**
```python
import subprocess, json

result = subprocess.run(
    ["lake", "exe", "dataset_generator", "--", "--max-complexity", "3",
     "--output", "/tmp/batch.jsonl"],
    cwd="/path/to/BimodalLogic",
    capture_output=True, text=True
)
records = [json.loads(l) for l in open("/tmp/batch.jsonl")]
```
Use for: batch labeling, offline dataset generation. Zero bridge overhead.

**Path B: REPL (interactive, low-latency for training loops)**
```python
from lean_interact import LocalProject, LeanREPLConfig, AutoLeanServer, Command

project = LocalProject(directory="/path/to/BimodalLogic")
server = AutoLeanServer(LeanREPLConfig(project=project))

# Import the labeling function once
server.run(Command(cmd="import Bimodal.Automation.DatasetGenerator"))

# Per-step interaction in expert iteration loop
resp = server.run(Command(cmd=f"#eval labelFormula ({formula_lean_expr})"))
```
Use for: online expert iteration where Python generates candidate formulas and
Lean validates them in real-time.

### 3.2 Latency Estimates

| Operation | Estimated Latency | Notes |
|-----------|------------------|-------|
| REPL startup (cold) | 30-120 s | One-time, downloads+builds REPL |
| REPL startup (warm) | 2-10 s | Cached after first run |
| Mathlib import (cold) | 60-180 s | One-time per project session |
| Mathlib import (warm) | 5-15 s | `.olean` cache hit |
| `#eval labelFormula` | 10-500 ms | Depends on formula complexity |
| `ProofStep` tactic | 5-100 ms | Single tactic step |
| `lake exe dataset_generator` (cold) | 1-5 s | Build cache warm, no Mathlib reimport |

Actual benchmarks will require runtime measurement in Task 6 implementation
phase once lean-interact is installed.

---

## 4. Existing Bridge Stub Assessment

`/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/lean/bridge.py`
contains only a module docstring and `from __future__ import annotations`.
`__init__.py` is similarly empty.

**Required implementation** (Task 15+ prerequisite):
1. `LeanBridge` class wrapping `AutoLeanServer`
2. `label_formula(formula: str) -> LabeledFormulaResult` method
3. `apply_tactic(proof_state: int, tactic: str) -> ProofStepResult` method
4. Startup/teardown lifecycle management
5. Connection pool for parallel training workers

---

## 5. Compatibility Matrix

| Bridge | Lean v4.27.0-rc1 | Lakefile changes needed | Latency profile | Recommendation |
|--------|-----------------|------------------------|-----------------|----------------|
| lean-interact 0.11.3 | YES (confirmed) | None | Low (REPL) | **USE THIS** |
| LeanDojo-v2 1.0.4 | Likely (unconfirmed) | None | High (tracing overhead) | Not recommended |
| PyPantograph | BLOCKED (pin conflict) | None | Low (if pin resolved) | Do not use |

---

## 6. Recommended Next Steps

1. **Install lean-interact**: `pip install -e ".[lean]"` in BimodalHarness
2. **Smoke test**: Write a pytest (marked `@pytest.mark.lean`) that:
   - Instantiates `LocalProject(directory=BIMODAL_LOGIC_PATH)`
   - Runs `Command(cmd="import Bimodal.Automation.DatasetGenerator")`
   - Runs `Command(cmd="#eval (Bimodal.Syntax.Formula.atom_s \"p\").prettyPrint")`
   - Asserts successful response
3. **Latency benchmark**: Measure cold/warm startup times and per-formula labeling
   latency once smoke test passes
4. **Implement bridge stub**: Flesh out `bridge.py` with `LeanBridge` class for
   Task 15+ consumption

The subprocess path (`lake exe dataset_generator`) can serve as the fallback
if REPL integration proves unstable in long training runs.
