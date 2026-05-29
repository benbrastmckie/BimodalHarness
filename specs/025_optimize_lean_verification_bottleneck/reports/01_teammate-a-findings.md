# Teammate A Findings: Implementation Approaches and Patterns for Lean Verification Optimization

**Task**: 25 - Optimize Lean Verification Bottleneck for Expert Iteration
**Focus**: Best practices from existing projects; persistent server, batch, parallel, and caching approaches
**Date**: 2026-05-29

---

## Key Findings

### 1. The Dominant Pattern: Persistent REPL with Header-Based LRU Cache

The most important finding is that the field has converged on a single dominant architecture: a **pool of persistent Lean REPL processes** where each process is indexed by its `import` header in an **LRU cache**. The cold start cost of initializing a Lean REPL (especially one importing Mathlib or a large library) is substantial - the key insight is that this cost only needs to be paid once per worker, not per proof.

**How it works** (from the Kimina Lean Server paper, April 2025):
- The server pre-starts N Lean REPL processes (N = CPU count - 1 by default)
- Each worker is indexed by its `import` header in an LRU cache
- When a verification request arrives, the server finds a warmed worker with the same imports
- Only the proof *body* is verified; the imports environment is already loaded
- After verification, `"gc": true` discards the environment state, returning the worker to the pool
- Result: ~29% speedup from caching alone (3.65s vs 5.14s per proof on a MacBook Pro M2)

This maps directly to the BimodalHarness situation: every proof verification needs the same BimodalLogic imports. With a persistent worker pool, this cost is paid once at startup, not for every tactic check.

### 2. lean-interact Already Supports the Core Pattern

The existing `LeanBridge` in BimodalHarness uses `lean-interact`, and lean-interact v0.9.0+ already supports the pieces needed:

- **Incremental + Parallel elaboration** (`Elab.async`): Automatically reuses partial computations from previous commands
- **AutoLeanServer**: Experimental crash-recovering server that monitors memory usage - the recommended choice for multiprocessing
- **Environment references**: Every REPL response includes an `env` integer. Subsequent commands can pass `env=N` to run inside an already-loaded environment, avoiding re-import costs
- **Session cache**: `add_to_session_cache=True` on `run()` prevents selected environments from being cleared
- **Multiprocessing recommendation** (from lean-interact docs): "Use multiprocessing with one global `LeanREPLConfig` instance, and one `AutoLeanServer` instance per process. Instantiate `LeanREPLConfig` before starting the processes to avoid conflicts."

The critical implication: the existing `LeanBridge.run_command()` already supports `env=` via the underlying REPL protocol. A persistent-worker pool can be built on top of the current bridge infrastructure.

### 3. The Lean 4 REPL Protocol: `env` Field for Incremental Verification

The Lean 4 REPL (leanprover-community/repl) uses a JSON protocol where every command response includes an `env` field (an integer). Subsequent commands can reference this env to run incrementally in the previously established environment. This is the foundation of all efficient verification:

```json
// Send import command once
{"cmd": "import BimodalLogic"}
// Response: {"env": 1, "messages": [...]}

// All subsequent proofs reference env=1 - no re-import
{"cmd": "example : p → p := by intro h; exact h", "env": 1}
// Response: {"env": 2, "messages": [...]}
```

The REPL also supports `PickleEnvironment`/`UnpickleEnvironment` for serializing environments to disk, enabling cross-process state sharing without re-computation.

### 4. Parallelism: One Process Per Core

The consensus across all surveyed projects (LeanNavigator, Kimina, LeanTree) is:

- A Lean REPL process is **single-threaded** and uses at most one CPU core
- Parallelism is achieved by running **N independent REPL processes** (one per core)
- N = CPU_count - 1 is the practical default (leaving one core for the Python orchestrator)
- Memory is the binding constraint: each Lean process loading BimodalLogic will use on the order of gigabytes of memory

**LeanNavigator** used 24 parallel Ray workers to process Mathlib (28 days for 4.7M theorems). **Kimina Lean Server** measured linear scaling: 8 CPUs = 0.83 proofs/s, 32 CPUs = 2.82 proofs/s, 60 CPUs = 4.33 proofs/s.

### 5. Kimina Lean Server: Ready-Made Solution

The **Kimina Lean Server** (project-numina/kimina-lean-server, released April 2025) is a purpose-built high-performance Lean verification server for RL/expert iteration training loops. It provides:

- A REST server (`POST /verify`) accepting lists of proof scripts
- Python client: `pip install kimina-client`, then `KiminaClient().check("...")`
- Async client (`AsyncKiminaClient`) for high-throughput benchmarking
- Internal LRU worker pool with header-based caching (described above)
- Memory limits per REPL instance (`LEAN_SERVER_MAX_REPL_MEM=8G`)
- Configurable via env vars: `LEAN_SERVER_MAX_REPLS`, `LEAN_SERVER_MAX_REPL_USES`, `LEAN_SERVER_MAX_WAIT`
- Batch verification API with custom IDs per proof

**1.5-2x speedup** vs naive subprocess-per-proof approach is documented. For RL loops, the paper explicitly lists "proof search algorithms using a proof completion model" as the target use case.

### 6. LeanTree: AND-OR Tree with Factorized States

A July 2025 paper (LeanTree) provides a complementary approach specifically for white-box proof search (the BimodalHarness architecture):

- Decomposes multi-goal proof states into **independent sub-goals** that can be solved in parallel
- Uses a **dynamic pool of environments** for parallel execution across branches
- State reuse via AND-OR tree structure: if the same intermediate state is reached via two proof paths, it is explored only once
- Performance result: 18.36% success rate on MiniF2F vs 5.32% for black-box approach (same model)

This is directly applicable to the MCTS/best-first search in BimodalHarness (Tasks 15, 17): sub-goals in the bimodal logic proof system can often be decomposed independently.

### 7. HTPS and Expert Iteration Architecture

The HyperTree Proof Search (HTPS) paper (NeurIPS 2022) describes the reference architecture for online expert iteration with a formal verifier:

- **Distributed asynchronous architecture**: A trainer receives data from a set of asynchronous provers
- Provers run proof searches continuously, sending successful proofs to the trainer
- Provers periodically pull the latest model weights from the trainer
- This decouples CPU-bound Lean verification from GPU-bound model training
- The verifier (Metamath in the original HTPS, Lean in later work) runs on separate CPU workers
- Online training showed: 65.4% (offline) -> 82.6% (with online training) on Metamath

### 8. REAL-Prover and Goedel-Prover: Expert Iteration in Practice

**Goedel-Prover** (2025) uses expert iteration with 8 rounds:
- Generates 16 proof candidates per theorem in each round
- Batch-verifies via Lean compiler
- Adds verified proofs to training data for SFT in next round
- Uses RLPAF (RL from Proof Assistant Feedback) with GRPO, sampling 32 candidates per prompt; Lean verification gives reward=1 for valid proofs, else 0

**REAL-Prover** uses `Jixia-Interactive` for efficient stable Lean 4 interaction during both training and inference.

The key pattern across all expert iteration papers: **decouple proof generation (GPU) from proof verification (CPU)** with an asynchronous queue.

### 9. Metamath Zero (MM0): The Speed Extreme

MM0 verified 23,000 Metamath proofs in **195ms** on an Intel i7. This is 4-5 orders of magnitude faster than Lean/Coq/Isabelle for comparable libraries. However:

- MM0 is primarily a *verification kernel* for low-level proofs, not an interactive theorem prover
- There is essentially no ML ecosystem around MM0
- Migrating BimodalLogic from Lean 4 to MM0 would require a complete rewrite of the formalization and the bridge
- The speed difference only matters if Lean verification is the *only* bottleneck and cannot be parallelized - but parallelization closes most of the gap

**Verdict**: MM0 is not a practical alternative for this project. The BimodalLogic Lean formalization is already written, and the lean-interact/Kimina ecosystem provides sufficient optimization.

### 10. Alternative: Cached Python Oracle

A key optimization orthogonal to Lean is **proof state hash caching**:
- Maintain a Python dict mapping `hash(proof_state) -> verification_result`
- Before calling Lean, check if this exact (state, tactic sequence) has been verified
- The Kimina paper documented this reducing average verification time from 0.099s to 0.051s (1.94x speedup)

For expert iteration: if the policy network repeatedly proposes similar tactics on similar states across training rounds, cache hit rates can be high. This is entirely implementable in Python on top of any verification backend.

---

## Recommended Approach

Given the BimodalHarness architecture (small MLP networks, bimodal temporal logic, existing lean-interact bridge), the recommended implementation strategy in priority order:

### Tier 1 (Implement First): Persistent REPL Worker Pool (3-5 days)

Build a `LeanWorkerPool` class on top of the existing `LeanBridge`:

```python
class LeanWorkerPool:
    """Pool of persistent LeanBridge instances for parallel verification."""
    
    def __init__(self, n_workers: int = os.cpu_count() - 1):
        self._pool = multiprocessing.Pool(
            processes=n_workers,
            initializer=_worker_init,  # starts LeanBridge per process
        )
    
    def verify_batch(self, proof_scripts: list[str]) -> list[bool]:
        return self._pool.map(_verify_one, proof_scripts)
```

Key: `_worker_init` starts one `LeanBridge` with BimodalLogic imports at process startup, not per-proof. The `env` field from the startup import is stored globally in each worker process and passed to every subsequent verification call.

Expected gain: eliminates the per-proof startup cost; only the proof body elaboration time remains (estimated 50-200ms per proof body for simple bimodal logic proofs).

### Tier 2 (Implement Second): Proof State Cache (1-2 days)

Add a hash-based `ProofCache` in Python:

```python
class ProofCache:
    def __init__(self, maxsize: int = 10_000):
        self._cache: dict[str, bool] = {}
    
    def key(self, proof_state: str, tactic: str) -> str:
        return hashlib.sha256(f"{proof_state}|{tactic}".encode()).hexdigest()
    
    def get(self, key: str) -> bool | None:
        return self._cache.get(key)
    
    def put(self, key: str, result: bool) -> None:
        self._cache[key] = result
```

Cache lookup before every Lean call; persist to disk between expert iteration rounds.

### Tier 3 (Consider): Kimina Lean Server (drop-in if Tier 1 proves insufficient)

If the in-process worker pool hits memory or stability issues, the Kimina Lean Server (`pip install kimina-client`) provides an out-of-process server with the same architecture but production-tested. Setup requires a running server process but the client API is trivial.

### Not Recommended: Metamath Zero Migration

The cost-benefit is clearly negative. The BimodalLogic formalization in Lean 4 is already written; migrating to MM0 would require months of rework for diminishing returns that can be mostly achieved through parallelism.

---

## Evidence / Examples

### Kimina Performance Numbers (Table 1 from paper)
| Workers | Throughput |
|---------|------------|
| 8 CPUs  | 0.83 proofs/s |
| 32 CPUs | 2.82 proofs/s |
| 60 CPUs | 4.33 proofs/s |

### Caching Impact (Table 2 from Kimina paper)
| Mode       | Time per proof |
|------------|---------------|
| Cached     | 3.65 seconds  |
| Non-cached | 5.14 seconds  |
| Speedup    | 1.41x         |

(Note: these numbers are for Mathlib-importing proofs; BimodalLogic proofs will be faster since the library is much smaller than Mathlib.)

### LeanNavigator Scale
- 24 Ray workers (one LeanDojo instance per worker)
- Each tactic application: ~0.12 seconds
- Total Mathlib processing: 28 days for 4.7M theorems = ~194 proofs/hour per worker

### LeanTree White-Box vs Black-Box (MiniF2F, Llama-7B)
| Approach     | Success Rate |
|--------------|-------------|
| White-box    | 18.36%      |
| Black-box    | 5.32%       |
| Whole-proof  | 9.59%       |

### Lean REPL Environment Reuse Protocol
```json
// One-time import (pays startup cost)
{"cmd": "import BimodalLogic.Prover"}
// Response: {"env": 1, "messages": []}

// Every subsequent proof reuses env=1 (no re-import)
{"cmd": "theorem t1 : □p → p := by ...", "env": 1}
{"cmd": "theorem t2 : ◇p → ◇◇p := by ...", "env": 1}
```

### lean-interact Multiprocessing Pattern (from docs)
```python
# Create config once before spawning processes
repl_config = LeanREPLConfig(project=project)

def worker_fn(proof: str) -> bool:
    # Each process has its own server (initialized at start via initializer=)
    global _server, _base_env
    resp = _server.run(Command(cmd=proof, env=_base_env))
    return not any(m.severity == "error" for m in resp.messages)

with Pool(processes=8, initializer=init_worker, initargs=(repl_config,)) as pool:
    results = pool.map(worker_fn, proof_candidates)
```

---

## Confidence Level

**High confidence** on:
- The persistent REPL pool architecture (documented in Kimina, lean-interact, LeanDojo, LeanNavigator - consistent across the field)
- The `env` field mechanism for incremental verification (this is a core feature of the Lean 4 REPL protocol)
- lean-interact multiprocessing recommendation (from official docs)
- Caching giving ~1.5-2x speedup (multiple sources)
- Kimina Lean Server as a production-ready option (April 2025, actively maintained)

**Medium confidence** on:
- Specific performance numbers for BimodalLogic proofs (all benchmarks are for Mathlib-scale libraries; BimodalLogic is much smaller so cold start cost is lower and per-proof cost may dominate more)
- LeanTree factorized state approach for the bimodal logic proof structure (requires evaluating whether bimodal logic goals decompose cleanly into independent sub-goals)

**Low confidence** on:
- Exact memory requirements per Lean worker for BimodalLogic (needs empirical measurement)
- Whether the existing `lean-interact` REPL `env` reuse actually works correctly with the current LeanBridge implementation (needs testing with the actual BimodalLogic project)

---

## Sources

- [Kimina Lean Server paper (arxiv)](https://arxiv.org/html/2504.21230v1)
- [Kimina Lean Server GitHub](https://github.com/project-numina/kimina-lean-server)
- [LeanInteract GitHub](https://github.com/augustepoiroux/LeanInteract)
- [LeanTree: Factorized States (arxiv)](https://arxiv.org/html/2507.14722v1)
- [LeanNavigator: State Graphs (arxiv)](https://arxiv.org/html/2503.04772v1)
- [LeanDojo documentation](https://leandojo.readthedocs.io/)
- [LeanDojo project](https://leandojo.org/)
- [Lean 4 REPL (leanprover-community)](https://github.com/leanprover-community/repl)
- [Lean 4 REPL DeepWiki](https://deepwiki.com/leanprover-community/repl)
- [LeanProgress (arxiv)](https://arxiv.org/html/2502.17925)
- [HyperTree Proof Search (arxiv)](https://arxiv.org/abs/2205.11491)
- [Goedel-Prover (arxiv)](https://arxiv.org/pdf/2502.07640)
- [REAL-Prover (arxiv)](https://arxiv.org/html/2505.20613v3)
- [APE-Bench I / Eleanstic (arxiv)](https://arxiv.org/html/2504.19110v1)
- [Metamath Zero (arxiv)](https://ar5iv.labs.arxiv.org/html/1910.10703)
- [lean-interact PyPI](https://pypi.org/project/lean-interact/)
- [LeanAgent (leandojo.org)](https://leandojo.org/leanagent.html)
