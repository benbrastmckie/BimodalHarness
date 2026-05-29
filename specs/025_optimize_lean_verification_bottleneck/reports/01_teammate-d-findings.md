# Research Report: Task 25 — Teammate D (Horizons/Strategic)

**Task**: 25 — Optimize Lean verification bottleneck for expert iteration
**Artifact**: 01 (teammate-d-findings)
**Role**: Horizons (Strategic direction, long-term alignment, creative alternatives)
**Date**: 2026-05-29

---

## Key Findings

### 1. The Competitive Landscape Has Changed Dramatically

The ML-for-theorem-proving field moved faster than typical ML subfields in 2024–2026. Key data points:

- **AlphaProof** (Google DeepMind, Nature 2025): Lean-based RL agent, IMO silver-medal level. Ran for up to 3 days per problem. Verification was a subordinate cost — wall-time was dominated by proof search and model inference.
- **DeepSeek-Prover-V2** (April 2025): Expert iteration loop with Lean verification as binary RL reward signal. Non-CoT proofs via SFT + curriculum, then GRPO with Lean oracle. Used massive scale (671B params, 37B active). Key insight: they decompose proofs into *subgoals* rather than verifying whole proofs — this changes the bottleneck structure.
- **Goedel-Prover-V2** (August 2025): Scaffolded data synthesis + verifier-guided self-correction. Achieves 88.1% on MiniF2F with 32B model, outperforming DeepSeek-671B. Key technique: mines *failing subgoals* from incorrect Lean proofs as new training data. This is a form of "negative verification" that extracts value from timeouts and failures.
- **Kimina Lean Server** (April 2025): Purpose-built high-performance Lean verification server. LRU caching cuts average verification time from 99ms to 51ms (1.94x speedup). Near-linear scaling from 8 to 60 CPUs. This is the *existing engineered solution* to the Lean verification throughput problem — it exists, is open-source, and is production-tested.
- **Seed-Prover** (2025): Proved 78.1% of formalized IMO problems; 5/6 problems at IMO 2025.

**Key takeaway**: The field has converged on Lean as the trust anchor, not a Python alternative. Every top system uses Lean as the final verifier. The question is not "should we use Lean?" but "how do we make Lean verification fast enough to not be the bottleneck?"

### 2. Kimina Lean Server Directly Solves the Technical Problem

The Kimina Lean Server (github.com/project-numina/kimina-lean-server) is an open-source, production-tested solution for the exact bottleneck described in Task 25:

- REST API accepting batch proof scripts
- LRU caching of Lean imports (the primary cold-start cost)
- Server-side parallelism across N cores (one persistent REPL per core)
- 1.5–2x faster than LeanInteract alone; near-linear scaling to 60 CPUs
- Python SDK for submitting proof batches and receiving Lean feedback
- Used in production by Kimina-Prover (state-of-the-art model)

Measured overhead at 51ms per proof (cached). At 100 proofs per expert-iteration episode, that is ~5 seconds of verification per episode — entirely tolerable alongside GPU training time.

**Critical implication for Task 25**: The implementation path is largely "adopt Kimina Lean Server + run it locally" rather than novel engineering. The innovation space for this project is *not* general Lean verification infrastructure.

### 3. The Python Proof Checker Option Is a Strategic Dead-End for Commercialization

A custom Python proof checker for bimodal temporal logic would be:
- Faster for this specific logic (ms per proof vs. 50–100ms in Lean)
- Not trusted by frontier AI labs as a verification oracle
- Not publishable as a novel contribution (semantics checkers for modal logics are not new)
- A maintenance burden that diverges from the Lean formalization as BimodalLogic evolves

Frontier AI labs (OpenAI, Anthropic, Google DeepMind, xAI) acquiring training data care about **trust provenance**. A Python checker claiming to verify bimodal temporal logic proofs provides no stronger guarantee than the checker's own correctness — and that checker is not formally verified. Lean-checked proofs, by contrast, have machine-checkable certificates against a trusted kernel. The commercial value proposition of Task 22 (training data export pipeline) depends on this trust chain being unbroken.

**Exception**: A Python proof checker *does* make sense as a fast pre-filter (reject obvious non-proofs before invoking Lean) but not as a replacement for Lean verification.

### 4. The Real Bottleneck Architecture for This Project

The current architecture has two distinct Lean interaction patterns:

1. **`lake exe` subprocess**: Batch data extraction (DatasetGenerator, proof_extractor). Cold-start cost is ~seconds. Appropriate for offline preprocessing, not expert iteration inner loops.
2. **lean-interact REPL**: Interactive per-step verification during proof search. lean-interact is *not installed* in the current environment (confirmed in Task 9 research). Per-step REPL calls are needed for online expert iteration.

For expert iteration (Task 16), the verification bottleneck appears in the inner loop:
```
for episode in training_loop:
    proof = policy.search(formula)         # CPU/GPU, seconds
    valid = lean.verify(proof)             # Lean, currently undefined latency
    if valid: dataset.add(proof)
    policy.train(dataset)                  # GPU, minutes
```

If verification takes 30 seconds per proof (cold `lake exe` call), and training takes 5 minutes, the bottleneck is verification *only* if `n_episodes / verification_time > training_time`, which requires >10 proofs per verification call to saturate training. At 51ms per proof with Kimina, this flips: training becomes the bottleneck (desired situation).

---

## Strategic Recommendations

### Recommendation 1: Do Task 19 (Z3 Countermodels) Before Task 25

**Priority**: Task 19 before Task 25.

Task 19 is GPU-free, provides dual verification signal, and unblocks the full training pipeline (Tasks 20, 21). It can be done now without any GPU or Lean verification infrastructure. The countermodel signal is *complementary* to proof verification, not competing. Doing Task 19 first means when Task 16 (expert iteration) runs, it already has access to both positive (proof) and negative (countermodel) training signal.

**Task 19 → Task 20 → Task 21** is the highest-leverage GPU-free path. It defines the training pipeline architecture before expert iteration begins, avoiding a costly refactor later.

### Recommendation 2: Adopt Kimina Lean Server Instead of Building Custom Infrastructure

For Task 25, the implementation should be:
1. Deploy Kimina Lean Server locally (Docker or native)
2. Refactor `LeanBridge.run_subprocess()` to use Kimina REST API for verification calls
3. Add LRU caching in the Python client (on top of Kimina's server-side caching)
4. Parallelize expert-iteration proof checking across available CPU cores via Kimina

This is a 1–2 day implementation task, not a research task. The bulk of the "research" for Task 25 is the feasibility analysis that this report provides.

### Recommendation 3: Install lean-interact and Establish the REPL Path

The current `LeanBridge` has dead code: `lean-interact is not installed`. Before expert iteration can run, this path must be activated. The REPL path is essential for:
- Online tactic-step verification during proof search
- Test-time rollout verification (does each search step close the goal?)

This is a prerequisite for Task 16, not Task 25 specifically — but it should be flagged as a blocker to resolve before either task begins.

### Recommendation 4: For Publishability, Focus on the Dual Verification Contribution

The most publishable angle is *not* "we made Lean faster" (Kimina Lean Server exists). The publishable novelty is:

**"Dual verification training signal for bimodal temporal logic: proof certificates as positive RL reward + countermodel tensors as structured negative signal."**

This is novel because:
1. Bimodal temporal logic has a specific frame structure (3 frame classes, task relation, strict temporal operators) that makes countermodel extraction non-trivial
2. No published system uses structured countermodels (not just "no proof found" = negative) as RL training signal
3. The interaction between MCTS proof search and countermodel-guided curriculum is unexplored territory

TABLEAUX is the right venue: it covers modal and temporal logics, tableau/proof-search methods, and is open to system papers. The dual-signal training contribution would be a strong system paper at TABLEAUX 2026 or 2027.

### Recommendation 5: Defer True Expert Iteration Until GPU Is Available

The expert iteration loop (Task 16) requires GPU for training. Rather than trying to run expert iteration with slow CPU training, the recommended sequence is:

1. **Now (GPU-free)**: Tasks 19, 20, 21 (dual verification pipeline), Task 25 (Kimina setup + REPL activation)
2. **When GPU available**: Task 15 (best-first search with neural guidance), Task 16 (expert iteration)
3. **After GPU iteration**: Tasks 17, 18 (MCTS), Task 22 (data export), Task 23 (evaluation + paper)

The existing 79.4% accuracy policy network (Task 14) trained on synthetic data can drive initial proof search experiments without expert iteration. This is sufficient for Tasks 15 and 25 infrastructure work.

---

## Creative Alternatives

### Alternative A: Use Proof Search Trees as Training Data (Skip Online Verification)

**Idea**: Run the policy network in best-first search mode, collect all search trees (including failed paths), and train on the *successful path structure* within each tree — using path success/failure as implicit verification rather than explicit Lean checking.

**Assessment**: This is roughly what HTPS (HyperTree Proof Search, Meta 2022) does. It works when the search procedure itself is the oracle — the proof either closes or it doesn't. For BimodalHarness, the `best_first.py` search already has this structure: successful search paths are verified by construction (the search only succeeds when a `DerivationTree` is constructed). 

**Verdict**: Partially applicable. The Python-side best-first search in `search/best_first.py` does not invoke Lean to verify each step — it constructs derivations structurally. If the search succeeds, the proof is valid by construction (the Python search mirrors the Lean derivation system). This means:
- Search success = valid proof, no Lean verification needed for that proof
- Search failure = unknown (could be invalid formula or search budget exceeded)
- Lean verification is needed only to label formulas as valid/invalid *before* search

**Practical gain**: For the expert iteration inner loop, we may be able to skip per-proof Lean calls entirely if we trust the Python search's structural correctness. Lean verification is then needed only for formula labeling (is this formula provable?) which happens offline.

### Alternative B: Minimal Viable Expert Iteration via Offline Formula Pool

**Idea**: Pre-generate a large pool of formulas (via formula generator), label them offline with Lean (one `lake exe` call per formula batch), then run expert iteration against this static labeled pool. No online Lean calls during training.

**Assessment**: This eliminates the expert iteration verification bottleneck entirely. The formula generator already exists. The labeler already exists (`lake exe dataset_generator`). The expert iteration loop becomes:
```
# Offline phase (slow, but done once)
pool = generate_formulas(n=100_000)
labels = batch_label_with_lean(pool)  # one lake exe invocation

# Training loop (no Lean)
for epoch:
    for formula in pool.valid:
        proof = policy.search(formula)
        if proof.success:
            dataset.add(proof)
    policy.train(dataset)
```

This is exactly what AlphaProof's precomputed corpus approach looks like. The limitation is that the formula distribution is fixed — expert iteration won't discover *new* formulas, just improve the policy on the existing pool. For a research/publication context, this is acceptable as a first system.

**Verdict**: High-value alternative. Implement this as Task 16's first phase (static labeled pool), then extend to online formula generation with Lean labeling in a second phase. Removes Task 25 as a hard dependency for Task 16.

### Alternative C: Trust the Python DerivationTree System as the Verifier

**Idea**: The Python `search/best_first.py` already constructs `DerivationTree`-shaped proof objects. If the Python implementation correctly mirrors the Lean `DerivationTree` inductive type, then a successful Python search produces a valid proof by construction.

**Assessment**: This is valid *if* the Python search is a faithful implementation of the Lean rules. Given that the Python heuristic search was specifically built to mirror `Core.lean`, this claim holds for the proof search logic. However:
- Frame class semantics must be correctly implemented in Python
- Axiom applicability conditions must match Lean exactly
- The 49-action space masking must be correct

This is essentially a "Python proof checker" — but one that is *structurally trusted* because it mirrors the Lean derivation system, not a separate semantics-based checker. A one-time cross-validation (run Python search on 1000 formulas, verify all successes in Lean) establishes this trust relationship empirically.

**Verdict**: Worth doing as a one-time validation experiment. If 100% of Python search successes pass Lean verification (expected given the system design), this justifies using Python search success as the verification oracle for training purposes. Lean is then needed only for:
1. Initial formula pool labeling (offline)
2. Final verification for data export (Task 22, for trust provenance)

### Alternative D: Integrate Z3 as the Fast Online Verifier

**Idea**: Use Z3 (Task 19) as the fast online validity checker. If a formula is provable in bimodal temporal logic, Z3 finds no countermodel. This takes ~10ms per formula on CPU. If Z3 gives "satisfiable" (countermodel exists), the formula is invalid — no proof to look for.

**Assessment**: Z3 can determine formula *validity* (= no countermodel in any frame class instance) but not *derivability* (= has a formal derivation). For the logic in question (bimodal temporal logic with 3 frame classes), these coincide by completeness — every valid formula is derivable. However, Z3's unsatisfiable result corresponds to "valid in all models" which equals "provable in Base frame class." The mapping between frame classes and Z3 constraint systems must be implemented correctly (Task 19).

**Verdict**: This is the correct framing for Task 19. Once Z3 is working as a countermodel generator, it becomes a 10ms validity oracle that can replace the 50–100ms Lean call for formula labeling. Combined with Alternative B's offline pool approach, this eliminates essentially all Lean calls from the training hot path.

---

## 2-Year Vision: What Would a World-Class System Look Like?

By 2027–2028, a world-class ML-for-theorem-proving system in this domain would have:

1. **Dual oracle training**: Z3 (10ms) for formula validity + Lean (50ms cached) for proof certificate generation. Both run in parallel. Z3 catches invalidity early; Lean certifies proofs.

2. **Structured negative signal**: Countermodels as first-class training data (not just "no proof found"). This is the distinctive contribution of the BimodalHarness approach.

3. **Domain-specific formula curriculum**: Unlike Mathlib-scale systems (which prove graduate-level theorems), BimodalHarness proves bimodal temporal logic theorems in a constrained 49-action space. This enables *exhaustive curriculum design* — enumerate all provable formulas up to complexity N and train on them. This is not possible for Lean 4 + Mathlib (open-ended theorem space).

4. **Verifiably correct training data at scale**: Task 22's data export pipeline, with Lean proof certificates embedded, would be commercially differentiated from datasets that merely claim to be verified.

**Investments today that pay off most**:
- Z3 countermodel generator (Task 19): High leverage, GPU-free, enables dual signal
- Kimina Lean Server adoption (Task 25): 2-day implementation, eliminates latency concerns
- Offline formula pool approach (Task 16 Phase 1): Unblocks training immediately
- TABLEAUX paper draft around Tasks 19–21: Establishes academic credibility before commercialization

**Investments to defer**:
- Custom Python proof checker: Not needed, not trusted
- Large-scale Lean REPL engineering: Kimina solves this already
- MCTS (Task 17): Requires GPU and expert iteration first; don't optimize prematurely

---

## Confidence Level

| Finding | Confidence |
|---------|------------|
| Kimina Lean Server exists and directly addresses the bottleneck | High — published paper, open-source code, production-tested |
| Frontier labs require Lean trust anchor for commercial data | High — industry consensus, no counterexamples |
| Z3 can replace Lean for formula validity labeling | Medium — depends on Task 19 implementation correctness |
| Python search success = valid proof by construction | Medium — requires one-time empirical cross-validation |
| Task 19 before Task 25 is optimal ordering | High — GPU-free, high leverage, no dependencies |
| TABLEAUX is the right venue for dual-signal contribution | High — topic area, system paper fit, existing bimodal logic work |
| Offline formula pool is viable for initial expert iteration | High — standard approach (AlphaProof precomputed corpus) |

**Overall strategic confidence**: High. The bottleneck is real but the solutions are well-understood. The primary risk is not technical but scope: Task 25 could expand to a large custom infrastructure project when a 2-day Kimina adoption achieves the same goal.

---

## References

- [Kimina Lean Server (arxiv 2504.21230)](https://arxiv.org/abs/2504.21230)
- [DeepSeek-Prover-V2 (arxiv 2504.21801)](https://arxiv.org/pdf/2504.21801)
- [Goedel-Prover-V2 (arxiv 2508.03613)](https://arxiv.org/pdf/2508.03613)
- [AlphaProof — Olympiad-level formal mathematical reasoning (Nature 2025)](https://www.nature.com/articles/s41586-025-09833-y)
- [HyperTree Proof Search for Neural Theorem Proving (arxiv 2205.11491)](https://arxiv.org/abs/2205.11491)
- [TABLEAUX 2025 Conference Proceedings](https://link.springer.com/book/10.1007/978-3-032-06085-3)
- [Kimina Lean Server GitHub](https://github.com/project-numina/kimina-lean-server)
