# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Spatial Aggregation Engine
===========================

Aggregate gridded weather data to national/regional time-series using
area-weighted averaging.

Key Features
------------
- Area weighting by cos(latitude)
- Hierarchical aggregation (ADM0, ADM1, ADM2)
- Intensive vs extensive field handling
- Preserve temporal resolution
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Literal

import polars as pl
import numpy as np

from ..utils.logging import VerboseLogger


# =============================================================================
# Variable Classifications
# =============================================================================

# Intensive fields (area-weighted average)
DEFAULT_INTENSIVE_VARS = [
    "temperature_2m",
    "wind_u_10m",
    "wind_v_10m",
    "wind_u_100m",
    "wind_v_100m",
    "total_cloud_cover",
    "high_cloud_cover",
    "medium_cloud_cover",
    "low_cloud_cover",
    "k_index",
    "high_vegetation_cover",
    "low_vegetation_cover",
    "leaf_area_index_high_vegetation",
    "leaf_area_index_low_vegetation",
]

# Extensive fields (sum)
DEFAULT_EXTENSIVE_VARS = [
    "total_precipitation",
    "surface_net_short_wave_solar_radiation",
    "surface_net_long_wave_thermal_radiation",
    "surface_direct_short_wave_solar_radiation",
    "surface_short_wave_solar_radiation_downwards",
    "surface_long_wave_thermal_radiation_downwards",
    "top_net_short_wave_solar_radiation",
    "top_net_long_wave_thermal_radiation",
    "surface_downward_uv_radiation",
]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AggregationResult:
    """Result of spatial aggregation."""
    output_file: Path
    aggregation_level: str
    temporal_resolution: str
    num_regions: int
    num_timesteps: int
    processing_time_s: float


# =============================================================================
# Spatial Aggregator
# =============================================================================

class SpatialAggregator:
    """
    Aggregate gridded data to regional time-series.
    
    Parameters
    ----------
    aggregation_level : {'ADM0', 'ADM1', 'ADM2'}
        Administrative level for aggregation.
    weight_by_area : bool, optional
        Use area weighting (cos(latitude)).
    intensive_vars : list of str, optional
        Variables to aggregate using weighted average.
    extensive_vars : list of str, optional
        Variables to aggregate using sum.
    logger : VerboseLogger, optional
        Logger instance.
    
    Examples
    --------
    >>> aggregator = SpatialAggregator(aggregation_level="ADM1")
    >>> result = aggregator.aggregate_file(
    ...     input_file=Path("transformed/2018_halfhourly.parquet"),
    ...     output_file=Path("national/2018_ADM1_halfhourly.parquet")
    ... )
    """
    
    def __init__(
        self,
        aggregation_level: Literal["ADM0", "ADM1", "ADM2"] = "ADM0",
        weight_by_area: bool = True,
        intensive_vars: Optional[List[str]] = None,
        extensive_vars: Optional[List[str]] = None,
        logger: Optional[VerboseLogger] = None,
    ):
        self.aggregation_level = aggregation_level
        self.weight_by_area = weight_by_area
        self.intensive_vars = intensive_vars or DEFAULT_INTENSIVE_VARS
        self.extensive_vars = extensive_vars or DEFAULT_EXTENSIVE_VARS
        self.logger = logger or VerboseLogger("spatial_aggregator", verbose=False)
    
    def _compute_area_weights(
        self,
        df: pl.DataFrame | pl.LazyFrame
    ) -> pl.DataFrame | pl.LazyFrame:
        """
        Add area weight column based on cos(latitude).
        
        Area of grid cell ∝ cos(latitude)
        """
        df = df.with_columns(
            (pl.col("latitude") * np.pi / 180.0).cos().alias("area_weight")
        )
        
        # Also multiply by fractional coverage if available
        if "frac_in_region" in df.collect_schema().names():
            df = df.with_columns(
                (pl.col("area_weight") * pl.col("frac_in_region")).alias("area_weight")
            )
        
        return df
    
    def _get_group_columns(self, schema_cols: List[str]) -> List[str]:
        """Determine grouping columns based on aggregation level."""
        group_cols = ["time"]  # Always group by time
        
        if self.aggregation_level == "ADM0":
            # National level - just time
            pass
        elif self.aggregation_level == "ADM1":
            # State/province level
            if "adm1_code" in schema_cols:
                group_cols.append("adm1_code")
                if "adm1_name" in schema_cols:
                    group_cols.append("adm1_name")
        elif self.aggregation_level == "ADM2":
            # District level
            if "adm2_code" in schema_cols:
                group_cols.append("adm2_code")
                if "adm2_name" in schema_cols:
                    group_cols.append("adm2_name")
            # Also preserve ADM1 for hierarchy
            if "adm1_code" in schema_cols:
                group_cols.append("adm1_code")
                if "adm1_name" in schema_cols:
                    group_cols.append("adm1_name")
        
        return group_cols
    
    def aggregate_file(
        self,
        input_file: Path,
        output_file: Path,
        temporal_agg: Optional[str] = None,
        overwrite: bool = True
    ) -> AggregationResult:
        """
        Aggregate a single gridded file to regional time-series.
        
        Parameters
        ----------
        input_file : Path
            Input half-hourly gridded file.
        output_file : Path
            Output aggregated file.
        temporal_agg : str, optional
            Temporal aggregation ('daily', 'weekly', 'monthly', 'annual').
            If None, preserve original temporal resolution.
        overwrite : bool, optional
            Overwrite existing output.
        
        Returns
        -------
        AggregationResult
            Processing result.
        """
        t0 = time.perf_counter()
        
        if output_file.exists() and not overwrite:
            self.logger.debug(f"Skipping {output_file.name} (exists)")
            return None
        
        self.logger.info(f"Aggregating {input_file.name}", force=True)
        self.logger.info(f"  Level: {self.aggregation_level}")
        
        # Load data
        lf = pl.scan_parquet(input_file)
        
        # Get schema
        schema_cols = lf.collect_schema().names()
        
        # Compute area weights
        if self.weight_by_area:
            lf = self._compute_area_weights(lf)
        else:
            lf = lf.with_columns(pl.lit(1.0).alias("area_weight"))
        
        # Identify which variables are present
        intensive_present = [v for v in self.intensive_vars if v in schema_cols]
        extensive_present = [v for v in self.extensive_vars if v in schema_cols]
        
        # Get grouping columns
        group_cols = self._get_group_columns(schema_cols)
        
        # Apply temporal aggregation if requested
        if temporal_agg:
            if temporal_agg == "daily":
                lf = lf.with_columns(pl.col("time").dt.truncate("1d").alias("time"))
            elif temporal_agg == "weekly":
                lf = lf.with_columns(pl.col("time").dt.truncate("1w").alias("time"))
            elif temporal_agg == "monthly":
                lf = lf.with_columns(pl.col("time").dt.truncate("1mo").alias("time"))
            elif temporal_agg == "annual":
                lf = lf.with_columns(pl.col("time").dt.truncate("1y").alias("time"))
        
        # Build aggregation expressions
        agg_exprs = []
        
        # Intensive variables: weighted average
        for var in intensive_present:
            agg_exprs.append(
                (
                    (pl.col(var) * pl.col("area_weight")).sum()
                    / pl.col("area_weight").sum()
                ).alias(var)
            )
        
        # Extensive variables: weighted sum
        for var in extensive_present:
            agg_exprs.append(
                (pl.col(var) * pl.col("area_weight")).sum().alias(var)
            )
        
        # Aggregate
        lf_agg = lf.group_by(group_cols).agg(agg_exprs)
        
        # Sort by time and region
        lf_agg = lf_agg.sort(group_cols)
        
        # Collect and write
        df_result = lf_agg.collect()
        
        num_regions = 1
        if self.aggregation_level != "ADM0":
            region_col = "adm1_code" if self.aggregation_level == "ADM1" else "adm2_code"
            if region_col in df_result.columns:
                num_regions = df_result.select(pl.col(region_col).n_unique()).item()
        
        num_timesteps = df_result.select(pl.col("time").n_unique()).item()
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df_result.write_parquet(output_file, compression="zstd", statistics=True)
        
        dt = time.perf_counter() - t0
        
        self.logger.info(
            f"  Complete: {num_regions} region(s), {num_timesteps:,} timesteps ({dt:.2f}s)",
            force=True
        )
        
        return AggregationResult(
            output_file=output_file,
            aggregation_level=self.aggregation_level,
            temporal_resolution=temporal_agg or "original",
            num_regions=num_regions,
            num_timesteps=num_timesteps,
            processing_time_s=dt,
        )


# =============================================================================
# Temporal Aggregation Helper
# =============================================================================

def aggregate_temporal(
    df: pl.DataFrame,
    mode: Literal["daily", "weekly", "monthly", "annual"],
    intensive_cols: List[str],
    extensive_cols: List[str],
    group_cols: Optional[List[str]] = None
) -> pl.DataFrame:
    """
    Temporally aggregate a regional time-series.
    
    Parameters
    ----------
    df : pl.DataFrame
        Input time-series (already spatially aggregated).
    mode : str
        Temporal aggregation mode.
    intensive_cols : list of str
        Columns to average.
    extensive_cols : list of str
        Columns to sum.
    group_cols : list of str, optional
        Additional grouping columns (e.g., region codes).
    
    Returns
    -------
    pl.DataFrame
        Temporally aggregated time-series.
    """
    group_cols = group_cols or []
    
    # Truncate time
    if mode == "daily":
        df = df.with_columns(pl.col("time").dt.truncate("1d").alias("time"))
    elif mode == "weekly":
        df = df.with_columns(pl.col("time").dt.truncate("1w").alias("time"))
    elif mode == "monthly":
        df = df.with_columns(pl.col("time").dt.truncate("1mo").alias("time"))
    elif mode == "annual":
        df = df.with_columns(pl.col("time").dt.truncate("1y").alias("time"))
    
    # Build aggregation expressions
    agg_exprs = []
    
    # Intensive: mean
    for col in intensive_cols:
        if col in df.columns:
            agg_exprs.append(pl.col(col).mean().alias(col))
    
    # Extensive: sum
    for col in extensive_cols:
        if col in df.columns:
            agg_exprs.append(pl.col(col).sum().alias(col))
    
    # Aggregate
    df_agg = df.group_by(["time"] + group_cols).agg(agg_exprs)
    
    return df_agg.sort(["time"] + group_cols)
