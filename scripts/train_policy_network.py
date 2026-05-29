"""CLI script for training the BimodalHarness policy network.

Loads or generates proof step data, trains a PolicyNetwork MLP, saves a
checkpoint, and prints evaluation metrics on the test split.

Usage:
    python scripts/train_policy_network.py \\
        --data synthetic \\
        --synthetic-steps 5000 \\
        --output checkpoints/policy_net.pt \\
        --max-epochs 20

    python scripts/train_policy_network.py \\
        --data path/to/proof_steps.jsonl \\
        --output checkpoints/policy_net.pt \\
        --max-epochs 50
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Train a PolicyNetwork (tactic predictor) on BimodalHarness data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data",
        type=str,
        default="synthetic",
        metavar="PATH_OR_SYNTHETIC",
        help='Path to JSONL file of ProofStepRecords, or "synthetic" to generate data.',
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("checkpoints/policy_net.pt"),
        metavar="PATH",
        help="Output path for the best model checkpoint.",
    )
    parser.add_argument(
        "--synthetic-steps",
        type=int,
        default=5000,
        metavar="N",
        help="Number of base steps to generate when --data=synthetic.",
    )
    parser.add_argument(
        "--synthetic-frame-class",
        type=str,
        default="Base",
        choices=["Base", "Dense", "Discrete"],
        help="Frame class for synthetic data generation.",
    )
    parser.add_argument(
        "--hidden-sizes",
        type=str,
        default="1024,512,256",
        metavar="SIZES",
        help="Comma-separated hidden layer sizes.",
    )
    parser.add_argument(
        "--dropout",
        type=float,
        default=0.1,
        metavar="RATE",
        help="Dropout probability for hidden layers.",
    )
    parser.add_argument(
        "--label-smoothing",
        type=float,
        default=0.1,
        metavar="EPS",
        help="Label smoothing epsilon.",
    )
    parser.add_argument(
        "--lr",
        "--learning-rate",
        type=float,
        default=3e-4,
        dest="learning_rate",
        metavar="LR",
        help="Initial learning rate for AdamW optimizer.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        metavar="N",
        help="Training batch size.",
    )
    parser.add_argument(
        "--max-epochs",
        type=int,
        default=50,
        metavar="N",
        help="Maximum number of training epochs.",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=7,
        metavar="N",
        help="Early stopping patience (epochs without val top-1 improvement).",
    )
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=1e-4,
        metavar="WD",
        help="L2 weight decay for AdamW optimizer.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        metavar="SEED",
        help="Random seed for reproducibility.",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.8,
        help="Fraction of data for training.",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.1,
        help="Fraction of data for validation.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the policy network training pipeline."""
    args = parse_args()

    from bimodal_harness.data.policy_dataset import split_proof_steps
    from bimodal_harness.data.synthetic_policy_data import generate_synthetic_proof_steps
    from bimodal_harness.models.policy import PolicyNetwork, PolicyNetworkConfig
    from bimodal_harness.training.policy_trainer import PolicyTrainer, PolicyTrainerConfig

    print("BimodalHarness Policy Network Trainer")
    print("=" * 50)
    print(f"Data:         {args.data}")
    print(f"Output:       {args.output}")
    print(f"Hidden sizes: {args.hidden_sizes}")
    print(f"Dropout:      {args.dropout}")
    print(f"LR:           {args.learning_rate}")
    print(f"Batch size:   {args.batch_size}")
    print(f"Max epochs:   {args.max_epochs}")
    print(f"Patience:     {args.patience}")
    print()

    # Load or generate data
    if args.data == "synthetic":
        print(f"Generating {args.synthetic_steps:,} synthetic proof steps "
              f"(frame_class={args.synthetic_frame_class})...")
        t0 = time.monotonic()
        records = generate_synthetic_proof_steps(
            n_steps=args.synthetic_steps,
            seed=args.seed,
            frame_class=args.synthetic_frame_class,
        )
        load_time = time.monotonic() - t0
        print(f"Generated {len(records):,} records (after augmentation) in {load_time:.2f}s")
        augmented_pairs = [(r, "synthetic") for r in records]
    else:
        data_path = Path(args.data)
        if not data_path.exists():
            print(f"ERROR: data file not found: {data_path}", file=sys.stderr)
            sys.exit(1)

        import json
        print(f"Loading records from {data_path}...")
        t0 = time.monotonic()
        raw_records = []
        with open(data_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    from bimodal_harness.schema.records import ProofStepRecord
                    raw_records.append(ProofStepRecord.from_dict(json.loads(line)))
        load_time = time.monotonic() - t0
        print(f"Loaded {len(raw_records):,} records in {load_time:.2f}s")
        augmented_pairs = [(r, "original") for r in raw_records]

    if not augmented_pairs:
        print("ERROR: no records found.", file=sys.stderr)
        sys.exit(1)

    # Split dataset
    train_records, val_records, test_records = split_proof_steps(
        augmented_pairs,
        train_frac=args.train_ratio,
        val_frac=args.val_ratio,
        seed=args.seed,
        stratify_by_action=True,
    )
    print(f"Split: train={len(train_records):,}  val={len(val_records):,}  test={len(test_records):,}")
    print()

    if not train_records:
        print("ERROR: training split is empty.", file=sys.stderr)
        sys.exit(1)

    # Build model
    hidden_sizes = [int(x.strip()) for x in args.hidden_sizes.split(",")]
    model_config = PolicyNetworkConfig(
        input_dim=25,
        num_actions=49,
        hidden_sizes=hidden_sizes,
        dropout=args.dropout,
        label_smoothing=args.label_smoothing,
    )
    model = PolicyNetwork(model_config)
    print(f"PolicyNetwork: hidden_sizes={hidden_sizes}, params={model.param_count:,}")

    # Build trainer
    trainer_config = PolicyTrainerConfig(
        learning_rate=args.learning_rate,
        batch_size=args.batch_size,
        max_epochs=args.max_epochs,
        weight_decay=args.weight_decay,
        patience=args.patience,
        label_smoothing=args.label_smoothing,
        seed=args.seed,
    )
    trainer = PolicyTrainer(
        model=model,
        config=trainer_config,
        train_records=train_records,
        val_records=val_records,
    )

    # Train
    print(f"Training for up to {args.max_epochs} epochs (patience={args.patience})...")
    print(f"{'Epoch':>6}  {'Train Loss':>12}  {'Val Top-1':>10}  {'Val Top-5':>10}  {'MRR':>8}")
    print("-" * 60)

    t_start = time.monotonic()
    results = trainer.train()
    train_time = time.monotonic() - t_start

    for epoch_idx, (loss, val_m) in enumerate(
        zip(results["train_losses"], results["val_metrics"])
    ):
        marker = " *" if epoch_idx == results["best_epoch"] else ""
        print(
            f"{epoch_idx:>6}  {loss:>12.4f}  {val_m['top1_acc']:>10.4f}  "
            f"{val_m['top5_acc']:>10.4f}  {val_m['mrr']:>8.4f}{marker}"
        )

    print()
    print(f"Training complete in {train_time:.1f}s")
    print(f"Best epoch: {results['best_epoch']} | Best val Top-1: {results['best_val_top1']:.4f}")

    # Save checkpoint
    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    trainer.save_checkpoint(str(output_path))
    print(f"Checkpoint saved to {output_path}")
    print()

    # Evaluate on test set
    if test_records:
        print("Test set evaluation:")
        model.eval()
        test_metrics = trainer.evaluate(test_records)
        print(f"  Top-1 accuracy:  {test_metrics['top1_acc']:.4f}")
        print(f"  Top-5 accuracy:  {test_metrics['top5_acc']:.4f}")
        print(f"  MRR:             {test_metrics['mrr']:.4f}")
        print(f"  Valid prob mass: {test_metrics['valid_prob_mass']:.4f}")
        print()
        print("Per-rule accuracy:")
        for rule, acc in sorted(test_metrics["per_rule_accuracy"].items()):
            print(f"  {rule:<30} {acc:.4f}")
        print()
        if test_metrics["top1_acc"] > 0.15:
            print("SUCCESS: Top-1 accuracy exceeds 15% target.")
        else:
            print(f"INFO: Top-1 accuracy {test_metrics['top1_acc']:.4f} below 15% target "
                  f"(expected on small/short runs).")
    else:
        print("No test records; skipping evaluation.")

    print("Done.")


if __name__ == "__main__":
    main()
