# Configuration Reference

This page documents every configuration parameter for the weather data retrieval package. Use this as a reference when creating JSON config files for batch mode.

## Complete Configuration Example

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

---

## Required Parameters

These parameters must be present in every configuration file.

### `data_provider`

**Type**: `string`  
**Required**: Yes  
**Options**: `"cds"` (Open-Meteo coming soon)

The data provider to use for downloading weather data.

```json
"data_provider": "cds"
```

**Validation**:
- Must be exactly `"cds"` (case-insensitive, but `"cds"` is standard)
- Other providers will be added in future releases

---

### `dataset_short_name`

**Type**: `string`  
**Required**: Yes  
**Options**: `"era5-land"`, `"era5-world"` (when provider is `"cds"`)

The specific dataset to download.

```json
"dataset_short_name": "era5-land"
```

**Options**:

| Value | Description | Resolution | Coverage |
|-------|-------------|------------|----------|
| `era5-land` | ERA5-Land reanalysis | 0.1° (~11 km) | Land only |
| `era5-world` | ERA5 global reanalysis | 0.25° (~27 km) | Global (land + ocean) |

**Validation**:
- Must match one of the available datasets for the chosen provider
- Case-sensitive

---

### `api_url`

**Type**: `string`  
**Required**: Yes (for CDS provider)  
**Default**: `"https://cds.climate.copernicus.eu/api"`

The base URL for the CDS API.

```json
"api_url": "https://cds.climate.copernicus.eu/api"
```

**Validation**:
- Must be a valid URL starting with `http://` or `https://`
- For CDS, this should almost always be the default value
- Only change if CDS announces a new API endpoint

---

### `api_key`

**Type**: `string`  
**Required**: Yes (for CDS provider)  
**Format**: `"UID:KEY"` (for CDS)

Your authentication credentials for the data provider.

```json
"api_key": "12345:abcdef123456-7890-ghij-1234-klmnopqr5678"
```

**For CDS**:
- Format: `"UID:KEY"` (colon-separated)
- Found on your CDS profile page after registration
- Example: `"123456:abcd1234-5678-90ef-ghij-1234567890ab"`

**Security**:
- ⚠️ **Never commit API keys to version control**
- Use placeholders like `"YOUR_API_KEY_HERE"` in committed configs
- Add real keys only in local/private copies
- Consider using environment variables (future feature)

**Validation**:
- Tested against the API before downloads begin
- Invalid keys cause immediate failure with clear error message

---

### `start_date`

**Type**: `string`  
**Required**: Yes  
**Format**: `"YYYY-MM-DD"`

The beginning of the date range to download (inclusive).

```json
"start_date": "2023-01-01"
```

**Notes**:
- Downloads are chunked by month, so this is rounded to the start of the month
- `"2023-01-15"` effectively becomes `"2023-01-01"`
- Must be on or before `end_date`

**Validation**:
- Must be a valid date in `YYYY-MM-DD` format
- Cannot be in the future
- For ERA5 datasets, must be on or after `1940-01-01`
- For ERA5-Land, must be on or after `1950-01-01`

---

### `end_date`

**Type**: `string`  
**Required**: Yes  
**Format**: `"YYYY-MM-DD"`

The end of the date range to download (inclusive).

```json
"end_date": "2023-12-31"
```

**Notes**:
- Downloads are chunked by month, so this is rounded to the end of the month
- `"2023-06-15"` means the entire June 2023 will be downloaded
- Must be on or after `start_date`

**Validation**:
- Must be a valid date in `YYYY-MM-DD` format
- Must be on or after `start_date`
- Can be up to ~5 days before current date (CDS processing delay)

**Example Date Ranges**:

```json
// Single month
"start_date": "2023-01-01",
"end_date": "2023-01-31"

// Full year
"start_date": "2023-01-01",
"end_date": "2023-12-31"

// Multi-year
"start_date": "2020-01-01",
"end_date": "2023-12-31"

// Partial months (rounded to full months)
"start_date": "2023-03-15",  // Becomes March 1
"end_date": "2023-09-20"      // Downloads through end of September
```

---

### `region_bounds`

**Type**: `array` of 4 numbers  
**Required**: Yes  
**Format**: `[North, West, South, East]`

The geographic bounding box for the data download.

```json
"region_bounds": [40.0, -10.0, 35.0, 5.0]
```

**Format**: `[North, West, South, East]` in decimal degrees

| Position | Name | Range | Notes |
|----------|------|-------|-------|
| 0 | North | -90 to 90 | Northern boundary (latitude) |
| 1 | West | -180 to 180 | Western boundary (longitude) |
| 2 | South | -90 to 90 | Southern boundary (latitude) |
| 3 | East | -180 to 180 | Eastern boundary (longitude) |

**Validation**:
- North must be > South
- Latitude values: -90 to 90
- Longitude values: -180 to 180
- East can be < West for regions crossing the 180° meridian

**Common Regions**:

```json
// India
"region_bounds": [35.0, 68.0, 8.0, 97.5]

// Europe
"region_bounds": [71.0, -25.0, 35.0, 40.0]

// United States (continental)
"region_bounds": [50.0, -125.0, 25.0, -65.0]

// Global
"region_bounds": [90.0, -180.0, -90.0, 180.0]

// Crossing 180° meridian (e.g., Pacific islands)
"region_bounds": [10.0, 170.0, -10.0, -170.0]
```

**Tips**:
- Use [boundingbox.klokantech.com](https://boundingbox.klokantech.com/) to find coordinates
- Smaller regions = faster downloads and less disk space
- Include a small buffer around your study area for edge effects
- Remember: larger regions with higher resolution (ERA5-Land) can be very large files

---

### `variables`

**Type**: `array` of strings  
**Required**: Yes  
**Minimum**: 1 variable

The weather variables to download from the dataset.

```json
"variables": [
  "2m_temperature",
  "total_precipitation",
  "10m_u_component_of_wind",
  "10m_v_component_of_wind"
]
```

**Validation**:
- Variable names must exactly match the CDS dataset specifications (case-sensitive)
- Each variable is validated against dataset-specific available variables
- Invalid variables cause immediate failure with a helpful error message

**Common ERA5/ERA5-Land Variables**:

| Variable Name | Description | Units | Typical Use |
|--------------|-------------|-------|-------------|
| `2m_temperature` | Temperature 2m above surface | Kelvin | Thermal analysis, comfort models |
| `total_precipitation` | Accumulated precipitation | meters | Hydrology, renewable energy (hydro) |
| `10m_u_component_of_wind` | Eastward wind at 10m | m/s | Wind power, dispersion models |
| `10m_v_component_of_wind` | Northward wind at 10m | m/s | Wind power (combine with u) |
| `surface_pressure` | Atmospheric pressure at surface | Pa | Weather patterns, calibration |
| `surface_solar_radiation_downwards` | Incoming solar radiation | J/m² | Solar power potential |
| `surface_thermal_radiation_downwards` | Incoming longwave radiation | J/m² | Energy balance |

**ERA5-Land Specific Variables**:

| Variable Name | Description | Units |
|--------------|-------------|-------|
| `soil_temperature_level_1` | Top soil layer temperature | Kelvin |
| `soil_temperature_level_2` | Second soil layer temperature | Kelvin |
| `soil_moisture_level_1` | Top soil layer moisture | m³/m³ |
| `snow_depth` | Snow depth | meters |
| `skin_temperature` | Surface skin temperature | Kelvin |
| `leaf_area_index_low_vegetation` | LAI for low vegetation | m²/m² |
| `leaf_area_index_high_vegetation` | LAI for high vegetation | m²/m² |

**ERA5 (World) Specific Variables**:

| Variable Name | Description | Units |
|--------------|-------------|-------|
| `sea_surface_temperature` | Ocean surface temperature | Kelvin |
| `significant_height_of_combined_wind_waves_and_swell` | Wave height | meters |
| `mean_wave_direction` | Wave direction | degrees |

!!! tip "Finding Variable Names"
    - Browse the [CDS ERA5 dataset page](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels)
    - Browse the [CDS ERA5-Land dataset page](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land)
    - Check the "Variables" tab for complete lists
    - Variable names use underscores (not spaces or hyphens)

**File Size Impact**:
- More variables = larger files
- Some variables (like radiation) have higher data density
- Test with 1-2 variables first, then expand

---

## Optional Parameters

These parameters have sensible defaults but can be customized.

### `existing_file_action`

**Type**: `string`  
**Required**: No  
**Default**: `"skip_all"`  
**Options**: `"skip_all"`, `"overwrite"`, `"prompt"`

How to handle months that already have downloaded files.

```json
"existing_file_action": "skip_all"
```

**Options**:

| Value | Behavior | When to Use |
|-------|----------|-------------|
| `skip_all` | Skip any month with an existing file | Default, resume failed downloads |
| `overwrite` | Re-download and replace all existing files | Force refresh, fix corrupted files |
| `prompt` | Ask for each file (interactive mode only) | Fine-grained control |

**Validation**:
- In batch mode, `"prompt"` is automatically converted to `"skip_all"` (no user to prompt)
- A warning is logged when this conversion happens

**Behavior Details**:

**`skip_all`**:
- Fastest option (no redundant downloads)
- Safe default for resuming interrupted downloads
- Checks for existing files by looking for the same filename pattern
- Even if the file is corrupted, it will be skipped (use `overwrite` to force redownload)

**`overwrite`**:
- Downloads everything from scratch
- Useful if CDS has updated the dataset
- Can waste significant time and bandwidth

**`prompt`**:
- Only works in interactive mode
- Shows you each file and asks: `Skip or overwrite? (s/o):`
- Gives you full control but requires attention

---

### `retry_settings`

**Type**: `object`  
**Required**: No  
**Default**: `{"max_retries": 3, "retry_delay_sec": 15}`

Controls retry behavior for failed download attempts.

```json
"retry_settings": {
  "max_retries": 6,
  "retry_delay_sec": 15
}
```

**Sub-parameters**:

#### `max_retries`
**Type**: `integer`  
**Range**: 0 to 20 (clamped if outside this range)  
**Default**: 3

Maximum number of times to retry a failed download.

- `0`: No retries (fail immediately)
- `1-3`: Fast failure, good for testing
- `3-6`: Recommended for production
- `6-10`: Patient, good for unreliable connections or HPC
- `10+`: Very patient (auto-clamped to 20)

#### `retry_delay_sec`
**Type**: `integer`  
**Range**: 5 to 300 seconds (clamped if outside)  
**Default**: 15

How long to wait between retry attempts (in seconds).

- `5-15`: Quick retries, good for minor hiccups
- `15-30`: Recommended for CDS (gives queue time to clear)
- `30-60`: Patient, good for busy periods
- `60+`: Very patient, good for HPC jobs that run overnight

**Example Scenarios**:

```json
// Fast failure for testing
"retry_settings": {
  "max_retries": 1,
  "retry_delay_sec": 10
}

// Balanced (default)
"retry_settings": {
  "max_retries": 3,
  "retry_delay_sec": 15
}

// Patient (HPC or overnight jobs)
"retry_settings": {
  "max_retries": 10,
  "retry_delay_sec": 60
}
```

**Validation**:
- Values outside the allowed ranges are automatically clamped
- A warning is logged when clamping occurs
- Example: `max_retries: 50` → clamped to 20 with a warning

---

### `parallel_settings`

**Type**: `object`  
**Required**: No  
**Default**: `{"enabled": false, "max_concurrent": 1}`

Controls parallel downloading of multiple months simultaneously.

```json
"parallel_settings": {
  "enabled": true,
  "max_concurrent": 2
}
```

**Sub-parameters**:

#### `enabled`
**Type**: `boolean`  
**Default**: `false`

Whether to enable parallel downloads.

- `false`: Download one month at a time (sequential)
- `true`: Download multiple months simultaneously

#### `max_concurrent`
**Type**: `integer`  
**Range**: 1 to 8 (clamped if outside)  
**Default**: 1

Maximum number of simultaneous downloads.

- `1`: Sequential (same as `enabled: false`)
- `2`: Good default for most cases
- `3-4`: Faster for large downloads, good network needed
- `4+`: Risks hitting CDS rate limits, not usually recommended

**Validation**:
- `max_concurrent` is clamped to 1-8
- If `enabled: false`, `max_concurrent` is ignored
- A warning is logged if values are clamped

**Performance Notes**:

The tool assumes parallel downloads have ~60% efficiency compared to perfect linear scaling:

| Months | Sequential Time | Parallel (2) | Parallel (4) |
|--------|----------------|--------------|--------------|
| 12 | 60 min | ~36 min | ~22 min |
| 24 | 120 min | ~72 min | ~44 min |
| 48 | 240 min | ~144 min | ~88 min |

This accounts for:
- CDS queue management overhead
- Network connection overhead
- Retry delays and throttling

**Example Scenarios**:

```json
// Sequential (most reliable)
"parallel_settings": {
  "enabled": false
}

// Balanced speed/reliability (recommended)
"parallel_settings": {
  "enabled": true,
  "max_concurrent": 2
}

// Fast (requires good connection)
"parallel_settings": {
  "enabled": true,
  "max_concurrent": 4
}
```

**When NOT to use parallelization**:
- Slow internet connection (<10 Mbps)
- Unreliable connection (frequent dropouts)
- Downloading from shared/metered connection
- CDS is reporting degraded performance

---

## Validation and Error Handling

### Automatic Corrections

Some invalid values are automatically corrected with a warning logged:

**Clamping**:
```json
// Input
"retry_settings": {
  "max_retries": 50,  // Too high
  "retry_delay_sec": 3  // Too low
}

// Auto-corrected to
"retry_settings": {
  "max_retries": 20,  // Clamped to maximum
  "retry_delay_sec": 5  // Clamped to minimum
}
// Warning logged: "max_retries clamped from 50 to 20"
```

**Mode Conversion**:
```json
// Input (batch mode)
"existing_file_action": "prompt"

// Auto-corrected to
"existing_file_action": "skip_all"
// Warning logged: "Cannot prompt in batch mode, using skip_all"
```

### Fatal Errors

These errors cause immediate failure:

- Missing required parameters
- Invalid data_provider or dataset_short_name
- Invalid date format or impossible date range
- Invalid region_bounds (North ≤ South, out of range coords)
- Invalid variables for chosen dataset
- Failed API authentication
- Malformed JSON

---

## Environment Variables

Some settings can be controlled via environment variables (useful for CI/CD or HPC).

!!! note "Future Feature"
    Environment variable support is limited in the current version. Full support is planned.

**Currently Supported**:

### `OSME_DATA_DIR`

Override the default data directory.

```bash
export OSME_DATA_DIR="/scratch/user/weather_data"
osme-weather --config my_config.json
```

Files will be saved to `$OSME_DATA_DIR/<dataset>/raw/` instead of `<repo_root>/data/`.

### `OSME_LOG_DIR`

Override the default log directory.

```bash
export OSME_LOG_DIR="/scratch/user/logs"
osme-weather --config my_config.json
```

Logs will be saved to `$OSME_LOG_DIR/weather_data_retrieval/` instead of `<repo_root>/logs/`.

---

## Complete Schema Reference

Here's the full JSON schema for validation:

```json
{
  "data_provider": "cds",  // required, string, enum: ["cds"]
  "dataset_short_name": "era5-land",  // required, string, enum: ["era5-land", "era5-world"]
  "api_url": "https://cds.climate.copernicus.eu/api",  // required (for CDS), string, URL
  "api_key": "UID:KEY",  // required (for CDS), string
  "start_date": "YYYY-MM-DD",  // required, string, date format
  "end_date": "YYYY-MM-DD",  // required, string, date format, >= start_date
  "region_bounds": [N, W, S, E],  // required, array of 4 numbers
  "variables": ["var1", "var2"],  // required, array of strings, min 1
  "existing_file_action": "skip_all",  // optional, string, enum: ["skip_all", "overwrite", "prompt"], default: "skip_all"
  "retry_settings": {  // optional, object
    "max_retries": 3,  // integer, 0-20, default: 3
    "retry_delay_sec": 15  // integer, 5-300, default: 15
  },
  "parallel_settings": {  // optional, object
    "enabled": false,  // boolean, default: false
    "max_concurrent": 1  // integer, 1-8, default: 1
  }
}
```

---

## Example Configurations

### Minimal Configuration

```json
{
  "data_provider": "cds",
  "dataset_short_name": "era5-land",
  "api_url": "https://cds.climate.copernicus.eu/api",
  "api_key": "12345:abcdef",
  "start_date": "2023-01-01",
  "end_date": "2023-01-31",
  "region_bounds": [40, -10, 35, 5],
  "variables": ["2m_temperature"]
}
```

All optional parameters use defaults.

### Production Configuration

```json
{
  "data_provider": "cds",
  "dataset_short_name": "era5-land",
  "api_url": "https://cds.climate.copernicus.eu/api",
  "api_key": "YOUR_API_KEY_HERE",
  "start_date": "2020-01-01",
  "end_date": "2023-12-31",
  "region_bounds": [35.0, 68.0, 8.0, 97.5],
  "variables": [
    "2m_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "surface_pressure",
    "total_precipitation",
    "surface_solar_radiation_downwards"
  ],
  "existing_file_action": "skip_all",
  "retry_settings": {
    "max_retries": 6,
    "retry_delay_sec": 30
  },
  "parallel_settings": {
    "enabled": true,
    "max_concurrent": 3
  }
}
```

This configuration:
- Downloads 4 years of data (48 monthly files)
- Covers India region
- Includes 6 common variables for energy modeling
- Uses robust retry settings
- Enables parallel downloads for speed
- Skips existing files (safe for resuming)

---

## Next Steps

- See [User Guide](user-guide.md) for usage patterns and workflows
- Check [Troubleshooting](troubleshooting.md) for common configuration errors
- Browse example configs in the repository's `configs/weather/` directory
