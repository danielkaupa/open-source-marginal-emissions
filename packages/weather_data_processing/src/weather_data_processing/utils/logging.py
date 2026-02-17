# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Logging Infrastructure for Weather Data Processing
===================================================

Provides centralized logging with verbose/non-verbose modes and
integration with tqdm for progress bars.

Key Features
------------
- Dual-mode logging: verbose (all to console) vs quiet (critical only)
- File logging always captures everything at DEBUG level
- tqdm-compatible console output (non-blocking)
- Automatic log directory creation
- Consistent formatting across all modules
"""

from __future__ import annotations

import logging
import datetime
from pathlib import Path
from typing import Optional

from tqdm import tqdm

# Try to import osme_common.paths, fall back to manual resolution
try:
    from osme_common.paths import log_dir as get_log_dir
except ImportError:
    def get_log_dir(create: bool = False) -> Path:
        """Fallback log directory resolution."""
        log_path = Path.home() / ".osme" / "logs"
        if create:
            log_path.mkdir(parents=True, exist_ok=True)
        return log_path


class VerboseLogger:
    """
    Logger wrapper that supports verbose and non-verbose modes.
    
    In verbose mode:
        - Everything logged to file also goes to console
    
    In non-verbose mode:
        - Only messages logged with force=True or level >= WARNING go to console
        - Everything still goes to file
    
    Parameters
    ----------
    name : str
        Logger name (typically module name).
    log_file : Path or None, optional
        Path to log file. If None, auto-generated in log directory.
    verbose : bool, optional
        Whether to echo all logs to console (default True).
    module_name : str, optional
        Module name for the log filename (default "weather_processing").
    
    Attributes
    ----------
    logger : logging.Logger
        Underlying Python logger instance.
    verbose : bool
        Current verbose mode setting.
    """
    
    def __init__(
        self,
        name: str,
        log_file: Optional[Path] = None,
        verbose: bool = True,
        module_name: str = "weather_processing"
    ):
        self.verbose = verbose
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Clear any existing handlers
        if self.logger.hasHandlers():
            for h in list(self.logger.handlers):
                self.logger.removeHandler(h)
        
        # -----------------------------------------------------------------
        # File Handler: Always DEBUG, captures everything
        # -----------------------------------------------------------------
        if log_file is None:
            log_dir = get_log_dir(create=True) / module_name
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = log_dir / f"{name}_{timestamp}.log"
        else:
            log_file = Path(log_file)
            log_file.parent.mkdir(parents=True, exist_ok=True)
        
        fh = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
        )
        self.logger.addHandler(fh)
        
        # -----------------------------------------------------------------
        # Console Handler: Level depends on verbose mode
        # -----------------------------------------------------------------
        # We don't add a console handler here; instead we use tqdm.write
        # in the log_msg method for non-blocking output
        
        self.log_file = log_file
        self.logger.info(f"Logging initialized at {log_file}")
        if verbose:
            self.logger.info("Verbose mode: ALL logs will echo to console")
        else:
            self.logger.info("Quiet mode: Only warnings/errors/forced messages to console")
    
    def debug(self, msg: str, echo_console: bool = False, force: bool = False):
        """Log a DEBUG message."""
        self.log_msg(msg, level="debug", echo_console=echo_console, force=force)
    
    def info(self, msg: str, echo_console: bool = False, force: bool = False):
        """Log an INFO message."""
        self.log_msg(msg, level="info", echo_console=echo_console, force=force)
    
    def warning(self, msg: str, echo_console: bool = True, force: bool = False):
        """Log a WARNING message (defaults to console output)."""
        self.log_msg(msg, level="warning", echo_console=echo_console, force=force)
    
    def error(self, msg: str, echo_console: bool = True, force: bool = True):
        """Log an ERROR message (always to console)."""
        self.log_msg(msg, level="error", echo_console=echo_console, force=force)
    
    def critical(self, msg: str, echo_console: bool = True, force: bool = True):
        """Log a CRITICAL message (always to console)."""
        self.log_msg(msg, level="critical", echo_console=echo_console, force=force)
    
    def log_msg(
        self,
        msg: str,
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
        level : str, optional
            Log level: "debug", "info", "warning", "error", "critical".
        echo_console : bool, optional
            Print to console when True (subject to verbose mode).
        force : bool, optional
            Print to console regardless of verbose mode and echo_console setting.
        """
        # Always log to file
        log_fn = getattr(self.logger, level, self.logger.info)
        log_fn(msg)
        
        # Console output decision
        should_echo = False
        
        if force:
            # force=True always prints
            should_echo = True
        elif self.verbose:
            # In verbose mode, all messages go to console
            should_echo = True
        elif echo_console:
            # In non-verbose mode, only echo if explicitly requested
            should_echo = True
        elif level in ("warning", "error", "critical"):
            # Always show warnings and errors, even in non-verbose mode
            should_echo = True
        
        if should_echo:
            tqdm.write(msg)


def setup_logger(
    name: str = "weather_processing",
    save_dir: Optional[Path] = None,
    verbose: bool = True,
    module_name: str = "weather_data_processing"
) -> VerboseLogger:
    """
    Initialize and return a configured logger.
    
    Logs are written to <repo_root>/logs/weather_data_processing
    (or $OSME_LOG_DIR/weather_data_processing).
    
    Parameters
    ----------
    name : str, optional
        Logger name (default "weather_processing").
    save_dir : Path or None, optional
        Directory to save log files. If None, uses osme_common.paths.log_dir().
    verbose : bool, optional
        Whether to echo logs to console (default True).
    module_name : str, optional
        Module name for organizing logs (default "weather_data_processing").
    
    Returns
    -------
    VerboseLogger
        Configured logger instance.
    
    Examples
    --------
    >>> logger = setup_logger(verbose=True)
    >>> logger.info("This goes to file and console", force=True)
    >>> logger.debug("This goes to file only (unless verbose=True)")
    
    >>> logger = setup_logger(verbose=False)
    >>> logger.info("File only")
    >>> logger.warning("File and console (warnings always show)")
    """
    if save_dir is None:
        base_dir = get_log_dir(create=True) / module_name
    else:
        base_dir = Path(save_dir) / module_name
    
    base_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = base_dir / f"{name}_{timestamp}.log"
    
    return VerboseLogger(
        name=name,
        log_file=log_file,
        verbose=verbose,
        module_name=module_name
    )
