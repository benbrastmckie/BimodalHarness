#!/usr/bin/env python3
"""
Validate all JSONL files in the data/ directory against the LabeledFormula schema.

Usage:
    python scripts/validate_data.py
    make validate-data
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src/ to path for standalone invocation
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bimodal_harness.data import load_jsonl  # noqa: E402


def main() -> int:
    data_dir = Path("data")
    if not data_dir.exists():
        print("data/ directory not found — nothing to validate")
        return 0

    files = sorted(data_dir.glob("**/*.jsonl"))
    if not files:
        print("No .jsonl files found in data/")
        return 0

    errors = 0
    for f in files:
        count = 0
        try:
            for _record in load_jsonl(f):
                count += 1
            print(f"  OK  {f} ({count} records)")
        except Exception as exc:
            print(f"  ERR {f}: {exc}")
            errors += 1

    if errors:
        print(f"\nValidation failed: {errors} file(s) with errors")
        return 1

    print(f"\nAll {len(files)} file(s) valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
