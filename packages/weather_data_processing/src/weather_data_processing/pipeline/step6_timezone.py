# packages/weather_data_processing/src/weather_data_processing/pipeline/step6_timezone.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Step 6: Timezone Conversion Pipeline
=====================================

Convert UTC timestamps to target timezone for final output files.

This step runs AFTER spatial aggregation (Step 5) and converts the single
consolidated output file from UTC to the configured target timezone
(e.g., Asia/Kolkata).

The step is intentionally separate so you can inspect outputs before and after
timezone conversion.

Input:  era5-world_INDIA_916d3fbb_2018-01_2026-02_ADM0_halfhourly.parquet (UTC)
Output: era5-world_INDIA_916d3fbb_2018-01_2026-02_ADM0_halfhourly_tz-kolkata.parquet
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import polars as pl

from ..utils.logging import VerboseLogger
from ..utils.parallel import is_rank_zero


@dataclass
class TimezoneConversionResult:
    """Result of timezone conversion."""
    input_file: Path
    output_file: Path
    source_timezone: str
    target_timezone: str
    num_rows: int
    processing_time_s: float


def build_timezone_filename(input_file: Path, timezone_suffix: str) -> str:
    """
    Build output filename with timezone suffix.
    
    Example:
        Input:  era5-world_INDIA_916d3fbb_2018-01_2026-02_ADM0_halfhourly.parquet
        Output: era5-world_INDIA_916d3fbb_2018-01_2026-02_ADM0_halfhourly_tz-kolkata.parquet
    """
    stem = input_file.stem
    
    # Remove any existing timezone suffix
    stem = re.sub(r'_tz-\w+$', '', stem)
    
    return f"{stem}_{timezone_suffix}.parquet"


class TimezonePipeline:
    """
    Orchestrator for Step 6: Timezone conversion.

    Converts the single consolidated UTC output from Step 5 to the target timezone.

    Parameters
    ----------
    input_dir : Path
        Directory containing the consolidated half-hourly file from Step 5.
    output_dir : Path
        Directory for timezone-converted output.
    target_timezone : str
        IANA timezone name (e.g., "Asia/Kolkata").
    keep_utc_column : bool, optional
        If True, keep original UTC timestamp as "time_utc" column.
    logger : VerboseLogger, optional
        Logger instance.

    Examples
    --------
    >>> pipeline = TimezonePipeline(
    ...     input_dir=Path("data/era5-world/processed/ADM0"),
    ...     output_dir=Path("data/era5-world/final/ADM0"),
    ...     target_timezone="Asia/Kolkata",
    ... )
    >>> result = pipeline.run()
    """

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        target_timezone: str = "UTC",
        keep_utc_column: bool = False,
        logger: Optional[VerboseLogger] = None,
    ):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.target_timezone = target_timezone
        self.keep_utc_column = keep_utc_column
        self.logger = logger or VerboseLogger("timezone_pipeline", verbose=False)
        
        # Generate timezone suffix for filenames
        # e.g., "Asia/Kolkata" -> "tz-kolkata"
        tz_short = target_timezone.split("/")[-1].lower().replace("_", "-")
        self.timezone_suffix = f"tz-{tz_short}"

    def _discover_file(self) -> Path:
        """Discover the consolidated half-hourly file from Step 5."""
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {self.input_dir}")

        # Look for the consolidated file (should be just one)
        files = sorted(self.input_dir.glob("*_halfhourly.parquet"))
        
        # Exclude any already-converted files
        files = [f for f in files if "_tz-" not in f.name]

        if not files:
            raise FileNotFoundError(
                f"No half-hourly parquet file found in {self.input_dir}"
            )
        
        if len(files) > 1:
            self.logger.warning(
                f"Multiple files found, using: {files[0].name}"
            )

        return files[0]

    def convert_file(
        self,
        input_file: Path,
        output_file: Path,
    ) -> TimezoneConversionResult:
        """
        Convert timestamps in the file from UTC to target timezone.

        Parameters
        ----------
        input_file : Path
            Input parquet file (timestamps in UTC).
        output_file : Path
            Output parquet file (timestamps in target timezone).

        Returns
        -------
        TimezoneConversionResult
        """
        t0 = time.perf_counter()

        self.logger.info(f"Converting: {input_file.name}", force=True)
        self.logger.info(f"  Source timezone: UTC", force=True)
        self.logger.info(f"  Target timezone: {self.target_timezone}", force=True)

        # Read the file
        df = pl.read_parquet(input_file)
        num_rows = len(df)

        self.logger.info(f"  Rows: {num_rows:,}", force=True)

        # Keep UTC column if requested
        if self.keep_utc_column:
            df = df.with_columns(
                pl.col("time").alias("time_utc")
            )

        # Convert timezone
        # Polars datetime conversion: first set timezone to UTC, then convert
        df = df.with_columns(
            pl.col("time")
            .dt.replace_time_zone("UTC")
            .dt.convert_time_zone(self.target_timezone)
            .alias("time")
        )

        # Write output
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(output_file, compression="zstd", statistics=True)

        dt = time.perf_counter() - t0

        self.logger.info(f"  Output: {output_file.name}", force=True)
        self.logger.info(f"  Completed in {dt:.2f}s", force=True)

        return TimezoneConversionResult(
            input_file=input_file,
            output_file=output_file,
            source_timezone="UTC",
            target_timezone=self.target_timezone,
            num_rows=num_rows,
            processing_time_s=dt,
        )

    def run(
        self,
        use_mpi: bool = False  # Ignored - single file doesn't need MPI
    ) -> Dict:
        """
        Execute the timezone conversion pipeline.

        Parameters
        ----------
        use_mpi : bool, optional
            Ignored for this step (single file processing).

        Returns
        -------
        dict
            Pipeline results with statistics.
        """
        t_total = time.perf_counter()

        self.logger.info("", force=True)
        self.logger.info("#" * 72, force=True)
        self.logger.info("# STEP 6: TIMEZONE CONVERSION", force=True)
        self.logger.info("#" * 72, force=True)
        self.logger.info("", force=True)

        # Discover input file
        input_file = self._discover_file()
        self.logger.info(f"Input file: {input_file.name}", force=True)

        # Build output filename
        output_name = build_timezone_filename(input_file, self.timezone_suffix)
        output_file = self.output_dir / output_name

        # Convert
        result = self.convert_file(input_file, output_file)

        dt_total = time.perf_counter() - t_total

        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("TIMEZONE CONVERSION COMPLETE", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info(f"  Total time: {dt_total:.2f}s", force=True)
        self.logger.info(f"  Input:  {input_file.name} (UTC)", force=True)
        self.logger.info(f"  Output: {output_file.name} ({self.target_timezone})", force=True)
        self.logger.info(f"  Rows: {result.num_rows:,}", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("", force=True)

        return {
            "result": result,
            "output_file": output_file,
            "target_timezone": self.target_timezone,
            "total_time_s": dt_total,
        }
