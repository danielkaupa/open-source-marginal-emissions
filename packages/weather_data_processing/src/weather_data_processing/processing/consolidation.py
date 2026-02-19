# packages/weather_data_processing/src/weather_data_processing/processing/consolidation.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Data Consolidation Processor
=============================

Optimize, consolidate, and rename parquet files from Step 2.

Three-stage processing:
1. **Optimize**: Filter timestamps, drop columns, cast dtypes, write cleaned files
2. **Consolidate**: Combine monthly files into annual/biannual/quarterly files
3. **Rename**: Apply metadata-based column renaming

This module wraps the logic from step3a_optimise_and_consolidate.py with
improved integration and configuration management.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Literal

import polars as pl

from ..utils.validation import (
    build_global_dtype_map,
    validate_schema,
    cast_columns,
    drop_columns,
    DEFAULT_DROP_COLS,
    DEFAULT_DTYPE_MAP,
)
from ..utils.logging import VerboseLogger


# =============================================================================
# Filename Parsing
# =============================================================================

# Matches: era5-world_INDIA_d514a3a3c256_2025_06.parquet
FNAME_RE = re.compile(
    r"^(?P<prefix>[^_]+_[^_]+)_"      # era5-world_INDIA
    r"(?P<uid>[A-Za-z0-9]+)_"         # d514a3a3c256
    r"(?P<year>\d{4})_"               # 2025
    r"(?P<month>\d{2})\.parquet$"     # 06.parquet
)


def parse_filename(path: Path) -> Tuple[str, str, int, int]:
    """
    Parse filename to extract prefix, UID, year, month.

    Parameters
    ----------
    path : Path
        Path to parquet file.

    Returns
    -------
    tuple
        (prefix, uid, year, month)

    Raises
    ------
    ValueError
        If filename doesn't match expected pattern.

    Examples
    --------
    >>> prefix, uid, year, month = parse_filename(
    ...     Path("era5-world_INDIA_d514a3a3c256_2025_06.parquet")
    ... )
    >>> print(year, month)
    2025 6
    """
    m = FNAME_RE.match(path.name)
    if not m:
        raise ValueError(f"Filename not recognized: {path.name}")

    return (
        m.group("prefix"),
        m.group("uid"),
        int(m.group("year")),
        int(m.group("month")),
    )


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class OptimizationResult:
    """Result of file optimization."""
    input_file: Path
    output_file: Path
    rows_before: int
    rows_after: int
    columns_dropped: List[str]
    columns_cast: List[str]
    processing_time_s: float


@dataclass
class ConsolidationResult:
    """Result of file consolidation."""
    output_file: Path
    mode: str
    year: int
    input_files: List[Path]
    total_rows: int
    processing_time_s: float


@dataclass
class RenamingResult:
    """Result of column renaming."""
    input_file: Path
    output_file: Path
    columns_renamed: Dict[str, str]
    processing_time_s: float


# =============================================================================
# Consolidation Processor
# =============================================================================

class ConsolidationProcessor:
    """
    Three-stage consolidation processor.

    Parameters
    ----------
    global_dtype_map : dict
        Global schema with target dtypes.
    drop_cols : list of str, optional
        Columns to drop during optimization.
    metadata_rename : dict, optional
        Column rename map from metadata (shortName → datasetProcessingName).
    logger : VerboseLogger, optional
        Logger instance.

    Examples
    --------
    >>> processor = ConsolidationProcessor(
    ...     global_dtype_map=global_map,
    ...     drop_cols=DEFAULT_DROP_COLS,
    ...     metadata_rename=rename_map
    ... )
    >>>
    >>> # Stage 1: Optimize
    >>> result = processor.optimize_file(input_file, output_file)
    >>>
    >>> # Stage 2: Consolidate
    >>> result = processor.consolidate_year(
    ...     year=2018,
    ...     monthly_files=files,
    ...     output_dir=output_dir,
    ...     mode="annual"
    ... )
    >>>
    >>> # Stage 3: Rename
    >>> result = processor.rename_file(input_file, output_file)
    """

    def __init__(
        self,
        global_dtype_map: Dict[str, pl.DataType],
        drop_cols: Optional[List[str]] = None,
        metadata_rename: Optional[Dict[str, str]] = None,
        logger: Optional[VerboseLogger] = None,
    ):
        self.global_dtype_map = global_dtype_map
        self.drop_cols = drop_cols or DEFAULT_DROP_COLS
        self.metadata_rename = metadata_rename or {}
        self.logger = logger or VerboseLogger("consolidation", verbose=False)

    # -------------------------------------------------------------------------
    # Stage 1: Optimize
    # -------------------------------------------------------------------------

    def optimize_file(
        self,
        input_file: Path,
        output_file: Path,
        overwrite: bool = True
    ) -> OptimizationResult:
        """
        Optimize a single parquet file: filter, drop, cast, save.

        Parameters
        ----------
        input_file : Path
            Input parquet file from Step 2.
        output_file : Path
            Output cleaned parquet file.
        overwrite : bool, optional
            Overwrite existing output file.

        Returns
        -------
        OptimizationResult
            Processing result with statistics.
        """
        t0 = time.perf_counter()

        if output_file.exists() and not overwrite:
            self.logger.debug(f"Skipping {output_file.name} (exists)")
            return None

        self.logger.debug(f"Optimizing {input_file.name}")

        # Load file
        df = pl.scan_parquet(input_file)

        rows_before = df.select(pl.len()).collect().item()

        # Step 1: Filter timestamps if needed
        # (Assuming timestamps are already valid from Step 2)

        # Step 2: Drop unwanted columns
        cols_before_drop = df.collect_schema().names()
        df = drop_columns(df, self.drop_cols)
        cols_after_drop = df.collect_schema().names()

        dropped_cols = sorted(set(cols_before_drop) - set(cols_after_drop))

        # Step 3: Validate schema
        current_schema = df.collect_schema()
        expected_cols = set(self.global_dtype_map.keys())
        actual_cols = set(current_schema.names())

        # Allow extra columns from Step 2 (like ADM columns)
        # but ensure all expected columns are present
        missing_cols = expected_cols - actual_cols
        if missing_cols:
            raise ValueError(
                f"Missing required columns in {input_file.name}: {missing_cols}"
            )

        # Step 4: Cast columns
        df_cast = cast_columns(df, self.global_dtype_map)

        cast_schema = df_cast.collect_schema()
        cast_cols = [
            col for col in current_schema.names()
            if col in self.global_dtype_map
            and current_schema[col] != self.global_dtype_map[col]
        ]

        # Step 5: Sort columns (consistent ordering)
        # Put standard columns first, then extras (like ADM)
        standard_cols = sorted(set(cols_after_drop) & expected_cols)
        extra_cols = sorted(set(cols_after_drop) - expected_cols)
        ordered_cols = standard_cols + extra_cols

        df_final = df_cast.select(ordered_cols)

        # Collect and write
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df_final.collect().write_parquet(
            output_file,
            compression="zstd",
            statistics=True
        )

        rows_after = rows_before  # No row filtering in current implementation

        dt = time.perf_counter() - t0

        self.logger.debug(
            f"  Optimized: {input_file.name} → {output_file.name} "
            f"({rows_after:,} rows, {dt:.2f}s)"
        )

        return OptimizationResult(
            input_file=input_file,
            output_file=output_file,
            rows_before=rows_before,
            rows_after=rows_after,
            columns_dropped=dropped_cols,
            columns_cast=cast_cols,
            processing_time_s=dt,
        )

    # -------------------------------------------------------------------------
    # Stage 2: Consolidate
    # -------------------------------------------------------------------------

    def consolidate_year(
        self,
        year: int,
        monthly_files: List[Path],
        output_dir: Path,
        prefix: str,
        uid: str,
        mode: Literal["annual", "biannual", "quarterly"] = "annual",
        overwrite: bool = True
    ) -> ConsolidationResult:
        """
        Consolidate monthly files for a year into annual/biannual/quarterly file.

        Parameters
        ----------
        year : int
            Year to consolidate.
        monthly_files : list of Path
            List of monthly parquet files for this year.
        output_dir : Path
            Output directory.
        prefix : str
            Dataset prefix (e.g., "era5-world_INDIA").
        uid : str
            Dataset UID (e.g., "d514a3a3c256").
        mode : {'annual', 'biannual', 'quarterly'}
            Consolidation mode.
        overwrite : bool, optional
            Overwrite existing output file.

        Returns
        -------
        ConsolidationResult
            Processing result.
        """
        t0 = time.perf_counter()

        # Build output filename
        if mode == "annual":
            output_name = f"{prefix}_{uid}_{year}.parquet"
        elif mode == "biannual":
            # Determine which half
            months = [parse_filename(f)[3] for f in monthly_files]
            if any(m <= 6 for m in months):
                output_name = f"{prefix}_{uid}_{year}_H1.parquet"
            else:
                output_name = f"{prefix}_{uid}_{year}_H2.parquet"
        elif mode == "quarterly":
            # Determine which quarter
            months = [parse_filename(f)[3] for f in monthly_files]
            avg_month = sum(months) / len(months)
            if avg_month <= 3:
                q = "Q1"
            elif avg_month <= 6:
                q = "Q2"
            elif avg_month <= 9:
                q = "Q3"
            else:
                q = "Q4"
            output_name = f"{prefix}_{uid}_{year}_{q}.parquet"
        else:
            raise ValueError(f"Unknown mode: {mode}")

        output_file = output_dir / output_name

        if output_file.exists() and not overwrite:
            self.logger.debug(f"Skipping {output_name} (exists)")
            return None

        self.logger.debug(f"Consolidating {year} ({mode}): {len(monthly_files)} files")

        # Read and concatenate
        dfs = [pl.scan_parquet(f) for f in sorted(monthly_files)]
        df_concat = pl.concat(dfs)

        # Ensure consistent column order
        schema = df_concat.collect_schema()
        standard_cols = sorted(set(schema.names()) & set(self.global_dtype_map.keys()))
        extra_cols = sorted(set(schema.names()) - set(self.global_dtype_map.keys()))
        ordered_cols = standard_cols + extra_cols

        df_final = df_concat.select(ordered_cols)

        # Collect and write
        output_dir.mkdir(parents=True, exist_ok=True)
        df_collected = df_final.collect()

        df_collected.write_parquet(
            output_file,
            compression="zstd",
            statistics=True
        )

        total_rows = len(df_collected)

        dt = time.perf_counter() - t0

        self.logger.debug(
            f"  Consolidated: {output_name} ({total_rows:,} rows, {dt:.2f}s)"
        )

        return ConsolidationResult(
            output_file=output_file,
            mode=mode,
            year=year,
            input_files=monthly_files,
            total_rows=total_rows,
            processing_time_s=dt,
        )

    # -------------------------------------------------------------------------
    # Stage 3: Rename
    # -------------------------------------------------------------------------

    def rename_file(
        self,
        input_file: Path,
        output_file: Path,
        overwrite: bool = True
    ) -> RenamingResult:
        """
        Rename columns using metadata mapping.

        Parameters
        ----------
        input_file : Path
            Input parquet file (from Stage 2).
        output_file : Path
            Output parquet file with renamed columns.
        overwrite : bool, optional
            Overwrite existing output file.

        Returns
        -------
        RenamingResult
            Processing result.
        """
        t0 = time.perf_counter()

        if output_file.exists() and not overwrite:
            self.logger.debug(f"Skipping {output_file.name} (exists)")
            return None

        self.logger.debug(f"Renaming columns: {input_file.name}")

        # Load file
        df = pl.read_parquet(input_file)

        # Build rename map (only for columns that exist)
        actual_rename = {
            old: new
            for old, new in self.metadata_rename.items()
            if old in df.columns and old != new
        }

        if not actual_rename:
            # No renaming needed, just copy
            self.logger.debug("  No columns to rename")
            df.write_parquet(output_file, compression="zstd", statistics=True)
        else:
            # Apply renaming
            df_renamed = df.rename(actual_rename)

            # Write
            output_file.parent.mkdir(parents=True, exist_ok=True)
            df_renamed.write_parquet(
                output_file,
                compression="zstd",
                statistics=True
            )

        dt = time.perf_counter() - t0

        self.logger.debug(
            f"  Renamed: {input_file.name} → {output_file.name} "
            f"({len(actual_rename)} columns, {dt:.2f}s)"
        )

        return RenamingResult(
            input_file=input_file,
            output_file=output_file,
            columns_renamed=actual_rename,
            processing_time_s=dt,
        )


# =============================================================================
# Metadata Utilities
# =============================================================================

def load_metadata_rename_map(metadata_file: Path) -> Dict[str, str]:
    """
    Load column rename map from metadata JSON.

    Parameters
    ----------
    metadata_file : Path
        Path to metadata JSON file.

    Returns
    -------
    dict
        Rename map: shortName → datasetProcessingName

    Examples
    --------
    >>> rename_map = load_metadata_rename_map(Path("metadata.json"))
    >>> print(rename_map["2t"])
    temperature_2m
    """
    if not metadata_file.exists():
        raise FileNotFoundError(f"Metadata file not found: {metadata_file}")

    with open(metadata_file, "r") as f:
        metadata = json.load(f)

    # Extract rename map from metadata
    rename_map = {}

    # Metadata structure varies, adapt based on your actual format
    # Example: metadata["variables"][shortName]["datasetProcessingName"]
    if "variables" in metadata:
        for short_name, var_info in metadata["variables"].items():
            if "datasetProcessingName" in var_info:
                proc_name = var_info["datasetProcessingName"]
                if proc_name and proc_name != short_name:
                    rename_map[short_name] = proc_name

    return rename_map
