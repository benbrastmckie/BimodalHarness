# Value Network Integration with Lean Proof Search

**Task**: 13 — Integrate value network with Lean proof search
**Date**: 2026-05-29
**Agent**: python-research-agent

---

## Executive Summary

The value network integration cannot proceed via the Lean-native search engine
(Option B). The Lean search runs inside the REPL and cannot call back into Python
during execution. The only viable approach is Option A: **Python drives search,
calls Lean for tactic verification only**. This requires implementing a pure-Python
best-first search loop that mirrors `bestFirst_search` from Strategies.lean,
scored with the value network, and using the LeanBridge solely to verify
individual proof closures. `search/best_first.py` is already a stub waiting for
this implementation.

The value network stub (`models/value.py`) and evaluation stub
(`evaluation/benchmark.py`) are both empty — all neural model and benchmark code
must be written from scratch in this task and its predecessors.

---

## 1. Existing Infrastructure Survey

### 1.1 LeanBridge (task 6) — bridge.py

`/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/lean/bridge.py`

Fully implemented. Key capabilities relevant to task 13:

| Method | Use in task 13 |
|--------|----------------|
| `run_command(cmd)` | Execute `#eval search(...)` for batch verification |
| `label_formula(formula)` | Verify that a formula is provable (binary decision) |
| `apply_tactic(proof_state, tactic)` | Check single tactic steps in tactic-mode proofs |
| `run_subprocess(args)` | Call `lake exe dataset_generator` for batch labelling |

`AutoLeanServer` is used by default (`LEAN_AUTO_RECOVER=True`), providing crash
recovery for long training loops.

**Latency** (from task 6 research):
- `#eval labelFormula`: 10–500 ms per query
- `ProofStep` tactic: 5–100 ms per step
- Cold REPL startup: 30–120 s (one-time per session)

### 1.2 Value Network (task 11) — models/value.py

Currently a stub: only `from __future__ import annotations`. All neural model
code must be implemented in task 11 before this integration point. The research
report from task 10 specifies the 12-dim PatternKey tensor encoding:

| Indices | Feature | Encoding |
|---------|---------|----------|
| 0 | modal_depth | float (log1p-normalized) |
| 1 | temporal_depth | float |
| 2 | imp_count | float (log1p) |
| 3 | complexity | float (log1p) |
| 4–11 | top_operator | one-hot over 8 GoalCategory values |

The feature extractor (`schema/features.py`) is fully implemented and produces
`PatternKey` instances ready for tensor encoding.

### 1.3 Evaluation (task 12) — evaluation/benchmark.py

Currently a stub: only `from __future__ import annotations`. All benchmark code
must be implemented.

### 1.4 Python-Side Search Stub — search/best_first.py

`/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/search/best_first.py`

Also a stub. This is the **primary target** for task 13: implement a
Python-native best-first search that mirrors Lean's `bestFirst_search` but calls
the value network for heuristic scoring.

---

## 2. Lean Search Architecture

### 2.1 `SearchNode` (Strategies.lean lines 17–28)

```lean
structure SearchNode where
  context : Context        -- List[Formula]
  goal    : Formula
  cost    : Nat            -- path length (steps taken)
  heuristic : Nat          -- estimated remaining cost
  fscore  : Nat := cost + heuristic
```

The `heuristic` field is populated by `pattern_aware_score` (Core.lean line 735),
which combines:
1. `advanced_heuristic_score` (base rules: axiom=0, assumption=1, modus ponens, modal/temporal costs)
2. `patternDb.heuristicBonus` (learned pattern bonus from `PatternDatabase`)

### 2.2 `heuristic_score` (Core.lean lines 650–668)

The base scoring function:
- Axiom match: 0 (top priority)
- Context assumption: 1
- Modus ponens: `mpBase(2) + min_complexity * mpComplexityWeight`
- Modal box: `modalBase(5) + contextPenaltyWeight * |Γ|`
- Until: `temporalBase(5) + contextPenaltyWeight * |Γ|`
- Dead end: 100

### 2.3 `advanced_heuristic_score` (Core.lean lines 686–692)

Adds domain bonuses on top of `heuristic_score`:
- Modal bonus: −5 for `box`/`diamond` goals
- Temporal bonus: −5 for temporal operator goals
- Structure penalty: `structure_heuristic(φ) / 4` (damped)

Combined score is clamped to 0 minimum (`.toNat`).

### 2.4 `pattern_aware_score` (Core.lean lines 735–740)

```lean
def pattern_aware_score ... : Nat :=
  let baseScore : Int := advanced_heuristic_score weights Γ φ
  let patternBonus := patternDb.heuristicBonus φ strategy
  (baseScore + patternBonus).toNat
```

Pattern bonuses from `PatternDatabase.heuristicBonus` (SuccessPatterns.lean):
- >80% success rate: −10 bonus
- >50% success rate: −5 bonus
- >20% success rate: −2 bonus

### 2.5 Search Loop

The `bestFirst_search` function in Strategies.lean (lines 90–173) runs a standard
A* loop: priority queue ordered by `fscore`, expansion generates `mpNodes`,
`modalNodes`, `temporalNodes`, scores them via `pattern_aware_score`. No external
callback is possible in this context.

---

## 3. Integration Architecture Decision

### Option A: Python Drives Search (RECOMMENDED)

Python implements the full priority queue search loop. At each node expansion,
Python computes the heuristic score as:

```
heuristic(Γ, φ) = advanced_heuristic_score(Γ, φ)   [rule-based]
                 + value_network_bonus(Γ, φ)          [neural additive bonus]
```

Lean is only called when Python needs to **verify** a leaf node (axiom or
assumption check), or for final proof validation. The bridge `label_formula`
call verifies provability end-to-end.

**Advantages**:
- No modification to Lean source required
- Value network scoring runs at Python speed (batched GPU inference)
- Full control over search hyperparameters in Python
- Works with existing `LeanBridge.label_formula` for verification

**Disadvantages**:
- Must reimplement Lean's search logic in Python (but `best_first.py` is a stub
  awaiting this exact implementation)
- Python rule-based scoring must exactly mirror Lean's formulas for fair A/B comparison

### Option B: Lean Drives Search, Calls Python (NOT VIABLE)

Lean's proof search runs inside the REPL as a pure Lean function. There is no
mechanism to call back into Python during Lean REPL execution. Lean has no
foreign function interface to Python during proof search. This option is
technically impossible without modifying the Lean source to add an IPC layer.

### Option C: Hybrid (NOT RECOMMENDED FOR TASK 13)

Periodic checkpoints would require modifying `bestFirst_search` to serialize
the priority queue state to JSON, pass it to Python for scoring, and reload it.
This is feasible in principle but adds significant Lean serialization complexity
and does not improve over Option A for this use case.

**Decision: Option A** — Python implements the search loop in `search/best_first.py`.

---

## 4. Additive Bonus Design

### 4.1 Score Combination

The value network provides an **additive bonus** to the rule-based heuristic:

```python
def compute_heuristic(context, goal, value_net, weights):
    rule_score = advanced_heuristic_score(context, goal, weights)
    value_estimate = value_net.predict(extract_pattern_key(goal))
    # value_estimate in [0, 1]: 1.0 = high confidence this is provable
    # Convert to additive bonus: lower score = higher priority
    # A value of 1.0 gives maximum bonus (-alpha)
    neural_bonus = -alpha * value_estimate
    return max(0, int(rule_score + neural_bonus))
```

The blending weight `alpha` controls how much the value network influences
ordering relative to the rule-based score. Recommended initial value: `alpha = 5`
(same magnitude as the modal/temporal bonuses in `advanced_heuristic_score`).

### 4.2 Temperature Scaling

Before computing the neural bonus, apply temperature scaling to the raw value
estimate to prevent overconfidence:

```python
value_scaled = sigmoid(logit(value_estimate) / temperature)
```

`temperature = 1.0` is neutral; `temperature > 1.0` flattens confidence. Start
with `temperature = 1.5` to avoid the value network dominating cold-start models.

### 4.3 Fallback Behavior

When the value network is `None` or disabled, the search falls back to the pure
rule-based `advanced_heuristic_score`, producing identical behavior to Lean's
current `bestFirst_search`. This ensures clean A/B comparison.

### 4.4 Goal-Level vs. State-Level Scoring

The `PatternKey` (12-dim) encodes goal formula features only, not the full proof
context. Two options:
- **Goal-only** (simple): score(goal) — ignores context assumptions
- **Goal + context summary** (extended): concatenate goal features with context
  summary features (e.g., context length, fraction of modal formulas)

Start with goal-only to match the feature spec from task 10. The 12-dim tensor
is the minimum viable input.

---

## 5. Module Design for task 13

### 5.1 `search/best_first.py`

Primary implementation target. Must implement:

```python
@dataclass
class SearchNode:
    context: list[dict]  # formula JSON list
    goal: dict           # formula JSON
    cost: int
    heuristic: int

class PythonBestFirstSearch:
    def __init__(
        self,
        value_net=None,         # optional: ValueNetwork instance
        weights=None,           # HeuristicWeights (mirrors Lean's)
        alpha: float = 5.0,     # neural bonus weight
        temperature: float = 1.5,
        max_expansions: int = 10000,
    ): ...

    def search(
        self,
        context: list[dict],
        goal: dict,
        bridge: LeanBridge,     # for leaf verification
    ) -> tuple[bool, SearchStats]: ...
```

The rule-based scoring functions (axiom check, assumption check, implication
search, modal/temporal cost) must be ported from Core.lean into Python, using
`schema/features.py` for formula analysis.

### 5.2 `models/value.py` (task 11 prerequisite)

Needs to expose:
```python
class ValueNetwork:
    def predict(self, pattern_key: PatternKey) -> float: ...
    def predict_batch(self, keys: list[PatternKey]) -> list[float]: ...
    @classmethod
    def load(cls, path: str) -> "ValueNetwork": ...
```

The integration in `best_first.py` calls `predict_batch` for all nodes in the
expansion set to amortize GPU latency.

### 5.3 `evaluation/benchmark.py` (task 12 prerequisite)

Needs to expose:
```python
class BenchmarkSuite:
    formulas: list[tuple[list[dict], dict, bool]]  # (context, goal, expected)

def run_comparison(
    baseline_searcher,
    neural_searcher,
    suite: BenchmarkSuite,
) -> ComparisonResult: ...
```

---

## 6. Evaluation Protocol

### 6.1 A/B Comparison

Two conditions:
- **Baseline**: `PythonBestFirstSearch(value_net=None)` — pure rule-based
- **Neural**: `PythonBestFirstSearch(value_net=loaded_model)` — with value network

Both run on identical benchmark formulas (from task 12). The Python search must
produce the same results as Lean's `bestFirst_search` in baseline mode (validation
criterion before adding the neural component).

### 6.2 Metrics

| Metric | How to measure |
|--------|----------------|
| Proof rate | #proofs found / #formulas |
| Node expansions | SearchStats.visited average |
| Wall-clock time | time.perf_counter() per formula |
| Visit limit hits | SearchStats.prunedByLimit rate |

Primary metric: **proof rate at fixed expansion budget** (e.g., 1000 expansions).
Secondary: mean expansions-to-proof for successful cases.

### 6.3 Statistical Significance

Minimum benchmark size: 200 formulas (100 provable, 100 non-provable) for 80%
power to detect a 5pp proof rate improvement with p < 0.05. Use McNemar's test
for paired comparison (same formulas tested under both conditions).

---

## 7. Latency Analysis

The critical constraint: value network inference must not dominate expansion time.

| Operation | Estimated latency |
|-----------|-------------------|
| Rule-based heuristic (Python) | < 1 ms |
| `PatternKey` extraction per goal | < 1 ms |
| Value network inference (CPU, single) | 1–5 ms |
| Value network inference (batched, GPU) | < 0.5 ms/item at batch=32 |
| Lean `label_formula` verification | 10–500 ms |

The value network scoring per expansion must be < 5 ms to keep per-node cost under
10 ms total. With batched inference, scoring an entire expansion's successors in
one GPU call is feasible.

For **interactive search** (user-facing), the search budget should be capped at
~30 seconds, implying at most 3000 expansions at 10 ms/expansion. This is
sufficient for most benchmark formulas.

---

## 8. Dependency Chain

| Dependency | Status | Blocking? |
|------------|--------|-----------|
| LeanBridge (task 6) | COMPLETED | No — bridge.py is implemented |
| PatternKey extractor (task 10) | COMPLETED | No — features.py is implemented |
| Value network (task 11) | STUB ONLY | Yes — models/value.py needs implementation |
| Benchmark suite (task 12) | STUB ONLY | Yes — evaluation/benchmark.py needs implementation |
| Python best-first search (task 13) | STUB ONLY | This task |

Task 13 can proceed to implementation once tasks 11 and 12 have completed their
core model/benchmark implementations.

---

## 9. Files to Implement

| File | Status | Notes |
|------|--------|-------|
| `src/bimodal_harness/search/best_first.py` | Stub | Primary: Python A* + neural scorer |
| `src/bimodal_harness/models/value.py` | Stub | Prerequisite: ValueNetwork class |
| `src/bimodal_harness/evaluation/benchmark.py` | Stub | Prerequisite: BenchmarkSuite + run_comparison |
| `tests/test_search/test_best_first.py` | Missing | Unit + integration tests |
| `tests/test_evaluation/test_benchmark.py` | Missing | Comparison test runner |

No Lean source modifications are needed.

---

## 10. Key Design Decisions

1. **Option A only**: Python drives the search; Lean is for verification only.
   The REPL cannot callback to Python.

2. **Additive bonus with weight alpha**: Start `alpha=5`, tune via grid search
   over {1, 2, 5, 10} on a validation split of the benchmark.

3. **Goal-level scoring only**: Use 12-dim PatternKey tensor; context features
   added only if baseline gap remains after initial experiments.

4. **Batched inference**: Score all successor nodes in one `predict_batch` call
   per expansion to amortize GPU overhead.

5. **Baseline parity check**: The Python baseline (value_net=None) must replicate
   Lean's `bestFirst_search` results exactly on the validation set before enabling
   the neural component. This confirms the port is correct.

6. **McNemar test**: Paired binary outcomes per formula → McNemar's test is the
   correct statistical test, not an unpaired proportion test.
