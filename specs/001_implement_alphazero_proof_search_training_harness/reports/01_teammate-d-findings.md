# Teammate D (Horizons) Findings: Strategic Alignment of BimodalHarness

**Task**: 1 — Implement AlphaZero proof search training harness
**Angle**: Strategic alignment, long-term direction, ecosystem fit
**Date**: 2026-05-29

---

## Key Findings

### 1. BimodalHarness Is Strategically Central, Not a Side Project

The technical memo frames the Logos commercialization as a three-stage pipeline:
1. **Stage 1**: Sell verified synthetic training data (proof certificates + countermodels)
2. **Stage 2**: Personal assistant with verified reasoning
3. **Stage 3**: Domain partnerships (medical, legal, financial)

The BimodalHarness directly enables Stage 1. The training pipeline that converts BimodalLogic's proof infrastructure into ML training data IS the revenue-generating product. The task decomposition from BimodalLogic task 201 (formula enumerator → Python-Lean bridge → training data pipeline → value network → policy network → MCTS) maps directly onto the pre-seed roadmap's Stream A (Training Infrastructure) and the training pipeline tasks (2.1-2.5).

This means BimodalHarness should not be scoped as a research experiment. It should be scoped as **production training infrastructure** that will eventually serve as the backbone for Stage 1 revenue.

### 2. The Dual Verification Architecture Creates a Three-Repository Dependency

The technical memo's core thesis is dual verification: proof certificates (positive signal) + countermodels (negative signal). The ecosystem maps cleanly:

| Signal | Source | Repository | Status |
|--------|--------|------------|--------|
| Positive (proofs) | ProofChecker (Lean 4) | BimodalLogic | Mature — 42 axiom constructors, 7 inference rules, decision procedure |
| Negative (countermodels) | ModelChecker (Python/Z3) | Logos/ModelChecker | **Semantically incompatible** — missing Until/Since, wrong frame classes |
| Training pipeline | Training harness | BimodalHarness | **New** — this project |

The Round 2 team research (02_team-research.md) confirmed the ModelChecker cannot be used directly. The three-tier corrective signal strategy (Lean-native → standalone Z3 → full ModelChecker update) must be reflected in BimodalHarness task decomposition.

### 3. The BimodalLogic Task Decomposition Needs Adaptation for BimodalHarness

The 6-phase decomposition from BimodalLogic task 201 was scoped as Lean 4 tasks within the BimodalLogic repo. But BimodalHarness is a **Python** repository. The decomposition needs restructuring:

**Phases that stay in BimodalLogic** (Lean-native):
- Formula enumerator (Phase 1's Lean module)
- Decision procedure integration (already exists)
- Lean-side proof search modifications

**Phases that belong in BimodalHarness** (Python-native):
- Python-Lean bridge validation and abstraction layer
- Training data extraction and dataset management
- Value network training
- Policy network and expert iteration
- MCTS implementation
- Evaluation benchmark infrastructure
- Countermodel generation (Tier 1: Lean-native export; Tier 2: standalone Z3)

**Cross-repo coordination tasks** (new):
- JSON export format specification (BimodalLogic exports → BimodalHarness consumes)
- API contract between Lean formula enumerator and Python pipeline
- Conformance test suite (validating signal sources against ProofChecker)

### 4. The ModelChecker Refactor Is a Strategic Dependency

The bimodal module in `/home/benjamin/Projects/Logos/ModelChecker/code/src/model_checker/theory_lib/bimodal/` currently implements only Box, Future, Past operators — no Until/Since. The Round 2 research identified 7 semantic divergences (4 critical). For the training pipeline to produce **both** positive and negative signals (the technical memo's key differentiator), either:

a. **Tier 1 (minimal)**: Export countermodels from Lean's `CountermodelExtraction.lean` — these are shallow (atoms only) but semantically guaranteed
b. **Tier 2 (richer)**: Build a standalone Z3 countermodel generator aligned to ProofChecker semantics (~500 LOC, in BimodalHarness)
c. **Tier 3 (full vision)**: Update ModelChecker to match ProofChecker — this is a separate project-level effort

BimodalHarness tasks should include Tier 1 and Tier 2 as concrete deliverables. Tier 3 should be a separate task in ModelChecker, not blocked on.

### 5. The Pre-Seed Roadmap Expects a CTO and ML Team

The pre-seed roadmap allocates training infrastructure to a CTO + ML1 + ML2 team (Streams A and D). The current BimodalHarness task decomposition appears to be solo-developer scoped. This creates a tension:

- If BimodalHarness is pre-CTO foundational work, tasks should be scoped for **one person** and focus on infrastructure that a CTO can build on
- If BimodalHarness is the actual training pipeline, it needs to be architected for **team collaboration** from the start

**Recommendation**: Scope BimodalHarness tasks as foundational infrastructure that demonstrates feasibility and establishes architecture patterns. Design interfaces (data formats, API contracts, configuration) to be extensible by a team. This makes BimodalHarness a proof-of-concept for the pre-seed roadmap's Phase 1/Stream A deliverables.

---

## Strategic Alignment Assessment

**Overall alignment: HIGH** — BimodalHarness is directly on the critical path for the Logos commercial strategy.

| Dimension | Alignment | Notes |
|-----------|-----------|-------|
| Stage 1 revenue (training data) | ✅ Direct | This IS the training pipeline |
| Technical memo vision | ✅ Direct | Implements dual verification architecture |
| Pre-seed roadmap | ✅ Direct | Maps to Stream A + Phase 2 |
| Publication target | ✅ Direct | TABLEAUX/CADE 2026 from Phases 4-5 |
| ModelChecker evolution | ⚠️ Partial | Must design for semantic alignment gap |
| Team scaling | ⚠️ Partial | Solo now, but must be team-ready |

---

## Opportunities for Adjacent Progress

1. **Data Format Standardization**: Defining the JSON export format for (formula, label, proof_trace, countermodel) tuples early creates a contract that benefits BimodalLogic, ModelChecker, AND future extensions. This is low-cost, high-leverage work.

2. **Benchmark Suite as Marketing Asset**: The evaluation benchmark from Phase 1 can be published as an open benchmark for neural theorem proving in modal logic — no prior benchmark exists for this domain. This serves both the publication strategy and the commercial narrative.

3. **ModelBuilder Integration Point**: The pre-seed roadmap's Stream D (ModelBuilder) needs formal language formulas as input. If BimodalHarness defines a clean formula representation format, ModelBuilder can consume it directly. Design the data schema with ModelBuilder in mind.

4. **Countermodel Visualization**: If BimodalHarness exports structured countermodels, they can be visualized using ModelChecker's existing display infrastructure. This creates a demo-ready artifact for investor presentations — "here's a proof certificate, here's a countermodel showing exactly how this alternative inference fails."

---

## Creative/Unconventional Suggestions

1. **Flip the dependency: Python-first formula generation**. The task decomposition assumes formulas are generated in Lean and exported. But BimodalHarness is Python. Consider generating formulas in Python (using the operator grammar from the ModelChecker's `operators.py`), then validating them in Lean. This removes the formula enumerator as a Lean dependency and lets BimodalHarness generate training data independently. The Lean decision procedure is only called for labeling/validation.

2. **Use the semantic gap as a feature**. The ModelChecker/ProofChecker divergence isn't just a bug — it's a natural source of hard negative examples. Formulas that are valid in one but not the other (due to frame class differences) are exactly the kind of subtle distinctions the neural network needs to learn. A conformance test suite that catalogs these divergences becomes training data for teaching the network about frame sensitivity.

3. **Skip to value network with synthetic labels**. The 6-phase waterfall (enumerate → bridge → extract → value → policy → MCTS) is conservative. An aggressive alternative: generate formulas in Python, label them with a heuristic (formula complexity metrics that correlate with proof difficulty), train an initial value estimator, and only then invest in the Lean bridge. This produces a working prototype faster and de-risks the bridge validation.

4. **Bidirectional training signal from existing proofs**. BimodalLogic has ~2,519 theorem/lemma declarations. For each theorem, generate "near-miss" mutations (flip one operator, weaken one premise) and check if the mutation is still provable. This produces contrastive training pairs (valid vs near-invalid) without any new infrastructure — just formula manipulation and the decision procedure.

---

## Long-term Risks and Considerations

1. **Lean Version Lock-in**: The BimodalLogic project uses Lean v4.27.0-rc1. LeanDojo, lean-interact, and PyPantograph each have their own Lean version requirements. A version mismatch could block the Python-Lean bridge entirely. BimodalHarness should include a version compatibility matrix as a first-class artifact.

2. **Scale Ceiling for Bimodal Fragment**: The bimodal fragment has 42 axiom constructors + 7 rules — a finite, manageable action space. But the full Logos (pre-seed roadmap target) will have many more operators (constitutive, epistemic, normative, abilities). BimodalHarness architecture must be designed so that extending the action space doesn't require rewriting the training pipeline. Use a registry/configuration pattern for operators.

3. **Publication vs. Product Tension**: The task decomposition targets TABLEAUX/CADE 2026 publication. The pre-seed roadmap targets investor-ready demonstrations. These timelines may conflict. Publication requires reproducible experiments and careful evaluation; product demos require polished UX and impressive results. BimodalHarness tasks should explicitly separate "publication artifacts" from "demo artifacts."

4. **Compute Trajectory**: Phases 0-1 are CPU-only, Phase 2 needs 1x 24GB GPU, Phase 3 needs A100. The pre-seed roadmap allocates compute budget in Phase 2 (M5+). If BimodalHarness tasks are pursued before pre-seed close, they must stay in the CPU-only regime. Architecture decisions (model size, training loop design) should accommodate this constraint.

5. **Single Point of Failure**: Ben appears to be the sole developer spanning BimodalLogic, ModelChecker, and BimodalHarness. Any task decomposition should minimize cross-repo coordination overhead and maximize the ability to work on one repo at a time without blocking progress in others.

---

## Confidence Level

**HIGH** on strategic alignment assessment — the technical memo, pre-seed roadmap, and task decomposition are well-aligned and the BimodalHarness role is clear.

**MEDIUM** on task scoping recommendations — the right decomposition depends on whether this is pre-CTO foundational work or team-ready infrastructure, and on the actual Lean bridge compatibility (untested).

**MEDIUM-HIGH** on creative suggestions — Python-first formula generation and near-miss mutations are low-risk, high-value alternatives that should at least be evaluated during research phases.
