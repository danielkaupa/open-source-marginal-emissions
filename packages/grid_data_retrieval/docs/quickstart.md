# Quickstart Guide

Get started with `grid_data_retrieval` in 5 minutes.

---

## Prerequisites

Before you begin, ensure you have:

- Python ≥ 3.11
- The OSME repository cloned
- `osme_common` package installed (shared utilities)

---

## Installation

### 1. Install the Module

From the repository root:

```bash
# Install in editable mode
pip install -e packages/grid_data_retrieval
```

This registers two CLI commands:
- `osme-grid` (recommended)
- `gdr` (short alias)

### 2. Verify Installation

```bash
osme-grid --help
```

You should see usage information and available options.

---

## First Run: Fetch 2 Months of Data

Let's fetch grid data for November-December 2018.

### Using CLI Arguments

```bash
osme-grid \
  --start-date "2018-11-01 00:00:00" \
  --end-date "2018-12-31 23:55:00" \
  --verbose
```

### Using a Configuration File

Create `configs/grid/quickstart.json`:

```json
{
  "start_date": "2018-11-01 00:00:00",
  "end_date": "2018-12-31 23:55:00"
}
```

Run:

```bash
osme-grid --config configs/grid/quickstart.json --verbose
```

### Expected Output

```
============================================================
Starting Grid Data Retrieval at 2025-02-10T14:30:00
============================================================

============================================================
Fetching Monthly Batches from API
============================================================
Fetching monthly batches from 2018-11-01 00:00:00 → 2018-12-31 23:55:00
API URL: https://32u36xakx6.execute-api.us-east-2.amazonaws.com/v4/get-merit-data
Output directory: /path/to/data/grid_data/raw/monthly

Fetching monthly data: 100%|████████████████| 2/2 [00:15<00:00,  7.5s/it]
Saved: carbontracker_grid-data_2018_11.parquet
Saved: carbontracker_grid-data_2018_12.parquet
Fetched 2 monthly file(s).

============================================================
Combining Monthly Files
============================================================
Found 2 monthly file(s) to combine.
Date range: 2018-11-01 00:00:00 → 2018-12-31 23:55:00
Writing combined file: carbontracker_grid-data_2018-11_2018-12.parquet
Combined file created successfully.

============================================================
Retrieval completed successfully!
Raw data saved to: /path/to/data/grid_data/raw/carbontracker_grid-data_2018-11_2018-12.parquet
============================================================

Next steps:
  - Use data_cleaning_and_joining module for processing
  - Apply gap-filling, resampling, timezone conversion as needed
```

---

## Check Your Output

### File Structure

```
data/grid_data/raw/
├── monthly/
│   ├── carbontracker_grid-data_2018_11.parquet
│   └── carbontracker_grid-data_2018_12.parquet
└── carbontracker_grid-data_2018-11_2018-12.parquet  # Combined

logs/grid_data_retrieval/
└── grid_retrieval_20250210_143000.log
```

### Inspect Data

Using Python:

```python
import polars as pl

# Load combined file
df = pl.read_parquet("data/grid_data/raw/carbontracker_grid-data_2018-11_2018-12.parquet")

print(f"Shape: {df.shape}")
print(f"Columns: {df.columns}")
print(f"\nFirst 5 rows:")
print(df.head())

# Summary stats
print(f"\nSummary:")
print(df.describe())
```

### Expected Variables

Your dataset should include:

- `timestamp` - UTC datetime (5-min intervals)
- `thermal_generation` - MW
- `gas_generation` - MW
- `hydro_generation` - MW
- `nuclear_generation` - MW
- `renewable_generation` - MW
- `total_generation` - MW
- `demand_met` - MW
- `net_demand` - MW
- `g_co2_per_kwh` - g CO₂/kWh
- `tons_co2_per_mwh` - tons CO₂/MWh
- `tons_co2` - tons CO₂

---

## Common Use Cases

### Fetch Full Year

```bash
osme-grid \
  --start-date "2020-01-01 00:00:00" \
  --end-date "2020-12-31 23:55:00" \
  --verbose
```

### Re-Download Existing Data

By default, existing months are skipped. To re-download:

```bash
osme-grid \
  --config configs/grid/my_config.json \
  --overwrite-existing
```

### Keep Monthly Files Separate

If you don't want a combined file:

```bash
osme-grid \
  --start-date "..." \
  --end-date "..." \
  --no-combine
```

### Custom Output Directory

```bash
osme-grid \
  --config configs/grid/my_config.json \
  --output-dir /path/to/custom/directory
```

---

## Configuration File Examples

### Minimal Config

```json
{
  "start_date": "2020-01-01 00:00:00",
  "end_date": "2020-12-31 23:55:00"
}
```

### Full Config

```json
{
  "start_date": "2020-01-01 00:00:00",
  "end_date": "2020-12-31 23:55:00",
  "api_url": "https://32u36xakx6.execute-api.us-east-2.amazonaws.com/v4/get-merit-data",
  "output_dir": null,
  "overwrite_existing": false,
  "combine_files": true
}
```

### Multi-Year Batch

For large downloads, create separate configs per year:

**configs/grid/india_2019.json:**
```json
{
  "start_date": "2019-01-01 00:00:00",
  "end_date": "2019-12-31 23:55:00"
}
```

**configs/grid/india_2020.json:**
```json
{
  "start_date": "2020-01-01 00:00:00",
  "end_date": "2020-12-31 23:55:00"
}
```

Run sequentially or in parallel:

```bash
# Sequential
osme-grid --config configs/grid/india_2019.json
osme-grid --config configs/grid/india_2020.json

# Parallel (in separate terminals)
osme-grid --config configs/grid/india_2019.json --output-dir data/grid_data/2019 &
osme-grid --config configs/grid/india_2020.json --output-dir data/grid_data/2020 &
```

---

## Next Steps

### 1. Process Your Data

Raw grid data is at 5-minute intervals in UTC. You'll likely want to:

- **Resample** to 30-minute intervals (to match weather data)
- **Convert timezone** to local time (e.g., Asia/Kolkata for India)
- **Check for gaps** and fill if necessary

These operations are handled by the `data_cleaning_and_joining` module:

```bash
# Resample (example - not yet implemented)
python -m data_cleaning_and_joining.grid.resample \
  --input data/grid_data/raw/carbontracker_grid-data_2020-01_2020-12.parquet \
  --output data/grid_data/processed/grid_30min.parquet \
  --frequency "30min"

# Convert timezone (example - not yet implemented)
python -m data_cleaning_and_joining.grid.set_timezone \
  --input data/grid_data/processed/grid_30min.parquet \
  --output data/grid_data/processed/grid_30min_ist.parquet \
  --timezone "Asia/Kolkata"
```

### 2. Fetch Weather Data

To train MEF models, you'll also need weather data:

```bash
osme-weather --config configs/weather/india_era5_2020.json
```

See the [`weather_data_retrieval` documentation](../weather_data_retrieval/) for details.

### 3. Join Datasets

Once you have both grid and weather data processed to the same temporal resolution and timezone, join them:

```python
import polars as pl

grid = pl.read_parquet("data/grid_data/processed/grid_30min_ist.parquet")
weather = pl.read_parquet("data/weather_data/processed/weather_30min_ist.parquet")

# Join on timestamp
joined = grid.join(weather, on="timestamp", how="inner")

joined.write_parquet("data/processed/grid_weather_joined.parquet")
```

### 4. Build MEF Models

Use `marginal_emissions_modelling` to train and evaluate models.

---

## Troubleshooting

### Command not found

```bash
# Make sure package is installed
pip install -e packages/grid_data_retrieval

# Verify entry points
pip show grid-data-retrieval | grep "Entry points" -A 5
```

### Rate limiting errors

The API has a 5-second delay between requests. If you see rate limit errors, increase the delay in `sources/carbontracker.py`:

```python
API_DELAY_SECONDS = 10  # Change from 5 to 10
```

### Path resolution issues

Check your data directory:

```bash
python -c "from osme_common.paths import data_dir; print(data_dir())"
```

If it's not what you expect, set the environment variable:

```bash
export OSME_DATA_DIR="/path/to/your/data"
```

### Network errors

If downloads are interrupted:

1. Re-run the same command - existing months will be skipped automatically
2. Check your internet connection
3. Verify the API is accessible: `curl https://carbontracker.in/`

---

## CLI Options Reference

Quick reference for all CLI options:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--config` | path | - | JSON config file |
| `--start-date` | datetime | 2018-11-21 00:00:00 | Start date |
| `--end-date` | datetime | 2019-01-31 23:55:00 | End date |
| `--api-url` | URL | CarbonTracker | API endpoint |
| `--output-dir` | path | data/grid_data/raw/ | Output directory |
| `--overwrite-existing` | flag | false | Re-download existing |
| `--no-combine` | flag | false | Don't combine files |
| `--verbose` | flag | false | Console output |
| `--quiet` | flag | false | Suppress console |

---

## Python API

If you prefer to script your data retrieval:

```python
from grid_data_retrieval.runner import run_grid_retrieval

config = {
    "start_date": "2020-01-01 00:00:00",
    "end_date": "2020-12-31 23:55:00",
    "overwrite_existing": False,
    "combine_files": True,
}

exit_code = run_grid_retrieval(config, verbose=True)

if exit_code == 0:
    print("Success!")
else:
    print("Failed!")
```

---

## What's Next?

✅ You've successfully retrieved grid data  
✅ You understand the output structure  
✅ You know how to customize the retrieval  

**Next:**
- Read the [Codebase Reference](codebase.md) to understand the module architecture
- Check the main [README](../README.md) for detailed API documentation
- Explore the [OSME documentation](../../) for the full MEF workflow

---

**Need help?** Open an issue on [GitHub](https://github.com/danielkaupa/open-source-marginal-emissions/issues) or email daniel.kaupa@outlook.com
