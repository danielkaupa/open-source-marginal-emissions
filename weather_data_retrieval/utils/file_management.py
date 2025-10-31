# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

# N/A

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------


def generate_filename_hash(
        dataset_short_name: str,
        variables: list[str],
        boundaries: list[float]
        ) -> str:
    """
    Generate a unique hash for the download parameters that will be used to create the filename.

    Parameters
    ----------
    dataset_short_name : str
        The dataset short name (era5-world etc).
    variables : list[str]
        List of variable names.
    boundaries : list[float]
        List of boundaries [north, west, south, east].

    Returns
    -------
        str: A unique hash string representing the download parameters.
    """
    # Create unique string from all parameters
    param_string = f"{dataset_short_name}|{sorted(variables)}|{boundaries}"

    # Generate hash
    hash_object = hashlib.md5(param_string.encode())
    return hash_object.hexdigest()[:12]  # 12 characters


def find_existing_month_file(
        save_dir: Path,
        filename_base: str,
        year: int,
        month: int
        ) -> Optional[Path]:
    """
    Tolerant matcher that finds an existing file for the given month.
    Accepts both `_YYYY-MM.ext` and `_YYYY_MM.ext` patterns and any extension.

    Parameters
    ----------
    save_dir : Path
        Directory where files are saved.
    filename_base : str
        Base filename (without date or extension).
    year : int
        Year of the file.
    month : int
        Month of the file.

    Returns
    -------
    Optional[Path]
        Path to the existing file if found, else None.

    """
    save_dir = Path(save_dir)
    if not save_dir.exists():
        return None

    # Accept dash or underscore between year-month; any extension
    pattern = re.compile(
        rf"^{re.escape(filename_base)}_(?:{year:04d}[-_]{month:02d})\.[A-Za-z0-9]+$"
    )
    for p in save_dir.iterdir():
        if p.is_file() and pattern.match(p.name):
            return p
    return None


def estimate_era5_monthly_file_size(
    variables: list[str],
    area: list[float],
    grid_resolution: float = 0.25,
    timestep_hours: float = 1.0,
    bytes_per_value: float = 4.0,  # typically float32
) -> float:
    """
    Estimate ERA5 GRIB file size (MB) for a monthly dataset.

    Parameters
    ----------
    variables : list[str]
        Variables requested (e.g. ['2m_temperature', 'total_precipitation']).
    area : list[float]
        [north, west, south, east] geographic bounds in degrees.
    grid_resolution : float
        Grid spacing in degrees (default 0.25° for ERA5).
    timestep_hours : float
        Temporal resolution in hours (1 = hourly, 3 = 3-hourly, 6 = 6-hourly, etc.).
    bytes_per_value : float
        Bytes per gridpoint per variable (float32 = 4 bytes).

    Returns
    -------
    float
        Estimated monthly file size in MB.
    """
    if not variables or not area:
        return 0.0

    north, west, south, east = area
    n_vars = len(variables)

    # --- Reference (from empirical files)
    ref_size_MB = 0.509
    ref_vars = 2
    ref_area_deg2 = 3 * 2
    ref_res = 0.25
    ref_timestep_hours = 1.0
    days_per_month = 30

    # --- Compute derived quantities
    # Handle wrap-around longitude
    lon_span = (east - west) if east > west else (360 + east - west)
    lat_span = north - south
    req_area_deg2 = lat_span * lon_span

    # --- Compute scaling factors
    area_factor = req_area_deg2 / ref_area_deg2
    var_factor = n_vars / ref_vars
    res_factor = (ref_res / grid_resolution) ** 2
    timestep_factor = (ref_timestep_hours / timestep_hours)
    time_factor = timestep_factor * (days_per_month / 30)  # normalize to 30 days

    # --- Estimated size (MB)
    estimated_MB = ref_size_MB * var_factor * area_factor * res_factor * time_factor

    # --- Safety floor
    return round(max(estimated_MB, 0.05), 3)  # at least 0.05 MB


def estimate_cds_download(
    variables: list[str],
    area: list[float],
    start_date: str,
    end_date: str,
    observed_speed_mbps: float,
    grid_resolution: float = 0.25,
    timestep_hours: float = 1.0,
    bytes_per_value: float = 4.0,
    overhead_per_request_s: float = 180.0,
    overhead_per_var_s: float = 12.0,
) -> dict:
    """
    Estimate per-file and total download size/time for CDS (ERA5) retrievals,
    using an empirically grounded file size model.

    Parameters
    ----------
    variables : list[str]
        Variables selected (e.g. ['2m_temperature', 'total_precipitation']).
    area : list[float]
        [north, west, south, east] bounds in degrees.
    start_date, end_date : str
        Date range (YYYY-MM-DD).
    observed_speed_mbps : float
        Measured internet speed in megabits per second (Mbps).
    grid_resolution : float, optional
        Grid resolution in degrees (default 0.25°).
    timestep_hours : float, optional
        Temporal resolution in hours (default 1-hourly).
    bytes_per_value : float, optional
        Bytes per stored value (float32 = 4).
    overhead_per_request_s : float, optional
        Fixed CDS request overhead time (queue/prep).
    overhead_per_var_s : float, optional
        Per-variable overhead for CDS throttling/prep.

    Returns
    -------
    dict
        {
          "months": int,
          "file_size_MB": float,
          "total_size_MB": float,
          "time_per_file_sec": float,
          "total_time_sec": float
        }
    """
    if not variables or not area:
        return {
            "months": 0,
            "file_size_MB": 0.0,
            "total_size_MB": 0.0,
            "time_per_file_sec": 0.0,
            "total_time_sec": 0.0,
        }

    # --- Compute number of months
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    months = (end.year - start.year) * 12 + (end.month - start.month) + 1

    # --- Estimate per-month file size using the new empirical function
    file_size_MB = estimate_era5_monthly_file_size(
        variables=variables,
        area=area,
        grid_resolution=grid_resolution,
        timestep_hours=timestep_hours,
        bytes_per_value=bytes_per_value,
    )

    total_size_MB = file_size_MB * months

    # --- Compute transfer rates (convert Mbps → MB/s)
    download_speed_MBps = max(observed_speed_mbps, 1.0) / 8.0  # Avoid zero/negatives

    # --- Per-file download time
    time_per_file_s = (
        (file_size_MB / download_speed_MBps)
        + overhead_per_request_s
        + (len(variables) * overhead_per_var_s)
    )

    total_time_s = time_per_file_s * months

    return {
        "months": months,
        "file_size_MB": round(file_size_MB, 3),
        "total_size_MB": round(total_size_MB, 3),
        "time_per_file_sec": round(time_per_file_s, 1),
        "total_time_sec": round(total_time_s, 1),
    }


# def expected_save_path(
#         save_dir: Path,
#         filename_base: str,
#         year: int,
#         month: int,
#         data_format: str = "grib"
#         ) -> Path:
#     """
#     Single source of truth for how monthly files are named & where they live.
#     Format: {filename_base}_{YYYY}-{MM}.{ext}
#     """
#     return Path(save_dir) / f"{filename_base}_{year:04d}-{month:02d}.{data_format}"