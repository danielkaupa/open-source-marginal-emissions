# packages/weather_data_processing/src/weather_data_processing/pipeline/step3_consolidation.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Step 3: Consolidation Pipeline
================================

Optimize, consolidate, and rename parquet files from Step 2.

Three-stage pipeline:
1. **Optimize**: Clean monthly files (drop columns, cast dtypes)
2. **Consolidate**: Combine into annual/biannual/quarterly files
3. **Rename**: Apply metadata-based column renaming

Supports both sequential and MPI parallelization (distributes years across ranks).
"""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Literal

try:
    from mpi4py import MPI
    HAS_MPI = True
except ImportError:
    HAS_MPI = False
    MPI = None

import polars as pl

from ..processing.consolidation import (
    ConsolidationProcessor,
    parse_filename,
    OptimizationResult,
    ConsolidationResult,
)

from osme_common.paths import repo_root, resolve_under
from ..utils.validation import build_global_dtype_map, DEFAULT_DROP_COLS, DEFAULT_DTYPE_MAP
from ..utils.logging import VerboseLogger
from ..utils.parallel import get_mpi_rank, is_rank_zero


class ConsolidationPipeline:
    """
    Orchestrator for Step 3: Data consolidation.

    Parameters
    ----------
    input_dir : Path
        Directory containing monthly parquet files from Step 2.
    output_dir : Path
        Directory for final processed files.
    temp_dir : Path, optional
        Directory for intermediate files (cleaned, aggregated).
    metadata_file : Path, optional
        Metadata JSON for column renaming.
    modes : list of str, optional
        Consolidation modes: 'annual', 'biannual', 'quarterly'.
    drop_cols : list of str, optional
        Columns to drop during optimization.
    dtype_map : dict, optional
        Custom dtype overrides.
    overwrite : bool, optional
        Overwrite existing files.
    cleanup_temp : bool, optional
        Remove temporary directories after completion.
    logger : VerboseLogger, optional
        Logger instance.

    Examples
    --------
    >>> pipeline = ConsolidationPipeline(
    ...     input_dir=Path("data/era5-world/interim"),
    ...     output_dir=Path("data/era5-world/processed"),
    ...     metadata_file=Path("data/era5-world/interim/metadata.json"),
    ...     modes=["annual", "quarterly"]
    ... )
    >>> results = pipeline.run(use_mpi=True)
    """

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        temp_dir: Optional[Path] = None,
        metadata_file: Optional[Path] = None,
        modes: Optional[List[str]] = None,
        drop_cols: Optional[List[str]] = None,
        dtype_map: Optional[Dict[str, pl.DataType]] = None,
        overwrite: bool = True,
        cleanup_temp: bool = False,
        expected_uid: Optional[str] = None,
        logger: Optional[VerboseLogger] = None,
    ):
        from osme_common.paths import data_dir
        base = data_dir()

        self.input_dir = resolve_under(base, input_dir)
        self.output_dir = resolve_under(base, output_dir)
        self.temp_dir = resolve_under(base, temp_dir) if temp_dir else (self.input_dir.parent / "consolidation" / "temp")
        self.metadata_file = None  # Column rename disabled — keeping ERA5 shortnames
        self.modes = modes or ["annual"]
        self.drop_cols = drop_cols or DEFAULT_DROP_COLS
        self.dtype_map = dtype_map or DEFAULT_DTYPE_MAP
        self.overwrite = overwrite
        self.cleanup_temp = cleanup_temp
        self.expected_uid = expected_uid  # If set, only files with this uid are processed
        self.logger = logger or VerboseLogger("consolidation_pipeline", verbose=False)

        # Subdirectories for each stage
        # Stage 3a: trimmed monthly files (out-of-month rows removed)
        self.trimmed_dir = resolve_under(base, input_dir).parent / "consolidation" / "trimmed"
        # Stage 3b: consolidated annual/quarterly files
        self.consolidated_dir = resolve_under(base, input_dir).parent / "consolidation" / "consolidated"

    def _discover_files(self) -> Tuple[str, str, Dict[int, List[Path]]]:
        """
        Discover monthly files and group by year.

        If ``self.expected_uid`` is set (derived from the active mask config),
        only files whose uid token matches are included.  Any other files in
        the directory are silently ignored — this lets the operator keep old
        mask runs on disk without them interfering.

        Returns
        -------
        tuple
            (prefix, uid, files_by_year)
        """
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {self.input_dir}")

        files = sorted(self.input_dir.glob("*.parquet"))

        if not files:
            raise FileNotFoundError(f"No parquet files found in {self.input_dir}")

        files_by_year: Dict[int, List[Path]] = defaultdict(list)
        prefix_seen: Optional[str] = None
        uid_seen: Optional[str] = None
        skipped_uids: set = set()

        for f in files:
            try:
                p, u, year, month = parse_filename(f)
            except ValueError as e:
                self.logger.warning(f"Skipping {f.name}: {e}")
                continue

            # If caller specified which uid to use, enforce it strictly.
            if self.expected_uid is not None and u != self.expected_uid:
                skipped_uids.add(u)
                continue

            # On first accepted file, lock in prefix/uid.
            if uid_seen is None:
                prefix_seen = p
                uid_seen = u
            elif p != prefix_seen or u != uid_seen:
                # Shouldn't happen if expected_uid is set, but guard anyway.
                self.logger.warning(
                    f"Skipping {f.name}: uid mismatch (expected {uid_seen}, got {u})"
                )
                skipped_uids.add(u)
                continue

            files_by_year[year].append(f)

        if skipped_uids:
            self.logger.info(
                f"  Ignored {len(skipped_uids)} other uid(s) in {self.input_dir.name}/: "
                + ", ".join(sorted(skipped_uids))
            )

        if not files_by_year:
            if self.expected_uid:
                raise FileNotFoundError(
                    f"No files with uid='{self.expected_uid}' found in {self.input_dir}. "
                    f"Uids present: {sorted(skipped_uids) or 'none parseable'}. "
                    f"Check that --step masking has been run with the current config."
                )
            raise ValueError("No valid files found after parsing")

        # Sort each year's file list by month
        for year in files_by_year:
            files_by_year[year].sort()

        total_files = sum(len(v) for v in files_by_year.values())

        self.logger.info(f"Discovered {total_files} files across {len(files_by_year)} years")
        self.logger.info(f"  Prefix: {prefix_seen}")
        self.logger.info(f"  UID: {uid_seen}")
        self.logger.info(f"  Years: {sorted(files_by_year.keys())}")

        return prefix_seen, uid_seen, dict(files_by_year)

    def _build_global_dtype_map(
        self,
        reference_file: Path
    ) -> Dict[str, pl.DataType]:
        """Build global dtype map from reference file and overrides."""
        ref_schema = pl.read_parquet_schema(reference_file)

        global_map = build_global_dtype_map(
            reference_schema=ref_schema,
            override_map=self.dtype_map,
            drop_cols=self.drop_cols
        )

        return global_map

    def _load_metadata_rename(self) -> Dict[str, str]:
        """Column renaming is disabled — ERA5 shortnames are preserved."""
        return {}

    def _run_stage1_trim(
        self,
        files_by_year: Dict[int, List[Path]],
        my_years: List[int],
        processor: ConsolidationProcessor
    ) -> Tuple[Dict[int, List[Path]], List[OptimizationResult]]:
        """
        Stage 3a: Trim out-of-month rows and optimise each monthly file.

        ERA5 GRIB exports include a small number of rows from adjacent months
        at file boundaries (all-null values). These are stripped here using a
        strict calendar filter: only rows whose timestamp falls within the
        file's named year-month are kept.

        Returns
        -------
        tuple
            (trimmed_files_by_year, results)
        """
        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("STAGE 3a: TRIM + OPTIMISE MONTHLY FILES", force=True)
        self.logger.info("=" * 72, force=True)

        trimmed_by_year = {}
        results = []

        for year in my_years:
            monthly_files = files_by_year.get(year, [])
            self.logger.info(f"  Year {year}: {len(monthly_files)} files", force=True)
            trimmed_files = []

            for monthly_file in sorted(monthly_files):
                try:
                    _, _, file_year, file_month = parse_filename(monthly_file)
                except ValueError as e:
                    self.logger.warning(f"Skipping {monthly_file.name}: {e}")
                    continue

                trimmed_file = self.trimmed_dir / monthly_file.name

                try:
                    result = processor.optimize_file(
                        input_file=monthly_file,
                        output_file=trimmed_file,
                        overwrite=self.overwrite,
                        trim_to_month=(file_year, file_month),
                    )
                    if result:
                        results.append(result)
                        trimmed_files.append(trimmed_file)
                except Exception as e:
                    self.logger.error(f"Failed to trim {monthly_file.name}: {e}")

            trimmed_by_year[year] = trimmed_files

        return trimmed_by_year, results

    def _run_stage2_consolidate(
        self,
        trimmed_by_year: Dict[int, List[Path]],
        my_years: List[int],
        prefix: str,
        uid: str,
        processor: ConsolidationProcessor
    ) -> Tuple[Dict[int, List[Path]], List[ConsolidationResult]]:
        """
        Stage 3b: Consolidate trimmed monthly files into annual/quarterly.

        Returns
        -------
        tuple
            (aggregated_files_by_year, results)
        """
        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("STAGE 3b: CONSOLIDATING FILES", force=True)
        self.logger.info("=" * 72, force=True)

        agg_by_year = {}
        results = []

        for year in my_years:
            cleaned_files = trimmed_by_year.get(year, [])

            if not cleaned_files:
                self.logger.warning(f"No cleaned files for year {year}, skipping")
                continue

            self.logger.info(f"  Consolidating year {year}: {len(cleaned_files)} files")

            year_agg_files = []

            for mode in self.modes:
                # Determine which files to consolidate based on mode
                if mode == "annual":
                    files_to_consolidate = [cleaned_files]
                elif mode == "biannual":
                    # Split into H1 (Jan-Jun) and H2 (Jul-Dec)
                    h1_files = [f for f in cleaned_files if parse_filename(f)[3] <= 6]
                    h2_files = [f for f in cleaned_files if parse_filename(f)[3] > 6]
                    files_to_consolidate = [h1_files, h2_files] if h1_files and h2_files else []
                elif mode == "quarterly":
                    # Split into Q1-Q4
                    quarters = defaultdict(list)
                    for f in cleaned_files:
                        month = parse_filename(f)[3]
                        q = (month - 1) // 3 + 1
                        quarters[q].append(f)
                    files_to_consolidate = [quarters[q] for q in sorted(quarters.keys())]
                else:
                    self.logger.warning(f"Unknown mode: {mode}")
                    continue

                # Consolidate each group
                for group_files in files_to_consolidate:
                    if not group_files:
                        continue

                    try:
                        result = processor.consolidate_year(
                            year=year,
                            monthly_files=group_files,
                            output_dir=self.consolidated_dir,
                            prefix=prefix,
                            uid=uid,
                            mode=mode,
                            overwrite=self.overwrite
                        )

                        if result:
                            results.append(result)
                            year_agg_files.append(result.output_file)
                    except Exception as e:
                        self.logger.error(f"Failed to consolidate {year} ({mode}): {e}")

            agg_by_year[year] = year_agg_files

        return agg_by_year, results



    def _cleanup_temp_dirs(self):
        """Remove temporary directories."""
        import shutil

        self.logger.info("", force=True)
        self.logger.info("=" * 72, force=True)
        self.logger.info("CLEANING UP TEMPORARY DIRECTORIES", force=True)
        self.logger.info("=" * 72, force=True)

        for temp_dir in [self.trimmed_dir, self.consolidated_dir]:
            if temp_dir.exists():
                file_count = len(list(temp_dir.glob("*")))
                shutil.rmtree(temp_dir)
                self.logger.info(f"  Deleted {temp_dir}: {file_count} files")

    def run(
        self,
        use_mpi: bool = False
    ) -> Dict:
        """
        Execute the complete consolidation pipeline.

        Parameters
        ----------
        use_mpi : bool, optional
            Use MPI parallelization (distributes years across ranks).

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
            self.logger.info("# STEP 3: CONSOLIDATION PIPELINE", force=True)
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
            prefix, uid, files_by_year = self._discover_files()

            # Build reference file (first file)
            all_files = [f for flist in files_by_year.values() for f in flist]
            reference_file = sorted(all_files)[0]

            # Build global dtype map
            global_dtype_map = self._build_global_dtype_map(reference_file)

            # Load metadata rename map
            metadata_rename = self._load_metadata_rename()

            # Distribute years across ranks
            all_years = sorted(files_by_year.keys())
        else:
            prefix = uid = None
            files_by_year = None
            global_dtype_map = None
            metadata_rename = None
            all_years = None

        # Broadcast to all ranks
        if comm:
            prefix = comm.bcast(prefix, root=0)
            uid = comm.bcast(uid, root=0)
            files_by_year = comm.bcast(files_by_year, root=0)
            global_dtype_map = comm.bcast(global_dtype_map, root=0)
            metadata_rename = comm.bcast(metadata_rename, root=0)
            all_years = comm.bcast(all_years, root=0)

        # Assign years to this rank
        my_years = [y for i, y in enumerate(all_years) if i % size == rank]

        if rank == 0:
            self.logger.info(f"Processing {len(all_years)} years across {size} ranks")
            self.logger.info(f"  Each rank processes ~{len(all_years) // size} years")

        # ------------------------------------------------------------------
        # Create processor
        # ------------------------------------------------------------------
        processor = ConsolidationProcessor(
            global_dtype_map=global_dtype_map,
            drop_cols=self.drop_cols,
            metadata_rename=metadata_rename,
            logger=self.logger
        )

        # ------------------------------------------------------------------
        # Stage 3a: Trim + Optimise
        # ------------------------------------------------------------------
        trimmed_by_year_local, results1_local = self._run_stage1_trim(
            files_by_year, my_years, processor
        )

        # Gather results
        if comm:
            all_trimmed = comm.gather(trimmed_by_year_local, root=0)
            all_results1 = comm.gather(results1_local, root=0)
            comm.Barrier()

            if rank == 0:
                trimmed_by_year_global = {}
                for trimmed_map in all_trimmed:
                    trimmed_by_year_global.update(trimmed_map)
            else:
                trimmed_by_year_global = None

            trimmed_by_year_global = comm.bcast(trimmed_by_year_global, root=0)
        else:
            trimmed_by_year_global = trimmed_by_year_local
            all_results1 = [results1_local]

        # ------------------------------------------------------------------
        # Stage 3b: Consolidate
        # ------------------------------------------------------------------
        agg_by_year_local, results2_local = self._run_stage2_consolidate(
            trimmed_by_year_global, my_years, prefix, uid, processor
        )

        # Gather results
        if comm:
            all_agg = comm.gather(agg_by_year_local, root=0)
            all_results2 = comm.gather(results2_local, root=0)
            comm.Barrier()

            if rank == 0:
                agg_by_year_global = {}
                for agg_map in all_agg:
                    agg_by_year_global.update(agg_map)
            else:
                agg_by_year_global = None

            agg_by_year_global = comm.bcast(agg_by_year_global, root=0)
        else:
            agg_by_year_global = agg_by_year_local
            all_results2 = [results2_local]

        # Column rename stage removed — ERA5 shortnames preserved throughout.
        all_results3 = [[]]

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
            results1_flat = [r for rlist in all_results1 for r in rlist if r]
            results2_flat = [r for rlist in all_results2 for r in rlist if r]
            results3_flat = [r for rlist in all_results3 for r in rlist if r]

            self.logger.info("", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info("CONSOLIDATION PIPELINE COMPLETE", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info(f"  Total time: {dt_total:.2f}s", force=True)
            self.logger.info(f"  Files optimized: {len(results1_flat)}", force=True)
            self.logger.info(f"  Files consolidated: {len(results2_flat)}", force=True)
            self.logger.info(f"  Modes: {', '.join(self.modes)}", force=True)
            self.logger.info(f"  Trimmed files → {self.trimmed_dir}", force=True)
            self.logger.info(f"  Consolidated files → {self.consolidated_dir}", force=True)
            self.logger.info("=" * 72, force=True)
            self.logger.info("", force=True)

            return {
                "results_stage1": results1_flat,
                "results_stage2": results2_flat,
                "results_stage3": results3_flat,
                "output_dir": self.output_dir,
                "total_time_s": dt_total,
            }
        else:
            return {}