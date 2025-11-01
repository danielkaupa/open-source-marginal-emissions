# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

import calendar
from datetime import datetime, time, timedelta
import tempfile
from typing import List, Optional, Any
import cdsapi
import os
from pathlib import Path


# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from weather_data_retrieval.utils.logging import log_msg


# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# This file lives at: <project_root>/weather_data_retrieval/utils/data_validation.py
# parents[0] = .../utils, parents[1] = .../weather_data_retrieval, parents[2] = <project_root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
INPUT_DIR = PROJECT_ROOT / "input"

# Public defaults used by the rest of the app
default_save_dir = RAW_DATA_DIR
default_input_dir = INPUT_DIR

# Lists of known "bad" variables for various datasets
invalid_era5_world_variables = [
    'fraction_of_cloud_cover',
    'large_scale_precipitation',
    # UNTESTED
    'snow_density',
    'snow_depth',
    'snowfall',
    'surface_runoff',
    'sub_surface_runoff',
    'total_evaporation',
    'volumetric_soil_water_layer_1',
    'volumetric_soil_water_layer_2',
    'volumetric_soil_water_layer_3',
    'volumetric_soil_water_layer_4',
    'skin_reservoir_content',
    'temperature_of_snow_layer',
    'soil_temperature_level_1',
    'soil_temperature_level_2',
    'soil_temperature_level_3',
    'soil_temperature_level_4'
]

test_payload = {
    "dataset": "reanalysis-era5-single-levels",
    "request": {
        "product_type": ["reanalysis"],
        "variable": ["2m_temperature"],
        "year": ["2025"],
        "month": ["01"],
        "day": ["01"],
        "time": ["00:00"],
        "data_format": "grib",
        "download_format": "unarchived",
        "area": [90, 81, 89, 82]
        }
    }


# - TO BE IMPLEMENTED -
invalid_era5_land_variables = [
    # UNTESTED
    'boundary_layer_height',
    'vertical_integral_of_eastward_water_vapour_flux',
    'vertical_integral_of_northward_water_vapour_flux',
    'vertical_integral_of_divergence_of_cloud_frozen_water_flux',
    'vertical_integral_of_divergence_of_cloud_liquid_water_flux',
    'vertical_integral_of_divergence_of_geopotential_flux',
    'vertical_integral_of_divergence_of_kinetic_energy_flux',
    'vertical_integral_of_divergence_of_mass_flux',
    'vertical_integral_of_divergence_of_moisture_flux',
    'vertical_integral_of_divergence_of_ozone_flux',
    'vertical_integral_of_divergence_of_thermal_energy_flux',
    'vertical_integral_of_divergence_of_total_energy_flux',
    'vertical_integral_of_eastward_cloud_frozen_water_flux',
    'vertical_integral_of_eastward_cloud_liquid_water_flux',
    'vertical_integral_of_eastward_geopotential_flux',
    'vertical_integral_of_eastward_heat_flux',
    'vertical_integral_of_eastward_kinetic_energy_flux',
    'vertical_integral_of_eastward_mass_flux',
    'vertical_integral_of_eastward_ozone_flux',
    'vertical_integral_of_eastward_total_energy_flux',
    'vertical_integral_of_eastward_water_vapour_flux',
    'vertical_integral_of_energy_conversion',
    'vertical_integral_of_kinetic_energy',
    'vertical_integral_of_mass_of_atmosphere',
    'vertical_integral_of_northward_cloud_frozen_water_flux',
    'vertical_integral_of_northward_cloud_liquid_water_flux',
    'vertical_integral_of_northward_geopotential_flux',
    'vertical_integral_of_northward_heat_flux',
    'vertical_integral_of_northward_kinetic_energy_flux',
    'vertical_integral_of_northward_mass_flux',
    'vertical_integral_of_northward_ozone_flux',
    'vertical_integral_of_northward_total_energy_flux',
    'vertical_integral_of_northward_water_vapour_flux',
    'vertical_integral_of_potential_and_internal_energy',
    'vertical_integral_of_potential_internal_and_latent_energy',
    'vertical_integral_of_temperature',
    'vertical_integral_of_thermal_energy',
    'vertical_integral_of_total_energy',
    'geopotential',
    'specific_cloud_ice_water_content',
    'specific_cloud_liquid_water_content',
    'specific_humidity',
    'specific_rain_water_content',
    'specific_snow_water_content',
    'fraction_of_cloud_cover',
    'large_scale_precipitation'
]

invalid_open_meteo_variables = []

# Accepted Values & Mappings
NORMALIZATION_MAP = {
    "data_provider": {
        "cds": "cds",
        "copernicus": "cds",
        "copernicus climate": "cds",
        "copernicus data store": "cds",
        "copernicus climate data store": "cds",
        "era5": "cds",
        "1": "cds",
        "open-meteo": "open-meteo",
        "openmeteo": "open-meteo",
        "om": "open-meteo",
        "open": "open-meteo",
        "2": "open-meteo",

    },
    "era5_dataset_short_name": {
        "era5land": "era5-land",
        "era5-land": "era5-land",
        "land": "era5-land",
        "0.1": "era5-land",     # resolution of the dataset in EPSG:4326
        "1": "era5-land",
        "era5-world": "era5-world",
        "era5_world": "era5-world",
        "world": "era5-world",
        "era5": "era5-world",
        "0.25": "era5-world",   # resolution of the dataset in EPSG:4326
        "2" : "era5-world",
    },
    "open_meteo_dataset_short_name": {
        # NOT YET IMPLEMENTED
    },
    "boolean": {
        "yes": True, "y": True, "1": True, "true": True, "t": True, "on": True,
        "no": False, "n": False, "0": False, "false": False, "f": False, "off": False
    },
    "confirmation": {  # for yes/no questions
        "y": "yes", "yes": "yes", "ok": "yes", "sure": "yes", "confirm": "yes",
        "n": "no", "no": "no", "nah": "no", "never": "no"
    }
}

CDS_DATASETS = {
    "era5-world": {
        "dataset_product_name": "reanalysis-era5-single-levels",
        "product_type": "reanalysis",
        "data_download_format": "grib",
    },
    "era5-land": {
        "dataset_product_name": "reanalysis-era5-land",
        "product_type": "reanalysis",
        "data_download_format": "grib",
    }
}

# ----------------------------------------------
# FUNCTION DEFINITIONS - Miscellaneous Validation and Formatting functions
# ----------------------------------------------

def normalize_input(
        value: str,
        category: str
    ) -> str:
    """
    Normalize user input to canonical internal value as defined in NORMALIZATION_MAP.

    Parameters
    ----------
    value : str
        The user input value to normalize.
    category : str
        The category of normalization (e.g., 'data_provider', 'dataset_short_name')

    Returns
    -------
    str
        The normalized value.

    """
    if not isinstance(value, str):
        return value
    v = value.strip().lower()
    return NORMALIZATION_MAP.get(category, {}).get(v, value)


def format_duration(seconds: float) -> str:
    """
    Convert seconds to a nice Hh Mm Ss string (with decimal seconds).

    Parameters
    ----------
    seconds : float
        Duration in seconds.

    Returns
    -------
        str: Formatted duration string.
    """
    seconds = max(0, seconds)

    hours = int(seconds // 3600)
    days = int(hours // 24)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60  # keep remainder as float

    if days > 0:
        hours = hours % 24
        return f"{days}d {hours}h {minutes}m {secs:.2f}s"
    if hours > 0:
        return f"{hours}h {minutes}m {secs:.2f}s"
    elif minutes > 0:
        return f"{minutes}m {secs:.2f}s"
    else:
        return f"{secs:.5f}s"


def format_coordinates_nwse(boundaries: List[float]) -> str:

    """
    Extracts and formats coordinates as integers in N-W-S-E order
    Used for compact representation in filenames.

    Parameters
    ----------
    boundaries : list
        List of boundaries in the order [north, west, south, east]
    Returns
    -------
        str: Formatted string in the format 'N{north}W{west}S{south}E{east}'
    """
    n, w, s, e = boundaries
    # compact string for filenames
    return f"N{int(n)}W{int(w)}S{int(s)}E{int(e)}"


def month_days(
        year: int,
        month: int
        ) -> List[str]:
    """
    Get list of days in a month formatted as two-digit strings.

    Parameters
    ----------
    year : int
        Year of interest.
    month : int
        Month of interest.

    Returns
    -------
    List[str]
        List of days in the month as two-digit strings.
    """
    last = calendar.monthrange(year, month)[1]
    return [f"{d:02d}" for d in range(1, last + 1)]


# ----------------------------------------------
# FUNCTION DEFINITIONS - Prompt specific validation functions
# ----------------------------------------------


# 1 - DATA PROVIDER (data_provider)
def validate_data_provider(provider: str) -> bool:
    """
    Ensure dataprovider is recognized and implemented.

    Parameters
    ----------
    provider : str
        Name of the data provider.
    Returns
    -------
        bool: True if valid, False otherwise.
    """
    if provider not in ("cds", "open-meteo"):
        return False
    return True


# 2 - DATASET NAME (dataset_short_name)
def validate_dataset_short_name(
        dataset_short_name: str,
        provider: str
        ) -> bool:
    """
    Check dataset compatibility with provider.

    Parameters
    ----------
    dataset_short_name : str
        Dataset short name.
    provider : str
        Name of the data provider.

    Returns
    -------
    bool
        True if valid, False otherwise.
    """
    if provider == "cds":
        return dataset_short_name in CDS_DATASETS
    if provider == "open-meteo":
        raise NotImplementedError("Open-Meteo dataset validation not yet implemented.")
    log_msg(f"Warning: Unknown provider '{provider}'.")
    return False


# 3 & 4 - API URL (api_url) and API KEY (api_key)
def validate_cds_api_key(
        url: str,
        key: str,
        *,
        logger=None,
        echo_console: bool = False
        ) -> cdsapi.Client | None:
    """
    Validate CDS API credentials by attempting to initialize a cdsapi.Client.

    Parameters
    ----------
    url : str
        CDS API URL.
    key : str
        CDS API key.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    echo_console : bool, optional
        Whether to echo messages to console, by default False.

    Returns
    -------
    cdsapi.Client | None
        Authenticated client if successful, otherwise None.
    """

    if logger:
        log_msg("Testing CDS API connection with provided credentials...", logger, level="info")

    # 1) Initialize client
    try:
        client = cdsapi.Client(url=url, key=key, quiet=True, timeout=30)
    except Exception as e:
        if logger:
            log_msg(f"\tFailed to initialize CDS client: {e}", logger, level="warning")
        return None

    # 2) Probe using the predefined payload (normalize keys minimally)
    #    Expecting a dict like: test_payload = {"dataset": "...", "request": {...}}
    try:
        dataset = test_payload["dataset"]
        request = dict(test_payload["request"])  # shallow copy so we can tweak keys safely

        # product_type must be a string
        if isinstance(request.get("product_type"), list) and request["product_type"]:
            request["product_type"] = request["product_type"][0]

        # -------------------------------------------------------------------
        tmp_path = Path(tempfile.gettempdir()) / f"cds_probe_{os.getpid()}_{int(datetime.now().timestamp())}.grib"

        if logger:
            log_msg("\tProbing ERA5 permissions with a minimal retrieve...", logger)
            request_items = ""
            for k, v in request.items():
                request_items += f"\n\t   {k}: {v}"
            log_msg(f"\tRequest details: dataset='{dataset}' {request_items}", logger)

        client.retrieve(dataset, request, target=str(tmp_path))

        if logger:
            log_msg("\tPermission probe succeeded.\n", logger)
        return client

    except Exception as e:
        msg = str(e)
        if logger:
            log_msg(f"\tAuthentication/probe failed: {msg}\n", logger, level="warning")
            if "401" in msg or "Unauthorized" in msg or "operation not allowed" in msg:
                log_msg(
                    f"\tCDS returned 401/Unauthorized. This usually means you haven’t accepted the "
                    f"licence for '{test_payload.get('dataset','(unknown)')}'. Please log into the CDS website and accept it.\n",
                    logger,
                    level="warning",
                )
        return None
    finally:
        # Cleanup
        try:
            if 'tmp_path' in locals() and tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass

# 5 - SAVE DIRECTORY (save_dir)
def validate_directory(path: str) -> bool:
    """
    Check if path exists or can be created.

    Parameters
    ----------
    path : str
        Directory path to validate.

    Returns
    -------
    bool
        True if path exists or was created successfully, False otherwise.
    """
    p = Path(path)
    if p.exists():
        return True
    try:
        p.mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


# 6 & 7 - START & END DATE (start_date, end_date)
def validate_date(
        value: str,
        allow_month_only: bool = False
        ) -> bool:
    """
    Validate date format as YYYY-MM-DD or optionally YYYY-MM.

    Parameters
    ----------
    value : str
        Date string to validate.
    allow_month_only : bool, optional
        If True, also accept YYYY-MM format, by default False.

    Returns
    -------
    bool
        True if valid, False otherwise.
    """
    try:
        # Try full date format first
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        if allow_month_only:
            try:
                # Try year-month format
                datetime.strptime(value, "%Y-%m")
                return True
            except ValueError:
                log_msg(f"Invalid date format '{value}'. Expected YYYY-MM-DD or YYYY-MM.\n")
                return False
        return False


# 6 & 7 - START & END DATE (start_date, end_date)
def parse_date_with_defaults(
        date_str: str,
        default_to_month_end: bool = False
        ) -> tuple[datetime, str]:
    """
    Parse date string and apply defaults for incomplete dates.

    Parameters
    ----------
    date_str : str
        Date string in format YYYY-MM-DD or YYYY-MM.
    default_to_month_end : bool, optional
        If True and date is YYYY-MM format, default to last day of month.
        If False and date is YYYY-MM format, default to first day of month.
        By default False.

    Returns
    -------
    tuple[datetime, str]
        Tuple of (parsed datetime object, ISO format string YYYY-MM-DD)

    Raises
    ------
    ValueError
        If date string is invalid.
    """
    if len(date_str) == 7:  # YYYY-MM format
        year, month = date_str.split('-')
        year, month = int(year), int(month)

        if default_to_month_end:
            # Get last day of month
            last_day = calendar.monthrange(year, month)[1]
            date_str_full = f"{year}-{month:02d}-{last_day:02d}"
        else:
            # Default to first day
            date_str_full = f"{year}-{month:02d}-01"

        dt = datetime.strptime(date_str_full, "%Y-%m-%d")
        return dt, date_str_full

    elif len(date_str) == 10:  # YYYY-MM-DD format
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt, date_str

    else:
        raise ValueError(f"Invalid date format '{date_str}'. Expected YYYY-MM-DD or YYYY-MM.")


# 7 - END DATE (end_date)
def clamp_era5_available_end_date(end: datetime) -> datetime:
    """
    Clamp end date to ERA5 data availability boundary (8 days ago).

    Parameters
    ----------
    end : datetime
        Desired end date.

    Returns
    -------
        datetime: Clamped end date.

    NOTES: ERA5 data is available up to 8 days prior to the current date.
    8-day lag is used to ensure data availability.

    """
    EIGHT_DAY_LAG = 8
    upper = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=EIGHT_DAY_LAG)
    if end > upper:
        log_msg(f"Adjusting end date from {end.date()} to data availability boundary {upper.date()} (−{EIGHT_DAY_LAG} days).")
        return upper
    return end


# 8 - REGION BOUNDS (region_bounds: north, west, south, east)
def validate_coordinates(
        north: int | float,
        west: int | float,
        south: int | float,
        east: int | float,
        ) -> bool:
    """
    Ensure coordinates are within realistic bounds.

    Parameters
    ----------
    north : int | float
        Northern latitude boundary.
    west : int | float
        Western longitude boundary.
    south : int | float
        Southern latitude boundary.
    east : int | float
        Eastern longitude boundary.

    Returns
    -------
    bool
        True if coordinates are valid, False otherwise.
    """
    return all([
        -90 <= south <= 90,
        -90 <= north <= 90,
        -180 <= west <= 180,
        -180 <= east <= 180,
        north > south
    ])


# 9 - VARIABLES (variables)
def validate_variables(
        variable_list: list[str],
        variable_restrictions: list[str],
        restriction_allow: bool = False
        ) -> bool:
    """
    Ensure user-specified variables are available for this dataset.

    Parameters
    ----------
    variable_list : list[str]
        List of variable names to validate.
    variable_restrictions : list[str]
        List of variables that are either allowed or disallowed.
    restriction_allow : bool
        If True, variable_restrictions is an allowlist (i.e. in). If False, it's a denylist
        (i.e. not in)

    Returns
    -------
    bool
        True if all variables are valid, False otherwise.
    """
    if not variable_list:
        return False

    # Normalize for case consistency
    variables = [v.lower().strip() for v in variable_list]
    restrictions = [r.lower().strip() for r in variable_restrictions]

    if restriction_allow:
        return all(v in restrictions for v in variables)
    else:
        return all(v not in restrictions for v in variables)


# 10 - EXISTING FILE ACTION (existing_file_action)
def validate_existing_file_action(
        session: Any,
        *,
        allow_prompts: bool,
        logger,
        echo_console: bool = False
        ) -> str:
    """
    Normalize existing_file_action for the current run-mode.
    - If 'case_by_case' is set but prompts are not allowed (automatic mode),
      coerce to 'skip_all' and warn.

    Parameters
    ----------
    session : Any
        Current session state.
    allow_prompts : bool
        Whether prompts are allowed (i.e., interactive mode).
    logger : logging.Logger
        Logger for logging messages.
    echo_console : bool
        Whether to echo messages to console.

    Returns
    -------
    str
        Normalized existing_file_action policy.
    """
    policy = session.get("existing_file_action") or "case_by_case"
    allowed = {"overwrite_all", "skip_all", "case_by_case"}

    if policy not in allowed:
        if allow_prompts:
            # treat as case-by-case if we can prompt
            log_msg(
                f"Unrecognized existing_file_action='{policy}'; treating as 'case_by_case' due to interactive mode.",
                logger, level="warning", echo_console=echo_console
            )
            return "case_by_case"
        else:
            # automatic: force skip_all
            log_msg(
                f"Unrecognized existing_file_action='{policy}'; coercing to 'skip_all' for automatic mode.",
                logger, level="warning", echo_console=echo_console
            )
            session.set("existing_file_action", "skip_all")
            return "skip_all"

    if policy == "case_by_case" and not allow_prompts:
        log_msg(
            "existing_file_action='case_by_case' is not supported without prompts; "
            "coercing to 'skip_all' for automatic mode.",
            logger, level="warning", echo_console=echo_console
        )
        session.set("existing_file_action", "skip_all")
        return "skip_all"

    return policy


# ----------------------------------------------
# CONFIG VALIDATION (shared + provider-specific)
# ----------------------------------------------

def _require_keys(
        config: dict,
        keys: list[str]
        ) -> None:
    """
    Ensure required keys are present in config.

    Parameters
    ----------
    config : dict
        Configuration dictionary.
    keys : list[str]
        List of required keys.

    Raises
    ------
    ValueError
        If any required keys are missing.

    Returns
    -------
    None

    """
    missing = [k for k in keys if k not in config]
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")


def validate_config(
        config: dict,
        *,
        logger=None,
        run_mode: str = "automatic",
        echo_console: bool = False,
        live_auth_check: bool = False,
        ) -> None:
    """
    Entry point. Validates common shape then dispatches to provider-specific validator.

    Parameters
    ----------
    config : dict
        Configuration dictionary.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "automatic".
    echo_console : bool, optional
        Whether to echo messages to console, by default False.
    live_auth_check : bool, optional
        Whether to perform live authentication checks (e.g., CDS API), by default False.

    Returns
    -------
    None
    """
    _validate_common(config, logger=logger, run_mode=run_mode, echo_console=echo_console)

    provider = config["data_provider"]
    if provider == "cds":
        _validate_cds(config, logger=logger, run_mode=run_mode, echo_console=echo_console, live_auth_check=live_auth_check)
    elif provider == "open-meteo":
        _validate_open_meteo(config, logger=logger, run_mode=run_mode, echo_console=echo_console)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def _validate_common(
        config: dict,
        *,
        logger=None,
        run_mode="automatic",
        echo_console=False
        ) -> None:
    """
    Validate provider-agnostic config fields.

    Parameters
    ----------
    config : dict
        Configuration dictionary.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "automatic".
    echo_console : bool, optional
        Whether to echo messages to console, by default False.

    Returns
    -------
    None
    """
    # Required keys that are provider-agnostic
    _require_keys(config, [
        "data_provider",
        "dataset_short_name",
        "save_dir",
        "start_date",
        "end_date",
        "region_bounds",
        "variables",
        "existing_file_action",
        "retry_settings",
        "parallel_settings",
    ])

    # Provider + dataset
    if not validate_data_provider(config["data_provider"]):
        raise ValueError("Invalid data provider")
    if not validate_dataset_short_name(config["dataset_short_name"], config["data_provider"]):
        raise ValueError("Invalid dataset short name")

    # Save dir
    p = Path(config["save_dir"]).expanduser()
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ValueError(f"Cannot create/access save_dir '{p}': {e}")
    config["save_dir"] = str(p)

    # Dates (normalize to YYYY-MM-DD; end > start; CDS clamping handled later)
    s_raw, e_raw = config["start_date"], config["end_date"]
    if not validate_date(s_raw, allow_month_only=True):
        raise ValueError("Invalid start_date format; use YYYY-MM-DD or YYYY-MM")
    if not validate_date(e_raw, allow_month_only=True):
        raise ValueError("Invalid end_date format; use YYYY-MM-DD or YYYY-MM")
    s_dt, s_iso = parse_date_with_defaults(s_raw, default_to_month_end=False)
    e_dt, e_iso = parse_date_with_defaults(e_raw, default_to_month_end=True)
    if e_dt <= s_dt:
        raise ValueError("end_date must be strictly after start_date")
    config["start_date"], config["end_date"] = s_iso, e_iso

    # Region bounds
    rb = config["region_bounds"]
    if (not isinstance(rb, (list, tuple))) or len(rb) != 4:
        raise ValueError("region_bounds must be [north, west, south, east]")
    try:
        n, w, s, e = map(float, rb)
    except Exception:
        raise ValueError("region_bounds entries must be numeric")
    if not validate_coordinates(n, w, s, e):
        raise ValueError("Invalid coordinates: ensure -90≤lat≤90, -180≤lon≤180, and north > south")
    config["region_bounds"] = [n, w, s, e]

    # Variables (dataset-specific rules are enforced in provider validator)
    if not isinstance(config["variables"], list) or not config["variables"]:
        raise ValueError("variables must be a non-empty list")

    # existing_file_action
    efa = str(config.get("existing_file_action", "case_by_case"))
    if efa not in ("overwrite_all", "skip_all", "case_by_case"):
        raise ValueError("existing_file_action must be one of: overwrite_all | skip_all | case_by_case")
    if run_mode == "automatic" and efa == "case_by_case":
        log_msg(
            "Config provided 'case_by_case' in automatic mode; coercing to 'skip_all'.",
            logger, level="warning", echo_console=False
        )
        config["existing_file_action"] = "skip_all"

    # Retry settings
    rs = config["retry_settings"]
    if not isinstance(rs, dict):
        raise ValueError("retry_settings must be a dict")
    max_retries = rs.get("max_retries", 6)
    retry_delay = rs.get("retry_delay_sec", 15)
    if not (isinstance(max_retries, int) and max_retries >= 0):
        raise ValueError("retry_settings.max_retries must be an integer ≥ 0")
    if not (isinstance(retry_delay, int) and retry_delay >= 0):
        raise ValueError("retry_settings.retry_delay_sec must be an integer ≥ 0")
    # Soft caps
    if max_retries > 20:
        log_msg("Capping max_retries at 20.", logger, level="warning", echo_console=echo_console)
        max_retries = 20
    if retry_delay > 3600:
        log_msg("Capping retry_delay_sec at 3600.", logger, level="warning", echo_console=echo_console)
        retry_delay = 3600
    config["retry_settings"] = {"max_retries": max_retries, "retry_delay_sec": retry_delay}

    # Parallel settings
    ps = config["parallel_settings"]
    if not isinstance(ps, dict):
        raise ValueError("parallel_settings must be a dict")
    enabled = bool(ps.get("enabled", False))
    max_conc = ps.get("max_concurrent", 1)
    if not isinstance(max_conc, int):
        raise ValueError("parallel_settings.max_concurrent must be an integer")
    if enabled and max_conc < 1:
        log_msg("parallel_settings.enabled=True but max_concurrent<1; forcing to 1.",
                logger, level="warning", echo_console=echo_console)
        max_conc = 1
    if enabled and max_conc > 8:
        log_msg("Limiting max_concurrent to 8 to avoid throttling.", logger,
                level="warning", echo_console=echo_console)
        max_conc = 8
    config["parallel_settings"] = {"enabled": enabled, "max_concurrent": max_conc}


def _validate_cds(
        config: dict,
        *,
        logger=None,
        run_mode="automatic",
        echo_console=False,
        live_auth_check=False,
        ) -> None:
    """
    CDS-specific validation and normalization.

    Parameters
    ----------
    config : dict
        Configuration dictionary.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "automatic".
    echo_console : bool, optional
        Whether to echo messages to console, by default False.
    live_auth_check : bool, optional
        Whether to perform live authentication checks, by default False.

    Returns
    -------
    None
    """
    # Required keys for CDS
    _require_keys(config, ["api_url", "api_key"])

    # Variables rule (you’re using a deny-list for era5-world today; swap per dataset as needed)
    if not validate_variables(config["variables"], invalid_era5_world_variables, restriction_allow=False):
        raise ValueError("Invalid variables specified for CDS dataset")

    # Clamp ERA5 availability window
    # (Only if you want to clamp at config-time; otherwise you can clamp at runtime)
    from datetime import datetime
    e_dt = datetime.strptime(config["end_date"], "%Y-%m-%d")
    e_clamped = clamp_era5_available_end_date(e_dt)
    if e_clamped.date().isoformat() != config["end_date"]:
        log_msg(
            f"End date clamped from {config['end_date']} to {e_clamped.date().isoformat()} for ERA5 availability.",
            logger, level="warning", echo_console=echo_console
        )
        config["end_date"] = e_clamped.date().isoformat()

    # live auth check (off by default)
    if live_auth_check:
        from weather_data_retrieval.utils.data_validation import validate_cds_api_key
        client = validate_cds_api_key(config["api_url"], config["api_key"], logger=logger, run_mode=run_mode)
        if client is None:
            raise ValueError("CDS authentication failed with provided api_url/api_key")


def _validate_open_meteo(
        config: dict,
        *,
        logger=None,
        run_mode="automatic",
        echo_console=False,
        ) -> None:
    """
    Open-Meteo-specific validation.

    Parameters
    ----------
    config : dict
        Configuration dictionary.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "automatic".
    echo_console : bool, optional
        Whether to echo messages to console, by default False.

    Returns
    -------
    None
    """
    # No api_url/api_key required for Open-Meteo
    # Variables—switch to allowlist or a different rule when you define it
    # For now just ensure it’s non-empty (already done in common)
    pass
