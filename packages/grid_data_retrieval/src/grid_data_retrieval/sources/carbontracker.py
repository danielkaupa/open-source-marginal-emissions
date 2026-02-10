# packages/grid_data_retrieval/src/grid_data_retrieval/sources/carbontracker.py

# =============================================================================
# Copyright © {2026} Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
CarbonTracker Merit API Data Retrieval
=======================================

Fetches grid electricity data from the CarbonTracker Merit API
and saves monthly Parquet files.

Functions
---------
fetch_monthly_batches : Retrieve data for all months in date range
combine_monthly_files : Merge monthly files into single dataset
"""

# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

import json
import time
from pathlib import Path
from datetime import datetime
from dateutil.relativedelta import relativedelta
from urllib.parse import quote as url_escape
from typing import List

import requests
import polars as pl
from tqdm.auto import tqdm

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from grid_data_retrieval.utils.logging import log_msg

# ----------------------------------------------
# CONSTANTS
# ----------------------------------------------

VARIABLES_TO_COLLECT = [
    "thermal_generation",
    "gas_generation",
    "g_co2_per_kwh",
    "hydro_generation",
    "nuclear_generation",
    "renewable_generation",
    "tons_co2",
    "total_generation",
    "tons_co2_per_mwh",
    "demand_met",
    "net_demand",
]

API_DELAY_SECONDS = 5  # Rate limiting


# ----------------------------------------------
# HELPER FUNCTIONS
# ----------------------------------------------


def _month_ranges(start: datetime, end: datetime):
    """
    Generate (month_start, month_end) tuples for each month in the range.

    Parameters
    ----------
    start : datetime
        Start datetime.
    end : datetime
        End datetime.

    Yields
    ------
    tuple[datetime, datetime]
        (month_start, month_end) pairs.
    """
    cur = datetime(start.year, start.month, 1)
    while cur <= end:
        month_start = cur
        next_month = cur + relativedelta(months=1)
        month_end = min(next_month, end)
        yield month_start, month_end
        cur = next_month


def _month_filename(output_dir: Path, month_start: datetime) -> Path:
    """
    Construct filename for monthly grid data.

    Parameters
    ----------
    output_dir : Path
        Directory for output files.
    month_start : datetime
        First day of the month.

    Returns
    -------
    Path
        Full path to output file.
    """
    return output_dir / f"carbontracker_grid-data_{month_start:%Y_%m}.parquet"


# ----------------------------------------------
# MAIN FUNCTIONS
# ----------------------------------------------


def fetch_monthly_batches(
    start_date: str,
    end_date: str,
    api_url: str,
    output_dir: Path | str,
    *,
    overwrite_existing: bool = True,
    logger=None,
    echo_console: bool = True,
) -> List[Path]:
    """
    Fetch grid data from CarbonTracker API in monthly batches.

    Parameters
    ----------
    start_date : str
        Start date in format "YYYY-MM-DD HH:MM:SS".
    end_date : str
        End date in format "YYYY-MM-DD HH:MM:SS".
    api_url : str
        Base URL for the Merit API.
    output_dir : Path or str
        Directory to save monthly Parquet files.
    overwrite_existing : bool, optional
        Whether to overwrite months that already have files.
    logger : logging.Logger, optional
        Logger instance.
    echo_console : bool, optional
        Whether to echo to console.

    Returns
    -------
    List[Path]
        List of paths to fetched/existing monthly files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_dt = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")

    log_msg(f"Fetching monthly batches from {start_dt} → {end_dt}", logger, echo_console=echo_console)
    log_msg(f"API URL: {api_url}", logger, echo_console=echo_console)
    log_msg(f"Output directory: {output_dir}", logger, echo_console=echo_console)

    monthly_files = []
    months = list(_month_ranges(start_dt, end_dt))

    for month_start, month_end in tqdm(months, desc="Fetching monthly data", disable=not echo_console):
        file_path = _month_filename(output_dir, month_start)

        # Skip if exists
        if not overwrite_existing and file_path.exists():
            log_msg(f"Skipping existing: {file_path.name}", logger, echo_console=echo_console)
            monthly_files.append(file_path)
            continue

        # Prepare API request
        ms_str = url_escape(month_start.strftime("%Y-%m-%d %H:%M:%S"), safe=":")
        me_str = url_escape(month_end.strftime("%Y-%m-%d %H:%M:%S"), safe=":")

        url = (
            f"{api_url}"
            f"?start_time={ms_str}"
            f"&end_time={me_str}"
            f"&corrected_values=true"
        )

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            raw_json = json.loads(response.json())

            # Validate response
            if "timeseries_values" not in raw_json:
                log_msg(
                    f"API error for {month_start:%Y-%m}: {raw_json}",
                    logger,
                    level="error",
                    echo_console=echo_console,
                    force=True
                )
                continue

            # Extract data
            values = raw_json["timeseries_values"]
            timestamps = values["timestamps"]

            rows = []
            for j in range(len(timestamps)):
                row = {"timestamp": timestamps[j]}
                for var in VARIABLES_TO_COLLECT:
                    row[var] = values[var][j]
                rows.append(row)

            # Create DataFrame
            df = pl.DataFrame(rows)
            df = df.with_columns(
                pl.col("timestamp").str.strptime(pl.Datetime, format="%Y-%m-%d %H:%M:%S")
            )

            # Save
            df.write_parquet(file_path)
            log_msg(f"Saved: {file_path.name}", logger, echo_console=echo_console)
            monthly_files.append(file_path)

        except requests.exceptions.RequestException as e:
            log_msg(
                f"Request error for {month_start:%Y-%m}: {e}",
                logger,
                level="error",
                echo_console=echo_console,
                force=True
            )
        except Exception as e:
            log_msg(
                f"Unexpected error for {month_start:%Y-%m}: {e}",
                logger,
                level="exception",
                echo_console=echo_console,
                force=True
            )

        # Rate limiting
        time.sleep(API_DELAY_SECONDS)

    return monthly_files


def combine_monthly_files(
    monthly_dir: Path | str,
    output_dir: Path | str,
    *,
    logger=None,
    echo_console: bool = True,
) -> Path:
    """
    Combine all monthly Parquet files into a single dataset.

    Parameters
    ----------
    monthly_dir : Path or str
        Directory containing monthly Parquet files.
    output_dir : Path or str
        Directory for combined output file.
    logger : logging.Logger, optional
        Logger instance.
    echo_console : bool, optional
        Whether to echo to console.

    Returns
    -------
    Path
        Path to the combined output file.
    """
    monthly_dir = Path(monthly_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find monthly files
    files = sorted(monthly_dir.glob("carbontracker_grid-data_*.parquet"))

    if not files:
        raise FileNotFoundError(f"No monthly Parquet files found in {monthly_dir}")

    log_msg(f"Found {len(files)} monthly file(s) to combine.", logger, echo_console=echo_console)

    # Load lazily
    lazy_frames = [pl.scan_parquet(f) for f in files]
    combined_lazy = pl.concat(lazy_frames, how="vertical_relaxed")

    # Get timestamp range for filename
    min_max = combined_lazy.select([
        pl.col("timestamp").min().alias("min_ts"),
        pl.col("timestamp").max().alias("max_ts"),
    ]).collect()

    min_ts = min_max["min_ts"][0]
    max_ts = min_max["max_ts"][0]

    start_str = min_ts.strftime("%Y-%m")
    end_str = max_ts.strftime("%Y-%m")

    # Construct output path
    output_path = output_dir / f"carbontracker_grid-data_{start_str}_{end_str}.parquet"

    log_msg(f"Date range: {min_ts} → {max_ts}", logger, echo_console=echo_console)
    log_msg(f"Writing combined file: {output_path.name}", logger, echo_console=echo_console)

    # Write to Parquet
    combined_lazy.sort("timestamp").sink_parquet(output_path)

    log_msg(f"Combined file created successfully.", logger, echo_console=echo_console, force=True)

    return output_path
