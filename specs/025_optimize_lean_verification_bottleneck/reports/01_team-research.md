# Research Report: Task #25

**Task**: 25 - Optimize Lean verification bottleneck for expert iteration
**Date**: 2026-05-29
**Mode**: Team Research (4 teammates)
**Session**: sess_1780094525_bd653c

## Summary

Four-teammate investigation of Lean verification optimization for the expert iteration training loop. The team converges on three key conclusions: (1) the bottleneck assumption is unvalidated and benchmarking must come first, (2) the Kimina Lean Server is a production-tested drop-in solution that addresses the Lean-side bottleneck in 1-2 days, and (3) a dual-verification architecture (fast Python checker for training, Lean for final validation) provides the highest-throughput path but carries trust tradeoffs that must be weighed against commercial goals. The critic identified a likely silent bug in the bridge import configuration that should be fixed immediately.

## Key Findings

### 1. Benchmark Before Optimizing (All Teammates Converge)

No profiling data exists in the codebase. The `elapsed` field is recorded per REPL call in `bridge.py` but never aggregated. The 10-500ms per-verification estimate from Task 6 research is theoretical and spans two orders of magnitude. The Python search in `best_first.py` already minimizes Lean calls — `_is_proved()` checks axioms and assumptions locally, calling Lean only at non-trivial proof leaves (0-3 calls per formula search, not one per expansion).

**Required before any optimization investment:**
- Wall-clock breakdown: what fraction of expert iteration time is (Python search, neural inference, Lean verification)?
- Latency distribution: run 500 `label_formula` calls against real formulas and plot the distribution
- Scale target: how many Lean verifications per training epoch? (1K = non-issue, 100K = critical)

### 2. Kimina Lean Server: Production-Tested Drop-In (Teammates A, B, D)

The Kimina Lean Server (project-numina/kimina-lean-server, April 2025, arXiv 2504.21230) directly solves the Lean verification throughput problem:

| Feature | Detail |
|---------|--------|
| Architecture | Pool of persistent Lean REPL processes with LRU import caching |
| Speed | 51ms/proof cached (vs ~100ms uncached), 1.5-2x speedup |
| Scaling | Near-linear: 8 CPUs = 0.83 proofs/s, 60 CPUs = 4.33 proofs/s |
| Client | `pip install kimina-client`, REST API, async batch support |
| Trust | Full Lean verification — no correctness tradeoff |
| Effort | 1-2 day adoption task, not a research problem |

Used in production by Kimina-Prover (state-of-the-art Lean 4 prover). This eliminates the need for custom Lean infrastructure engineering.

### 3. Persistent REPL Worker Pool via lean-interact (Teammate A)

lean-interact v0.9.0+ already supports the building blocks for a custom worker pool:
- `env` field for incremental environment reuse (pay import cost once)
- `AutoLeanServer` with crash recovery and memory monitoring
- Official multiprocessing pattern: one global `LeanREPLConfig`, one `AutoLeanServer` per process
- `PickleEnvironment`/`UnpickleEnvironment` for cross-process state sharing

This is the DIY alternative to Kimina Lean Server — same architecture, more control, more maintenance burden.

### 4. Python Native Proof Checker: Fast But Trust-Risky (Teammates B vs C, D)

**Teammate B strongly recommends** a Python-native `DerivationTree` checker exploiting the fixed 42-axiom + 7-rule system. Structural recursion over formula JSON trees yields ~100K verifications/sec with zero subprocess overhead — 3 orders of magnitude faster than Lean.

**Teammate C warns** that false positives compound across expert iteration rounds: an incorrectly accepted proof corrupts training data, biasing the policy toward invalid proofs in subsequent rounds.

**Teammate D argues** this is a commercial dead-end: frontier AI labs acquiring training data require Lean proof certificates as trust anchor, not Python checker attestations.

**Resolution**: A Python checker is viable as a **fast pre-filter** (reject obviously wrong proofs before invoking Lean) but not as a Lean replacement. The dual-verification architecture (Python fast path + Lean slow path) has precedent in AlphaProof-style systems.

### 5. Alternative: Trust the Python Search as Implicit Verifier (Teammate D)

The `best_first.py` search constructs `DerivationTree` objects structurally, mirroring the Lean inductive type. If the Python implementation is correct, search success = valid proof by construction. A one-time cross-validation experiment (run 1000 Python search successes through Lean, confirm 100% agreement) would establish this trust relationship empirically.

This potentially eliminates Lean from the training hot path entirely — Lean is needed only for:
1. Initial offline formula labeling (batch `lake exe`)
2. Final verification for data export (Task 22, trust provenance)

### 6. Z3 as Fast Online Validity Oracle (Teammate D)

Once Task 19 (Z3 countermodel generator) is implemented, Z3 becomes a ~10ms validity oracle: if Z3 finds a countermodel, the formula is invalid (no proof exists). By completeness of the logic, Z3 unsatisfiability = derivability. This replaces the 50-100ms Lean `labelFormula` call for formula validity checking.

### 7. Metamath Zero: Not Viable Here (All Teammates)

MM0 verifies 23,000 proofs in 195ms — impressive but irrelevant:
- No Python interface, no ML ecosystem
- Multi-month porting effort for BimodalLogic
- Speed advantage is mooted by Python checker and Lean parallelism options
- The field has converged on Lean 4 as the standard ML-for-theorem-proving platform

### 8. Silent Bug in Bridge Configuration (Teammate C)

`config.py` sets `LEAN_STARTUP_IMPORTS` to only `Bimodal.Syntax.Formula` and `Bimodal.Syntax.Atom`, but `label_formula()` calls `labelFormula` from `Bimodal.Automation.DatasetGenerator`, which is not imported at startup. The bridge's error handling masks failures as `label=None` rather than raising errors. **Fix immediately**: add `Bimodal.Automation.DatasetGenerator` to `LEAN_STARTUP_IMPORTS`.

### 9. Known Lean Memory Issues (Teammate C)

Long-running Lean REPL processes have documented memory growth issues (lean4 GitHub #6753, #5321). `AutoLeanServer` handles this via crash recovery, but each restart pays 5-15 seconds of import re-elaboration. The cumulative overhead across thousands of training iterations is non-trivial. The `PickleEnvironment` mechanism in lean-interact could mitigate this.

## Synthesis

### Conflicts Resolved

**Python checker as primary verifier (B) vs. Lean-only trust (C, D):**
Resolved in favor of Lean as the trust anchor with Python as optional fast pre-filter. The commercial and academic requirements for trust provenance outweigh the throughput gains from Python-only verification. However, the "implicit verification via search construction" approach (Teammate D) deserves empirical validation — if confirmed, it eliminates the need for either Python checker or online Lean calls.

**Custom infrastructure (A) vs. adopt Kimina (D):**
Resolved in favor of Kimina adoption first, custom work only if Kimina proves insufficient for BimodalLogic-specific needs. The engineering effort difference (1-2 days vs. 3-5 days) favors trying the production solution first.

### Gaps Identified

1. **lean-interact is not installed** — the REPL path in `LeanBridge` is dead code. Must be activated before any Lean optimization work.
2. **No formula complexity distribution analysis** — if expert iteration generates increasingly complex formulas, verification latency grows super-linearly (PSPACE-complete tableau).
3. **Lighter verification alternative**: `isValid` (boolean result only) vs. `labelFormula` (full decision procedure + proof extraction + countermodel extraction) could yield 2-5x speedup for verification-only use cases.

### Recommendations

**Immediate (before Task 25 implementation):**
1. Fix the `LEAN_STARTUP_IMPORTS` bug in `config.py` (1 hour)
2. Install lean-interact and activate the REPL path (1 day)
3. Write a benchmarking script: 500 `label_formula` calls with timing analysis (1 day)

**Task 25 Implementation (prioritized):**
1. Adopt Kimina Lean Server for parallelized Lean verification (1-2 days)
2. Add proof state hash cache in Python (1 day)
3. Cross-validate Python search: run 1000 search successes through Lean (1 day)
4. If cross-validation passes, use search success as training-time verification signal

**Strategic Task Ordering:**
- Task 19 (Z3 countermodels) → Task 20 → Task 21 **before** Task 16 (expert iteration)
- Task 25 (Lean optimization) in parallel with Task 19 (independent)
- Task 15 and 16 when GPU is available
- Publishability target: TABLEAUX 2026/2027, dual verification (proofs + countermodels) as novel contribution

## Teammate Contributions

| Teammate | Angle | Status | Confidence |
|----------|-------|--------|------------|
| A | Primary: Lean optimization patterns | completed | high |
| B | Alternatives: Python checker, MM0, dual verification | completed | high |
| C | Critic: gaps, assumptions, overlooked approaches | completed | high |
| D | Horizons: strategic alignment, task ordering | completed | high |

## References

### Primary Sources
- Kimina Lean Server (arXiv 2504.21230, April 2025)
- LeanInteract GitHub (augustepoiroux/LeanInteract)
- LeanTree: Factorized States (arXiv 2507.14722)
- LeanNavigator: State Graphs (arXiv 2503.04772)
- HyperTree Proof Search (arXiv 2205.11491, NeurIPS 2022)
- DeepSeek-Prover-V2 (arXiv 2504.21801, April 2025)
- Goedel-Prover-V2 (arXiv 2508.03613, August 2025)
- AlphaProof (Nature 2025)
- Metamath Zero (arXiv 1910.10703)
- Lean 4 REPL (leanprover-community/repl)

### Codebase References
- `src/bimodal_harness/lean/bridge.py` — LeanBridge, REPL path
- `src/bimodal_harness/config.py` — LEAN_STARTUP_IMPORTS (has bug)
- `src/bimodal_harness/search/best_first.py` — PythonBestFirstSearch, `_is_proved()`
- `src/bimodal_harness/schema/actions.py` — 42 axioms + 7 rules, action space
