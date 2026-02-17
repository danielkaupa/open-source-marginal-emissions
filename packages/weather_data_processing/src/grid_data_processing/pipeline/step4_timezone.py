"""
Timezone Setting
================

Set (label) timezone on grid data timestamps.

IMPORTANT: The data is already in Asia/Kolkata timezone, but the timestamps
are naive (unlabeled). This step LABELS the timezone without converting/shifting
the actual time values.

Uses replace_time_zone() NOT convert_time_zone().
"""

import logging
from pathlib import Path
from typing import Optional

import polars as pl


def set_timezone(
    input_path: Path,
    target_tz: str,
    timestamp_col: str = "timestamp",
    logger: Optional[logging.Logger] = None
) -> pl.DataFrame:
    """
    Label timestamps with the correct timezone.
    
    IMPORTANT: This does NOT convert times. The data is already in the target
    timezone; we're just adding the timezone label to previously naive timestamps.
    
    Parameters
    ----------
    input_path : Path
        Input parquet file
    target_tz : str
        Timezone to label (e.g., "Asia/Kolkata")
    timestamp_col : str
        Name of timestamp column
    logger : logging.Logger, optional
        Logger instance
        
    Returns
    -------
    pl.DataFrame
        DataFrame with timezone-aware timestamps
        
    Examples
    --------
    >>> df = set_timezone(
    ...     input_path="data.parquet",
    ...     target_tz="Asia/Kolkata"
    ... )
    # Timestamps are now labeled as Asia/Kolkata
    # but the actual time values are unchanged
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    logger.info(f"Loading data from: {input_path}")
    lf = pl.scan_parquet(input_path)
    
    # Get min/max timestamps before setting timezone (for logging)
    sample = lf.select([
        pl.col(timestamp_col).min().alias("min_ts"),
        pl.col(timestamp_col).max().alias("max_ts")
    ]).collect()
    
    min_ts_naive = sample["min_ts"][0]
    max_ts_naive = sample["max_ts"][0]
    
    logger.info(f"Timestamp range (naive): {min_ts_naive} → {max_ts_naive}")
    logger.info(f"Setting timezone label to: {target_tz}")
    logger.info("NOTE: This does NOT shift times - just labels them")
    
    # CRITICAL: Use replace_time_zone to LABEL, not convert
    lf = lf.with_columns(
        pl.col(timestamp_col)
        .dt.replace_time_zone(target_tz)
        .alias(timestamp_col)
    )
    
    df = lf.collect()
    
    # Verify timestamps after labeling
    min_ts_aware = df.select(pl.col(timestamp_col).min()).item()
    max_ts_aware = df.select(pl.col(timestamp_col).max()).item()
    
    logger.info(f"Timestamp range (labeled): {min_ts_aware} → {max_ts_aware}")
    logger.info(f"✓ Timezone set to {target_tz}")
    
    return df
