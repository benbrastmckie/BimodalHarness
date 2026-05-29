# Implementation Plan: Integrate Value Network with Lean Proof Search

- **Task**: 13 - Integrate value network with Lean proof search
- **Status**: [NOT STARTED]
- **Effort**: 8 hours
- **Dependencies**: Task 11 (value network), Task 12 (benchmark suite)
- **Research Inputs**: specs/013_integrate_value_network_with_lean_proof_search/reports/01_value-integration.md
- **Artifacts**: plans/01_value-integration-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: python
- **Lean Intent**: false

## Overview

Implement Python-driven best-first proof search in `search/best_first.py` that mirrors Lean's `bestFirst_search` from Strategies.lean. The search loop uses a priority queue scored by a rule-based heuristic (ported from Core.lean) with an additive neural bonus from the value network. Lean is called only for leaf verification via the existing LeanBridge. A comparison runner evaluates neural-augmented search versus pure rule-based baseline on a benchmark suite from task 12, using McNemar's test for statistical significance.

### Research Integration

Key findings from the research report (01_value-integration.md):

- **Architecture**: Option A (Python drives search) is the only viable approach. Lean's REPL cannot callback to Python during proof search execution.
- **Score blending**: Additive bonus with weight `alpha=5` and temperature scaling (`T=1.5`) to prevent overconfidence in cold-start models.
- **Feature encoding**: 12-dim PatternKey tensor (goal-level only). The `schema/features.py` extractor is fully implemented.
- **Latency budget**: Value network inference must stay under 5ms per node; batched GPU inference at 32 nodes achieves < 0.5ms/item.
- **Baseline parity**: Python rule-based baseline must replicate Lean's `bestFirst_search` results exactly before enabling the neural component.

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Implement a complete Python best-first search loop with priority queue in `search/best_first.py`
- Port Lean's rule-based heuristic scoring functions (`heuristic_score`, `advanced_heuristic_score`, `pattern_aware_score`) to Python
- Integrate the value network as an additive bonus with configurable `alpha` and `temperature` parameters
- Build an A/B comparison runner that evaluates neural vs. baseline on the benchmark suite
- Validate that the Python baseline produces identical results to Lean's search on a validation set

**Non-Goals**:
- Implementing the value network itself (task 11)
- Implementing the benchmark suite itself (task 12)
- Modifying any Lean source code
- Adding context-level features beyond the 12-dim PatternKey (deferred to future work)
- Hyperparameter tuning of `alpha`/`temperature` (this task sets up the infrastructure; tuning is a follow-on)

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Rule-based port diverges from Lean scoring | H | M | Validate baseline parity on 50+ formulas before adding neural component |
| Task 11/12 stubs not yet implemented | H | M | Design against documented interfaces; use mock ValueNetwork and BenchmarkSuite in tests |
| Value network inference too slow on CPU | M | L | Batch all successor nodes per expansion; add configurable batch size |
| Priority queue memory pressure on deep searches | M | L | Cap max_expansions (default 10000); track queue size in SearchStats |
| Formula JSON schema drift between Lean export and Python | L | L | Use existing schema/validation.py for input validation |

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

### Phase 1: Rule-Based Heuristic Port and Search Data Structures [COMPLETED]

**Goal**: Port Lean's heuristic scoring functions to Python and define all data structures needed by the search loop.

**Tasks**:
- [ ] Define `HeuristicWeights` dataclass in `search/best_first.py` mirroring Lean's weight constants (mpBase=2, modalBase=5, temporalBase=5, mpComplexityWeight, contextPenaltyWeight, dead_end=100)
- [ ] Define `SearchNode` dataclass with `context`, `goal`, `cost`, `heuristic`, `fscore` fields
- [ ] Define `SearchStats` dataclass with `visited`, `expanded`, `pruned_by_limit`, `max_queue_size`, `wall_clock_seconds` fields
- [ ] Implement `heuristic_score(context, goal, weights)` porting Core.lean lines 650-668 (axiom=0, assumption=1, modus ponens cost, modal/temporal cost, dead end=100)
- [ ] Implement `advanced_heuristic_score(context, goal, weights)` porting Core.lean lines 686-692 (domain bonuses for modal/temporal goals, structure penalty)
- [ ] Implement helper functions: `is_axiom(goal)`, `is_assumption(context, goal)`, `structure_heuristic(goal)`, `formula_eq(a, b)` for formula comparison
- [ ] Add unit tests in `tests/test_search/test_best_first.py` covering each scoring function against known Lean outputs

**Timing**: 2 hours

**Depends on**: none

**Files to modify**:
- `src/bimodal_harness/search/best_first.py` - Data structures and heuristic functions
- `tests/test_search/test_best_first.py` - Unit tests for scoring (create new)

**Verification**:
- All scoring functions return expected values for a set of 10+ hand-crafted formula/context pairs
- `pytest tests/test_search/test_best_first.py` passes

---

### Phase 2: Python Best-First Search Loop [COMPLETED]

**Goal**: Implement the core A* search loop that expands nodes using the priority queue, generates successor nodes (modus ponens, modal, temporal expansions), and calls LeanBridge for leaf verification.

**Tasks**:
- [ ] Implement `PythonBestFirstSearch` class with `__init__` accepting `value_net`, `weights`, `alpha`, `temperature`, `max_expansions`
- [ ] Implement node expansion: `_expand_node(node)` generating successor nodes via modus ponens application, modal rule application (box introduction), and temporal rule application (until/since unfolding)
- [ ] Implement `_compute_heuristic(context, goal)` combining rule-based score with optional neural bonus (additive, temperature-scaled)
- [ ] Implement `search(context, goal, bridge)` method: priority queue loop ordered by fscore, expansion with scoring, leaf verification via `bridge.label_formula`
- [ ] Implement fallback behavior: when `value_net is None`, use pure rule-based scoring (identical to Lean baseline)
- [ ] Add `SearchResult` dataclass wrapping `(proved: bool, stats: SearchStats)` as return type
- [ ] Add unit tests using mock LeanBridge (no real Lean dependency) for search loop mechanics

**Timing**: 2.5 hours

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/search/best_first.py` - Search loop implementation
- `tests/test_search/test_best_first.py` - Search loop unit tests (append to existing)

**Verification**:
- Search finds proof for trivial formulas (axiom, single-step modus ponens) using mock bridge
- Search correctly terminates at `max_expansions` limit
- SearchStats accurately tracks visited/expanded/queue metrics
- Fallback mode (no value network) produces identical ordering to pure heuristic
- `pytest tests/test_search/test_best_first.py` passes

---

### Phase 3: Value Network Integration and Score Blending [COMPLETED]

**Goal**: Wire the value network into the search heuristic with proper tensor encoding, batched inference, and temperature scaling. Handle the case where task 11 is not yet complete by supporting a mock/dummy value network.

**Tasks**:
- [ ] Implement `_pattern_key_to_tensor(key: PatternKey) -> list[float]` encoding the 12-dim tensor (4 numeric features log1p-normalized + 8-dim one-hot for GoalCategory) in `search/best_first.py`
- [ ] Implement temperature-scaled sigmoid: `_scale_value(raw_value, temperature)` using `sigmoid(logit(v) / T)` with numerical stability guards
- [ ] Implement `_batch_score_nodes(nodes, value_net, temperature)` calling `value_net.predict_batch` on all successor PatternKeys and returning per-node neural bonuses
- [ ] Define `ValueNetworkProtocol` (typing.Protocol) specifying `predict(PatternKey) -> float` and `predict_batch(list[PatternKey]) -> list[float]` for interface-driven testing independent of task 11
- [ ] Implement `MockValueNetwork` conforming to protocol for testing (returns configurable constant or random values)
- [ ] Add tests verifying: (a) tensor encoding matches expected 12-dim format, (b) temperature scaling produces expected output ranges, (c) batched scoring integrates correctly with search loop

**Timing**: 1.5 hours

**Depends on**: 2

**Files to modify**:
- `src/bimodal_harness/search/best_first.py` - Neural integration, tensor encoding, protocol
- `tests/test_search/test_best_first.py` - Neural scoring tests (append)

**Verification**:
- PatternKey encoding for a `box(imp(atom("p"), atom("q")))` formula produces correct 12-dim vector
- Temperature=1.0 preserves input values; temperature>1.0 flattens toward 0.5
- Search with MockValueNetwork(constant=0.9) prioritizes nodes differently than baseline
- `pytest tests/test_search/test_best_first.py` passes

---

### Phase 4: A/B Comparison Runner and Integration Tests [COMPLETED]

**Goal**: Build the comparison infrastructure that runs baseline vs. neural search on a benchmark suite and computes statistical significance. Write integration tests that validate end-to-end behavior.

**Tasks**:
- [ ] Implement `ComparisonResult` dataclass in `evaluation/benchmark.py` or `search/best_first.py` with per-formula results, aggregate metrics (proof_rate, mean_expansions, mean_time), and McNemar test p-value
- [ ] Implement `run_comparison(baseline_searcher, neural_searcher, formulas)` function that runs both searchers on each formula and collects paired outcomes
- [ ] Implement McNemar's test computation: build 2x2 contingency table of (baseline_found, neural_found) outcomes; compute chi-squared statistic and p-value
- [ ] Add a CLI-compatible entry point or function `run_benchmark_comparison(model_path, benchmark_path, alpha, temperature, max_expansions)` for scripted evaluation
- [ ] Write integration test using mock bridge and mock value network that validates the full pipeline: benchmark loading -> baseline run -> neural run -> comparison output
- [ ] Update `search/__init__.py` to export `PythonBestFirstSearch`, `SearchNode`, `SearchStats`, `SearchResult`

**Timing**: 2 hours

**Depends on**: 3

**Files to modify**:
- `src/bimodal_harness/search/best_first.py` - ComparisonResult and run_comparison (or evaluation/benchmark.py if task 12 provides the host module)
- `src/bimodal_harness/search/__init__.py` - Public exports
- `tests/test_search/test_best_first.py` - Integration tests (append)
- `tests/test_search/test_comparison.py` - Comparison runner tests (create new)

**Verification**:
- run_comparison produces correct proof rates for a 10-formula mock benchmark
- McNemar p-value computed correctly for known contingency tables
- Full pipeline test passes without any real Lean or GPU dependency
- `pytest tests/test_search/` passes all tests

## Testing & Validation

- [ ] Unit tests: All scoring functions match expected Lean outputs for hand-crafted formulas
- [ ] Unit tests: Search loop finds proofs, respects expansion limits, tracks stats
- [ ] Unit tests: Tensor encoding produces correct 12-dim vectors for all GoalCategory values
- [ ] Unit tests: Temperature scaling produces expected output ranges
- [ ] Integration tests: Mock bridge + mock value network end-to-end search
- [ ] Integration tests: Comparison runner produces valid ComparisonResult with McNemar p-value
- [ ] Baseline parity: Python rule-based search (value_net=None) produces identical results to mock of Lean's bestFirst_search on validation formulas
- [ ] All tests pass: `pytest tests/test_search/ -v`

## Artifacts & Outputs

- `src/bimodal_harness/search/best_first.py` - Python best-first search with neural scorer
- `src/bimodal_harness/search/__init__.py` - Updated public exports
- `tests/test_search/test_best_first.py` - Unit and integration tests
- `tests/test_search/test_comparison.py` - Comparison runner tests
- `specs/013_integrate_value_network_with_lean_proof_search/plans/01_value-integration-plan.md` - This plan
- `specs/013_integrate_value_network_with_lean_proof_search/summaries/01_value-integration-summary.md` - Execution summary (created by /implement)

## Rollback/Contingency

All implementation is in new or stub files. Rollback consists of:
1. Revert `search/best_first.py` to its 3-line stub
2. Revert `search/__init__.py` to its 2-line stub
3. Remove new test files (`test_best_first.py`, `test_comparison.py`)

No existing code is modified, so rollback has zero risk of breaking other modules. If task 11 (value network) is delayed, the search module functions fully in baseline mode (value_net=None) and all tests pass using the MockValueNetwork protocol.
