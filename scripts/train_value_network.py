"""CLI script for training the BimodalHarness value network.

Loads JSONL training data, trains a ValueNetwork MLP, saves a checkpoint,
and prints evaluation metrics on the test split.

Usage:
    python scripts/train_value_network.py \\
        --data path/to/training_data.jsonl \\
        --output checkpoints/value_net.pt \\
        --max-epochs 50 \\
        --batch-size 64
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure project src is on the path when running as a script
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Train a ValueNetwork (proof-progress predictor) on BimodalHarness data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Data arguments
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        metavar="JSONL",
        help="Path to training data JSONL file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("checkpoints/value_net.pt"),
        metavar="PATH",
        help="Output path for the best model checkpoint.",
    )
    # Architecture arguments
    parser.add_argument(
        "--hidden-sizes",
        type=str,
        default="2048,1024,512,256",
        metavar="SIZES",
        help="Comma-separated hidden layer sizes (e.g. '2048,1024,512,256').",
    )
    parser.add_argument(
        "--dropout",
        type=float,
        default=0.1,
        metavar="RATE",
        help="Dropout probability for hidden layers.",
    )
    # Training hyperparameters
    parser.add_argument(
        "--lr",
        "--learning-rate",
        type=float,
        default=3e-4,
        dest="learning_rate",
        metavar="LR",
        help="Initial learning rate for Adam optimizer.",
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
        help="Early stopping patience (epochs without val MAE improvement).",
    )
    parser.add_argument(
        "--huber-delta",
        type=float,
        default=1.0,
        metavar="DELTA",
        help="Huber loss delta parameter.",
    )
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=1e-4,
        metavar="WD",
        help="L2 weight decay for Adam optimizer.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        metavar="SEED",
        help="Random seed for reproducibility.",
    )
    parser.add_argument(
        "--no-curriculum",
        action="store_true",
        help="Disable CurriculumSampler (use standard shuffle instead).",
    )
    # Data split ratios
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
    """Run the value network training pipeline."""
    args = parse_args()

    # Lazy imports after path setup
    from bimodal_harness.data.dataset import split_dataset
    from bimodal_harness.models.value import ValueNetwork, ValueNetworkConfig
    from bimodal_harness.schema.serialization import read_jsonl
    from bimodal_harness.training.value_trainer import TrainerConfig, ValueTrainer

    print(f"BimodalHarness Value Network Trainer")
    print(f"{'=' * 50}")
    print(f"Data:         {args.data}")
    print(f"Output:       {args.output}")
    print(f"Hidden sizes: {args.hidden_sizes}")
    print(f"Dropout:      {args.dropout}")
    print(f"LR:           {args.learning_rate}")
    print(f"Batch size:   {args.batch_size}")
    print(f"Max epochs:   {args.max_epochs}")
    print(f"Patience:     {args.patience}")
    print(f"Curriculum:   {not args.no_curriculum}")
    print()

    # Load data
    data_path = args.data
    if not data_path.exists():
        print(f"ERROR: data file not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading records from {data_path}...")
    t0 = time.monotonic()
    records = read_jsonl(data_path)
    load_time = time.monotonic() - t0
    print(f"Loaded {len(records):,} records in {load_time:.2f}s")

    if not records:
        print("ERROR: no records found in data file.", file=sys.stderr)
        sys.exit(1)

    # Split dataset
    test_ratio = 1.0 - args.train_ratio - args.val_ratio
    if test_ratio < 0:
        print(
            f"ERROR: train_ratio + val_ratio = {args.train_ratio + args.val_ratio:.3f} > 1.0",
            file=sys.stderr,
        )
        sys.exit(1)

    train_ds, val_ds, test_ds = split_dataset(
        records,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=test_ratio,
        seed=args.seed,
    )
    print(f"Split: train={len(train_ds):,}  val={len(val_ds):,}  test={len(test_ds):,}")
    print()

    # Build model
    hidden_sizes = [int(x.strip()) for x in args.hidden_sizes.split(",")]
    model_config = ValueNetworkConfig(
        input_dim=12,
        hidden_sizes=hidden_sizes,
        dropout=args.dropout,
        output_activation="softplus",
    )
    model = ValueNetwork(model_config)
    print(f"ValueNetwork: hidden_sizes={hidden_sizes}, params={model.param_count:,}")

    # Build trainer
    trainer_config = TrainerConfig(
        learning_rate=args.learning_rate,
        batch_size=args.batch_size,
        max_epochs=args.max_epochs,
        huber_delta=args.huber_delta,
        weight_decay=args.weight_decay,
        patience=args.patience,
        use_curriculum=not args.no_curriculum,
        seed=args.seed,
    )
    trainer = ValueTrainer(
        model=model,
        config=trainer_config,
        train_dataset=train_ds,
        val_dataset=val_ds,
    )

    # Train
    print(f"Training for up to {args.max_epochs} epochs (patience={args.patience})...")
    print(f"{'Epoch':>6}  {'Train Loss':>12}  {'Val MAE':>10}  {'Spearman':>10}  {'Acc@1':>8}")
    print("-" * 60)

    t_start = time.monotonic()
    results = trainer.train()
    train_time = time.monotonic() - t_start

    # Print per-epoch history
    for epoch_idx, (loss, val_m) in enumerate(
        zip(results["train_losses"], results["val_metrics"])
    ):
        marker = " *" if epoch_idx == results["best_epoch"] else ""
        print(
            f"{epoch_idx:>6}  {loss:>12.4f}  {val_m['mae']:>10.4f}  "
            f"{val_m['spearman']:>10.4f}  {val_m['accuracy_at_1']:>8.4f}{marker}"
        )

    print()
    print(f"Training complete in {train_time:.1f}s")
    print(f"Best epoch: {results['best_epoch']} | Best val MAE: {results['best_val_mae']:.4f}")

    # Save checkpoint
    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    trainer.save_checkpoint(str(output_path))
    print(f"Checkpoint saved to {output_path}")
    print()

    # Evaluate on test set
    print("Test set evaluation:")
    model.eval()
    test_metrics = trainer.evaluate(test_ds)
    print(f"  MAE:           {test_metrics['mae']:.4f}")
    print(f"  Spearman:      {test_metrics['spearman']:.4f}")
    print(f"  Accuracy@1:    {test_metrics['accuracy_at_1']:.4f}")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
