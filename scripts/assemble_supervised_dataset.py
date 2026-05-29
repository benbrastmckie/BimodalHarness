"""CLI script: assemble the final augmented supervised proof-step dataset.

Loads raw proof steps from a JSONL file produced by ``lake exe proof_extractor``
(or the ``extract_and_ingest.py`` script), applies temporal dual and context
variation augmentation strategies, computes final dataset statistics, verifies
data integrity, and writes train/val/test JSONL splits.

Usage
-----
    # Assemble from an existing raw proof-steps JSONL:
    python scripts/assemble_supervised_dataset.py --input data/proof-steps.jsonl

    # Specify output directory:
    python scripts/assemble_supervised_dataset.py \\
        --input data/proof-steps.jsonl \\
        --output-dir data/supervised/

    # Control augmentation:
    python scripts/assemble_supervised_dataset.py \\
        --input data/proof-steps.jsonl \\
        --max-context-additions 5 \\
        --no-temporal-dual

    # Skip writing output files (stats only):
    python scripts/assemble_supervised_dataset.py \\
        --input data/proof-steps.jsonl \\
        --dry-run

Output Files
------------
When ``--output-dir`` is set (default: ``data/supervised/``), the following
JSONL files are written:

- ``combined.jsonl``  - All records (originals + augmented)
- ``train.jsonl``     - 80% training split
- ``val.jsonl``       - 10% validation split
- ``test.jsonl``      - 10% test split

Each output line is a JSON object with all ``ProofStepRecord`` fields plus an
``augmentation_source`` field tracking provenance.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from bimodal_harness.data.augmentation import (  # noqa: E402
    augmented_statistics,
    context_variation_augmentation,
    split_dataset,
    temporal_dual_augmentation,
)
from bimodal_harness.data.ingestion import load_proof_steps  # noqa: E402
from bimodal_harness.schema.records import ProofStepRecord  # noqa: E402

log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble augmented supervised proof-step dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        metavar="JSONL_PATH",
        help="Path to raw proof-steps JSONL produced by lake exe proof_extractor.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/supervised"),
        metavar="DIR",
        help="Directory to write combined and split JSONL files (default: data/supervised/).",
    )
    parser.add_argument(
        "--max-context-additions",
        type=int,
        default=3,
        metavar="N",
        help=(
            "Maximum number of context formulas added per step in context variation "
            "augmentation (default: 3)."
        ),
    )
    parser.add_argument(
        "--no-temporal-dual",
        action="store_true",
        help="Disable temporal dual augmentation.",
    )
    parser.add_argument(
        "--no-context-variation",
        action="store_true",
        help="Disable context variation augmentation.",
    )
    parser.add_argument(
        "--no-split",
        action="store_true",
        help="Skip train/val/test split; write only combined.jsonl.",
    )
    parser.add_argument(
        "--train-frac",
        type=float,
        default=0.8,
        metavar="F",
        help="Training split fraction (default: 0.8).",
    )
    parser.add_argument(
        "--val-frac",
        type=float,
        default=0.1,
        metavar="F",
        help="Validation split fraction (default: 0.1).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        metavar="N",
        help="Random seed for dataset splitting (default: 42).",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip action_index consistency validation when loading raw steps.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute statistics but do not write any output files.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args()


def write_augmented_jsonl(
    path: Path,
    records: list[tuple[ProofStepRecord, str]],
) -> None:
    """Write augmented records to a JSONL file.

    Each line is a JSON object with all ProofStepRecord fields plus
    ``augmentation_source``.

    Parameters
    ----------
    path:
        Destination file path (created or overwritten).
    records:
        List of (ProofStepRecord, augmentation_source) tuples.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record, source in records:
            d = record.to_dict()
            d["augmentation_source"] = source
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    log.info("Wrote %d records to %s", len(records), path)


def print_augmented_statistics(stats: dict) -> None:
    """Print human-readable augmented dataset statistics."""
    print("Augmented Dataset Statistics")
    print("============================")
    print(f"Total steps:            {stats['total_steps']}")
    print(f"Unique step IDs:        {stats['unique_step_ids']}")
    print(f"Duplicate step IDs:     {stats['duplicate_step_ids']}")
    print(f"Action index coverage:  {stats['action_index_coverage']} / 49")
    print()
    print("Augmentation source breakdown:")
    for src, count in sorted(stats["augmentation_source_counts"].items()):
        print(f"  {src:<30} {count}")
    print()
    print("Rule distribution:")
    for rule, count in stats["rule_distribution"].items():
        print(f"  {rule:<30} {count}")
    print()
    print("Proof height distribution:")
    for height, count in sorted(stats["proof_height_distribution"].items()):
        print(f"  height={height:<5} {count}")


def verify_no_duplicates(records: list[tuple[ProofStepRecord, str]]) -> bool:
    """Check for duplicate step_ids and warn if found.

    Returns True if no duplicates found, False otherwise.
    """
    step_ids = [r.step_id for r, _ in records]
    seen: set[str] = set()
    duplicates: list[str] = []
    for sid in step_ids:
        if sid in seen:
            duplicates.append(sid)
        seen.add(sid)
    if duplicates:
        print(
            f"[assemble] WARNING: {len(duplicates)} duplicate step_ids found.",
            file=sys.stderr,
        )
        for sid in duplicates[:5]:
            print(f"  - {sid!r}", file=sys.stderr)
        if len(duplicates) > 5:
            print(f"  ... and {len(duplicates) - 5} more", file=sys.stderr)
        return False
    return True


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Step 1: Load raw proof steps.
    if not args.input.exists():
        print(
            f"[assemble] ERROR: Input file not found: {args.input}",
            file=sys.stderr,
        )
        return 1

    print(f"[assemble] Loading raw proof steps from {args.input} ...")
    validate = not args.no_validate
    raw_records = load_proof_steps(args.input, validate_action_index=validate)
    print(f"[assemble] Loaded {len(raw_records)} raw proof step records.")

    # Step 2: Apply augmentation strategies.
    augmented: list[tuple[ProofStepRecord, str]] = [(r, "original") for r in raw_records]

    if not args.no_temporal_dual:
        temporal_duals = temporal_dual_augmentation(raw_records)
        print(
            f"[assemble] Temporal dual augmentation: +{len(temporal_duals)} records."
        )
        augmented.extend(temporal_duals)
    else:
        print("[assemble] Temporal dual augmentation: disabled.")

    if not args.no_context_variation:
        ctx_variations = context_variation_augmentation(
            raw_records, max_context_additions=args.max_context_additions
        )
        print(
            f"[assemble] Context variation augmentation: +{len(ctx_variations)} records."
        )
        augmented.extend(ctx_variations)
    else:
        print("[assemble] Context variation augmentation: disabled.")

    print(f"[assemble] Total combined records: {len(augmented)}")

    # Step 3: Verify data integrity.
    print("[assemble] Verifying data integrity ...")
    no_dups = verify_no_duplicates(augmented)
    if not no_dups:
        print("[assemble] WARNING: Duplicate step_ids detected (see above).", file=sys.stderr)

    # Check action_index coverage.
    action_indices = set(r.action_index for r, _ in augmented)
    print(f"[assemble] Action index coverage: {len(action_indices)} / 49")

    # Step 4: Compute and print statistics.
    stats = augmented_statistics(augmented)
    print()
    print_augmented_statistics(stats)

    if args.dry_run:
        print()
        print("[assemble] Dry run: no output files written.")
        return 0

    # Step 5: Write combined JSONL.
    combined_path = args.output_dir / "combined.jsonl"
    print(f"\n[assemble] Writing combined dataset to {combined_path} ...")
    write_augmented_jsonl(combined_path, augmented)
    print(f"[assemble] Wrote {len(augmented)} records to {combined_path}")

    # Step 6: Write train/val/test splits.
    if not args.no_split:
        print("[assemble] Splitting dataset ...")
        train, val, test = split_dataset(
            augmented,
            train_frac=args.train_frac,
            val_frac=args.val_frac,
            seed=args.seed,
        )
        print(
            f"[assemble] Split sizes: train={len(train)}, val={len(val)}, test={len(test)}"
        )

        train_path = args.output_dir / "train.jsonl"
        val_path = args.output_dir / "val.jsonl"
        test_path = args.output_dir / "test.jsonl"

        write_augmented_jsonl(train_path, train)
        write_augmented_jsonl(val_path, val)
        write_augmented_jsonl(test_path, test)

        print(f"[assemble] Splits written to {args.output_dir}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
