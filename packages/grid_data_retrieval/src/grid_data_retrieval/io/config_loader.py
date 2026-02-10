# packages/grid_data_retrieval/src/grid_data_retrieval/io/config_loader.py

# =============================================================================
# Copyright © {2026} Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Configuration File Loading
===========================

Load and validate JSON configuration files for grid data retrieval.
"""

# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

import json
from pathlib import Path

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from osme_common.paths import config_dir, resolve_under

# ----------------------------------------------
# CONFIG LOADING
# ----------------------------------------------


def load_config(file_path: str | Path) -> dict:
    """
    Load configuration from a JSON file.

    Searches in:
    1. Absolute path (if provided)
    2. Relative to config_dir()
    3. Relative to config_dir()/grid/

    Parameters
    ----------
    file_path : str or Path
        Path to JSON config file.

    Returns
    -------
    dict
        Configuration dictionary.

    Raises
    ------
    FileNotFoundError
        If the configuration file cannot be found.
    """
    cfg_path = _resolve_config_path(file_path)
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_config_path(path: str | Path) -> Path:
    """
    Resolve a config path safely relative to osme_common.config_dir().

    Parameters
    ----------
    path : str or Path
        The path or filename to resolve.

    Returns
    -------
    Path
        Fully resolved path to the configuration file.

    Raises
    ------
    FileNotFoundError
        If the file cannot be found.
    """
    p = Path(path)

    # If absolute and exists, use it
    if p.is_absolute() and p.exists():
        return p

    # Try relative to config_dir()
    resolved = resolve_under(config_dir(create=True), p)
    if resolved.exists():
        return resolved

    # Try in config_dir()/grid/
    grid_resolved = config_dir(create=True) / "grid" / p.name
    if grid_resolved.exists():
        return grid_resolved

    raise FileNotFoundError(
        f"Configuration file not found. Tried:\n"
        f"  - {p}\n"
        f"  - {resolved}\n"
        f"  - {grid_resolved}"
    )
