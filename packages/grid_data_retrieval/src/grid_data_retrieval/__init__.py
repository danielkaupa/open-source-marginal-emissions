# packages/grid_data_retrieval/src/grid_data_retrieval/__init__.py

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

from osme_common.version_utils import get_repo_version

__version__ = get_repo_version()
__all__ = ["__version__"]


"""
Grid Data Retrieval Module
===========================

Module for retrieving electricity grid data from various sources.

This module focuses exclusively on data retrieval/fetching.
Data processing, resampling, and timezone conversion are handled
by the data_cleaning_and_joining module.

Submodules
----------
sources : API-specific data retrieval implementations
utils : Shared utilities for validation, file management, logging
io : Configuration loading and CLI interfaces
"""
