"""
Progressive Gap Filling Pipeline
=================================

This module implements a sophisticated multi-stage gap filling approach that progressively
fills data gaps using a combination of linear interpolation and gradient-based methods.

The core philosophy is to start with the easiest gaps (short duration, linear interpolation)
and progressively tackle harder gaps, with each stage benefiting from the cleaner data
produced by previous stages. This creates a bootstrapping effect where:

1. Short linear fills create more complete donor days for gradient method
2. Gradient fills create better context for longer linear interpolations
3. Each pass increases the pool of clean reference data for subsequent passes

The pipeline saves output at each major stage, allowing detailed analysis and visualization
of which gaps are filled when, and how the data quality evolves through the process.

Author: Daniel Kaupa
Date: 2026-02-16
"""

import logging
from typing import Optional, List, Dict, Tuple, Any, Sequence, Iterable
from pathlib import Path
from datetime import datetime, timedelta, date
import math

import polars as pl
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def slots_per_day(step_minutes: int) -> int:
    """
    Calculate how many time slots fit in a 24-hour day.

    For 5-minute data: 24 hours * 60 minutes / 5 minutes = 288 slots per day
    This is used throughout the gradient method to ensure slot indices stay within bounds.
    """
    if 1440 % int(step_minutes) != 0:
        raise ValueError(f"step_minutes ({step_minutes}) must divide evenly into 1440 (minutes per day)")
    return (24 * 60) // int(step_minutes)


def add_date_and_slot(
    df: pl.DataFrame,
    timestamp_col: str,
    step_minutes: int,
) -> pl.DataFrame:
    """
    Add helper columns for date-slot indexing used by gradient method.

    This function adds two critical columns:
    - _date: The calendar date (date portion of timestamp)
    - _slot: The within-day slot number (0 to slots_per_day-1)

    The slot number represents which time slot within a day this observation falls into.
    For example, with 5-minute data:
    - 00:00 → slot 0
    - 00:05 → slot 1
    - 12:00 → slot 144
    - 23:55 → slot 287

    These columns allow the gradient method to find corresponding times across different days.
    For instance, "slot 144 on 2024-01-15" corresponds to "slot 144 on 2024-01-22" (same time,
    different day), which is essential for finding similar donor days.

    Parameters
    ----------
    df : pl.DataFrame
        Input dataframe with timestamp column
    timestamp_col : str
        Name of the timestamp column
    step_minutes : int
        Time resolution in minutes (typically 5)

    Returns
    -------
    pl.DataFrame
        Input dataframe with added _date and _slot columns
    """
    spd = slots_per_day(step_minutes)

    # Remove any existing helper columns from previous runs to avoid conflicts
    drop_cols = [c for c in ("_date", "_slot", "_mins") if c in df.columns]
    out = df.drop(drop_cols) if drop_cols else df

    # Cast to Int32 to avoid overflow issues with Int8 (which can only go to 127)
    # This is important because minute values range 0-59, and hour*60 can exceed 127
    h = pl.col(timestamp_col).dt.hour().cast(pl.Int32)
    m = pl.col(timestamp_col).dt.minute().cast(pl.Int32)

    out = out.with_columns([
        pl.col(timestamp_col).dt.date().alias("_date"),
        (h * 60 + m).alias("_mins").cast(pl.Int32),
    ]).with_columns([
        (pl.col("_mins") // int(step_minutes)).cast(pl.Int32).alias("_slot"),
    ]).drop("_mins")

    # Sanity check: slot numbers should be within expected range
    # This catches timestamp corruption or calculation errors early
    smin = out.select(pl.col("_slot").min()).item()
    smax = out.select(pl.col("_slot").max()).item()
    if (smin is None) or (smax is None) or (smin < 0) or (smax >= spd):
        raise AssertionError(
            f"_slot out of bounds: min={smin}, max={smax}, expected 0 to {spd-1}. "
            f"This usually indicates timestamp corruption or overflow in hour/minute calculation."
        )

    return out


def choose_fill_columns(
    df: pl.DataFrame,
    timestamp_col: str = "timestamp",
    fill_cols: Optional[Iterable[str]] = None,
) -> List[str]:
    """
    Determine which columns should be filled with gap-filling methods.

    If specific columns are provided, use those. Otherwise, automatically detect
    all numeric columns (excluding the timestamp column). This automatic detection
    ensures that all generation, demand, and emissions columns get filled consistently.
    """
    if fill_cols is not None:
        return [c for c in fill_cols if c in df.columns and c != timestamp_col]

    # Use Polars' dtype.is_numeric() to find all numeric columns
    return [
        c for c, dtype in df.schema.items()
        if c != timestamp_col and dtype.is_numeric()
    ]


def clamp_nonneg(df: pl.DataFrame, cols: List[str]) -> pl.DataFrame:
    """
    Clamp negative values to zero in specified columns.

    This is necessary because gradient-based filling uses numerical integration,
    which can occasionally produce small negative values due to:
    1. Numerical precision issues
    2. Gradient averaging that doesn't perfectly match boundary conditions
    3. Extrapolation beyond observed ranges

    Since generation values cannot be physically negative, we clamp them to zero.
    Note that emission intensity columns (g_co2_per_kwh, tons_co2_per_mwh) are NOT
    clamped here as they're recalculated from the generation values later.
    """
    return df.with_columns([
        pl.when(pl.col(c) < 0)
          .then(pl.lit(0.0))
          .otherwise(pl.col(c))
          .alias(c)
        for c in cols
    ])


def empty_audit_df_gradient() -> pl.DataFrame:
    """
    Create an empty audit dataframe with the correct schema.

    The audit log tracks which gradient method was used for each gap:
    - gradient_two_sided: Had anchors on both sides of gap
    - gradient_forward: Had anchor before gap only
    - gradient_backward: Had anchor after gap only
    - gradient_seeded_from_blended_donors: No anchors, used donor day values
    - no_donor_gradients: Could not find suitable donor days
    - no_anchor_no_seed: Could not fill at all
    """
    return pl.DataFrame(schema={
        "_date": pl.Date,
        "_slot": pl.Int32,
        "method": pl.Utf8,
    })


def _nanmean_smooth(arr: np.ndarray, k: int) -> np.ndarray:
    """
    Apply NaN-aware moving average smoothing.

    This smoothing is applied to donor day gradients before using them to fill gaps.
    The smoothing reduces noise and creates more realistic filled values by averaging
    gradients across adjacent time slots.

    Why smoothing matters:
    Real electricity demand doesn't change in sharp spikes. Even when an event causes
    demand to rise (e.g., everyone turning on air conditioning), the rise is gradual
    over multiple 5-minute periods. Raw gradients can be noisy due to measurement
    variations or brief anomalies. Smoothing with a window of 3 slots (15 minutes for
    5-minute data) removes noise while preserving genuine demand trends.

    Parameters
    ----------
    arr : np.ndarray
        Array of gradients (first differences)
    k : int
        Window size for smoothing (k=3 means average over 3 adjacent slots)

    Returns
    -------
    np.ndarray
        Smoothed gradients
    """
    if k <= 1:
        # No smoothing requested
        return arr.copy()

    n = len(arr)
    out = np.full(n, np.nan, dtype=float)
    r = k // 2  # Radius around center point

    for i in range(n):
        # Define window bounds, staying within array limits
        lo = max(0, i - r)
        hi = min(n, i + r + 1)
        win = arr[lo:hi]

        # Only compute mean if at least one valid value exists in window
        if np.all(np.isnan(win)):
            out[i] = np.nan
        else:
            out[i] = np.nanmean(win)

    return out


# ============================================================================
# PANDAS-BASED HELPER FUNCTIONS FOR GRADIENT METHOD
# ============================================================================
#
# The gradient method uses Pandas for the core donor day lookup and gradient
# computation because it's heavily index-based. We create a MultiIndex with
# (date, slot) keys, which makes lookups like "get value for Jan 15 at slot 144"
# very fast and clean syntactically.
#
# The overall flow uses Polars for bulk operations and Pandas for the indexed lookups.

def to_unique_date_slot_index(
    work: pl.DataFrame,
    ref_col: str,
    fill_cols: Sequence[str],
    extra_cols: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """
    Convert to a Pandas MultiIndex DataFrame keyed by (date, slot).

    This index structure enables efficient lookup of values for specific dates and time slots,
    which is essential for the gradient method's donor day matching. For example, you can
    quickly ask "What was the demand on January 15th at 2:00 PM (slot 168)?" and get the
    answer with a simple index lookup.

    When there are multiple rows for the same (date, slot) combination (which shouldn't
    happen in clean data but might occur during processing), we keep the row with the
    most non-null values across important columns. This ensures we use the highest-quality
    data available.

    Returns
    -------
    pd.DataFrame
        MultiIndex DataFrame with (date, slot) as index, contains ref_col and fill_cols
    """
    key_cols = list(dict.fromkeys([ref_col] + list(fill_cols) + (list(extra_cols) if extra_cols else [])))
    pdf = work.select(["_date", "_slot", *key_cols]).to_pandas()

    # Ensure dates are Python date objects (not timestamps)
    pdf["_date"] = pd.to_datetime(pdf["_date"]).dt.date

    # Quality score: count how many important columns have non-null values
    # This helps us pick the "best" row if there are duplicates
    pdf["_qual"] = pdf[key_cols].notna().sum(axis=1)

    pdf = (pdf.sort_values(["_date", "_slot", "_qual"], ascending=[True, True, False])
              .drop_duplicates(["_date", "_slot"], keep="first")
              .drop(columns="_qual")
              .set_index(["_date", "_slot"])
              .sort_index())

    assert pdf.index.is_unique, "Date-slot index should be unique after deduplication"
    return pdf


def get_value(
    pdf: pd.DataFrame,
    date_obj: Any,
    slot: int,
    col: str
) -> Optional[float]:
    """
    Retrieve a single value from the (date, slot) indexed DataFrame.

    This is a simple helper that handles the index lookup and None/NaN conversion.
    It's used extensively by the gradient method to check whether donor days have
    complete data at specific time slots.
    """
    try:
        val = pdf.loc[(pd.Timestamp(date_obj).date(), int(slot)), col]
        return None if pd.isna(val) else float(val)
    except KeyError:
        # Date-slot combination doesn't exist in index
        return None


def have_value(
    pdf: pd.DataFrame,
    date_obj: Any,
    slot: int,
    col: str
) -> bool:
    """
    Check if a non-null value exists for (date, slot, column).

    This is used when searching for donor days: we need to verify that a candidate
    donor day actually has complete data at the time slots we're trying to fill.
    """
    return get_value(pdf, date_obj, slot, col) is not None


# ============================================================================
# DONOR DAY SEARCH FUNCTIONS
# ============================================================================

def find_nearest_donor_date(
    pdf: pd.DataFrame,
    *,
    date0,
    slot: int,
    ref_col: str,
    direction: int,
    max_search_days: int,
    prefer_same_weekday: bool = True,
    slot_tolerance: int = 0,
    spd: Optional[int] = None,
) -> Optional[date]:
    """
    Find the nearest date in the specified direction that has data at the target slot.

    This is the core search function for finding donor days. It implements a two-pass
    search strategy:

    Pass 1: If prefer_same_weekday=True, search for days with the same day of week
    (e.g., if filling a gap on Tuesday, prefer other Tuesdays as donors)

    Pass 2: Search for any day regardless of weekday

    Why prefer same weekday? Electricity demand has strong weekly patterns. Weekdays
    typically have different demand profiles than weekends, and even within weekdays
    there can be differences (Monday morning ramps vs. Friday afternoon declines).
    By preferring same-weekday donors, we match these patterns more accurately.

    Parameters
    ----------
    pdf : pd.DataFrame
        MultiIndex DataFrame with (date, slot) index
    date0 : date
        The date we're trying to fill
    slot : int
        The time slot we're trying to fill
    ref_col : str
        Reference column that must be non-null in donor day
    direction : int
        -1 to search backwards in time, +1 to search forwards
    max_search_days : int
        Maximum number of days to search in each direction
    prefer_same_weekday : bool
        Whether to prefer donors with matching day of week
    slot_tolerance : int
        Allow matching nearby slots if exact slot is missing (0 = exact match only)
    spd : int, optional
        Slots per day (needed if slot_tolerance > 0)

    Returns
    -------
    date or None
        The date of a suitable donor day, or None if no donor found within search window
    """
    slot = int(slot)
    direction = int(direction)
    max_search_days = int(max_search_days)
    slot_tolerance = max(0, int(slot_tolerance))

    base_day: date = pd.Timestamp(date0).date()
    base_wd = base_day.weekday()  # Monday=0, Sunday=6

    def _has_coverage(d: date) -> bool:
        """Check if date d has data at (or near) the target slot."""
        if slot_tolerance > 0 and spd:
            # Allow matching nearby slots within tolerance
            lo = max(0, slot - slot_tolerance)
            hi = min(int(spd) - 1, slot + slot_tolerance)
            for ss in range(lo, hi + 1):
                try:
                    v = pdf.loc[(d, ss), ref_col]
                except KeyError:
                    v = np.nan
                if not pd.isna(v):
                    return True
            return False
        else:
            # Exact slot match required
            try:
                v = pdf.loc[(d, slot), ref_col]
            except KeyError:
                return False
            return not pd.isna(v)

    # Pass 1: Prefer same weekday if requested
    if prefer_same_weekday:
        for k in range(1, max_search_days + 1):
            d = (pd.Timestamp(base_day) + pd.Timedelta(days=direction * k)).date()
            if d.weekday() == base_wd and _has_coverage(d):
                return d

    # Pass 2: Any day regardless of weekday
    for k in range(1, max_search_days + 1):
        d = (pd.Timestamp(base_day) + pd.Timedelta(days=direction * k)).date()
        if _has_coverage(d):
            return d

    return None


def donor_gradients_for_slots(
    pdf: pd.DataFrame,
    *,
    donor_date,
    slots: Sequence[int],
    cols: Sequence[str],
    smooth_window_slots: int = 1,
) -> Dict[str, np.ndarray]:
    """
    Compute smoothed gradients (first differences) from a donor day.

    Gradients represent the change in value from one time slot to the next.
    For example, if demand at slot 100 is 150 MW and demand at slot 101 is 153 MW,
    the gradient is +3 MW.

    These gradients capture the "shape" of how demand evolves throughout the day,
    independent of the absolute level. By averaging gradients from multiple donor
    days and integrating them, we can fill gaps while preserving realistic temporal
    patterns.

    The smoothing step removes noise from the gradients, creating smoother filled
    values. Extensive testing showed that smooth_window_slots=3 produces optimal
    results: values of 1 are too spiky, while values of 5+ over-smooth and lose
    important short-term variations.

    Parameters
    ----------
    pdf : pd.DataFrame
        MultiIndex DataFrame with donor day data
    donor_date : date
        The date to extract gradients from
    slots : Sequence[int]
        Which slots to compute gradients for
    cols : Sequence[str]
        Which columns to compute gradients for
    smooth_window_slots : int
        Smoothing window size (3 is optimal from testing)

    Returns
    -------
    Dict[str, np.ndarray]
        Gradients for each column, as arrays parallel to slots
    """
    grads: Dict[str, np.ndarray] = {}

    for c in cols:
        g = []
        for s in slots:
            # Gradient at slot s is: value[s] - value[s-1]
            x_curr = get_value(pdf, donor_date, s, c)
            x_prev = get_value(pdf, donor_date, s - 1, c)

            if x_curr is None or x_prev is None:
                g.append(np.nan)
            else:
                g.append(x_curr - x_prev)

        g = np.asarray(g, dtype=float)

        # Apply smoothing if requested
        if smooth_window_slots and smooth_window_slots > 1:
            g = _nanmean_smooth(g, int(smooth_window_slots))

        grads[c] = g

    return grads


def average_gradients(
    grad_prev: Optional[Dict[str, np.ndarray]],
    grad_next: Optional[Dict[str, np.ndarray]],
) -> Dict[str, np.ndarray]:
    """
    Average gradients from previous and next donor days.

    When we have donor days on both sides of a gap (previous and next), we average
    their gradients to get a balanced estimate. This averaging helps smooth out
    day-to-day variations and produces more stable filled values.

    If only one donor is available (either previous or next), we use it as-is.

    The averaging is NaN-aware: if one donor has a NaN gradient at a particular slot
    but the other donor has a valid value, we use the valid value. If both have NaN,
    the result is NaN.

    Returns
    -------
    Dict[str, np.ndarray]
        Averaged gradients for each column
    """
    if grad_prev is None and grad_next is None:
        return {}

    cols = set()
    if grad_prev:
        cols.update(grad_prev.keys())
    if grad_next:
        cols.update(grad_next.keys())

    out: Dict[str, np.ndarray] = {}
    for c in cols:
        a = grad_prev[c] if grad_prev else None
        b = grad_next[c] if grad_next else None

        if a is None:
            out[c] = b
        elif b is None:
            out[c] = a
        else:
            # Stack and compute NaN-aware mean across donors
            arr = np.vstack([a, b])
            with np.errstate(invalid="ignore"):
                m = np.nanmean(arr, axis=0)
            out[c] = m

    return out


def blended_donor_absolute(
    pdf: pd.DataFrame,
    *,
    day,
    slot: int,
    col: str,
    donor_prev: Optional[Any],
    donor_next: Optional[Any],
    dist_power: float = 1.0,
    weekday_boost: float = 1.2,
) -> Optional[float]:
    """
    Blend absolute values from donor days using distance-weighted averaging.

    This is used when we don't have anchor points (values immediately before/after
    a gap) to integrate gradients from. Instead, we look at the actual values from
    donor days at the target slot and blend them together.

    The blending weights are based on:
    1. Temporal distance: Closer donor days get higher weight (1/distance^dist_power)
    2. Weekday match: Donors with matching day-of-week get a small boost

    This blending strategy recognizes that recent patterns are more relevant than
    distant patterns, but also that weekly cycles matter for electricity demand.

    Returns
    -------
    float or None
        Blended value, or None if no valid donor values available
    """
    vals, wts = [], []

    def _add(donor):
        """Add a donor's value to the blend if available."""
        if donor is None:
            return

        v = get_value(pdf, donor, slot, col)
        if v is None:
            return

        # Calculate temporal distance (how many days away)
        dist = abs((pd.Timestamp(day) - pd.Timestamp(donor)).days)
        dist = max(0.5, float(dist))  # Avoid division by zero

        # Weight decreases with distance
        w = 1.0 / (dist ** dist_power)

        # Boost weight if weekdays match
        if pd.Timestamp(day).weekday() == pd.Timestamp(donor).weekday():
            w *= weekday_boost

        vals.append(float(v))
        wts.append(float(w))

    _add(donor_prev)
    _add(donor_next)

    if not wts:
        return None

    # Weighted average
    wsum = sum(wts)
    return float(sum(v * w for v, w in zip(vals, wts)) / wsum)


def integrate_gradients_into_gap(
    pdf: pd.DataFrame,
    *,
    day,
    slots: Sequence[int],
    cols: Sequence[str],
    avg_grads: Dict[str, np.ndarray],
    donor_prev: Optional[Any],
    donor_next: Optional[Any],
) -> Tuple[List[Dict[str, float]], List[Dict[str, object]]]:
    """
    Integrate averaged gradients to reconstruct values across a gap.

    This is where the magic happens. We take the averaged gradients from donor days
    and integrate them (accumulate the changes) to fill in missing values.

    The integration strategy depends on what anchor points are available:

    1. TWO-SIDED (both anchors): We have values immediately before and after the gap.
       - Integrate forward from the left anchor
       - Apply drift correction to ensure we end exactly at the right anchor
       - This is the most accurate case

    2. ONE-SIDED FORWARD: Only have value before the gap
       - Integrate forward from the left anchor
       - No drift correction possible
       - Accuracy decreases with gap length

    3. ONE-SIDED BACKWARD: Only have value after the gap
       - Integrate backward from the right anchor
       - Equivalent to forward, just in reverse

    4. NO ANCHORS: Don't have values on either side (gap at start/end of dataset)
       - Use blended donor absolute values as seed points
       - Integrate between start and end seeds
       - Least accurate but better than leaving gap unfilled

    The drift correction in two-sided integration is crucial. When you integrate
    gradients forward, small errors accumulate. If the gradients don't perfectly
    match the gap, you might end up at a different value than the actual right anchor.
    The drift correction applies a linear ramp to smoothly adjust the integrated
    values so they end exactly where they should.

    Returns
    -------
    fills : List[Dict]
        Filled values keyed by (_date, _slot, column_name)
    audit : List[Dict]
        Audit records indicating which method was used
    """
    fills_by_slot: Dict[int, Dict[str, float]] = {int(s): {} for s in slots}
    audit: List[Dict[str, object]] = []
    s_first, s_last = int(slots[0]), int(slots[-1])
    n = len(slots)

    # Look for anchor points (values immediately adjacent to gap)
    left_anchor  = {c: get_value(pdf, day, s_first - 1, c) for c in cols}
    right_anchor = {c: get_value(pdf, day, s_last + 1,  c) for c in cols}

    used_method = None

    for c in cols:
        g = avg_grads.get(c)
        if g is None or len(g) != n:
            continue

        # Convert NaNs to zeros for integration (missing gradients = no change)
        gi = np.nan_to_num(g, nan=0.0)
        y = np.full(n, np.nan, dtype=float)

        L = left_anchor[c]
        R = right_anchor[c]

        if (L is not None) and (R is not None):
            # CASE 1: Two-sided with drift correction
            # This is the best case - we can integrate and ensure we hit both endpoints

            v = float(L)
            for i in range(n):
                v += gi[i]
                y[i] = v

            # Calculate drift: difference between where we ended up and where we should be
            delta = float(R) - y[-1]

            if n == 1:
                # Single slot gap: just use the right anchor directly
                y[-1] = float(R)
            else:
                # Multi-slot gap: apply linear ramp to distribute the drift correction
                ramp = np.arange(n, dtype=float) / (n - 1)
                y = y + delta * ramp

            used_method = "gradient_two_sided"

        elif (L is not None):
            # CASE 2: One-sided (left anchor only)
            # Integrate forward, but no drift correction possible

            v = float(L)
            for i in range(n):
                v += gi[i]
                y[i] = v

            used_method = "gradient_forward"

        elif (R is not None):
            # CASE 3: One-sided (right anchor only)
            # Integrate backward from right anchor

            v = float(R)
            for i in range(n - 1, -1, -1):
                v -= gi[i]
                y[i] = v

            used_method = "gradient_backward"

        else:
            # CASE 4: No anchors - use blended donor values
            # This happens at dataset boundaries or very sparse data

            start_seed = blended_donor_absolute(
                pdf, day=day, slot=s_first, col=c,
                donor_prev=donor_prev, donor_next=donor_next
            )
            if start_seed is None:
                continue  # Can't fill this column at all

            v = float(start_seed)
            for i in range(n):
                if i == 0:
                    y[i] = v
                else:
                    v += gi[i]
                    y[i] = v

            # Try to get end seed and apply drift correction
            end_target = blended_donor_absolute(
                pdf, day=day, slot=s_last, col=c,
                donor_prev=donor_prev, donor_next=donor_next
            )
            if end_target is not None:
                delta = float(end_target) - y[-1]
                if n == 1:
                    y[-1] = float(end_target)
                else:
                    ramp = np.arange(n, dtype=float) / (n - 1)
                    y = y + delta * ramp

            used_method = "gradient_seeded_from_blended_donors"

        # Store filled values for this column
        for i, s in enumerate(slots):
            if not np.isnan(y[i]):
                fills_by_slot[int(s)][c] = float(y[i])

    if used_method is None:
        # Could not fill this gap at all
        audit.append({"_date": day, "_slot": int(s_first), "method": "no_anchor_no_seed"})
        return [], audit

    # Convert fills to list of dicts format expected by caller
    fills = [{"_date": day, "_slot": s, **vals} for s, vals in fills_by_slot.items() if vals]
    audit.append({"_date": day, "_slot": int(s_first), "method": used_method})

    return fills, audit


def contiguous_null_runs(
    work: pl.DataFrame,
    ref_col: str,
) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """
    Identify contiguous runs of null values in the reference column.

    A "run" is a sequence of consecutive null or non-null values. This function
    assigns each row a run_id, then extracts just the null runs (gaps) with their
    start/end slots and total length.

    This information is used by the gradient method to process each gap individually.

    Returns
    -------
    base : pl.DataFrame
        Original work dataframe with added run_id column
    gaps : pl.DataFrame
        Summary of null runs with columns: _date, _run_id, slot_start, slot_end, n_missing
    """
    work = work.sort(["_date", "_slot"])

    base = (
        work
        .with_columns(pl.col(ref_col).is_null().alias("_is_null"))
        .with_columns(
            pl.col("_is_null").shift(1).sort_by("_slot").over("_date").alias("_prev_is_null")
        )
        .with_columns(
            ((pl.col("_is_null") != pl.col("_prev_is_null")) | pl.col("_prev_is_null").is_null())
            .cast(pl.Int32)
            .alias("_chg")
        )
        .with_columns(
            pl.col("_chg").cum_sum().sort_by("_slot").over("_date").alias("_run_id")
        )
    )

    gaps = (
        base
        .filter(pl.col("_is_null"))
        .group_by(["_date", "_run_id"])
        .agg([
            pl.col("_slot").min().alias("slot_start"),
            pl.col("_slot").max().alias("slot_end"),
            pl.len().alias("n_missing"),
        ])
        .sort(["_date", "slot_start"])
    )

    return base, gaps


def build_timestamp_map(
    work: pl.DataFrame,
    timestamp_col: str = "timestamp"
) -> pd.Series:
    """
    Build a lookup table from (_date, _slot) to original timestamp.

    This is needed when converting filled values (which are keyed by date/slot)
    back to timestamp-keyed format for merging into the main dataframe.
    """
    ts_map = (
        work.select(["_date", "_slot", timestamp_col])
            .unique(subset=["_date", "_slot"])
            .to_pandas()
    )
    ts_map["_date"] = pd.to_datetime(ts_map["_date"]).dt.date
    return ts_map.set_index(["_date", "_slot"])[timestamp_col]


# ============================================================================
# MAIN GRADIENT FILLING FUNCTION
# ============================================================================

def fill_long_gaps_by_gradient(
    df: pl.DataFrame,
    *,
    ref_col: str = "demand_met",
    fill_cols: Optional[Sequence[str]] = None,
    step_minutes: int = 5,
    max_search_days: int = 21,
    smooth_window_slots: int = 3,
    prefer_same_weekday: bool = True,
    slot_tolerance: int = 0,
    logger: Optional[logging.Logger] = None,
) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """
    Fill gaps using gradient-based donor day method.

    This function implements the sophisticated gradient-based gap filling approach
    that has been extensively tested and validated. It works by:

    1. Finding similar historical days (donors) that have complete data
    2. Computing gradients (first differences) from those donor days
    3. Averaging gradients from multiple donors to reduce noise
    4. Integrating the gradients to reconstruct missing values
    5. Applying drift correction when anchor points exist

    The method preserves realistic temporal patterns because it uses the "shape"
    of historical demand curves (captured by gradients) rather than just interpolating
    linearly. This produces much better results for long gaps where linear interpolation
    would create unrealistic straight lines through periods that should show natural
    daily cycles.

    Parameters
    ----------
    df : pl.DataFrame
        Input dataframe with possible gaps
    ref_col : str
        Reference column that defines which rows are missing (default: demand_met)
    fill_cols : Sequence[str], optional
        Columns to fill (default: all numeric columns)
    step_minutes : int
        Time resolution in minutes (default: 5)
    max_search_days : int
        How far to search for donor days (default: 21)
    smooth_window_slots : int
        Smoothing window for gradients (default: 3, optimal from testing)
    prefer_same_weekday : bool
        Prefer donors with matching day of week (default: True)
    slot_tolerance : int
        Allow matching nearby slots (default: 0 = exact match only)
    logger : logging.Logger, optional
        Logger for progress messages

    Returns
    -------
    filled_df : pl.DataFrame
        Dataframe with gaps filled where possible
    audit_df : pl.DataFrame
        Audit log showing which method was used for each gap
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    if ref_col not in df.columns:
        raise KeyError(f"Reference column '{ref_col}' not found in DataFrame")

    # Determine which columns to fill
    cols = choose_fill_columns(df, timestamp_col="timestamp", fill_cols=fill_cols)
    if not cols:
        logger.warning("No numeric columns found to fill")
        return df, empty_audit_df_gradient()

    # Add date and slot helper columns
    work = add_date_and_slot(df, timestamp_col="timestamp", step_minutes=step_minutes)
    need_cols = list(dict.fromkeys(["_date", "_slot", "timestamp", ref_col] + cols))
    work = work.select(need_cols).sort("timestamp")

    # Find gaps in the data
    base_runs, gaps = contiguous_null_runs(work, ref_col=ref_col)
    if gaps.is_empty():
        logger.info("No gaps found - returning original dataframe")
        return df, empty_audit_df_gradient()

    # Create indexed reference for fast donor lookups
    pdf = to_unique_date_slot_index(work, ref_col=ref_col, fill_cols=cols)

    spd = slots_per_day(step_minutes)
    ts_map = build_timestamp_map(work, timestamp_col="timestamp")

    fills_all: List[Dict[str, float]] = []
    audit_all: List[Dict[str, object]] = []

    logger.debug(f"Processing {gaps.height} gaps with gradient method")

    # Process each gap
    for g in gaps.iter_rows(named=True):
        day = pd.Timestamp(g["_date"]).date()
        s0 = int(g["slot_start"])
        s1 = int(g["slot_end"])
        slots = list(range(s0, s1 + 1))

        if not slots:
            continue

        # Find donor days before and after this gap
        prev_date = find_nearest_donor_date(
            pdf,
            date0=day,
            slot=s0,
            ref_col=ref_col,
            direction=-1,
            max_search_days=max_search_days,
            prefer_same_weekday=prefer_same_weekday,
            slot_tolerance=slot_tolerance,
            spd=spd,
        )
        next_date = find_nearest_donor_date(
            pdf,
            date0=day,
            slot=s1,
            ref_col=ref_col,
            direction=+1,
            max_search_days=max_search_days,
            prefer_same_weekday=prefer_same_weekday,
            slot_tolerance=slot_tolerance,
            spd=spd,
        )

        # Compute gradients from donor days
        grad_prev = donor_gradients_for_slots(
            pdf,
            donor_date=prev_date,
            slots=slots,
            cols=cols,
            smooth_window_slots=smooth_window_slots,
        ) if prev_date else None

        grad_next = donor_gradients_for_slots(
            pdf,
            donor_date=next_date,
            slots=slots,
            cols=cols,
            smooth_window_slots=smooth_window_slots,
        ) if next_date else None

        # Average gradients from both donors
        avg_grads = average_gradients(grad_prev, grad_next)
        if not avg_grads:
            audit_all.append({"_date": day, "_slot": s0, "method": "no_donor_gradients"})
            continue

        # Integrate gradients to fill the gap
        fills, audit = integrate_gradients_into_gap(
            pdf,
            day=day,
            slots=slots,
            cols=cols,
            avg_grads=avg_grads,
            donor_prev=prev_date,
            donor_next=next_date,
        )
        fills_all.extend(fills)
        audit_all.extend(audit)

    # Convert fills to Polars format and merge back into original dataframe
    if fills_all:
        fills_pl = pl.DataFrame(fills_all).with_columns([
            pl.col("_date").cast(pl.Date),
            pl.col("_slot").cast(pl.Int32),
        ])
        fills_pl = fills_pl.unique(subset=["_date", "_slot"], keep="first")

        df_with_keys = add_date_and_slot(df, timestamp_col="timestamp", step_minutes=step_minutes)
        merged = df_with_keys.join(fills_pl, on=["_date", "_slot"], how="left", suffix="_gradfill")

        # Coalesce: use filled value only where original was null
        for c in cols:
            c_new = f"{c}_gradfill"
            if c_new in merged.columns:
                merged = merged.with_columns(
                    pl.coalesce([pl.col(c), pl.col(c_new)]).alias(c)
                ).drop(c_new)

        merged = merged.drop(["_date", "_slot"])
    else:
        logger.warning("Gradient method produced no fills")
        merged = df

    # Create audit dataframe
    audit_pl = (
        pl.DataFrame(audit_all or [])
        .with_columns([
            pl.col("_date").cast(pl.Date),
            pl.col("_slot").cast(pl.Int32),
            pl.col("method").cast(pl.Utf8),
        ])
        if audit_all else empty_audit_df_gradient()
    )

    return merged, audit_pl


# ============================================================================
# SHORT GAP FILLING (Linear Interpolation)
# ============================================================================

def fill_short_gaps_linear(
    df: pl.DataFrame,
    *,
    ref_col: str,
    step_minutes: int = 5,
    max_gap_minutes: int = 80,
    cols_to_fill: Optional[List[str]] = None,
    logger: Optional[logging.Logger] = None,
) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """
    Fill short gaps using linear interpolation.

    Linear interpolation draws a straight line between the last known value before
    a gap and the first known value after it, then fills in the intermediate points
    along that line. This works well for short gaps because demand doesn't change
    dramatically over brief periods.

    For longer gaps, linear interpolation becomes problematic because it creates
    unrealistic straight lines through periods that should show natural cycles.
    That's why we use the gradient method for longer gaps.

    This function only fills gaps that are <= max_gap_minutes in duration. Longer
    gaps are left unfilled for the gradient method to handle.

    Parameters
    ----------
    df : pl.DataFrame
        Input dataframe
    ref_col : str
        Reference column that defines gaps
    step_minutes : int
        Time resolution in minutes
    max_gap_minutes : int
        Maximum gap length to fill (longer gaps left for gradient method)
    cols_to_fill : List[str], optional
        Columns to fill (default: all numeric columns)
    logger : logging.Logger, optional
        Logger for progress messages

    Returns
    -------
    filled_df : pl.DataFrame
        Dataframe with short gaps filled
    gaps_before : pl.DataFrame
        Summary of gaps that existed before filling (for logging/analysis)
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    max_rows = int(round(max_gap_minutes / step_minutes))

    if cols_to_fill is None:
        cols_to_fill = [
            c for c, dt in df.schema.items()
            if c != "timestamp" and dt.is_numeric()
        ]

    # Record gaps before filling for analysis
    gaps_before = find_null_runs(df, ref_col=ref_col)

    # Identify null runs and their lengths
    base = (
        df.with_columns(pl.col(ref_col).is_null().alias("is_null"))
        .with_columns(
            (pl.col("is_null") != pl.col("is_null").shift(1))
            .cum_sum()
            .alias("run_id")
        )
    )

    run_sizes = base.group_by("run_id").agg(pl.len().alias("run_len"))
    base = base.join(run_sizes, on="run_id", how="left")

    # Mask for short gaps only
    short_gap_mask = pl.col("is_null") & (pl.col("run_len") <= max_rows)

    # Interpolate each column, but only fill in short gaps
    fill_exprs = []
    for c in cols_to_fill:
        # Compute interpolated values for entire column
        interp = pl.col(c).cast(pl.Float64).interpolate()
        # But only use interpolated values where mask is True
        fill_exprs.append(
            pl.when(short_gap_mask)
              .then(interp)
              .otherwise(pl.col(c))
              .alias(c)
        )

    filled = base.with_columns(fill_exprs).drop(["is_null", "run_id", "run_len"])

    return filled, gaps_before


def find_null_runs(df: pl.DataFrame, *, ref_col: str) -> pl.DataFrame:
    """
    Find all contiguous null runs in the reference column.

    This function identifies gaps by finding sequences of consecutive null values.
    It returns a summary dataframe with one row per gap, showing when it starts,
    when it ends, and how many points are missing.

    This is used for analysis and reporting, showing users exactly where the gaps
    are in their data.

    Returns
    -------
    pl.DataFrame
        Gap summary with columns: missing_start, missing_end, n_missing
    """
    base = (
        df.select(["timestamp", ref_col])
        .with_columns(pl.col(ref_col).is_null().alias("is_null"))
        .with_columns(
            (pl.col("is_null") != pl.col("is_null").shift(1))
            .cum_sum()
            .alias("run_id")
        )
    )

    gaps = (
        base.filter(pl.col("is_null"))
        .group_by("run_id")
        .agg([
            pl.col("timestamp").min().alias("missing_start"),
            pl.col("timestamp").max().alias("missing_end"),
            pl.len().alias("n_missing"),
        ])
        .sort("missing_start")
    )

    return gaps


# ============================================================================
# EMISSION INTENSITY RECALCULATION
# ============================================================================

def recompute_intensities_from_rates(
    df: pl.DataFrame,
    step_minutes: int = 5,
    total_col: str = "total_generation",
    tons_col: str = "tons_co2",
    t_mwh_col: str = "tons_co2_per_mwh",
    g_kwh_col: str = "g_co2_per_kwh",
    eps: float = 1e-9,
    clamp_to_existing: bool = True,
    q_low: float = 0.001,
    q_high: float = 0.999,
    pad: float = 0.05,
    logger: Optional[logging.Logger] = None,
) -> pl.DataFrame:
    """
    Recompute emission intensity columns from generation and emissions.

    After gap filling, generation values and absolute emissions (tons_co2) have been
    filled, but the emission intensity columns (tons_co2_per_mwh, g_co2_per_kwh) may
    be inconsistent. This function recalculates them to ensure consistency.

    The calculation:
    - interval_energy_mwh = generation_mw * (step_minutes / 60)
    - tons_co2_per_mwh = tons_co2 / interval_energy_mwh
    - g_co2_per_kwh = tons_co2_per_mwh * 1000

    The clamping step prevents extreme outliers. Gap filling can occasionally produce
    values outside the historically observed range, especially when extrapolating.
    By clamping to a robust quantile-based range (0.1% to 99.9% with 5% padding),
    we prevent physically unrealistic intensities while allowing reasonable variation.

    Parameters
    ----------
    df : pl.DataFrame
        Input dataframe with filled generation and emissions
    step_minutes : int
        Time resolution for energy calculation
    total_col : str
        Total generation column name
    tons_col : str
        Absolute CO2 emissions column name
    t_mwh_col : str
        Tons CO2 per MWh column name (will be recalculated)
    g_kwh_col : str
        Grams CO2 per kWh column name (will be recalculated)
    eps : float
        Minimum generation threshold to avoid division by zero
    clamp_to_existing : bool
        Whether to clamp intensities to historical quantile range
    q_low, q_high : float
        Quantiles for clamping bounds
    pad : float
        Padding beyond quantiles (as fraction of quantile range)
    logger : logging.Logger, optional
        Logger for progress messages

    Returns
    -------
    pl.DataFrame
        Dataframe with recalculated and clamped intensity columns
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    factor = float(step_minutes) / 60.0

    # Recompute tons_co2_per_mwh from first principles
    # Guard against division by zero with eps threshold
    new_t_expr = (
        pl.when((pl.col(total_col) * factor) > eps)
        .then(pl.col(tons_col) / (pl.col(total_col) * factor))
        .otherwise(None)
    )

    out = df.with_columns(
        # Prefer new calculation, fall back to existing if calculation fails
        pl.coalesce([new_t_expr, pl.col(t_mwh_col)]).alias(t_mwh_col)
    )

    # Apply robust clamping to prevent extreme outliers
    if clamp_to_existing:
        # Get quantiles from original data
        qdf = df.select([
            pl.col(t_mwh_col).quantile(q_low, "nearest").alias("_q_lo"),
            pl.col(t_mwh_col).quantile(q_high, "nearest").alias("_q_hi"),
        ])
        q_lo, q_hi = qdf.row(0)

        # If original data had no valid values, use recalculated quantiles
        if q_lo is None or q_hi is None:
            qdf2 = out.select([
                pl.col(t_mwh_col).quantile(q_low, "nearest").alias("_q_lo"),
                pl.col(t_mwh_col).quantile(q_high, "nearest").alias("_q_hi"),
            ])
            q_lo, q_hi = qdf2.row(0)

        # Calculate padded bounds
        if q_lo is not None and q_hi is not None and math.isfinite(q_lo) and math.isfinite(q_hi):
            span = max(0.0, q_hi - q_lo)
            lb = max(0.0, q_lo - pad * span)  # Lower bound can't be negative
            ub = q_hi + pad * span

            out = out.with_columns(pl.col(t_mwh_col).clip(lb, ub))
            logger.debug(f"Clamped {t_mwh_col} to [{lb:.2f}, {ub:.2f}]")

    # Keep g_co2_per_kwh consistent with tons_co2_per_mwh
    out = out.with_columns((pl.col(t_mwh_col) * 1000.0).alias(g_kwh_col))

    return out


# ============================================================================
# UTILITY FUNCTIONS FOR ANALYSIS
# ============================================================================

def create_full_time_grid(df: pl.DataFrame, step_minutes: int = 5) -> pl.DataFrame:
    """
    Create a complete time grid and left-join original data.

    This function creates a dataframe with every expected timestamp from the start
    to the end of the data range, then left-joins the original data onto it. This
    makes gaps explicit as null values, which is necessary for the gap filling
    algorithms to identify and process them.

    Without this step, gaps would simply be missing rows, and we wouldn't know
    they should be there.
    """
    data_start = df.select(pl.col("timestamp").min()).item()
    data_end = df.select(pl.col("timestamp").max()).item()

    full_grid = pl.DataFrame({
        "timestamp": pl.datetime_range(
            start=data_start,
            end=data_end,
            interval=f"{step_minutes}m",
            closed="both",
            eager=True,
            time_unit="us"
        )
    })

    return full_grid.join(df, on="timestamp", how="left")


def count_null_rows(df: pl.DataFrame, ref_col: str) -> int:
    """Count how many rows have null values in the reference column."""
    return int(df.select(pl.col(ref_col).is_null().sum()).item())


def analyze_gaps(
    df: pl.DataFrame,
    ref_col: str,
    step_minutes: int = 5,
    logger: Optional[logging.Logger] = None
) -> Dict[str, Any]:
    """
    Perform comprehensive gap analysis with binned statistics.

    This function provides detailed insights into the gap structure:
    - Total number of gaps and missing points
    - Breakdown by year (which years have more gaps?)
    - Breakdown by gap length (many short gaps vs few long gaps?)
    - Column consistency check (do all columns have same gaps?)

    This analysis helps understand data quality issues and guides the choice
    of gap filling parameters.

    Returns
    -------
    dict
        Comprehensive gap analysis with multiple facets
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    gaps = find_null_runs(df, ref_col=ref_col)

    if gaps.is_empty():
        return {
            "total_gaps": 0,
            "total_missing_points": 0,
            "by_year": [],
            "by_length_bin": [],
            "columns_consistent": True
        }

    # Add gap duration in minutes
    gaps = gaps.with_columns(
        (pl.col("n_missing") * step_minutes).alias("gap_minutes")
    )

    total_gaps = gaps.height
    total_missing = gaps.select(pl.col("n_missing").sum()).item()

    # Analyze by year
    gaps_with_year = gaps.with_columns(
        pl.col("missing_start").dt.year().alias("year")
    )
    by_year = (
        gaps_with_year
        .group_by("year")
        .agg([
            pl.len().alias("n_gaps"),
            pl.col("n_missing").sum().alias("total_missing")
        ])
        .sort("year")
    )

    # Analyze by gap length bins
    bins = [20, 60, 80, 120, 240, 480]
    bin_labels = ["< 20 min", "20-60 min", "60-80 min", "80-120 min",
                  "120-240 min", "240-480 min", "> 480 min"]

    def assign_bin(minutes):
        """Assign a gap to a length bin."""
        for i, b in enumerate(bins):
            if minutes < b:
                return bin_labels[i]
        return bin_labels[-1]

    gaps_pd = gaps.to_pandas()
    gaps_pd["bin"] = gaps_pd["gap_minutes"].apply(assign_bin)

    by_bin = (
        gaps_pd.groupby("bin", sort=False)
        .agg({
            "n_missing": ["count", "sum"]
        })
        .reset_index()
    )
    by_bin.columns = ["bin", "n_gaps", "total_missing"]

    # Reorder by bin progression
    bin_order = {label: i for i, label in enumerate(bin_labels)}
    by_bin["order"] = by_bin["bin"].map(bin_order)
    by_bin = by_bin.sort_values("order").drop(columns="order")

    # Check if all columns have same null pattern
    all_cols = [c for c in df.columns if c != "timestamp"]
    null_patterns = {}
    for col in all_cols:
        null_count = count_null_rows(df, col)
        null_patterns[col] = null_count

    columns_consistent = len(set(null_patterns.values())) == 1

    return {
        "total_gaps": total_gaps,
        "total_missing_points": int(total_missing),
        "by_year": by_year.to_pandas().to_dict("records"),
        "by_length_bin": by_bin.to_dict("records"),
        "columns_consistent": columns_consistent,
        "null_patterns": null_patterns if not columns_consistent else {}
    }


def print_gap_analysis(analysis: Dict[str, Any], logger: logging.Logger) -> None:
    """Pretty-print gap analysis results."""
    logger.info("\n" + "=" * 80)
    logger.info("GAP ANALYSIS")
    logger.info("=" * 80)

    logger.info(f"\nTotal gaps found: {analysis['total_gaps']:,}")
    logger.info(f"Total missing data points: {analysis['total_missing_points']:,}")

    logger.info("\nMissing data by year:")
    logger.info("-" * 40)
    for row in analysis["by_year"]:
        logger.info(f"  {row['year']}: {row['n_gaps']:3d} gaps, {row['total_missing']:6,} points")

    logger.info("\nMissing data by gap length:")
    logger.info("-" * 40)
    for row in analysis["by_length_bin"]:
        logger.info(f"  {row['bin']:15s}: {row['n_gaps']:4d} gaps, {row['total_missing']:7,} points")

    if analysis["columns_consistent"]:
        logger.info("\n✓ All columns have consistent null patterns")
    else:
        logger.warning("\n⚠ COLUMNS HAVE DIFFERENT NULL PATTERNS:")
        for col, count in analysis["null_patterns"].items():
            logger.warning(f"  {col}: {count:,} nulls")

    logger.info("=" * 80 + "\n")


# ============================================================================
# PROGRESSIVE GAP FILLING ORCHESTRATOR
# ============================================================================

def fill_all_gaps_progressive(
    input_path: Path,
    config: Dict[str, Any],
    output_dir: Path,
    logger: logging.Logger,
    interactive: bool = False
) -> Tuple[pl.DataFrame, Dict[str, Any]]:
    """
    Progressive multi-stage gap filling pipeline with checkpoint saving.

    This is the main orchestrator that implements your sophisticated progressive
    gap filling strategy. It runs multiple passes, alternating between linear
    interpolation (with progressively lower thresholds) and gradient filling.

    The strategy is:
    1. Fill short gaps (80 min) with linear interpolation
    2. Fill long gaps with gradient method → SAVE CHECKPOINT
    3. Fill remaining medium gaps (40 min) with linear interpolation
    4. Fill long gaps with gradient method → SAVE CHECKPOINT
    5. Fill remaining short gaps (20 min) with linear interpolation
    6. Fill long gaps with gradient method → SAVE CHECKPOINT
    7. Loop: Fill tiny gaps (10 min) then gradient until no more progress → SAVE EACH ITERATION

    After each major stage, we save a checkpoint file so you can analyze exactly
    which gaps were filled at which stage and validate that the progressive
    approach is working as intended.

    Parameters
    ----------
    input_path : Path
        Input parquet file
    config : dict
        Gap filling configuration
    output_dir : Path
        Directory to save checkpoint files
    logger : logging.Logger
        Logger instance
    interactive : bool
        If True, prompt for confirmation before proceeding (default: False for automation)

    Returns
    -------
    final_df : pl.DataFrame
        Fully processed dataframe with all gaps filled
    stats : dict
        Detailed statistics about what was filled at each stage
    """
    logger.info("Loading input data...")
    df = pl.read_parquet(input_path)

    # Extract configuration
    step_minutes = 5
    ref_col = config["ref_column"]
    cols_to_fill = config["columns_to_fill"]
    gradient_config = config["gradient"]

    # Columns that should be non-negative (generation, not intensities)
    nonneg_cols = [c for c in cols_to_fill if c not in ["g_co2_per_kwh", "tons_co2_per_mwh"]]

    # Analyze original data
    logger.info("\n" + "=" * 80)
    logger.info("ANALYZING ORIGINAL DATA")
    logger.info("=" * 80)

    data_start = df.select(pl.col("timestamp").min()).item()
    data_end = df.select(pl.col("timestamp").max()).item()
    actual_points = df.height
    expected_points = int((data_end - data_start).total_seconds() / 60 / step_minutes) + 1

    logger.info(f"\nData range:")
    logger.info(f"  Start: {data_start}")
    logger.info(f"  End:   {data_end}")
    logger.info(f"  Frequency: {step_minutes} minutes")
    logger.info(f"\nData points:")
    logger.info(f"  Expected: {expected_points:,}")
    logger.info(f"  Actual:   {actual_points:,}")
    logger.info(f"  Missing:  {expected_points - actual_points:,} ({(expected_points - actual_points) / expected_points * 100:.2f}%)")

    # Create full time grid
    logger.info("\n" + "=" * 80)
    logger.info("CREATING FULL TIME GRID")
    logger.info("=" * 80)
    df_current = create_full_time_grid(df, step_minutes=step_minutes)

    # Initial gap analysis
    gap_analysis = analyze_gaps(df_current, ref_col=ref_col, step_minutes=step_minutes, logger=logger)
    print_gap_analysis(gap_analysis, logger)

    # Show configuration
    logger.info("\n" + "=" * 80)
    logger.info("PROGRESSIVE GAP FILLING CONFIGURATION")
    logger.info("=" * 80)
    logger.info("\nStrategy:")
    logger.info("  Stage 1: Linear interp (≤80 min) → Gradient fill → CHECKPOINT")
    logger.info("  Stage 2: Linear interp (≤40 min) → Gradient fill → CHECKPOINT")
    logger.info("  Stage 3: Linear interp (≤20 min) → Gradient fill → CHECKPOINT")
    logger.info("  Stage 4: Loop [Linear interp (≤10 min) → Gradient fill] → CHECKPOINT each iteration")
    logger.info(f"\nGradient parameters:")
    logger.info(f"  Max search days: {gradient_config['max_search_days']}")
    logger.info(f"  Smoothing window: {gradient_config['smooth_window_slots']} slots")
    logger.info(f"  Prefer same weekday: {gradient_config['prefer_same_weekday']}")
    logger.info("=" * 80 + "\n")

    if interactive:
        response = input("\nProceed with gap filling? (Y/n): ").strip().lower()
        if response == 'n':
            logger.info("Gap filling cancelled by user.")
            return df_current, {"status": "cancelled"}

    # Track statistics for each step (not stage - we save after each operation)
    stats = {
        "initial_nulls": count_null_rows(df_current, ref_col),
        "steps": []
    }

    step_num = 0

    # Helper function to save a checkpoint
    def save_checkpoint(name: str, nulls_before: int, nulls_after: int):
        """Save checkpoint after an individual step."""
        nonlocal step_num
        step_num += 1

        filled = nulls_before - nulls_after

        checkpoint_path = output_dir / f"checkpoint_step{step_num:02d}_{name.replace(' ', '_')}.parquet"
        df_current.write_parquet(checkpoint_path, compression="snappy")
        logger.info(f"✓ Checkpoint saved: {checkpoint_path.name}")
        logger.info(f"  Filled this step: {filled:,} points")
        logger.info(f"  Remaining nulls: {nulls_after:,}")

        # Record step statistics
        stats["steps"].append({
            "step_num": step_num,
            "name": name,
            "nulls_before": nulls_before,
            "nulls_after": nulls_after,
            "filled": filled,
            "checkpoint": str(checkpoint_path)
        })

    # Helper function to run linear interpolation step
    def run_linear_step(threshold_min: int, description: str):
        """Run linear interpolation and save checkpoint."""
        nonlocal df_current

        logger.info("\n" + "=" * 80)
        logger.info(f"LINEAR INTERPOLATION: {description}")
        logger.info("=" * 80)

        nulls_before = count_null_rows(df_current, ref_col)
        logger.info(f"Nulls before: {nulls_before:,}")

        df_current, _ = fill_short_gaps_linear(
            df_current,
            ref_col=ref_col,
            step_minutes=step_minutes,
            max_gap_minutes=threshold_min,
            cols_to_fill=cols_to_fill,
            logger=logger
        )

        nulls_after = count_null_rows(df_current, ref_col)

        save_checkpoint(description, nulls_before, nulls_after)

        return nulls_after

    # Helper function to run gradient step
    def run_gradient_step(description: str):
        """Run gradient filling and save checkpoint."""
        nonlocal df_current

        logger.info("\n" + "=" * 80)
        logger.info(f"GRADIENT FILLING: {description}")
        logger.info("=" * 80)

        nulls_before = count_null_rows(df_current, ref_col)
        logger.info(f"Nulls before: {nulls_before:,}")

        df_current, _ = fill_long_gaps_by_gradient(
            df_current,
            ref_col=ref_col,
            fill_cols=cols_to_fill,
            step_minutes=step_minutes,
            max_search_days=gradient_config["max_search_days"],
            smooth_window_slots=gradient_config["smooth_window_slots"],
            prefer_same_weekday=gradient_config["prefer_same_weekday"],
            logger=logger
        )

        # Cleanup after gradient filling
        df_current = clamp_nonneg(df_current, nonneg_cols)
        df_current = recompute_intensities_from_rates(
            df_current,
            step_minutes=step_minutes,
            clamp_to_existing=True,
            q_low=0.001,
            q_high=0.999,
            pad=0.05,
            logger=logger
        )

        nulls_after = count_null_rows(df_current, ref_col)

        save_checkpoint(description, nulls_before, nulls_after)

        return nulls_after

    # Execute progressive filling strategy
    # Each step saves its own checkpoint

    # Step 1 & 2: 80-min linear, then gradient
    nulls = run_linear_step(80, "linear_80min")
    if nulls > 0:
        nulls = run_gradient_step("gradient_pass1")

    # Step 3 & 4: 40-min linear, then gradient (if still have nulls)
    if nulls > 0:
        nulls = run_linear_step(40, "linear_40min")
        if nulls > 0:
            nulls = run_gradient_step("gradient_pass2")

    # Step 5 & 6: 20-min linear, then gradient (if still have nulls)
    if nulls > 0:
        nulls = run_linear_step(20, "linear_20min")
        if nulls > 0:
            nulls = run_gradient_step("gradient_pass3")

    # Loop: 10-min linear + gradient until no progress
    loop_iteration = 0
    while nulls > 0:
        loop_iteration += 1
        nulls_before_loop = nulls

        # Linear step
        nulls = run_linear_step(10, f"linear_10min_loop{loop_iteration}")

        # Gradient step (if still have nulls)
        if nulls > 0:
            nulls = run_gradient_step(f"gradient_loop{loop_iteration}")

        # Stop if no progress made in this loop iteration
        if nulls >= nulls_before_loop:
            logger.info(f"\nNo progress in loop iteration {loop_iteration}, stopping.")
            break

        # Safety: limit to 10 iterations
        if loop_iteration >= 10:
            logger.warning(f"\nReached maximum loop iterations (10), stopping.")
            break

    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("PROGRESSIVE GAP FILLING COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Initial nulls: {stats['initial_nulls']:,}")
    logger.info(f"Final nulls:   {nulls:,}")
    logger.info(f"Total filled:  {stats['initial_nulls'] - nulls:,}")
    logger.info(f"Total steps completed: {step_num}")
    logger.info(f"Checkpoints saved: {step_num}")

    if nulls == 0:
        logger.info("\n✓ All gaps successfully filled!")
    else:
        logger.warning(f"\n⚠ {nulls:,} null values remain after all steps")

    logger.info("=" * 80 + "\n")

    stats["final_nulls"] = nulls
    stats["total_steps"] = step_num

    return df_current, stats


# ============================================================================
# SIMPLE GAP FILLING (FOR COMPATIBILITY WITH EXISTING CODE)
# ============================================================================

def fill_all_gaps(
    input_path: Path,
    config: Dict[str, Any],
    logger: logging.Logger,
    interactive: bool = False
) -> Tuple[pl.DataFrame, pl.DataFrame, Dict[str, Any]]:
    """
    Simple gap filling pipeline for backward compatibility.

    This provides a simpler interface that matches the original code structure,
    but you should use fill_all_gaps_progressive for production work.

    This runs a basic 3-step process:
    1. Linear interpolation for short gaps (≤80 min)
    2. Gradient filling for long gaps
    3. Final linear cleanup for stragglers
    """
    logger.info("Loading input data...")
    df = pl.read_parquet(input_path)

    step_minutes = 5
    ref_col = config["ref_column"]
    cols_to_fill = config["columns_to_fill"]
    short_threshold = config["short_gap_threshold_minutes"]
    gradient_config = config["gradient"]

    nonneg_cols = [c for c in cols_to_fill if c not in ["g_co2_per_kwh", "tons_co2_per_mwh"]]

    # Create full time grid
    df_full = create_full_time_grid(df, step_minutes=step_minutes)

    initial_nulls = count_null_rows(df_full, ref_col)

    # Step 1: Short gaps
    logger.info(f"\nStep 1: Linear interpolation (≤{short_threshold} min)")
    df_step1, _ = fill_short_gaps_linear(
        df_full,
        ref_col=ref_col,
        step_minutes=step_minutes,
        max_gap_minutes=short_threshold,
        cols_to_fill=cols_to_fill,
        logger=logger
    )

    nulls_after_step1 = count_null_rows(df_step1, ref_col)
    filled_step1 = initial_nulls - nulls_after_step1
    logger.info(f"Filled: {filled_step1:,}")

    # Step 2: Gradient
    logger.info(f"\nStep 2: Gradient filling")
    df_step2, audit = fill_long_gaps_by_gradient(
        df_step1,
        ref_col=ref_col,
        fill_cols=cols_to_fill,
        step_minutes=step_minutes,
        max_search_days=gradient_config["max_search_days"],
        smooth_window_slots=gradient_config["smooth_window_slots"],
        prefer_same_weekday=gradient_config["prefer_same_weekday"],
        logger=logger
    )

    df_step2 = clamp_nonneg(df_step2, nonneg_cols)
    df_step2 = recompute_intensities_from_rates(df_step2, step_minutes=step_minutes, logger=logger)

    nulls_after_step2 = count_null_rows(df_step2, ref_col)
    filled_step2 = nulls_after_step1 - nulls_after_step2
    logger.info(f"Filled: {filled_step2:,}")

    # Step 3: Final cleanup
    logger.info(f"\nStep 3: Final linear cleanup")
    # Just fill any remaining with aggressive linear interpolation
    df_final = df_step2.with_columns([
        pl.col(c).cast(pl.Float64).interpolate().alias(c)
        for c in cols_to_fill
    ])

    df_final = clamp_nonneg(df_final, nonneg_cols)
    df_final = recompute_intensities_from_rates(df_final, step_minutes=step_minutes, logger=logger)

    final_nulls = count_null_rows(df_final, ref_col)
    filled_step3 = nulls_after_step2 - final_nulls
    logger.info(f"Filled: {filled_step3:,}")

    stats = {
        "total_rows": df_full.height,
        "nulls_initial": initial_nulls,
        "filled_step1": filled_step1,
        "filled_step2": filled_step2,
        "filled_step3": filled_step3,
        "nulls_final": final_nulls
    }

    return df_final, audit, stats