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

import json
import os
from datetime import datetime

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from weather_data_retrieval.sources.cds_era5 import orchestrate_cds_downloads
from weather_data_retrieval.io.cli import run_prompt_wizard

from weather_data_retrieval.utils.session_management import (
    SessionState,
    internet_speedtest,
    map_config_to_session,
)
from weather_data_retrieval.utils.data_validation import (
    format_coordinates_nwse,
    validate_config,
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
    load_and_validate_config,
    load_config
)
from osme_common.paths import data_dir, log_dir, resolve_under


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

    console_handler_active = (run_mode == "interactive") or verbose

    def echo_only_if_no_console_handler(force: bool = False) -> bool:
        # In automatic non-verbose mode, console handler is absent.
        # Return True to echo only selected messages (summary, warnings/errors/exceptions).
        return force and (not console_handler_active)

    save_base = config.get("save_dir")
    if save_base:
        save_path = resolve_under(data_dir(create=True), save_base)
    else:
        save_path = data_dir(create=True)

    if logger is None:
        logger = setup_logger(str(log_dir(create=True)), run_mode=run_mode, verbose=verbose)

    # Header
    log_msg("=" * 60, logger, echo_console=echo_only_if_no_console_handler(False))
    log_msg(f"Starting {run_mode.upper()} run at {datetime.now().isoformat()}",
            logger, echo_console=echo_only_if_no_console_handler(False))
    log_msg("=" * 60, logger, echo_console=echo_only_if_no_console_handler(False))

    try:
        # 1) Validate config
        validate_config(config, logger=logger, run_mode=run_mode)
        log_msg("Configuration validation successful.", logger, echo_console=echo_only_if_no_console_handler(False))

        # 2) Map config → session
        session = SessionState()
        ok, notes = map_config_to_session(config, session, logger=logger)
        for note in notes:
            log_msg(note, logger, echo_console=echo_only_if_no_console_handler(False))
        if not ok:
            log_msg("Config mapping reported blocking issues. Exiting.",
                    logger, level="error", echo_console=echo_only_if_no_console_handler(True))
            create_final_log_file(session, filename_base, logger, delete_original=True, reattach_to_final=True)
            return 1

        # 2b) Automatic mode cannot be case-by-case for existing file policy (already coerced by validate_config)
        # Nothing to do here; messages already logged.

        # 3) Short internet speed test (both modes)
        speed_mbps = internet_speedtest(test_urls=None, max_seconds=10, logger=logger, echo_console=echo_only_if_no_console_handler(False))
        log_msg(f"Detected speed: {speed_mbps:.1f} Mbps", logger, echo_console=echo_only_if_no_console_handler(False))

        dataset_short_name = session.get("dataset_short_name")
        if dataset_short_name == "era5-world":
            grid_res = 0.25
        elif dataset_short_name == "era5-land":
            grid_res = 0.1
        else:
            raise ValueError(f"Unknown dataset_short_name: {dataset_short_name}")
        # 4) Estimate size/time
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
                f"Adjusted total time for parallel downloads: {estimates['total_time_sec']:.1f} sec",
                logger, echo_console=echo_only_if_no_console_handler(False)
            )

        # 5) Filename + hash
        coord_str = format_coordinates_nwse(boundaries=session.get("region_bounds"))
        hash_str = generate_filename_hash(
            dataset_short_name=session.get("dataset_short_name"),
            variables=session.get("variables"),
            boundaries=session.get("region_bounds"),
        )
        filename_base = f"{session.get('dataset_short_name')}_{coord_str}_{hash_str}"

        # 6) Summary (ALWAYS printed in interactive/verbose; printed in non-verbose via echo)
        summary = build_download_summary(session, estimates, speed_mbps)
        log_msg(msg=summary, logger=logger, echo_console=echo_only_if_no_console_handler(force=True))
        log_msg(msg=f"Output base filename: {filename_base}", logger=logger, echo_console=echo_only_if_no_console_handler(True))

        # 7) Downloads
        successful, failed, skipped = [], [], []

        log_msg("\n" + "-" * 60 + "\n\n\nBeginning download process...", logger, echo_console=echo_only_if_no_console_handler(False))
        orchestrate_cds_downloads(
            session=session,
            filename_base=filename_base,
            successful_downloads=successful,
            failed_downloads=failed,
            skipped_downloads=skipped,
            logger=logger,
            echo_console=echo_only_if_no_console_handler(False),  # internal steps won’t echo in non-verbose
            allow_prompts=(run_mode == "interactive"),
        )

        # Final counts — treat as summary (echo in non-verbose)
        log_msg("-" * 60, logger, echo_console=echo_only_if_no_console_handler(True))
        log_msg("Download process completed.", logger, echo_console=echo_only_if_no_console_handler(True))
        log_msg(f"Successful : {len(successful)}", logger, echo_console=echo_only_if_no_console_handler(True))
        log_msg(f"Skipped    : {len(skipped)}", logger, echo_console=echo_only_if_no_console_handler(True))
        log_msg(f"Failed     : {len(failed)}", logger, echo_console=echo_only_if_no_console_handler(True))
        log_msg("-" * 60, logger, echo_console=echo_only_if_no_console_handler(True))

        if failed:
            log_msg("Some downloads failed. Review logs for details.",
                    logger, level="warning", echo_console=echo_only_if_no_console_handler(True))
            create_final_log_file(session, filename_base, logger, delete_original=True, reattach_to_final=True)
            log_msg(msg="\nProgram ended, goodbye.\n\n", logger=logger, echo_console=echo_only_if_no_console_handler(False))
            return 2
        create_final_log_file(session, filename_base, logger, delete_original=True, reattach_to_final=True)
        log_msg(msg="*"*60 + "\nProgram completed, thank you for using this tool. Goodbye!\n" + "*"*60 + "\n\n", logger=logger, echo_console=echo_only_if_no_console_handler(False))


    except Exception as e:
        # Always echo errors in non-verbose mode
        log_msg(f"Run failed with exception: {e}", logger, level="exception", echo_console=echo_only_if_no_console_handler(True))
        coord_str = format_coordinates_nwse(session.get("region_bounds"))
        hash_str = generate_filename_hash(
            dataset_short_name=session.get("dataset_short_name"),
            variables=session.get("variables"),
            boundaries=session.get("region_bounds"),
        )
        filename_base = f"{session.get('dataset_short_name')}_{coord_str}_{hash_str}"
        create_final_log_file(session, filename_base, logger, delete_original=True, reattach_to_final=True)
        log_msg("\nProgram ended, goodbye.\n\n", logger, echo_console=echo_only_if_no_console_handler(True))
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