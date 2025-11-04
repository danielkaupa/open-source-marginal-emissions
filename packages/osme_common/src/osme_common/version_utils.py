# packages/osme_common/src/osme_common/version_utils.py

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
Shared utility for retrieving the installed OSME package version safely.

This avoids repeating `importlib.metadata.version()` try/except logic across subpackages.
"""

#----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

from importlib.metadata import PackageNotFoundError, version

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

# N/A

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ---------------------------------------------

# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------


def get_repo_version(package_name: str = "open-source-marginal-emissions") -> str:
    """
    Return the version of the OSME package (or subpackage) from package metadata.

    Parameters
    ----------
    package_name : str, optional
        Name of the installed package to query (defaults to the main OSME distribution).

    Returns
    -------
    str
        Version string (e.g., "0.1.dev19+g71555cd41.d20251102") or "0+unknown" if not found.
    """
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "0+unknown"
