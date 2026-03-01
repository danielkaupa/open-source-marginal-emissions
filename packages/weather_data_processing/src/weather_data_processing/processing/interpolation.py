# packages/weather_data_processing/src/weather_data_processing/processing/interpolation.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Temporal Interpolation Engine
==============================

Interpolate hourly ERA-style weather data to half-hourly resolution.

For each file, interpolates to half-hourly resolution using:
  - Static forward-fill for static fields (e.g., region fractions).
  - Midpoint averages for intensive (instantaneous/mean) fields
    (e.g., temperature, clouds, winds, vegetation).
  - A rate-shaped split for radiative extensive totals
    (e.g., short-wave/long-wave radiation, UV).
  - An even-split (midpoint-based) for extensive precipitation totals.

All variable names use ERA5 shortnames (e.g., t2m, ssr, tp).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Literal

import polars as pl
from polars.datatypes import Datetime, Utf8, Int64, Int32

from ..utils.logging import VerboseLogger


# =============================================================================
# Variable Classifications (ERA5 shortnames)
# =============================================================================

# Static fields (forward-fill, no interpolation)
DEFAULT_STATIC_COLS = [
    "frac_in_region",
]

# Intensive fields (midpoint average) - ERA5 shortnames
DEFAULT_INTENSIVE_COLS = [
    "t2m",      # 2m temperature
    "tcc",      # total cloud cover
    "hcc",      # high cloud cover
    "mcc",      # medium cloud cover
    "lcc",      # low cloud cover
    "kx",       # K-index
    "u10",      # 10m u-wind
    "v10",      # 10m v-wind
    "u100",     # 100m u-wind
    "v100",     # 100m v-wind
    "cvh",      # high vegetation cover
    "cvl",      # low vegetation cover
    "lai_hv",   # leaf area index high vegetation
    "lai_lv",   # leaf area index low vegetation
]

# Extensive radiation fields (rate-shaped split) - ERA5 shortnames
DEFAULT_RATE_SHAPED_COLS = [
    "ssrdc",    # surface solar radiation downward clear-sky
    "cdir",     # clear-sky direct solar radiation
    "ssr",      # surface net solar radiation
    "ssrc",     # surface net solar radiation clear-sky
    "ssrd",     # surface solar radiation downwards
    "fdir",     # direct solar radiation
    "str",      # surface net thermal radiation
    "strc",     # surface net thermal radiation clear-sky
    "strd",     # surface thermal radiation downwards
    "strdc",    # surface thermal radiation downward clear-sky
    "tsr",      # top net solar radiation
    "tsrc",     # top net solar radiation clear-sky
    "ttr",      # top net thermal radiation
    "ttrc",     # top net thermal radiation clear-sky
    "uvb",      # downward UV radiation at surface
]

# Extensive precipitation fields (even-split) - ERA5 shortnames
DEFAULT_EVEN_SPLIT_COLS = [
    "tp",       # total precipitation
]

# Columns to clamp to [0, 1] after interpolation - ERA5 shortnames
DEFAULT_CLAMP_COLS = [
    "tcc",      # total cloud cover
    "hcc",      # high cloud cover
    "mcc",      # medium cloud cover
    "lcc",      # low cloud cover
    "cvh",      # high vegetation cover
    "cvl",      # low vegetation cover
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
# Helper functions (ported from proven working code)
# =============================================================================


def _ensure_datetime_unit(
    lf: pl.LazyFrame,
    ts_col: str,
    precision_unit: str,
) -> pl.LazyFrame:
    """Ensure that a timestamp column uses a specific time unit.

    Handles Datetime (cast), Utf8 (parse+cast), and Int epoch (from_epoch).
    """
    schema = lf.collect_schema()

    if ts_col not in schema:
        raise ValueError(f"Timestamp column '{ts_col}' not found in file schema.")

    dtype = schema[ts_col]

    if isinstance(dtype, Datetime):
        return lf.with_columns(pl.col(ts_col).dt.cast_time_unit(precision_unit))

    if isinstance(dtype, Utf8):
        return lf.with_columns(
            pl.col(ts_col)
            .str.strptime(pl.Datetime, strict=False)
            .dt.cast_time_unit(precision_unit)
        )

    if isinstance(dtype, (Int64, Int32)):
        return lf.with_columns(
            pl.from_epoch(pl.col(ts_col), unit=precision_unit).alias(ts_col)
        )

    raise TypeError(
        f"Timestamp column '{ts_col}' has unsupported dtype {dtype}. "
        "Expected Datetime, Utf8, or integer epoch."
    )


def _with_next(
    lf: pl.LazyFrame,
    grouping_cols: Sequence[str],
    ts_col: str,
    cols_to_shift: Sequence[str],
    require_exact_hour: bool = True,
) -> pl.LazyFrame:
    """Attach ``__next`` columns, aligned by group and timestamp.

    Filters to rows with exactly 60-minute gaps to the next row.
    """
    lf = lf.sort([*grouping_cols, ts_col])

    next_exprs = [
        pl.col(c).shift(-1).over(grouping_cols).alias(f"{c}__next")
        for c in cols_to_shift
    ]
    lf2 = lf.with_columns(
        pl.col(ts_col).shift(-1).over(grouping_cols).alias(f"{ts_col}__next"),
        *next_exprs,
    )

    if require_exact_hour:
        lf2 = lf2.filter(
            (pl.col(f"{ts_col}__next") - pl.col(ts_col)) == pl.duration(minutes=60)
        )

    return lf2


def _merge_parts_on_keys(
    parts: Sequence[pl.LazyFrame],
    keys: Sequence[str],
) -> Optional[pl.LazyFrame]:
    """Horizontally merge multiple LazyFrames that share the same key columns."""
    if not parts:
        return None

    out = parts[0]
    for p in parts[1:]:
        out = out.join(p, on=keys, how="left")

    return out


def _make_rate_shaped_halves(
    lf: pl.LazyFrame,
    group_cols: Sequence[str],
    ts_col: str,
    cols: Sequence[str],
    end_of_interval: bool = True,
    logger: Optional[VerboseLogger] = None,
) -> Tuple[pl.LazyFrame, pl.LazyFrame]:
    """Split hourly accumulated radiation totals into two 30-minute totals
    using a linear-rate model, conserving energy exactly.

    Each value E(t) is accumulated over the preceding hour: (t-1h, t].
    Splits into:
      - First half:  E1 over (t-1h, t-30min], timestamp = t-30min
      - Second half: E2 over (t-30min, t],     timestamp = t
    """
    lf_sorted = lf.sort([*group_cols, ts_col])

    # Attach prev/next values; keep rows with exact 60-min gap OR last row per group
    # (last row has null __dt_next; expressions handle null next via fallback to E/2)
    base = (
        lf_sorted.with_columns(
            pl.col(ts_col).shift(-1).over(group_cols).alias(f"{ts_col}__next"),
            *[
                pl.col(c).shift(1).over(group_cols).alias(f"{c}__prev")
                for c in cols
            ],
            *[
                pl.col(c).shift(-1).over(group_cols).alias(f"{c}__next")
                for c in cols
            ],
        )
        .with_columns(
            (pl.col(f"{ts_col}__next") - pl.col(ts_col)).alias("__dt_next")
        )
        .filter(
            (pl.col("__dt_next") == pl.duration(minutes=60))
            | pl.col("__dt_next").is_null()  # include last row per group
        )
        .drop("__dt_next", f"{ts_col}__next")
    )

    # Build expressions for first and second half-hour energies
    first_exprs: List[pl.Expr] = []
    second_exprs: List[pl.Expr] = []

    for c in cols:
        e_prev = pl.col(f"{c}__prev")
        e_curr = pl.col(c)
        e_next = pl.col(f"{c}__next")

        # Interpreting totals as "rates" over unit-length hours
        r_prev = e_prev
        r_curr = e_curr
        r_next = e_next

        # Endpoint rate estimates at hour boundaries
        r0 = pl.when(r_prev.is_not_null()).then((r_prev + r_curr) / 2.0).otherwise(r_curr)
        r1 = pl.when(r_next.is_not_null()).then((r_curr + r_next) / 2.0).otherwise(r_curr)

        # Provisional half-hour energies under linear rate across the hour
        # First half (0 -> 0.5):  E1* = 0.5*r0 + (r1 - r0)/8
        # Second half (0.5 -> 1): E2* = 0.5*r1 - (r1 - r0)/8
        e1_star = (0.5 * r0 + (r1 - r0) / 8.0)
        e2_star = (0.5 * r1 - (r1 - r0) / 8.0)

        sum_star = e1_star + e2_star

        # Scale to enforce exact conservation: E1 + E2 == E_curr
        scale = pl.when(sum_star.abs() > 0).then(e_curr / sum_star).otherwise(1.0)

        e1 = (e1_star * scale).alias(c)
        e2 = (e2_star * scale).alias(c)

        first_exprs.append(e1)
        second_exprs.append(e2)

    # Timestamps: backward-looking ERA5 convention
    if end_of_interval:
        ts_first = (pl.col(ts_col) - pl.duration(minutes=30)).alias(ts_col)
        ts_second = pl.col(ts_col).alias(ts_col)
    else:
        ts_first = (pl.col(ts_col) - pl.duration(minutes=60)).alias(ts_col)
        ts_second = (pl.col(ts_col) - pl.duration(minutes=30)).alias(ts_col)

    first_rows = base.select([*group_cols, ts_first, *first_exprs])
    second_rows = base.select([*group_cols, ts_second, *second_exprs])

    return first_rows, second_rows


def _make_even_split_halves(
    lf: pl.LazyFrame,
    group_cols: Sequence[str],
    ts_col: str,
    extensive_cols: Sequence[str],
    end_of_interval: bool = True,
) -> Tuple[pl.LazyFrame, pl.LazyFrame]:
    """Split hourly extensive totals into two half-hour totals via midpoint split.

    Uses cumulative sums for a smooth midpoint-based split.
    Backward-looking ERA5 timestamps.
    """
    lf = lf.sort([*group_cols, ts_col])
    cumulative = {c: f"__cum__{c}" for c in extensive_cols}

    lf_cum = lf.with_columns(
        *[
            pl.col(c).cum_sum().over(group_cols).alias(cumulative[c])
            for c in extensive_cols
        ]
    )

    w = (
        lf_cum.with_columns(
            pl.col(ts_col).shift(-1).over(group_cols).alias(f"{ts_col}__next"),
            *[
                pl.col(cumulative[c]).shift(-1).over(group_cols).alias(
                    f"{cumulative[c]}__next"
                )
                for c in extensive_cols
            ],
        )
        .with_columns(
            (pl.col(f"{ts_col}__next") - pl.col(ts_col)).alias("__dt")
        )
        .filter(
            (pl.col("__dt") == pl.duration(minutes=60))
            | pl.col("__dt").is_null()  # include last row per group
        )
        .drop("__dt", f"{ts_col}__next")
    )

    # Backward-looking timestamps
    if end_of_interval:
        ts_first = (pl.col(ts_col) - pl.duration(minutes=30)).alias(ts_col)
        ts_second = pl.col(ts_col).alias(ts_col)
    else:
        ts_first = (pl.col(ts_col) - pl.duration(minutes=60)).alias(ts_col)
        ts_second = (pl.col(ts_col) - pl.duration(minutes=30)).alias(ts_col)

    # When cum_next is null (last row per group), fall back to E/2
    first_exprs = [
        pl.when(pl.col(f"{cumulative[c]}__next").is_not_null())
        .then(
            (pl.col(cumulative[c]) + pl.col(f"{cumulative[c]}__next")) / 2.0
            - pl.col(cumulative[c])
        )
        .otherwise(pl.col(c) / 2.0)
        .alias(c)
        for c in extensive_cols
    ]
    second_exprs = [
        pl.when(pl.col(f"{cumulative[c]}__next").is_not_null())
        .then(
            pl.col(f"{cumulative[c]}__next")
            - (pl.col(cumulative[c]) + pl.col(f"{cumulative[c]}__next")) / 2.0
        )
        .otherwise(pl.col(c) / 2.0)
        .alias(c)
        for c in extensive_cols
    ]

    first_rows = w.select([*group_cols, ts_first, *first_exprs])
    second_rows = w.select([*group_cols, ts_second, *second_exprs])

    return first_rows, second_rows


def _align_to_schema(
    lf: Optional[pl.LazyFrame],
    ref_schema: pl.Schema,
    logger: VerboseLogger,
    context: str = "",
) -> Optional[pl.LazyFrame]:
    """Align a LazyFrame to a reference schema.

    Missing columns are filled with nulls. Extra columns are dropped.
    Dtype mismatches are cast with a warning.
    """
    if lf is None:
        return None

    ref_cols = list(ref_schema.names())
    ref_dtypes = {k: v for k, v in ref_schema.items()}

    lf_schema = lf.collect_schema()
    lf_cols = set(lf_schema.names())

    missing = [c for c in ref_cols if c not in lf_cols]
    extra = [c for c in lf_cols if c not in ref_cols]

    if extra:
        logger.debug(
            f"[{context}] Dropping {len(extra)} extra column(s): {sorted(extra)}"
        )
    if missing:
        logger.debug(
            f"[{context}] Adding {len(missing)} missing column(s) as nulls: {sorted(missing)}"
        )

    exprs: List[pl.Expr] = []
    for col in ref_cols:
        ref_dtype = ref_dtypes[col]
        if col in lf_schema:
            lf_dtype = lf_schema[col]
            if lf_dtype != ref_dtype:
                logger.debug(
                    f"[{context}] Casting column '{col}' from {lf_dtype} to {ref_dtype}"
                )
                exprs.append(pl.col(col).cast(ref_dtype).alias(col))
            else:
                exprs.append(pl.col(col))
        else:
            exprs.append(pl.lit(None).cast(ref_dtype).alias(col))

    return lf.select(exprs)


# =============================================================================
# Temporal Interpolator
# =============================================================================

class TemporalInterpolator:
    """
    Interpolate hourly data to half-hourly using appropriate methods.

    All variable names use ERA5 shortnames (t2m, ssr, tp, etc.).

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
        self.rate_shaped_cols = rate_shaped_cols or DEFAULT_RATE_SHAPED_COLS
        self.even_split_cols = even_split_cols or DEFAULT_EVEN_SPLIT_COLS
        self.clamp_cols = clamp_cols or DEFAULT_CLAMP_COLS
        self.datetime_unit = datetime_unit
        self.logger = logger or VerboseLogger("temporal_interpolator", verbose=False)

    def interpolate_file(
        self,
        input_file: Path,
        output_file: Path,
        overwrite: bool = True,
    ) -> InterpolationResult:
        """
        Interpolate a single hourly file to half-hourly.

        Implements the full interpolation policy:
        * Static columns: propagated from the current hour to :30.
        * Intensive columns: midpoint average between current and next hour.
        * Solar/radiative extensives: split using a rate-shaped model.
        * Other extensives (precipitation): split via even (midpoint) splitting.
        * Extensives for :00 are overwritten by the second-half totals.
        * Dec 31 23:30 of the last day is left for boundary_fix to handle.

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
        t_start = time.perf_counter()

        if output_file.exists() and not overwrite:
            self.logger.debug(f"Skipping {output_file.name} (exists)")
            return None

        self.logger.info(f"Interpolating {input_file.name}", force=True)

        # =====================================================================
        # 1. Load + normalise time unit
        # =====================================================================
        lf = pl.scan_parquet(str(input_file))
        lf = _ensure_datetime_unit(lf, self.timestamp_col, precision_unit=self.datetime_unit)
        schema = lf.collect_schema()
        actual_cols = schema.names()

        rows_before = lf.select(pl.len()).collect().item()
        self.logger.info(
            f"  Loaded: {rows_before:,} rows, {len(actual_cols)} columns"
        )

        # Filter column lists to only those present in the data
        static_present = [c for c in self.static_cols if c in actual_cols]
        intensive_present = [c for c in self.intensive_cols if c in actual_cols]
        rate_shaped_present = [c for c in self.rate_shaped_cols if c in actual_cols]
        even_split_present = [c for c in self.even_split_cols if c in actual_cols]

        # Include any ADM columns as static
        adm_cols = [c for c in actual_cols if c.startswith("adm")]
        all_static = list(dict.fromkeys(static_present + adm_cols))

        keys = [*self.group_cols, self.timestamp_col]

        # =====================================================================
        # 2. Generate FIRST and SECOND half sets for extensive fields
        # =====================================================================
        first_parts: List[pl.LazyFrame] = []
        second_parts: List[pl.LazyFrame] = []

        if rate_shaped_present:
            self.logger.info(
                f"  Rate-shaped split for {len(rate_shaped_present)} radiation column(s)..."
            )
            solar_first, solar_second = _make_rate_shaped_halves(
                lf,
                group_cols=self.group_cols,
                ts_col=self.timestamp_col,
                cols=rate_shaped_present,
                end_of_interval=True,
                logger=self.logger,
            )
            first_parts.append(solar_first)
            second_parts.append(solar_second)

        if even_split_present:
            self.logger.info(
                f"  Even-split for {len(even_split_present)} extensive column(s)..."
            )
            even_first, even_second = _make_even_split_halves(
                lf,
                group_cols=self.group_cols,
                ts_col=self.timestamp_col,
                extensive_cols=even_split_present,
                end_of_interval=True,
            )
            first_parts.append(even_first)
            second_parts.append(even_second)

        first_rows = _merge_parts_on_keys(first_parts, keys)
        second_rows = _merge_parts_on_keys(second_parts, keys)

        # =====================================================================
        # 3. Overwrite hourly :00 extensives using second-half totals
        # =====================================================================
        hourly_updated = lf
        all_extensive_cols = list(rate_shaped_present) + list(even_split_present)

        if second_rows is not None and all_extensive_cols:
            self.logger.info(
                f"  Overwriting :00 extensives with second-half totals ({len(all_extensive_cols)} cols)"
            )
            suffix = "__second"
            hourly_updated = (
                lf.join(second_rows, on=keys, how="left", suffix=suffix)
                .with_columns(
                    *[
                        pl.coalesce([pl.col(f"{c}{suffix}"), pl.col(c)]).alias(c)
                        for c in all_extensive_cols
                    ]
                )
                .drop(*[f"{c}{suffix}" for c in all_extensive_cols], strict=False)
            )

        # =====================================================================
        # 4. Build :30 rows for static + intensive columns
        # =====================================================================
        cols_for_next = list(dict.fromkeys(intensive_present))
        with_next = _with_next(
            lf=hourly_updated,
            grouping_cols=self.group_cols,
            ts_col=self.timestamp_col,
            cols_to_shift=cols_for_next,
            require_exact_hour=True,
        )

        ts_mid = (pl.col(self.timestamp_col) + pl.duration(minutes=30)).alias(
            self.timestamp_col
        )

        static_cols_for_30 = [
            c for c in all_static
            if c not in self.group_cols and c != self.timestamp_col
        ]

        exprs_30: List[pl.Expr] = []

        # Static: forward-fill from current hour
        for c in static_cols_for_30:
            exprs_30.append(pl.col(c).alias(c))

        # Intensive: midpoint average
        for c in intensive_present:
            exprs_30.append(
                ((pl.col(c) + pl.col(f"{c}__next")) / 2.0).alias(c)
            )

        halfhour_30 = with_next.select([*self.group_cols, ts_mid, *exprs_30])

        # Attach first-half extensive totals into :30 frame
        if first_rows is not None:
            self.logger.info("  Joining first-half extensive totals into :30 frame...")
            halfhour_30 = halfhour_30.join(first_rows, on=keys, how="left")

        # Apply clamping for [0, 1] fields on :30 rows
        clamp_cols = [
            c for c in self.clamp_cols
            if c in halfhour_30.collect_schema().names()
        ]
        if clamp_cols:
            halfhour_30 = halfhour_30.with_columns(
                *[pl.col(c).clip(0.0, 1.0) for c in clamp_cols]
            )
            self.logger.info(f"  Clamped {len(clamp_cols)} column(s) to [0,1]")

        # =====================================================================
        # 5. Schema alignment
        # =====================================================================
        # Note: 23:30 rows are already in halfhour_30 (from _with_next on
        # 23:00→00:00 pairs) with first-half extensives joined in.
        # The only missing 23:30 is the last day of the year (Dec 31),
        # which boundary_fix handles using the next year's Jan 1 00:00.
        ref_schema = hourly_updated.collect_schema()

        hourly_aligned = _align_to_schema(
            hourly_updated, ref_schema, self.logger, context="hourly_updated"
        )
        halfhour_30_aligned = _align_to_schema(
            halfhour_30, ref_schema, self.logger, context="halfhour_30"
        )

        out_cols = list(ref_schema.names())

        # =====================================================================
        # 6. Final concatenation
        # =====================================================================
        frames: List[pl.LazyFrame] = [
            hourly_aligned.select(out_cols),        # :00 rows (second-half extensives)
            halfhour_30_aligned.select(out_cols),   # :30 rows (first-half extensives)
        ]

        self.logger.info("  Collecting and sorting...", force=True)
        final_df = pl.concat(frames, how="vertical_relaxed").sort(keys).collect()

        # =====================================================================
        # 8. Write result
        # =====================================================================
        os.makedirs(output_file.parent, exist_ok=True)
        final_df.write_parquet(str(output_file), compression="snappy", statistics=True)

        dt = time.perf_counter() - t_start

        rows_after = len(final_df)

        # Check if year boundary issue exists (use in-memory data, not re-read)
        has_boundary = final_df.filter(
            (pl.col(self.timestamp_col).dt.month() == 12)
            & (pl.col(self.timestamp_col).dt.day() == 31)
            & (pl.col(self.timestamp_col).dt.hour() == 23)
            & (pl.col(self.timestamp_col).dt.minute() == 30)
        ).height > 0

        del final_df  # free memory before returning

        self.logger.info(
            f"  Complete: {rows_before:,} -> {rows_after:,} rows ({dt:.2f}s)",
            force=True,
        )

        if has_boundary:
            self.logger.warning(
                "  Year boundary detected: Dec 31 23:30 needs fixing"
            )

        return InterpolationResult(
            output_file=output_file,
            input_file=input_file,
            rows_before=rows_before,
            rows_after=rows_after,
            processing_time_s=dt,
            has_boundary_issue=has_boundary,
        )

    def _check_boundary_issue(self, output_file: Path) -> bool:
        """Check if Dec 31 23:30 exists with potential null intensives."""
        lf = pl.scan_parquet(str(output_file))
        boundary_check = lf.filter(
            (pl.col(self.timestamp_col).dt.month() == 12)
            & (pl.col(self.timestamp_col).dt.day() == 31)
            & (pl.col(self.timestamp_col).dt.hour() == 23)
            & (pl.col(self.timestamp_col).dt.minute() == 30)
        )
        return boundary_check.select(pl.len()).collect().item() > 0
