# packages/weather_data_processing/src/weather_data_processing/processing/boundary_fix.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Year Boundary Fix
=================

Handle Dec 31 23:30 interpolation that requires Jan 1 00:00 from next year.

The Problem
-----------
When interpolating Dec 31 23:00 to create Dec 31 23:30:
- Intensive fields need: (Dec31_23:00 + Jan1_00:00) / 2
- But Jan 1 00:00 is in the next year's file!

The Solution
------------
Two-pass approach:
1. **Pass 1 (interpolation)**: Create placeholder rows for Dec 31 23:30
2. **Pass 2 (this module)**: Fix those rows using adjacent years' data
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import polars as pl

from ..utils.logging import VerboseLogger


@dataclass
class BoundaryFixResult:
    """Result of year boundary fix."""
    output_file: Path
    year: int
    boundary_rows_fixed: int
    processing_time_s: float


class YearBoundaryFixer:
    """
    Fix year boundary rows (Dec 31 23:30) using adjacent years.

    Parameters
    ----------
    group_cols : list of str, optional
        Grouping columns (default: ["latitude", "longitude"]).
    timestamp_col : str, optional
        Timestamp column name (default: "time").
    logger : VerboseLogger, optional
        Logger instance.

    Examples
    --------
    >>> fixer = YearBoundaryFixer()
    >>> result = fixer.fix_boundary(
    ...     current_year_file=Path("2018_halfhourly.parquet"),
    ...     next_year_file=Path("2019_halfhourly.parquet"),
    ...     output_file=Path("2018_halfhourly_fixed.parquet"),
    ...     year=2018
    ... )
    """

    def __init__(
        self,
        group_cols: Optional[List[str]] = None,
        timestamp_col: str = "time",
        logger: Optional[VerboseLogger] = None,
    ):
        self.group_cols = group_cols or ["latitude", "longitude"]
        self.timestamp_col = timestamp_col
        self.logger = logger or VerboseLogger("boundary_fixer", verbose=False)

    def fix_boundary(
        self,
        current_year_file: Path,
        next_year_file: Path,
        output_file: Path,
        year: int,
        overwrite: bool = True
    ) -> BoundaryFixResult:
        """
        Fix Dec 31 23:30 rows using data from next year.

        Parameters
        ----------
        current_year_file : Path
            Half-hourly file for current year (with incomplete Dec 31 23:30).
        next_year_file : Path
            Half-hourly file for next year (has Jan 1 00:00).
        output_file : Path
            Output file with fixed boundaries.
        year : int
            Current year being processed.
        overwrite : bool, optional
            Overwrite existing output.

        Returns
        -------
        BoundaryFixResult
            Processing result.
        """
        t0 = time.perf_counter()

        if output_file.exists() and not overwrite:
            self.logger.debug(f"Skipping {output_file.name} (exists)")
            return None

        self.logger.info(f"Fixing year boundary for {year}", force=True)

        if not next_year_file.exists():
            self.logger.warning(
                f"  Next year file not found: {next_year_file.name}, skipping fix"
            )
            # Just copy current file
            import shutil
            shutil.copy(current_year_file, output_file)
            return BoundaryFixResult(
                output_file=output_file,
                year=year,
                boundary_rows_fixed=0,
                processing_time_s=time.perf_counter() - t0
            )

        # Load current year
        df_current = pl.scan_parquet(current_year_file)

        # Load next year (just Jan 1 00:00)
        df_next = pl.scan_parquet(next_year_file).filter(
            (pl.col(self.timestamp_col).dt.month() == 1) &
            (pl.col(self.timestamp_col).dt.day() == 1) &
            (pl.col(self.timestamp_col).dt.hour() == 0) &
            (pl.col(self.timestamp_col).dt.minute() == 0)
        )

        # Separate Dec 31 23:30 rows from rest
        boundary_mask = (
            (pl.col(self.timestamp_col).dt.month() == 12) &
            (pl.col(self.timestamp_col).dt.day() == 31) &
            (pl.col(self.timestamp_col).dt.hour() == 23) &
            (pl.col(self.timestamp_col).dt.minute() == 30)
        )

        df_boundary = df_current.filter(boundary_mask)
        df_rest = df_current.filter(~boundary_mask)

        # Get Dec 31 23:00 for reference
        dec31_23_mask = (
            (pl.col(self.timestamp_col).dt.month() == 12) &
            (pl.col(self.timestamp_col).dt.day() == 31) &
            (pl.col(self.timestamp_col).dt.hour() == 23) &
            (pl.col(self.timestamp_col).dt.minute() == 0)
        )

        df_dec31_23 = df_current.filter(dec31_23_mask)

        # Identify column types
        schema = df_current.collect_schema()

        # Classify columns
        static_cols = ["frac_in_region"] + [
            c for c in schema.names() if c.startswith("adm")
        ]

        intensive_cols = [
            c for c in schema.names()
            if c not in self.group_cols
            and c != self.timestamp_col
            and c not in static_cols
            and not c.endswith("_precipitation")  # Extensive
            and not c.endswith("_radiation")       # Extensive
        ]

        # Build fixed boundary rows
        # Static fields: from Dec 31 23:00
        # Intensive fields: (Dec31_23:00 + Jan1_00:00) / 2
        # Extensive fields: Already correct (not touched)

        # Join Dec 31 23:00 with Jan 1 00:00
        df_joined = df_dec31_23.join(
            df_next,
            on=self.group_cols,
            how="left",
            suffix="_jan1"
        )

        # Build fix expressions
        fix_exprs = []

        # Keep grouping cols
        for col in self.group_cols:
            fix_exprs.append(pl.col(col))

        # Set timestamp to Dec 31 23:30
        # Build timestamp from components
        fix_exprs.append(
            pl.datetime(year, 12, 31, 23, 30).alias(self.timestamp_col)
        )

        # Static fields: from current
        for col in static_cols:
            if col in schema.names():
                fix_exprs.append(pl.col(col))

        # Intensive fields: midpoint
        for col in intensive_cols:
            if col in schema.names() and f"{col}_jan1" in df_joined.collect_schema().names():
                fix_exprs.append(
                    ((pl.col(col) + pl.col(f"{col}_jan1")) / 2.0).alias(col)
                )
            elif col in schema.names():
                # Jan 1 data not available, keep Dec 31 23:00 value
                fix_exprs.append(pl.col(col))

        # Extensive fields: keep from boundary rows (already correct)
        extensive_cols = [
            c for c in schema.names()
            if c not in self.group_cols
            and c != self.timestamp_col
            and c not in static_cols
            and c not in intensive_cols
        ]

        # We need to get extensive values from the original boundary rows
        # This is tricky - we'll need to merge them back

        # Simpler approach: use df_boundary values for extensive fields
        df_fixed_partial = df_joined.select(fix_exprs)

        # Get extensive columns from df_boundary
        if extensive_cols:
            df_boundary_extensive = df_boundary.select(
                self.group_cols + [self.timestamp_col] + extensive_cols
            )

            df_fixed = df_fixed_partial.join(
                df_boundary_extensive,
                on=self.group_cols + [self.timestamp_col],
                how="left"
            )
        else:
            df_fixed = df_fixed_partial

        # Concatenate: rest + fixed boundary
        df_final = pl.concat([df_rest, df_fixed])

        # Sort by group and time
        df_final = df_final.sort([*self.group_cols, self.timestamp_col])

        # Collect and write
        df_result = df_final.collect()

        output_file.parent.mkdir(parents=True, exist_ok=True)
        df_result.write_parquet(output_file, compression="zstd", statistics=True)

        # Count fixed rows
        boundary_count = df_boundary.select(pl.len()).collect().item()

        dt = time.perf_counter() - t0

        self.logger.info(
            f"  Fixed {boundary_count:,} boundary rows ({dt:.2f}s)",
            force=True
        )

        return BoundaryFixResult(
            output_file=output_file,
            year=year,
            boundary_rows_fixed=boundary_count,
            processing_time_s=dt,
        )

    def process_year_sequence(
        self,
        halfhourly_files: List[Path],
        output_dir: Path,
        overwrite: bool = True
    ) -> List[BoundaryFixResult]:
        """
        Process a sequence of years, fixing boundaries.

        Parameters
        ----------
        halfhourly_files : list of Path
            Sorted list of half-hourly files by year.
        output_dir : Path
            Output directory for fixed files.
        overwrite : bool, optional
            Overwrite existing outputs.

        Returns
        -------
        list of BoundaryFixResult
            Results for each year.
        """
        results = []

        # Ensure output directory exists before any writes.
        # This is critical for the last-year path (shutil.copy) which does not
        # call fix_boundary and therefore never hits the per-file mkdir inside it.
        output_dir.mkdir(parents=True, exist_ok=True)

        for i, current_file in enumerate(halfhourly_files):
            # Extract year from filename (assumes pattern: *_YYYY_*.parquet)
            year_match = None
            for part in current_file.stem.split("_"):
                if part.isdigit() and len(part) == 4:
                    year_match = int(part)
                    break

            if year_match is None:
                self.logger.warning(f"Could not extract year from {current_file.name}, skipping")
                continue

            year = year_match

            # Get next year file
            if i + 1 < len(halfhourly_files):
                next_file = halfhourly_files[i + 1]
            else:
                next_file = None

            # Build output path
            output_file = output_dir / current_file.name.replace(".parquet", "_fixed.parquet")

            # Fix boundary
            if next_file:
                result = self.fix_boundary(
                    current_year_file=current_file,
                    next_year_file=next_file,
                    output_file=output_file,
                    year=year,
                    overwrite=overwrite
                )
            else:
                # Last year: just copy
                self.logger.info(f"Last year {year}: no boundary fix needed")
                import shutil
                shutil.copy(current_file, output_file)
                result = BoundaryFixResult(
                    output_file=output_file,
                    year=year,
                    boundary_rows_fixed=0,
                    processing_time_s=0.0
                )

            if result:
                results.append(result)

        return results