# Teammate B Findings: Alternative Approaches and Prior Art

**Task**: 14 — Implement policy network (tactic predictor)
**Date**: 2026-05-29
**Angle**: Alternative approaches, prior art, small-data strategies, GPU requirements
**Confidence**: High (well-grounded in codebase analysis and literature review)

---

## Key Findings

### 1. The 49-Action Space Is Unusually Small — This Changes Everything

The BimodalHarness action space (42 axiom constructors + 7 inference rules = 49 total) is **orders of magnitude smaller** than typical neural theorem proving settings. For comparison:

- **LeanDojo/ReProver**: Generates entire tactic strings from an unbounded vocabulary — effectively infinite action space
- **HTPS (Hyper-Tree Proof Search)**: Samples from a language model over a large vocabulary
- **AlphaProof**: Uses language model sampling over Lean tactics — thousands of possible actions per state
- **DeepSeek-Prover-V2**: Full sequence generation with 16K+ token context windows

**Implication**: Most prior art is designed for the *infinite-action-space* regime where a language model must *generate* the tactic. BimodalHarness faces a *classification* problem over 49 classes with frame-class masking reducing it to 44-47 effective classes. This is fundamentally a different (and much easier) problem. A simple MLP or shallow transformer classifier suffices; an autoregressive language model is overkill.

### 2. PatternKey-Based MLP as a Strong Baseline (Recommended First Step)

The existing `ValueNetwork` architecture (12-dim PatternKey → MLP → scalar) directly suggests a **PatternKey-based policy MLP** as the natural first baseline:

- **Input**: Same 12-dim PatternKey encoding (4 log1p numerics + 8 one-hot top_operator) already implemented in `models/value.py`
- **Output**: 49-dim logits with frame-class masking (mask already implemented in `schema/actions.py`)
- **Architecture**: MLP with [512, 256, 128] hidden layers → 49-dim output → masked softmax
- **Parameter count**: ~200K params — trivially CPU-trainable

**Why this should come first**:
1. The `PatternKey` captures exactly the features the Lean `SuccessPatterns.lean` uses for heuristic scoring (`modalDepth`, `temporalDepth`, `impCount`, `complexity`, `topOperator`)
2. The existing `FeatureNormalizer` + `encode_pattern_key` can be reused verbatim
3. The `ValueTrainer` pattern (train loop, checkpointing, curriculum sampler) can be adapted with minimal changes
4. It establishes a measurable baseline before investing in more complex encoders
5. With only 49 classes, even a 12-dim input may carry enough signal — the top operator alone narrows the action space significantly (e.g., `Box` goals predominantly need `modal_*` axioms)

**Expected performance**: With the structured nature of bimodal logic proofs (axiom selection is heavily correlated with goal structure), a PatternKey MLP should achieve 40-60% top-1 accuracy and 80%+ top-5 accuracy even with limited training data.

### 3. Prior Art Analysis: What Works for Small, Structured Action Spaces

#### a) HTPS (Hyper-Tree Proof Search) — Most Relevant Architecture Pattern

HTPS introduced the AND/OR tree backup for theorem proving (already planned for Task 17). Key insight: the **policy network doesn't need to be a language model**. For structured action spaces, HTPS uses a classifier head over a fixed set of tactics, which is exactly the BimodalHarness setting. The critical innovation is the PUCT-guided MCTS over the AND/OR tree, not the policy architecture itself.

#### b) PACT (Proof Artifact Co-Training) — Training Strategy

PACT demonstrated that **co-training on proof artifacts** (intermediate proof states, not just final proofs) significantly improves tactic prediction. This aligns with the `ProofStepRecord` design — training on (goal_state → action) pairs from every node of the `DerivationTree`, not just the root. The existing augmentation strategies (temporal duals, context variations) are a form of artifact co-training.

#### c) DeepSeek-Prover-V2 — RL Strategy (GRPO)

DeepSeek-Prover-V2 uses **Group Relative Policy Optimization (GRPO)** instead of PPO: sample a group of candidate proofs for each theorem, then optimize based on relative rewards within the group. This eliminates the need for a separate critic model. For BimodalHarness, this could be adapted post-SFT: generate multiple action sequences, verify with Lean, and optimize based on which sequences produced valid proofs.

#### d) Kaliszyk et al. (2018) — RL for Theorem Proving

The original RL-for-theorem-proving work showed that **pure RL from scratch is ineffective** for tactic prediction. The successful formula is: SFT pretraining → RL fine-tuning. This confirms the task description's plan to "start with SFT on proof trace dataset."

### 4. Alternative Training Strategies Beyond SFT

#### a) Contrastive Learning with Near-Miss Formulas

The `formula/mutator.py` already implements 10 mutation operators producing syntactically valid near-miss formulas. These can generate **contrastive training pairs**:

- **Positive**: (goal, correct_action) from proof traces
- **Hard negative**: (mutated_goal, same_action) — the action that works for the original goal fails for the mutant

This is valuable because contrastive learning has been shown to improve few-shot learning and representation quality, particularly with "near-miss" examples where only small relational aspects differ. However, **hard negatives that are too difficult can degrade performance** — calibrate mutation severity to produce moderate-difficulty negatives.

**Practical approach**: Use the mutator to generate formulas, run the Lean prover on them, and collect (formula, action, success/failure) triples. This creates a richer signal than pure SFT.

#### b) Offline RL from Search Traces

The Lean proof search (`ProofSearch/Core.lean`) already produces search traces including failed branches. These contain valuable negative signal:

- **Successful paths**: (goal, action) → proof found → positive reward
- **Failed paths**: (goal, action) → search exhausted → negative reward
- **Near-miss paths**: (goal, action) → partial progress → intermediate reward

This maps naturally to **Decision Transformer** or **offline RL** (Conservative Q-Learning). The `SearchStats` from `bestFirst_search` provide the trajectory data.

#### c) Curriculum Learning (Already Partially Built)

The `CurriculumSampler` in `data/dataset.py` implements epoch-gated difficulty progression through 4 tiers (easy → medium → hard → very_hard). This should be extended to the policy network training:

- **Phase 1**: Train on propositional-only goals (Layers 1-2 axioms, depth ≤ 2)
- **Phase 2**: Add modal goals (Layer 2-4 axioms)
- **Phase 3**: Add temporal goals (Layer 3 axioms)
- **Phase 4**: Full action space including frame-class-specific axioms

#### d) Self-Play via Expert Iteration (Task 16 Preview)

The planned expert iteration loop (Task 16) is the gold standard for this setting. The policy network bootstrap goes: SFT on existing proofs → guide search → verify new proofs → add to training set → retrain. Each iteration produces harder training data. The policy network architecture should be designed to support this loop from the start.

### 5. ModelChecker as a Training Signal Source

The Python-side model checker at `/home/benjamin/Projects/Logos/ModelChecker/code/src/model_checker/theory_lib/bimodal/` provides:

#### a) Countermodel Generation as Reward Signal

`BimodalSemantics` + Z3 can determine if a formula is valid or invalid, producing countermodels for invalid formulas. This enables:

- **Reward for search**: If the policy's predicted action sequence leads to a formula the model checker can verify, that's a positive signal
- **Negative signal**: If the action sequence leads to a provably invalid subgoal (countermodel exists), that's a strong negative signal — stronger than just "search failed"
- **Data generation**: Systematically generate (formula, valid/invalid) labels for formulas the Lean prover hasn't seen, then use the Lean prover to find proofs for valid ones → new training data

#### b) Semantic Evaluation for Action Filtering

The model checker's truth evaluation (`BimodalProposition.evaluate()`) could provide a **semantic filter** for candidate actions: if applying an axiom to a goal would produce subgoals that are semantically invalid (countermodel exists), prune that action before search. This is complementary to the frame-class mask (which is syntactic).

#### c) Model Iteration for Data Diversity

`BimodalModelIterator` generates multiple distinct models satisfying constraints. This could generate diverse countermodels for contrastive training — showing the network multiple reasons why a formula is invalid, not just one.

**Practical limitation**: The model checker operates on the semantic level (Kripke frames, world histories) while the policy network operates on the syntactic level (formula ASTs, proof goals). Bridging this gap requires encoding countermodel information into the input features, which is the subject of Task 20.

### 6. Small Data Regime Strategies

With potentially only hundreds to low-thousands of proof steps initially:

#### a) Existing Augmentation (Good Start)

- **Temporal duals**: Doubles temporal axiom coverage via BX future/past symmetry (26-entry dual map in `augmentation.py`)
- **Context variations**: Generates weakening variants for empty-context steps (up to 3x multiplier)
- **Combined**: `augment_all()` can 3-5x the effective training set

#### b) Additional Augmentation Strategies

1. **Formula substructure permutation**: For commutative operators (temporal linearity axioms), swap operands to generate equivalent training examples
2. **Proof tree mirroring**: For symmetric axiom pairs (e.g., `left_mono_until_G` / `right_mono_until`), generate training pairs by swapping the role of the arguments
3. **Frame-class transfer**: A proof step valid on Base is also valid on Dense and Discrete — create copies with different `frame_class` labels for steps using Base-only axioms
4. **Synthetic proof generation**: Use the formula enumerator (`formula/generator.py`) to generate simple formulas, prove them exhaustively with bounded search, and extract all proof steps

#### c) Transfer Learning

Pre-train the formula encoder on an **auxiliary task** before SFT:
- **Formula validity classification**: Predict whether a formula is valid/invalid (binary classification, data from TrainingRecord labels)
- **Tree height prediction**: Predict `DerivationTree.height` from the goal formula (regression, data from ProofTrace.height) — this is essentially what the ValueNetwork already does, so weight sharing between value and policy encoders is natural
- **Axiom layer prediction**: Predict which axiom *layer* (1-8) is needed for a goal — a coarser version of the full 49-class problem, more learnable with limited data

### 7. Architecture Progression (Recommended Phased Approach)

| Phase | Architecture | Input | Params | GPU Required? |
|-------|-------------|-------|--------|---------------|
| **0. Baseline** | PatternKey MLP | 12-dim PatternKey | ~200K | No (CPU) |
| **1. Enhanced MLP** | Deep MLP with depth/context features | ~50-dim handcrafted | ~500K | No (CPU) |
| **2. Tree-NN** | TreeLSTM or GNN over formula AST | AST graph | ~2-5M | Optional |
| **3. Transformer** | Small transformer (e.g., 4-layer, 128-dim) | Token sequence | ~5-15M | Yes (modest) |
| **4. LoRA LM** | LoRA-finetuned T5-small or GPT-2-small | Token sequence | ~60M (0.5M trainable) | Yes |

**Recommendation**: Start with Phase 0 (PatternKey MLP). Only progress to Phase 2+ if the MLP plateaus below acceptable accuracy on the benchmark suite (Task 12). The 49-class structure of the problem means simple models may perform surprisingly well.

### 8. GPU Compute Requirements

#### Phase 0-1 (MLP): No GPU needed
- 200K-500K params, trains in minutes on CPU
- Existing `ValueTrainer` handles this already

#### Phase 2 (Tree-NN / GNN): Modest GPU helpful but optional
- 2-5M params, batch processing of variable-size graphs
- **Minimum**: Any GPU with 4GB VRAM (GTX 1050 Ti, etc.)
- **Recommended**: 8GB (RTX 3060, RTX 4060)
- Can train on CPU in hours, GPU brings it to minutes
- Cost: ~$0.30-1.00/hour on cloud (T4 or L4 instance)

#### Phase 3-4 (Transformer / LoRA LM): GPU required
- T5-small with LoRA: ~60M params, 0.5M trainable
  - **Minimum**: 8GB VRAM (RTX 3060)
  - **Recommended**: 16GB VRAM (RTX 4080, A4000, V100)
  - Training time: ~1-4 hours for small dataset
  - Cloud cost: ~$1-5/hour (A10G, V100, or L4 instance)
- GPT-2-small with LoRA: Similar requirements
  - LoRA config: r=16, alpha=32, targeting attention layers
  - Reduces trainable params from 124M to ~0.5-1M

#### Expert Iteration Loop (Task 16): Significant GPU
- Repeated training + inference cycles
- **Recommended**: 24GB VRAM (RTX 3090, RTX 4090, A5000)
- Multiple training runs per iteration, each 1-4 hours
- Cloud cost: ~$2-8/hour (A100 40GB ideal, V100 workable)

**Bottom line for getting started**: No GPU is needed for Phase 0-1. A single consumer GPU (8-16GB VRAM, ~$500-1500) or cloud instance ($1-5/hr) suffices through Phase 4. Only the full expert iteration loop (Task 16+) benefits from high-end GPU resources.

---

## Alternative Approaches Identified

| Approach | Applicability | Effort | Expected Gain | Confidence |
|----------|--------------|--------|---------------|------------|
| PatternKey MLP baseline | Immediate | Low | High (establishes baseline) | High |
| Contrastive learning with mutator | After SFT baseline | Medium | Medium (+5-10% acc) | Medium |
| GRPO-style RL (DeepSeek-Prover-V2) | After SFT + search integration | High | High (10-20% gain) | Medium |
| Offline RL from search traces | After search integration | Medium | Medium-High | Medium |
| ModelChecker as reward signal | After Z3 encoding (Task 19-20) | High | Medium (complementary) | Medium |
| Frame-class transfer augmentation | Immediate | Low | Low-Medium (+2-5% acc) | High |
| Auxiliary task pre-training | Before SFT | Medium | Medium (cold-start help) | Medium |
| Tree-NN / GNN over AST | After MLP baseline | Medium-High | Medium (structure-aware) | Medium |

---

## Evidence / Examples

### Evidence from Codebase

1. **PatternKey → action correlation**: The `SuccessPatterns.lean` module records exactly `PatternKey` → `(successful_strategy, success_rate)` mappings, proving that PatternKey features carry strong signal for action selection
2. **Frame-class masking**: `FRAME_CLASS_MASKS` in `actions.py` already implements the legal action filter needed for masked softmax — only 44-47 of 49 actions valid per frame class
3. **Augmentation pipeline ready**: `augment_all()` in `augmentation.py` can 3-5x training data immediately
4. **Training infrastructure exists**: `ValueTrainer` in `training/value_trainer.py` provides the complete train/eval/checkpoint loop, curriculum sampling, and early stopping — needs only a new collate function for policy targets

### Evidence from Literature

1. **SFT → RL pipeline is standard**: AlphaProof, DeepSeek-Prover-V2, and HTPS all use supervised pretraining followed by RL refinement
2. **Small action spaces favor classifiers over generators**: When the action space is finite and small (49), classification outperforms autoregressive generation
3. **GRPO eliminates critic model**: For the expert iteration loop (Task 16), GRPO's group-relative rewards are simpler than PPO and require no separate value network for the RL phase (the existing `ValueNetwork` serves the *search* value function, not the RL critic)
4. **LoRA makes LM fine-tuning feasible on consumer GPU**: T5-small + LoRA needs only 4-8GB VRAM, ~$13 in cloud compute for a training run

---

## Confidence Level

**Overall: High**

- **Architecture recommendation (PatternKey MLP first)**: High confidence — directly supported by codebase structure and the small action space
- **Prior art analysis**: High confidence — well-established literature, key papers from 2022-2025
- **Training strategy (SFT → curriculum → RL)**: High confidence — consensus approach in the field
- **GPU requirements**: High confidence — based on published benchmarks for T5-small/LoRA
- **ModelChecker integration potential**: Medium confidence — conceptually sound but requires bridging semantic/syntactic gap (Tasks 19-20)
- **Contrastive learning gains**: Medium confidence — theoretically motivated, untested in this specific domain

---

## Sources

- [HTPS: HyperTree Proof Search for Neural Theorem Proving](https://arxiv.org/pdf/2205.11491)
- [DeepSeek-Prover-V2: Advancing Formal Mathematical Reasoning via RL](https://arxiv.org/html/2504.21801v1)
- [CARTS: Advancing Neural Theorem Proving (ICLR 2025)](https://proceedings.iclr.cc/paper_files/paper/2025/file/69dbaf03f7f37a7ccad9ccc92875a44d-Paper-Conference.pdf)
- [RL of Theorem Proving (Kaliszyk et al., 2018)](https://proceedings.neurips.cc/paper/8098-reinforcement-learning-of-theorem-proving.pdf)
- [Graph Representations for Higher-Order Logic](https://arxiv.org/pdf/1905.10006)
- [A Survey on Deep Learning for Theorem Proving (COLM 2024)](https://github.com/zhaoyu-li/DL4TP)
- [Learning Rules Explaining ITP Tactic Prediction](https://arxiv.org/pdf/2411.01188)
- [An Ensemble Approach for ATP Based on GNN](https://arxiv.org/pdf/2305.08676)
