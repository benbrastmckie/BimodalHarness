# Research Findings: Task 25 — Lean Verification Bottleneck (Critic)

**Task**: 25 — Optimize Lean verification bottleneck for expert iteration
**Teammate**: C (Critic)
**Date**: 2026-05-29
**Role**: Identify gaps, invalid assumptions, and overlooked problems

---

## Key Findings

### Finding 1: The Bottleneck Assumption Is Unvalidated

No profiling data exists anywhere in the codebase. The current bridge
implementation records `elapsed` times on every `run_command` and
`label_formula` call (see `bridge.py` lines 95-99, 408), but there is no
code that aggregates, logs, or analyzes these timings. The only latency
numbers available are estimates from the Task 6 research report:

| Operation | Estimated Latency |
|-----------|------------------|
| `#eval labelFormula` per formula | 10–500 ms |
| `ProofStep` tactic | 5–100 ms |
| Cold REPL startup | 30–120 s (one-time) |

These are **estimates, not measurements**. The 10-500 ms range spans two
orders of magnitude. Before any optimization investment, actual benchmarks
against real BimodalLogic formulas are mandatory.

### Finding 2: The Search Loop Already Minimizes Lean Calls

The Python search implementation in `search/best_first.py` is architecturally
well-designed to reduce verification calls. The `_is_proved()` method
(lines 957-993) checks axioms and assumptions **locally in Python** without
touching Lean, and only calls the bridge for non-trivial leaves. This means:

- The vast majority of search node evaluations never touch Lean
- Lean is called only at proof leaves, not at every expansion step
- The neural heuristic (value network bonus) runs entirely in Python

The concern that "Lean verification will dominate the training loop" may
already be partially addressed by the current design. The real verification
cost per formula search could be 0-3 Lean calls, not one per node expansion.
This needs to be measured before assuming it is a bottleneck.

### Finding 3: Scale Is Completely Unspecified

No task (1-24) specifies how many Lean verifications are expected per
expert iteration epoch. This is the single most important unknown. The
optimization investment differs by orders of magnitude depending on scale:

| Scale | Verifications/Epoch | Lean Cost at 100ms avg | Conclusion |
|-------|---------------------|----------------------|------------|
| Small | 1,000 | ~100 seconds | Probably fine, no action needed |
| Medium | 10,000 | ~17 minutes | Warrants parallel workers |
| Large | 100,000 | ~2.8 hours | Critical bottleneck |
| Industrial | 1,000,000+ | 28+ hours | Complete redesign needed |

InternLM2.5-StepProver required **20,000+ CPU days** for their expert
iteration run, suggesting industrial scale is plausible but this project
begins at small to medium scale. For 1,000 verifications per epoch, even
500ms per call yields only 8 minutes total — not a bottleneck.

### Finding 4: A Production-Grade Alternative Already Exists

The Kimina Lean Server (April 2025, project-numina/kimina-lean-server) is
an open-source, high-performance Lean server specifically designed for
reinforcement learning pipelines. It directly addresses the bottleneck
concern using:

- A pool of pre-started Lean REPL workers (one per CPU core)
- LRU caching keyed on import headers — reuses warmed workers
- 1.5-2x speedup over lean-interact in benchmarks on 60-core Xeon
- Verified on the Goedel-LM/Lean-workbook-proofs dataset

This is a drop-in alternative to `AutoLeanServer` that has already been
benchmarked at production scale. The cost of adoption is much lower than
building a custom solution or porting to another verifier. This was not
mentioned in Tasks 6, 13, or elsewhere in the codebase research.

### Finding 5: Known Memory Issues in Long-Running Lean Processes

GitHub issues #6753 and #5321 on the leanprover/lean4 repo document
excessive memory consumption in long-running Lean server processes:

- The Lean server accumulates memory as it reprocesses definitions
- Issue #6753 specifically involves continuous memory growth in a running server
- `AutoLeanServer` in lean-interact monitors memory and has recovery, but
  the recovery mechanism restarts the process, causing import re-elaboration
  overhead that is non-trivial (5-15 seconds per restart for Mathlib imports)

For a training loop running thousands of iterations, the REPL may crash
and recover many times, each time paying the warm-startup cost. The
cumulative overhead could be significant and is not accounted for in
any existing latency estimates.

### Finding 6: The "Pre-Compiled .olean" Approach Is Already in Use

The existing bridge design relies on a pre-built BimodalLogic project
(`.lake/build/` must exist before `LocalProject` is created). The `.olean`
files for Bimodal modules are already compiled. What the bridge does NOT do:

- It does not `PickleEnvironment` / `UnpickleEnvironment` between sessions
- Each new `LeanBridge.start()` session re-imports startup modules
  (`Bimodal.Syntax.Formula`, `Bimodal.Syntax.Atom`) paying import overhead

The lean-interact REPL supports pickling proof states to `.olean` files and
resuming from them — this is not currently used. For the expert iteration
loop, a single warmed environment (with DatasetGenerator imported) could be
pickled once and unpickled for each new training process, saving the
5-15 second Mathlib import on each worker startup.

### Finding 7: The Real Bottleneck May Be Proof Search, Not Verification

The Python best-first search (`PythonBestFirstSearch`) is entirely sequential.
For a max_expansions budget of 10,000 and a per-expansion cost of ~1ms (Python
only, no Lean), each formula search takes up to 10 seconds in pure Python.
If proof search itself takes 10 seconds per formula and Lean verification takes
0.1 seconds, then Lean is 1% of the wall-clock cost, not the bottleneck.

The MCTS implementation (`search/mcts.py`) adds stochastic branching and
further increases per-formula search time. Network inference is estimated at
1-5ms per node (CPU), and batched GPU inference at <0.5ms/item at batch=32
(Task 13 report). For 10,000 expansions with CPU inference, neural scoring
alone could dominate at 10-50 seconds per formula — far more than any
reasonable Lean verification cost.

---

## Gaps and Blind Spots

### Gap 1: No Benchmarks Have Been Run

There is no benchmark script, no timing analysis, and no profiling data
anywhere in the codebase. The `elapsed` field is recorded per REPL call but
never aggregated. Before Task 25 implementation, the team must run:

1. A warm-start REPL timing benchmark: send 100 `labelFormula` calls with
   varying formula complexity and plot latency distribution
2. A full formula search timing breakdown: proportion of wall time in
   (a) Python search logic, (b) neural inference, (c) Lean verification
3. A memory growth measurement: track RSS of the Lean REPL process over 1000+
   consecutive calls

Without these measurements, any optimization is premature.

### Gap 2: Parallelism Architecture Is Undesigned

The Task 6 bridge report notes: "Connection pool for parallel training workers"
as a required implementation item. This was never implemented. The current
`LeanBridge` manages a single REPL process. If training uses multiple parallel
workers (common in actor-learner architectures), each needs its own REPL.
The Kimina Lean Server handles this correctly; the current design does not.

### Gap 3: The Decision Procedure Has Its Own Latency Profile

BimodalLogic's `decide` function (DecisionProcedure.lean) uses a tableau method
with fuel/timeout. The `DifficultyMetrics.decisionTimeMs` field is tracked per
formula, suggesting the Lean team knows runtime varies. The complexity is stated
as O(2^n) worst case (PSPACE-complete), though typical cases are much faster
with pruning. For complex formulas, the tableau itself might take hundreds of ms
— independent of the REPL overhead. This complexity profile is not reflected in
the 10-500ms estimate, which appears to be for simple formulas only.

### Gap 4: False Positive Risk from Custom Python Checker Is Understated

If the team builds a custom Python proof checker (e.g., porting the tableau to
Python for speed), it creates a dual-verifier trust problem:

- Python checker says VALID, Lean says INVALID: training data is corrupted
- Python checker says INVALID, Lean says VALID: misses valid training examples

For expert iteration, corrupted training data compounds across iterations.
A formula incorrectly labeled as "proved" in one iteration produces a policy
that generates proofs for invalid formulas, which then get labeled as valid
in the next iteration — a feedback loop that degrades training quality.
The correctness guarantee of Lean is precisely its value here; a faster
but incorrect verifier undermines the entire expert iteration premise.

### Gap 5: The `#eval` Interface Has Inherent Overhead

The current `label_formula` method (bridge.py lines 375-412) sends:
```
#eval labelFormula "<formula>"
```
This invokes the `DatasetGenerator.labelFormula` function, which runs the
**full decision procedure** including tableau construction, proof extraction,
and countermodel extraction. For training loop verification where we only need
a binary valid/invalid answer, running the full decision procedure and extracting
proof traces is unnecessarily expensive. A lighter `#eval isValid φ` using only
`DecisionProcedure.decide` might be 2-5x faster for the verification-only case.

### Gap 6: Import Scope Is Too Narrow

The `LEAN_STARTUP_IMPORTS` in `config.py` currently imports only:
- `Bimodal.Syntax.Formula`
- `Bimodal.Syntax.Atom`

But `label_formula` calls `labelFormula` from `Bimodal.Automation.DatasetGenerator`.
This means the actual import of `DatasetGenerator` happens implicitly (or fails
silently with a warning per bridge.py lines 277-284). If the startup import of
`DatasetGenerator` is not guaranteed, every `label_formula` call may fail with
`unknown identifier 'labelFormula'` and return `label=None`. The error handling
masks this as a None result rather than a hard failure. This is a latent
correctness bug, not just a performance issue.

### Gap 7: No Analysis of Formula Complexity Distribution

Expert iteration generates candidate formulas through proof search. If the
policy network becomes biased toward complex formulas (high modal/temporal depth)
as training progresses, verification latency will grow super-linearly with
training time due to the O(2^n) tableau complexity. The current system has no
mechanism to monitor or bound verification latency as formula complexity drifts.

---

## Questions That Need Answering

**Before Any Optimization:**

1. What is the actual wall-clock breakdown per expert iteration loop?
   Specifically: what fraction of time is (search, neural inference, Lean verification)?

2. What is the target number of Lean verification calls per training epoch?
   100? 10,000? 100,000? This determines whether optimization is needed at all.

3. Does the current bridge correctly import `DatasetGenerator` before calling
   `labelFormula`? (Check: does `label_formula` ever return `label=None`
   in integration tests?)

**About the Kimina Lean Server:**

4. Does the Kimina Lean Server support the BimodalLogic project as a
   `LocalProject`? (It uses the same underlying lean-interact REPL mechanism,
   so it likely does, but this is unverified.)

5. What is the per-verification latency with Kimina Lean Server vs. plain
   `AutoLeanServer` on BimodalLogic formulas specifically?

**About Long-Running Stability:**

6. How often does `AutoLeanServer` crash and recover in a 1000-iteration
   training run? What is the cumulative restart overhead?

7. What is the RSS memory growth rate of the Lean REPL process over 10,000
   consecutive `labelFormula` calls?

**About the Decision Procedure:**

8. What is the actual latency distribution for `labelFormula` on the existing
   training corpus (the ~15K-50K formulas extracted in Task 9)? The 10-500ms
   estimate is theoretical — real distribution may be much narrower or wider.

9. Could `isValid` (a leaner boolean function) replace `labelFormula` in the
   training loop to reduce per-call overhead?

**About Architecture:**

10. Is the Python search loop itself the actual bottleneck? What is the
    distribution of wall-clock time across (Python A*, neural scoring, Lean verification)?

---

## Overlooked Approaches Worth Investigating

**Approach A: Kimina Lean Server (immediate, low risk)**
Drop lean-interact's `AutoLeanServer` for the Kimina Lean Server's worker pool.
This is production-tested at scale and achieves 1.5-2x speedup with no
correctness tradeoff. Estimated 1-2 days integration effort.

**Approach B: Use `isValid` Instead of `labelFormula` (immediate, low risk)**
The full `labelFormula` runs the complete decision procedure AND extracts proof
traces AND computes difficulty metrics. For training loop verification, only the
boolean result is needed. Using `isValid φ` (if it exists in the Lean API) or
a stripped-down `#eval (decide φ).isValid` reduces overhead.

**Approach C: Pickle-Based Environment Reuse (medium effort, medium payoff)**
The lean-interact REPL supports `PickleEnvironment`. After the first warm-start,
serialize the environment with DatasetGenerator imported to disk. Each worker
process unpickles this environment instead of re-importing. Eliminates the
5-15s Mathlib import per worker restart.

**Approach D: Batch Verification via `labelBatch` (immediate, medium payoff)**
`DatasetGenerator.lean` defines `labelBatch` for processing multiple formulas
in one call. The current Python bridge calls Lean once per formula. Calling
`#eval labelBatch [φ1, φ2, ..., φN]` from Python and parsing the JSON output
amortizes REPL round-trip overhead. For a batch of 100 formulas this could
reduce network/IPC overhead by 100x.

**Approach E: Parallel Process Pool With Separate REPL Per Worker (medium effort)**
Python's `multiprocessing` + one `AutoLeanServer` per process. Each training
worker gets its own Lean REPL. Total throughput scales linearly with CPU count.
The Kimina Lean Server does exactly this, making custom implementation unnecessary.

---

## Confidence Level

**High confidence** findings:
- No benchmarks exist; bottleneck is unvalidated (directly verifiable from codebase)
- Memory issues in long-running Lean processes are documented (GitHub issues)
- Kimina Lean Server exists and provides 1.5-2x speedup (published paper)
- Search loop already minimizes Lean calls architecturally (verified in source)
- LEAN_STARTUP_IMPORTS gap is a latent bug (verified in config.py vs bridge.py)

**Medium confidence** findings:
- Real bottleneck may be proof search, not Lean verification (depends on formula complexity)
- Batch verification via `labelBatch` would reduce overhead (requires testing)
- `PickleEnvironment` would save restart overhead (lean-interact docs, untested)

**Low confidence** findings:
- Quantitative estimates of memory growth rate (no measurements)
- False positive rate of a hypothetical Python checker (no implementation to evaluate)
- Formula complexity distribution in the training loop (no training data yet)

---

## Summary Recommendation

Do not invest in optimization before measuring. Run the following in priority order:

1. **Benchmark** (1 day): Write a script that calls `label_formula` 500 times
   with formulas from the existing Task 9 corpus and plots the latency
   distribution. Determine actual mean and tail latency.

2. **Fix the silent bug** (1 hour): Add `Bimodal.Automation.DatasetGenerator`
   to `LEAN_STARTUP_IMPORTS` in `config.py`. Verify `label_formula` never
   returns `None` in normal operation.

3. **Evaluate Kimina Lean Server** (1-2 days): Try the drop-in replacement
   before building anything custom. It addresses the exact problem at the exact
   scale, with published benchmarks.

4. **Only then** consider custom solutions if measured benchmarks show Lean
   verification is a genuine bottleneck that the Kimina server does not solve.

---

## References

- lean-interact REPL, AutoLeanServer: https://github.com/augustepoiroux/LeanInteract
- Kimina Lean Server (2025): https://arxiv.org/abs/2504.21230
- Lean4 memory issue #6753: https://github.com/leanprover/lean4/issues/6753
- Lean4 memory issue #5321: https://github.com/leanprover/lean4/issues/5321
- leanclient LSP parallel batch: https://pypi.org/project/leanclient/
- InternLM2.5-StepProver (20K CPU days): https://arxiv.org/abs/2410.15700
- Metamath Zero verifier: https://arxiv.org/pdf/1910.10703
- ProofSketcher hybrid checker: https://arxiv.org/pdf/2604.06401
