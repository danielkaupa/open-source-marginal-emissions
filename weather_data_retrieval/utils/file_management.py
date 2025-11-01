# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional
import math

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
        overhead_per_request_s: float = 180.0,      # ignored but kept for signature consistency
        overhead_per_var_s: float = 12.0,       # ignored but kept for signature consistency
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
    if not variables or not area or not start_date or not end_date:
        return {
            "months": 0,
            "file_size_MB": 0.0,
            "total_size_MB": 0.0,
            "time_per_file_sec": 0.0,
            "total_time_sec": 0.0,
        }

    # ---------- month list (inclusive) ----------
    s = datetime.strptime(start_date, "%Y-%m-%d")
    e = datetime.strptime(end_date, "%Y-%m-%d")
    months = []
    y, m = s.year, s.month
    while (y < e.year) or (y == e.year and m <= e.month):
        # days in this month
        if m == 12:
            next_first = datetime(y + 1, 1, 1)
        else:
            next_first = datetime(y, m + 1, 1)
        this_first = datetime(y, m, 1)
        dim = (next_first - this_first).days
        months.append((y, m, dim))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1

    n_files = len(months)
    n_vars = max(1, len(variables))

    # ---------- area → grid cells ----------
    north, west, south, east = map(float, area)
    # handle wrap-around longitude
    lon_span = (east - west) if east > west else (360.0 + east - west)
    lat_span = max(0.0, north - south)
    lat_cells = max(1, int(math.ceil(lat_span / grid_resolution)))
    lon_cells = max(1, int(math.ceil(lon_span / grid_resolution)))
    grid_cells = lat_cells * lon_cells

    # ---------- file sizes (use your existing estimator for MB) ----------
    file_size_MB = estimate_era5_monthly_file_size(
        variables=variables,
        area=area,
        grid_resolution=grid_resolution,
        timestep_hours=timestep_hours,
        bytes_per_value=bytes_per_value,
    )
    total_size_MB = file_size_MB * n_files

    # ---------- timing model constants (tune if you like) ----------
    BASELINE_SEC   = 8.0        # small per-request overhead
    UNITS_PER_SEC  = 8000.0     # processing throughput (units -> seconds); lower = more conservative
    SERVER_CAP_MBPS = 80.0      # effective server-side cap (≈ 10 MB/s)
    SAFETY_FACTOR  = 1.25       # pad for variability

    # effective MB/s (line vs server)
    line_MBps = max(0.5, float(observed_speed_mbps) / 8.0)
    srv_MBps  = max(0.5, SERVER_CAP_MBPS / 8.0)
    eff_MBps  = min(line_MBps, srv_MBps)

    per_file_secs = []
    for (_, _, days_in_month) in months:
        # how many time steps in this month
        steps = int((24.0 / max(0.0001, timestep_hours)) * days_in_month)

        # processing “units” = grid_cells × steps × vars
        units = grid_cells * steps * n_vars
        processing_sec = BASELINE_SEC + (units / UNITS_PER_SEC)

        # network time from your size model
        network_sec = file_size_MB / eff_MBps

        per_file_secs.append((processing_sec + network_sec) * SAFETY_FACTOR)

    time_per_file_sec = max(per_file_secs) if per_file_secs else 0.0
    total_time_sec    = sum(per_file_secs)

    return {
        "months": n_files,
        "file_size_MB": round(file_size_MB, 3),
        "total_size_MB": round(total_size_MB, 3),
        "time_per_file_sec": round(time_per_file_sec, 1),
        "total_time_sec": round(total_time_sec, 1),
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