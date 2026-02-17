"""
Step 2: Gap Filling
===================

Fill missing data gaps using a comprehensive 3-step process:
1. Linear interpolation for short gaps (≤80 min by default)
2. Gradient-based donor day method (first pass)
3. Gradient-based donor day method (second pass for remaining gaps)

This module provides a thin wrapper around the gap_filling implementation,
exposing the main fill_all_gaps() function for use in the pipeline.

The actual implementation logic lives in gap_filling.py at the package root,
keeping the reusable functions separate from the pipeline step interface.
"""

from grid_data_processing.gap_filling import fill_all_gaps

__all__ = ["fill_all_gaps"]
