# packages/weather_data_processing/src/weather_data_processing/processing/aggregation.py
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
- Dual avg/total output for extensive (radiation, precipitation) variables
- Wind speed and direction derived from weighted-average u/v components
- Preserves half-hourly temporal resolution (NO temporal aggregation)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Literal

import polars as pl
import numpy as np

from ..utils.logging import VerboseLogger


# =============================================================================
# Variable Classifications (ERA5 shortnames only)
# =============================================================================

# Intensive fields: area-weighted average only.
# Wind u/v components belong here so they receive a proper weighted mean;
# speed and direction are then derived after aggregation.
DEFAULT_INTENSIVE_VARS = [
    "t2m",
    "u10",  "v10",
    "u100", "v100",
    "tcc", "hcc", "mcc", "lcc",
    "kx",
    "cvh", "cvl",
    "lai_hv", "lai_lv",
]

# Extensive fields: produce BOTH a weighted average ({var}_avg) AND a
# weighted area-integrated total ({var}_total) in output.
#
#   {var}_avg   — intensity: how much per unit area (comparable across regions)
#   {var}_total — magnitude: how much in total over the region
DEFAULT_EXTENSIVE_VARS = [
    "tp",
    "ssr",  "ssrc",  "ssrd",  "ssrdc",
    "str",  "strc",  "strd",  "strdc",
    "tsr",  "tsrc",
    "ttr",  "ttrc",
    "cdir", "fdir",
    "uvb",
]

# Wind component pairs → derive speed + direction after spatial aggregation.
# Key is the height label used in output column names (e.g. "10m").
# Value is (u_shortname, v_shortname).
DEFAULT_WIND_PAIRS: Dict[str, Tuple[str, str]] = {
    "10m":  ("u10",  "v10"),
    "100m": ("u100", "v100"),
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SpatialAggregationResult:
    """Result of spatial aggregation."""
    output_file: Path
    aggregation_level: str
    num_regions: int
    num_timesteps: int
    processing_time_s: float


# =============================================================================
# Spatial Aggregator
# =============================================================================

class SpatialAggregator:
    """
    Aggregate gridded data to regional time-series.

    For intensive variables (temperature, cloud cover, wind components, etc.)
    a single area-weighted mean column is produced with the bare variable name.

    For extensive variables (radiation, precipitation) two columns are produced:
        ``{var}_avg``   — area-weighted mean (intensity, comparable across regions)
        ``{var}_total`` — area-weighted sum   (magnitude, energy/mass budget)

    After spatial aggregation, wind speed and direction are derived from the
    weighted-average u/v columns and appended as:
        ``wind_{height}_speed``   — m/s
        ``wind_{height}_dir_deg`` — meteorological degrees (0 = N, 90 = E)

    **Temporal resolution is always preserved** — half-hourly input produces
    half-hourly output.

    Parameters
    ----------
    aggregation_level : {'ADM0', 'ADM1', 'ADM2'}
        Administrative level for aggregation.
    weight_by_area : bool, optional
        Use cos(latitude) area weighting (default True).
    intensive_vars : list of str, optional
        Variables to aggregate with weighted mean only.
    extensive_vars : list of str, optional
        Variables to aggregate with both weighted mean and weighted sum.
    wind_pairs : dict, optional
        Mapping of height label → (u_col, v_col) for wind derivation.
    logger : VerboseLogger, optional
        Logger instance.
    """

    def __init__(
        self,
        aggregation_level: Literal["ADM0", "ADM1", "ADM2"] = "ADM0",
        weight_by_area: bool = True,
        intensive_vars: Optional[List[str]] = None,
        extensive_vars: Optional[List[str]] = None,
        wind_pairs: Optional[Dict[str, Tuple[str, str]]] = None,
        logger: Optional[VerboseLogger] = None,
    ):
        self.aggregation_level = aggregation_level
        self.weight_by_area = weight_by_area
        self.intensive_vars = intensive_vars if intensive_vars is not None else DEFAULT_INTENSIVE_VARS
        self.extensive_vars = extensive_vars if extensive_vars is not None else DEFAULT_EXTENSIVE_VARS
        self.wind_pairs = wind_pairs if wind_pairs is not None else DEFAULT_WIND_PAIRS
        self.logger = logger or VerboseLogger("spatial_aggregator", verbose=False)

    def _compute_area_weights(
        self,
        lf: pl.LazyFrame,
    ) -> pl.LazyFrame:
        """
        Add ``area_weight`` column: cos(latitude) × frac_in_region (if present).

        Grid cell area ∝ cos(latitude).  Multiplying by fractional coverage
        (from combined-mode masking) further weights border cells correctly.
        """
        lf = lf.with_columns(
            (pl.col("latitude") * np.pi / 180.0).cos().alias("area_weight")
        )
        if "frac_in_region" in lf.collect_schema().names():
            lf = lf.with_columns(
                (pl.col("area_weight") * pl.col("frac_in_region")).alias("area_weight")
            )
        return lf

    def _get_group_columns(self, schema_cols: List[str]) -> List[str]:
        """Determine grouping columns based on aggregation level."""
        group_cols = ["time"]
        if self.aggregation_level == "ADM1":
            if "adm1_code" in schema_cols:
                group_cols.append("adm1_code")
                if "adm1_name" in schema_cols:
                    group_cols.append("adm1_name")
        elif self.aggregation_level == "ADM2":
            if "adm2_code" in schema_cols:
                group_cols.append("adm2_code")
                if "adm2_name" in schema_cols:
                    group_cols.append("adm2_name")
            if "adm1_code" in schema_cols:
                group_cols.append("adm1_code")
                if "adm1_name" in schema_cols:
                    group_cols.append("adm1_name")
        return group_cols

    def _derive_wind(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Append wind speed and meteorological direction columns.

        Requires weighted-mean u/v columns (bare variable names) to already
        be present in ``df`` from the spatial aggregation step.

        Speed:     sqrt(u² + v²)  [m/s]
        Direction: meteorological convention — the direction FROM which the
                   wind is blowing, measured clockwise from north.
                   dir = (270 − atan2(v, u) × 180/π) mod 360
        """
        for height, (u_col, v_col) in self.wind_pairs.items():
            if u_col not in df.columns or v_col not in df.columns:
                continue
            df = df.with_columns([
                ((pl.col(u_col) ** 2 + pl.col(v_col) ** 2).sqrt())
                    .alias(f"wind_{height}_speed"),
                (
                    (270.0 - (
                        pl.arctan2(pl.col(v_col), pl.col(u_col)) * 180.0 / np.pi
                    )) % 360.0
                ).alias(f"wind_{height}_dir_deg"),
            ])
        return df

    def aggregate_file(
        self,
        input_file: Path,
        output_file: Path,
        overwrite: bool = True,
    ) -> SpatialAggregationResult:
        """
        Spatially aggregate a gridded half-hourly file to a regional time-series.

        Half-hourly temporal resolution is preserved (half-hourly in, half-hourly out).

        Parameters
        ----------
        input_file : Path
            Input half-hourly gridded parquet (one row per cell per timestep).
        output_file : Path
            Output aggregated parquet (one row per region per timestep).
        overwrite : bool, optional
            Overwrite existing output.

        Returns
        -------
        SpatialAggregationResult
        """
        t0 = time.perf_counter()

        if output_file.exists() and not overwrite:
            self.logger.debug(f"Skipping {output_file.name} (exists)")
            return None

        self.logger.info(f"Aggregating {input_file.name}", force=True)
        self.logger.info(f"  Level: {self.aggregation_level}")

        lf = pl.scan_parquet(input_file)
        schema_cols = lf.collect_schema().names()

        # Area weights
        if self.weight_by_area:
            lf = self._compute_area_weights(lf)
        else:
            lf = lf.with_columns(pl.lit(1.0).alias("area_weight"))

        # Identify present variables
        intensive_present = [v for v in self.intensive_vars if v in schema_cols]
        extensive_present = [v for v in self.extensive_vars if v in schema_cols]

        group_cols = self._get_group_columns(schema_cols)

        # Build aggregation expressions
        agg_exprs = []

        # Intensive → single weighted mean, bare column name
        for var in intensive_present:
            agg_exprs.append(
                (
                    (pl.col(var) * pl.col("area_weight")).sum()
                    / pl.col("area_weight").sum()
                ).alias(var)
            )

        # Extensive → weighted mean (_avg) + weighted sum (_total)
        for var in extensive_present:
            agg_exprs.append(
                (
                    (pl.col(var) * pl.col("area_weight")).sum()
                    / pl.col("area_weight").sum()
                ).alias(f"{var}_avg")
            )
            agg_exprs.append(
                (pl.col(var) * pl.col("area_weight")).sum().alias(f"{var}_total")
            )

        lf_agg = lf.group_by(group_cols).agg(agg_exprs)
        lf_agg = lf_agg.sort(group_cols)
        df_result = lf_agg.collect()

        # Derive wind speed and direction from averaged u/v
        df_result = self._derive_wind(df_result)

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
            f"  Complete: {num_regions} region(s), {num_timesteps:,} half-hourly timesteps ({dt:.2f}s)",
            force=True
        )

        return SpatialAggregationResult(
            output_file=output_file,
            aggregation_level=self.aggregation_level,
            num_regions=num_regions,
            num_timesteps=num_timesteps,
            processing_time_s=dt,
        )