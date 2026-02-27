# packages/weather_data_processing/src/weather_data_processing/pipeline/step5_aggregation.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Step 5: Spatial Aggregation Pipeline
=====================================

Create national and regional time-series from half-hourly gridded data.

This step:
1. Aggregates each yearly gridded file to regional time-series
2. Combines all years into a **single output file** per aggregation level

Output filename includes the full date range, e.g.:
    era5-world_INDIA_916d3fbb_2018-01_2026-02_ADM0_halfhourly.parquet

Pipeline outputs:
- ADM0 (national): Single time-series for the entire country
- ADM1 (state/province): One time-series per first-level administrative unit
- ADM2 (district): One time-series per second-level administrative unit

Supports both sequential and MPI parallelization for the aggregation phase.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import polars as pl

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


def extract_date_range_from_files(filepaths: List[Path]) -> Tuple[int, int, int, int]:
    """
    Extract the overall date range from multiple parquet files.
    
    Returns
    -------
    tuple
        (start_year, start_month, end_year, end_month)
    """
    global_min = None
    global_max = None
    
    for fp in filepaths:
        df = pl.read_parquet(fp, columns=["time"])
        file_min = df.select(pl.col("time").min()).item()
        file_max = df.select(pl.col("time").max()).item()
        
        if global_min is None or file_min < global_min:
            global_min = file_min
        if global_max is None or file_max > global_max:
            global_max = file_max
    
    return (
        global_min.year,
        global_min.month,
        global_max.year,
        global_max.month,
    )


def extract_base_name(filepath: Path) -> str:
    """
    Extract the base name pattern from a filename.
    
    Example:
        'era5-world_INDIA_916d3fbb_2018_halfhourly.parquet' 
        → 'era5-world_INDIA_916d3fbb'
    """
    stem = filepath.stem
    
    # Remove _halfhourly suffix
    stem = stem.replace("_halfhourly", "")
    
    # Remove year patterns (_2018, _2018_2019, etc.)
    stem = re.sub(r'_\d{4}(_\d{4})?$', '', stem)
    
    # Remove date range patterns (_2018-01_2026-02)
    stem = re.sub(r'_\d{4}-\d{2}_\d{4}-\d{2}$', '', stem)
    
    return stem


def build_consolidated_filename(
    base_name: str,
    level: str,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> str:
    """
    Build output filename with date range.
    
    Example output:
        era5-world_INDIA_916d3fbb_2018-01_2026-02_ADM0_halfhourly.parquet
    """
    date_range = f"{start_year:04d}-{start_month:02d}_{end_year:04d}-{end_month:02d}"
    return f"{base_name}_{date_range}_{level}_halfhourly.parquet"


class AggregationPipeline:
    """
    Orchestrator for Step 5: Spatial aggregation.

    This pipeline:
    1. Aggregates each gridded half-hourly file to regional time-series
    2. Combines all aggregated files into a single output per level

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
    ...     output_dir=Path("data/era5-world/processed"),
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

        # Look for files with _halfhourly in the name (from Step 4)
        files = sorted(self.input_dir.glob("*_halfhourly.parquet"))
        
        # If none found, try without the suffix (in case naming differs)
        if not files:
            files = sorted(self.input_dir.glob("*.parquet"))

        if not files:
            raise FileNotFoundError(
                f"No parquet files found in {self.input_dir}"
            )

        self.logger.info(f"Discovered {len(files)} half-hourly files to aggregate")

        return files

    def _aggregate_single_file(
        self,
        input_file: Path,
        aggregator: SpatialAggregator,
        temp_dir: Path,
    ) -> Optional[Path]:
        """
        Aggregate a single file and save to temp directory.
        
        Returns the path to the temporary aggregated file.
        """
        temp_output = temp_dir / f"temp_{input_file.name}"
        
        try:
            result = aggregator.aggregate_file(
                input_file=input_file,
                output_file=temp_output,
                overwrite=True
            )
            return temp_output if result else None
        except Exception as e:
            self.logger.error(f"Failed to aggregate {input_file.name}: {e}")
            return None

    def _run_spatial_aggregation(
        self,
        files: List[Path],
        all_files: List[Path],  # All files (for date range extraction)
    ) -> Dict[str, dict]:
        """
        Run spatial aggregation for all levels.
        
        Each level produces a single consolidated output file.

        Returns
        -------
        dict
            Mapping of aggregation_level → {"temp_files": [...], "temp_dir": Path}.
        """
        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("STEP 5: SPATIAL AGGREGATION", force=True)
        self.logger.info("=" * 72, force=True)

        output_files = {}

        for level in self.aggregation_levels:
            self.logger.info(f"\n  Aggregating to {level} level...", force=True)

            aggregator = SpatialAggregator(
                aggregation_level=level,
                weight_by_area=self.weight_by_area,
                logger=self.logger,
                intensive_vars=self.intensive_vars,
                extensive_vars=self.extensive_vars,
                wind_pairs=self.wind_pairs,
            )

            # Create temp directory for intermediate files
            temp_dir = self.output_dir / level / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Aggregate each file
            temp_files = []
            for i, input_file in enumerate(files, 1):
                self.logger.info(f"    [{i}/{len(files)}] {input_file.name}")
                
                temp_file = self._aggregate_single_file(
                    input_file=input_file,
                    aggregator=aggregator,
                    temp_dir=temp_dir,
                )
                if temp_file:
                    temp_files.append(temp_file)

            output_files[level] = {
                "temp_files": temp_files,
                "temp_dir": temp_dir,
            }

        return output_files

    def _consolidate_results(
        self,
        aggregation_results: Dict[str, dict],
        all_files: List[Path],
    ) -> Dict[str, SpatialAggregationResult]:
        """
        Consolidate temporary aggregated files into single output per level.
        """
        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("CONSOLIDATING RESULTS", force=True)
        self.logger.info("=" * 72, force=True)

        # Extract overall date range from original files
        self.logger.info("  Extracting date range from input files...")
        start_year, start_month, end_year, end_month = extract_date_range_from_files(all_files)
        self.logger.info(
            f"  Date range: {start_year:04d}-{start_month:02d} to {end_year:04d}-{end_month:02d}",
            force=True
        )

        # Extract base name from first file
        base_name = extract_base_name(all_files[0])
        self.logger.info(f"  Base name: {base_name}", force=True)

        final_results = {}

        for level, result_data in aggregation_results.items():
            temp_files = result_data["temp_files"]
            temp_dir = result_data["temp_dir"]

            if not temp_files:
                self.logger.warning(f"  No files to consolidate for {level}")
                continue

            self.logger.info(f"\n  Consolidating {level}: {len(temp_files)} files...", force=True)

            t0 = time.perf_counter()

            # Read and concatenate all temp files
            dfs = []
            for tf in sorted(temp_files):
                dfs.append(pl.read_parquet(tf))
            
            df_combined = pl.concat(dfs)
            
            # Sort by time (and region columns if present)
            sort_cols = ["time"]
            if "adm1_code" in df_combined.columns:
                sort_cols.append("adm1_code")
            if "adm2_code" in df_combined.columns:
                sort_cols.append("adm2_code")
            
            df_combined = df_combined.sort(sort_cols)

            # Build output filename
            output_name = build_consolidated_filename(
                base_name=base_name,
                level=level,
                start_year=start_year,
                start_month=start_month,
                end_year=end_year,
                end_month=end_month,
            )
            output_file = self.output_dir / level / output_name

            # Write final output
            output_file.parent.mkdir(parents=True, exist_ok=True)
            df_combined.write_parquet(output_file, compression="zstd", statistics=True)

            dt = time.perf_counter() - t0

            # Count regions and timesteps
            num_timesteps = df_combined.select(pl.col("time").n_unique()).item()
            num_regions = 1
            if level == "ADM1" and "adm1_code" in df_combined.columns:
                num_regions = df_combined.select(pl.col("adm1_code").n_unique()).item()
            elif level == "ADM2" and "adm2_code" in df_combined.columns:
                num_regions = df_combined.select(pl.col("adm2_code").n_unique()).item()

            self.logger.info(
                f"    Output: {output_name}",
                force=True
            )
            self.logger.info(
                f"    {num_regions} region(s), {num_timesteps:,} half-hourly timesteps ({dt:.2f}s)",
                force=True
            )

            final_results[level] = SpatialAggregationResult(
                output_file=output_file,
                aggregation_level=level,
                num_regions=num_regions,
                num_timesteps=num_timesteps,
                processing_time_s=dt,
            )

            # Clean up temp files
            for tf in temp_files:
                tf.unlink()
            try:
                temp_dir.rmdir()
            except OSError:
                pass  # Directory not empty or other issue

        return final_results

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
            all_files = self._discover_files()
        else:
            all_files = None

        # Broadcast to all ranks
        if comm:
            all_files = comm.bcast(all_files, root=0)

        # Assign files to this rank
        my_files = [f for i, f in enumerate(all_files) if i % size == rank]

        if rank == 0:
            self.logger.info(f"Processing {len(all_files)} files across {size} ranks")
            self.logger.info(f"  Aggregation levels: {', '.join(self.aggregation_levels)}")
            self.logger.info("  Temporal resolution: half-hourly (preserved)")
            self.logger.info("  Output: Single consolidated file per level")

        # ------------------------------------------------------------------
        # Spatial Aggregation (parallel across files)
        # ------------------------------------------------------------------
        aggregation_results_local = self._run_spatial_aggregation(my_files, all_files)

        # ------------------------------------------------------------------
        # Gather and consolidate (rank 0 only)
        # ------------------------------------------------------------------
        if comm:
            all_results = comm.gather(aggregation_results_local, root=0)
            comm.Barrier()

            if rank == 0:
                # Merge temp file lists from all ranks
                merged_results = {}
                for level in self.aggregation_levels:
                    merged_results[level] = {
                        "temp_files": [],
                        "temp_dir": None,
                    }
                    for rank_results in all_results:
                        if level in rank_results:
                            merged_results[level]["temp_files"].extend(
                                rank_results[level]["temp_files"]
                            )
                            if rank_results[level]["temp_dir"]:
                                merged_results[level]["temp_dir"] = rank_results[level]["temp_dir"]
                
                aggregation_results = merged_results
            else:
                aggregation_results = None
        else:
            aggregation_results = aggregation_results_local

        # Consolidate on rank 0
        if rank == 0:
            final_results = self._consolidate_results(aggregation_results, all_files)
        else:
            final_results = None

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

            for level, result in final_results.items():
                self.logger.info(
                    f"  {level}: {result.output_file.name}",
                    force=True
                )
                self.logger.info(
                    f"       {result.num_regions} region(s), {result.num_timesteps:,} timesteps",
                    force=True
                )

            self.logger.info(f"  Output directory: {self.output_dir}", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info("", force=True)

            return {
                "results": final_results,
                "output_dir": self.output_dir,
                "total_time_s": dt_total,
            }
        else:
            return {}
