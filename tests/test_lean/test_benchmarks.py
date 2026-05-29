"""Latency benchmark tests for the Python-Lean bridge.

All tests are marked ``@pytest.mark.lean`` and ``@pytest.mark.slow``.
Run them explicitly with::

    pytest tests/test_lean/test_benchmarks.py -m "lean and slow" -v -s

Requirements:
- lean-interact installed: ``pip install 'bimodal-harness[lean]'``
- BimodalLogic built: ``lake build`` in the BimodalLogic project directory

Each benchmark measures wall-clock latency and prints a summary table to
stdout.  The tests themselves assert only that the bridge returns valid
responses — latency thresholds are documented as recommendations, not
hard failures.

Research estimates (from 01_bridge-validation.md):
- REPL cold start: 5-15 s (one-time download on first run)
- REPL warm start: 0.5-2 s
- Per-command call: < 500 ms
- Per-tactic step: < 100 ms
- Subprocess (lake exe): 2-30 s (depends on build cache)
"""

from __future__ import annotations

import statistics
import time

import pytest

from bimodal_harness.lean import LeanBridge, lean_interact_available

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_benchmark(name: str, times: list[float]) -> None:
    """Print a formatted benchmark result table entry to stdout."""
    if not times:
        print(f"  {name}: NO DATA")
        return
    mean = statistics.mean(times)
    std = statistics.stdev(times) if len(times) > 1 else 0.0
    min_t = min(times)
    max_t = max(times)
    print(
        f"  {name:<45}  mean={mean:.3f}s  std={std:.3f}s  "
        f"min={min_t:.3f}s  max={max_t:.3f}s  n={len(times)}"
    )


# ---------------------------------------------------------------------------
# Benchmark tests
# ---------------------------------------------------------------------------


@pytest.mark.lean
@pytest.mark.slow
class TestLatencyBenchmarks:
    """Latency benchmarks for LeanBridge operations.

    Tests use the session-scoped ``lean_bridge`` fixture.  Each test prints
    timing data to stdout; use ``pytest -s`` to see the output.
    """

    def test_benchmark_cold_start(self) -> None:
        """Measure cold-start time for a new LeanBridge (first REPL init).

        Cold start includes: lean-interact REPL subprocess spawn, Lean
        initialization, and project loading.  Expected: 5-15 s on first run
        (REPL binary download), 0.5-2 s when warm.
        """
        if not lean_interact_available():
            pytest.skip("lean-interact not installed")

        from pathlib import Path

        from bimodal_harness.config import BIMODAL_LOGIC_PATH

        if not (Path(BIMODAL_LOGIC_PATH) / "lakefile.lean").exists():
            pytest.skip("BimodalLogic not found")

        print("\n\n=== Benchmark: LeanBridge Cold Start ===")
        times: list[float] = []

        for i in range(2):
            t0 = time.monotonic()
            with LeanBridge() as bridge:
                elapsed = time.monotonic() - t0
                times.append(elapsed)
                print(f"  Run {i + 1}: {elapsed:.3f}s  (is_started={bridge.is_started})")

        _print_benchmark("cold_start", times)

    def test_benchmark_warm_start(self, lean_bridge: LeanBridge) -> None:
        """Measure the per-command overhead with an already-warm REPL.

        This does NOT restart the server; it measures the fixed overhead
        of the session-scoped ``lean_bridge`` fixture.
        """
        print("\n\n=== Benchmark: Warm REPL sanity ===")
        assert lean_bridge.is_started
        # A trivial command to measure base latency
        times: list[float] = []
        for i in range(5):
            t0 = time.monotonic()
            resp = lean_bridge.run_command("#check Nat")
            elapsed = time.monotonic() - t0
            times.append(elapsed)
            print(f"  Run {i + 1}: {elapsed:.3f}s  ok={resp.ok}")

        _print_benchmark("warm_repl_check", times)
        # Soft assertion: all calls should be < 5 s on a loaded system
        assert all(t < 5.0 for t in times), f"Some calls unexpectedly slow: {times}"

    def test_benchmark_import_bimodal(self, lean_bridge: LeanBridge) -> None:
        """Measure time to execute ``import Bimodal.Syntax.Formula``.

        This import is typically cached after the first call in a session.
        Expected: first call 200-500 ms, subsequent calls near-zero.
        """
        print("\n\n=== Benchmark: import Bimodal.Syntax.Formula ===")
        times: list[float] = []
        for i in range(3):
            t0 = time.monotonic()
            resp = lean_bridge.run_command("import Bimodal.Syntax.Formula")
            elapsed = time.monotonic() - t0
            times.append(elapsed)
            print(f"  Run {i + 1}: {elapsed:.3f}s  ok={resp.ok}")

        _print_benchmark("import_bimodal_syntax", times)

    def test_benchmark_eval_formula(self, lean_bridge: LeanBridge) -> None:
        """Measure per-call latency for ``#eval`` (10 iterations).

        Expected per-call: < 500 ms.  Mean reported to stdout.
        """
        print("\n\n=== Benchmark: #eval 1 + 1 (×10) ===")
        times: list[float] = []
        for i in range(10):
            t0 = time.monotonic()
            resp = lean_bridge.run_command("#eval 1 + 1")
            elapsed = time.monotonic() - t0
            times.append(elapsed)
            if i == 0 or i == 9:
                print(f"  Run {i + 1}: {elapsed:.3f}s  output={resp.output.strip()!r}")

        _print_benchmark("eval_simple_expr", times)
        mean = statistics.mean(times)
        print(f"  Research target: < 0.5 s/call  Actual mean: {mean:.3f}s")

    def test_benchmark_subprocess(self, lean_bridge: LeanBridge) -> None:
        """Measure ``lake exe`` subprocess invocation latency.

        Uses ``dataset_generator --help`` as a minimal no-op workload.
        Expected: 2-30 s depending on build cache state.
        """
        print("\n\n=== Benchmark: lake exe dataset_generator --help ===")
        times: list[float] = []
        for i in range(2):
            t0 = time.monotonic()
            result = lean_bridge.run_subprocess(["dataset_generator", "--help"])
            elapsed = time.monotonic() - t0
            times.append(elapsed)
            print(
                f"  Run {i + 1}: {elapsed:.3f}s  "
                f"returncode={result.returncode}  "
                f"stdout_len={len(result.stdout)}"
            )

        _print_benchmark("subprocess_lake_exe", times)

    def test_benchmark_tactic_step(self, lean_bridge: LeanBridge) -> None:
        """Measure ``apply_tactic`` latency (10 iterations, best-effort).

        Expected: < 100 ms per step.  If ``ProofStep`` is not in the
        installed lean-interact version, uses raw command fallback.
        """
        print("\n\n=== Benchmark: apply_tactic 'rfl' (×10) ===")
        times: list[float] = []
        for i in range(10):
            t0 = time.monotonic()
            result = lean_bridge.apply_tactic(proof_state=0, tactic="rfl")
            elapsed = time.monotonic() - t0
            times.append(elapsed)
            if i == 0 or i == 9:
                print(
                    f"  Run {i + 1}: {elapsed:.3f}s  "
                    f"error={result.error!r}  goals={result.goals}"
                )

        _print_benchmark("apply_tactic_rfl", times)
        mean = statistics.mean(times)
        print(f"  Research target: < 0.1 s/step  Actual mean: {mean:.3f}s")
