# packages/weather_data_processing/src/weather_data_processing/pipeline/step2_masking.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Step 2: GRIB Masking Pipeline
==============================

Apply spatial masks to GRIB files and convert to Parquet with ADM enrichment.

Pipeline Steps:
1. Load mask and metadata from Step 1
2. Set up ADM enrichment (if configured)
3. Discover GRIB files to process
4. Process files in parallel (MPI or multiprocessing)
5. Save masked+enriched Parquet files

This module supports both sequential and parallel execution:
- Local: ProcessPoolExecutor with auto-detected workers
- HPC: MPI parallelization (one file per rank)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from packages.osme_common.src.osme_common.paths import repo_root, resolve_under

try:
    from mpi4py import MPI
    HAS_MPI = True
except ImportError:
    HAS_MPI = False
    MPI = None

from ..config_schema import GeographicConfig, DataPathsConfig
from ..processing.grib_masking import GRIBMaskingProcessor, MaskingResult
from ..processing.admin_enrichment import ADMEnricher
from ..utils.logging import VerboseLogger
from ..utils.parallel import detect_environment, get_mpi_rank, is_rank_zero


class MaskingPipeline:
    """
    Orchestrator for Step 2: GRIB masking with ADM enrichment.

    Parameters
    ----------
    mask_file : Path
        Path to spatial mask parquet file (output from Step 1).
    mask_metadata_file : Path
        Path to mask metadata JSON file (output from Step 1).
    geographic_config : GeographicConfig or None
        Geographic configuration (for ADM enrichment).
    data_paths : DataPathsConfig
        Data paths configuration.
    logger : VerboseLogger or None
        Logger instance.

    Examples
    --------
    >>> pipeline = MaskingPipeline(
    ...     mask_file=Path("masks/era5-world_INDIA_mask.parquet"),
    ...     mask_metadata_file=Path("masks/metadata/era5-world_INDIA_mask.json"),
    ...     geographic_config=config.geographic,
    ...     data_paths=config.data_paths
    ... )
    >>> results = pipeline.run()
    """

    def __init__(
        self,
        mask_file: Path,
        mask_metadata_file: Path,
        geographic_config: Optional[GeographicConfig],
        data_paths: DataPathsConfig,
        logger: Optional[VerboseLogger] = None,
    ):
        self.mask_file = mask_file
        self.mask_metadata_file = mask_metadata_file
        self.geographic_config = geographic_config
        self.data_paths = data_paths
        self.logger = logger or VerboseLogger("masking_pipeline", verbose=False)

        # Load mask metadata
        self.mask_metadata = json.loads(mask_metadata_file.read_text())

        # Set up ADM enricher (if configured)
        self.adm_enricher: Optional[ADMEnricher] = None
        if geographic_config and geographic_config.adm_enrichment:
            self._setup_adm_enrichment()

    def _setup_adm_enrichment(self):
        """Set up ADM enrichment if configured."""
        if not self.geographic_config:
            return

        adm_config = self.geographic_config.adm_enrichment
        boundary_config = self.geographic_config.boundary

        if not (adm_config.enable_adm1 or adm_config.enable_adm2):
            self.logger.info("ADM enrichment disabled")
            return

        self.logger.info("Setting up ADM enrichment...")

        # Resolve shapefile paths
        adm1_shp = None
        adm2_shp = None

        if adm_config.enable_adm1 and boundary_config.shapefile_adm1:
            adm1_shp = resolve_under(repo_root(), boundary_config.shapefile_adm1)
            if not adm1_shp.exists():
                self.logger.warning(f"ADM1 shapefile not found: {adm1_shp}")
                adm1_shp = None

        if adm_config.enable_adm2 and boundary_config.shapefile_adm2:
            adm2_shp = resolve_under(repo_root(), boundary_config.shapefile_adm2)
            if not adm2_shp.exists():
                self.logger.warning(f"ADM2 shapefile not found: {adm2_shp}")
                adm2_shp = None

        # Create enricher
        try:
            self.adm_enricher = ADMEnricher(
                config=adm_config,
                adm1_shapefile=adm1_shp,
                adm2_shapefile=adm2_shp,
                logger=self.logger
            )

            summary = self.adm_enricher.summary()
            self.logger.info(f"  ADM1: {summary['adm1_features']} features")
            self.logger.info(f"  ADM2: {summary['adm2_features']} features")
        except Exception as e:
            self.logger.warning(f"Failed to set up ADM enrichment: {e}")
            self.adm_enricher = None

    def _discover_grib_files(self) -> List[Path]:
        """Discover GRIB files to process."""
        grib_dir = resolve_under(repo_root(), self.data_paths.grib_dir)

        if not grib_dir.exists():
            raise FileNotFoundError(f"GRIB directory not found: {grib_dir}")

        # Find all GRIB files
        grib_files = sorted(grib_dir.glob("*.grib"))

        if not grib_files:
            raise FileNotFoundError(f"No GRIB files found in {grib_dir}")

        self.logger.info(f"Discovered {len(grib_files)} GRIB files")

        return grib_files

    def _process_file_worker(
        self,
        grib_file: Path,
        output_dir: Path,
        processor: GRIBMaskingProcessor
    ) -> MaskingResult:
        """Process a single file (worker function)."""
        # Build output filename
        # Pattern: {dataset_prefix}_{COUNTRY}_{hash}_{year}-{month}.parquet
        prefix = self.mask_metadata.get("dataset_prefix", "era5-world")
        country = self.mask_metadata.get("country_token", "COUNTRY")

        # Extract year-month from GRIB filename
        # Expected: era5-world_N37W68S6E98_d514a3a3c256_2018-01.grib
        stem = grib_file.stem
        parts = stem.split("_")

        # Try to find year-month pattern
        year_month = None
        for part in parts:
            if "-" in part and len(part) >= 7:
                year_month = part
                break

        if year_month:
            output_name = f"{prefix}_{country}_{year_month}.parquet"
        else:
            output_name = f"{prefix}_{country}_{stem}.parquet"

        output_file = output_dir / output_name

        return processor.process_file(
            grib_file=grib_file,
            output_file=output_file
        )

    def run_sequential(
        self,
        grib_files: List[Path],
        output_dir: Path
    ) -> List[MaskingResult]:
        """Run processing sequentially."""
        self.logger.info("Running in SEQUENTIAL mode")

        processor = GRIBMaskingProcessor(
            mask_file=self.mask_file,
            mask_metadata=self.mask_metadata,
            adm_enricher=self.adm_enricher,
            logger=self.logger
        )

        results = []
        for i, grib_file in enumerate(grib_files, 1):
            self.logger.info(f"[{i}/{len(grib_files)}]", force=True)

            try:
                result = self._process_file_worker(grib_file, output_dir, processor)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Failed to process {grib_file.name}: {e}")

        return results

    def run_mpi(
        self,
        grib_files: List[Path],
        output_dir: Path
    ) -> List[MaskingResult]:
        """Run processing with MPI parallelization."""
        if not HAS_MPI:
            raise RuntimeError("MPI requested but mpi4py not available")

        comm = MPI.COMM_WORLD
        rank = comm.Get_rank()
        size = comm.Get_size()

        if rank == 0:
            self.logger.info(f"Running in MPI mode with {size} ranks")

        # Distribute files across ranks
        my_files = [f for i, f in enumerate(grib_files) if i % size == rank]

        if rank == 0:
            self.logger.info(f"Each rank will process ~{len(grib_files) // size} files")

        # Process assigned files
        processor = GRIBMaskingProcessor(
            mask_file=self.mask_file,
            mask_metadata=self.mask_metadata,
            adm_enricher=self.adm_enricher,
            logger=self.logger
        )

        results = []
        for i, grib_file in enumerate(my_files, 1):
            self.logger.info(
                f"[Rank {rank}] [{i}/{len(my_files)}] {grib_file.name}",
                force=True
            )

            try:
                result = self._process_file_worker(grib_file, output_dir, processor)
                results.append(result)
            except Exception as e:
                self.logger.error(f"[Rank {rank}] Failed: {grib_file.name}: {e}")

        # Gather results at rank 0
        all_results = comm.gather(results, root=0)

        if rank == 0:
            # Flatten results
            results = [r for rank_results in all_results for r in rank_results]
            return results
        else:
            return []

    def run(
        self,
        use_mpi: bool = False
    ) -> Dict[str, Any]:
        """
        Execute the complete masking pipeline.

        Parameters
        ----------
        use_mpi : bool, optional
            Whether to use MPI parallelization (default False).
            If True but MPI not available, falls back to sequential.

        Returns
        -------
        dict
            Pipeline result dictionary with:
            - results: List of MaskingResult objects
            - output_dir: Output directory path
            - total_files: Number of files processed
            - total_time_s: Total processing time
        """
        t_total = time.perf_counter()

        if is_rank_zero():
            self.logger.info("", force=True)
            self.logger.info("#" * 72, force=True)
            self.logger.info("# STEP 2: GRIB MASKING PIPELINE", force=True)
            self.logger.info("#" * 72, force=True)
            self.logger.info("", force=True)

        # ------------------------------------------------------------------
        # Stage 1: Discover GRIB files
        # ------------------------------------------------------------------
        grib_files = self._discover_grib_files()

        # ------------------------------------------------------------------
        # Stage 2: Set up output directory
        # ------------------------------------------------------------------
        output_dir = resolve_under(repo_root(), self.data_paths.interim_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if is_rank_zero():
            self.logger.info(f"Output directory: {output_dir}")
            self.logger.info("")

        # ------------------------------------------------------------------
        # Stage 3: Process files
        # ------------------------------------------------------------------
        env = detect_environment()

        if use_mpi and HAS_MPI and env.backend in ("pbs", "slurm", "mpi"):
            results = self.run_mpi(grib_files, output_dir)
        else:
            if use_mpi:
                self.logger.warning("MPI requested but not available, using sequential")
            results = self.run_sequential(grib_files, output_dir)

        # ------------------------------------------------------------------
        # Summary (only on rank 0)
        # ------------------------------------------------------------------
        if is_rank_zero():
            dt_total = time.perf_counter() - t_total

            successful = len(results)
            failed = len(grib_files) - successful
            total_rows = sum(r.rows_after_adm for r in results)
            total_size = sum(r.file_size_mb for r in results)

            self.logger.info("", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info("MASKING PIPELINE COMPLETE", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info(f"  Total time: {dt_total:.2f}s", force=True)
            self.logger.info(f"  Files processed: {successful}/{len(grib_files)}", force=True)
            self.logger.info(f"  Failed: {failed}", force=True)
            self.logger.info(f"  Total rows: {total_rows:,}", force=True)
            self.logger.info(f"  Total size: {total_size:.1f} MB", force=True)
            self.logger.info(f"  Output: {output_dir}", force=True)

            if self.adm_enricher:
                self.logger.info("  ADM enrichment: ENABLED", force=True)
                summary = self.adm_enricher.summary()
                if summary["adm1_enabled"]:
                    self.logger.info(f"    ADM1: {summary['adm1_features']} features", force=True)
                if summary["adm2_enabled"]:
                    self.logger.info(f"    ADM2: {summary['adm2_features']} features", force=True)
            else:
                self.logger.info("  ADM enrichment: DISABLED", force=True)

            self.logger.info("=" * 72, force=True)
            self.logger.info("", force=True)

        return {
            "results": results,
            "output_dir": output_dir,
            "total_files": len(grib_files),
            "total_time_s": time.perf_counter() - t_total,
        }
