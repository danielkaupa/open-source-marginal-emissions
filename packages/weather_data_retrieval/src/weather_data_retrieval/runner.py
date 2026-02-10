# packages/weather_data_retrieval/src/weather_data_retrieval/runner.py

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

from pathlib import Path
from datetime import datetime

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from weather_data_retrieval.sources.cds_era5 import orchestrate_cds_downloads

from weather_data_retrieval.utils.session_management import (
    SessionState,
    internet_speedtest,
    map_config_to_session,
)
from weather_data_retrieval.utils.data_validation import (
    format_coordinates_nwse,
    validate_config,
    format_duration,
)
from weather_data_retrieval.utils.file_management import (
    generate_filename_hash,
    estimate_cds_download,
)
from weather_data_retrieval.utils.logging import (
    setup_logger,
    build_download_summary,
    log_msg,
    create_final_log_file,
)
from weather_data_retrieval.io.config_loader import (
    load_config
)
from osme_common.paths import data_dir, log_dir


# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------

def run(
        config: dict,
        run_mode: str = "interactive",
        verbose: bool = True,
        logger=None
        ) -> int:
    """
    Unified orchestration entry point for both interactive and automatic runs.
    Handles validation, logging, estimation, and download orchestration.

    Returns: 0=success, 1=fatal error, 2=some downloads failed.

    Parameters
    ----------
    config : dict
        Configuration dictionary with all required parameters.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "interactive".
    logger : logging.Logger, optional
        Pre-configured logger instance, by default None.

    Returns
    -------
    int
        Exit code: 0=success, 1=fatal error, 2=some downloads failed.
    """
    if logger is None:
        package_log_dir = log_dir(create=True) / "weather_data_retrieval"
        logger = setup_logger(str(package_log_dir), run_mode=run_mode, verbose=verbose)
        log_msg(f"Logging initialized at {package_log_dir}", logger, echo_console=verbose, force=True)
    else:
        log_msg("Using provided logger.", logger, echo_console=verbose, force=True)

    # Header
    log_msg("=" * 60, logger, echo_console=verbose)
    log_msg(f"Starting {run_mode.upper()} run at {datetime.now().isoformat()}",
            logger=logger, echo_console=verbose, force=True)
    log_msg("=" * 60, logger, echo_console=verbose)

    # initialise
    session = None
    filename_base = None

    try:
        # 1) Validate config
        validate_config(config, logger=logger, run_mode=run_mode)
        log_msg("Configuration validation successful.", logger, echo_console=verbose, force=True)

        # 2) Map config → session
        session = SessionState()
        ok, notes = map_config_to_session(config, session, logger=logger, echo_console=verbose)
        for note in notes:
            log_msg(note, logger, echo_console=verbose)
        if not ok:
            log_msg("Config mapping reported blocking issues. Exiting.",
                    logger=logger, level="error", echo_console=verbose, force=True)
            if "filename_base":
                create_final_log_file(session=session, filename_base=filename_base, original_logger=logger, delete_original=True, reattach_to_final=True)
            else:
                log_msg("Skipping final log file creation because filename_base was not defined (run failed early).", logger=logger, echo_console=verbose, force=True)
            return 1

        # 3) Determine save directory (always data/<dataset_short_name>/raw)
        dataset_short_name = session.get("dataset_short_name")
        if not dataset_short_name or not isinstance(dataset_short_name, str):
            raise ValueError("dataset_short_name must be set in session before computing save_path")
        save_path = data_dir(create=True) / str(dataset_short_name) / "raw"
        save_path.mkdir(parents=True, exist_ok=True)

        # 4) Short internet speed test (both modes)
        speed_mbps = internet_speedtest(test_urls=None, max_seconds=10, logger=logger, echo_console=verbose)
        log_msg(f"Detected speed: {speed_mbps:.1f} Mbps", logger, echo_console=verbose)

        dataset_short_name = session.get("dataset_short_name")
        if dataset_short_name == "era5-world":
            grid_res = 0.25
        elif dataset_short_name == "era5-land":
            grid_res = 0.1
        else:
            raise ValueError(f"Unknown dataset_short_name: {dataset_short_name}")
        # 5) Estimate size/time
        estimates = estimate_cds_download(
            variables=session.get("variables"),
            area=session.get("region_bounds"),
            start_date=session.get("start_date"),
            end_date=session.get("end_date"),
            observed_speed_mbps=speed_mbps,
            grid_resolution=grid_res,
        )

        # Adjust for parallelisation — scale total_time_sec only
        parallel_conf = session.get("parallel_settings")
        if parallel_conf and parallel_conf.get("enabled"):
            efficiency_factor = 0.60
            max_conc = max(1, int(parallel_conf["max_concurrent"]))
            estimates["total_time_sec"] = estimates["total_time_sec"] / (max_conc * efficiency_factor)
            log_msg(
                f"Adjusted total time for parallel downloads: {format_duration(estimates['total_time_sec'])}",
                logger, echo_console=verbose
            )

        # 6) Filename + hash
        coord_str = format_coordinates_nwse(boundaries=session.get("region_bounds"))
        hash_str = generate_filename_hash(
            dataset_short_name=session.get("dataset_short_name"),
            variables=session.get("variables"),
            boundaries=session.get("region_bounds"),
        )
        filename_base = f"{session.get('dataset_short_name')}_{coord_str}_{hash_str}"

        # 7) Summary (ALWAYS printed in interactive/verbose; printed in non-verbose via echo)
        summary = build_download_summary(session, estimates, speed_mbps, save_dir=save_path)
        log_msg(msg=summary, logger=logger, echo_console=verbose, force=True)
        log_msg(msg=f"Output base filename: {filename_base}", logger=logger, echo_console=verbose, force=True)

        # 8) Downloads
        successful, failed, skipped = [], [], []

        log_msg("-" * 60 + "\n\n", logger, echo_console=verbose)
        log_msg("Beginning download process...\n\n", logger, echo_console=verbose, force=True)
        log_msg( "-" * 60, logger, echo_console=verbose)

        orchestrate_cds_downloads(
            session=session,
            filename_base=filename_base,
            save_dir=save_path,
            successful_downloads=successful,
            failed_downloads=failed,
            skipped_downloads=skipped,
            logger=logger,
            echo_console=verbose,  # internal steps won’t echo in non-verbose
            allow_prompts=(run_mode == "interactive"),
        )

        # Final counts — treat as summary (echo in non-verbose)
        log_msg("-" * 60, logger, echo_console=verbose, force=True)
        log_msg("Download process completed.", logger, echo_console=verbose, force=True)
        log_msg(f"\tSuccessful : {len(successful)}", logger, echo_console=verbose, force=True)
        log_msg(f"\tSkipped    : {len(skipped)}", logger, echo_console=verbose, force=True)
        log_msg(f"\tFailed     : {len(failed)}", logger, echo_console=verbose, force=True)
        log_msg("-" * 60, logger, echo_console=verbose, force=True)

        if failed:
            log_msg("Some downloads failed. Review logs for details.",
                    logger=logger, level="warning", echo_console=verbose, force=True)
            create_final_log_file(session, filename_base, logger, delete_original=True, reattach_to_final=True)
            log_msg("", logger=logger, echo_console=verbose)
            log_msg(msg="*"*60, logger=logger, echo_console=verbose)
            log_msg(msg="Program ended, goodbye.", logger=logger, echo_console=verbose, force=True)
            log_msg(msg="*"*60 + "\n\n", logger=logger, echo_console=verbose)
            return 2
        create_final_log_file(session, filename_base, logger, delete_original=True, reattach_to_final=True)
        log_msg("", logger=logger, echo_console=verbose)
        log_msg(msg="*"*60, logger=logger, echo_console=verbose)
        log_msg("Program completed, thank you for using this tool. Goodbye!",logger=logger, echo_console=verbose, force=True)
        log_msg(msg="*"*60+ "\n\n", logger=logger, echo_console=verbose)

    except Exception as e:
        # Always echo errors in non-verbose mode
        log_msg(f"Run failed with exception: {e}", logger=logger, level="exception", echo_console=verbose, force=True)
        if session is not None and session.get("region_bounds") and session.get("dataset_short_name"):

            coord_str = format_coordinates_nwse(boundaries=session.get(key="region_bounds"))
            hash_str = generate_filename_hash(
                dataset_short_name=session.get("dataset_short_name"),
                variables=session.get("variables"),
                boundaries=session.get("region_bounds"),
            )
            filename_base = f"{session.get('dataset_short_name')}_{coord_str}_{hash_str}"
            create_final_log_file(session, filename_base, logger, delete_original=True, reattach_to_final=True)
        else:
            create_final_log_file(session=None, filename_base="run_failed_early",  logger=logger, delete_original=True, reattach_to_final=True)
        log_msg("\nProgram ended, goodbye.\n\n", logger=logger, echo_console=verbose, force=True)
        return 1


# ----------------------------------------------------------------------
# HELPER FUNCTIONS
# ----------------------------------------------------------------------


def run_batch_from_config(
        cfg_path: str,
        logger=None
        ) -> int:
    """
    Run automatic batch from a config file.

    Parameters
    ----------
    config : dict
        Configuration dictionary with all required parameters.
    logger : logging.Logger, optional
        Pre-configured logger instance, by default None.

    Returns
    -------
    int
        Exit code: 0=success, 1=fatal error, 2=some downloads failed.
    """
    config = load_config(cfg_path)
    return run(config, run_mode="automatic", verbose=False, logger=logger)