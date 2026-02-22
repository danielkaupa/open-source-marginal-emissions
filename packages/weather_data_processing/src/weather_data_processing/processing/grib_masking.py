# packages/weather_data_processing/src/weather_data_processing/processing/grib_masking.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
GRIB Masking Processor
=======================

Apply spatial masks to GRIB files and convert to Parquet with optional
ADM boundary enrichment.

This module wraps the core logic from step2a_mask_and_process_grib.py with
improved integration, configuration management, and ADM enrichment.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List

import polars as pl
import xarray as xr

from ..io.grib_io import (
    load_grib_dataset,
    grib_to_dataframe,
    extract_variable_metadata,
    estimate_grib_size_mb,
)
from ..processing.admin_enrichment import ADMEnricher
from ..config_schema import ADMEnrichmentConfig
from ..utils.logging import VerboseLogger


@dataclass
class MaskingResult:
    """
    Result of GRIB masking operation.

    Attributes
    ----------
    output_file : Path
        Path to output parquet file.
    input_file : Path
        Path to input GRIB file.
    rows_before_mask : int
        Number of rows before spatial filtering.
    rows_after_mask : int
        Number of rows after spatial filtering.
    rows_after_adm : int
        Number of rows after ADM enrichment (may differ if spatial join fails for some points).
    variables : list of str
        Variables extracted.
    processing_time_s : float
        Total processing time in seconds.
    file_size_mb : float
        Output file size in MB.
    """

    output_file: Path
    input_file: Path
    rows_before_mask: int
    rows_after_mask: int
    rows_after_adm: int
    variables: List[str]
    processing_time_s: float
    file_size_mb: float


class GRIBMaskingProcessor:
    """
    Process GRIB files by applying spatial mask and optionally enriching with ADM boundaries.

    Parameters
    ----------
    mask_file : Path
        Path to spatial mask parquet file (with lat, lon, frac_in_region).
    mask_metadata : dict
        Mask metadata (from JSON file).
    adm_enricher : ADMEnricher or None
        Optional ADM enricher for adding administrative boundaries.
    logger : VerboseLogger or None
        Logger instance.

    Examples
    --------
    >>> processor = GRIBMaskingProcessor(
    ...     mask_file=Path("masks/era5-world_INDIA_mask.parquet"),
    ...     mask_metadata={"dataset_prefix": "era5-world", ...},
    ...     adm_enricher=enricher
    ... )
    >>> result = processor.process_file(
    ...     grib_file=Path("data/raw/era5_2018-01.grib"),
    ...     output_file=Path("data/interim/era5_2018-01.parquet")
    ... )
    """

    def __init__(
        self,
        mask_file: Path,
        mask_metadata: Dict[str, Any],
        adm_enricher: Optional[ADMEnricher] = None,
        logger: Optional[VerboseLogger] = None,
    ):
        self.mask_file = mask_file
        self.mask_metadata = mask_metadata
        self.adm_enricher = adm_enricher
        self.logger = logger or VerboseLogger("grib_masking", verbose=False)

        # Load mask
        t0 = time.perf_counter()
        self.logger.debug(f"Loading spatial mask from {mask_file.name}")
        self.mask = pl.read_parquet(mask_file)

        dt = time.perf_counter() - t0
        self.logger.debug(
            f"  Mask loaded: {len(self.mask):,} grid cells in {dt:.2f}s"
        )

    def process_file(
        self,
        grib_file: Path,
        output_file: Path,
        variables: Optional[List[str]] = None
    ) -> MaskingResult:
        """
        Process a single GRIB file: apply mask, enrich with ADM, save to parquet.

        Parameters
        ----------
        grib_file : Path
            Input GRIB file.
        output_file : Path
            Output parquet file path.
        variables : list of str, optional
            If provided, only extract these variables (by shortName).
            If None, extract all variables.

        Returns
        -------
        MaskingResult
            Processing result with statistics.
        """
        t_start = time.perf_counter()

        self.logger.info(f"Processing {grib_file.name}", force=True)
        self.logger.debug(f"  Size: {estimate_grib_size_mb(grib_file):.1f} MB")

        # ------------------------------------------------------------------
        # Step 1: Load GRIB dataset
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        self.logger.debug("  Loading GRIB dataset...")

        ds = load_grib_dataset(grib_file, variables=variables)
        var_names = list(ds.data_vars)

        dt = time.perf_counter() - t0
        self.logger.debug(f"    Loaded in {dt:.2f}s: {var_names}")

        # ------------------------------------------------------------------
        # Step 2: Convert to long-form DataFrame all at once
        #
        # We use the reference script approach: ds.to_dataframe().reset_index()
        # This avoids per-timestep .sel() loops, which cause timestamp
        # corruption when numpy datetime64 values from cfgrib's internal
        # representation are passed back as selection keys.
        # ------------------------------------------------------------------
        t0 = time.perf_counter()

        # ds.to_dataframe() on a (time, latitude, longitude) dataset produces
        # a long-form DataFrame with a MultiIndex of (time, latitude, longitude).
        # reset_index() promotes those to plain columns.
        # This is identical to the reference script's approach and correctly
        # inherits the pd.to_datetime() normalisation applied in
        # _open_single_variable() — no post-hoc time fixup needed.
        import pandas as pd
        df_pd = ds.to_dataframe().reset_index()
        n_timestamps = ds["time"].shape[0] if "time" in ds.dims else 1
        ds.close()

        # Drop cfgrib auxiliary coordinate columns that aren't useful downstream
        # (step, surface level identifiers, forecast number, etc.)
        drop_cols = [c for c in (
            "step", "number", "surface", "depthBelowLandLayer",
            "entireAtmosphere", "level", "valid_time",
        ) if c in df_pd.columns]
        if drop_cols:
            df_pd = df_pd.drop(columns=drop_cols)

        # Ensure time dtype is pandas Timestamp (not numpy datetime64 from cfgrib)
        if "time" in df_pd.columns:
            df_pd["time"] = pd.to_datetime(df_pd["time"])

        df = pl.from_pandas(df_pd)

        # Apply spatial mask — inner join on (latitude, longitude) exactly as
        # the reference script does: lf.join(mask_lf, on=[lat, lon], how="inner")
        df = df.join(
            self.mask.select(["latitude", "longitude"]),
            on=["latitude", "longitude"],
            how="inner"
        )
        if "frac_in_region" in self.mask.columns:
            df = df.join(
                self.mask.select(["latitude", "longitude", "frac_in_region"]),
                on=["latitude", "longitude"],
                how="left"
            )

        dt = time.perf_counter() - t0
        rows_before = len(df)
        self.logger.debug(
            f"    Converted + masked in {dt:.2f}s: {rows_before:,} rows"
        )

        # ------------------------------------------------------------------
        # Step 3: ADM Enrichment (if configured)
        # ------------------------------------------------------------------
        rows_after_adm = rows_before

        if self.adm_enricher is not None:
            t0 = time.perf_counter()
            self.logger.debug("  Enriching with ADM boundaries...")

            df = self.adm_enricher.enrich(df)

            rows_after_adm = len(df)
            dt = time.perf_counter() - t0

            self.logger.debug(
                f"    ADM enrichment complete in {dt:.2f}s "
                f"({rows_after_adm:,} rows)"
            )

            # Log if any rows were lost during spatial join
            if rows_after_adm < rows_before:
                self.logger.warning(
                    f"    Lost {rows_before - rows_after_adm} rows during ADM enrichment"
                )
        else:
            self.logger.debug("  ADM enrichment disabled")

        # ------------------------------------------------------------------
        # Step 4: Save to Parquet
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        self.logger.debug(f"  Writing to {output_file.name}...")

        output_file.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(output_file, compression="zstd", statistics=True)

        dt_write = time.perf_counter() - t0
        file_size = output_file.stat().st_size / (1024 ** 2)

        self.logger.debug(f"    Written in {dt_write:.2f}s ({file_size:.1f} MB)")

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        dt_total = time.perf_counter() - t_start

        self.logger.info(
            f"  Complete: {grib_file.name} → {output_file.name} "
            f"({rows_after_adm:,} rows, {dt_total:.2f}s)",
            force=True
        )

        return MaskingResult(
            output_file=output_file,
            input_file=grib_file,
            rows_before_mask=len(self.mask) * n_timestamps,
            rows_after_mask=rows_before,
            rows_after_adm=rows_after_adm,
            variables=var_names,
            processing_time_s=dt_total,
            file_size_mb=file_size,
        )

    def process_batch(
        self,
        grib_files: List[Path],
        output_dir: Path,
        output_pattern: str = "{stem}.parquet",
        variables: Optional[List[str]] = None
    ) -> List[MaskingResult]:
        """
        Process a batch of GRIB files sequentially.

        Parameters
        ----------
        grib_files : list of Path
            Input GRIB files to process.
        output_dir : Path
            Output directory for parquet files.
        output_pattern : str, optional
            Output filename pattern. {stem} will be replaced with input filename stem.
        variables : list of str, optional
            Variables to extract.

        Returns
        -------
        list of MaskingResult
            Results for each file.
        """
        results = []

        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info(f"PROCESSING BATCH: {len(grib_files)} FILES", force=True)
        self.logger.info("=" * 72, force=True)

        for i, grib_file in enumerate(grib_files, 1):
            self.logger.info(f"[{i}/{len(grib_files)}]", force=True)

            output_name = output_pattern.format(stem=grib_file.stem)
            output_file = output_dir / output_name

            try:
                result = self.process_file(
                    grib_file=grib_file,
                    output_file=output_file,
                    variables=variables
                )
                results.append(result)
            except Exception as e:
                self.logger.error(f"  Failed to process {grib_file.name}: {e}")
                continue

        # Summary
        successful = len(results)
        failed = len(grib_files) - successful

        total_time = sum(r.processing_time_s for r in results)
        total_rows = sum(r.rows_after_adm for r in results)
        total_size = sum(r.file_size_mb for r in results)

        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("BATCH COMPLETE", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info(f"  Successful: {successful}/{len(grib_files)}", force=True)
        self.logger.info(f"  Failed: {failed}", force=True)
        self.logger.info(f"  Total rows: {total_rows:,}", force=True)
        self.logger.info(f"  Total size: {total_size:.1f} MB", force=True)
        self.logger.info(f"  Total time: {total_time:.2f}s", force=True)
        self.logger.info("=" * 72, force=True)

        return results