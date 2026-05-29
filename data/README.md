# BimodalHarness Data Directory

This directory holds exported training data from BimodalLogic.

## Directory Structure

```
data/
├── README.md          # This file
├── VERSION            # Schema version and source tracking
├── .gitignore         # Excludes large JSONL files, keeps samples/
├── samples/           # Synthetic test fixtures (tracked in git)
│   └── test_formulas.jsonl
└── bimodal/           # Exported JSONL from BimodalLogic (NOT tracked)
    └── *.jsonl
```

## Data Flow

```
BimodalLogic (Lean 4)
  lake exe dataset_generator
      |
      v
  BimodalLogic/data/*.jsonl     (Lean export directory)
      |
      v  make sync-data
  BimodalHarness/data/bimodal/  (Local copy, not tracked in git)
      |
      v  bimodal_harness.data.load_jsonl()
  Python training pipeline
```

## Data Contract

All JSONL files in `data/bimodal/` must conform to the `LabeledFormula` schema
defined in `src/bimodal_harness/data/schema.py`. Each line is one JSON object.

See `docs/architecture/cross-repo-integration.md` for the complete schema
specification and version compatibility matrix.

## Syncing Data

To copy the latest exports from a local BimodalLogic checkout:

```bash
make sync-data BIMODAL_LOGIC_PATH=/path/to/BimodalLogic
```

Default source path is `../BimodalLogic` (sibling directory).

To validate that all JSONL files match the schema:

```bash
make validate-data
```

## Version Tracking

`data/VERSION` records the schema version and the BimodalLogic Git commit from
which the current `data/bimodal/` files were generated. Update this file after
each sync.

## Large Data Files

Files matching `data/bimodal/*.jsonl` and `data/*.jsonl` are excluded from git
(see `.gitignore`). For sharing large datasets, use:

- **Development**: rsync / Makefile sync target
- **Production**: GitHub Releases (attach as release assets) or git LFS
  (for repos where git LFS is configured)

The `data/samples/` directory is tracked in git and contains small synthetic
fixtures used by the test suite.
