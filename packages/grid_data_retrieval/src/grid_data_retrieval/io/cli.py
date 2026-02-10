# packages/grid_data_retrieval/src/grid_data_retrieval/io/cli.py

# =============================================================================
# Copyright © {2025} Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Command-Line Interface
======================

CLI for grid data retrieval (fetching only).

Data processing should be done via the data_cleaning_and_joining module.
"""

# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

import argparse
import sys

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from grid_data_retrieval.io.config_loader import load_config
from grid_data_retrieval.runner import run_grid_retrieval
from grid_data_retrieval.utils.logging import setup_logger, log_msg
from osme_common.paths import log_dir

# ----------------------------------------------
# DEFAULTS
# ----------------------------------------------

DEFAULT_START_DATE = "2018-11-21 00:00:00"
DEFAULT_END_DATE = "2019-01-31 23:55:00"
DEFAULT_API_URL = "https://32u36xakx6.execute-api.us-east-2.amazonaws.com/v4/get-merit-data"


# ----------------------------------------------
# ARGUMENT PARSING
# ----------------------------------------------


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Grid Data Retrieval - Fetch electricity grid data from APIs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using configuration file
  osme-grid-fetch --config configs/grid/my_config.json

  # Using command-line arguments
  osme-grid-fetch --start-date "2020-01-01 00:00:00" --end-date "2020-12-31 23:55:00"

  # Re-download existing files
  osme-grid-fetch --config my_config.json --overwrite-existing

  # Verbose mode
  osme-grid-fetch --config configs/grid/my_config.json --verbose

Note: This command only FETCHES data. For processing (resampling, timezone
conversion, gap-filling), use the data_cleaning_and_joining module.
        """
    )

    # Config file or manual parameters
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to JSON configuration file. If provided, other arguments are ignored.",
    )

    # Manual parameters (used if --config not provided)
    parser.add_argument(
        "--start-date",
        type=str,
        default=DEFAULT_START_DATE,
        help='Start date (format: "YYYY-MM-DD HH:MM:SS").',
    )

    parser.add_argument(
        "--end-date",
        type=str,
        default=DEFAULT_END_DATE,
        help='End date (format: "YYYY-MM-DD HH:MM:SS").',
    )

    parser.add_argument(
        "--api-url",
        type=str,
        default=DEFAULT_API_URL,
        help="API URL for grid data retrieval.",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help='Output directory for data files (default: data/grid_data/raw/).',
    )

    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        dest="overwrite_existing",
        help="Overwrite existing files if they already exist (default: skip existing).",
    )

    parser.add_argument(
        "--no-combine",
        action="store_false",
        dest="combine_files",
        help="Don't combine monthly files into single dataset (default: combine files).",
    )

    # Verbosity
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose console output.",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress console output (logs still written to file).",
    )

    # Set defaults for boolean flags
    parser.set_defaults(overwrite_existing=False, combine_files=True)

    return parser.parse_args()


# ----------------------------------------------
# MAIN CLI ENTRY
# ----------------------------------------------


def main():
    """
    Main entry point for the grid data retrieval CLI.

    This function:
      1. Parses CLI arguments or loads configuration file.
      2. Initializes logging.
      3. Executes the grid data fetching.

    Automatically invoked by the `osme-grid-fetch` CLI script.
    """
    args = parse_args()

    # Determine verbosity
    if args.quiet:
        verbose = False
    elif args.verbose:
        verbose = True
    else:
        # Default: verbose if interactive, quiet if config
        verbose = args.config is None

    # Initialize logger
    package_log_dir = log_dir(create=True) / "grid_data_retrieval"
    logger = setup_logger(str(package_log_dir), verbose=verbose)

    try:
        # Load configuration
        if args.config:
            log_msg(f"Loading configuration from: {args.config}", logger, echo_console=verbose, force=True)
            config = load_config(args.config)
        else:
            # Build config from CLI arguments
            config = {
                "start_date": args.start_date,
                "end_date": args.end_date,
                "api_url": args.api_url,
                "output_dir": args.output_dir,
                "overwrite_existing": args.overwrite_existing,  # Default False, --overwrite-existing sets to True
                "combine_files": args.combine_files,  # Default True, --no-combine sets to False
            }

        # Run retrieval
        exit_code = run_grid_retrieval(
            config=config,
            logger=logger,
            verbose=verbose,
        )

        sys.exit(exit_code)

    except Exception as e:
        log_msg(f"Critical error: {e}", logger, level="exception", echo_console=True, force=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
