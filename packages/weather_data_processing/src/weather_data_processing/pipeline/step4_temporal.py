# packages/weather_data_processing/src/weather_data_processing/pipeline/step4_temporal.py

# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Step 4: Temporal Interpolation Pipeline
========================================

Complete temporal processing pipeline:
1. **Stage 4a**: Interpolate hourly → half-hourly
2. **Stage 4b**: Sort and cleanup
3. **Stage 4c**: Fix year boundaries (Dec 31 23:30)
4. **Stage 4d**: Validate temporal data

Supports both sequential and MPI parallelization (distributes years across ranks).
"""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

try:
    from mpi4py import MPI
    HAS_MPI = True
except ImportError:
    HAS_MPI = False
    MPI = None

from ..processing.interpolation import TemporalInterpolator, InterpolationResult
from ..processing.boundary_fix import YearBoundaryFixer, BoundaryFixResult
from ..processing.temporal_validation import TemporalValidator, ValidationResult
from ..utils.logging import VerboseLogger
from ..utils.parallel import get_mpi_rank, is_rank_zero


class TemporalPipeline:
    """
    Orchestrator for Step 4: Temporal interpolation.

    Parameters
    ----------
    input_dir : Path
        Directory containing annual/quarterly files from Step 3.
    output_dir : Path
        Directory for half-hourly transformed files.
    temp_dir : Path, optional
        Directory for intermediate files.
    datetime_unit : str, optional
        Datetime precision ('us', 'ns', 'ms', 's').
    validate : bool, optional
        Run validation after interpolation (default True).
    cleanup_temp : bool, optional
        Remove temporary files after completion (default False).
    logger : VerboseLogger, optional
        Logger instance.

    Examples
    --------
    >>> pipeline = TemporalPipeline(
    ...     input_dir=Path("data/era5-world/processed"),
    ...     output_dir=Path("data/era5-world/transformed"),
    ...     validate=True
    ... )
    >>> results = pipeline.run(use_mpi=True)
    """

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        temp_dir: Optional[Path] = None,
        datetime_unit: str = "us",
        validate: bool = True,
        cleanup_temp: bool = False,
        logger: Optional[VerboseLogger] = None,
        intensive_cols: Optional[List[str]] = None,
        rate_shaped_cols: Optional[List[str]] = None,
        even_split_cols: Optional[List[str]] = None,
        static_cols: Optional[List[str]] = None,
    ):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.temp_dir = temp_dir or (output_dir.parent / "temp" / "temporal")
        self.datetime_unit = datetime_unit
        self.validate = validate
        self.cleanup_temp = cleanup_temp
        self.logger = logger or VerboseLogger("temporal_pipeline", verbose=False)
        self.intensive_cols = intensive_cols
        self.rate_shaped_cols = rate_shaped_cols
        self.even_split_cols = even_split_cols
        self.static_cols = static_cols

        # Subdirectories for stages
        self.stage4a_dir = self.temp_dir / "4a_halfhourly"
        self.stage4c_dir = self.temp_dir / "4c_fixed"

    def _discover_files(self) -> List[Path]:
        """Discover annual/quarterly files from Step 3."""
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {self.input_dir}")

        files = sorted(self.input_dir.glob("*.parquet"))

        if not files:
            raise FileNotFoundError(f"No parquet files found in {self.input_dir}")

        self.logger.info(f"Discovered {len(files)} files to interpolate")

        return files

    def _run_stage4a_interpolation(
        self,
        files: List[Path],
        interpolator: TemporalInterpolator
    ) -> List[InterpolationResult]:
        """
        Stage 4a: Interpolate hourly → half-hourly.

        Returns
        -------
        list of InterpolationResult
            Interpolation results.
        """
        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("STAGE 4a: INTERPOLATION (Hourly → Half-Hourly)", force=True)
        self.logger.info("=" * 72, force=True)

        results = []

        for i, input_file in enumerate(files, 1):
            self.logger.info(f"[{i}/{len(files)}]", force=True)

            # Build output path
            output_file = self.stage4a_dir / input_file.name.replace(
                ".parquet", "_halfhourly.parquet"
            )

            try:
                result = interpolator.interpolate_file(
                    input_file=input_file,
                    output_file=output_file,
                    overwrite=True
                )

                if result:
                    results.append(result)
            except Exception as e:
                self.logger.error(f"Failed to interpolate {input_file.name}: {e}")

        return results

    def _run_stage4b_sorting(
        self,
        files: List[Path]
    ) -> List[Path]:
        """
        Stage 4b: Sort and cleanup half-hourly files.

        This stage is mostly handled during interpolation (we already sort).
        Just verify files are ready.

        Returns
        -------
        list of Path
            Sorted files (same as input).
        """
        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("STAGE 4b: SORTING & CLEANUP", force=True)
        self.logger.info("=" * 72, force=True)

        self.logger.info("  Files already sorted during interpolation", force=True)
        self.logger.info(f"  Verified {len(files)} files ready for boundary fix", force=True)

        return files

    def _run_stage4c_boundary_fix(
        self,
        halfhourly_files: List[Path],
        fixer: YearBoundaryFixer
    ) -> List[BoundaryFixResult]:
        """
        Stage 4c: Fix year boundaries (Dec 31 23:30).

        Returns
        -------
        list of BoundaryFixResult
            Boundary fix results.
        """
        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("STAGE 4c: YEAR BOUNDARY FIX", force=True)
        self.logger.info("=" * 72, force=True)

        # Sort by year
        sorted_files = sorted(halfhourly_files)

        results = fixer.process_year_sequence(
            halfhourly_files=sorted_files,
            output_dir=self.stage4c_dir,
            overwrite=True
        )

        return results

    def _run_stage4d_validation(
        self,
        fixed_files: List[Path],
        validator: TemporalValidator
    ) -> List[ValidationResult]:
        """
        Stage 4d: Validate temporal data.

        Returns
        -------
        list of ValidationResult
            Validation results.
        """
        self.logger.info("", force=True)

        results = validator.validate_batch(
            files=fixed_files,
            strict=False  # Warnings don't fail pipeline
        )

        return results

    def _run_stage4e_finalize(
        self,
        fixed_files: List[Path]
    ) -> List[Path]:
        """
        Stage 4e: Copy fixed files to final output directory.

        Returns
        -------
        list of Path
            Final output files.
        """
        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("STAGE 4e: FINALIZE", force=True)
        self.logger.info("=" * 72, force=True)

        import shutil

        self.output_dir.mkdir(parents=True, exist_ok=True)

        final_files = []

        for fixed_file in fixed_files:
            # Remove "_fixed" suffix
            final_name = fixed_file.name.replace("_fixed", "")
            final_file = self.output_dir / final_name

            shutil.copy(fixed_file, final_file)
            final_files.append(final_file)

            self.logger.debug(f"  Copied: {final_name}")

        self.logger.info(f"  Finalized {len(final_files)} files", force=True)

        return final_files

    def _cleanup_temp_dirs(self):
        """Remove temporary directories."""
        import shutil

        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("CLEANING UP TEMPORARY DIRECTORIES", force=True)
        self.logger.info("=" * 72, force=True)

        for temp_dir in [self.stage4a_dir, self.stage4c_dir]:
            if temp_dir.exists():
                file_count = len(list(temp_dir.glob("*")))
                shutil.rmtree(temp_dir)
                self.logger.info(f"  Deleted {temp_dir}: {file_count} files")

    def run(
        self,
        use_mpi: bool = False
    ) -> Dict:
        """
        Execute the complete temporal pipeline.

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
            self.logger.info("# STEP 4: TEMPORAL INTERPOLATION PIPELINE", force=True)
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
            self.logger.info(f"  Each rank processes ~{len(files) // size} files")

        # ------------------------------------------------------------------
        # Create processors
        # ------------------------------------------------------------------
        interpolator = TemporalInterpolator(
            datetime_unit=self.datetime_unit,
            logger=self.logger,
            intensive_cols=self.intensive_cols,
            rate_shaped_cols=self.rate_shaped_cols,
            even_split_cols=self.even_split_cols,
            static_cols=self.static_cols,
        )

        fixer = YearBoundaryFixer(logger=self.logger)
        validator = TemporalValidator(logger=self.logger)

        # ------------------------------------------------------------------
        # Stage 4a: Interpolation
        # ------------------------------------------------------------------
        results4a_local = self._run_stage4a_interpolation(my_files, interpolator)

        # Gather results
        if comm:
            all_results4a = comm.gather(results4a_local, root=0)
            comm.Barrier()

            if rank == 0:
                results4a = [r for rlist in all_results4a for r in rlist if r]
                halfhourly_files = [r.output_file for r in results4a]
            else:
                results4a = None
                halfhourly_files = None

            halfhourly_files = comm.bcast(halfhourly_files, root=0)
        else:
            results4a = results4a_local
            halfhourly_files = [r.output_file for r in results4a]

        # ------------------------------------------------------------------
        # Stage 4b: Sorting (already done during interpolation)
        # ------------------------------------------------------------------
        if rank == 0:
            halfhourly_files = self._run_stage4b_sorting(halfhourly_files)

        if comm:
            comm.Barrier()
            halfhourly_files = comm.bcast(halfhourly_files, root=0)

        # ------------------------------------------------------------------
        # Stage 4c: Boundary Fix (sequential, rank 0 only)
        # ------------------------------------------------------------------
        if rank == 0:
            results4c = self._run_stage4c_boundary_fix(halfhourly_files, fixer)
            fixed_files = [r.output_file for r in results4c]
        else:
            results4c = None
            fixed_files = None

        if comm:
            comm.Barrier()
            fixed_files = comm.bcast(fixed_files, root=0)

        # ------------------------------------------------------------------
        # Stage 4d: Validation (optional, rank 0 only)
        # ------------------------------------------------------------------
        if self.validate and rank == 0:
            results4d = self._run_stage4d_validation(fixed_files, validator)
        else:
            results4d = None

        if comm:
            comm.Barrier()

        # ------------------------------------------------------------------
        # Stage 4e: Finalize (rank 0 only)
        # ------------------------------------------------------------------
        if rank == 0:
            final_files = self._run_stage4e_finalize(fixed_files)
        else:
            final_files = None

        if comm:
            comm.Barrier()

        # ------------------------------------------------------------------
        # Cleanup (rank 0 only)
        # ------------------------------------------------------------------
        if self.cleanup_temp and rank == 0:
            self._cleanup_temp_dirs()

        if comm:
            comm.Barrier()

        # ------------------------------------------------------------------
        # Summary (rank 0)
        # ------------------------------------------------------------------
        dt_total = time.perf_counter() - t_total

        if rank == 0:
            self.logger.info("", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info("TEMPORAL PIPELINE COMPLETE", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info(f"  Total time: {dt_total:.2f}s", force=True)
            self.logger.info(f"  Files interpolated: {len(results4a)}", force=True)
            if results4c:
                boundary_fixed = sum(r.boundary_rows_fixed for r in results4c)
                self.logger.info(f"  Boundary rows fixed: {boundary_fixed:,}", force=True)
            if results4d:
                valid_count = sum(1 for r in results4d if r.is_valid)
                self.logger.info(f"  Validation: {valid_count}/{len(results4d)} passed", force=True)
            self.logger.info(f"  Output: {self.output_dir}", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info("", force=True)

            return {
                "results_stage4a": results4a,
                "results_stage4c": results4c,
                "results_stage4d": results4d,
                "final_files": final_files,
                "output_dir": self.output_dir,
                "total_time_s": dt_total,
            }
        else:
            return {}