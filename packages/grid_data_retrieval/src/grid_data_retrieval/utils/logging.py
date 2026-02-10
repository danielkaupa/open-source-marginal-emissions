# packages/grid_data_retrieval/src/grid_data_retrieval/utils/logging.py

# =============================================================================
# Copyright © {2025} Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Logging Infrastructure
======================

Provides centralized logging for the grid_data_retrieval package.

Reuses patterns from osme_common and weather_data_retrieval for consistency.
"""

# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

import logging
from pathlib import Path
import datetime
from tqdm import tqdm

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from osme_common.paths import log_dir

# ----------------------------------------------
# LOGGER SETUP
# ----------------------------------------------


def setup_logger(
    save_dir: str | None = None,
    verbose: bool = True,
) -> logging.Logger:
    """
    Initialize and return a configured logger.

    Logs are written to <repo_root>/logs/grid_data_retrieval (or $OSME_LOG_DIR/grid_data_retrieval).

    Parameters
    ----------
    save_dir : str or None, optional
        Directory to save log files. If None, defaults to osme_common.paths.log_dir().
    verbose : bool, optional
        Whether to echo logs to console (via console handler).

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """
    # Resolve log directory
    base_dir = Path(save_dir) if save_dir else log_dir(create=True)
    base_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = base_dir / f"grid_retrieval_{timestamp}.log"

    logger = logging.getLogger("grid_retrieval")
    logger.setLevel(logging.DEBUG)

    # Clear old handlers safely
    if logger.hasHandlers():
        for h in list(logger.handlers):
            logger.removeHandler(h)

    # File handler – DEBUG (captures everything)
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(fh)

    logger.info(f"Logging initialized at {log_path}")
    return logger


def log_msg(
    msg: str,
    logger,
    *,
    level: str = "info",
    echo_console: bool = False,
    force: bool = False,
) -> None:
    """
    Unified logging utility.

    - Always logs to file.
    - Optionally echoes to console via tqdm.write (non-blocking).

    Parameters
    ----------
    msg : str
        Message to log.
    logger : logging.Logger
        Logger instance.
    level : str, optional
        Log level: "debug", "info", "warning", "error", "exception".
    echo_console : bool, optional
        Print to console when True.
    force : bool, optional
        Print to console regardless of echo_console (for critical messages).

    Returns
    -------
    None
    """
    if not logger:
        raise ValueError("Logger instance must be provided to log_msg().")

    log_fn = getattr(logger, level, logger.info)
    log_fn(msg)

    if force or echo_console:
        tqdm.write(s=msg)
