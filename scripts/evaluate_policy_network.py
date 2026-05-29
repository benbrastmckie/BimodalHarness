"""CLI script for evaluating a trained policy network checkpoint.

Loads a checkpoint and evaluates it on a JSONL proof step dataset or
synthetic data, printing top-1/top-5/MRR/per-rule accuracy.

Usage:
    python scripts/evaluate_policy_network.py \\
        --checkpoint checkpoints/policy_net.pt \\
        --data path/to/proof_steps.jsonl

    python scripts/evaluate_policy_network.py \\
        --checkpoint checkpoints/policy_net.pt \\
        --data synthetic \\
        --synthetic-steps 1000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate a PolicyNetwork checkpoint on proof step data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        metavar="PATH",
        help="Path to checkpoint file saved by train_policy_network.py.",
    )
    parser.add_argument(
        "--data",
        type=str,
        default="synthetic",
        metavar="PATH_OR_SYNTHETIC",
        help='Path to JSONL file of ProofStepRecords, or "synthetic".',
    )
    parser.add_argument(
        "--synthetic-steps",
        type=int,
        default=1000,
        metavar="N",
        help="Number of synthetic steps to generate when --data=synthetic.",
    )
    parser.add_argument(
        "--synthetic-frame-class",
        type=str,
        default="Base",
        choices=["Base", "Dense", "Discrete"],
        help="Frame class for synthetic data.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        metavar="N",
        help="Batch size for evaluation.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        metavar="SEED",
        help="Random seed for synthetic generation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from bimodal_harness.data.synthetic_policy_data import generate_synthetic_proof_steps
    from bimodal_harness.models.policy import PolicyNetwork, PolicyNetworkConfig
    from bimodal_harness.training.policy_trainer import PolicyTrainer, PolicyTrainerConfig

    ckpt_path = args.checkpoint
    if not ckpt_path.exists():
        print(f"ERROR: checkpoint not found: {ckpt_path}", file=sys.stderr)
        sys.exit(1)

    print(f"BimodalHarness Policy Network Evaluator")
    print("=" * 50)
    print(f"Checkpoint: {ckpt_path}")
    print(f"Data:       {args.data}")
    print()

    # Load data
    if args.data == "synthetic":
        print(f"Generating {args.synthetic_steps:,} synthetic records...")
        records = generate_synthetic_proof_steps(
            n_steps=args.synthetic_steps,
            seed=args.seed,
            frame_class=args.synthetic_frame_class,
        )
        print(f"Generated {len(records):,} records (after augmentation)")
    else:
        data_path = Path(args.data)
        if not data_path.exists():
            print(f"ERROR: data file not found: {data_path}", file=sys.stderr)
            sys.exit(1)
        from bimodal_harness.schema.records import ProofStepRecord
        records = []
        with open(data_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(ProofStepRecord.from_dict(json.loads(line)))
        print(f"Loaded {len(records):,} records")

    if not records:
        print("ERROR: no records found.", file=sys.stderr)
        sys.exit(1)

    # Load checkpoint and build trainer
    trainer = PolicyTrainer.from_checkpoint(
        str(ckpt_path),
        train_records=records[:1],  # Placeholder (not used for eval)
        val_records=records[:1],
    )
    # Override batch size if specified
    trainer.config.batch_size = args.batch_size

    print(f"Model: hidden_sizes={trainer.model.config.hidden_sizes}, "
          f"params={trainer.model.param_count:,}")
    print()

    # Evaluate
    print("Evaluating...")
    trainer.model.eval()
    metrics = trainer.evaluate(records)

    print(f"Results on {len(records):,} records:")
    print(f"  Top-1 accuracy:  {metrics['top1_acc']:.4f}  ({metrics['top1_acc']*100:.1f}%)")
    print(f"  Top-5 accuracy:  {metrics['top5_acc']:.4f}  ({metrics['top5_acc']*100:.1f}%)")
    print(f"  MRR:             {metrics['mrr']:.4f}")
    print(f"  Valid prob mass: {metrics['valid_prob_mass']:.4f}")
    print()
    print("Per-rule accuracy:")
    for rule, acc in sorted(metrics["per_rule_accuracy"].items()):
        print(f"  {rule:<30} {acc:.4f}  ({acc*100:.1f}%)")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
