# packages/weather_data_processing/src/weather_data_processing/pipeline/step1_geographic.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Step 1: Geographic Processing Pipeline
=======================================

Complete geographic setup pipeline:
1. Extract country boundary from global shapefiles
2. Generate spatial mask for filtering gridded data
3. Set up ADM1/ADM2 boundary files for enrichment
4. Create audit trail visualizations

This module orchestrates all geographic preprocessing steps required before
applying the mask to GRIB files.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Dict, Any

import geopandas as gpd

from osme_common.paths import resolve_under

from ..config_schema import GeographicConfig
from ..processing.mask_builder import MaskBuilder, MaskResult
from ..utils.logging import VerboseLogger


class GeographicPipeline:
    """
    Orchestrator for geographic preprocessing steps.

    Parameters
    ----------
    config : GeographicConfig
        Complete geographic configuration.
    data_dir : Path
        Base data directory (for resolving relative paths).
    logger : VerboseLogger or None
        Logger instance.

    Examples
    --------
    >>> config = GeographicConfig(...)
    >>> pipeline = GeographicPipeline(
    ...     config=config,
    ...     data_dir=Path("data")
    ... )
    >>> result = pipeline.run(grib_dir=Path("data/era5-world/raw"))
    """

    def __init__(
        self,
        config: GeographicConfig,
        data_dir: Path,
        logger: Optional[VerboseLogger] = None,
    ):
        self.config = config
        self.logger = logger or VerboseLogger("geographic_pipeline", verbose=False)

        # Stable anchors — data_base is the resolved data/ directory
        self.data_base = data_dir  # passed in as a resolved Path from run_pipeline

        # Paths for intermediate outputs (extracted boundaries)
        self.boundary_dir = self.data_base / "geoBoundaries" / "extracted"
        self.boundary_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path_str: str) -> Path:
        """Resolve path relative to data_dir (not repo root).

        All shapefile and mask paths in the config are relative to the data
        directory (e.g. ``"geoBoundaries/..."`` → ``<data_dir>/geoBoundaries/...``).
        Using repo_root here was the original bug — geoBoundaries lives inside
        data/, not directly under the repo root.
        """
        return resolve_under(self.data_base, path_str)

    def _extract_country_boundary(self) -> Path:
        """
        Extract country boundary from ADM0 shapefile and save as GeoJSON.

        Returns
        -------
        Path
            Path to the extracted boundary GeoJSON file.
        """
        t0 = time.perf_counter()

        shapefile_path = self._resolve_path(self.config.boundary.shapefile_adm0)
        country_name = self.config.boundary.country_name
        name_field = self.config.boundary.country_field

        self.logger.info("=" * 72, force=True)
        self.logger.info("EXTRACTING COUNTRY BOUNDARY", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info(f"  Shapefile: {shapefile_path.name}")
        self.logger.info(f"  Country: {country_name}")
        self.logger.info(f"  Name field: {name_field}")

        if not shapefile_path.exists():
            raise FileNotFoundError(f"ADM0 shapefile not found: {shapefile_path}")

        # Load shapefile
        self.logger.info("Loading global boundaries...")
        gdf_world = gpd.read_file(shapefile_path)

        # Validate field exists
        if name_field not in gdf_world.columns:
            raise KeyError(
                f"Field '{name_field}' not found in shapefile. "
                f"Available: {list(gdf_world.columns)}"
            )

        # Filter for country
        self.logger.info(f"Filtering for '{country_name}'...")
        gdf_country = gdf_world[gdf_world[name_field] == country_name]

        if gdf_country.empty:
            # Try case-insensitive match
            gdf_country = gdf_world[
                gdf_world[name_field].str.lower() == country_name.lower()
            ]

            if gdf_country.empty:
                available = sorted(gdf_world[name_field].unique()[:10])
                raise ValueError(
                    f"Country '{country_name}' not found. "
                    f"Example entries: {available}"
                )

        # Ensure WGS84
        gdf_country = gdf_country.to_crs(epsg=4326)

        # Save as GeoJSON
        safe_name = country_name.replace(" ", "_")
        output_path = self.boundary_dir / f"{safe_name}.geojson"

        self.logger.info(f"Saving boundary to {output_path.name}...")
        gdf_country.to_file(output_path, driver="GeoJSON")

        dt = time.perf_counter() - t0
        self.logger.info(f"Boundary extracted successfully in {dt:.2f}s", force=True)
        self.logger.info(f"  Features: {len(gdf_country)}")
        self.logger.info(f"  Output: {output_path}")
        self.logger.info("")

        return output_path

    def _generate_masks(
        self,
        boundary_file: Path,
        grib_dir: Path
    ) -> MaskResult:
        """
        Generate all spatial masks in a single MaskBuilder call.

        Parameters
        ----------
        boundary_file : Path
            Path to extracted country boundary GeoJSON.
        grib_dir : Path
            Directory containing GRIB files (for grid extraction).

        Returns
        -------
        MaskResult
            Result containing one SingleMaskResult per configured mask.
        """
        self.logger.info("")

        builder = MaskBuilder(
            configs=self.config.masks,
            boundary_file=boundary_file,
            grib_dir=grib_dir,
            logger=self.logger
        )

        return builder.generate_mask(
            country_name=self.config.boundary.country_name
        )

    def _validate_adm_shapefiles(self) -> Dict[str, Optional[Path]]:
        """
        Validate ADM1/ADM2 shapefile availability.

        Returns
        -------
        dict
            Dictionary with 'adm1' and 'adm2' keys pointing to shapefile paths
            (or None if not enabled/available).
        """
        result = {"adm1": None, "adm2": None}

        # ADM1
        if self.config.adm_enrichment.enable_adm1:
            if self.config.boundary.shapefile_adm1:
                adm1_path = self._resolve_path(self.config.boundary.shapefile_adm1)
                if adm1_path.exists():
                    result["adm1"] = adm1_path
                    self.logger.info(f"ADM1 shapefile found: {adm1_path.name}")
                else:
                    self.logger.warning(
                        f"ADM1 enabled but shapefile not found: {adm1_path}"
                    )
            else:
                self.logger.warning("ADM1 enabled but no shapefile configured")

        # ADM2
        if self.config.adm_enrichment.enable_adm2:
            if self.config.boundary.shapefile_adm2:
                adm2_path = self._resolve_path(self.config.boundary.shapefile_adm2)
                if adm2_path.exists():
                    result["adm2"] = adm2_path
                    self.logger.info(f"ADM2 shapefile found: {adm2_path.name}")
                else:
                    self.logger.warning(
                        f"ADM2 enabled but shapefile not found: {adm2_path}"
                    )
            else:
                self.logger.warning("ADM2 enabled but no shapefile configured")

        return result

    def run(
        self,
        grib_dir: Path
    ) -> Dict[str, Any]:
        """
        Execute the complete geographic pipeline.

        Parameters
        ----------
        grib_dir : Path
            Directory containing GRIB files (for grid extraction).

        Returns
        -------
        dict
            Pipeline result dictionary containing:
            - boundary_file: Path to extracted boundary
            - mask_result: MaskResult object
            - adm_shapefiles: Dict of ADM1/ADM2 shapefile paths
        """
        t_total = time.perf_counter()

        self.logger.info("", force=True)
        self.logger.info("#" * 72, force=True)
        self.logger.info("# STEP 1: GEOGRAPHIC PROCESSING PIPELINE", force=True)
        self.logger.info("#" * 72, force=True)
        self.logger.info("", force=True)

        # ------------------------------------------------------------------
        # Stage 1: Extract country boundary
        # ------------------------------------------------------------------
        boundary_file = self._extract_country_boundary()

        # ------------------------------------------------------------------
        # Stage 2: Generate all masks in one MaskBuilder call
        # ------------------------------------------------------------------
        n = len(self.config.masks)
        modes = ", ".join(f"mode={mc.inclusion_mode}" for mc in self.config.masks)
        self.logger.info(f"  Generating {n} mask(s): {modes}", force=True)

        mask_result = self._generate_masks(
            boundary_file=boundary_file,
            grib_dir=grib_dir
        )
        mask_results = mask_result.masks   # list[SingleMaskResult]

        # ------------------------------------------------------------------
        # Stage 3: Validate ADM shapefiles for enrichment
        # ------------------------------------------------------------------
        self.logger.info("")
        self.logger.info("=" * 72, force=True)
        self.logger.info("VALIDATING ADM SHAPEFILES", force=True)
        self.logger.info("=" * 72, force=True)

        adm_shapefiles = self._validate_adm_shapefiles()

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        dt_total = time.perf_counter() - t_total

        self.logger.info("")
        self.logger.info("=" * 72, force=True)
        self.logger.info("GEOGRAPHIC PIPELINE COMPLETE", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info(f"  Total time: {dt_total:.2f}s")
        self.logger.info(f"  Boundary: {boundary_file.name}")
        for j, sr in enumerate(mask_results, 1):
            self.logger.info(f"  Mask {j}: {sr.mask_file.name} ({sr.row_count:,} cells)")
        if getattr(mask_result, "visualization_overview", None):
            self.logger.info(f"  Overview: {mask_result.visualization_overview.name}")
        for vd in getattr(mask_result, "visualization_details", []):
            self.logger.info(f"  Detail:   {vd.name}")
        if adm_shapefiles["adm1"]:
            self.logger.info(f"  ADM1: {adm_shapefiles['adm1'].name}")
        if adm_shapefiles["adm2"]:
            self.logger.info(f"  ADM2: {adm_shapefiles['adm2'].name}")
        self.logger.info("=" * 72, force=True)
        self.logger.info("", force=True)

        return {
            "boundary_file": boundary_file,
            "mask_result": mask_result,    # MaskResult (contains .masks list)
            "mask_results": mask_results,  # list[SingleMaskResult] — convenience
            "adm_shapefiles": adm_shapefiles,
        }