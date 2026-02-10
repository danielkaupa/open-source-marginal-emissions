# User Guide

This guide covers everything you need to know about using the weather data retrieval package effectively, from basic concepts to advanced workflows.

## Overview

The `weather_data_retrieval` package is designed to handle two main workflows:

1. **Interactive Mode**: Step-by-step wizard for exploring options and one-off downloads
2. **Batch/Automatic Mode**: JSON configuration files for reproducible, automated downloads

Both modes use the same underlying download engine and produce identical outputs.

---

## Interactive Mode Deep Dive

Interactive mode is perfect when you're:

- Exploring available datasets and variables
- Not sure exactly what parameters you need
- Doing a one-time download for analysis
- Learning how the tool works

### Starting Interactive Mode

```bash
osme-weather
```

Or with the shorter alias:

```bash
wdr
```

### Navigation Commands

At any prompt, you can use:

- **`back`** – Return to the previous question (your answers are preserved)
- **`exit`** – Quit the wizard (your progress is not saved)
- **`Ctrl+C`** – Immediately stop the program

### Quiet Mode

If you want minimal console output (only errors and critical messages):

```bash
osme-weather --quiet
```

Logs are still written to files; you just won't see the prompt flow in your terminal.

### Understanding the Wizard Flow

The interactive wizard follows this sequence:

1. **Data Provider** (CDS or Open-Meteo - *Open-Meteo coming soon*)
2. **Dataset** (ERA5-Land or ERA5)
3. **Authentication** (API URL and key)
4. **Date Range** (start and end dates)
5. **Geographic Region** (bounding box coordinates)
6. **Variables** (which weather parameters to download)
7. **File Handling** (what to do with existing files)
8. **Parallel Settings** (concurrent downloads)
9. **Retry Settings** (how to handle failures)
10. **Confirmation** (review and approve)

You can navigate backwards through any of these steps if you need to change something.

### Smart Validation

The wizard validates your inputs in real-time:

- **Dates**: Must be valid and end ≥ start
- **Coordinates**: Must be within valid ranges (-90 to 90 for lat, -180 to 180 for lon)
- **Variables**: Checked against dataset-specific availability
- **API Key**: Tested with CDS to ensure it works before proceeding

If something is invalid, you'll get a clear error message and chance to re-enter.

---

## Batch/Automatic Mode Deep Dive

Batch mode is essential for:

- **Reproducibility**: The same config always produces the same download
- **Automation**: Integrate into larger data pipelines
- **Version Control**: Track exactly what data you downloaded (minus the API key)
- **HPC Workflows**: Submit jobs without interactive prompts
- **Team Collaboration**: Share standardized configs across researchers

### Basic Usage

```bash
osme-weather --config path/to/config.json
```

### Verbose Output

By default, batch mode only writes to log files. To see progress in your terminal:

```bash
osme-weather --config path/to/config.json --verbose
```

This shows the same output you'd see in interactive mode, but without requiring any input.

### Config File Structure

Here's a complete, annotated example:

```json
{
  "data_provider": "cds",
  "dataset_short_name": "era5-land",
  "api_url": "https://cds.climate.copernicus.eu/api",
  "api_key": "12345:abcdef123456789",
  "start_date": "2023-01-01",
  "end_date": "2023-12-31",
  "region_bounds": [40.0, -10.0, 35.0, 5.0],
  "variables": [
    "2m_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "surface_pressure",
    "total_precipitation"
  ],
  "existing_file_action": "skip_all",
  "retry_settings": {
    "max_retries": 6,
    "retry_delay_sec": 15
  },
  "parallel_settings": {
    "enabled": true,
    "max_concurrent": 2
  }
}
```

See the [Configuration Reference](configuration.md) for detailed documentation of every field.

### Config File Locations

The tool looks for config files in this order:

1. **Absolute paths**: `/home/user/configs/download.json`
2. **Relative to config directory**: `configs/weather/download.json`  
   (resolved to `<repo_root>/configs/weather/download.json`)
3. **Relative to current directory**: `./my_config.json`

We recommend keeping configs in the repository's `configs/weather/` directory for organization.

### Managing API Keys in Configs

**Never commit API keys to version control!** Here are three safe approaches:

#### Option 1: Placeholder + Manual Edit (Simple)

In your committed config:
```json
{
  "api_key": "YOUR_API_KEY_HERE",
  ...
}
```

Before running, edit to add your real key (but don't commit the change).

#### Option 2: Separate Credentials File (Better)

`download_config.json` (committed to repo):
```json
{
  "data_provider": "cds",
  "dataset_short_name": "era5-land",
  "api_url": "https://cds.climate.copernicus.eu/api",
  "api_key": "PLACEHOLDER",
  ...
}
```

`.env` or `credentials.json` (in `.gitignore`):
```json
{
  "CDS_API_KEY": "12345:abcdef123456789"
}
```

Then merge them in a script before running (future feature).

#### Option 3: Environment Variables (Best for CI/CD)

Set in your shell:
```bash
export CDS_API_KEY="12345:abcdef123456789"
```

Then reference in config (future feature):
```json
{
  "api_key": "${CDS_API_KEY}",
  ...
}
```

!!! note "Current Limitation"
    Environment variable substitution is not yet implemented. For now, use Option 1 or 2.

---

## Provider-Specific Details

### CDS (Copernicus Climate Data Store)

Currently, the only supported provider. Provides access to ERA5 and ERA5-Land datasets.

#### Getting Access

1. Register at [https://cds.climate.copernicus.eu](https://cds.climate.copernicus.eu)
2. Accept terms for the datasets you want (ERA5, ERA5-Land)
3. Get your API key from your profile page

#### API Rate Limits

The CDS API has request limits:

- **Max concurrent requests**: 4 (per user account)
- **Request queue**: If the system is busy, requests wait in a queue
- **Throttling**: Large requests may be slowed or delayed during peak hours

The tool handles these automatically with retries and backoff.

#### Available Datasets

**ERA5** (`era5-world`)
- **Resolution**: 0.25° (~27 km at equator)
- **Coverage**: Global (land and ocean)
- **Frequency**: Hourly
- **Variables**: 100+ atmospheric, ocean, and land variables
- **Good for**: Global analyses, ocean regions, coarse-resolution studies

**ERA5-Land** (`era5-land`)
- **Resolution**: 0.1° (~11 km at equator)
- **Coverage**: Land surfaces only
- **Frequency**: Hourly
- **Variables**: 50+ land surface variables
- **Good for**: Regional studies, high-resolution land analysis, hydrology

#### Variable Names

Variable names must exactly match the CDS dataset specifications (case-sensitive).

Common variables:

| Variable Name | Description | Units | Datasets |
|--------------|-------------|-------|----------|
| `2m_temperature` | Temperature at 2m above surface | K | Both |
| `total_precipitation` | Accumulated precipitation | m | Both |
| `10m_u_component_of_wind` | Eastward wind at 10m | m/s | Both |
| `10m_v_component_of_wind` | Northward wind at 10m | m/s | Both |
| `surface_pressure` | Pressure at surface | Pa | Both |
| `surface_solar_radiation_downwards` | Incoming solar radiation | J/m² | Both |
| `soil_temperature_level_1` | Top layer soil temperature | K | ERA5-Land |
| `snow_depth` | Snow depth | m | ERA5-Land |

For the complete list, see:
- [ERA5 variables](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels)
- [ERA5-Land variables](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land)

### Open-Meteo

!!! info "Coming Soon"
    Open-Meteo integration is planned but not yet available. Check the [project roadmap](../../PROJECT_ROADMAP/) for updates.

---

## File Management

### Output Directory Structure

Downloaded files are organized by dataset:

```
<repo_root>/
  └── data/
      ├── era5-land/
      │   └── raw/
      │       ├── era5-land_N40W10S35E5_abc123_2023-01.grib
      │       ├── era5-land_N40W10S35E5_abc123_2023-02.grib
      │       └── ...
      └── era5-world/
          └── raw/
              ├── era5-world_N50W20S30E10_def456_2023-01.grib
              └── ...
```

The `raw/` subdirectory indicates these files haven't been processed yet. Later pipeline stages will create `processed/`, `cleaned/`, etc.

### Filename Convention

Each file follows this pattern:

```
{dataset}_{coordinates}_{hash}_{year}-{month}.{ext}
```

**Example**: `era5-land_N40W10S35E5_abc123def456_2023-01.grib`

- `dataset`: `era5-land` or `era5-world`
- `coordinates`: Encoded bounding box (N=north, W=west, S=south, E=east)
- `hash`: 12-character hash of (dataset + variables + region)
- `year-month`: Data period
- `ext`: File extension (`.grib` for CDS downloads)

**Why the hash?** It lets you distinguish between downloads of the same region but different variables:

```
era5-land_N40W10S35E5_abc123_2023-01.grib  # temperature only
era5-land_N40W10S35E5_def456_2023-01.grib  # temperature + precipitation
```

### Existing File Handling

The `existing_file_action` setting controls what happens when a file already exists:

#### `skip_all` (Recommended)
```json
"existing_file_action": "skip_all"
```

Skips any month that already has a complete file. This is:
- **Fast**: No re-downloads
- **Safe**: Doesn't overwrite good data
- **Resume-friendly**: If a download fails partway through, re-running skips completed months

**When to use**: Almost always (default for batch mode)

#### `overwrite`
```json
"existing_file_action": "overwrite"
```

Re-downloads everything, replacing existing files.

**When to use**: 
- You know the existing files are corrupted
- CDS has updated the dataset and you need the new version
- You're testing download settings

!!! warning
    This can waste a lot of time and bandwidth!

#### `prompt` (Interactive Only)
```json
"existing_file_action": "prompt"
```

Asks you for each file whether to skip or overwrite.

**When to use**: 
- Interactive mode when you want control over individual files
- Not available in batch mode (treated as `skip_all`)

### File Validation

After downloading, the tool validates each file:

- **ZIP files**: Automatically extracts `.grib` files
- **Magic number check**: Verifies file starts with GRIB signature
- **Size check**: Warns if file is suspiciously small (<50 KB)

Corrupted or incomplete downloads are logged as failures and can be retried.

---

## Download Settings

### Parallel Downloads

Download multiple months simultaneously to speed up large requests.

```json
"parallel_settings": {
  "enabled": true,
  "max_concurrent": 2
}
```

#### Choosing `max_concurrent`

- **1**: Sequential (slowest, but most reliable)
- **2**: Good default (balances speed and stability)
- **3-4**: Faster for large downloads, but risks hitting CDS rate limits
- **5+**: Not recommended (may cause timeouts or account warnings)

!!! tip "Connection Speed Matters"
    If you have slow internet (<10 Mbps), parallelization won't help much. Stick with 1-2.

#### Efficiency Factor

The tool assumes parallel downloads are about 60% as efficient as perfect linear scaling. For example:

- 12 files, sequential: 60 minutes
- 12 files, 2 parallel: ~36 minutes (not 30)
- 12 files, 4 parallel: ~22 minutes (not 15)

This accounts for:
- CDS queue management
- Connection overhead
- Retry delays

### Retry Settings

Handles temporary failures gracefully.

```json
"retry_settings": {
  "max_retries": 6,
  "retry_delay_sec": 15
}
```

#### How Retries Work

1. Download request sent to CDS
2. If it fails (timeout, connection error, server error), wait `retry_delay_sec` seconds
3. Try again (up to `max_retries` times total)
4. If all retries exhausted, mark month as failed and continue to next month

#### Common Failure Reasons

- **CDS queue delays**: Request waits too long in queue
- **Network hiccups**: Temporary connection loss
- **Server overload**: CDS is busy during peak hours (usually European daytime)
- **API errors**: Rare CDS internal errors

Most failures are temporary and resolve with retries.

#### Recommended Settings

| Scenario | max_retries | retry_delay_sec | Notes |
|----------|-------------|-----------------|-------|
| Default | 3-6 | 15-30 | Good for most cases |
| Unreliable connection | 10 | 30 | More patient |
| Fast failure | 1-2 | 10 | Fail fast and move on |
| HPC batch job | 10 | 60 | Jobs run unattended, be patient |

### Speed Estimation

Before downloading, the tool:

1. **Tests your internet speed** (quick 10-second test)
2. **Estimates file sizes** based on variables, region, and resolution
3. **Calculates total time** accounting for processing overhead and parallelization

These are estimates and can vary based on:
- CDS server load
- Network variability
- Actual data density (some months may be larger/smaller)

---

## Logging

Every run produces detailed logs with timestamps, parameters, and outcomes.

### Log File Locations

Logs are saved to `<repo_root>/logs/weather_data_retrieval/`:

```
logs/
  └── weather_data_retrieval/
      ├── era5-land_N40W10S35E5_abc123_2023-01_2023-12_retrieved-20250210T143022.log
      └── run_automatic_20250210_120045.log
```

### Log File Naming

**Final logs** (after successful completion):
```
{filename_base}_{start-date}_{end-date}_retrieved-{timestamp}.log
```

**Temporary logs** (if run fails early):
```
run_{mode}_{timestamp}.log
```

### What's Logged

Each log file contains:

- **Configuration summary**: All parameters used
- **Download estimates**: Size and time predictions
- **Progress updates**: Each month started/completed
- **Validation results**: File checks, size verifications
- **Errors and retries**: Failed attempts and retry counts
- **Final summary**: Success/skip/fail counts

### Log Levels

- **DEBUG**: Everything, including prompts and internal state (file only)
- **INFO**: Normal progress updates
- **WARNING**: Issues that didn't stop the download (e.g., retries)
- **ERROR**: Failed downloads or critical issues

### Example Log Excerpt

```
2025-02-10 14:30:15 | INFO | Starting AUTOMATIC run
2025-02-10 14:30:15 | INFO | Configuration validation successful
2025-02-10 14:30:16 | INFO | Detected speed: 45.3 Mbps
2025-02-10 14:30:16 | INFO | Estimated total size: 1,234.5 MB
2025-02-10 14:30:16 | INFO | Estimated total time: 22m 15s
2025-02-10 14:30:16 | INFO | Beginning download process
2025-02-10 14:30:45 | INFO | Download completed: 2023-01 (42.3 MB)
2025-02-10 14:31:12 | WARNING | Download failed: 2023-02 (Connection timeout)
2025-02-10 14:31:27 | INFO | Retry 1/6: 2023-02
2025-02-10 14:31:58 | INFO | Download completed: 2023-02 (41.8 MB)
...
2025-02-10 14:52:03 | INFO | Download process completed
2025-02-10 14:52:03 | INFO | Successful: 12, Skipped: 0, Failed: 0
```

---

## HPC Workflows

The package includes shell scripts optimized for HPC job submission.

### Using the Provided Scripts

Located in the package directory:

```bash
# For ERA5-Land downloads
bash packages/weather_data_retrieval/main_land.sh

# For ERA5 (world) downloads
bash packages/weather_data_retrieval/main_world.sh
```

These scripts:
- Load the conda environment
- Set up proper paths
- Run batch mode with a predefined config
- Can be submitted to Slurm, PBS, or other job schedulers

### Example SLURM Submission

Create a file `submit_weather_download.slurm`:

```bash
#!/bin/bash
#SBATCH --job-name=weather_download
#SBATCH --output=logs/weather_%j.out
#SBATCH --error=logs/weather_%j.err
#SBATCH --time=24:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G

# Load environment
module load anaconda3
source activate osme

# Run download
osme-weather --config configs/weather/era5_india_2023.json --verbose
```

Submit with:
```bash
sbatch submit_weather_download.slurm
```

### HPC Best Practices

1. **Use batch mode**: No prompts means it can run unattended
2. **Set high retry counts**: Jobs may run during off-peak hours with better CDS availability
3. **Enable verbose logging**: Helpful for debugging from log files later
4. **Request adequate time**: Better to overestimate than have jobs killed
5. **Use parallelization**: HPC nodes often have good network connections
6. **Store in scratch space**: Large downloads should go to fast scratch storage, not home directories

### Monitoring Long Jobs

Check progress by tailing the log file:

```bash
tail -f logs/weather_data_retrieval/era5-land_*.log
```

Or check the SLURM output:

```bash
tail -f logs/weather_12345.out
```

---

## Advanced Patterns

### Multi-Region Downloads

Download the same time period for multiple regions by using separate configs:

```bash
# Europe
osme-weather --config configs/weather/era5_europe_2023.json

# Asia
osme-weather --config configs/weather/era5_asia_2023.json

# Americas
osme-weather --config configs/weather/era5_americas_2023.json
```

### Multi-Year Pipelines

For very long time series, break into chunks:

```bash
for year in {2010..2023}; do
  echo "Downloading $year..."
  osme-weather --config configs/weather/era5_${year}.json
done
```

Each config differs only in start/end dates:

```json
{
  "start_date": "2010-01-01",
  "end_date": "2010-12-31",
  ...
}
```

### Resuming Failed Downloads

If a download fails partway through:

1. **Check the log** to see which months succeeded
2. **Re-run with the same config** – `skip_all` will skip completed months
3. **Only failed months** will be re-attempted

No need to manually track what's missing!

### Testing Configurations

Before downloading years of data, test your config with a small date range:

```json
{
  "start_date": "2023-01-01",
  "end_date": "2023-01-31",
  ...
}
```

Once you verify it works:

```json
{
  "start_date": "2020-01-01",
  "end_date": "2023-12-31",
  ...
}
```

---

## Common Workflows

### Workflow 1: Exploratory Research

**Goal**: Download a small sample to test analysis code

1. Use **interactive mode** to explore variables
2. Download **1-3 months** of data
3. Develop your analysis pipeline
4. When ready, create a **batch config** for full download
5. Run the full download overnight or on HPC

### Workflow 2: Production Pipeline

**Goal**: Reproducible data acquisition for published research

1. Create **version-controlled configs** in `configs/weather/`
2. Use **batch mode** for all downloads
3. **Document configs** in your README (which region, which dates, why)
4. **Archive configs** with your published research for reproducibility
5. Rerun identical configs if you need to verify or extend results

### Workflow 3: Multi-Country Comparison

**Goal**: Compare marginal emissions across countries

1. Create **one config per country** with appropriate region bounds
2. Use **identical variables and date ranges** for fair comparison
3. **Name configs clearly**: `era5_india.json`, `era5_spain.json`, etc.
4. Run downloads in **parallel** (different terminal sessions or HPC jobs)
5. Use `skip_all` so you can safely rerun without duplication

---

## Tips & Tricks

### 🚀 Speed Up Downloads

- Use **ERA5** (0.25°) instead of **ERA5-Land** (0.1°) if resolution doesn't matter
- **Smaller regions** = smaller files = faster downloads
- **Fewer variables** = smaller files (do you really need all 20 variables?)
- **Enable parallelization** with `max_concurrent: 2-3`
- Download during **off-peak hours** (nights/weekends in Europe)

### 💾 Save Disk Space

- **Compress old files**: GRIB files compress well with `gzip`
- **Delete unnecessary intermediate files** after processing
- **Use external storage** for archives (not actively used data)
- **Sample by month**: Do you need *every* month? Maybe every 3rd month is enough for validation?

### 🔧 Troubleshooting Downloads

- **Check CDS status**: [https://cds.climate.copernicus.eu](https://cds.climate.copernicus.eu) shows system status
- **Retry a different time**: CDS is faster at night (Europe timezone)
- **Simplify request**: Fewer variables or smaller region may avoid timeouts
- **Check your API key**: Expired keys cause authentication failures

### 📋 Organizing Configs

Suggested structure:

```
configs/
  └── weather/
      ├── production/
      │   ├── india_2020-2023.json
      │   └── global_2022.json
      ├── testing/
      │   └── quick_test.json
      └── archive/
          └── old_india_2019.json
```

### 🔄 Sharing Configs with Team

Use a template pattern:

**Template** (`configs/weather/template_country.json`):
```json
{
  "data_provider": "cds",
  "dataset_short_name": "era5-land",
  "api_key": "YOUR_API_KEY_HERE",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "region_bounds": [N, W, S, E],
  "variables": ["2m_temperature", "total_precipitation"],
  "existing_file_action": "skip_all",
  "retry_settings": {"max_retries": 6, "retry_delay_sec": 15},
  "parallel_settings": {"enabled": true, "max_concurrent": 2}
}
```

Team members copy and fill in their values.

---

## What's Next?

- **Dive deeper into configs**: See [Configuration Reference](configuration.md) for every parameter
- **Having issues?**: Check [Troubleshooting](troubleshooting.md) for solutions
- **Understand the code**: Browse the [API Reference](codebase.md)
- **Continue the pipeline**: Move to [grid_data_retrieval](../../osme-grid-data-retrieval-documentation/)
