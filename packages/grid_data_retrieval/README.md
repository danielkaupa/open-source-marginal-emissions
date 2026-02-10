# Grid Data Retrieval

**Status:** 🚧 Under Development  
**Part of:** [Open Source Marginal Emissions (OSME)](https://github.com/danielkaupa/open-source-marginal-emissions)

Retrieve electricity grid data (demand, generation, emissions) from public APIs for use in marginal emissions factor (MEF) estimation workflows.

---

## Overview

The `grid_data_retrieval` module fetches electricity grid datasets from public sources and saves them in analysis-ready formats. This module handles **data retrieval only** — subsequent processing (gap-filling, resampling, timezone conversion) is handled by the `data_cleaning_and_joining` module.

### Current Capabilities

- ✅ **CarbonTracker India API** - Fetch 5-minute resolution grid data
- ✅ **Monthly batching** - Automatic splitting into monthly files
- ✅ **File combining** - Optional merging into single dataset
- ✅ **CLI & config-based** - Interactive or batch execution

### Planned Features

- 🚧 Electricity Maps API integration
- 🚧 IEA Real-Time Tracker integration
- 🚧 Additional country-specific sources
- 🚧 Completeness validation and gap reporting

---

## Installation

### Prerequisites

- Python ≥ 3.11
- The `osme_common` package (shared utilities)

### Install as part of OSME

```bash
# From repository root
pip install -e packages/grid_data_retrieval
```

This registers the CLI commands:
- `osme-grid` (primary)
- `gdr` (short alias)

---

## Quick Start

### Using CLI

```bash
# Fetch data interactively
osme-grid \
  --start-date "2020-01-01 00:00:00" \
  --end-date "2020-12-31 23:55:00" \
  --verbose
```

### Using Configuration File

```bash
# Create config: configs/grid/my_config.json
{
  "start_date": "2020-01-01 00:00:00",
  "end_date": "2020-12-31 23:55:00",
  "api_url": "https://32u36xakx6.execute-api.us-east-2.amazonaws.com/v4/get-merit-data",
  "overwrite_existing": false,
  "combine_files": true
}

# Run
osme-grid --config configs/grid/my_config.json
```

### Output

```
data/grid_data/raw/
├── monthly/
│   ├── carbontracker_grid-data_2020_01.parquet
│   ├── carbontracker_grid-data_2020_02.parquet
│   └── ...
└── carbontracker_grid-data_2020-01_2020-12.parquet  # Combined

logs/grid_data_retrieval/
└── grid_retrieval_20250210_120000.log
```

---

## Data Variables

Grid data from CarbonTracker India includes:

| Variable | Description | Unit |
|----------|-------------|------|
| `timestamp` | UTC datetime (5-min intervals) | - |
| `thermal_generation` | Thermal power generation | MW |
| `gas_generation` | Gas power generation | MW |
| `hydro_generation` | Hydro power generation | MW |
| `nuclear_generation` | Nuclear power generation | MW |
| `renewable_generation` | Renewable power generation | MW |
| `total_generation` | Total generation | MW |
| `demand_met` | Demand met | MW |
| `net_demand` | Net demand | MW |
| `g_co2_per_kwh` | Carbon intensity | g CO₂/kWh |
| `tons_co2_per_mwh` | Carbon intensity | tons CO₂/MWh |
| `tons_co2` | Total emissions | tons CO₂ |

**Note:** Timestamps are in UTC. Use `data_cleaning_and_joining` for timezone conversion.

---

## Typical Workflow

### 1. Fetch (this module)

```bash
osme-grid --config configs/grid/india_2019_2023.json
```

Output: `data/grid_data/raw/carbontracker_grid-data_2019-01_2023-12.parquet`

### 2. Clean & Join (data_cleaning_and_joining module)

```bash
# Resample to 30-minute intervals
python -m data_cleaning_and_joining.grid.resample \
  --input data/grid_data/raw/carbontracker_grid-data_2019-01_2023-12.parquet \
  --output data/grid_data/processed/grid_30min.parquet

# Convert to local timezone
python -m data_cleaning_and_joining.grid.set_timezone \
  --input data/grid_data/processed/grid_30min.parquet \
  --timezone "Asia/Kolkata"
```

### 3. Model (marginal_emissions_modelling module)

Join with weather data and train MEF models.

---

## CLI Reference

```bash
osme-grid [OPTIONS]
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--config PATH` | JSON config file | None |
| `--start-date "YYYY-MM-DD HH:MM:SS"` | Start datetime | 2018-11-21 00:00:00 |
| `--end-date "YYYY-MM-DD HH:MM:SS"` | End datetime | 2019-01-31 23:55:00 |
| `--api-url URL` | API endpoint | CarbonTracker |
| `--output-dir PATH` | Output directory | data/grid_data/raw/ |
| `--overwrite-existing` | Re-download existing files | False |
| `--no-combine` | Keep monthly files separate | False (combines) |
| `--verbose` | Show progress in console | False |
| `--quiet` | Suppress console output | False |

### Examples

```bash
# Minimal
osme-grid --start-date "2020-01-01 00:00:00" --end-date "2020-12-31 23:55:00"

# Re-download everything
osme-grid --config my_config.json --overwrite-existing

# Keep monthly files separate
osme-grid --start-date "..." --end-date "..." --no-combine

# Custom output location
osme-grid --config my_config.json --output-dir /custom/path
```

---

## Python API

### Fetch Monthly Batches

```python
from grid_data_retrieval.sources.carbontracker import fetch_monthly_batches

files = fetch_monthly_batches(
    start_date="2020-01-01 00:00:00",
    end_date="2020-12-31 23:55:00",
    api_url="https://...",
    output_dir="data/grid_data/raw/monthly",
    overwrite_existing=False
)
```

### Combine Files

```python
from grid_data_retrieval.sources.carbontracker import combine_monthly_files

combined_path = combine_monthly_files(
    monthly_dir="data/grid_data/raw/monthly",
    output_dir="data/grid_data/raw"
)
```

### Complete Pipeline

```python
from grid_data_retrieval.runner import run_grid_retrieval

config = {
    "start_date": "2020-01-01 00:00:00",
    "end_date": "2020-12-31 23:55:00",
    "overwrite_existing": False,
    "combine_files": True,
}

exit_code = run_grid_retrieval(config, verbose=True)
```

---

## Configuration

### Directory Settings

Default output directories are defined in `runner.py`:

```python
# Lines 43-44 in runner.py
OUTPUT_BASE_DIR = "grid_data/raw"      # Relative to data_dir()
MONTHLY_SUBDIR = "monthly"              # Subdirectory for monthly files
```

To customize permanently, edit these constants. To override per-run, use `--output-dir` or `config["output_dir"]`.

### Configuration File Format

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

**Required:**
- `start_date`, `end_date`

**Optional:**
- `api_url` - defaults to CarbonTracker
- `output_dir` - defaults to `data/grid_data/raw/`
- `overwrite_existing` - defaults to `false`
- `combine_files` - defaults to `true`

---

## Module Structure

```
grid_data_retrieval/
├── io/
│   ├── cli.py              # Command-line interface
│   └── config_loader.py    # JSON config parsing
├── sources/
│   └── carbontracker.py    # CarbonTracker API client
├── utils/
│   └── logging.py          # Logging utilities
├── main.py                 # CLI entry point
└── runner.py               # Orchestration logic
```

---

## Dependencies

Core:
- `osme-common>=0.0.0` - Shared utilities
- `requests>=2.31` - HTTP client
- `polars>=2.0` - DataFrame library
- `tqdm>=4.66` - Progress bars

Optional:
- `pydantic>=2.0` - Validation (future)
- `pyyaml>=6` - YAML config support (future)

---

## Logging

Logs are written to: `logs/grid_data_retrieval/grid_retrieval_{timestamp}.log`

- **File handler:** Captures all DEBUG+ messages
- **Console output:** Optional (via `--verbose`)
- **Format:** `YYYY-MM-DD HH:MM:SS | LEVEL | message`

---

## Error Handling

The module handles common errors gracefully:

- **Network errors:** Logged and skipped (continues with remaining months)
- **Invalid dates:** Raises `ValueError` with clear message
- **Missing config:** Suggests search paths tried
- **API errors:** Logs response and continues

Exit codes:
- `0` - Success
- `1` - Error occurred

---

## Troubleshooting

### Command not found

```bash
# Add to pyproject.toml
[project.scripts]
osme-grid = "grid_data_retrieval.main:main"

# Reinstall
pip install -e packages/grid_data_retrieval
```

### API rate limiting

Adjust delay in `sources/carbontracker.py`:

```python
API_DELAY_SECONDS = 10  # Increase from default 5
```

### Path issues

Check data directory:

```bash
python -c "from osme_common.paths import data_dir; print(data_dir())"
```

---

## Integration with OSME

This module is part of the OSME pipeline:

```
weather_data_retrieval  ─┐
                         ├─→ data_cleaning_and_joining ─→ marginal_emissions_modelling
grid_data_retrieval ─────┘
```

**Workflow:**
1. **Retrieve** weather data (ERA5) → `weather_data_retrieval`
2. **Retrieve** grid data (CarbonTracker) → `grid_data_retrieval` ⬅ **You are here**
3. **Clean & join** datasets → `data_cleaning_and_joining`
4. **Model** MEFs → `marginal_emissions_modelling`

---

## Contributing

See the main [OSME repository](https://github.com/danielkaupa/open-source-marginal-emissions) for contribution guidelines.

---

## License

This project is dual-licensed:

- **Open Source:** AGPL-3.0-or-later
- **Commercial:** Contact daniel.kaupa@outlook.com

See [LICENSE](../../LICENSE) and [COMMERCIAL-TERMS.md](../../COMMERCIAL-TERMS.md).

---

## Citation

If you use this module in research, please cite:

```
Kaupa, D. (2025). Open Source Marginal Emissions: Grid Data Retrieval Module.
https://github.com/danielkaupa/open-source-marginal-emissions
```

---

## Support

- **Documentation:** https://danielkaupa.github.io/open-source-marginal-emissions/
- **Issues:** https://github.com/danielkaupa/open-source-marginal-emissions/issues
- **Email:** daniel.kaupa@outlook.com
