# packages/weather_data_retrieval/src/weather_data_retrieval/io/config_loader.py

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
from weather_data_retrieval.utils.data_validation import validate_config
from pathlib import Path

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from osme_common.paths import config_dir, resolve_under

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------


def load_and_validate_config(
        path: str,
        *,
        logger=None,
        run_mode: str = "automatic") -> dict:
    """
    Load JSON config and validate it using the centralized validator.
    This lets the validator log coercions/warnings (e.g., case_by_case → skip_all).

    Parameters
    ----------
    path : str
        Path to JSON config file.
    logger : logging.Logger, optional
        Logger instance for validation messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "automatic".

    Returns
    -------
    dict
        Validated configuration dictionary.
    """
    cfg_path = _resolve_config_path(path)
    with open(cfg_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    # Let validate_config perform normalization/clamping with logging context
    validate_config(config, logger=logger, run_mode=run_mode)
    return config


def load_config(file_path: str) -> dict:
    """
    Load configuration from a JSON requirements file (without validation).

    Parameters
    ----------
    file_path : str
        Path to JSON config file.

    Returns
    -------
    dict
        Configuration dictionary.
    """
    # if not os.path.exists(file_path):
    #     raise FileNotFoundError(f"Configuration file not found: {file_path}")
    # with open(file_path, "r", encoding="utf-8") as f:
    #     return json.load(f)
    cfg_path = _resolve_config_path(file_path)
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_config_path(path: str | Path) -> Path:
    """
    Resolve a config path safely relative to osme_common.config_dir().

    Parameters
    ----------
    path : str | Path
        The path or filename to resolve.

    Returns
    -------
    Path
        Fully resolved path to the configuration file.
    """
    p = Path(path)
    if p.is_absolute() and p.exists():
        return p
    resolved = resolve_under(config_dir(create=True), p)
    if not resolved.exists():
        raise FileNotFoundError(f"Configuration file not found: {resolved}")
    return resolved