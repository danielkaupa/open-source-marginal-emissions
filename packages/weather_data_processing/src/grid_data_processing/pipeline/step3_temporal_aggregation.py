"""
Step 3: Temporal Aggregation
=============================

Aggregate 5-minute data to half-hourly intervals.

Based on making_grid_data_half_hourly.py:
- Shift timestamps +5 minutes (end-of-interval convention)
- Align to 30-minute boundaries
- Mean for generation/demand/intensities
- Sum for CO2 emissions
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

import polars as pl


def aggregate_to_half_hourly(
    input_path: Path,
    config: Dict[str, Any],
    step_minutes: int = 5,
    logger: Optional[logging.Logger] = None
) -> pl.DataFrame:
    """
    Aggregate 5-minute grid data to half-hourly intervals.
    
    Parameters
    ----------
    input_path : Path
        Input parquet file with 5-minute data
    config : dict
        Aggregation configuration with keys:
        - avg_columns: list of columns to average
        - sum_columns: list of columns to sum
    step_minutes : int
        Source data frequency in minutes
    logger : logging.Logger, optional
        Logger instance
        
    Returns
    -------
    pl.DataFrame
        Half-hourly aggregated data
        
    Notes
    -----
    The function:
    1. Shifts timestamps forward by 5 minutes (measurement is at end of interval)
    2. Aligns to 30-minute boundaries using truncate
    3. Groups by timestamp and aggregates:
       - Mean for generation, demand, and intensity columns
       - Sum for absolute emissions (tons_co2)
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    logger.info(f"Loading data from: {input_path}")
    df = pl.read_parquet(input_path)
    
    # Verify time range
    tmin = df.select(pl.col("timestamp").min()).item()
    tmax = df.select(pl.col("timestamp").max()).item()
    logger.info(f"Input time range: {tmin} → {tmax}")
    logger.info(f"Input shape: {df.height:,} rows")
    
    # Sort by timestamp
    df = df.sort("timestamp")
    
    # Step 1: Shift timestamps forward by step_minutes (end-of-interval convention)
    # A reading at 14:00 represents the 5-minute interval ending at 14:00
    logger.info(f"Shifting timestamps by +{step_minutes} minutes (end-of-interval)")
    df = df.with_columns(
        (pl.col("timestamp") + pl.duration(minutes=step_minutes)).alias("end_timestamp")
    )
    
    # Step 2: Align to half-hour boundaries
    # Add 29 minutes 59 seconds, then truncate to 30-minute intervals
    # This ensures readings fall into the correct half-hour bucket
    logger.info("Aligning to 30-minute boundaries")
    df = df.with_columns(
        (pl.col("end_timestamp") + pl.duration(minutes=29, seconds=59))
        .dt.truncate("30m")
        .alias("timestamp")
    )
    
    # Step 3: Aggregate
    avg_cols = config["avg_columns"]
    sum_cols = config["sum_columns"]
    
    logger.info(f"Aggregating to half-hourly intervals")
    logger.info(f"  Mean columns: {len(avg_cols)}")
    logger.info(f"  Sum columns: {len(sum_cols)}")
    
    half_hourly = (
        df.group_by("timestamp")
        .agg([
            # Mean for generation, demand, and intensities
            *(pl.col(c).mean().alias(c) for c in avg_cols if c in df.columns),
            # Sum for absolute emissions
            *(pl.col(c).sum().alias(c) for c in sum_cols if c in df.columns),
        ])
        .sort("timestamp")
    )
    
    # Verify output
    tmin_out = half_hourly.select(pl.col("timestamp").min()).item()
    tmax_out = half_hourly.select(pl.col("timestamp").max()).item()
    logger.info(f"Output time range: {tmin_out} → {tmax_out}")
    logger.info(f"Output shape: {half_hourly.height:,} rows")
    
    # Check aggregation ratio
    expected_ratio = 6  # 30 min / 5 min = 6
    actual_ratio = df.height / half_hourly.height
    logger.info(f"Aggregation ratio: {actual_ratio:.2f} (expected ~{expected_ratio})")
    
    if abs(actual_ratio - expected_ratio) > 0.5:
        logger.warning(f"⚠ Aggregation ratio differs from expected ({actual_ratio:.2f} vs {expected_ratio})")
    
    return half_hourly
