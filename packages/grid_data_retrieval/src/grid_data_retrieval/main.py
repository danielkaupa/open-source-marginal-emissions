# packages/grid_data_retrieval/src/grid_data_retrieval/main.py

# =============================================================================
# Copyright © {2025} Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Main Entry Point for Grid Data Retrieval
=========================================

This script serves as the entry point for the grid data retrieval CLI.

Typically invoked through the CLI command: `osme-grid`.
"""

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from grid_data_retrieval.io.cli import main

# ----------------------------------------------
# ENTRY POINT
# ----------------------------------------------

if __name__ == "__main__":
    main()
