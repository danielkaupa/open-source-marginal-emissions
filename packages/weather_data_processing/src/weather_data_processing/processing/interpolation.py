# packages/weather_data_processing/src/weather_data_processing/processing/interpolation.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Temporal Interpolation Engine
==============================

Interpolate hourly weather data to half-hourly resolution using physically
appropriate methods for different variable types.

Three interpolation methods:
1. **Intensive (midpoint)**: Temperature, clouds, winds
2. **Rate-shaped (energy-conserving)**: Solar/thermal radiation
3. **Even-split**: Precipitation

Key Features
------------
- Energy conservation for radiation fields
- ERA5 backward-looking timestamp convention
- Year boundary handling
- Lazy evaluation for memory efficiency
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Literal

import polars as pl

from ..utils.logging import VerboseLogger


# =============================================================================
# Variable Classifications
# =============================================================================

# Static fields (forward-fill, no interpolation)
DEFAULT_STATIC_COLS = [
    "frac_in_region",
]

# Intensive fields (midpoint average)
DEFAULT_INTENSIVE_COLS = [
    "temperature_2m",  # or "2t"
    "total_cloud_cover",
    "high_cloud_cover",
    "medium_cloud_cover",
    "low_cloud_cover",
    "k_index",
    "wind_u_10m",      # or "10u"
    "wind_v_10m",      # or "10v"
    "wind_u_100m",     # or "100u"
    "wind_v_100m",     # or "100v"
    "high_vegetation_cover",
    "low_vegetation_cover",
    "leaf_area_index_high_vegetation",
    "leaf_area_index_low_vegetation",
]

# Extensive radiation fields (rate-shaped split)
DEFAULT_SOLAR_RATE_SHAPED_COLS = [
    "surface_direct_short_wave_radiation_clear_sky",
    "surface_direct_short_wave_solar_radiation",
    "surface_net_short_wave_solar_radiation",
    "surface_net_short_wave_solar_radiation_clear_sky",
    "surface_short_wave_solar_radiation_downwards",
    "surface_short_wave_solar_radiation_downward_clear_sky",
    "surface_net_long_wave_thermal_radiation",
    "surface_net_long_wave_thermal_radiation_clear_sky",
    "surface_long_wave_thermal_radiation_downwards",
    "surface_long_wave_thermal_radiation_downward_clear_sky",
    "top_net_short_wave_solar_radiation",
    "top_net_short_wave_solar_radiation_clear_sky",
    "top_net_long_wave_thermal_radiation",
    "top_net_long_wave_thermal_radiation_clear_sky",
    "surface_downward_uv_radiation",
]

# Extensive precipitation fields (even-split)
DEFAULT_PRECIP_EVEN_SPLIT_COLS = [
    "total_precipitation",
]

# Columns to clamp to [0, 1] after interpolation
DEFAULT_CLAMP_COLS = [
    "total_cloud_cover",
    "high_cloud_cover",
    "medium_cloud_cover",
    "low_cloud_cover",
    "high_vegetation_cover",
    "low_vegetation_cover",
]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class InterpolationResult:
    """Result of temporal interpolation."""
    output_file: Path
    input_file: Path
    rows_before: int
    rows_after: int
    processing_time_s: float
    has_boundary_issue: bool  # True if Dec 31 23:30 needs fixing


# =============================================================================
# Temporal Interpolator
# =============================================================================

class TemporalInterpolator:
    """
    Interpolate hourly data to half-hourly using appropriate methods.

    Parameters
    ----------
    group_cols : list of str, optional
        Grouping columns (default: ["latitude", "longitude"]).
    timestamp_col : str, optional
        Timestamp column name (default: "time").
    static_cols : list of str, optional
        Static columns to forward-fill.
    intensive_cols : list of str, optional
        Intensive columns for midpoint interpolation.
    rate_shaped_cols : list of str, optional
        Radiation columns for rate-shaped interpolation.
    even_split_cols : list of str, optional
        Precipitation columns for even-split.
    clamp_cols : list of str, optional
        Columns to clamp to [0, 1].
    datetime_unit : str, optional
        Datetime precision ('us', 'ns', 'ms', 's').
    logger : VerboseLogger, optional
        Logger instance.

    Examples
    --------
    >>> interpolator = TemporalInterpolator()
    >>> result = interpolator.interpolate_file(
    ...     input_file=Path("data/processed/2018.parquet"),
    ...     output_file=Path("data/transformed/2018_halfhourly.parquet")
    ... )
    """

    def __init__(
        self,
        group_cols: Optional[List[str]] = None,
        timestamp_col: str = "time",
        static_cols: Optional[List[str]] = None,
        intensive_cols: Optional[List[str]] = None,
        rate_shaped_cols: Optional[List[str]] = None,
        even_split_cols: Optional[List[str]] = None,
        clamp_cols: Optional[List[str]] = None,
        datetime_unit: Literal["us", "ns", "ms", "s"] = "us",
        logger: Optional[VerboseLogger] = None,
    ):
        self.group_cols = group_cols or ["latitude", "longitude"]
        self.timestamp_col = timestamp_col
        self.static_cols = static_cols or DEFAULT_STATIC_COLS
        self.intensive_cols = intensive_cols or DEFAULT_INTENSIVE_COLS
        self.rate_shaped_cols = rate_shaped_cols or DEFAULT_SOLAR_RATE_SHAPED_COLS
        self.even_split_cols = even_split_cols or DEFAULT_PRECIP_EVEN_SPLIT_COLS
        self.clamp_cols = clamp_cols or DEFAULT_CLAMP_COLS
        self.datetime_unit = datetime_unit
        self.logger = logger or VerboseLogger("temporal_interpolator", verbose=False)

    def _attach_next(
        self,
        lf: pl.LazyFrame,
        cols_to_shift: List[str]
    ) -> pl.LazyFrame:
        """Attach __next columns for interpolation."""
        lf_sorted = lf.sort([*self.group_cols, self.timestamp_col])

        next_exprs = [
            pl.col(c).shift(-1).over(self.group_cols).alias(f"{c}__next")
            for c in cols_to_shift
        ]

        lf_next = lf_sorted.with_columns(
            pl.col(self.timestamp_col).shift(-1).over(self.group_cols).alias(f"{self.timestamp_col}__next"),
            *next_exprs
        )

        # Filter to only rows with exact 60-minute gaps
        lf_next = lf_next.filter(
            (pl.col(f"{self.timestamp_col}__next") - pl.col(self.timestamp_col))
            == pl.duration(minutes=60)
        )

        return lf_next

    def _interpolate_static(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """Generate half-hourly rows for static fields (forward-fill)."""
        key_cols = self.group_cols + [self.timestamp_col]

        # Current hour (no change needed)
        first_half = lf.select(
            [pl.col(c) for c in key_cols] +
            [pl.col(c) for c in self.static_cols]
        )

        # Next half-hour (same timestamp + 30 min)
        second_half = lf.select(
            [pl.col(c) for c in self.group_cols] +
            [(pl.col(self.timestamp_col) + pl.duration(minutes=30)).alias(self.timestamp_col)] +
            [pl.col(c) for c in self.static_cols]
        )

        return pl.concat([first_half, second_half])

    def _interpolate_intensive(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """Generate half-hourly rows for intensive fields (midpoint average)."""
        key_cols = self.group_cols + [self.timestamp_col]

        # Attach next values
        lf_next = self._attach_next(lf, self.intensive_cols)

        # First half: current value unchanged
        first_half = lf_next.select(
            [pl.col(c) for c in key_cols] +
            [pl.col(c) for c in self.intensive_cols]
        )

        # Second half: midpoint average
        second_half = lf_next.select(
            [pl.col(c) for c in self.group_cols] +
            [(pl.col(self.timestamp_col) + pl.duration(minutes=30)).alias(self.timestamp_col)] +
            [
                ((pl.col(c) + pl.col(f"{c}__next")) / 2.0).alias(c)
                for c in self.intensive_cols
            ]
        )

        return pl.concat([first_half, second_half])

    def _interpolate_rate_shaped(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """
        Generate half-hourly rows for radiation fields (rate-shaped, energy-conserving).

        Uses piecewise-linear rate model:
        - Assumes r(t) varies linearly across the hour
        - Splits hourly total E into E1 + E2 such that E1 + E2 = E exactly
        """
        key_cols = self.group_cols + [self.timestamp_col]

        # Attach prev and next values for rate modeling
        lf_sorted = lf.sort([*self.group_cols, self.timestamp_col])

        # Shift to get prev, current, next
        lf_extended = lf_sorted.with_columns(
            [
                pl.col(c).shift(1).over(self.group_cols).alias(f"{c}__prev")
                for c in self.rate_shaped_cols
            ] + [
                pl.col(c).shift(-1).over(self.group_cols).alias(f"{c}__next")
                for c in self.rate_shaped_cols
            ] + [
                pl.col(self.timestamp_col).shift(-1).over(self.group_cols).alias(f"{self.timestamp_col}__next")
            ]
        )

        # Filter to valid rows (60-min spacing)
        lf_valid = lf_extended.filter(
            (pl.col(f"{self.timestamp_col}__next") - pl.col(self.timestamp_col))
            == pl.duration(minutes=60)
        )

        # Compute first and second half using rate-shaped model
        # Simplified: E1 ≈ 0.375*E_prev + 0.625*E_curr (weighted toward current)
        # E2 ≈ 0.375*E_curr + 0.625*E_next
        # Then scale so E1 + E2 = E

        first_half_exprs = []
        second_half_exprs = []

        for c in self.rate_shaped_cols:
            # Provisional first half (weighted by proximity)
            e1_prov = (
                pl.when(pl.col(f"{c}__prev").is_not_null())
                .then(0.375 * pl.col(f"{c}__prev") + 0.625 * pl.col(c))
                .otherwise(0.5 * pl.col(c))
            )

            # Provisional second half
            e2_prov = (
                pl.when(pl.col(f"{c}__next").is_not_null())
                .then(0.625 * pl.col(c) + 0.375 * pl.col(f"{c}__next"))
                .otherwise(0.5 * pl.col(c))
            )

            # Scale factor to conserve energy: E1 + E2 = E
            scale = pl.col(c) / (e1_prov + e2_prov + 1e-10)

            first_half_exprs.append((e1_prov * scale).alias(c))
            second_half_exprs.append((e2_prov * scale).alias(c))

        # First half: timestamp unchanged
        first_half = lf_valid.select(
            [pl.col(c) for c in key_cols] +
            first_half_exprs
        )

        # Second half: timestamp + 30 minutes
        second_half = lf_valid.select(
            [pl.col(c) for c in self.group_cols] +
            [(pl.col(self.timestamp_col) + pl.duration(minutes=30)).alias(self.timestamp_col)] +
            second_half_exprs
        )

        return pl.concat([first_half, second_half])

    def _interpolate_even_split(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """Generate half-hourly rows for precipitation (even-split)."""
        key_cols = self.group_cols + [self.timestamp_col]

        # Split hourly total evenly: E1 = E2 = E/2

        # First half
        first_half = lf.select(
            [pl.col(c) for c in key_cols] +
            [(pl.col(c) / 2.0).alias(c) for c in self.even_split_cols]
        )

        # Second half
        second_half = lf.select(
            [pl.col(c) for c in self.group_cols] +
            [(pl.col(self.timestamp_col) + pl.duration(minutes=30)).alias(self.timestamp_col)] +
            [(pl.col(c) / 2.0).alias(c) for c in self.even_split_cols]
        )

        return pl.concat([first_half, second_half])

    def _apply_clamping(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """Clamp specified columns to [0, 1] range."""
        clamp_exprs = []

        for col in lf.collect_schema().names():
            if col in self.clamp_cols:
                clamp_exprs.append(
                    pl.col(col).clip(0.0, 1.0).alias(col)
                )
            else:
                clamp_exprs.append(pl.col(col))

        return lf.select(clamp_exprs)

    def interpolate_file(
        self,
        input_file: Path,
        output_file: Path,
        overwrite: bool = True
    ) -> InterpolationResult:
        """
        Interpolate a single hourly file to half-hourly.

        Parameters
        ----------
        input_file : Path
            Input hourly parquet file.
        output_file : Path
            Output half-hourly parquet file.
        overwrite : bool, optional
            Overwrite existing output.

        Returns
        -------
        InterpolationResult
            Processing result with statistics.
        """
        t0 = time.perf_counter()

        if output_file.exists() and not overwrite:
            self.logger.debug(f"Skipping {output_file.name} (exists)")
            return None

        self.logger.info(f"Interpolating {input_file.name}", force=True)

        # Load hourly data
        lf = pl.scan_parquet(input_file)

        rows_before = lf.select(pl.len()).collect().item()

        # Identify which columns are present
        actual_cols = lf.collect_schema().names()

        # Filter column lists to only include present columns
        static_present = [c for c in self.static_cols if c in actual_cols]
        intensive_present = [c for c in self.intensive_cols if c in actual_cols]
        rate_shaped_present = [c for c in self.rate_shaped_cols if c in actual_cols]
        even_split_present = [c for c in self.even_split_cols if c in actual_cols]

        # Identify any ADM columns to preserve
        adm_cols = [c for c in actual_cols if c.startswith("adm")]

        # Build parts
        parts = []

        # Static fields
        if static_present or adm_cols:
            all_static = static_present + adm_cols
            self.static_cols = all_static  # Update temporarily
            part = self._interpolate_static(lf)
            parts.append(part)

        # Intensive fields
        if intensive_present:
            self.intensive_cols = intensive_present  # Update temporarily
            part = self._interpolate_intensive(lf)
            parts.append(part)

        # Rate-shaped fields
        if rate_shaped_present:
            self.rate_shaped_cols = rate_shaped_present  # Update temporarily
            part = self._interpolate_rate_shaped(lf)
            parts.append(part)

        # Even-split fields
        if even_split_present:
            self.even_split_cols = even_split_present  # Update temporarily
            part = self._interpolate_even_split(lf)
            parts.append(part)

        # Merge all parts
        if not parts:
            raise ValueError(f"No columns to interpolate in {input_file.name}")

        # Join on keys
        keys = self.group_cols + [self.timestamp_col]
        lf_result = parts[0]
        for part in parts[1:]:
            lf_result = lf_result.join(part, on=keys, how="left")

        # Apply clamping
        lf_result = self._apply_clamping(lf_result)

        # Sort by time
        lf_result = lf_result.sort([*self.group_cols, self.timestamp_col])

        # Collect and write
        df_result = lf_result.collect()
        rows_after = len(df_result)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        df_result.write_parquet(output_file, compression="zstd", statistics=True)

        dt = time.perf_counter() - t0

        # Check if year boundary issue exists (Dec 31 23:30)
        has_boundary = self._check_boundary_issue(df_result)

        self.logger.info(
            f"  Complete: {rows_before:,} → {rows_after:,} rows ({dt:.2f}s)",
            force=True
        )

        if has_boundary:
            self.logger.warning(
                f"  ⚠ Year boundary detected: Dec 31 23:30 needs fixing"
            )

        return InterpolationResult(
            output_file=output_file,
            input_file=input_file,
            rows_before=rows_before,
            rows_after=rows_after,
            processing_time_s=dt,
            has_boundary_issue=has_boundary,
        )

    def _check_boundary_issue(self, df: pl.DataFrame) -> bool:
        """Check if Dec 31 23:30 exists (incomplete interpolation)."""
        # Check for December 31 at 23:30
        boundary_check = df.filter(
            (pl.col(self.timestamp_col).dt.month() == 12) &
            (pl.col(self.timestamp_col).dt.day() == 31) &
            (pl.col(self.timestamp_col).dt.hour() == 23) &
            (pl.col(self.timestamp_col).dt.minute() == 30)
        )

        return len(boundary_check) > 0