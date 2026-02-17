"""
File handler for managing input/output files and cleanup operations.

This module provides utilities for:
- Managing file paths for different processing steps
- Automatic detection of date ranges from filenames
- Cleanup of intermediate files
"""

from pathlib import Path
from typing import Optional, List
import re
from datetime import datetime

from osme_common.paths import data_dir, resolve_under


class FileHandler:
    """
    Manages file paths and operations for grid data processing pipeline.

    This class handles:
    - Creating output directories
    - Generating standardized filenames for each processing step
    - Tracking intermediate files for optional cleanup
    - Extracting date ranges from input files

    Parameters
    ----------
    output_dir : Path or str
        Base output directory for processed files
    base_filename : str, optional
        Base filename stem (e.g., "carbontracker_grid-data_2018-11_2026-02")
        If not provided, will be auto-generated from input files

    Examples
    --------
    >>> handler = FileHandler(
    ...     output_dir="data/grid_data/processed",
    ...     base_filename="carbontracker_grid-data_2018-11_2026-02"
    ... )
    >>> handler.get_step_output_path("step1_gapfilled")
    PosixPath('data/grid_data/processed/carbontracker_grid-data_2018-11_2026-02_step1_gapfilled.parquet')
    """

    def __init__(
        self,
        output_dir: Path | str,
        base_filename: Optional[str] = None
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.base_filename = base_filename

        # Track intermediate files for cleanup
        self.intermediate_files: List[Path] = []

    def set_base_filename(self, filename: str) -> None:
        """
        Set the base filename stem for output files.

        Parameters
        ----------
        filename : str
            Base filename stem without step suffix or extension
        """
        self.base_filename = filename

    def get_step_output_path(self, step: str) -> Path:
        """
        Get output path for a processing step.

        The filename follows the pattern:
        {base_filename}_{step}.parquet

        For example:
        carbontracker_grid-data_2018-11_2026-02_step1_gapfilled.parquet

        Parameters
        ----------
        step : str
            Step identifier (e.g., "step1_gapfilled", "step2_half-hourly")

        Returns
        -------
        Path
            Full path to output file for this step
        """
        if not self.base_filename:
            raise ValueError(
                "base_filename not set. Call set_base_filename() or "
                "use detect_date_range_from_monthly() first."
            )

        filename = f"{self.base_filename}_{step}.parquet"
        return self.output_dir / filename

    def mark_as_intermediate(self, filepath: Path) -> None:
        """
        Mark a file as intermediate (eligible for cleanup).

        Parameters
        ----------
        filepath : Path
            Path to intermediate file
        """
        if filepath not in self.intermediate_files:
            self.intermediate_files.append(filepath)

    def cleanup_intermediate_files(self, logger=None) -> None:
        """
        Remove intermediate files that were marked for cleanup.

        This is typically called after successful pipeline completion to
        remove step outputs that aren't needed (keeping only final output).

        Parameters
        ----------
        logger : logging.Logger, optional
            Logger instance for logging cleanup operations
        """
        if not self.intermediate_files:
            if logger:
                logger.info("No intermediate files to clean up")
            return

        if logger:
            logger.info(f"Cleaning up {len(self.intermediate_files)} intermediate file(s)...")

        for filepath in self.intermediate_files:
            if filepath.exists():
                try:
                    filepath.unlink()
                    if logger:
                        logger.info(f"  Removed: {filepath.name}")
                except Exception as e:
                    if logger:
                        logger.warning(f"  Failed to remove {filepath.name}: {e}")

        if logger:
            logger.info("✓ Intermediate file cleanup complete")

        self.intermediate_files.clear()


def detect_date_range_from_monthly(
    monthly_dir: Path | str,
    pattern: str = r"carbontracker_grid-data_(\d{4})_(\d{2})\.parquet"
) -> str:
    """
    Detect the date range from monthly parquet files and generate base filename.

    This function scans a directory of monthly files, extracts their dates,
    and constructs a filename stem following the convention:
    carbontracker_grid-data_{earliest_YYYY-MM}_{latest_YYYY-MM}

    Parameters
    ----------
    monthly_dir : Path or str
        Directory containing monthly parquet files
    pattern : str, optional
        Regex pattern for extracting year and month from filenames.
        Default matches: carbontracker_grid-data_YYYY_MM.parquet

    Returns
    -------
    str
        Base filename stem (e.g., "carbontracker_grid-data_2018-11_2026-02")

    Raises
    ------
    FileNotFoundError
        If no matching monthly files found in directory

    Examples
    --------
    >>> stem = detect_date_range_from_monthly("data/grid_data/raw/monthly")
    >>> print(stem)
    'carbontracker_grid-data_2018-11_2026-02'
    """
    monthly_dir = Path(monthly_dir)

    if not monthly_dir.exists():
        raise FileNotFoundError(f"Monthly directory not found: {monthly_dir}")

    # Find all matching files
    files = list(monthly_dir.glob("carbontracker_grid-data_*.parquet"))

    if not files:
        raise FileNotFoundError(
            f"No monthly parquet files found in {monthly_dir}. "
            f"Expected pattern: carbontracker_grid-data_YYYY_MM.parquet"
        )

    # Extract dates from filenames
    dates = []
    regex = re.compile(pattern)

    for file in files:
        match = regex.search(file.name)
        if match:
            year, month = match.groups()
            dates.append((int(year), int(month)))

    if not dates:
        raise ValueError(
            f"Could not extract dates from filenames in {monthly_dir}. "
            f"Expected pattern: carbontracker_grid-data_YYYY_MM.parquet"
        )

    # Sort to get earliest and latest
    dates.sort()
    earliest_year, earliest_month = dates[0]
    latest_year, latest_month = dates[-1]

    # Construct base filename
    base_filename = (
        f"carbontracker_grid-data_"
        f"{earliest_year:04d}-{earliest_month:02d}_"
        f"{latest_year:04d}-{latest_month:02d}"
    )

    return base_filename


def detect_date_range_from_combined(
    combined_file: Path | str
) -> str:
    """
    Extract the date range from an existing combined filename.

    This handles cases where we already have a combined file and want to
    preserve its date range in subsequent output files.

    Parameters
    ----------
    combined_file : Path or str
        Path to combined file with embedded date range

    Returns
    -------
    str
        Base filename stem extracted from the combined file

    Examples
    --------
    >>> stem = detect_date_range_from_combined(
    ...     "data/carbontracker_grid-data_2018-11_2026-02.parquet"
    ... )
    >>> print(stem)
    'carbontracker_grid-data_2018-11_2026-02'
    """
    combined_file = Path(combined_file)
    stem = combined_file.stem  # Remove .parquet extension

    # Check if it already has the expected pattern
    pattern = r"carbontracker_grid-data_\d{4}-\d{2}_\d{4}-\d{2}"
    if re.match(pattern, stem):
        return stem

    # If it doesn't match, try to extract just the base part
    # Remove any step suffixes like "_step1_gapfilled"
    parts = stem.split("_step")
    if len(parts) > 1:
        return parts[0]

    return stem