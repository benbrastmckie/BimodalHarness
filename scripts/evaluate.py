"""Entry point for evaluating a trained bimodal harness proof search model.

Usage examples:

    # Generate a benchmark artifact to a directory
    python scripts/evaluate.py --generate --output-dir /tmp/bench_artifacts

    # Run mock evaluation on an existing benchmark
    python scripts/evaluate.py --benchmark-path /tmp/bench_artifacts/benchmark.jsonl \\
        --systems mock --output-dir /tmp/bench_results

    # Run multiple systems with custom budgets
    python scripts/evaluate.py --benchmark-path benchmark.jsonl \\
        --systems mock,naive_bfs --budgets 1000,5000,10000 \\
        --output-dir results/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the evaluate CLI.

    Returns
    -------
    argparse.ArgumentParser
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="evaluate",
        description="Bimodal harness benchmark evaluation suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--generate",
        action="store_true",
        default=False,
        help="Generate a new benchmark artifact to --output-dir",
    )

    parser.add_argument(
        "--benchmark-path",
        type=Path,
        default=None,
        help="Path to an existing benchmark JSONL file to evaluate",
    )

    parser.add_argument(
        "--systems",
        type=str,
        default="mock",
        help=(
            "Comma-separated list of systems to evaluate. "
            "Available: mock, naive_bfs, success_patterns. "
            "(default: mock)"
        ),
    )

    parser.add_argument(
        "--budgets",
        type=str,
        default="1000,5000,10000",
        help=(
            "Comma-separated node budgets for SR@K computation. "
            "(default: 1000,5000,10000)"
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmark_output"),
        help="Directory to write results and artifacts (default: benchmark_output)",
    )

    parser.add_argument(
        "--target-size",
        type=int,
        default=700,
        help="Target number of formulas to generate (default: 700)",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for generation (default: 42)",
    )

    return parser


def parse_systems(systems_str: str, budget: int) -> list:
    """Parse a comma-separated list of system names into BaselineRunner instances.

    Parameters
    ----------
    systems_str:
        Comma-separated system names (e.g. 'mock,naive_bfs').
    budget:
        Node budget to use for all systems.

    Returns
    -------
    list[BaselineRunner]
        Instantiated baseline runners.
    """
    from bimodal_harness.evaluation.baseline import MockBaseline

    names = [s.strip() for s in systems_str.split(",") if s.strip()]
    runners = []

    for name in names:
        if name == "mock":
            runners.append(MockBaseline(budget=budget))
        elif name in ("naive_bfs", "success_patterns"):
            print(
                f"Warning: {name} requires Lean to be installed and running. "
                "Falling back to mock baseline.",
                file=sys.stderr,
            )
            runners.append(MockBaseline(budget=budget))
        else:
            print(f"Warning: Unknown system {name!r}, skipping.", file=sys.stderr)

    if not runners:
        print("No valid systems specified, using mock baseline.", file=sys.stderr)
        runners.append(MockBaseline(budget=budget))

    return runners


def parse_budgets(budgets_str: str) -> list[int]:
    """Parse a comma-separated list of node budgets.

    Parameters
    ----------
    budgets_str:
        Comma-separated integers (e.g. '1000,5000,10000').

    Returns
    -------
    list[int]
        Sorted list of node budgets.
    """
    try:
        budgets = sorted(int(b.strip()) for b in budgets_str.split(",") if b.strip())
        if not budgets:
            raise ValueError("No valid budgets provided")
        return budgets
    except ValueError as e:
        print(f"Error parsing budgets {budgets_str!r}: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Run the benchmark evaluation suite."""
    parser = build_parser()
    args = parser.parse_args()

    budget_ks = parse_budgets(args.budgets)
    # Use the maximum budget for system initialization
    max_budget = max(budget_ks)
    systems = parse_systems(args.systems, budget=max_budget)

    if args.generate:
        # Generate mode: create benchmark artifact
        from bimodal_harness.evaluation.benchmark import BenchmarkSuite
        from bimodal_harness.evaluation.models import BenchmarkConfig

        config = BenchmarkConfig(
            target_size=args.target_size,
            seed=args.seed,
        )
        print(f"Generating benchmark with {config.target_size} problems to {args.output_dir}...")
        report = BenchmarkSuite.generate_and_save(
            output_dir=args.output_dir,
            config=config,
            systems=systems,
            budget_ks=budget_ks,
        )
        print(f"Done. Report saved to {args.output_dir / 'report.json'}")

        # Print summary table
        for system_name, metrics in report.per_system_metrics.items():
            print(f"\n=== {system_name} ===")
            for k, sr in sorted(metrics.success_rate_at_k.items()):
                print(f"  SR@{k}: {sr:.3f}")

    elif args.benchmark_path is not None:
        # Evaluation mode: run systems on existing benchmark
        from bimodal_harness.evaluation.benchmark import BenchmarkSuite

        if not args.benchmark_path.exists():
            print(f"Error: Benchmark file not found: {args.benchmark_path}", file=sys.stderr)
            sys.exit(1)

        print(f"Loading benchmark from {args.benchmark_path}...")
        suite = BenchmarkSuite(
            benchmark_path=args.benchmark_path,
            systems=systems,
            budget_ks=budget_ks,
        )
        report = suite.run()
        suite.save_report(report, output_dir=args.output_dir)
        print(f"Done. Report saved to {args.output_dir / 'report.json'}")

        # Print summary table
        print("\n" + report.format_comparison_table())

    else:
        print("Error: Must specify either --generate or --benchmark-path", file=sys.stderr)
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
