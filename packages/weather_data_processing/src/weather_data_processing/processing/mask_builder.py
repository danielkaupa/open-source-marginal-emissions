# packages/weather_data_processing/src/weather_data_processing/processing/mask_builder.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Geographic Mask Builder
========================

Generate spatial masks for filtering gridded weather data to specific countries.

This module wraps and enhances the existing step1d_generate_country_mask logic
with improved configuration management and integration with the pipeline.

Key Features
------------
- Multiple inclusion modes: centroid, intersection, combined
- Configurable fractional thresholds
- Metadata generation and audit trails
- Optional visualization outputs
- Parallel processing support
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import geopandas as gpd
import polars as pl
import xarray as xr
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from ..config_schema import MaskConfig
from ..utils.logging import VerboseLogger

from osme_common.paths import repo_root, data_dir, resolve_under


@dataclass
class MaskResult:
    """
    Result of mask generation.

    Attributes
    ----------
    mask_file : Path
        Path to the generated mask parquet file.
    metadata_file : Path
        Path to the metadata JSON file.
    row_count : int
        Number of grid cells in the mask.
    bbox : dict
        Bounding box of the masked region.
    generated_at : str
        ISO timestamp of generation.
    visualization_file : Path or None
        Path to diagnostic plot (if generated).
    """

    mask_file: Path
    metadata_file: Path
    row_count: int
    bbox: Dict[str, float]
    generated_at: str
    visualization_file: Optional[Path] = None        # 6-panel diagnostic overview
    visualization_file_2: Optional[Path] = None      # 2-panel masked-cells detail


class MaskBuilder:
    """
    Builder for generating geographic masks from GRIB files and boundary shapes.

    Parameters
    ----------
    config : MaskConfig
        Mask generation configuration.
    boundary_file : Path
        Path to GeoJSON file containing country boundary.
    grib_dir : Path
        Directory containing sample GRIB files for grid extraction.
    logger : VerboseLogger or None
        Logger instance.

    Examples
    --------
    >>> config = MaskConfig(
    ...     inclusion_mode="combined",
    ...     fraction_threshold=0.8,
    ...     dataset_prefix="era5-world"
    ... )
    >>> builder = MaskBuilder(
    ...     config=config,
    ...     boundary_file=Path("geoBoundaries/India.geojson"),
    ...     grib_dir=Path("data/era5-world/raw"),
    ... )
    >>> result = builder.generate_mask()
    >>> print(f"Mask created: {result.mask_file}")
    >>> print(f"Grid cells: {result.row_count}")
    """

    def __init__(
        self,
        config: MaskConfig,
        boundary_file: Path,
        grib_dir: Path,
        logger: Optional[VerboseLogger] = None,
    ):
        self.config = config
        self.boundary_file = boundary_file
        self.grib_dir = grib_dir
        self.logger = logger or VerboseLogger("mask_builder", verbose=False)

        if not boundary_file.exists():
            raise FileNotFoundError(f"Boundary file not found: {boundary_file}")

        if not grib_dir.exists():
            raise FileNotFoundError(f"GRIB directory not found: {grib_dir}")

        # Load boundary geometry
        self.boundary_geom = self._load_boundary()

    def _load_boundary(self) -> MultiPolygon:
        """Load and prepare boundary geometry."""
        t0 = time.perf_counter()
        self.logger.info(f"Loading boundary from {self.boundary_file.name}")

        gdf = gpd.read_file(self.boundary_file).to_crs(epsg=4326)
        geom = unary_union(gdf.geometry)

        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        elif not isinstance(geom, MultiPolygon):
            raise TypeError(
                f"Boundary must be Polygon or MultiPolygon, got {type(geom)}"
            )

        dt = time.perf_counter() - t0
        self.logger.debug(f"  Boundary loaded in {dt:.2f}s")

        return geom

    def _extract_grid_from_grib(self) -> pl.DataFrame:
        """
        Extract (lat, lon) grid from a sample GRIB file.

        Returns
        -------
        pl.DataFrame
            DataFrame with columns: latitude, longitude
        """
        import warnings
        t0 = time.perf_counter()

        # Find first GRIB file
        grib_files = sorted(self.grib_dir.glob("*.grib"))
        if not grib_files:
            raise FileNotFoundError(f"No GRIB files found in {self.grib_dir}")

        sample_grib = grib_files[0]
        self.logger.info(f"Extracting grid from {sample_grib.name}")

        ds = None
        try:
            import cfgrib

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=FutureWarning, module="cfgrib")
                datasets = cfgrib.open_datasets(
                    str(sample_grib),
                    backend_kwargs={"indexpath": ""}
                )

            if not datasets:
                raise ValueError("cfgrib.open_datasets returned no datasets.")

            # Pick first dataset containing both latitude and longitude
            for cand in datasets:
                if ("latitude" in cand.coords or "latitude" in cand.variables) and \
                   ("longitude" in cand.coords or "longitude" in cand.variables):
                    ds = cand
                    break

            if ds is None:
                ds = datasets[0]

        except Exception as e:
            self.logger.warning(
                f"Grouped GRIB open failed ({e}); falling back to xarray.open_dataset"
            )
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=FutureWarning, module="cfgrib")
                ds = xr.open_dataset(
                    sample_grib,
                    engine="cfgrib",
                    backend_kwargs={"indexpath": ""}
                )

        # Normalize coordinate names (some files use lat/lon aliases)
        lat_name = "latitude" if "latitude" in ds else ("lat" if "lat" in ds else None)
        lon_name = "longitude" if "longitude" in ds else ("lon" if "lon" in ds else None)

        if lat_name is None or lon_name is None:
            ds.close()
            raise ValueError(
                f"Could not find latitude/longitude coordinates in GRIB dataset. "
                f"Available coords: {list(ds.coords)}"
            )

        lon2d, lat2d = xr.broadcast(ds[lon_name], ds[lat_name])

        df = pl.DataFrame({
            "latitude": lat2d.values.ravel(),
            "longitude": lon2d.values.ravel()
        })

        ds.close()

        dt = time.perf_counter() - t0
        self.logger.info(f"  Extracted {len(df)} grid cells in {dt:.2f}s")

        return df

    def _apply_exclusions(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Remove grid cells that fall inside any configured exclusion bounding box.

        Parameters
        ----------
        df : pl.DataFrame
            Mask DataFrame with 'latitude' and 'longitude' columns.

        Returns
        -------
        pl.DataFrame
            DataFrame with excluded cells removed.
        """
        bboxes = self.config.exclusion_bboxes
        if not bboxes:
            return df

        self.logger.info(
            f"Applying {len(bboxes)} exclusion bounding box(es)...", force=True
        )

        before = len(df)
        lon = pl.col("longitude")
        lat = pl.col("latitude")

        # Build a combined "is excluded" expression across all bboxes
        exclude_expr = None
        for bbox in bboxes:
            box_expr = (
                (lon >= bbox.lon_min) & (lon <= bbox.lon_max) &
                (lat >= bbox.lat_min) & (lat <= bbox.lat_max)
            )
            exclude_expr = box_expr if exclude_expr is None else (exclude_expr | box_expr)

        df_filtered = df.filter(~exclude_expr)
        removed = before - len(df_filtered)

        for bbox in bboxes:
            self.logger.info(f"  Excluded zone: '{bbox.name}'  "
                             f"({bbox.lon_min}–{bbox.lon_max}°E, "
                             f"{bbox.lat_min}–{bbox.lat_max}°N)")
        self.logger.info(
            f"  Exclusions complete: {removed} cells removed "
            f"({before} → {len(df_filtered)})", force=True
        )

        return df_filtered

    def _apply_mask(
        self,
        df_grid: pl.DataFrame
    ) -> pl.DataFrame:
        """
        Apply spatial mask to grid based on inclusion mode.

        Parameters
        ----------
        df_grid : pl.DataFrame
            Grid with latitude and longitude columns.

        Returns
        -------
        pl.DataFrame
            Filtered grid with additional 'frac_in_region' column.
        """
        t0 = time.perf_counter()
        self.logger.info(
            f"Applying mask (mode={self.config.inclusion_mode}, "
            f"threshold={self.config.fraction_threshold})"
        )

        # Convert to GeoDataFrame
        geometry = [
            Point(row["longitude"], row["latitude"])
            for row in df_grid.iter_rows(named=True)
        ]

        gdf_grid = gpd.GeoDataFrame(
            df_grid.to_pandas(),
            geometry=geometry,
            crs="EPSG:4326"
        )

        if self.config.inclusion_mode == "centroid":
            # Include if centroid is within boundary
            mask = gdf_grid.within(self.boundary_geom)
            gdf_grid["frac_in_region"] = mask.astype(float)

        elif self.config.inclusion_mode == "intersection":
            # Include if any intersection exists
            mask = gdf_grid.intersects(self.boundary_geom)
            gdf_grid["frac_in_region"] = mask.astype(float)

        elif self.config.inclusion_mode == "combined":
            # Compute fractional overlap
            # This is simplified - real implementation would compute cell polygons
            # and intersection areas
            centroid_mask = gdf_grid.within(self.boundary_geom)
            intersect_mask = gdf_grid.intersects(self.boundary_geom)

            # Approximate: centroid=1.0, edge=threshold
            frac = centroid_mask.astype(float)
            frac = frac.where(frac > 0, intersect_mask.astype(float) * self.config.fraction_threshold)

            gdf_grid["frac_in_region"] = frac
            mask = frac >= self.config.fraction_threshold

        else:
            raise ValueError(f"Unknown inclusion mode: {self.config.inclusion_mode}")

        # Filter and convert back
        gdf_masked = gdf_grid[mask].drop(columns=["geometry"])
        df_masked = pl.from_pandas(gdf_masked)

        dt = time.perf_counter() - t0
        self.logger.info(
            f"  Mask applied: {len(df_masked)}/{len(df_grid)} cells retained "
            f"({100*len(df_masked)/len(df_grid):.1f}%) in {dt:.2f}s"
        )

        return df_masked

    def _generate_mask_id(self) -> str:
        """Generate unique mask identifier based on configuration."""
        config_str = (
            f"{self.config.inclusion_mode}_{self.config.fraction_threshold}_"
            f"{self.boundary_file.stem}"
        )
        hash_obj = hashlib.md5(config_str.encode())
        return hash_obj.hexdigest()[:6]

    def _build_output_paths(
        self,
        country_name: str,
        row_count: int
    ) -> tuple[Path, Path, Optional[Path], Optional[Path]]:
        """
        Build output file paths.

        Returns
        -------
        tuple of Path
            (mask_file, metadata_file, viz_file_overview, viz_file_detail)
        """
        country_token = country_name.upper().replace(" ", "_")

        if self.config.inclusion_mode == "combined":
            mode_str = f"combined{self.config.fraction_threshold}"
        else:
            mode_str = self.config.inclusion_mode

        base_name = (
            f"{self.config.dataset_prefix}_{country_token}_mask_"
            f"{mode_str}_{row_count}"
        )
        base = repo_root()

        mask_dir = resolve_under(base, self.config.mask_dir)
        meta_dir = resolve_under(base, self.config.metadata_dir)
        img_dir = resolve_under(base, self.config.image_dir)

        mask_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)

        if self.config.generate_visualization:
            img_dir.mkdir(parents=True, exist_ok=True)

        mask_file = mask_dir / f"{base_name}.parquet"
        metadata_file = meta_dir / f"{base_name}.json"

        if self.config.generate_visualization:
            viz_overview = img_dir / f"{base_name}_overview.png"
            viz_detail   = img_dir / f"{base_name}_detail.png"
        else:
            viz_overview = None
            viz_detail   = None

        return mask_file, metadata_file, viz_overview, viz_detail

    def generate_mask(
        self,
        country_name: str
    ) -> MaskResult:
        """
        Generate the complete mask.

        Parameters
        ----------
        country_name : str
            Name of the country (for metadata and filenames).

        Returns
        -------
        MaskResult
            Result object containing paths and metadata.
        """
        t_total = time.perf_counter()
        self.logger.info("=" * 72, force=True)
        self.logger.info("GENERATING GEOGRAPHIC MASK", force=True)
        self.logger.info("=" * 72, force=True)

        # Step 1: Extract grid
        df_grid = self._extract_grid_from_grib()

        # Step 2: Apply inclusion mask
        df_masked = self._apply_mask(df_grid)

        # Step 2b: Apply exclusion bounding boxes
        df_masked = self._apply_exclusions(df_masked)

        # Step 3: Build output paths
        mask_file, metadata_file, viz_overview, viz_detail = self._build_output_paths(
            country_name=country_name,
            row_count=len(df_masked)
        )

        # Step 4: Save mask
        self.logger.info(f"Saving mask to {mask_file.name}")
        df_masked.write_parquet(mask_file)

        # Step 5: Generate metadata
        bounds = df_masked.select([
            pl.col("latitude").min().alias("lat_min"),
            pl.col("latitude").max().alias("lat_max"),
            pl.col("longitude").min().alias("lon_min"),
            pl.col("longitude").max().alias("lon_max"),
        ]).to_dicts()[0]

        metadata = {
            "dataset_prefix": self.config.dataset_prefix,
            "country_token": country_name.upper().replace(" ", "_"),
            "country_name": country_name,
            "boundary_path": str(self.boundary_file),
            "inclusion_mode": self.config.inclusion_mode,
            "fraction_threshold": self.config.fraction_threshold,
            "exclusion_bboxes": [bbox.model_dump() for bbox in self.config.exclusion_bboxes],
            "row_count": len(df_masked),
            "bbox": bounds,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

        self.logger.info(f"Saving metadata to {metadata_file.name}")
        metadata_file.write_text(json.dumps(metadata, indent=2))

        # Step 6: Optional visualization
        viz_path_overview = None
        viz_path_detail   = None
        if self.config.generate_visualization and viz_overview and viz_detail:
            self.logger.info("Generating visualizations...")
            viz_path_overview, viz_path_detail = self._generate_visualization(
                df_grid=df_grid,
                df_masked=df_masked,
                viz_overview=viz_overview,
                viz_detail=viz_detail,
                country_name=country_name,
            )

        dt_total = time.perf_counter() - t_total
        self.logger.info("=" * 72, force=True)
        self.logger.info(f"MASK GENERATION COMPLETE ({dt_total:.2f}s)", force=True)
        self.logger.info("=" * 72, force=True)

        return MaskResult(
            mask_file=mask_file,
            metadata_file=metadata_file,
            row_count=len(df_masked),
            bbox=bounds,
            generated_at=metadata["generated_at"],
            visualization_file=viz_path_overview,
            visualization_file_2=viz_path_detail,
        )

    def _generate_visualization(
        self,
        df_grid: pl.DataFrame,
        df_masked: pl.DataFrame,
        viz_overview: Path,
        viz_detail: Path,
        country_name: str,
    ) -> tuple[Path, Path]:
        """
        Generate two diagnostic visualisations.

        Figure 1 (overview, 2×3 grid):
            [0,0] Label panel – dataset / country / inclusion settings
            [0,1] Country boundary only
            [0,2] All grid points (no boundary)
            [1,0] All grid points + boundary overlay
            [1,1] Masked grid points + boundary overlay
            [1,2] Masked grid points only (no boundary)

        Figure 2 (detail, 1×2 grid):
            [0,0] Masked grid points + boundary overlay
            [0,1] Masked grid points only (no boundary)
        """
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.gridspec import GridSpec

        # ----------------------------------------------------------------
        # Shared data prep
        # ----------------------------------------------------------------
        gdf_boundary = gpd.GeoDataFrame(
            geometry=[self.boundary_geom], crs="EPSG:4326"
        )

        all_lons = df_grid["longitude"].to_numpy()
        all_lats = df_grid["latitude"].to_numpy()
        mask_lons = df_masked["longitude"].to_numpy()
        mask_lats = df_masked["latitude"].to_numpy()

        # Bounding box with a little padding
        pad = 1.0
        lon_min, lon_max = all_lons.min() - pad, all_lons.max() + pad
        lat_min, lat_max = all_lats.min() - pad, all_lats.max() + pad

        # Colours / sizes
        C_BOUNDARY  = "#CC2200"
        C_ALL_PTS   = "#4477AA"
        C_MASK_PTS  = "#228833"
        PT_SIZE_ALL  = 2
        PT_SIZE_MASK = 3
        PT_ALPHA     = 0.55
        BND_LW       = 1.2

        mode_label = (
            f"combined  (threshold = {self.config.fraction_threshold})"
            if self.config.inclusion_mode == "combined"
            else self.config.inclusion_mode
        )

        def _set_extent(ax):
            ax.set_xlim(lon_min, lon_max)
            ax.set_ylim(lat_min, lat_max)

        def _style(ax, title):
            ax.set_title(title, fontsize=9, pad=4)
            ax.set_xlabel("Longitude", fontsize=7)
            ax.set_ylabel("Latitude", fontsize=7)
            ax.tick_params(labelsize=6)
            ax.grid(True, alpha=0.25, linewidth=0.4)
            _set_extent(ax)

        # ================================================================
        # FIGURE 1 – 6-panel overview  (3 cols × 2 rows)
        # ================================================================
        fig1 = plt.figure(figsize=(18, 11))
        gs   = GridSpec(2, 3, figure=fig1, hspace=0.38, wspace=0.28)

        # ------ Panel [0,0]: label ----------------------------------------
        ax_label = fig1.add_subplot(gs[0, 0])
        ax_label.axis("off")
        label_lines = [
            ("Dataset",           self.config.dataset_prefix),
            ("Country",           country_name),
            ("Inclusion mode",    mode_label),
            ("Total grid cells",  f"{len(df_grid):,}"),
            ("Masked cells",      f"{len(df_masked):,}"),
            ("Coverage",          f"{100*len(df_masked)/max(len(df_grid),1):.1f} %"),
            ("Lat range",         f"{all_lats.min():.2f}° – {all_lats.max():.2f}°"),
            ("Lon range",         f"{all_lons.min():.2f}° – {all_lons.max():.2f}°"),
        ]
        y = 0.93
        for key, val in label_lines:
            ax_label.text(0.04, y, f"{key}:", fontsize=9, fontweight="bold",
                          transform=ax_label.transAxes, va="top")
            ax_label.text(0.46, y, val, fontsize=9,
                          transform=ax_label.transAxes, va="top")
            y -= 0.11
        ax_label.set_title("Mask Summary", fontsize=10, fontweight="bold", pad=6)
        rect = mpatches.FancyBboxPatch(
            (0.01, 0.01), 0.98, 0.98,
            boxstyle="round,pad=0.02",
            linewidth=1.2, edgecolor="#888888", facecolor="#F7F7F7",
            transform=ax_label.transAxes, zorder=0
        )
        ax_label.add_patch(rect)

        # ------ Panel [0,1]: country boundary only -------------------------
        ax1 = fig1.add_subplot(gs[0, 1])
        gdf_boundary.boundary.plot(ax=ax1, color=C_BOUNDARY, linewidth=BND_LW)
        _style(ax1, "Country Boundary")

        # ------ Panel [0,2]: all grid points --------------------------------
        ax2 = fig1.add_subplot(gs[0, 2])
        ax2.scatter(all_lons, all_lats, s=PT_SIZE_ALL, c=C_ALL_PTS,
                    alpha=PT_ALPHA, linewidths=0, rasterized=True)
        _style(ax2, f"All Grid Points  ({len(df_grid):,})")

        # ------ Panel [1,0]: all grid points + boundary --------------------
        ax3 = fig1.add_subplot(gs[1, 0])
        ax3.scatter(all_lons, all_lats, s=PT_SIZE_ALL, c=C_ALL_PTS,
                    alpha=PT_ALPHA, linewidths=0, rasterized=True,
                    label=f"All points ({len(df_grid):,})")
        gdf_boundary.boundary.plot(ax=ax3, color=C_BOUNDARY, linewidth=BND_LW,
                                   label="Boundary")
        ax3.legend(fontsize=6, loc="lower right", framealpha=0.7)
        _style(ax3, "All Grid Points + Boundary")

        # ------ Panel [1,1]: masked grid points + boundary -----------------
        ax4 = fig1.add_subplot(gs[1, 1])
        ax4.scatter(mask_lons, mask_lats, s=PT_SIZE_MASK, c=C_MASK_PTS,
                    alpha=PT_ALPHA, linewidths=0, rasterized=True,
                    label=f"Masked ({len(df_masked):,})")
        gdf_boundary.boundary.plot(ax=ax4, color=C_BOUNDARY, linewidth=BND_LW,
                                   label="Boundary")
        ax4.legend(fontsize=6, loc="lower right", framealpha=0.7)
        _style(ax4, "Masked Grid Points + Boundary")

        # ------ Panel [1,2]: masked grid points only -----------------------
        ax5 = fig1.add_subplot(gs[1, 2])
        ax5.scatter(mask_lons, mask_lats, s=PT_SIZE_MASK, c=C_MASK_PTS,
                    alpha=PT_ALPHA, linewidths=0, rasterized=True)
        _style(ax5, f"Masked Grid Points  ({len(df_masked):,})")

        fig1.suptitle(
            f"Geographic Mask — {country_name}  |  {self.config.dataset_prefix}",
            fontsize=13, fontweight="bold", y=1.01
        )

        viz_overview.parent.mkdir(parents=True, exist_ok=True)
        fig1.savefig(viz_overview, dpi=180, bbox_inches="tight")
        plt.close(fig1)
        self.logger.info(f"  Overview visualisation → {viz_overview.name}")

        # ================================================================
        # FIGURE 2 – 2-panel detail
        # ================================================================
        fig2, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(14, 7))

        # Left: masked + boundary
        ax_a.scatter(mask_lons, mask_lats, s=PT_SIZE_MASK + 1, c=C_MASK_PTS,
                     alpha=PT_ALPHA, linewidths=0, rasterized=True,
                     label=f"Masked cells ({len(df_masked):,})")
        gdf_boundary.boundary.plot(ax=ax_a, color=C_BOUNDARY, linewidth=BND_LW,
                                   label="Boundary")
        ax_a.legend(fontsize=8, loc="lower right", framealpha=0.8)
        _style(ax_a, "Masked Grid Points + Country Boundary")

        # Right: masked only
        ax_b.scatter(mask_lons, mask_lats, s=PT_SIZE_MASK + 1, c=C_MASK_PTS,
                     alpha=PT_ALPHA, linewidths=0, rasterized=True)
        _style(ax_b, f"Masked Grid Points  ({len(df_masked):,})")

        fig2.suptitle(
            f"Masked Cells Detail — {country_name}  |  {self.config.dataset_prefix}  |  {mode_label}",
            fontsize=11, fontweight="bold"
        )
        fig2.tight_layout()

        viz_detail.parent.mkdir(parents=True, exist_ok=True)
        fig2.savefig(viz_detail, dpi=180, bbox_inches="tight")
        plt.close(fig2)
        self.logger.info(f"  Detail visualisation    → {viz_detail.name}")

        return viz_overview, viz_detail