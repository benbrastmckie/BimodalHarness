"""CLI script: extract proof steps and ingest them into ProofStepRecord objects.

This script orchestrates the end-to-end proof step extraction pipeline:

1. Optionally runs ``lake exe proof_extractor`` via subprocess to generate a
   JSONL file of proof steps from the BimodalLogic theorem corpus.
2. Ingests the JSONL file using ``load_proof_steps``.
3. Reports statistics about the loaded dataset.

Usage
-----
    # Ingest an existing JSONL file (skip Lean extraction):
    python scripts/extract_and_ingest.py --input data/proof-steps.jsonl

    # Run Lean extraction first, then ingest (requires BimodalLogic build):
    python scripts/extract_and_ingest.py --extract --output data/proof-steps.jsonl

    # Full pipeline with stats:
    python scripts/extract_and_ingest.py --extract --output data/proof-steps.jsonl --stats

    # Validate without loading (dry run):
    python scripts/extract_and_ingest.py --input data/proof-steps.jsonl --dry-run

Environment
-----------
BIMODAL_LOGIC_DIR:
    Path to the BimodalLogic repository root (used when --extract is set).
    Defaults to ``../BimodalLogic`` relative to this script's directory.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

# Add project root to path for imports when run directly.
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from bimodal_harness.data.ingestion import (  # noqa: E402
    load_proof_steps,
    print_proof_step_statistics,
)

log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract and ingest supervised proof step training data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input",
        type=Path,
        metavar="JSONL_PATH",
        help="Path to an existing proof-steps JSONL file to ingest.",
    )
    input_group.add_argument(
        "--extract",
        action="store_true",
        help="Run 'lake exe proof_extractor' to generate JSONL before ingesting.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        metavar="JSONL_PATH",
        default=Path("data/proof-steps.jsonl"),
        help=(
            "Output path for JSONL when --extract is set. "
            "Also used as the input path after extraction. "
            "Default: data/proof-steps.jsonl"
        ),
    )
    parser.add_argument(
        "--lean-dir",
        type=Path,
        metavar="DIR",
        default=None,
        help=(
            "Path to BimodalLogic repository root. "
            "Defaults to $BIMODAL_LOGIC_DIR or ../BimodalLogic."
        ),
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print dataset statistics after ingestion.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help=(
            "Skip action_index consistency validation during ingestion. "
            "Useful for debugging malformed JSONL files."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Load and validate records but do not write any output files. "
            "Implies --stats."
        ),
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args()


def find_lean_dir(args: argparse.Namespace) -> Path:
    """Resolve the BimodalLogic directory from CLI args or environment."""
    import os

    if args.lean_dir is not None:
        return args.lean_dir

    env_dir = os.environ.get("BIMODAL_LOGIC_DIR")
    if env_dir:
        return Path(env_dir)

    # Default: sibling directory of the repo root.
    default_dir = _REPO_ROOT.parent / "BimodalLogic"
    return default_dir


def run_lean_extractor(lean_dir: Path, output_path: Path) -> None:
    """Run ``lake exe proof_extractor`` and write output to ``output_path``.

    Parameters
    ----------
    lean_dir:
        Path to the BimodalLogic repository root (must contain ``lakefile.lean``).
    output_path:
        Destination for the JSONL output.

    Raises
    ------
    FileNotFoundError
        If ``lean_dir`` does not exist or does not contain ``lakefile.lean``.
    subprocess.CalledProcessError
        If the ``lake exe proof_extractor`` command fails.
    """
    if not lean_dir.exists():
        raise FileNotFoundError(
            f"BimodalLogic directory not found: {lean_dir}. "
            "Set --lean-dir or $BIMODAL_LOGIC_DIR."
        )
    lakefile = lean_dir / "lakefile.lean"
    if not lakefile.exists():
        raise FileNotFoundError(
            f"lakefile.lean not found in {lean_dir}. "
            "Is this a valid BimodalLogic repository?"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("Running: lake exe proof_extractor (cwd=%s)", lean_dir)
    print(f"[extract_and_ingest] Running lake exe proof_extractor in {lean_dir} ...")

    with output_path.open("w", encoding="utf-8") as outfh:
        result = subprocess.run(
            ["lake", "exe", "proof_extractor"],
            cwd=lean_dir,
            stdout=outfh,
            stderr=subprocess.PIPE,
            text=True,
        )

    if result.returncode != 0:
        print(f"[extract_and_ingest] lake exe failed (code {result.returncode}):")
        print(result.stderr, file=sys.stderr)
        raise subprocess.CalledProcessError(
            result.returncode, "lake exe proof_extractor"
        )

    line_count = sum(1 for _ in output_path.open("r", encoding="utf-8") if _.strip())
    print(f"[extract_and_ingest] Wrote {line_count} lines to {output_path}")


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Step 1: Determine the JSONL input path.
    if args.extract:
        lean_dir = find_lean_dir(args)
        output_path = args.output
        print(f"[extract_and_ingest] Extracting proof steps from {lean_dir} ...")
        run_lean_extractor(lean_dir, output_path)
        jsonl_path = output_path
    else:
        jsonl_path = args.input

    # Step 2: Ingest.
    validate = not args.no_validate
    print(f"[extract_and_ingest] Loading proof steps from {jsonl_path} ...")

    if not jsonl_path.exists():
        print(
            f"[extract_and_ingest] ERROR: File not found: {jsonl_path}",
            file=sys.stderr,
        )
        return 1

    records = load_proof_steps(jsonl_path, validate_action_index=validate)
    print(f"[extract_and_ingest] Loaded {len(records)} proof step records.")

    # Step 3: Report statistics.
    if args.stats or args.dry_run:
        print()
        print_proof_step_statistics(records)

    return 0


if __name__ == "__main__":
    sys.exit(main())
