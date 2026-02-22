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

from ..config_schema import MaskConfig, GeographicConfig
from ..utils.logging import VerboseLogger

from osme_common.paths import repo_root, data_dir, resolve_under


@dataclass
class SingleMaskResult:
    """Result for one inclusion-mode mask."""
    mask_file: Path
    metadata_file: Path
    mask_config: MaskConfig
    df_masked: Any            # pl.DataFrame kept in memory for visualisation
    row_count: int
    bbox: Dict[str, float]
    generated_at: str


@dataclass
class MaskResult:
    """
    Aggregated result of mask generation for all configured inclusion modes.

    Attributes
    ----------
    masks : list of SingleMaskResult
        One entry per MaskConfig in geographic.masks.
    visualization_overview : Path or None
        Combined overview figure (N×3 grid, one row per mask).
    visualization_details : list of Path
        Per-mask detail figures (one per MaskConfig).
    """
    masks: List[Any]                             # List[SingleMaskResult]
    visualization_overview: Optional[Path] = None
    visualization_details: List[Path] = None

    # Convenience: expose first mask's file/count for callers that expect
    # the old single-mask interface
    @property
    def mask_file(self) -> Optional[Path]:
        return self.masks[0].mask_file if self.masks else None

    @property
    def row_count(self) -> int:
        return self.masks[0].row_count if self.masks else 0

    @property
    def visualization_file(self) -> Optional[Path]:
        return self.visualization_overview

    def __post_init__(self):
        if self.visualization_details is None:
            self.visualization_details = []


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
        configs: List[MaskConfig],
        boundary_file: Path,
        grib_dir: Path,
        logger: Optional[VerboseLogger] = None,
    ):
        """
        Parameters
        ----------
        configs : list of MaskConfig
            One MaskConfig per inclusion mode to run.
        boundary_file : Path
            Path to GeoJSON file containing country boundary.
        grib_dir : Path
            Directory containing sample GRIB files for grid extraction.
        logger : VerboseLogger, optional
        """
        if not configs:
            raise ValueError("At least one MaskConfig must be provided")
        self.configs = configs
        # Convenience: first config drives shared settings (dirs, dataset_prefix)
        self.config = configs[0]
        self.boundary_file = boundary_file
        self.grib_dir = grib_dir
        self.logger = logger or VerboseLogger("mask_builder", verbose=False)

        if not boundary_file.exists():
            raise FileNotFoundError(f"Boundary file not found: {boundary_file}")

        if not grib_dir.exists():
            raise FileNotFoundError(f"GRIB directory not found: {grib_dir}")

        # Load boundary geometry once (shared across all configs)
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

    # Equal-area CRS for fractional area computation
    _EA_CRS = "EPSG:6933"

    def _apply_mask(
        self,
        df_grid: pl.DataFrame
    ) -> pl.DataFrame:
        """
        Apply spatial mask to grid based on inclusion mode.

        Modes
        -----
        centroid
            Keep a cell if its centre point lies inside the boundary.
            Fast. Conservative at borders — a cell that is 99% inside
            but whose centre is just outside will be dropped.

        intersection
            Keep a cell if any part of it touches the boundary.
            Most inclusive — picks up all border cells regardless of
            how little of the cell is actually inside the country.

        combined
            Compute the true fractional overlap between each grid cell
            polygon and the boundary (in an equal-area projection), then
            keep cells whose overlap >= fraction_threshold. This is the
            most accurate mode and the only one where fraction_threshold
            has a real effect.

        Parameters
        ----------
        df_grid : pl.DataFrame
            Grid with latitude and longitude columns.

        Returns
        -------
        pl.DataFrame
            Filtered grid with an added 'frac_in_region' column
            (always 0.0 or 1.0 for centroid/intersection; a true
            fraction for combined).
        """
        import shapely
        import numpy as np

        t0 = time.perf_counter()
        mode = self.config.inclusion_mode
        threshold = self.config.fraction_threshold
        self.logger.info(
            f"Applying mask (mode={mode}"
            + (f", threshold={threshold}" if mode == "combined" else "")
            + ")"
        )

        lats = df_grid["latitude"].to_numpy()
        lons = df_grid["longitude"].to_numpy()

        # --- Centroid points (used by all modes) --------------------------
        centroids = shapely.points(lons, lats)

        if mode == "centroid":
            inside = shapely.within(centroids, self.boundary_geom)
            frac_vals = inside.astype(float)
            keep = inside

        elif mode == "intersection":
            # Infer cell half-size from grid spacing
            dlat = float(np.abs(np.diff(np.unique(lats))).min()) / 2.0
            dlon = float(np.abs(np.diff(np.unique(lons))).min()) / 2.0
            cell_polys = shapely.box(
                lons - dlon, lats - dlat,
                lons + dlon, lats + dlat,
            )
            intersects = shapely.intersects(cell_polys, self.boundary_geom)
            frac_vals = intersects.astype(float)
            keep = intersects

        elif mode == "combined":
            # True fractional overlap in equal-area projection
            dlat = float(np.abs(np.diff(np.unique(lats))).min()) / 2.0
            dlon = float(np.abs(np.diff(np.unique(lons))).min()) / 2.0
            cell_polys = shapely.box(
                lons - dlon, lats - dlat,
                lons + dlon, lats + dlat,
            )

            # First pass: restrict to cells that intersect at all (fast cull)
            intersects = shapely.intersects(cell_polys, self.boundary_geom)
            candidate_polys = cell_polys[intersects]

            # Project to equal-area CRS for accurate area calculations
            gdf_cells = gpd.GeoSeries(candidate_polys, crs="EPSG:4326").to_crs(self._EA_CRS)
            region_ea = gpd.GeoSeries([self.boundary_geom], crs="EPSG:4326").to_crs(self._EA_CRS).iloc[0]

            cells_ea = np.asarray(gdf_cells)    # numpy array of shapely geoms
            cell_areas = shapely.area(cells_ea)
            inter_areas = shapely.area(shapely.intersection(cells_ea, region_ea))

            frac_candidate = np.where(cell_areas > 0, inter_areas / cell_areas, 0.0)
            frac_candidate = frac_candidate.clip(0.0, 1.0)

            # Map fractions back to full grid
            frac_vals = np.zeros(len(lats), dtype=float)
            frac_vals[intersects] = frac_candidate
            keep = frac_vals >= threshold

        else:
            raise ValueError(f"Unknown inclusion mode: {mode}")

        # Build output dataframe
        import numpy as np
        df_out = (
            df_grid
            .with_columns(pl.Series("frac_in_region", frac_vals))
            .with_columns(pl.Series("_keep", keep.astype(bool)))
            .filter(pl.col("_keep"))
            .drop("_keep")
        )

        dt = time.perf_counter() - t0
        self.logger.info(
            f"  Mask applied: {len(df_out)}/{len(df_grid)} cells retained "
            f"({100*len(df_out)/max(len(df_grid),1):.1f}%) in {dt:.2f}s"
        )

        return df_out

    def _generate_mask_id(self, config: Optional[MaskConfig] = None) -> str:
        """
        Generate a short config-based identifier for a mask.

        The hash is derived solely from the mask *settings* (inclusion mode,
        fraction threshold, boundary file stem) — not from the data — so the
        same settings always produce the same token regardless of how many cells
        happen to be inside the boundary.

        Parameters
        ----------
        config : MaskConfig or None
            Config to hash.  Defaults to ``self.config`` if not provided.

        Returns
        -------
        str
            6-character lowercase hex digest.
        """
        cfg = config if config is not None else self.config
        config_str = (
            f"{cfg.inclusion_mode}_{cfg.fraction_threshold}_"
            f"{self.boundary_file.stem}"
        )
        hash_obj = hashlib.md5(config_str.encode())
        return hash_obj.hexdigest()[:8]

    def _build_output_paths(
        self,
        config: MaskConfig,
        country_name: str,
        config_hash: str,
    ) -> tuple[Path, Path, Optional[Path]]:
        """
        Build output paths for a single MaskConfig.

        The ``config_hash`` is a short hex digest derived from the mask settings
        (inclusion mode, threshold, boundary file).  It disambiguates mask files
        generated with different settings for the same country, and is carried
        forward into masked-parquet filenames in Step 2 so every downstream file
        can be traced back to the mask that produced it.

        Returns (mask_file, metadata_file, viz_detail_file)
        """
        country_token = country_name.upper().replace(" ", "_")

        if config.inclusion_mode == "combined":
            mode_str = f"combined{config.fraction_threshold}"
        else:
            mode_str = config.inclusion_mode

        base_name = (
            f"{config.dataset_prefix}_{country_token}_mask_{mode_str}_{config_hash}"
        )
        base = data_dir()

        mask_dir  = resolve_under(base, config.mask_dir)
        meta_dir  = resolve_under(base, config.metadata_dir)
        img_dir   = resolve_under(base, config.image_dir)

        mask_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)
        if config.generate_visualization:
            img_dir.mkdir(parents=True, exist_ok=True)

        mask_file     = mask_dir / f"{base_name}.parquet"
        metadata_file = meta_dir / f"{base_name}.json"
        viz_detail    = (img_dir / f"{base_name}_detail.png") if config.generate_visualization else None

        return mask_file, metadata_file, viz_detail

    def _build_overview_path(self, country_name: str) -> Path:
        """Build path for the shared overview figure."""
        country_token = country_name.upper().replace(" ", "_")
        img_dir = resolve_under(data_dir(), self.config.image_dir)
        img_dir.mkdir(parents=True, exist_ok=True)
        return img_dir / f"{self.config.dataset_prefix}_{country_token}_mask_overview.png"

    def generate_mask(
        self,
        country_name: str
    ) -> MaskResult:
        """
        Generate masks for all configured inclusion modes.

        Parameters
        ----------
        country_name : str
            Name of the country (for metadata and filenames).

        Returns
        -------
        MaskResult
            Aggregated result containing one SingleMaskResult per config,
            plus paths to the overview and per-mask detail visualisations.
        """
        t_total = time.perf_counter()
        self.logger.info("=" * 72, force=True)
        self.logger.info(
            f"GENERATING GEOGRAPHIC MASKS ({len(self.configs)} config(s))",
            force=True
        )
        self.logger.info("=" * 72, force=True)

        # Step 1: Extract grid once (shared across all configs)
        df_grid = self._extract_grid_from_grib()

        single_results: List[SingleMaskResult] = []

        for i, cfg in enumerate(self.configs, 1):
            self.logger.info(
                f"  [{i}/{len(self.configs)}] mode={cfg.inclusion_mode}  "
                f"threshold={cfg.fraction_threshold}",
                force=True
            )

            # Temporarily swap active config for _apply_mask / _apply_exclusions
            self.config = cfg

            df_masked = self._apply_mask(df_grid)
            df_masked = self._apply_exclusions(df_masked)

            # Config-based hash — same settings → same token, always.
            config_hash = self._generate_mask_id(cfg)

            mask_file, metadata_file, viz_detail_path = self._build_output_paths(
                config=cfg,
                country_name=country_name,
                config_hash=config_hash,
            )

            # Save mask parquet
            self.logger.info(f"    Saving mask → {mask_file.name}")
            df_masked.write_parquet(mask_file)

            # Save metadata
            bounds = df_masked.select([
                pl.col("latitude").min().alias("lat_min"),
                pl.col("latitude").max().alias("lat_max"),
                pl.col("longitude").min().alias("lon_min"),
                pl.col("longitude").max().alias("lon_max"),
            ]).to_dicts()[0]

            metadata = {
                "dataset_prefix": cfg.dataset_prefix,
                "country_token": country_name.upper().replace(" ", "_"),
                "country_name": country_name,
                "boundary_path": str(self.boundary_file),
                "inclusion_mode": cfg.inclusion_mode,
                "fraction_threshold": cfg.fraction_threshold,
                "exclusion_bboxes": [bbox.model_dump() for bbox in cfg.exclusion_bboxes],
                "mask_uid": config_hash,
                "row_count": len(df_masked),
                "bbox": bounds,
                "generated_at": datetime.utcnow().isoformat() + "Z",
            }
            metadata_file.write_text(json.dumps(metadata, indent=2))
            self.logger.info(f"    Saving metadata → {metadata_file.name}")

            single_results.append(SingleMaskResult(
                mask_file=mask_file,
                metadata_file=metadata_file,
                mask_config=cfg,
                df_masked=df_masked,
                row_count=len(df_masked),
                bbox=bounds,
                generated_at=metadata["generated_at"],
            ))

        # Restore first config as the "primary"
        self.config = self.configs[0]

        # Step: Visualisations
        viz_overview_path = None
        viz_detail_paths: List[Path] = []

        if any(cfg.generate_visualization for cfg in self.configs):
            self.logger.info("Generating visualisations...", force=True)
            viz_overview_path, viz_detail_paths = self._generate_visualization(
                df_grid=df_grid,
                single_results=single_results,
                country_name=country_name,
            )

        dt_total = time.perf_counter() - t_total
        self.logger.info("=" * 72, force=True)
        self.logger.info(f"MASK GENERATION COMPLETE ({dt_total:.2f}s)", force=True)
        self.logger.info("=" * 72, force=True)

        return MaskResult(
            masks=single_results,
            visualization_overview=viz_overview_path,
            visualization_details=viz_detail_paths,
        )

    def _generate_visualization(
        self,
        df_grid: pl.DataFrame,
        single_results: List[SingleMaskResult],
        country_name: str,
    ) -> tuple[Optional[Path], List[Path]]:
        """
        Generate visualisations for all masks.

        Overview figure (N rows × 3 cols, where N = number of masks):
            Row 0 (shared grid context):
                [0,0] Country boundary only
                [0,1] All grid points
                [0,2] All grid points + boundary
            Rows 1..N (one per mask):
                [r,0] Text summary for this mask
                [r,1] Masked grid points only
                [r,2] Masked grid points + boundary

        Detail figures (one per mask):
            Left:  Masked grid points + boundary
            Right: Masked grid points only
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

        pad = 1.0
        lon_min = all_lons.min() - pad
        lon_max = all_lons.max() + pad
        lat_min = all_lats.min() - pad
        lat_max = all_lats.max() + pad

        C_BOUNDARY  = "#CC2200"
        C_ALL_PTS   = "#4477AA"
        BND_LW      = 1.2
        PT_SIZE_ALL = 2
        PT_ALPHA    = 0.55

        # One distinct green per mask (cycles if >5)
        MASK_COLOURS = ["#228833", "#AA3377", "#CCBB44", "#66CCEE", "#EE6677"]

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

        def _mode_label(cfg: MaskConfig) -> str:
            if cfg.inclusion_mode == "combined":
                return f"combined  (threshold = {cfg.fraction_threshold})"
            return cfg.inclusion_mode

        # ================================================================
        # OVERVIEW FIGURE
        # (1 header row + 1 row per mask) × 3 cols
        # ================================================================
        n_masks  = len(single_results)
        n_rows   = 1 + n_masks   # row 0 = shared context; rows 1..n = per-mask
        fig_h    = 5 + n_masks * 4.5

        fig1 = plt.figure(figsize=(18, fig_h))
        gs   = GridSpec(n_rows, 3, figure=fig1, hspace=0.40, wspace=0.28)

        # ------ Row 0: shared grid context --------------------------------
        # [0,0] Country boundary
        ax_bnd = fig1.add_subplot(gs[0, 0])
        gdf_boundary.boundary.plot(ax=ax_bnd, color=C_BOUNDARY, linewidth=BND_LW)
        _style(ax_bnd, "Country Boundary")

        # [0,1] All grid points
        ax_all = fig1.add_subplot(gs[0, 1])
        ax_all.scatter(all_lons, all_lats, s=PT_SIZE_ALL, c=C_ALL_PTS,
                       alpha=PT_ALPHA, linewidths=0, rasterized=True)
        _style(ax_all, f"All Grid Points  ({len(df_grid):,})")

        # [0,2] All grid points + boundary
        ax_all_bnd = fig1.add_subplot(gs[0, 2])
        ax_all_bnd.scatter(all_lons, all_lats, s=PT_SIZE_ALL, c=C_ALL_PTS,
                           alpha=PT_ALPHA, linewidths=0, rasterized=True,
                           label=f"All points ({len(df_grid):,})")
        gdf_boundary.boundary.plot(ax=ax_all_bnd, color=C_BOUNDARY, linewidth=BND_LW,
                                   label="Boundary")
        ax_all_bnd.legend(fontsize=6, loc="lower right", framealpha=0.7)
        _style(ax_all_bnd, "All Grid Points + Boundary")

        # ------ Rows 1..N: per-mask ----------------------------------------
        for r, sr in enumerate(single_results, start=1):
            cfg        = sr.mask_config
            mask_lons  = sr.df_masked["longitude"].to_numpy()
            mask_lats  = sr.df_masked["latitude"].to_numpy()
            c_mask     = MASK_COLOURS[(r - 1) % len(MASK_COLOURS)]
            ml         = _mode_label(cfg)
            coverage   = 100 * sr.row_count / max(len(df_grid), 1)

            # [r,0] Text summary
            ax_txt = fig1.add_subplot(gs[r, 0])
            ax_txt.axis("off")
            label_lines = [
                ("Dataset",        cfg.dataset_prefix),
                ("Country",        country_name),
                ("Mode",           ml),
                ("Total cells",    f"{len(df_grid):,}"),
                ("Masked cells",   f"{sr.row_count:,}"),
                ("Coverage",       f"{coverage:.1f} %"),
                ("Exclusions",     str(len(cfg.exclusion_bboxes))),
            ]
            y = 0.95
            for key, val in label_lines:
                ax_txt.text(0.04, y, f"{key}:", fontsize=9, fontweight="bold",
                            transform=ax_txt.transAxes, va="top")
                ax_txt.text(0.46, y, val, fontsize=9,
                            transform=ax_txt.transAxes, va="top")
                y -= 0.13
            ax_txt.set_title(f"Mask {r} Summary", fontsize=10, fontweight="bold", pad=6)
            rect = mpatches.FancyBboxPatch(
                (0.01, 0.01), 0.98, 0.98,
                boxstyle="round,pad=0.02",
                linewidth=1.2, edgecolor="#888888", facecolor="#F7F7F7",
                transform=ax_txt.transAxes, zorder=0
            )
            ax_txt.add_patch(rect)

            # [r,1] Masked points only
            ax_msk = fig1.add_subplot(gs[r, 1])
            ax_msk.scatter(mask_lons, mask_lats, s=3, c=c_mask,
                           alpha=PT_ALPHA, linewidths=0, rasterized=True)
            _style(ax_msk, f"Masked  ({sr.row_count:,})  |  {ml}")

            # [r,2] Masked points + boundary
            ax_msk_bnd = fig1.add_subplot(gs[r, 2])
            ax_msk_bnd.scatter(mask_lons, mask_lats, s=3, c=c_mask,
                               alpha=PT_ALPHA, linewidths=0, rasterized=True,
                               label=f"Masked ({sr.row_count:,})")
            gdf_boundary.boundary.plot(ax=ax_msk_bnd, color=C_BOUNDARY,
                                       linewidth=BND_LW, label="Boundary")
            ax_msk_bnd.legend(fontsize=6, loc="lower right", framealpha=0.7)
            _style(ax_msk_bnd, f"Masked + Boundary  |  {ml}")

        fig1.suptitle(
            f"Geographic Masks — {country_name}  |  {self.config.dataset_prefix}",
            fontsize=13, fontweight="bold", y=1.005
        )

        overview_path = self._build_overview_path(country_name)
        overview_path.parent.mkdir(parents=True, exist_ok=True)
        fig1.savefig(overview_path, dpi=180, bbox_inches="tight")
        plt.close(fig1)
        self.logger.info(f"  Overview visualisation → {overview_path.name}")

        # ================================================================
        # DETAIL FIGURES — one per mask
        # ================================================================
        detail_paths: List[Path] = []

        for r, sr in enumerate(single_results):
            cfg       = sr.mask_config
            if not cfg.generate_visualization:
                continue

            mask_lons = sr.df_masked["longitude"].to_numpy()
            mask_lats = sr.df_masked["latitude"].to_numpy()
            c_mask    = MASK_COLOURS[r % len(MASK_COLOURS)]
            ml        = _mode_label(cfg)

            _, _, viz_detail_path = self._build_output_paths(
                config=cfg,
                country_name=country_name,
                config_hash=self._generate_mask_id(cfg),
            )
            if viz_detail_path is None:
                continue

            fig2, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(14, 7))

            # Left: masked + boundary
            ax_a.scatter(mask_lons, mask_lats, s=4, c=c_mask,
                         alpha=PT_ALPHA, linewidths=0, rasterized=True,
                         label=f"Masked cells ({sr.row_count:,})")
            gdf_boundary.boundary.plot(ax=ax_a, color=C_BOUNDARY,
                                       linewidth=BND_LW, label="Boundary")
            ax_a.legend(fontsize=8, loc="lower right", framealpha=0.8)
            _style(ax_a, "Masked Grid Points + Country Boundary")

            # Right: masked only
            ax_b.scatter(mask_lons, mask_lats, s=4, c=c_mask,
                         alpha=PT_ALPHA, linewidths=0, rasterized=True)
            _style(ax_b, f"Masked Grid Points  ({sr.row_count:,})")

            fig2.suptitle(
                f"Mask Detail — {country_name}  |  {cfg.dataset_prefix}  |  {ml}",
                fontsize=11, fontweight="bold"
            )
            fig2.tight_layout()

            viz_detail_path.parent.mkdir(parents=True, exist_ok=True)
            fig2.savefig(viz_detail_path, dpi=180, bbox_inches="tight")
            plt.close(fig2)
            self.logger.info(f"  Detail visualisation    → {viz_detail_path.name}")
            detail_paths.append(viz_detail_path)

        return overview_path, detail_paths