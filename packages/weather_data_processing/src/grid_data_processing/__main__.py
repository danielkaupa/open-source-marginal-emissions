"""
Main entry point for grid_data_processing when run as a module.

This allows the package to be run with:
    python -m grid_data_processing [args]

It simply delegates to the runner module's main function.
"""

from grid_data_processing.runner import run_pipeline

if __name__ == "__main__":
    run_pipeline()
