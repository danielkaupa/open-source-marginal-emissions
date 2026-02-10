# API Reference

This page documents the internal structure of the `weather_data_retrieval` package. This is useful if you want to understand how the code works, extend it, or integrate it into other tools.

!!! note "For End Users"
    If you're just using the package to download data, you probably don't need this page. See the [User Guide](user-guide.md) or [Quickstart](quickstart.md) instead.

## Package Structure

The package is organized into several modules:

```
weather_data_retrieval/
├── main.py                 # Entry point for CLI
├── runner.py               # Core orchestration logic
├── io/                     # Input/output handling
│   ├── cli.py             # Command-line interface
│   ├── prompts.py         # Interactive wizard prompts
│   └── config_loader.py   # JSON config loading
├── sources/               # Data provider implementations
│   ├── cds_era5.py       # CDS/ERA5 downloader
│   └── open_meteo.py     # Open-Meteo (planned)
└── utils/                 # Shared utilities
    ├── session_management.py  # Session state tracking
    ├── data_validation.py     # Input validation
    ├── file_management.py     # File naming and checking
    └── logging.py             # Logging configuration
```

---

## Core Modules

### Entry Point & Orchestration

#### `main.py`

The main entry point for the CLI. This is what gets called when you run `osme-weather`.

::: weather_data_retrieval.main
    options:
      show_source: false
      heading_level: 4

**Key Function**: `main()`

- Parses command-line arguments
- Determines run mode (interactive vs. batch)
- Sets up logging
- Delegates to either the interactive wizard or batch runner

**Usage**:
```python
# Called automatically by CLI
# osme-weather [--config FILE] [--verbose] [--quiet]
```

---

#### `runner.py`

Core orchestration logic for the download workflow. This handles validation, estimation, and download coordination.

::: weather_data_retrieval.runner
    options:
      show_source: false
      heading_level: 4

**Key Functions**:

**`run(config, run_mode, verbose, logger)`**

Main workflow orchestrator that:

1. Validates the configuration
2. Maps config to session state
3. Performs internet speed test
4. Estimates download size and time
5. Generates filename hash
6. Orchestrates downloads
7. Reports final statistics

**Parameters**:
- `config` (dict): Configuration dictionary
- `run_mode` (str): `"interactive"` or `"automatic"`
- `verbose` (bool): Whether to echo progress to console
- `logger` (logging.Logger): Logger instance

**Returns**:
- `int`: Exit code (0=success, 1=fatal error, 2=some failures)

**`run_batch_from_config(cfg_path, logger)`**

Convenience wrapper for batch mode. Loads config and calls `run()`.

---

## Input/Output Modules

### `io/cli.py`

Command-line interface and interactive wizard.

::: weather_data_retrieval.io.cli
    options:
      show_source: false
      heading_level: 4

**Key Functions**:

**`parse_args()`**

Parses command-line arguments using argparse.

**Returns**: `argparse.Namespace` with fields:
- `config`: Path to config file (if `--config` provided)
- `verbose`: Boolean for verbose output (batch mode)
- `quiet`: Boolean for quiet mode (interactive mode)

**`run_prompt_wizard(session, logger)`**

Drives the interactive prompt flow. Steps through each configuration parameter, validates inputs, and handles back/exit commands.

**Parameters**:
- `session` (SessionState): Session state to populate
- `logger` (logging.Logger): Logger instance

**Returns**:
- `bool`: `True` if completed successfully, `False` if user exited early

---

### `io/prompts.py`

Individual prompt functions for each configuration step.

::: weather_data_retrieval.io.prompts
    options:
      show_source: false
      heading_level: 4

**Key Functions**:

Each prompt function handles user input for a specific configuration parameter:

- `prompt_data_provider()` - Choose CDS or Open-Meteo
- `prompt_dataset_short_name()` - Choose ERA5-Land or ERA5
- `prompt_cds_url()` - CDS API URL
- `prompt_cds_api_key()` - CDS API key
- `prompt_date_range()` - Start and end dates
- `prompt_coordinates()` - Region bounds [N, W, S, E]
- `prompt_variables()` - Variable selection
- `prompt_skip_overwrite_files()` - Existing file handling
- `prompt_parallelisation_settings()` - Parallel download settings
- `prompt_retry_settings()` - Retry configuration
- `prompt_continue_confirmation()` - Final review and confirmation

All prompt functions follow the same pattern:

**Parameters**:
- `session` (SessionState): Current session state
- `logger` (logging.Logger): Logger instance
- `echo_console` (bool): Whether to echo to console

**Returns**: 
- The validated input value, or
- `"__EXIT__"` if user wants to quit, or
- `"__BACK__"` if user wants to go to previous prompt

---

### `io/config_loader.py`

JSON configuration file loading and validation.

::: weather_data_retrieval.io.config_loader
    options:
      show_source: false
      heading_level: 4

**Key Functions**:

**`load_and_validate_config(path, logger, run_mode)`**

Loads a JSON config file and validates it.

**Parameters**:
- `path` (str): Path to JSON config file
- `logger` (logging.Logger, optional): Logger for validation messages
- `run_mode` (str): `"interactive"` or `"automatic"`

**Returns**:
- `dict`: Validated configuration

**Raises**:
- `FileNotFoundError`: If config file doesn't exist
- `ValueError`: If config is invalid

**`load_config(file_path)`**

Simple config loader without validation (for internal use).

---

## Data Provider Modules

### `sources/cds_era5.py`

CDS/ERA5 data provider implementation.

::: weather_data_retrieval.sources.cds_era5
    options:
      show_source: false
      heading_level: 4

**Key Functions**:

**`orchestrate_cds_downloads(session, filename_base, save_dir, ...)`**

Manages the entire CDS download workflow:

1. Generates list of months to download
2. Checks for existing files (skip logic)
3. Coordinates parallel or sequential downloads
4. Handles retries and failures
5. Validates downloaded files
6. Updates success/failure lists

**Parameters**:
- `session` (SessionState): Current session with all parameters
- `filename_base` (str): Base filename for output files
- `save_dir` (Path): Directory to save files
- `successful_downloads` (list): List to append successful months
- `failed_downloads` (list): List to append failed months
- `skipped_downloads` (list): List to append skipped months
- `logger` (logging.Logger): Logger instance
- `echo_console` (bool): Whether to echo progress
- `allow_prompts` (bool): Whether prompts are allowed (interactive mode)

**`download_monthly_era5_file(...)`**

Downloads a single month of ERA5 data.

**Parameters**:
- `client` (cdsapi.Client): Authenticated CDS client
- `dataset_full_name` (str): Full CDS dataset name
- `year` (int): Year to download
- `month` (int): Month to download
- `variables` (list): Variables to request
- `region_bounds` (list): Geographic bounds [N, W, S, E]
- `output_file` (Path): Where to save the file
- Various retry and logging parameters

**Returns**:
- `Path`: Path to downloaded file if successful, else `None`

---

### `sources/open_meteo.py`

Open-Meteo data provider (planned, not yet implemented).

::: weather_data_retrieval.sources.open_meteo
    options:
      show_source: false
      heading_level: 4

!!! info "Coming Soon"
    This module is a placeholder for future Open-Meteo integration.

---

## Utility Modules

### `utils/session_management.py`

Session state tracking and management.

::: weather_data_retrieval.utils.session_management
    options:
      show_source: false
      heading_level: 4

**Key Classes**:

**`SessionState`**

A simple key-value store for tracking configuration state during interactive sessions.

**Methods**:
- `get(key, default=None)` - Retrieve a value
- `set(key, value)` - Store a value
- `unset(key)` - Remove a value
- `first_unfilled_key()` - Get the next required key that hasn't been set
- `to_dict()` - Convert session to a dictionary (for saving)

**Usage**:
```python
session = SessionState()
session.set("data_provider", "cds")
session.set("dataset_short_name", "era5-land")

provider = session.get("data_provider")  # "cds"
config = session.to_dict()  # {"data_provider": "cds", ...}
```

**Key Functions**:

**`internet_speedtest(test_urls, max_seconds, logger, echo_console)`**

Performs a quick internet speed test to estimate download times.

**Parameters**:
- `test_urls` (list, optional): URLs to test (uses defaults if None)
- `max_seconds` (int): Maximum time to spend testing
- `logger` (logging.Logger): Logger instance
- `echo_console` (bool): Whether to echo results

**Returns**:
- `float`: Estimated speed in Mbps

**`map_config_to_session(config, session, logger, echo_console)`**

Maps a configuration dictionary to a SessionState, validating as it goes.

---

### `utils/data_validation.py`

Input validation functions.

::: weather_data_retrieval.utils.data_validation
    options:
      show_source: false
      heading_level: 4

**Key Functions**:

**`validate_config(config, logger, run_mode)`**

Comprehensive configuration validation. Checks:

- All required fields are present
- Data types are correct
- Values are in valid ranges
- Enumerations match allowed values
- Dates are properly formatted and logical
- Region bounds are valid

**Side Effects**:
- Clamps out-of-range values with warnings
- Converts incompatible settings (e.g., `prompt` → `skip_all` in batch mode)

**`validate_cds_api_key(api_url, api_key, logger, echo_console)`**

Tests CDS API credentials by attempting to create a client connection.

**Returns**:
- `cdsapi.Client` if successful, else `None`

**`invalid_era5_world_variables(variables)`**

Checks for invalid variable names in ERA5 (world) dataset.

**Returns**:
- `list`: Invalid variable names (empty if all valid)

**`invalid_era5_land_variables(variables)`**

Checks for invalid variable names in ERA5-Land dataset.

**Returns**:
- `list`: Invalid variable names (empty if all valid)

**Formatting Helpers**:

- `format_coordinates_nwse(boundaries)` - Convert bounds to string like `"N40W10S35E5"`
- `format_duration(seconds)` - Convert seconds to human-readable duration
- `validate_date_format(date_string)` - Check if date string is valid YYYY-MM-DD

---

### `utils/file_management.py`

File naming, checking, and estimation functions.

::: weather_data_retrieval.utils.file_management
    options:
      show_source: false
      heading_level: 4

**Key Functions**:

**`generate_filename_hash(dataset_short_name, variables, boundaries)`**

Creates a unique 12-character hash from download parameters. This ensures files with different parameters don't collide.

**Returns**:
- `str`: 12-character hash (e.g., `"abc123def456"`)

**`find_existing_month_file(save_dir, filename_base, year, month)`**

Searches for an existing file for a given month, handling different date separators and extensions.

**Returns**:
- `Path` if file exists, else `None`

**`estimate_era5_monthly_file_size(variables, area, grid_resolution, ...)`**

Estimates file size for a monthly ERA5 download based on empirical data.

**Parameters**:
- `variables` (list): Variables to download
- `area` (list): Region bounds
- `grid_resolution` (float): Grid spacing in degrees
- `timestep_hours` (float): Temporal resolution
- `bytes_per_value` (float): Storage size per value

**Returns**:
- `float`: Estimated size in MB

**`estimate_cds_download(variables, area, start_date, end_date, observed_speed_mbps, ...)`**

Comprehensive download estimation including size, time, and parallelization effects.

**Returns**:
- `dict`: 
  ```python
  {
    "months": 12,              # Number of monthly files
    "file_size_MB": 42.3,      # Average file size
    "total_size_MB": 507.6,    # Total download size
    "time_per_file_sec": 180,  # Time per file
    "total_time_sec": 2160     # Total estimated time
  }
  ```

**File Format Helpers**:

- `is_zip_file(path)` - Check if file is a ZIP archive
- `is_grib_file(path)` - Check if file is a GRIB file
- `unpack_zip_to_grib(zip_path, final_grib_path)` - Extract GRIB from ZIP

---

### `utils/logging.py`

Logging configuration and utilities.

::: weather_data_retrieval.utils.logging
    options:
      show_source: false
      heading_level: 4

**Key Functions**:

**`setup_logger(save_dir, run_mode, verbose)`**

Initializes a configured logger for the package.

**Parameters**:
- `save_dir` (str, optional): Directory for log files (defaults to `logs/weather_data_retrieval/`)
- `run_mode` (str): `"interactive"` or `"automatic"`
- `verbose` (bool): Whether to show console output

**Returns**:
- `logging.Logger`: Configured logger instance

**Configuration**:
- File handler: DEBUG level (everything)
- Console handler: INFO level (only in interactive or verbose mode)
- Format: `"%(asctime)s | %(levelname)s | %(message)s"`

**`log_msg(msg, logger, level, echo_console, force)`**

Unified logging utility that writes to file and optionally to console.

**Parameters**:
- `msg` (str): Message to log
- `logger` (logging.Logger): Logger instance
- `level` (str): `"debug"`, `"info"`, `"warning"`, `"error"`, `"exception"`
- `echo_console` (bool): Print to console
- `force` (bool): Print even if `echo_console=False` (for critical messages)

**`build_download_summary(session, estimates, speed_mbps, save_dir)`**

Constructs a formatted summary of the download configuration.

**Returns**:
- `str`: Multi-line summary string

**`create_final_log_file(session, filename_base, original_logger, ...)`**

Creates a final log file with the same naming convention as data files.

**Parameters**:
- `session` (SessionState): Current session
- `filename_base` (str): Base filename
- `original_logger` (logging.Logger): Current logger
- `delete_original` (bool): Remove temporary log
- `reattach_to_final` (bool): Continue logging to final file

**Returns**:
- `str`: Path to final log file

---

## Usage Examples

### Creating a Custom Download Script

```python
from weather_data_retrieval.runner import run

# Define your configuration
config = {
    "data_provider": "cds",
    "dataset_short_name": "era5-land",
    "api_url": "https://cds.climate.copernicus.eu/api",
    "api_key": "YOUR_KEY",
    "start_date": "2023-01-01",
    "end_date": "2023-03-31",
    "region_bounds": [40, -10, 35, 5],
    "variables": ["2m_temperature"],
    "existing_file_action": "skip_all",
    "retry_settings": {"max_retries": 3, "retry_delay_sec": 15},
    "parallel_settings": {"enabled": True, "max_concurrent": 2}
}

# Run the download
exit_code = run(config, run_mode="automatic", verbose=True)

if exit_code == 0:
    print("Download completed successfully!")
elif exit_code == 2:
    print("Download completed with some failures. Check logs.")
else:
    print("Download failed. Check logs.")
```

### Validating a Config Before Running

```python
from weather_data_retrieval.utils.data_validation import validate_config
from weather_data_retrieval.utils.logging import setup_logger

logger = setup_logger(run_mode="automatic", verbose=True)

config = { ... }  # Your config

try:
    validate_config(config, logger=logger, run_mode="automatic")
    print("✓ Configuration is valid!")
except ValueError as e:
    print(f"✗ Configuration error: {e}")
```

### Estimating Download Before Running

```python
from weather_data_retrieval.utils.file_management import estimate_cds_download
from weather_data_retrieval.utils.session_management import internet_speedtest

# Test internet speed
speed_mbps = internet_speedtest(max_seconds=10, logger=None, echo_console=True)

# Estimate download
estimates = estimate_cds_download(
    variables=["2m_temperature", "total_precipitation"],
    area=[40, -10, 35, 5],
    start_date="2023-01-01",
    end_date="2023-12-31",
    observed_speed_mbps=speed_mbps,
    grid_resolution=0.1
)

print(f"Estimated files: {estimates['months']}")
print(f"Total size: {estimates['total_size_MB']:.1f} MB")
print(f"Estimated time: {estimates['total_time_sec'] / 60:.1f} minutes")
```

---

## Extending the Package

### Adding a New Data Provider

To add a new provider (e.g., Open-Meteo):

1. **Create provider module**: `sources/my_provider.py`

2. **Implement download function**:
   ```python
   def orchestrate_my_provider_downloads(
       session, filename_base, save_dir,
       successful_downloads, failed_downloads, skipped_downloads,
       logger, echo_console, allow_prompts
   ):
       # Your implementation
       pass
   ```

3. **Add to session mapping**: Update `session_management.py` to handle new provider

4. **Add validation**: Update `data_validation.py` to validate provider-specific params

5. **Update prompts**: Add provider selection in `io/prompts.py`

### Adding New Variables

Variables are validated against hard-coded lists in `data_validation.py`:

```python
# In data_validation.py

ERA5_LAND_VARIABLES = [
    "2m_temperature",
    "total_precipitation",
    # ... add new variable here
]
```

### Adding New Configuration Parameters

1. **Define in SessionState**: Add to the required/optional keys list

2. **Add validation**: Update `validate_config()` in `data_validation.py`

3. **Add prompt** (if interactive): Create `prompt_new_parameter()` in `io/prompts.py`

4. **Use in runner**: Access via `session.get("new_parameter")` in your code

---

## Testing

### Running Unit Tests

```bash
# From repo root
pytest packages/weather_data_retrieval/tests/
```

### Testing Individual Modules

```python
# Test validation
from weather_data_retrieval.utils.data_validation import validate_config

config = {...}
validate_config(config, logger=None, run_mode="automatic")
```

### Mock Testing Downloads

For testing without hitting the CDS API, you can mock the download functions:

```python
from unittest.mock import patch, MagicMock

with patch('weather_data_retrieval.sources.cds_era5.download_monthly_era5_file') as mock_download:
    mock_download.return_value = Path("/fake/file.grib")
    # Run your test
```

---

## Further Reading

- [User Guide](user-guide.md) for usage patterns
- [Configuration Reference](configuration.md) for all parameters
- [Troubleshooting](troubleshooting.md) for common issues
- [GitHub Repository](https://github.com/danielkaupa/open-source-marginal-emissions) for source code
