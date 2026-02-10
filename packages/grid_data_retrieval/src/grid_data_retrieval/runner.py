# packages/grid_data_retrieval/src/grid_data_retrieval/runner.py

# =============================================================================
# Copyright © {2025} Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Grid Data Retrieval Runner
===========================

Orchestrates grid data fetching from APIs.

This module handles ONLY data retrieval. Subsequent processing
(gap-filling, resampling, timezone conversion) should be done
via the data_cleaning_and_joining module.
"""

# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

from pathlib import Path
from datetime import datetime

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from grid_data_retrieval.utils.logging import setup_logger, log_msg
from grid_data_retrieval.sources.carbontracker import fetch_monthly_batches, combine_monthly_files
from osme_common.paths import data_dir, log_dir

# ----------------------------------------------
# CONSTANTS
# ----------------------------------------------

DEFAULT_API_URL = "https://32u36xakx6.execute-api.us-east-2.amazonaws.com/v4/get-merit-data"

# Output directory configuration
# These paths are relative to data_dir() from osme_common.paths
# Default structure: data/grid_data/raw/monthly/ and data/grid_data/raw/
OUTPUT_BASE_DIR = "grid_data/raw"      # Base directory for grid data
MONTHLY_SUBDIR = "monthly"              # Subdirectory for monthly files

# ----------------------------------------------
# MAIN RUNNER
# ----------------------------------------------


def run_grid_retrieval(
    config: dict,
    *,
    logger=None,
    verbose: bool = True,
) -> int:
    """
    Execute grid data retrieval from API.

    This function ONLY fetches and combines data. Processing happens elsewhere.

    Parameters
    ----------
    config : dict
        Configuration dictionary containing:
        - start_date : str (YYYY-MM-DD HH:MM:SS)
        - end_date : str (YYYY-MM-DD HH:MM:SS)
        - api_url : str (optional)
        - overwrite_existing : bool (optional, default: True)
        - combine_files : bool (optional, default: True)
    logger : logging.Logger, optional
        Pre-configured logger instance.
    verbose : bool, optional
        Whether to echo logs to console.

    Returns
    -------
    int
        Exit code: 0=success, 1=error.
    """
    # Initialize logger if not provided
    if logger is None:
        package_log_dir = log_dir(create=True) / "grid_data_retrieval"
        logger = setup_logger(str(package_log_dir), verbose=verbose)
        log_msg(f"Logging initialized at {package_log_dir}", logger, echo_console=verbose, force=True)

    log_msg("=" * 60, logger, echo_console=verbose)
    log_msg(f"Starting Grid Data Retrieval at {datetime.now().isoformat()}",
            logger=logger, echo_console=verbose, force=True)
    log_msg("=" * 60, logger, echo_console=verbose)

    try:
        # Extract config
        start_date = config["start_date"]
        end_date = config["end_date"]
        api_url = config.get("api_url", DEFAULT_API_URL)
        overwrite_existing = config.get("overwrite_existing", False)
        combine_files = config.get("combine_files", True)

        # Define output directories
        # Users can override via config["output_dir"], otherwise use defaults from constants above
        if "output_dir" in config and config["output_dir"] is not None:
            base_output_dir = Path(config["output_dir"])
        else:
            # Use constants defined at top of file
            base_output_dir = data_dir(create=True) / OUTPUT_BASE_DIR

        monthly_dir = base_output_dir / MONTHLY_SUBDIR
        combined_dir = base_output_dir

        # Step 1: Fetch monthly batches
        log_msg("\n" + "=" * 60, logger, echo_console=verbose)
        log_msg("Fetching Monthly Batches from API", logger, echo_console=verbose, force=True)
        log_msg("=" * 60, logger, echo_console=verbose)

        monthly_files = fetch_monthly_batches(
            start_date=start_date,
            end_date=end_date,
            api_url=api_url,
            output_dir=monthly_dir,
            overwrite_existing=overwrite_existing,
            logger=logger,
            echo_console=verbose,
        )

        if not monthly_files:
            log_msg("No monthly files to process. Exiting.", logger, level="warning", echo_console=verbose, force=True)
            return 0

        log_msg(f"Fetched {len(monthly_files)} monthly file(s).", logger, echo_console=verbose, force=True)

        # Step 2: Optionally combine monthly files
        if combine_files:
            log_msg("\n" + "=" * 60, logger, echo_console=verbose)
            log_msg("Combining Monthly Files", logger, echo_console=verbose, force=True)
            log_msg("=" * 60, logger, echo_console=verbose)

            combined_path = combine_monthly_files(
                monthly_dir=monthly_dir,
                output_dir=combined_dir,
                logger=logger,
                echo_console=verbose,
            )

            log_msg(f"Combined file created: {combined_path}", logger, echo_console=verbose, force=True)
            final_output = combined_path
        else:
            final_output = monthly_dir

        # Success
        log_msg("\n" + "=" * 60, logger, echo_console=verbose)
        log_msg("Retrieval completed successfully!", logger, echo_console=verbose, force=True)
        log_msg(f"Raw data saved to: {final_output}", logger, echo_console=verbose, force=True)
        log_msg("=" * 60, logger, echo_console=verbose)
        log_msg("\nNext steps:", logger, echo_console=verbose, force=True)
        log_msg("  - Use data_cleaning_and_joining module for processing", logger, echo_console=verbose, force=True)
        log_msg("  - Apply gap-filling, resampling, timezone conversion as needed", logger, echo_console=verbose, force=True)

        return 0

    except Exception as e:
        log_msg(f"Retrieval failed with exception: {e}", logger=logger, level="exception", echo_console=verbose, force=True)
        return 1