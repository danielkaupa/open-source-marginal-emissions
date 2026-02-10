# packages/weather_data_retrieval/src/weather_data_retrieval/utils/file_management.py

# =============================================================================
# Copyright © {2025} Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# If you did not receive a copy of the GNU Affero General Public License
# along with this program, see <https://www.gnu.org/licenses/>.
# =============================================================================

# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

from __future__ import annotations

import re
import hashlib
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
import math

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from osme_common.paths import data_dir, resolve_under

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

ZIP_MAGIC = b"PK\x03\x04"
GRIB_MAGIC = b"GRIB"

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
    BASELINE_SEC   = 30.0            # small per-request overhead
    UNITS_PER_SEC  = 8_000_000.0     # processing throughput (units -> seconds); lower = more conservative
    SERVER_CAP_Mbps = 400.0          # upper network cap in megabits/sec (≈ 50 MB/s)
    SAFETY_FACTOR  = 5.0             # inflate to capture throttling, retries, etc.

    # Effective MB/s (convert from Mbps → MB/s)
    line_MBps = max(0.5, float(observed_speed_mbps) / 8.0)
    srv_MBps  = max(0.5, SERVER_CAP_Mbps / 8.0)
    eff_MBps  = min(line_MBps, srv_MBps)

    per_file_secs = []
    for (_, _, days_in_month) in months:
        steps = int((24.0 / max(0.0001, timestep_hours)) * days_in_month)

        # processing “units” = grid_cells × steps × vars
        units = grid_cells * steps * n_vars
        processing_sec = BASELINE_SEC + (units / UNITS_PER_SEC)

        # network time based on file size and effective MB/s
        network_sec = file_size_MB / eff_MBps

        per_file_secs.append((processing_sec + network_sec) * SAFETY_FACTOR)

    time_per_file_sec = max(per_file_secs) if per_file_secs else 0.0
    total_time_sec    = sum(per_file_secs)

    return {
        "months": n_files,
        "file_size_MB": round(file_size_MB, 3),
        "total_size_MB": round(total_size_MB, 3),
        "time_per_file_sec": round(time_per_file_sec, 1),
        "total_time_sec": round(number=total_time_sec, ndigits=1),
    }

def expected_save_stem(
        save_dir: str | Path | None,
        filename_base: str,
        year: int,
        month: int,
        ) -> Path:
    """
    Construct canonical save stem (without extension) for monthly data.

    Parameters
    ----------
    save_dir : str | Path | None
        Base directory for saving. If None, defaults to osme_common.paths.data_dir().
    filename_base : str
        Base name without date or extension.
    year, month : int
        Year and month of the file.

    Returns
    -------
    Path
        Resolved path under the proper data directory.
    """
    base = Path(save_dir)
    return base / f"{filename_base}_{year:04d}-{month:02d}"

def expected_save_path(
        save_dir: str | Path | None,
        filename_base: str,
        year: int,
        month: int,
        data_format: str = "grib"
        ) -> Path:
    """
    Construct canonical save path for monthly data.

    Parameters
    ----------
    save_dir : str | Path | None
        Base directory for saving. If None, defaults to osme_common.paths.data_dir().
    filename_base : str
        Base name without date or extension.
    year, month : int
        Year and month of the file.
    data_format : str
        File extension, e.g., 'grib' or 'nc'.

    Returns
    -------
    Path
        Resolved path under the proper data directory.
    """
    return expected_save_stem(save_dir, filename_base, year, month).with_suffix(f".{data_format}")



def is_zip_file(path: Path) -> bool:
    """
    Check if a file is a ZIP archive by reading its magic number.

    Parameters
    ----------
    path : Path
        Path to the file to check.

    Returns
    -------
    bool
        True if the file is a ZIP archive, False otherwise.
    """

    try:
        with path.open("rb") as f:
            return f.read(4) == ZIP_MAGIC
    except Exception:
        return False


def is_grib_file(path: Path) -> bool:
    """
    Check if a file is a GRIB file by reading its magic number.
    GRIB files begin with ASCII bytes 'GRIB'.

    Parameters
    ----------
    path : Path
        Path to the file to check.

    Returns
    -------
    bool
        True if the file is a GRIB file, False otherwise.
    """
    try:
        with path.open("rb") as f:
            return f.read(4) == GRIB_MAGIC
    except Exception:
        return False

def unpack_zip_to_grib(
        zip_path: Path,
        final_grib_path: Path
        ) -> Path:
    """
    Extract a ZIP and move the contained GRIB-like file to final_grib_path.
    If multiple candidates exist, prefer .grib/.grb/.grib2; otherwise take the largest file.

    Parameters
    ----------
    zip_path : Path
        Path to the ZIP file.
    final_grib_path : Path
        Desired final path for the extracted GRIB file.

    Returns
    -------
    Path
        Path to the final GRIB file.

    """
    tmp_dir = zip_path.parent / (zip_path.stem + "_extract_tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmp_dir)

    files = [p for p in tmp_dir.rglob("*") if p.is_file()]
    if not files:
        raise RuntimeError(f"ZIP extracted but contained no files: {zip_path}")

    # Prefer GRIB-like extensions
    preferred_exts = {".grib", ".grb", ".grib2"}
    candidates = [p for p in files if p.suffix.lower() in preferred_exts]

    if len(candidates) == 1:
        chosen = candidates[0]
    elif len(candidates) > 1:
        chosen = max(candidates, key=lambda p: p.stat().st_size)
    else:
        # Fallback: largest file
        chosen = max(files, key=lambda p: p.stat().st_size)

    final_grib_path.parent.mkdir(parents=True, exist_ok=True)
    if final_grib_path.exists():
        final_grib_path.unlink()

    shutil.move(str(chosen), str(final_grib_path))

    shutil.rmtree(tmp_dir, ignore_errors=True)
    return final_grib_path
