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

from weather_data_retrieval.utils.session_management import SessionState
from weather_data_retrieval.utils.data_validation import format_duration

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------


def build_download_summary(session: SessionState,
                           estimates: dict,
                           speed_mbps: float) -> str:
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
        f"\n" + "="* 40 +
        f"\nDownload Request Summary\n" + "="* 40 + "\n"
        f"Provider: {session.get('data_provider').upper()}\n"
        f"Dataset: {session.get('dataset_short_name')}\n"
        f"Dates: {session.get('start_date')} → {session.get('end_date')}\n"
        f"Area: {session.get('region_bounds')}\n"
        f"Variables: {session.get('variables')}\n"
        f"Save Directory: {session.get('save_dir')}\n"
        f"Retries: {session.get('retry_settings')}\n"
        f"Parallelisation: {session.get('parallel_settings')}\n\n"
        f"----------------------------------------\n\n"
        f"Estimated number of monthly files: {estimates['months']}\n"
        f"Estimated size per file: {estimates['file_size_MB']:.1f} MB\n"
        f"Estimated total size: {estimates['total_size_MB']:.1f} MB\n\n"
        f"Measured connection speed: {speed_mbps:.4f} Mbps\n\n"
        f"Estimated maximum time per file: {format_duration(estimates['time_per_file_sec'])}\n"
        f"Estimated maximum total time: {format_duration(estimates['total_time_sec'])}\n"
    )
    return summary


def setup_logger(
        save_dir: str,
        run_mode: str = "interactive",
        verbose: bool = True
        ) -> logging.Logger:
    """
    Mode: "interactive" (console + file) or "automatic" (file only)

    Parameters
    ----------
    save_dir : str
        Directory to save log files.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "interactive".
    verbose : bool, optional
        Whether to also echo log messages to console in automatic mode, by default True.

    Returns
    -------
    logging.Logger
        Configured logger instance.

    """
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = Path(save_dir) / f"run_{run_mode}_{timestamp}.log"

    logger = logging.getLogger("weather_retrieval")
    logger.setLevel(logging.INFO)

    # Clear old handlers safely
    if logger.hasHandlers():
        for h in list(logger.handlers):
            logger.removeHandler(h)

    # File handler
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(fh)

    # Console handler only for interactive or verbose automatic
    if run_mode == "interactive" or verbose:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(ch)

    logger.info(f"Logging initialized at {log_path}")
    return logger


def log_msg(
        msg: str,
        logger,
        *,
        level: str = "info",
        echo_console: bool = False
        ) -> None:
    """
    Unified logging utility.
    - Always logs to file.
    - Echo to console (via tqdm.write) only in interactive mode.

    Parameters
    ----------
    msg : str
        Message to log.
    logger : logging.Logger
        Logger instance.
    level : str, optional
        Logging level: 'info', 'warning', 'error', 'exception', by default "info".
    echo_console : bool, optional
        Whether to also echo to console, by default False.

    Returns
    -------
    None

    """
    if not logger:
        raise ValueError("Logger instance must be provided to log_msg().")

    log_fn = getattr(logger, level, logger.info)
    log_fn(msg)

    if echo_console:
        tqdm.write(msg)