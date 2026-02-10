# Grid Data Retrieval Module - Simplified (Fetch Only)

## Overview

This module provides **data retrieval only** for electricity grid data from the CarbonTracker Merit API. It has been designed to integrate seamlessly with your existing `osme_common` infrastructure and follows the same patterns as `weather_data_retrieval`.

**Important**: This module **only fetches** raw data. All data processing (gap-filling, resampling, timezone conversion) should be handled by the `data_cleaning_and_joining` module.

## What This Module Does

✅ **Fetch** monthly grid data from CarbonTracker API  
✅ **Combine** monthly files into single dataset  
✅ **Save** raw data to `data/grid_data/raw/`  

## What This Module Does NOT Do

❌ Gap-filling  
❌ Resampling (5-min → half-hourly)  
❌ Timezone conversion  
❌ Any data cleaning or transformation  

→ Use `data_cleaning_and_joining` module for these tasks

## Module Structure

```
grid_data_retrieval/
├── __init__.py              # Package initialization
├── version.py               # Version management
├── main.py                  # CLI entry point
├── runner.py                # Fetching orchestration
├── io/
│   ├── __init__.py
│   ├── cli.py              # Command-line interface
│   └── config_loader.py    # JSON config loading
├── sources/
│   ├── __init__.py
│   └── carbontracker.py    # CarbonTracker API implementation
└── utils/
    ├── __init__.py
    └── logging.py          # Logging infrastructure
```

## Quick Start

### 1. Installation

```bash
# Copy files to your project
cp -r grid_data_retrieval /path/to/packages/grid_data_retrieval/src/

# Add CLI entry point to pyproject.toml
[project.scripts]
osme-grid-fetch = "grid_data_retrieval.main:main"

# Reinstall
pip install -e .
```

### 2. Fetch Data

**Using CLI**:
```bash
osme-grid-fetch \
  --start "2020-01-01 00:00:00" \
  --end "2020-12-31 23:55:00" \
  --verbose
```

**Using config file**:
```bash
osme-grid-fetch --config configs/grid/my_config.json
```

### 3. Process Data

After fetching, use `data_cleaning_and_joining` module:

```bash
# Example workflow (you'll implement these in data_cleaning_and_joining)
osme-clean-grid gap-fill --input data/grid_data/raw/combined.parquet
osme-clean-grid resample --input data/grid_data/gap_filled.parquet
osme-clean-grid set-timezone --input data/grid_data/resampled.parquet --tz "Asia/Kolkata"
```

## CLI Reference

### osme-grid-fetch

Fetch grid data from API and save to `data/grid_data/raw/`.

**Arguments**:
```
--config PATH           Path to JSON config file
--start DATETIME        Start date (YYYY-MM-DD HH:MM:SS)
--end DATETIME          End date (YYYY-MM-DD HH:MM:SS)
--api-url URL           API endpoint URL
--skip-existing         Skip months that already have files (default)
--no-skip-existing      Re-download all months
--no-combine            Keep monthly files separate (don't combine)
--verbose               Echo logs to console
--quiet                 Suppress console output
```

**Examples**:
```bash
# Fetch one month
osme-grid-fetch \
  --start "2020-01-01 00:00:00" \
  --end "2020-01-31 23:55:00" \
  --verbose

# Fetch full year with config
osme-grid-fetch --config configs/grid/fetch_2020.json

# Re-download existing data
osme-grid-fetch --config my_config.json --no-skip-existing
```

## Configuration File

### Example config.json

```json
{
  "start_date": "2018-11-21 00:00:00",
  "end_date": "2019-01-31 23:55:00",
  "api_url": "https://32u36xakx6.execute-api.us-east-2.amazonaws.com/v4/get-merit-data",
  "skip_existing": true,
  "combine_files": true
}
```

### Configuration Options

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `start_date` | string | Yes | - | Start datetime (YYYY-MM-DD HH:MM:SS) |
| `end_date` | string | Yes | - | End datetime (YYYY-MM-DD HH:MM:SS) |
| `api_url` | string | No | CarbonTracker URL | API endpoint |
| `skip_existing` | boolean | No | true | Skip existing monthly files |
| `combine_files` | boolean | No | true | Combine monthly files into one |

## Python API

### Fetch monthly batches

```python
from grid_data_retrieval.sources.carbontracker import fetch_monthly_batches

files = fetch_monthly_batches(
    start_date="2020-01-01 00:00:00",
    end_date="2020-12-31 23:55:00",
    api_url="https://...",
    output_dir="data/grid_data/raw/monthly",
    skip_existing=True
)
```

### Combine monthly files

```python
from grid_data_retrieval.sources.carbontracker import combine_monthly_files

combined_path = combine_monthly_files(
    monthly_dir="data/grid_data/raw/monthly",
    output_dir="data/grid_data/raw"
)
```

### Run complete retrieval

```python
from grid_data_retrieval.runner import run_grid_retrieval

config = {
    "start_date": "2020-01-01 00:00:00",
    "end_date": "2020-12-31 23:55:00",
    "skip_existing": True,
    "combine_files": True,
}

exit_code = run_grid_retrieval(config, verbose=True)
```

## Output Structure

After running `osme-grid-fetch`, you'll have:

```
data/grid_data/raw/
├── monthly/
│   ├── carbontracker_grid-data_2020_01.parquet
│   ├── carbontracker_grid-data_2020_02.parquet
│   └── ...
└── carbontracker_grid-data_2020-01_2020-12.parquet  # Combined file

logs/grid_data_retrieval/
└── grid_retrieval_20250210_120000.log
```

## Data Variables

The following variables are fetched from the API:

| Variable | Description | Unit |
|----------|-------------|------|
| `timestamp` | Datetime of observation | - |
| `thermal_generation` | Thermal power generation | MW |
| `gas_generation` | Gas power generation | MW |
| `hydro_generation` | Hydro power generation | MW |
| `nuclear_generation` | Nuclear power generation | MW |
| `renewable_generation` | Renewable power generation | MW |
| `total_generation` | Total generation | MW |
| `demand_met` | Demand met | MW |
| `net_demand` | Net demand | MW |
| `g_co2_per_kwh` | Emission intensity | g CO₂/kWh |
| `tons_co2_per_mwh` | Emission intensity | tons CO₂/MWh |
| `tons_co2` | Total CO₂ emissions | tons |

**Note**: Data is at **5-minute intervals** and timestamps are **UTC**.

## Typical Workflow

### 1. Fetch Raw Data (This Module)

```bash
osme-grid-fetch --config configs/grid/fetch_2020.json
```

Output: `data/grid_data/raw/carbontracker_grid-data_2020-01_2020-12.parquet`

### 2. Process Data (data_cleaning_and_joining module)

You'll create these scripts in `data_cleaning_and_joining`:

```bash
# Gap-filling (if needed)
python -m data_cleaning_and_joining.grid.gap_fill \
  --input data/grid_data/raw/carbontracker_grid-data_2020-01_2020-12.parquet \
  --output data/grid_data/processed/gap_filled.parquet

# Resample to half-hourly
python -m data_cleaning_and_joining.grid.resample \
  --input data/grid_data/processed/gap_filled.parquet \
  --output data/grid_data/processed/half_hourly.parquet

# Convert timezone
python -m data_cleaning_and_joining.grid.set_timezone \
  --input data/grid_data/processed/half_hourly.parquet \
  --timezone "Asia/Kolkata" \
  --output data/grid_data/processed/final.parquet
```

## Reusing Original Processing Scripts

Your original `step4_accumulating_to_half-hourly.py` and `step5_set_timezone.py` can be adapted for `data_cleaning_and_joining`:

```
data_cleaning_and_joining/
└── src/
    └── data_cleaning_and_joining/
        └── grid/
            ├── __init__.py
            ├── gap_fill.py        # New
            ├── resample.py        # Adapted from step4
            └── set_timezone.py    # Adapted from step5
```

## Error Handling

- **API Errors**: Logged and skipped; continues with remaining months
- **Network Issues**: Includes 5-second rate limiting
- **Missing Files**: Raises `FileNotFoundError` with clear message

Exit codes:
- `0` - Success
- `1` - Error occurred

## Logging

Logs written to: `logs/grid_data_retrieval/grid_retrieval_YYYYMMDD_HHMMSS.log`

- **File handler**: Captures all DEBUG+ messages
- **Console handler** (optional): Shows INFO+ messages
- Uses `tqdm.write()` for non-blocking progress output

## Differences from Full Version

| Feature | Full Version | This Version |
|---------|-------------|--------------|
| Fetch data | ✅ | ✅ |
| Combine files | ✅ | ✅ |
| Resample to half-hourly | ✅ | ❌ (use data_cleaning_and_joining) |
| Timezone conversion | ✅ | ❌ (use data_cleaning_and_joining) |
| Gap-filling | ❌ | ❌ (use data_cleaning_and_joining) |

## Migration from Original Scripts

| Original Script | New Location |
|----------------|--------------|
| `step1_fetch_grid_data.py` | `sources/carbontracker.py::fetch_monthly_batches()` |
| `step2_join_monthly_files.py` | `sources/carbontracker.py::combine_monthly_files()` |
| `step4_accumulating_to_half-hourly.py` | → Move to `data_cleaning_and_joining/grid/` |
| `step5_set_timezone.py` | → Move to `data_cleaning_and_joining/grid/` |

## Troubleshooting

### "Command 'osme-grid-fetch' not found"

Add to `pyproject.toml`:
```toml
[project.scripts]
osme-grid-fetch = "grid_data_retrieval.main:main"
```

Then reinstall: `pip install -e .`

### API Rate Limiting

Increase delay in `sources/carbontracker.py`:
```python
API_DELAY_SECONDS = 10  # Change from 5 to 10
```

### Path Issues

Check search paths:
```bash
python -c "from osme_common.paths import data_dir; print(data_dir())"
```

## Next Steps

1. ✅ Install this module for data **fetching**
2. ✅ Create `data_cleaning_and_joining/grid/` for **processing**
3. ✅ Move `step4` and `step5` scripts to processing module
4. ✅ Build unified processing pipeline
5. ✅ Run end-to-end workflow

## Integration with Other Modules

```
┌─────────────────────────┐
│  grid_data_retrieval    │  ← This module (fetch only)
│  osme-grid-fetch        │
└──────────┬──────────────┘
           │
           ├─ Saves to: data/grid_data/raw/
           │
           ↓
┌─────────────────────────┐
│ data_cleaning_and_joining │
│   ├── grid/              │
│   │   ├── gap_fill.py   │
│   │   ├── resample.py   │  ← Adapted from step4
│   │   └── set_timezone.py │  ← Adapted from step5
└─────────────────────────┘
```

---

**Author**: Daniel Kaupa  
**License**: AGPL-3.0-or-later  
**Module**: grid_data_retrieval (Retrieval Only)
