# packages/weather_data_retrieval/src/weather_data_retrieval/utils/logging.py

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

import logging
from pathlib import Path
import datetime
import shutil
import os
from typing import Any
from tqdm import tqdm

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from osme_common.paths import log_dir, data_dir, resolve_under

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------

def _format_duration(seconds: float) -> str:
    """
    Format a duration in seconds into a human-readable string.
    Reimplements format_duration from data_validation to avoid circular imports.

    Parameters
    ----------
    seconds : float
        Duration in seconds.
    Returns
    -------
    str
        Formatted duration string.
    """

    seconds = max(0, seconds)
    hours = int(seconds // 3600)
    days = int(hours // 24)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    if days > 0:
        hours = hours % 24
        return f"{days}d {hours}h {minutes}m {secs:.2f}s"
    if hours > 0:
        return f"{hours}h {minutes}m {secs:.2f}s"
    if minutes > 0:
        return f"{minutes}m {secs:.2f}s"
    return f"{secs:.5f}s"


def build_download_summary(
        session: Any,
        estimates: dict,
        speed_mbps: float,
        save_dir: str | Path | None = None) -> str:
    """
    Construct a formatted summary string of the current download configuration.

    Parameters
    ----------
    session : SessionState
        Current session state containing all parameters.
    estimates : dict
        Dictionary containing download size and time estimates.
    speed_mbps : float
        Measured or estimated internet speed in Mbps.

    Returns
    -------
    str
        Nicely formatted summary string for display or logging.
    """
    summary = (
        f"\n" + "="* 60 +
        f"\nDownload Request Summary\n" + "="* 60 + "\n"
        f"Provider: {session.get('data_provider').upper()}\n"
        f"Dataset: {session.get('dataset_short_name')}\n"
        f"Dates: {session.get('start_date')} → {session.get('end_date')}\n"
        f"Area: {session.get('region_bounds')}\n"
        f"Variables: {session.get('variables')}\n"
        f"Save Directory: {save_dir if save_dir is not None else '(auto)'}\n"
        f"Retries: {session.get('retry_settings')}\n"
        f"Parallelisation: {session.get('parallel_settings')}\n\n"
        f"----------------------------------------\n\n"
        f"Estimated number of monthly files: {estimates['months']}\n"
        f"Estimated size per file: {estimates['file_size_MB']:,.1f} MB\n"
        f"Estimated total size: {estimates['total_size_MB']:,.1f} MB\n\n"
        f"Measured connection speed: {speed_mbps:.4f} Mbps\n\n"
        f"Estimated maximum time per file: {_format_duration(estimates['time_per_file_sec'])}\n"
        f"Estimated maximum total time: {_format_duration(estimates['total_time_sec'])}\n"
    )
    return summary


def setup_logger(
        save_dir: str | None = None,
        run_mode: str = "interactive",
        verbose: bool = False
        ) -> logging.Logger:
    """
    Initialize and return a configured logger.

    Logs are written to <repo_root>/logs (or $OSME_LOG_DIR) by default,
    with optional console output in interactive or verbose modes.

    Parameters
    ----------
    save_dir : str or None, optional
        Directory to save log files. If None, defaults to osme_common.paths.log_dir().
    run_mode : str, optional
        Either 'interactive' or 'automatic', by default 'interactive'.
    verbose : bool, optional
        Whether to echo logs to console in automatic mode, by default False.

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """
    # --- Resolve log directory ---
    base_dir = Path(save_dir) if save_dir else log_dir(create=True)
    base_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = base_dir / f"run_{run_mode}_{timestamp}.log"

    logger = logging.getLogger("weather_retrieval")
    # Make sure logger captures everything; handlers will filter
    logger.setLevel(logging.DEBUG)

    # Clear old handlers safely
    if logger.hasHandlers():
        for h in list(logger.handlers):
            logger.removeHandler(h)

    # File handler — DEBUG (captures prompts + everything)
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(fh)

    # # Console handler:
    # # - interactive: always show console at INFO+
    # # - automatic: show console only if verbose=True
    # add_console = (run_mode == "interactive") or (run_mode == "automatic" and verbose)
    # if add_console:
    #     ch = logging.StreamHandler()
    #     ch.setLevel(logging.INFO)   # <- no DEBUG on console, so prompts won't duplicate
    #     ch.setFormatter(logging.Formatter("%(message)s"))
    #     logger.addHandler(ch)

    # logger.info(f"Logging initialized at {log_path}")
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
    - Optionally echoes to console via tqdm.write.

    Parameters
    ----------
    echo_console:
        Print to console when True (used for verbose mode).
    force:
        Print to console regardless of echo_console (used for summaries/errors).
    """
    if not logger:
        raise ValueError("Logger instance must be provided to log_msg().")

    log_fn = getattr(logger, level, logger.info)
    log_fn(msg)

    if force or echo_console:
        tqdm.write(s=msg)



def create_final_log_file(
        session,
        filename_base: str,
        original_logger: logging.Logger,
        *,
        delete_original: bool = True,
        reattach_to_final: bool = True,
        ) -> str | None:
    """
    Create a final log file with the same naming pattern as data files.
    Copies content from the original log file.

    Parameters
    ----------
    session : Any (SessionState)
        Current session state.
    filename_base : str
        Base filename pattern (same as data files).
    original_logger : logging.Logger
        The original logger instance.
    delete_original : bool, optional
        Whether to delete the original log file after creating the final one, by default True.
    reattach_to_final : bool, optional
        Whether to reattach the logger to the final log file, by default True.

    Returns
    -------
    str
        Path to the final log file.
    """
    # 1) locate the current FileHandler
    fh = None
    for h in original_logger.handlers:
        if isinstance(h, logging.FileHandler):
            fh = h
            break

    if fh is None or not hasattr(fh, "baseFilename"):
        # No file handler found
        return None

    original_path = Path(fh.baseFilename)

    # 2) build final path
    log_base = log_dir(create=True) / "weather_data_retrieval"
    log_base.mkdir(parents=True, exist_ok=True)

    start = session.get("start_date")
    end = session.get("end_date")
    retrieved = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")

    final_name = f"{filename_base}_{start}-{end}_retrieved-{retrieved}.log"
    final_path = log_base / final_name
    final_path.parent.mkdir(parents=True, exist_ok=True)

    # 3) flush & close the original handler, detach from logger
    fh.flush()
    fh.close()
    original_logger.removeHandler(fh)

    # 4) copy to final and optionally delete original
    try:
        # If same filesystem, you could also use os.replace to move instead of copy
        shutil.copyfile(original_path, final_path)
        if delete_original:
            try:
                os.remove(original_path)
            except Exception:
                pass
    except Exception as e:
        # Reattach the original handler if something failed so we don't lose logging
        try:
            fh = logging.FileHandler(original_path, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
            original_logger.addHandler(fh)
        except Exception:
            pass
        # Log to console if possible
        original_logger.warning(f"Failed to create final log file: {e}")
        return None

    # 5) optionally attach a new FileHandler pointing at the final file
    if reattach_to_final:
        new_fh = logging.FileHandler(final_path, encoding="utf-8")
        new_fh.setLevel(logging.DEBUG)
        new_fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        original_logger.addHandler(new_fh)

    # 6) log a confirmation (now goes to final file if reattached, and to console in interactive mode)
    try:
        original_logger.info(f"Final log file created: {final_path}")
    except Exception:
        pass

    return str(final_path)