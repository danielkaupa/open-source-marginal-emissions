"""
Logging utilities for grid data processing.

This module provides a unified logging system that:
- Always writes complete DEBUG logs to file
- Optionally echoes INFO+ messages to console (controlled by verbose flag)
- Integrates with osme_common.paths for log directory resolution
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from osme_common.paths import log_dir


def setup_logging(
    name: str = "grid_data_processing",
    log_subdir: str = "grid_data_processing",
    verbose: bool = False
) -> logging.Logger:
    """
    Set up logging for grid data processing.
    
    The logging system uses a dual-handler approach:
    - File handler: ALWAYS captures everything at DEBUG level for complete audit trail
    - Console handler: Shows INFO+ messages only if verbose=True
    
    This ensures you never lose information (complete log file) while keeping
    console output clean during automated runs.
    
    Parameters
    ----------
    name : str
        Logger name (default: "grid_data_processing")
    log_subdir : str
        Subdirectory under logs/ for this package's logs
    verbose : bool
        If True, echo INFO+ messages to console. If False, console is silent.
        File logging is always enabled regardless of this setting.
        
    Returns
    -------
    logging.Logger
        Configured logger instance
        
    Examples
    --------
    >>> # Silent mode - everything to file, nothing to console
    >>> logger = setup_logging(verbose=False)
    >>> 
    >>> # Verbose mode - everything to file, INFO+ to console
    >>> logger = setup_logging(verbose=True)
    """
    # Get or create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Logger itself accepts all levels
    
    # Remove any existing handlers to avoid duplicates
    logger.handlers = []
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    # Create detailed formatter for file logs
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Create simpler formatter for console
    console_formatter = logging.Formatter('%(message)s')
    
    # Setup file handler - ALWAYS gets everything at DEBUG level
    base_log_dir = log_dir(create=True)
    package_log_dir = base_log_dir / log_subdir
    package_log_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = package_log_dir / f"grid_processing_{timestamp}.log"
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Setup console handler - only if verbose mode
    if verbose:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # Log initialization (this goes to file always, console only if verbose)
    logger.info("=" * 80)
    logger.info("Grid Data Processing - Logging Initialized")
    logger.info("=" * 80)
    logger.info(f"Log file: {log_file}")
    logger.info(f"Verbose mode: {verbose}")
    logger.info("")
    
    return logger
