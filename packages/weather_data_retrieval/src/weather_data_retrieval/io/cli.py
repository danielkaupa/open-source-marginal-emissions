# packages/weather_data_retrieval/src/weather_data_retrieval/io/cli.py

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

import argparse
import logging

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from weather_data_retrieval.utils.session_management import SessionState
from weather_data_retrieval.io.prompts import (
    prompt_data_provider,
    prompt_dataset_short_name,
    prompt_cds_url,
    prompt_cds_api_key,
    prompt_date_range,
    prompt_coordinates,
    prompt_variables,
    prompt_skip_overwrite_files,
    prompt_parallelisation_settings,
    prompt_retry_settings,
    prompt_continue_confirmation
)
from weather_data_retrieval.utils.data_validation import (
    validate_cds_api_key,
    invalid_era5_world_variables,
    invalid_era5_land_variables,
    # invalid_open_meteo_variables
)
from osme_common.paths import data_dir, resolve_under
from weather_data_retrieval.utils.logging import log_msg


# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

ECHO = True

# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Parameters
    ----------
    None

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """
    p = argparse.ArgumentParser(
        description="ERA5/Open-Meteo downloader — interactive or batch via config file."
    )
    p.add_argument(
        "--config",
        nargs="?",
        default=None,
        help="Path to JSON config file. If provided, runs in non-interactive (automatic) mode."
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Automatic mode only: also echo log messages to console and show a prompt-style transcript (no input)."
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Interactive mode only: suppress console echo (logs still written to file)."
    )

    return p.parse_args()


def run_prompt_wizard(
        session: SessionState,
        logger: logging.Logger = None,
    ) -> bool:
    """
    Drives the interactive prompt flow (no config-source step).
    Returns True if all fields completed; False if user exits.

    Parameters
    ----------
    session : SessionState
        The session state to populate.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.

    Returns
    -------
    bool
        True if completed; False if exited early.
    """

    log_msg("\n\n" + "=" * 60, logger, echo_console=ECHO)
    log_msg("Welcome to the Weather Data Retrieval Prompt Wizard!\n" + "="*60, logger, echo_console=ECHO)
    log_msg("\nPlease follow the prompts to configure your data retrieval settings.\n", logger, echo_console=ECHO)
    log_msg("At any point, you may type:\n   'back' to return to the previous prompt.", logger, echo_console=ECHO)
    log_msg("   'exit' to quit the wizard\n   'Ctrl+C' to stop the program.\n", logger, echo_console=ECHO)
    log_msg("=" * 60 + "\n", logger, echo_console=ECHO)

    while True:
        key = session.first_unfilled_key()
        if key is None:
            return True

        if key == "data_provider":
            res = prompt_data_provider(session, logger=logger, echo_console=ECHO)
            if res == "__EXIT__": return False
            if res == "__BACK__": continue

        elif key == "dataset_short_name":
            provider = session.get("data_provider")
            res = prompt_dataset_short_name(session, provider, logger=logger, echo_console=ECHO)
            if res == "__EXIT__": return False
            if res == "__BACK__":
                session.unset("data_provider")
                continue

        # CDS-specific prompts
        elif session.get("data_provider") == "cds":
            if key == "api_url":
                res_url = prompt_cds_url(session, "https://cds.climate.copernicus.eu/api", logger=logger, echo_console=ECHO)
                if res_url == "__EXIT__": return False
                if res_url == "__BACK__":
                    session.unset("dataset_short_name")
                    continue

            elif key == "api_key":
                res_key = prompt_cds_api_key(session, logger=logger, echo_console=ECHO)
                if res_key == "__EXIT__": return False
                if res_key == "__BACK__":
                    session.unset("api_url")
                    continue

                client = validate_cds_api_key(session.get("api_url"), session.get("api_key"), logger=logger, echo_console=ECHO)
                if client is None:
                    log_msg("Authentication failed. Please re-enter your API details.\n", logger, echo_console=ECHO)
                    session.unset("api_key")
                    session.unset("api_url")
                    continue
                session.set("session_client", client)

        # Open-Meteo-specific prompts
        elif session.get("data_provider") == "open-meteo":
            raise NotImplementedError("Open-Meteo variable validation not yet implemented.")

        elif key == "start_date":
            # This prompt sets BOTH start_date and end_date
            s, e = prompt_date_range(session, logger=logger, echo_console=ECHO)
            if s == "__EXIT__": return False
            if s == "__BACK__":
                session.unset("dataset_short_name")
                continue

        elif key == "end_date":
            # Will already be filled by prompt_date_range; just skip
            continue

        elif key == "region_bounds":
            bounds = prompt_coordinates(session, logger=logger, echo_console=ECHO)
            if bounds == "__EXIT__": return False
            if bounds == "__BACK__":
                session.unset("start_date")
                session.unset("end_date")
                continue

        elif key == "variables":
            if session.get("dataset_short_name") == "era5-world":
                invalid_vars = invalid_era5_world_variables
            elif session.get("dataset_short_name") == "era5-land":
                invalid_vars = invalid_era5_land_variables
            else:
                raise ValueError("Unknown dataset for variable validation.")
            variables = prompt_variables(session, invalid_vars, logger=logger, echo_console=ECHO)
            if variables in ("__EXIT__", "__BACK__"):
                if variables == "__BACK__":
                    session.unset("region_bounds")
                    continue
                return False

        elif key == "existing_file_action":
            efa = prompt_skip_overwrite_files(session, logger=logger, echo_console=ECHO)
            if efa in ("__EXIT__", "__BACK__"):
                if efa == "__BACK__":
                    session.unset("variables")
                    continue
                return False

        elif key == "parallel_settings":
            ps = prompt_parallelisation_settings(session, logger=logger, echo_console=ECHO)
            if ps in ("__EXIT__", "__BACK__"):
                if ps == "__BACK__":
                    session.unset("existing_file_action")
                    continue
                return False

        elif key == "retry_settings":
            rs = prompt_retry_settings(session, logger=logger, echo_console=ECHO)
            if rs in ("__EXIT__", "__BACK__"):
                if rs == "__BACK__":
                    session.unset("parallel_settings")
                    continue
                return False

        elif key == "inputs_confirmed":
            log_msg("\n" + "*" * 60 + "\n" + "*" * 60 + "\n", logger, echo_console=ECHO)
            log_msg("\nPrompting wizard complete. Please review your selections:\n", logger, echo_console=ECHO)
            rs = prompt_continue_confirmation(session=session, logger=logger, echo_console=ECHO)
            if rs in ("__EXIT__", "__BACK__"):
                if rs == "__BACK__":
                    session.unset("parallel_settings")
                    continue
                return False
            session.set("inputs_confirmed", True)
            log_msg("\nSelections confirmed.", logger, echo_console=ECHO)