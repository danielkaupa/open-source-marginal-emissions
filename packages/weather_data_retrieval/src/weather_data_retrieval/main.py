# packages/weather_data_retrieval/src/weather_data_retrieval/main.py

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


"""
Main entry point for the Weather Data Retrieval CLI.

This script can be run either:
  - Automatically via a configuration file (`--config path/to/config.json`), or
  - Interactively through a guided prompt wizard.

It handles session management, logging setup, and orchestration of
the retrieval workflow defined in `weather_data_retrieval.runner`.

Typically invoked through the CLI command: `osme-weather` or `wdr`.
"""


# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from weather_data_retrieval.io.cli import parse_args, run_prompt_wizard
from weather_data_retrieval.io.config_loader import load_and_validate_config
from weather_data_retrieval.utils.session_management import SessionState
from weather_data_retrieval.runner import run
from weather_data_retrieval.utils.logging import setup_logger, log_msg
from osme_common.paths import data_dir

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------


def main():
    """
    Entry point for the Weather Data Retrieval CLI.

    This function:
      1. Parses CLI arguments or launches the interactive prompt wizard.
      2. Loads or builds a configuration file for weather dataset download.
      3. Initializes logging via `osme_common.paths.data_dir()`.
      4. Executes the main retrieval workflow using `weather_data_retrieval.runner.run`.

    Automatically invoked by the `osme-weather` CLI script.
    """
    args = parse_args()
    session = SessionState()

    run_mode = "automatic" if args.config else "interactive"
    verbose = bool(args.verbose) if run_mode == "automatic" else True  # interactive is always verbose

    # Initialize logger (console handler is attached when interactive or verbose)
    logger = setup_logger(str(data_dir(create=True)), run_mode=run_mode, verbose=verbose)

    try:
        if run_mode == "automatic":
            config = load_and_validate_config(args.config)
            exit_code = run(config, run_mode=run_mode, verbose=verbose, logger=logger)
        else:
            # Wizard handles its own console echo; we still attach console handler via verbose=True above
            completed = run_prompt_wizard(session, logger=logger)
            if not completed:
                return
            config = session.to_dict()
            exit_code = run(config, run_mode=run_mode, verbose=True, logger=logger)

        # No extra print logic here; runner handles final summary echoing

    except Exception as e:
        # Runner also handles exceptions; this is just a fallback
        if logger:
            logger.exception(f"Critical error: {e}")
        else:
            print(f"Critical error: {e}")

if __name__ == "__main__":
    main()