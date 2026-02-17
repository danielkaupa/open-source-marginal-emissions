"""
Step 1: Combine Monthly Files
==============================

Combine monthly parquet files into a single consolidated file.
"""

import logging
from pathlib import Path
from typing import Optional
import glob

import polars as pl


def combine_monthly_files(
    monthly_dir: Path,
    output_path: Path,
    logger: Optional[logging.Logger] = None
) -> Path:
    """
    Combine monthly parquet files into a single file.
    
    Parameters
    ----------
    monthly_dir : Path
        Directory containing monthly parquet files
    output_path : Path
        Output file path for combined data
    logger : logging.Logger, optional
        Logger instance
        
    Returns
    -------
    Path
        Path to combined file
        
    Examples
    --------
    >>> combine_monthly_files(
    ...     monthly_dir=Path("data/grid_data/raw/monthly"),
    ...     output_path=Path("data/grid_data/raw/combined.parquet")
    ... )
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    monthly_dir = Path(monthly_dir)
    output_path = Path(output_path)
    
    if not monthly_dir.exists():
        raise FileNotFoundError(f"Monthly directory not found: {monthly_dir}")
    
    # Find all monthly parquet files
    pattern = str(monthly_dir / "carbontracker_grid-data_*.parquet")
    files = sorted(glob.glob(pattern))
    
    if not files:
        raise FileNotFoundError(f"No parquet files found in {monthly_dir}")
    
    logger.info(f"Found {len(files)} monthly files")
    logger.info(f"First file: {Path(files[0]).name}")
    logger.info(f"Last file:  {Path(files[-1]).name}")
    
    # Create lazy frames
    lazy_frames = [pl.scan_parquet(f) for f in files]
    
    # Concatenate
    logger.info("Concatenating files...")
    combined_lazy = pl.concat(lazy_frames, how="vertical_relaxed")
    
    # Get time range for logging
    min_max = combined_lazy.select([
        pl.col("timestamp").min().alias("min_ts"),
        pl.col("timestamp").max().alias("max_ts"),
    ]).collect()
    
    min_ts = min_max["min_ts"][0]
    max_ts = min_max["max_ts"][0]
    
    logger.info(f"Combined data range: {min_ts} → {max_ts}")
    
    # Sort and save
    logger.info(f"Sorting and saving to: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    combined_lazy.sort("timestamp").sink_parquet(
        output_path,
        compression="snappy"
    )
    
    # Verify
    saved_df = pl.read_parquet(output_path)
    logger.info(f"✓ Combined file saved: {saved_df.height:,} rows")
    
    return output_path
