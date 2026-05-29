# Research Report: Task #14

**Task**: Implement policy network (tactic predictor)
**Date**: 2026-05-29
**Mode**: Team Research (4 teammates)
**Session**: sess_1780088852_149fde

## Summary

The policy network predicts which of 49 proof actions (42 axiom constructors + 7 inference rules) to apply given a proof goal state. Team research converges strongly on a two-phase approach: Phase 1 MLP baseline over PatternKey features (CPU-trainable, immediate), Phase 2 formula AST encoder via small transformer (for real production quality). GPU is NOT required for initial development — the "GPU required" blocker is overstated. All 4 teammates independently confirmed CPU viability. The critical blocker is training data: Lean proof step extraction (Task 9 Phases 1, 3) is deferred, but synthetic data generation can bootstrap development.

## Key Findings

### Primary Approach (from Teammate A)

**Two-tier architecture recommendation:**

1. **Tier 1 — MLP Baseline (immediate, CPU)**: 25-dim input features (12-dim PatternKey reusing existing `encode_pattern_key` + 4-dim context summary + 2-dim depth + 3-dim frame class one-hot + 4-dim subgoal summary) → MLP [1024, 512, 256] → 49-dim logits with frame-class masking. ~699K parameters, CPU-trainable in minutes.

2. **Tier 2 — Formula AST Encoder (when data/GPU available)**: TreeLSTM or small transformer over the formula AST producing a fixed-size embedding, replacing the 25-dim handcrafted features while keeping the same output head.

**Output head (both tiers)**: 49-dim logits → frame-class masking via `FRAME_CLASS_MASKS` (set invalid actions to -inf) → softmax. Cross-entropy loss with label smoothing (ε=0.1).

**Integration is straightforward**: PolicyNetwork mirrors ValueNetwork in structure. Reuse `encode_pattern_key`, `FRAME_CLASS_MASKS`, `ProofStepRecord`, `load_proof_steps`, and adapt `ValueTrainer` pattern.

**New code needed**: PolicyNetworkConfig, PolicyNetwork, encode_proof_step(), ProofStepDataset, policy_collate_fn, PolicyTrainer.

### Alternative Approaches (from Teammate B)

**The 49-action space is orders of magnitude smaller than typical neural theorem proving** — this is a classification problem, not a generation problem. Most prior art (LeanDojo, HTPS, AlphaProof, DeepSeek-Prover) targets infinite action spaces where language models must generate tactic strings. The small fixed action space means simple classifiers can work.

**Prior art alignment**: The consensus pipeline is SFT → curriculum → RL (confirmed by AlphaProof, DeepSeek-Prover-V2, HTPS, Kaliszyk et al.). Start with supervised fine-tuning, graduate to GRPO-style RL for expert iteration.

**Augmentation is ready**: Temporal duals + context variations via existing `augment_all()` can 3-5x the dataset. Additional strategies: frame-class transfer augmentation, contrastive learning with the formula mutator (10 mutation operators exist).

**Architecture progression** (converges with Teammate A):
- Phase 0: PatternKey MLP (~200K params, CPU)
- Phase 1: Enhanced MLP with depth/context features (~500K, CPU)
- Phase 2: Tree-NN or small transformer (~2-5M, optional GPU)
- Phase 3: LoRA fine-tuned T5-small (60M total, 0.5M trainable, GPU required)

### Gaps and Shortcomings (from Critic)

**GAP 1 — No real training data exists (Critical)**: Task 9 Lean extraction phases are deferred. Only 10 synthetic test fixtures exist. The policy network can be architecturally implemented but cannot be meaningfully trained without data. This is a partial blocker.

**GAP 2 — PatternKey is insufficient for full policy prediction**: Two formulas with identical PatternKey can require different proof steps (e.g., `□p→p` needs `modal_t` while `□p→□□p` needs `modal_4`, both have same top_operator=Implication). The policy network ultimately MUST encode the full formula AST. PatternKey MLP is acknowledged as a limited baseline only.

**GAP 3 — No AST-to-tensor encoding pipeline exists**: No mechanism to convert `goal_json` (nested dict) into tensors. This is a prerequisite for any architecture beyond the PatternKey MLP.

**GAP 4 — Action distribution likely highly skewed**: `modus_ponens` is the workhorse rule in Hilbert-style proofs. Naive cross-entropy will overfit to majority class. Need focal loss or class-weighted cross-entropy.

**GAP 5 — Missing evaluation metrics**: Search-oriented metrics (MRR, top-k coverage, probability mass on valid actions) matter more than raw classification accuracy for downstream proof search.

**GAP 6 — Hierarchical action structure**: The 49 actions are really two-level: rule selection (7) then axiom selection (42 if rule=axiom). A hierarchical head may outperform flat softmax.

### Strategic Horizons (from Horizons)

**GPU is NOT required for initial development.** MLP (2.8M params, ~43 MB training memory) trains on CPU in minutes. The "GPU required" blocker should be removed for Task 14.

**Phased GPU escalation**:
| Phase | GPU Requirement | Recommended Hardware | Cost |
|-------|----------------|---------------------|------|
| Task 14 (MLP + code) | None (CPU) | Any modern CPU | $0 |
| Task 14 (full SFT) | Optional | RTX 3060 12GB | $0.10-0.20/hr cloud |
| Task 15 (search) | None (inference) | CPU | $0 |
| Task 16 (expert iteration) | Recommended | RTX 3060 12GB min | $0.20/hr |
| Task 17 (MCTS) | Recommended | RTX 4090 24GB | $0.50/hr |
| Tasks 18-23 (full pipeline) | Required | A100 40GB | $1.29/hr |

**Cloud GPU recommendation**: vast.ai RTX 3060 at $0.10/hr suffices through Task 16. Only upgrade to RTX 4090 ($0.50/hr) for MCTS.

**Training data bootstrap path**: Synthetic steps from formula structure rules (available now, ~5K-10K steps) → Lean proof extraction (when build env available, ~15K-50K steps) → expert iteration (Task 16, generates new data online).

**Architecture longevity**: The policy network should expose `forward(features) → logits[49]` regardless of encoder backend. Phase 1 MLP → Phase 2 small transformer → Phase 3 LoRA LM — all share the same output interface, enabling progressive upgrading without breaking downstream tasks.

## Synthesis

### Conflicts Resolved

1. **PatternKey sufficiency** — Teammates A/B recommend PatternKey MLP as first step; Critic (C) argues it's "provably insufficient" with concrete counterexamples. **Resolution**: All agree PatternKey MLP is a limited baseline, not the final architecture. The counterexample (□p→p vs □p→□□p) is valid and demonstrates that full AST encoding is needed for production quality. Phase 1 uses PatternKey knowingly as a bootstrap; Phase 2 adds AST encoding.

2. **Architecture for Phase 2** — A recommends TreeLSTM; B/C/D converge on linearized AST + small transformer. **Resolution**: Small transformer over tokenized formula AST is the consensus. It batches more efficiently, upgrades naturally to LoRA/LM fine-tuning, and provides sub-millisecond inference. TreeLSTM has marginal structural advantage but harder batching and less ecosystem support.

3. **Hierarchical vs flat policy head** — C argues for 2-level (rule then axiom); others use flat 49-way. **Resolution**: Start with flat 49-way softmax (simpler, proven, compatible with all training strategies). Add hierarchical head as an ablation study after establishing the flat baseline. The frame-class masking already provides the most important action filtering.

4. **Training data strategy** — C identifies no real data as critical blocker; D proposes synthetic data bootstrap. **Resolution**: Generate synthetic proof steps from formula structure rules (~5K-10K labeled pairs for common axiom patterns) to bootstrap Phase 1 development. Prioritize completing Lean extraction (Task 9 Phases 1, 3) for Phase 2. This unblocks Task 14 without waiting for Lean build environment.

### Gaps Identified

1. **AST-to-tensor encoding** — No encoding pipeline exists. Required for Phase 2+. Define tokenizer vocabulary (~20 tokens: 6 AST tags + atom names + special tokens) and implement formula linearization (prefix notation).

2. **Action distribution analysis** — No empirical data on which actions dominate real proofs. Need to analyze the first batch of extracted proof steps to inform loss function design (class weights, focal loss).

3. **Applicability constraints** — Beyond frame-class masks, structural constraints exist (necessitation requires empty context, assumption requires goal in context). Currently unmodeled. Consider adding applicability masks during training.

4. **Evaluation framework** — Need search-oriented metrics beyond classification accuracy: MRR (mean reciprocal rank), top-5 recall, calibration quality. These predict downstream proof search performance better than top-1 accuracy.

### Recommendations

**Recommended implementation plan:**

| Phase | Description | GPU | Deliverable |
|-------|-------------|-----|-------------|
| 1 | PolicyNetworkConfig + PolicyNetwork (MLP, 25→49) | No | `models/policy.py` |
| 2 | ProofStepDataset + policy_collate_fn | No | `data/policy_dataset.py` |
| 3 | PolicyTrainer (mirrors ValueTrainer) | No | `training/policy_trainer.py` |
| 4 | Synthetic training data generator | No | `scripts/generate_synthetic_policy_data.py` |
| 5 | Train MLP on synthetic data + evaluate | No | Baseline checkpoint |
| 6 | Formula AST tokenizer + small transformer encoder | No | `models/formula_encoder.py` |
| 7 | Train on real proof steps (after Lean extraction) | Optional | Production checkpoint |

**Architecture decisions:**
- **Phase 1**: MLP with 25-dim handcrafted features → [1024, 512, 256] → 49-dim logits + frame-class mask. ~699K params. Cross-entropy with label smoothing ε=0.1, AdamW lr=3e-4.
- **Phase 2**: Replace 25-dim features with transformer formula encoder (d=128, L=3, ~0.6M params). Same output head. Total ~1.3M params.
- **Loss**: Weighted cross-entropy or focal loss to handle class imbalance. Label smoothing ε=0.1 (multiple valid proof continuations exist).
- **Metrics**: Top-1 accuracy, top-5 accuracy, MRR, per-rule accuracy, calibration.

**Key strategic decision**: Remove the GPU blocker from Task 14. Phases 1-5 are fully CPU-executable. The first real GPU need is Task 16 (expert iteration), not Task 14.

## Teammate Contributions

| Teammate | Angle | Status | Confidence |
|----------|-------|--------|------------|
| A | Primary architecture & integration | completed | high |
| B | Alternative approaches & prior art | completed | high |
| C | Critic (gaps & blind spots) | completed | high |
| D | Strategic horizons & GPU compute | completed | high |

## References

- HTPS: HyperTree Proof Search for Neural Theorem Proving (Lample et al., 2022)
- DeepSeek-Prover-V2: Advancing Formal Mathematical Reasoning via RL (2025)
- CARTS: Advancing Neural Theorem Proving (ICLR 2025)
- PACT: Proof Artifact Co-Training (Han et al., 2022)
- RL of Theorem Proving (Kaliszyk et al., 2018)
- Graph Representations for Higher-Order Logic (Paliwal et al., 2019)
- A Survey on Deep Learning for Theorem Proving (COLM 2024)
- Learning Rules Explaining ITP Tactic Prediction (2024)
