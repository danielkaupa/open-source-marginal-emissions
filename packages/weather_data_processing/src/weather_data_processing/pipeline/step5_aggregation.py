# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Step 5: Aggregation Pipeline
=============================

Create national and regional time-series from half-hourly gridded data.

Pipeline stages:
1. **Spatial aggregation**: Grid → Regional time-series
2. **Temporal aggregation** (optional): Half-hourly → Daily/Monthly
3. **Multi-level outputs**: ADM0 (national), ADM1 (state), ADM2 (district)

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

from ..processing.aggregation import SpatialAggregator, AggregationResult
from ..utils.logging import VerboseLogger
from ..utils.parallel import get_mpi_rank, is_rank_zero


class AggregationPipeline:
    """
    Orchestrator for Step 5: Spatial and temporal aggregation.
    
    Parameters
    ----------
    input_dir : Path
        Directory containing half-hourly transformed files from Step 4.
    output_dir : Path
        Directory for aggregated time-series outputs.
    aggregation_levels : list of str, optional
        Administrative levels to aggregate ('ADM0', 'ADM1', 'ADM2').
    temporal_modes : list of str, optional
        Temporal aggregation modes ('daily', 'weekly', 'monthly', 'annual').
        If None or empty, keep half-hourly resolution.
    weight_by_area : bool, optional
        Use area-weighted averaging (default True).
    logger : VerboseLogger, optional
        Logger instance.
    
    Examples
    --------
    >>> pipeline = AggregationPipeline(
    ...     input_dir=Path("data/era5-world/transformed"),
    ...     output_dir=Path("data/era5-world/national"),
    ...     aggregation_levels=["ADM0", "ADM1"],
    ...     temporal_modes=["daily", "monthly"]
    ... )
    >>> results = pipeline.run(use_mpi=True)
    """
    
    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        aggregation_levels: Optional[List[str]] = None,
        temporal_modes: Optional[List[str]] = None,
        weight_by_area: bool = True,
        logger: Optional[VerboseLogger] = None,
    ):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.aggregation_levels = aggregation_levels or ["ADM0"]
        self.temporal_modes = temporal_modes or []
        self.weight_by_area = weight_by_area
        self.logger = logger or VerboseLogger("aggregation_pipeline", verbose=False)
    
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
    ) -> Dict[str, List[AggregationResult]]:
        """
        Run spatial aggregation for all levels.
        
        Returns
        -------
        dict
            Mapping of aggregation_level → list of results.
        """
        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("STAGE 5a: SPATIAL AGGREGATION", force=True)
        self.logger.info("=" * 72, force=True)
        
        results_by_level = {}
        
        for level in self.aggregation_levels:
            self.logger.info(f"  Aggregating to {level} level...", force=True)
            
            aggregator = SpatialAggregator(
                aggregation_level=level,
                weight_by_area=self.weight_by_area,
                logger=self.logger
            )
            
            level_results = []
            
            for i, input_file in enumerate(files, 1):
                self.logger.info(f"    [{i}/{len(files)}] {input_file.name}")
                
                # Build output path
                # Pattern: {stem}_{level}_halfhourly.parquet
                output_name = input_file.stem.replace(
                    "_halfhourly", f"_{level}_halfhourly"
                ) + ".parquet"
                
                output_file = self.output_dir / level / "halfhourly" / output_name
                
                try:
                    result = aggregator.aggregate_file(
                        input_file=input_file,
                        output_file=output_file,
                        temporal_agg=None,  # Keep half-hourly
                        overwrite=True
                    )
                    
                    if result:
                        level_results.append(result)
                except Exception as e:
                    self.logger.error(f"Failed to aggregate {input_file.name}: {e}")
            
            results_by_level[level] = level_results
        
        return results_by_level
    
    def _run_temporal_aggregation(
        self,
        spatial_results: Dict[str, List[AggregationResult]]
    ) -> Dict[str, Dict[str, List[AggregationResult]]]:
        """
        Run temporal aggregation on spatially aggregated files.
        
        Returns
        -------
        dict
            Mapping of aggregation_level → temporal_mode → list of results.
        """
        if not self.temporal_modes:
            self.logger.info("  Temporal aggregation: SKIPPED (no modes specified)")
            return {}
        
        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("STAGE 5b: TEMPORAL AGGREGATION", force=True)
        self.logger.info("=" * 72, force=True)
        
        results_by_level_mode = {}
        
        for level, spatial_results_list in spatial_results.items():
            results_by_level_mode[level] = {}
            
            for mode in self.temporal_modes:
                self.logger.info(
                    f"  Aggregating {level} to {mode} resolution...",
                    force=True
                )
                
                aggregator = SpatialAggregator(
                    aggregation_level=level,
                    weight_by_area=self.weight_by_area,
                    logger=self.logger
                )
                
                mode_results = []
                
                for spatial_result in spatial_results_list:
                    # Input is the half-hourly aggregated file
                    input_file = spatial_result.output_file
                    
                    # Output pattern: {stem}_{mode}.parquet
                    output_name = input_file.stem.replace(
                        "_halfhourly", f"_{mode}"
                    ) + ".parquet"
                    
                    output_file = self.output_dir / level / mode / output_name
                    
                    try:
                        result = aggregator.aggregate_file(
                            input_file=input_file,
                            output_file=output_file,
                            temporal_agg=mode,
                            overwrite=True
                        )
                        
                        if result:
                            mode_results.append(result)
                    except Exception as e:
                        self.logger.error(
                            f"Failed temporal aggregation {input_file.name}: {e}"
                        )
                
                results_by_level_mode[level][mode] = mode_results
        
        return results_by_level_mode
    
    def run(
        self,
        use_mpi: bool = False
    ) -> Dict:
        """
        Execute the complete aggregation pipeline.
        
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
            self.logger.info("# STEP 5: AGGREGATION PIPELINE", force=True)
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
            self.logger.info(f"  Temporal modes: {', '.join(self.temporal_modes) if self.temporal_modes else 'None (keep half-hourly)'}")
        
        # ------------------------------------------------------------------
        # Stage 5a: Spatial Aggregation
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
        
        # ------------------------------------------------------------------
        # Stage 5b: Temporal Aggregation (rank 0 only for simplicity)
        # ------------------------------------------------------------------
        if rank == 0:
            temporal_results = self._run_temporal_aggregation(spatial_results_global)
        else:
            temporal_results = None
        
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
                    f"{total_regions} region(s), {total_timesteps:,} timesteps",
                    force=True
                )
            
            # Temporal aggregation summary
            if temporal_results:
                self.logger.info("", force=True)
                self.logger.info("  Temporal aggregation:", force=True)
                for level, modes_dict in temporal_results.items():
                    for mode, results in modes_dict.items():
                        self.logger.info(
                            f"    {level} {mode}: {len(results)} files",
                            force=True
                        )
            
            self.logger.info(f"  Output: {self.output_dir}", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info("", force=True)
            
            return {
                "spatial_results": spatial_results_global,
                "temporal_results": temporal_results,
                "output_dir": self.output_dir,
                "total_time_s": dt_total,
            }
        else:
            return {}
