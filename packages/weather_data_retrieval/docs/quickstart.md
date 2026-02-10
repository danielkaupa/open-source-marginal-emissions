# Quickstart Guide

Welcome! This guide will walk you through downloading your first weather dataset. We'll start with an interactive session, then show you how to automate with configuration files.

## Before You Start

### 1. Get Your CDS API Credentials

To download ERA5 data, you need a free account with the Copernicus Climate Data Store:

1. **Register** at [https://cds.climate.copernicus.eu](https://cds.climate.copernicus.eu)
2. **Log in** and go to your profile page
3. **Copy your API key** – it looks like: `12345:abcd1234-ef56-7890-gh12-ijklmnop3456`
4. **Accept the license terms** for the datasets you plan to use (ERA5, ERA5-Land)

!!! tip "Keep Your API Key Safe"
    Don't commit your API key to version control! The tool will prompt you for it interactively, or you can set it in a `.env` file or environment variable.

### 2. Verify Installation

Check that the package is installed:

```bash
osme-weather --help
```

You should see the help message with available options.

---

## Your First Download (Interactive Mode)

Let's download 3 months of temperature and precipitation data for a small region. This should take about 5-10 minutes depending on your connection.

### Step 1: Start the Interactive Wizard

```bash
osme-weather
```

You'll see a welcome message explaining that you can type `back`, `exit`, or `Ctrl+C` at any time.

### Step 2: Follow the Prompts

The wizard will guide you through each configuration step:

#### 🌍 Data Provider
```
Which data provider would you like to use?
  1. CDS (Copernicus Climate Data Store - ERA5, ERA5-Land)
  2. Open-Meteo (coming soon)

Enter your choice (1-2): 1
```

Choose **1** for CDS.

---

#### 📊 Dataset Selection
```
Which dataset would you like to download?
  1. ERA5-Land (0.1° resolution, land surfaces only)
  2. ERA5 (0.25° resolution, global coverage)

Enter your choice (1-2): 1
```

Choose **1** for ERA5-Land (higher resolution, smaller files).

---

#### 🔐 API Authentication
```
Enter your CDS API URL (or press Enter for default):
[default: https://cds.climate.copernicus.eu/api]
```

Just press **Enter** to use the default.

```
Enter your CDS API key (format: UID:KEY):
```

Paste your API key from your CDS profile.

The tool will test your credentials. If successful, you'll see:
```
✓ CDS authentication successful!
```

---

#### 📅 Date Range
```
Enter start date (YYYY-MM-DD): 2023-01-01
```

```
Enter end date (YYYY-MM-DD): 2023-03-31
```

This will download data for January through March 2023 (3 monthly files).

---

#### 📍 Geographic Region
```
Define your region of interest.

Enter coordinates in [North, West, South, East] format.
Example for India: [35.0, 68.0, 8.0, 97.5]
Example for California: [42.0, -124.5, 32.5, -114.0]

Coordinates: [40, -5, 35, 5]
```

This example covers a region in southern Europe (roughly Spain and surrounding areas).

!!! tip "Finding Coordinates"
    - Use [https://boundingbox.klokantech.com/](https://boundingbox.klokantech.com/) to find coordinates
    - Format: `[North, West, South, East]` in decimal degrees
    - North/South: -90 to 90 (negative = Southern hemisphere)
    - West/East: -180 to 180 (negative = Western hemisphere)

---

#### 🌡️ Variables
```
Enter variable names (comma-separated).

Example: 2m_temperature, total_precipitation

Available variables: 2m_temperature, 10m_u_component_of_wind,
10m_v_component_of_wind, surface_pressure, total_precipitation,
surface_solar_radiation_downwards, surface_thermal_radiation_downwards,
and more...

Variables: 2m_temperature, total_precipitation
```

Start simple with these two common variables.

---

#### ⚙️ Download Settings

**Existing files:**
```
What should we do if files already exist?
  1. Skip existing files (recommended)
  2. Overwrite all files
  3. Ask me each time

Choice (1-3): 1
```

Choose **1** to avoid re-downloading.

**Parallel downloads:**
```
Enable parallel downloads? (y/n): y
```

**Maximum concurrent downloads:**
```
Max concurrent downloads (1-4, recommended: 2): 2
```

**Retry settings:**
```
Maximum retry attempts (0-10): 3
Delay between retries (seconds): 15
```

These defaults are usually good.

---

### Step 3: Review and Confirm

The wizard will show you a summary:

```
===========================================================
Download Request Summary
===========================================================
Provider: CDS
Dataset: era5-land
Dates: 2023-01-01 → 2023-03-31
Area: [40.0, -5.0, 35.0, 5.0]
Variables: ['2m_temperature', 'total_precipitation']
Save Directory: <repo_root>/data/era5-land/raw
...
Estimated number of monthly files: 3
Estimated size per file: 42.5 MB
Estimated total size: 127.5 MB
...
Estimated maximum total time: 8m 45s
```

```
Does this look correct? (yes/no): yes
```

Type **yes** to start downloading!

### Step 4: Watch the Progress

You'll see progress bars for each monthly file:

```
Downloading: era5-land_N40W5S35E5_abc123def456_2023-01.grib
Progress: [████████████████████] 100% | 42.5 MB | 4.2 MB/s
```

### Step 5: Find Your Data

When complete, your files will be saved to:

```
<repo_root>/
  └── data/
      └── era5-land/
          └── raw/
              ├── era5-land_N40W5S35E5_abc123def456_2023-01.grib
              ├── era5-land_N40W5S35E5_abc123def456_2023-02.grib
              └── era5-land_N40W5S35E5_abc123def456_2023-03.grib
```

Plus a detailed log file:

```
  └── logs/
      └── weather_data_retrieval/
          └── era5-land_N40W5S35E5_abc123def456_2023-01_2023-03_retrieved-20250210T143022.log
```

---

## Your Second Download (Batch Mode)

Now that you know what parameters you need, let's create a configuration file for reproducible downloads.

### Step 1: Create a Config File

Create `my_download.json`:

```json
{
  "data_provider": "cds",
  "dataset_short_name": "era5-land",
  "api_url": "https://cds.climate.copernicus.eu/api",
  "api_key": "YOUR_UID:YOUR_KEY_HERE",
  "start_date": "2023-01-01",
  "end_date": "2023-03-31",
  "region_bounds": [40, -5, 35, 5],
  "variables": [
    "2m_temperature",
    "total_precipitation"
  ],
  "existing_file_action": "skip_all",
  "retry_settings": {
    "max_retries": 3,
    "retry_delay_sec": 15
  },
  "parallel_settings": {
    "enabled": true,
    "max_concurrent": 2
  }
}
```

!!! warning "API Key Security"
    **Don't commit config files with API keys to GitHub!** Either:

    - Keep config files in a `private/` directory (add to `.gitignore`)
    - Use `"YOUR_API_KEY"` as a placeholder and pass the real key via environment variable
    - Use a separate credentials file

### Step 2: Run the Download

```bash
osme-weather --config my_download.json
```

That's it! The download runs automatically with no prompts.

### Step 3: Run with Verbose Output (Optional)

By default, batch mode only logs to files. To see progress in the terminal:

```bash
osme-weather --config my_download.json --verbose
```

---

## Common First-Time Scenarios

### Scenario 1: Small Region, Short Time Period
**Goal:** Quick test download to verify everything works

```json
{
  "data_provider": "cds",
  "dataset_short_name": "era5-land",
  "start_date": "2023-01-01",
  "end_date": "2023-01-31",
  "region_bounds": [41, -10, 36, 4],
  "variables": ["2m_temperature"]
}
```

Expected size: ~20 MB, ~2-3 minutes

---

### Scenario 2: Full Year, Medium Region
**Goal:** Complete annual dataset for a country or large region

```json
{
  "data_provider": "cds",
  "dataset_short_name": "era5-land",
  "start_date": "2023-01-01",
  "end_date": "2023-12-31",
  "region_bounds": [35, 68, 8, 97.5],
  "variables": [
    "2m_temperature",
    "total_precipitation",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind"
  ],
  "parallel_settings": {
    "enabled": true,
    "max_concurrent": 3
  }
}
```

This example is for India. Expected size: ~8-12 GB, 1-3 hours depending on connection.

---

### Scenario 3: Multiple Years, Global
**Goal:** Long-term global analysis

```json
{
  "data_provider": "cds",
  "dataset_short_name": "era5",
  "start_date": "2020-01-01",
  "end_date": "2023-12-31",
  "region_bounds": [90, -180, -90, 180],
  "variables": ["2m_temperature", "total_precipitation"],
  "parallel_settings": {
    "enabled": true,
    "max_concurrent": 4
  }
}
```

!!! warning "Large Download"
    This is a very large download (potentially 50+ GB). Make sure you have:

    - Sufficient disk space
    - A stable internet connection
    - Time (this could take several hours to days)
    - Retry settings configured

---

## What's Next?

Now that you've downloaded some weather data:

1. **Explore the files**: Use `xarray` to open the `.grib` files:
   ```python
   import xarray as xr
   ds = xr.open_dataset('data/era5-land/raw/era5-land_*.grib', engine='cfgrib')
   print(ds)
   ```

2. **Download grid data**: Move to the [grid_data_retrieval](../../osme-grid-data-retrieval-documentation/) package

3. **Process your data**: Continue to [data_cleaning_and_joining](../../osme-data-cleaning-and-joining-documentation/)

4. **Learn more about configs**: See the [Configuration Reference](configuration.md) for all available options

5. **Automate with scripts**: Check out the [User Guide](user-guide.md) for HPC batch scripts

---

## Troubleshooting Quick Tips

**"Authentication failed"**
→ Double-check your API key format: `UID:KEY` with no extra spaces

**"Request timed out"**
→ The CDS API can be slow during peak hours. The tool will retry automatically.

**"Invalid variable name"**
→ Check the [CDS dataset documentation](https://cds.climate.copernicus.eu/datasets) for exact variable names (they're case-sensitive)

**"Disk space"**
→ Check the estimate before downloading. Each month of ERA5-Land data is typically 30-100 MB depending on variables and region size.

For more help, see the full [Troubleshooting Guide](troubleshooting.md).
