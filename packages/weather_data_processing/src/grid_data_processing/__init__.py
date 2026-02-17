"""
Grid Data Processing
====================

A production pipeline for processing Indian national grid electricity data.

This package provides tools to:
- Combine monthly grid data files
- Fill data gaps using linear interpolation and gradient methods
- Aggregate to half-hourly intervals
- Apply timezone labeling
- Validate processed outputs

Main Components
---------------
- GridDataProcessor: Main orchestrator class
- Command-line tools: gdp, griddataprocessing, gridprocessing, gridproc

Usage
-----
From command line::

    gdp --monthly-dir data/grid_data/raw/monthly --verbose

From Python::

    from grid_data_processing import GridDataProcessor
    
    processor = GridDataProcessor(
        monthly_dir="data/grid_data/raw/monthly",
        verbose=True
    )
    final_file = processor.run_full_pipeline()
"""

from grid_data_processing.main import GridDataProcessor

__version__ = "1.0.0"
__all__ = ["GridDataProcessor"]
