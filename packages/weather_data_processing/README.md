# Grid Data Processing

A production pipeline for processing Indian national grid electricity data from raw monthly files to cleaned, validated, half-hourly time series with proper timezone labeling.

## Overview

This package provides a complete data processing pipeline that:

1. **Combines monthly parquet files** into a single consolidated dataset
2. **Fills data gaps** using linear interpolation (short gaps) and gradient-based donor day methods (long gaps)
3. **Aggregates** 5-minute data to half-hourly intervals
4. **Labels timezone** information (Asia/Kolkata)
5. **Validates** the output to ensure data quality
6. **Optionally cleans up** intermediate files to save disk space

## Installation

From the repository root:

```bash
cd packages/grid_data_processing
pip install -e .
```

This will install the package in editable mode and create command-line entry points.

## Quick Start

### Command Line Usage

The package provides multiple command aliases (all equivalent):

```bash
# Process monthly files with default settings
gdp --monthly-dir data/grid_data/raw/monthly

# Same command with different aliases
griddataprocessing --monthly-dir data/grid_data/raw/monthly
gridprocessing --monthly-dir data/grid_data/raw/monthly
gridproc --monthly-dir data/grid_data/raw/monthly

# Process with verbose output
gdp --monthly-dir data/grid_data/raw/monthly --verbose

# Process existing combined file
gdp --input data/grid_data/raw/combined.parquet --verbose

# Keep intermediate files for inspection
gdp --monthly-dir data/grid_data/raw/monthly --keep-intermediate

# Custom config and output directory
gdp --monthly-dir data/grid_data/raw/monthly \
    --config configs/grid_data_processing/custom.json \
    --output data/custom_output
```

### Python API Usage

```python
from grid_data_processing import GridDataProcessor

# Create processor instance
processor = GridDataProcessor(
    monthly_dir="data/grid_data/raw/monthly",
    output_dir="data/grid_data/processed",
    verbose=True,
    keep_intermediate=False
)

# Run the full pipeline
final_file = processor.run_full_pipeline()
print(f"Processing complete: {final_file}")
```

## Command-Line Options

### Input Options

- `--input`, `-i`: Path to an existing combined parquet file (skips monthly file combination)
- `--monthly-dir`, `-m`: Directory containing monthly parquet files to be combined

Note: You must provide either `--input` or `--monthly-dir`.

### Output Options

- `--output`, `-o`: Output directory for processed files (default: `<data_dir>/grid_data/processed`)
- `--keep-intermediate`, `-k`: Keep intermediate step files (by default they are removed after successful completion)

### Configuration

- `--config`, `-c`: Path to custom configuration JSON file (default: auto-detect from `configs/grid_data_processing/default_processing.json`)

### Behavior

- `--verbose`, `-v`: Echo INFO+ messages to console (file logging always enabled)
- `--quiet`, `-q`: Suppress all console output (file logging still enabled)

## File Naming Convention

The pipeline automatically detects the date range from input files and uses it in output filenames:

**Input files** (monthly):
- `carbontracker_grid-data_2018_11.parquet`
- `carbontracker_grid-data_2018_12.parquet`
- ...
- `carbontracker_grid-data_2026_02.parquet`

**Output files** (automatically named):
- `carbontracker_grid-data_2018-11_2026-02_step0_combined.parquet` (if combining monthly files)
- `carbontracker_grid-data_2018-11_2026-02_step1_gapfilled.parquet`
- `carbontracker_grid-data_2018-11_2026-02_step2_half-hourly.parquet`
- `carbontracker_grid-data_2018-11_2026-02_step3_final.parquet` (final output)

The date range `2018-11_2026-02` indicates data spans from November 2018 to February 2026.

## Logging

The pipeline uses a comprehensive logging system:

- **File logs**: Complete DEBUG-level logs are ALWAYS written to `<repo_root>/logs/grid_data_processing/`
- **Console output**: Controlled by `--verbose` flag
  - `--verbose`: Shows INFO+ messages on console
  - Default (no flag): Console is silent, only file logging
  
This ensures you never lose diagnostic information while keeping automated runs clean.

**Additional logs** written to the logs directory:
- `gap_filling_audit_<timestamp>.parquet`: Detailed audit trail of all gap-filling operations
- `gap_filling_stats_<timestamp>.json`: Summary statistics of gap-filling results
- `validation_report_<timestamp>.txt`: Final validation report

## Pipeline Steps

### Step 0: Combine Monthly Files (Optional)

If `--monthly-dir` is provided, monthly parquet files are combined into a single time series, sorted by timestamp.

**Output**: `*_step0_combined.parquet`

### Step 1: Gap Filling

Fills missing data using a three-phase approach:

1. **Short gaps** (≤80 minutes by default): Linear interpolation
2. **Long gaps**: Gradient-based donor day method (first pass)
3. **Remaining gaps**: Gradient-based donor day method (second pass)

The gradient method finds similar days based on the gradient (rate of change) of a reference column (usually `demand_met`), ensuring filled values maintain realistic temporal patterns.

**Output**: `*_step1_gapfilled.parquet`

### Step 2: Temporal Aggregation

Aggregates 5-minute data to half-hourly intervals:

- Generation and demand columns: **mean** aggregation
- Emissions (tons_co2): **sum** aggregation
- Timestamps shifted to end-of-interval convention

**Output**: `*_step2_half-hourly.parquet`

### Step 3: Timezone Labeling

Adds timezone information (Asia/Kolkata) to timestamps. **Important**: This does NOT shift times—the data is already in the target timezone. This step just labels previously naive timestamps.

**Output**: `*_step3_final.parquet` (FINAL OUTPUT)

### Step 4: Validation

Comprehensive validation checks:
- Time range and span
- Time interval consistency (no unexpected gaps)
- Null value detection
- Negative value checks in generation columns
- Summary statistics

**Output**: Validation report in logs directory

### Step 5: Cleanup (Optional)

If `--keep-intermediate` is NOT set (default), removes intermediate files (steps 0, 1, 2), keeping only the final output.

## Configuration

Configuration files define:
- Data frequency (default: 5 minutes)
- Gap filling parameters (thresholds, columns, methods)
- Aggregation settings (target interval, columns to average/sum)
- Timezone settings

**Default location**: `configs/grid_data_processing/default_processing.json`

**Example configuration**:

```json
{
  "data_frequency_minutes": 5,
  "gap_filling": {
    "short_gap_threshold_minutes": 80,
    "ref_column": "demand_met",
    "columns_to_fill": [
      "thermal_generation",
      "gas_generation",
      "hydro_generation",
      "nuclear_generation",
      "renewable_generation",
      "tons_co2",
      "total_generation",
      "demand_met",
      "net_demand"
    ],
    "gradient": {
      "max_search_days": 21,
      "smooth_window_slots": 3,
      "prefer_same_weekday": true
    }
  },
  "aggregation": {
    "target_interval_minutes": 30,
    "avg_columns": [
      "thermal_generation",
      "gas_generation",
      "hydro_generation",
      "nuclear_generation",
      "renewable_generation",
      "total_generation",
      "demand_met",
      "net_demand",
      "g_co2_per_kwh",
      "tons_co2_per_mwh"
    ],
    "sum_columns": ["tons_co2"]
  },
  "timezone": {
    "target": "Asia/Kolkata"
  }
}
```

## Directory Structure

The package integrates with osme_common for standardized paths:

```
<repo_root>/
├── configs/
│   └── grid_data_processing/
│       └── default_processing.json
├── data/
│   └── grid_data/
│       ├── raw/
│       │   ├── monthly/              # Input: monthly parquet files
│       │   └── combined.parquet      # Optional: pre-combined file
│       └── processed/                # Output: processed files
└── logs/
    └── grid_data_processing/         # All logs and reports
        ├── grid_processing_<timestamp>.log
        ├── gap_filling_audit_<timestamp>.parquet
        ├── gap_filling_stats_<timestamp>.json
        └── validation_report_<timestamp>.txt
```

## Environment Variables

You can override default paths using environment variables (via osme_common):

- `OSME_DATA_DIR`: Override data directory
- `OSME_CONFIG_DIR`: Override config directory
- `OSME_LOG_DIR`: Override log directory
- `OSME_REPO_ROOT`: Override repository root detection

## Non-Interactive Operation

The pipeline runs in **non-interactive mode by default**, making it suitable for:
- Automated workflows
- Cron jobs
- Batch processing
- CI/CD pipelines

All operations proceed automatically without user prompts. Status and progress are logged to file and optionally echoed to console with `--verbose`.

## Error Handling

If the pipeline encounters an error:
- Complete error information is logged to the log file
- In verbose mode, error details are shown on console
- Exit codes indicate success (0) or failure (1)
- Partial outputs are preserved for debugging

## Examples

### Basic Usage

```bash
# Silent automated run (most common)
gdp --monthly-dir data/grid_data/raw/monthly

# Verbose run for monitoring
gdp --monthly-dir data/grid_data/raw/monthly --verbose
```

### Custom Configuration

```bash
# Use custom config for different gap-filling parameters
gdp --monthly-dir data/grid_data/raw/monthly \
    --config configs/grid_data_processing/aggressive_filling.json \
    --verbose
```

### Development and Debugging

```bash
# Keep intermediate files for inspection
gdp --monthly-dir data/grid_data/raw/monthly \
    --keep-intermediate \
    --verbose
    
# Process specific combined file
gdp --input data/grid_data/raw/carbontracker_grid-data_2018-11_2020-12.parquet \
    --output data/grid_data/test_output \
    --keep-intermediate \
    --verbose
```

## Troubleshooting

**Problem**: Command not found (gdp, griddataprocessing, etc.)

**Solution**: Ensure package is installed: `pip install -e .` from the package directory

---

**Problem**: Config file not found

**Solution**: Either place `default_processing.json` in `configs/grid_data_processing/` or specify path with `--config`

---

**Problem**: Missing input files

**Solution**: Verify either `--input` file exists or `--monthly-dir` contains parquet files matching pattern `carbontracker_grid-data_YYYY_MM.parquet`

---

**Problem**: Want to see what happened during processing

**Solution**: Check the log file in `logs/grid_data_processing/grid_processing_<timestamp>.log` - it contains complete DEBUG-level information

## Contributing

When modifying the pipeline:

1. Update configuration schema if adding new parameters
2. Add validation checks for new data transformations
3. Update logging to capture important operations
4. Test with both `--verbose` and quiet modes
5. Verify cleanup works correctly with `--keep-intermediate` flag

## License

See LICENSE file in repository root.
