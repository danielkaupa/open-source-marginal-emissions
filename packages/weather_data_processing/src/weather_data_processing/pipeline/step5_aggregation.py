# packages/weather_data_processing/src/weather_data_processing/pipeline/step5_aggregation.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Step 5: Spatial Aggregation Pipeline
=====================================

Create national and regional time-series from half-hourly gridded data.

This step performs **spatial aggregation only** — half-hourly temporal resolution
is always preserved. Output files contain one row per region per half-hourly timestep.

Pipeline outputs:
- ADM0 (national): Single time-series for the entire country
- ADM1 (state/province): One time-series per first-level administrative unit
- ADM2 (district): One time-series per second-level administrative unit

Supports both sequential and MPI parallelization (distributes files across ranks).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    from mpi4py import MPI
    HAS_MPI = True
except ImportError:
    HAS_MPI = False
    MPI = None

from ..processing.aggregation import (
    SpatialAggregator,
    SpatialAggregationResult,
    DEFAULT_WIND_PAIRS,
)
from ..utils.logging import VerboseLogger
from ..utils.parallel import get_mpi_rank, is_rank_zero


class AggregationPipeline:
    """
    Orchestrator for Step 5: Spatial aggregation.

    This pipeline aggregates gridded half-hourly data to regional time-series.
    **Temporal resolution is always preserved** — half-hourly input produces
    half-hourly output.

    Parameters
    ----------
    input_dir : Path
        Directory containing half-hourly transformed files from Step 4.
    output_dir : Path
        Directory for aggregated time-series outputs.
    aggregation_levels : list of str, optional
        Administrative levels to aggregate ('ADM0', 'ADM1', 'ADM2').
    weight_by_area : bool, optional
        Use area-weighted averaging (default True).
    intensive_vars : list of str, optional
        ERA5 shortnames for intensive variables (weighted mean only).
    extensive_vars : list of str, optional
        ERA5 shortnames for extensive variables (weighted mean + weighted sum).
    wind_pairs : dict, optional
        Mapping of height label → (u_col, v_col) for wind derivation.
    logger : VerboseLogger, optional
        Logger instance.

    Examples
    --------
    >>> pipeline = AggregationPipeline(
    ...     input_dir=Path("data/era5-world/transformed"),
    ...     output_dir=Path("data/era5-world/national"),
    ...     aggregation_levels=["ADM0", "ADM1"],
    ... )
    >>> results = pipeline.run(use_mpi=True)
    """

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        aggregation_levels: Optional[List[str]] = None,
        weight_by_area: bool = True,
        logger: Optional[VerboseLogger] = None,
        intensive_vars: Optional[List[str]] = None,
        extensive_vars: Optional[List[str]] = None,
        wind_pairs: Optional[Dict] = None,
    ):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.aggregation_levels = aggregation_levels or ["ADM0"]
        self.weight_by_area = weight_by_area
        self.logger = logger or VerboseLogger("aggregation_pipeline", verbose=False)
        self.intensive_vars = intensive_vars
        self.extensive_vars = extensive_vars
        self.wind_pairs = wind_pairs if wind_pairs is not None else DEFAULT_WIND_PAIRS

    def _discover_files(self) -> List[Path]:
        """Discover half-hourly files from Step 4."""
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {self.input_dir}")

        files = sorted(self.input_dir.glob("*_halfhourly.parquet"))

        if not files:
            raise FileNotFoundError(
                f"No half-hourly parquet files found in {self.input_dir}"
            )

        self.logger.info(f"Discovered {len(files)} files to aggregate")

        return files

    def _run_spatial_aggregation(
        self,
        files: List[Path]
    ) -> Dict[str, List[SpatialAggregationResult]]:
        """
        Run spatial aggregation for all levels.

        Returns
        -------
        dict
            Mapping of aggregation_level → list of results.
        """
        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("STEP 5: SPATIAL AGGREGATION", force=True)
        self.logger.info("=" * 72, force=True)

        results_by_level = {}

        for level in self.aggregation_levels:
            self.logger.info(f"  Aggregating to {level} level...", force=True)

            aggregator = SpatialAggregator(
                aggregation_level=level,
                weight_by_area=self.weight_by_area,
                logger=self.logger,
                intensive_vars=self.intensive_vars,
                extensive_vars=self.extensive_vars,
                wind_pairs=self.wind_pairs,
            )

            level_results = []

            for i, input_file in enumerate(files, 1):
                self.logger.info(f"    [{i}/{len(files)}] {input_file.name}")

                # Build output path
                # Pattern: {stem}_{level}_halfhourly.parquet
                output_name = input_file.stem.replace(
                    "_halfhourly", f"_{level}_halfhourly"
                ) + ".parquet"

                output_file = self.output_dir / level / output_name

                try:
                    result = aggregator.aggregate_file(
                        input_file=input_file,
                        output_file=output_file,
                        overwrite=True
                    )

                    if result:
                        level_results.append(result)
                except Exception as e:
                    self.logger.error(f"Failed to aggregate {input_file.name}: {e}")

            results_by_level[level] = level_results

        return results_by_level

    def run(
        self,
        use_mpi: bool = False
    ) -> Dict:
        """
        Execute the spatial aggregation pipeline.

        Parameters
        ----------
        use_mpi : bool, optional
            Use MPI parallelization (distributes files across ranks).

        Returns
        -------
        dict
            Pipeline results with statistics.
        """
        t_total = time.perf_counter()

        # ------------------------------------------------------------------
        # Setup
        # ------------------------------------------------------------------
        if is_rank_zero():
            self.logger.info("", force=True)
            self.logger.info("#" * 72, force=True)
            self.logger.info("# STEP 5: SPATIAL AGGREGATION PIPELINE", force=True)
            self.logger.info("#" * 72, force=True)
            self.logger.info("", force=True)

        # MPI setup
        if use_mpi and HAS_MPI:
            comm = MPI.COMM_WORLD
            rank = comm.Get_rank()
            size = comm.Get_size()
        else:
            if use_mpi:
                self.logger.warning("MPI requested but not available, using sequential")
            rank = 0
            size = 1
            comm = None

        # ------------------------------------------------------------------
        # Discovery (rank 0)
        # ------------------------------------------------------------------
        if rank == 0:
            files = self._discover_files()
        else:
            files = None

        # Broadcast to all ranks
        if comm:
            files = comm.bcast(files, root=0)

        # Assign files to this rank
        my_files = [f for i, f in enumerate(files) if i % size == rank]

        if rank == 0:
            self.logger.info(f"Processing {len(files)} files across {size} ranks")
            self.logger.info(f"  Aggregation levels: {', '.join(self.aggregation_levels)}")
            self.logger.info("  Temporal resolution: half-hourly (preserved)")

        # ------------------------------------------------------------------
        # Spatial Aggregation
        # ------------------------------------------------------------------
        spatial_results_local = self._run_spatial_aggregation(my_files)

        # Gather results
        if comm:
            all_spatial_results = comm.gather(spatial_results_local, root=0)
            comm.Barrier()

            if rank == 0:
                # Merge results from all ranks
                spatial_results_global = {}
                for level in self.aggregation_levels:
                    spatial_results_global[level] = []
                    for rank_results in all_spatial_results:
                        if level in rank_results:
                            spatial_results_global[level].extend(rank_results[level])
            else:
                spatial_results_global = None
        else:
            spatial_results_global = spatial_results_local

        if comm:
            comm.Barrier()

        # ------------------------------------------------------------------
        # Summary (rank 0)
        # ------------------------------------------------------------------
        dt_total = time.perf_counter() - t_total

        if rank == 0:
            self.logger.info("", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info("AGGREGATION PIPELINE COMPLETE", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info(f"  Total time: {dt_total:.2f}s", force=True)

            # Spatial aggregation summary
            for level, results in spatial_results_global.items():
                total_regions = sum(r.num_regions for r in results)
                total_timesteps = sum(r.num_timesteps for r in results)
                self.logger.info(
                    f"  {level}: {len(results)} files, "
                    f"{total_regions} region(s), {total_timesteps:,} half-hourly timesteps",
                    force=True
                )

            self.logger.info(f"  Output: {self.output_dir}", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info("", force=True)

            return {
                "spatial_results": spatial_results_global,
                "output_dir": self.output_dir,
                "total_time_s": dt_total,
            }
        else:
            return {}