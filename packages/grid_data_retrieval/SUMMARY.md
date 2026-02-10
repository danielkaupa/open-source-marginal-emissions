# Grid Data Retrieval - Simplified Module Summary

## What Changed

You asked for **retrieval only**, so I've simplified the module to focus exclusively on fetching data from the API.

## Module Scope

### ✅ What This Module Does

1. **Fetch** monthly grid data from CarbonTracker Merit API
2. **Combine** monthly files into single dataset  
3. **Save** raw data to `data/grid_data/raw/`
4. **Log** all operations

### ❌ What This Module Does NOT Do

- Gap-filling
- Resampling (5-minute → half-hourly)
- Timezone conversion
- Any data transformation

→ **These should go in your `data_cleaning_and_joining` module**

## File Structure

```
grid_data_retrieval_simplified/
├── README.md                          # Complete documentation
├── example_grid_config.json           # Example configuration
└── grid_data_retrieval/              # Module code
    ├── __init__.py
    ├── version.py
    ├── main.py                       # CLI entry
    ├── runner.py                     # Orchestration (fetch + combine)
    ├── io/
    │   ├── cli.py                    # Command-line interface
    │   └── config_loader.py          # Config file loading
    ├── sources/
    │   └── carbontracker.py          # API fetching
    └── utils/
        └── logging.py                # Logging utilities
```

**Total**: 10 Python files (down from 16 in the full version)

## What Was Removed

Compared to the full version, I removed:

- ❌ `utils/resampling.py` - Move to `data_cleaning_and_joining`
- ❌ `utils/timezone_conversion.py` - Move to `data_cleaning_and_joining`
- ❌ All processing logic from `runner.py`

## Installation

### 1. Copy Files

```bash
cp -r grid_data_retrieval /path/to/packages/grid_data_retrieval/src/
```

### 2. Update pyproject.toml

```toml
[project.scripts]
osme-grid-fetch = "grid_data_retrieval.main:main"
```

### 3. Install

```bash
pip install -e .
```

## Usage

### Fetch Data

```bash
# CLI
osme-grid-fetch --start "2020-01-01 00:00:00" --end "2020-12-31 23:55:00"

# With config file
osme-grid-fetch --config configs/grid/my_config.json
```

### Python API

```python
from grid_data_retrieval.runner import run_grid_retrieval

config = {
    "start_date": "2020-01-01 00:00:00",
    "end_date": "2020-12-31 23:55:00",
    "skip_existing": True,
    "combine_files": True,
}

run_grid_retrieval(config, verbose=True)
```

## Output

After running `osme-grid-fetch`:

```
data/grid_data/raw/
├── monthly/
│   ├── carbontracker_grid-data_2020_01.parquet
│   ├── carbontracker_grid-data_2020_02.parquet
│   └── ...
└── carbontracker_grid-data_2020-01_2020-12.parquet  # Combined
```

## Next: Process Data in data_cleaning_and_joining

Your original processing scripts should move to `data_cleaning_and_joining`:

```
data_cleaning_and_joining/
└── src/
    └── data_cleaning_and_joining/
        └── grid/
            ├── __init__.py
            ├── gap_fill.py              # New
            ├── resample.py              # Adapted from step4
            └── set_timezone.py          # Adapted from step5
```

Then create a processing pipeline:

```bash
# After fetching with osme-grid-fetch
python -m data_cleaning_and_joining.grid.resample \
  --input data/grid_data/raw/combined.parquet \
  --output data/grid_data/processed/half_hourly.parquet

python -m data_cleaning_and_joining.grid.set_timezone \
  --input data/grid_data/processed/half_hourly.parquet \
  --timezone "Asia/Kolkata"
```

## Module Comparison

| Feature | Full Version | Simplified Version | Location |
|---------|-------------|-------------------|----------|
| **Fetch monthly data** | ✅ | ✅ | grid_data_retrieval |
| **Combine files** | ✅ | ✅ | grid_data_retrieval |
| **Resample to half-hourly** | ✅ | ❌ | → data_cleaning_and_joining |
| **Timezone conversion** | ✅ | ❌ | → data_cleaning_and_joining |
| **Gap-filling** | ❌ | ❌ | → data_cleaning_and_joining |

## Workflow

### 1. Fetch (This Module)

```bash
osme-grid-fetch --config configs/grid/fetch_2020.json
```

Output: `data/grid_data/raw/carbontracker_grid-data_2020-01_2020-12.parquet`

### 2. Process (data_cleaning_and_joining)

```bash
# You'll create these
osme-clean-grid resample --input data/grid_data/raw/...
osme-clean-grid set-timezone --input data/grid_data/processed/...
```

## Dependencies

Same as full version:
- `polars>=0.19.0`
- `requests>=2.31.0`
- `python-dateutil>=2.8.0`
- `tqdm>=4.66.0`

Plus your existing:
- `osme_common` (for paths, logging patterns)

## Key Benefits of This Approach

1. **Clear Separation**: Retrieval vs Processing are separate concerns
2. **Modular**: Each module does one thing well
3. **Reusable**: Processing scripts can work on any grid data source
4. **Maintainable**: Easier to test and debug each piece
5. **Follows Conventions**: Similar to how `weather_data_retrieval` fetches and `data_cleaning_and_joining` processes

## Files to Download

All files are in the `grid_data_retrieval_simplified/` folder:

- ✅ Complete Python module
- ✅ README with full documentation
- ✅ Example configuration file
- ✅ All necessary `__init__.py` files

---

**Ready to use!** Just copy to your project and follow the installation steps in the README.
