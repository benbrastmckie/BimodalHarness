# Teammate D Findings: Strategic Horizons — Policy Network (Task 14)

**Date**: 2026-05-29
**Role**: Horizons (Strategic Direction + GPU Compute Assessment)
**Confidence Level**: High (GPU assessment), Medium (architecture longevity)

---

## GPU Compute Assessment

### Key Insight: GPU Is NOT Required to Start

The task description's "NOTE: Requires GPU for training" is overstated. Based on analysis of the actual model sizes and data volumes, **CPU-only development is viable for all architecture work and initial training**. GPU becomes necessary only for scaled-up expert iteration (Task 16+).

### Model Size Analysis

| Architecture | Parameters | Training Memory | CPU Train Time (10K steps) |
|-------------|-----------|-----------------|--------------------------|
| MLP (12→49, matching ValueNetwork) | 2.8M | ~43 MB | Minutes |
| MLP + AST embedding (140→49) | 3.1M | ~47 MB | Minutes |
| Small Transformer (d=128, L=3) | 0.6M | ~9 MB | Minutes |
| T5-small LoRA (r=8) | 0.3M trainable / 60M total | ~300 MB | 1–2 hours |
| T5-small full fine-tune | 60M | ~1 GB | Hours (needs GPU) |

### Data Volume Analysis

The BimodalLogic codebase contains ~5,276 theorem/lemma declarations across 207 files. The ProofStepExtractor (already implemented in Lean) can extract ordered (context, goal, action) tuples from each derivation tree node, producing an estimated:

- **Estimated raw proof steps**: 15,000–50,000 (assuming avg 3–10 steps per theorem)
- **With augmentation** (temporal duals + context variation from Task 9): 45,000–150,000 steps
- **Current sample data**: 8 test records in `data/samples/test_lean_export.jsonl`

At these scales, **CPU training converges in minutes** for MLP/Transformer architectures. Even T5-small LoRA would complete in 1–2 hours on CPU.

### GPU Tier Requirements (When Needed)

| Phase | GPU Requirement | Recommended | Cost Estimate |
|-------|----------------|-------------|---------------|
| Task 14: Architecture + initial SFT | **None (CPU)** | Any modern CPU | $0 |
| Task 14: Full SFT with real data | Optional (speeds up) | RTX 3060 12GB | $0.20/hr cloud |
| Task 15: Best-first search | **None** (inference only) | CPU | $0 |
| Task 16: Expert iteration | **Recommended** | RTX 3060 12GB min | $0.20/hr |
| Task 17: MCTS with PUCT | **Recommended** | RTX 4090 24GB | $0.50/hr |
| Task 18: Online MCTS training | **Required** | RTX 4090 24GB+ | $0.50/hr |
| Tasks 21–23: Full pipeline + eval | **Required** | A100 40GB (or 2x RTX 4090) | $1.50/hr |

### Cloud GPU Options for Getting Started

| Provider | GPU | VRAM | Hourly Cost | Notes |
|----------|-----|------|------------|-------|
| vast.ai | RTX 3060 | 12GB | $0.10–0.15 | Cheapest, sufficient for Task 14–16 |
| RunPod | RTX 4090 | 24GB | $0.40–0.50 | Sweet spot for Task 16–17 |
| Lambda | A10G | 24GB | $0.60 | Reliable, good for CI |
| Lambda | A100 | 40GB | $1.29 | Only needed for Tasks 21+ |

**Recommendation**: Start on CPU. When ready for Task 16 (expert iteration), a spot RTX 3060 on vast.ai ($0.10/hr) is sufficient. The first real GPU bottleneck is Task 17 (MCTS) where inference latency during tree search benefits from GPU.

---

## Architecture Longevity

### What Serves Tasks 15–23 Best?

The critical architectural decision is the **input representation**, not the model architecture itself. The policy network needs to consume a formula goal state and produce a distribution over 49 actions. Three representations are viable:

#### Option A: PatternKey Features (12-dim, like ValueNetwork)

- **Pros**: Matches existing infrastructure, trains instantly on CPU, simple
- **Cons**: Loses structural information; two formulas with same PatternKey get identical predictions. Cannot distinguish between `(p → (q → r))` and `((p → q) → r)` if they share the same impCount/complexity/topOperator
- **Longevity**: Dead end for expert iteration — search needs to discriminate between structurally different goals with identical summary statistics

#### Option B: Tree-RNN / TreeLSTM over Formula AST

- **Pros**: Captures recursive structure naturally; AST is fixed (6 node types); compositional
- **Cons**: Variable-length computation; harder to batch; sequential bottleneck on deep formulas
- **Longevity**: Good for Tasks 15–17. May struggle with Task 18 (online training) due to latency

#### Option C: Sequence Encoding (flatten AST to tokens + Transformer)

- **Pros**: Leverages standard Transformer infrastructure; easy to extend to context encoding; batches well; trivial to add LoRA later for fine-tuning
- **Cons**: Slightly more complex setup; needs tokenizer; positional encoding matters for trees
- **Longevity**: Best long-term path — directly upgradable to T5-small or larger LMs for expert iteration. MCTS (Task 17) needs fast inference; small Transformer (d=128, L=3, 0.6M params) gives sub-millisecond inference on CPU

### Recommended Architecture Strategy

**Implement both Option A and Option C**, with Option A as the immediate baseline:

1. **Phase 1 (CPU, immediate)**: MLP policy head using PatternKey 12-dim features. Mirrors ValueNetwork architecture exactly. Gets Task 14 "done" for downstream unblocking.

2. **Phase 2 (CPU, after Lean extraction)**: Formula AST tokenizer + small Transformer encoder (d=128, L=3). Produces a formula embedding that replaces the 12-dim PatternKey input. The MLP policy head from Phase 1 sits on top.

3. **Phase 3 (GPU, Task 16)**: Replace small Transformer with T5-small encoder via LoRA. The policy head interface doesn't change.

This progressive architecture means:
- Task 15 (best-first search) can use the Phase 1 MLP immediately
- Task 16 (expert iteration) upgrades to Phase 2/3 without API changes
- The `PolicyNetwork` class exposes `forward(features) → logits[49]` regardless of which encoder is behind it

---

## Training Signal Strategy

### The Lean Extraction Gap

Task 9 delivered the Python-side pipeline (schema, ingestion, augmentation) but Phases 1 and 3 (Lean-side extraction) are deferred — they require the BimodalLogic Lean build environment. This is the critical bottleneck: **no real proof steps exist yet**.

### Proposed Signal Sources (Ordered by Availability)

1. **Synthetic proof steps from formula generator (available now)**
   - The formula generator (Task 8) produces formulas with known structure
   - For simple propositional formulas, the correct axiom is deterministic from the formula structure
   - Generate synthetic (goal, action) pairs: `prop_k` for K-shaped implications, `modal_t` for `□φ→φ`, etc.
   - Estimate: 5,000–10,000 synthetic steps with perfect labels
   - **This unblocks Task 14 development and initial training**

2. **ModelChecker-derived signals (moderate effort)**
   - The ModelChecker (`/home/benjamin/Projects/Logos/ModelChecker/code/src/model_checker/theory_lib/bimodal/`) provides Z3-based model checking with the same bimodal logic
   - It doesn't produce proof traces, but it produces validity/invalidity verdicts
   - Cross-reference: formulas the ModelChecker marks valid → positive examples; invalid → negative (no proof exists)
   - Useful for data augmentation and validation, not directly for policy training

3. **Lean proof extraction (blocked, highest value)**
   - 5,276 theorem/lemma declarations → estimated 15K–50K proof steps
   - ProofStepExtractor.lean is already implemented
   - Needs: `lake exe proof_extractor` executable (Task 9, Phase 3)
   - **This should be prioritized for Task 14 to reach real-data training**

4. **Formula enumerator + decision procedure (available)**
   - BimodalLogic's FormulaEnumerator generates all formulas up to a given complexity
   - The decision procedure classifies each as valid/invalid
   - For valid formulas, the automated proof search finds a derivation
   - **Can run batch_search_with_learning to generate additional labeled steps**

### Recommended Bootstrap Path

```
Phase 1 (immediate): Synthetic steps from formula structure rules
    ↓
Phase 2 (parallel): Run Lean proof extraction (unblock with Lean env)
    ↓
Phase 3 (after extraction): Train on real proof steps + augmentation
    ↓
Phase 4 (Task 16): Expert iteration generates new training data online
```

---

## Long-term Alignment

### Cross-Repo Integration Architecture

The current artifact-only integration (Lean exports JSONL → Python consumes) is sufficient for Tasks 14–15 but **becomes a bottleneck at Task 16 (expert iteration)**. Expert iteration requires:

1. Python proposes tactic (policy network inference)
2. Lean verifies the tactic (sends goal state back)
3. Python updates training data with verified steps

This requires a **live bridge**, not just file export. Task 6 (bridge validation) already evaluated options:
- **lean-interact**: Direct subprocess communication (recommended for initial expert iteration)
- **LeanDojo-v2**: Higher-level but version-sensitive
- **PyPantograph**: Lean 4 native but experimental

The policy network should be designed with the bridge interface in mind: it needs to handle **Lean goal states as input** (which map to ProofStepRecord's `goal_json`), not just static features. This is another reason to invest in a formula AST encoder (Option C) rather than relying solely on PatternKey features.

### Dual Verification Integration (Tasks 20–21)

Tasks 20–21 integrate countermodel signals (from Z3/ModelChecker) as corrective training signal. The policy network architecture should accommodate:
- Positive signal: proof certificates (current design)
- Negative signal: countermodels showing why certain actions fail

This suggests the policy head should eventually support **contrastive learning**: given (goal, correct_action, wrong_action), learn to prefer the correct action. The MLP head with cross-entropy loss already supports this naturally via the 49-way softmax — no architecture change needed, just a training loop enhancement.

---

## Phased Approach Recommendation

### Phase Structure for Task 14

| Phase | Description | Requires GPU | Deliverable |
|-------|-------------|-------------|------------|
| 1 | PolicyNetworkConfig + PolicyNetwork class (MLP, 12→49) | No | `models/policy.py` with full API |
| 2 | PolicyTrainer (mirrors ValueTrainer pattern) | No | `training/policy_trainer.py` |
| 3 | Policy collate_fn + ProofStep dataset | No | `data/policy_dataset.py` |
| 4 | Synthetic training data generator | No | `scripts/generate_synthetic_policy_data.py` |
| 5 | Train on synthetic data + evaluate | No (CPU) | Trained baseline checkpoint |
| 6 | Formula AST tokenizer + Transformer encoder | No | `models/formula_encoder.py` |
| 7 | Train on real proof steps (when available) | Optional | Production checkpoint |

**Phases 1–5 are fully CPU-executable** and can proceed immediately. Phase 6 is a refinement that improves quality but isn't needed to unblock downstream tasks.

### Unblocking Downstream Tasks

- **Task 15** (best-first search) needs: `PolicyNetwork.forward(features) → logits[49]` ✓ (Phase 1)
- **Task 16** (expert iteration) needs: Policy trainer + checkpoint save/load ✓ (Phase 2)
- **Task 13** (value integration, completed) already provides the pattern for neural network integration with proof search

### Key Strategic Decision

The "GPU required" note has been blocking this task unnecessarily. **Recommend removing the GPU blocker and starting Phases 1–5 on CPU immediately.** The MLP baseline with synthetic data will produce a functional (if weak) policy network that Tasks 15–16 can build on. Real quality comes from expert iteration (Task 16), not from the initial supervised training.

---

## Confidence Assessment

| Finding | Confidence | Rationale |
|---------|-----------|-----------|
| CPU viability for Phases 1–5 | **High** | Computed exact memory requirements; MLP with 2.8M params trivially fits in CPU |
| Model size estimates | **High** | Measured directly via PyTorch parameter counting |
| Training data volume from Lean | **Medium** | Based on theorem count (5,276) and average proof tree size assumptions |
| Architecture longevity of Transformer path | **Medium** | Standard in theorem proving literature but domain is niche; may need tuning |
| Cloud GPU pricing | **Medium** | Prices fluctuate; estimates based on May 2026 spot rates |
| Synthetic data bootstrapping quality | **Low-Medium** | Synthetic steps for simple axioms are reliable; complex proof strategies less so |
