# packages/weather_data_processing/src/weather_data_processing/processing/temporal_validation.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Temporal Data Validation
=========================

Validate half-hourly temporal data for quality issues:
- Duplicate timestamps
- Irregular time intervals
- Missing expected timestamps
- Invalid minute values (should be 0 or 30)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import polars as pl

from ..utils.logging import VerboseLogger


@dataclass
class ValidationResult:
    """Result of temporal validation."""
    file_path: Path
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    total_rows: int
    total_groups: int
    min_timestamp: str
    max_timestamp: str


class TemporalValidator:
    """
    Validate half-hourly temporal data.

    Parameters
    ----------
    group_cols : list of str, optional
        Grouping columns (default: ["latitude", "longitude"]).
    timestamp_col : str, optional
        Timestamp column name (default: "time").
    expected_interval_minutes : int, optional
        Expected time interval in minutes (default: 30).
    logger : VerboseLogger, optional
        Logger instance.

    Examples
    --------
    >>> validator = TemporalValidator()
    >>> result = validator.validate_file(
    ...     Path("data/transformed/2018_halfhourly_fixed.parquet")
    ... )
    >>> if not result.is_valid:
    ...     for err in result.errors:
    ...         print(f"ERROR: {err}")
    """

    def __init__(
        self,
        group_cols: Optional[List[str]] = None,
        timestamp_col: str = "time",
        expected_interval_minutes: int = 30,
        logger: Optional[VerboseLogger] = None,
    ):
        self.group_cols = group_cols or ["latitude", "longitude"]
        self.timestamp_col = timestamp_col
        self.expected_interval = expected_interval_minutes
        self.logger = logger or VerboseLogger("temporal_validator", verbose=False)

    def validate_file(
        self,
        file_path: Path,
        strict: bool = True
    ) -> ValidationResult:
        """
        Validate a single half-hourly file.

        Parameters
        ----------
        file_path : Path
            Path to half-hourly parquet file.
        strict : bool, optional
            If True, treat warnings as errors (default True).

        Returns
        -------
        ValidationResult
            Validation result with errors and warnings.
        """
        self.logger.info(f"Validating {file_path.name}")

        errors = []
        warnings = []

        # Load data
        df = pl.read_parquet(file_path)

        total_rows = len(df)

        # Count groups
        total_groups = (
            df.select(self.group_cols)
            .unique()
            .height
        )

        # Get time range
        min_ts = df.select(pl.col(self.timestamp_col).min()).item()
        max_ts = df.select(pl.col(self.timestamp_col).max()).item()

        # ----------------------------------------------------------------
        # Check 1: Duplicate timestamps within groups
        # ----------------------------------------------------------------
        duplicates = (
            df.group_by(self.group_cols + [self.timestamp_col])
            .agg(pl.len().alias("count"))
            .filter(pl.col("count") > 1)
        )

        if len(duplicates) > 0:
            errors.append(
                f"Found {len(duplicates)} duplicate timestamps across groups"
            )

        # ----------------------------------------------------------------
        # Check 2: Invalid minute values (should be 0 or 30)
        # ----------------------------------------------------------------
        invalid_minutes = df.filter(
            ~pl.col(self.timestamp_col).dt.minute().is_in([0, 30])
        )

        if len(invalid_minutes) > 0:
            errors.append(
                f"Found {len(invalid_minutes)} rows with invalid minute values "
                f"(not 0 or 30)"
            )

        # ----------------------------------------------------------------
        # Check 3: Irregular intervals
        # ----------------------------------------------------------------
        # Compute time differences within each group
        df_sorted = df.sort([*self.group_cols, self.timestamp_col])

        df_with_diff = df_sorted.with_columns(
            (
                pl.col(self.timestamp_col).diff().over(self.group_cols)
            ).alias("time_diff")
        )

        # Filter to non-null diffs (first row in each group will be null)
        df_diffs = df_with_diff.filter(pl.col("time_diff").is_not_null())

        # Check for unexpected intervals
        expected_duration = pl.duration(minutes=self.expected_interval)

        irregular = df_diffs.filter(
            pl.col("time_diff") != expected_duration
        )

        if len(irregular) > 0:
            # Count by interval type
            interval_counts = (
                irregular
                .select((pl.col("time_diff").dt.total_minutes()).alias("minutes"))
                .group_by("minutes")
                .agg(pl.len().alias("count"))
                .sort("count", descending=True)
            )

            details = ", ".join([
                f"{row['minutes']}min: {row['count']}"
                for row in interval_counts.iter_rows(named=True)
            ])

            warnings.append(
                f"Found {len(irregular)} irregular intervals "
                f"(expected {self.expected_interval} min). Details: {details}"
            )

        # ----------------------------------------------------------------
        # Check 4: Gaps in time series
        # ----------------------------------------------------------------
        # Expected number of timestamps per group
        time_range_hours = (max_ts - min_ts).total_seconds() / 3600
        expected_count = int(time_range_hours * 2) + 1  # +1 for inclusive

        actual_counts = (
            df.group_by(self.group_cols)
            .agg(pl.len().alias("count"))
        )

        groups_with_gaps = actual_counts.filter(
            pl.col("count") < expected_count * 0.95  # Allow 5% tolerance
        )

        if len(groups_with_gaps) > 0:
            warnings.append(
                f"Found {len(groups_with_gaps)}/{total_groups} groups with "
                f"potential gaps (expected ~{expected_count} rows, found less)"
            )

        # ----------------------------------------------------------------
        # Determine validity
        # ----------------------------------------------------------------
        if strict:
            is_valid = len(errors) == 0 and len(warnings) == 0
        else:
            is_valid = len(errors) == 0

        # ----------------------------------------------------------------
        # Log results
        # ----------------------------------------------------------------
        if is_valid:
            self.logger.info(f"  ✓ Validation passed", force=True)
        else:
            self.logger.error(f"  ✗ Validation failed", force=True)
            for err in errors:
                self.logger.error(f"    ERROR: {err}")
            for warn in warnings:
                self.logger.warning(f"    WARNING: {warn}")

        return ValidationResult(
            file_path=file_path,
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            total_rows=total_rows,
            total_groups=total_groups,
            min_timestamp=str(min_ts),
            max_timestamp=str(max_ts),
        )

    def validate_batch(
        self,
        files: List[Path],
        strict: bool = True
    ) -> List[ValidationResult]:
        """
        Validate multiple files.

        Parameters
        ----------
        files : list of Path
            List of files to validate.
        strict : bool, optional
            If True, treat warnings as errors.

        Returns
        -------
        list of ValidationResult
            Validation results for each file.
        """
        results = []

        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("TEMPORAL VALIDATION", force=True)
        self.logger.info("=" * 72, force=True)

        for f in files:
            result = self.validate_file(f, strict=strict)
            results.append(result)

        # Summary
        valid_count = sum(1 for r in results if r.is_valid)
        invalid_count = len(results) - valid_count

        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("VALIDATION SUMMARY", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info(f"  Total files: {len(results)}", force=True)
        self.logger.info(f"  Valid: {valid_count}", force=True)
        self.logger.info(f"  Invalid: {invalid_count}", force=True)
        self.logger.info("=" * 72, force=True)

        return results

    def check_energy_conservation(
        self,
        hourly_file: Path,
        halfhourly_file: Path,
        radiation_cols: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Check energy conservation for radiation fields.

        Verifies that sum of half-hourly values equals hourly total.

        Parameters
        ----------
        hourly_file : Path
            Original hourly file.
        halfhourly_file : Path
            Interpolated half-hourly file.
        radiation_cols : list of str, optional
            Radiation columns to check.

        Returns
        -------
        dict
            Mapping of column name to conservation error (should be ~0).
        """
        if radiation_cols is None:
            # Default radiation columns
            radiation_cols = [
                "surface_net_short_wave_solar_radiation",
                "surface_net_long_wave_thermal_radiation",
            ]

        self.logger.info("Checking energy conservation...")

        # Load hourly data
        df_hourly = pl.read_parquet(hourly_file)

        # Load half-hourly data
        df_half = pl.read_parquet(halfhourly_file)

        # Round half-hourly timestamps to nearest hour
        df_half_agg = df_half.with_columns(
            pl.col(self.timestamp_col).dt.truncate("1h").alias("hour")
        ).group_by(self.group_cols + ["hour"]).agg([
            pl.col(c).sum().alias(f"{c}_sum")
            for c in radiation_cols
            if c in df_half.columns
        ])

        # Join with hourly
        df_joined = df_hourly.join(
            df_half_agg,
            left_on=self.group_cols + [self.timestamp_col],
            right_on=self.group_cols + ["hour"],
            how="inner"
        )

        # Compute errors
        errors = {}

        for col in radiation_cols:
            if col in df_hourly.columns and f"{col}_sum" in df_joined.columns:
                # Compute relative error
                rel_error = (
                    df_joined.select(
                        ((pl.col(f"{col}_sum") - pl.col(col)).abs() / (pl.col(col).abs() + 1e-10))
                        .mean()
                    ).item()
                )

                errors[col] = rel_error

                if rel_error > 0.01:  # 1% error
                    self.logger.warning(
                        f"  {col}: {rel_error*100:.2f}% average error (energy not conserved)"
                    )
                else:
                    self.logger.info(f"  {col}: ✓ Energy conserved ({rel_error*100:.4f}% error)")

        return errors