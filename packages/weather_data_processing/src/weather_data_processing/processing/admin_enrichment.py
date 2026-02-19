# packages/weather_data_processing/src/weather_data_processing/processing/admin_enrichment.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Administrative Boundary Enrichment
===================================

Add ADM1 (state/province) and ADM2 (district/county) columns to gridded
weather data based on lat/lon coordinates.

This module enables downstream aggregation at different administrative levels
while preserving hierarchical relationships (ADM2 ⊂ ADM1 ⊂ ADM0).

Key Features
------------
- Spatial join of (lat, lon) points to ADM shapefiles
- ISO code and name columns for each admin level
- Configurable handling of undefined regions (islands, offshore areas)
- Lazy evaluation with Polars for memory efficiency
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Dict, Any

import geopandas as gpd
import polars as pl
from shapely.geometry import Point

from ..config_schema import ADMEnrichmentConfig
from ..utils.logging import VerboseLogger


class ADMEnricher:
    """
    Enrich gridded data with administrative boundary information.

    Parameters
    ----------
    config : ADMEnrichmentConfig
        Configuration specifying ADM levels, field names, and defaults.
    adm1_shapefile : Path or None
        Path to ADM1 shapefile (required if enable_adm1=True).
    adm2_shapefile : Path or None
        Path to ADM2 shapefile (required if enable_adm2=True).
    logger : VerboseLogger or None
        Logger instance for progress/debug messages.

    Attributes
    ----------
    config : ADMEnrichmentConfig
        Configuration settings.
    gdf_adm1 : gpd.GeoDataFrame or None
        Loaded ADM1 boundaries.
    gdf_adm2 : gpd.GeoDataFrame or None
        Loaded ADM2 boundaries.
    logger : VerboseLogger
        Logger instance.

    Examples
    --------
    >>> from pathlib import Path
    >>> config = ADMEnrichmentConfig(enable_adm1=True, enable_adm2=True)
    >>> enricher = ADMEnricher(
    ...     config=config,
    ...     adm1_shapefile=Path("data/geoBoundaries/ADM1.zip"),
    ...     adm2_shapefile=Path("data/geoBoundaries/ADM2.zip"),
    ... )
    >>> df_enriched = enricher.enrich(df)
    >>> print(df_enriched.columns)
    ['latitude', 'longitude', 'time', ..., 'adm1_name', 'adm1_code', 'adm2_name', 'adm2_code']
    """

    def __init__(
        self,
        config: ADMEnrichmentConfig,
        adm1_shapefile: Optional[Path] = None,
        adm2_shapefile: Optional[Path] = None,
        logger: Optional[VerboseLogger] = None,
    ):
        self.config = config
        self.logger = logger or VerboseLogger("adm_enricher", verbose=False)

        self.gdf_adm1: Optional[gpd.GeoDataFrame] = None
        self.gdf_adm2: Optional[gpd.GeoDataFrame] = None

        # Load ADM1 if requested
        if config.enable_adm1:
            if adm1_shapefile is None:
                raise ValueError("adm1_shapefile required when enable_adm1=True")
            self.gdf_adm1 = self._load_shapefile(
                adm1_shapefile, level="ADM1"
            )

        # Load ADM2 if requested
        if config.enable_adm2:
            if adm2_shapefile is None:
                raise ValueError("adm2_shapefile required when enable_adm2=True")
            self.gdf_adm2 = self._load_shapefile(
                adm2_shapefile, level="ADM2"
            )

    def _load_shapefile(
        self,
        path: Path,
        level: str
    ) -> gpd.GeoDataFrame:
        """
        Load and prepare a shapefile for spatial joins.

        Parameters
        ----------
        path : Path
            Path to shapefile (can be .zip or .shp).
        level : str
            Administrative level ('ADM1' or 'ADM2') for logging.

        Returns
        -------
        gpd.GeoDataFrame
            Loaded and projected GeoDataFrame in EPSG:4326.
        """
        t0 = time.perf_counter()
        self.logger.info(f"Loading {level} shapefile: {path}", force=True)

        if not path.exists():
            raise FileNotFoundError(f"{level} shapefile not found: {path}")

        gdf = gpd.read_file(path)

        # Ensure WGS84 projection
        if gdf.crs is None or gdf.crs.to_string() != "EPSG:4326":
            self.logger.warning(
                f"{level} shapefile not in EPSG:4326, reprojecting..."
            )
            gdf = gdf.to_crs(epsg=4326)

        dt = time.perf_counter() - t0
        self.logger.info(
            f"Loaded {level}: {len(gdf)} features in {dt:.2f}s"
        )

        return gdf

    def _spatial_join_to_adm(
        self,
        df: pl.DataFrame,
        gdf_adm: gpd.GeoDataFrame,
        name_field: str,
        code_field: Optional[str],
        level: str
    ) -> pl.DataFrame:
        """
        Perform spatial join to assign administrative boundaries.

        Parameters
        ----------
        df : pl.DataFrame
            Input DataFrame with 'latitude' and 'longitude' columns.
        gdf_adm : gpd.GeoDataFrame
            Administrative boundary GeoDataFrame.
        name_field : str
            Field in gdf_adm containing boundary names.
        code_field : str or None
            Field in gdf_adm containing ISO codes (optional).
        level : str
            Level name for output columns (e.g., 'adm1').

        Returns
        -------
        pl.DataFrame
            Input DataFrame with added '{level}_name' and '{level}_code' columns.
        """
        t0 = time.perf_counter()
        self.logger.info(f"Performing spatial join for {level.upper()}...")

        # Extract unique (lat, lon) pairs
        unique_coords = (
            df.select(["latitude", "longitude"])
            .unique()
            .collect() if hasattr(df, 'collect') else df.select(["latitude", "longitude"]).unique()
        )

        n_unique = unique_coords.height
        self.logger.debug(f"  {n_unique} unique coordinate pairs to process")

        # Convert to GeoDataFrame
        geometry = [
            Point(row["longitude"], row["latitude"])
            for row in unique_coords.iter_rows(named=True)
        ]

        gdf_points = gpd.GeoDataFrame(
            unique_coords.to_pandas(),
            geometry=geometry,
            crs="EPSG:4326"
        )

        # Spatial join
        joined = gpd.sjoin(
            gdf_points,
            gdf_adm[[name_field, code_field, "geometry"] if code_field else [name_field, "geometry"]],
            how="left",
            predicate="within"
        )

        # Build result columns
        result_cols = {
            f"{level}_name": joined[name_field].fillna(self.config.undefined_value)
        }

        if code_field and code_field in joined.columns:
            result_cols[f"{level}_code"] = joined[code_field].fillna(self.config.undefined_value)

        # Convert back to Polars
        result_df = pl.from_pandas(
            joined[["latitude", "longitude"]].assign(**result_cols)
        )

        # Join back to original dataframe
        if hasattr(df, 'collect'):
            # LazyFrame
            df_enriched = df.join(
                result_df.lazy(),
                on=["latitude", "longitude"],
                how="left"
            )
        else:
            # DataFrame
            df_enriched = df.join(
                result_df,
                on=["latitude", "longitude"],
                how="left"
            )

        dt = time.perf_counter() - t0

        # Count undefined
        if hasattr(df_enriched, 'collect'):
            n_undefined = (
                df_enriched.select(pl.col(f"{level}_name"))
                .collect()
                .filter(pl.col(f"{level}_name") == self.config.undefined_value)
                .height
            )
        else:
            n_undefined = df_enriched.filter(
                pl.col(f"{level}_name") == self.config.undefined_value
            ).height

        self.logger.info(
            f"  {level.upper()} join complete in {dt:.2f}s "
            f"({n_undefined}/{n_unique} undefined)"
        )

        return df_enriched

    def enrich(
        self,
        df: pl.DataFrame | pl.LazyFrame
    ) -> pl.DataFrame | pl.LazyFrame:
        """
        Add ADM1 and/or ADM2 columns to a DataFrame.

        Parameters
        ----------
        df : pl.DataFrame or pl.LazyFrame
            Input data with 'latitude' and 'longitude' columns.

        Returns
        -------
        pl.DataFrame or pl.LazyFrame
            DataFrame with added administrative boundary columns:
            - '{level}_name': Name of the administrative region
            - '{level}_code': ISO code of the region (if available)

        Raises
        ------
        ValueError
            If required columns are missing.

        Notes
        -----
        The function preserves the input type (DataFrame vs LazyFrame).
        For LazyFrames, joins are performed lazily but unique coordinate
        extraction requires a collect() operation.
        """
        was_lazy = hasattr(df, 'collect')

        # Validate required columns
        schema_cols = df.collect_schema().names() if was_lazy else df.columns
        if "latitude" not in schema_cols or "longitude" not in schema_cols:
            raise ValueError(
                "DataFrame must contain 'latitude' and 'longitude' columns"
            )

        result = df

        # ADM1 enrichment
        if self.config.enable_adm1 and self.gdf_adm1 is not None:
            result = self._spatial_join_to_adm(
                df=result,
                gdf_adm=self.gdf_adm1,
                name_field=self.config.adm1_name_field,
                code_field=self.config.adm1_code_field,
                level="adm1"
            )

        # ADM2 enrichment
        if self.config.enable_adm2 and self.gdf_adm2 is not None:
            result = self._spatial_join_to_adm(
                df=result,
                gdf_adm=self.gdf_adm2,
                name_field=self.config.adm2_name_field,
                code_field=self.config.adm2_code_field,
                level="adm2"
            )

        return result

    def summary(self) -> Dict[str, Any]:
        """
        Get enrichment configuration summary.

        Returns
        -------
        dict
            Summary of enabled levels and settings.
        """
        return {
            "adm1_enabled": self.config.enable_adm1,
            "adm2_enabled": self.config.enable_adm2,
            "adm1_loaded": self.gdf_adm1 is not None,
            "adm2_loaded": self.gdf_adm2 is not None,
            "adm1_features": len(self.gdf_adm1) if self.gdf_adm1 is not None else 0,
            "adm2_features": len(self.gdf_adm2) if self.gdf_adm2 is not None else 0,
            "undefined_value": self.config.undefined_value,
        }
