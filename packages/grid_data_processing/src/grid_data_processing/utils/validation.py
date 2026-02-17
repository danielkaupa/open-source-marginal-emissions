"""
Validation utilities for grid data processing.

This module provides comprehensive validation checks for processed grid data,
ensuring data quality, completeness, and consistency across the pipeline.
"""

import logging
from typing import Optional, Dict, Any

import polars as pl


def validate_processed_data(
    df: pl.DataFrame,
    expected_interval_minutes: int = 30,
    logger: Optional[logging.Logger] = None
) -> Dict[str, Any]:
    """
    Validate processed grid data with comprehensive checks.
    
    This function performs multiple validation checks:
    - Data shape and structure
    - Time range and timezone information
    - Time interval consistency (no unexpected gaps)
    - Null value detection
    - Value range checks (e.g., no negative generation)
    
    Parameters
    ----------
    df : pl.DataFrame
        Processed dataframe to validate
    expected_interval_minutes : int
        Expected time interval between consecutive records (default: 30)
    logger : logging.Logger, optional
        Logger instance for outputting validation results
        
    Returns
    -------
    dict
        Validation report with results of all checks
        
    Examples
    --------
    >>> df = pl.read_parquet("final_output.parquet")
    >>> report = validate_processed_data(df, expected_interval_minutes=30)
    >>> print(f"Total rows: {report['n_rows']}")
    >>> print(f"Has nulls: {report['has_nulls']}")
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    report = {}
    
    # Check shape
    report["n_rows"] = df.height
    report["n_cols"] = df.width
    logger.info(f"Shape: {df.height:,} rows × {df.width} columns")
    
    # Check timestamp column
    if "timestamp" not in df.columns:
        logger.warning("⚠ No 'timestamp' column found")
        report["has_timestamp"] = False
        return report
    
    report["has_timestamp"] = True
    
    # Check time range
    tmin = df.select(pl.col("timestamp").min()).item()
    tmax = df.select(pl.col("timestamp").max()).item()
    report["time_range"] = (str(tmin), str(tmax))
    logger.info(f"Time range: {tmin} → {tmax}")
    
    # Calculate time span
    time_span = tmax - tmin
    report["time_span_days"] = time_span.total_seconds() / 86400
    logger.info(f"Time span: {report['time_span_days']:.1f} days")
    
    # Check timezone
    if df.schema["timestamp"].time_zone is not None:
        tz = df.schema["timestamp"].time_zone
        report["timezone"] = tz
        logger.info(f"✓ Timezone: {tz}")
    else:
        report["timezone"] = None
        logger.warning("⚠ Timestamp is timezone-naive")
    
    # Check for time gaps
    logger.info("Checking time interval consistency...")
    time_diffs = df.select(
        pl.col("timestamp").diff().alias("time_diff")
    ).drop_nulls()
    
    expected_diff = pl.duration(minutes=expected_interval_minutes)
    
    # Count unexpected gaps
    unexpected_gaps = time_diffs.filter(
        pl.col("time_diff") != expected_diff
    )
    
    if unexpected_gaps.height > 0:
        report["unexpected_gaps"] = unexpected_gaps.height
        logger.warning(f"⚠ Found {unexpected_gaps.height:,} unexpected time gaps")
        
        # Show some examples of gap sizes
        gap_samples = unexpected_gaps.head(5)
        for row in gap_samples.iter_rows(named=True):
            logger.warning(f"  Gap size: {row['time_diff']}")
    else:
        report["unexpected_gaps"] = 0
        logger.info(f"✓ All time intervals consistent ({expected_interval_minutes} minutes)")
    
    # Check for null values
    logger.info("Checking for null values...")
    null_counts = df.null_count()
    has_nulls = False
    null_details = {}
    
    for col in df.columns:
        count = null_counts[col][0]
        if count > 0:
            has_nulls = True
            pct = 100 * count / df.height
            null_details[col] = {"count": count, "percentage": pct}
            logger.warning(f"⚠ Column '{col}' has {count:,} null values ({pct:.2f}%)")
    
    if not has_nulls:
        logger.info("✓ No null values found")
    
    report["has_nulls"] = has_nulls
    report["null_details"] = null_details
    
    # Check for negative values in generation columns
    logger.info("Checking for invalid values in generation columns...")
    gen_cols = [c for c in df.columns if "generation" in c.lower()]
    negative_issues = {}
    
    for col in gen_cols:
        if col in df.columns and df.schema[col].is_numeric():
            min_val = df.select(pl.col(col).min()).item()
            if min_val is not None and min_val < 0:
                negative_issues[col] = min_val
                logger.warning(f"⚠ Column '{col}' has negative values (min: {min_val:.2f})")
    
    if not negative_issues:
        logger.info("✓ No negative values in generation columns")
    
    report["negative_generation"] = negative_issues
    
    # Summary statistics for key columns
    logger.info("Summary statistics for key columns:")
    key_cols = [
        "demand_met", "total_generation", "renewable_generation",
        "thermal_generation", "tons_co2", "g_co2_per_kwh"
    ]
    
    stats_cols = [c for c in key_cols if c in df.columns]
    if stats_cols:
        stats_df = df.select(stats_cols).describe()
        
        # Log statistics in a readable format
        for stat_row in stats_df.iter_rows(named=True):
            stat_name = stat_row.get("statistic", stat_row.get("describe", ""))
            logger.info(f"  {stat_name}:")
            for col in stats_cols:
                value = stat_row.get(col)
                if value is not None:
                    logger.info(f"    {col}: {value:,.2f}")
    
    logger.info("")
    logger.info("Validation complete")
    
    return report


def validate_config_compatibility(
    df: pl.DataFrame,
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None
) -> bool:
    """
    Validate that a dataframe's columns match the configuration.
    
    This checks that all columns specified in the config for gap filling
    and aggregation actually exist in the dataframe.
    
    Parameters
    ----------
    df : pl.DataFrame
        Dataframe to validate
    config : dict
        Configuration dictionary
    logger : logging.Logger, optional
        Logger instance
        
    Returns
    -------
    bool
        True if all required columns exist, False otherwise
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    all_valid = True
    df_cols = set(df.columns)
    
    # Check gap filling columns
    if "gap_filling" in config:
        gap_cols = config["gap_filling"].get("columns_to_fill", [])
        missing_cols = [c for c in gap_cols if c not in df_cols]
        
        if missing_cols:
            logger.warning(f"⚠ Gap filling config references missing columns: {missing_cols}")
            all_valid = False
    
    # Check aggregation columns
    if "aggregation" in config:
        avg_cols = config["aggregation"].get("avg_columns", [])
        sum_cols = config["aggregation"].get("sum_columns", [])
        
        missing_avg = [c for c in avg_cols if c not in df_cols]
        missing_sum = [c for c in sum_cols if c not in df_cols]
        
        if missing_avg:
            logger.warning(f"⚠ Aggregation avg_columns config references missing columns: {missing_avg}")
            all_valid = False
        
        if missing_sum:
            logger.warning(f"⚠ Aggregation sum_columns config references missing columns: {missing_sum}")
            all_valid = False
    
    if all_valid:
        logger.info("✓ All config columns present in dataframe")
    
    return all_valid
