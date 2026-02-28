# packages/weather_data_processing/src/weather_data_processing/utils/validation.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Schema Validation and Data Type Management
===========================================

Utilities for validating parquet schemas, managing data types, and ensuring
data quality across the pipeline.

All variable names use ERA5 shortnames (e.g., t2m, ssr, tp).

Key Features
------------
- Schema validation against reference schemas
- Dtype casting and optimization
- Column dropping and filtering
- Schema comparison and reporting
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import polars as pl


# =============================================================================
# Default Column Configurations
# =============================================================================

# Columns to drop during consolidation (before schema enforcement)
DEFAULT_DROP_COLS = [
    "centroid_in_region",
    "cell_area_m2",
    "number",
    "step",
    "surface",
    "valid_time",
]

# Target dtypes for ERA5 variables (shortnames only) and coordinates
DEFAULT_DTYPE_MAP: Dict[str, pl.DataType] = {
    # Coordinates
    "longitude": pl.Float32,
    "latitude": pl.Float32,
    "time": pl.Datetime("us"),

    # Fractional region coverage
    "frac_in_region": pl.Float32,

    # Administrative boundaries
    "adm0_name": pl.String,
    "adm0_code": pl.String,
    "adm1_name": pl.String,
    "adm1_code": pl.String,
    "adm2_name": pl.String,
    "adm2_code": pl.String,

    # ERA5 shortnames - Temperature
    "t2m": pl.Float64,      # 2m temperature

    # ERA5 shortnames - Precipitation
    "tp": pl.Float64,       # Total precipitation

    # ERA5 shortnames - Wind components
    "u10": pl.Float64,      # 10m U wind
    "v10": pl.Float64,      # 10m V wind
    "u100": pl.Float64,     # 100m U wind
    "v100": pl.Float64,     # 100m V wind

    # ERA5 shortnames - Solar radiation
    "ssr": pl.Float64,      # Surface net solar radiation
    "ssrc": pl.Float64,     # Surface net solar radiation clear-sky
    "ssrdc": pl.Float64,    # Surface solar radiation downward clear-sky
    "ssrd": pl.Float64,     # Surface downward solar radiation
    "fdir": pl.Float64,     # Total sky direct solar radiation
    "cdir": pl.Float64,     # Clear-sky direct solar radiation

    # ERA5 shortnames - Thermal radiation
    "str": pl.Float64,      # Surface net thermal radiation
    "strc": pl.Float64,     # Surface net thermal radiation clear-sky
    "strdc": pl.Float64,    # Surface thermal radiation downward clear-sky
    "strd": pl.Float64,     # Surface downward thermal radiation

    # ERA5 shortnames - Top-of-atmosphere radiation
    "tsr": pl.Float64,      # Top net solar radiation
    "tsrc": pl.Float64,     # Top net solar radiation clear-sky
    "ttr": pl.Float64,      # Top net thermal radiation
    "ttrc": pl.Float64,     # Top net thermal radiation clear-sky

    # ERA5 shortnames - UV radiation
    "uvb": pl.Float64,      # UV biologically active

    # ERA5 shortnames - Cloud cover
    "tcc": pl.Float64,      # Total cloud cover
    "hcc": pl.Float64,      # High cloud cover
    "mcc": pl.Float64,      # Medium cloud cover
    "lcc": pl.Float64,      # Low cloud cover

    # ERA5 shortnames - Vegetation
    "cvh": pl.Float64,      # High vegetation cover
    "cvl": pl.Float64,      # Low vegetation cover
    "lai_hv": pl.Float64,   # Leaf area index (high vegetation)
    "lai_lv": pl.Float64,   # Leaf area index (low vegetation)

    # ERA5 shortnames - Other
    "kx": pl.Float64,       # K index
}


# =============================================================================
# Schema Validation Functions
# =============================================================================

def build_global_dtype_map(
    reference_schema: Dict[str, pl.DataType],
    override_map: Optional[Dict[str, pl.DataType]] = None,
    drop_cols: Optional[List[str]] = None
) -> Dict[str, pl.DataType]:
    """
    Build a global dtype map from reference schema with optional overrides.

    Parameters
    ----------
    reference_schema : dict
        Schema from a reference parquet file.
    override_map : dict, optional
        Manual dtype overrides (e.g., DEFAULT_DTYPE_MAP).
    drop_cols : list of str, optional
        Columns to exclude from the global map.

    Returns
    -------
    dict
        Global dtype map: column_name -> polars.DataType

    Examples
    --------
    >>> ref_schema = pl.read_parquet_schema("reference.parquet")
    >>> global_map = build_global_dtype_map(
    ...     ref_schema,
    ...     override_map=DEFAULT_DTYPE_MAP,
    ...     drop_cols=DEFAULT_DROP_COLS
    ... )
    """
    override_map = override_map or {}
    drop_cols = set(drop_cols or [])

    global_map = {}

    for col, dtype in reference_schema.items():
        if col in drop_cols:
            continue

        # Use override if available, otherwise use reference
        global_map[col] = override_map.get(col, dtype)

    return global_map


def validate_schema(
    df_schema: Dict[str, pl.DataType],
    expected_schema: Dict[str, pl.DataType],
    allow_extra: bool = False,
    allow_missing: bool = False
) -> Tuple[bool, List[str]]:
    """
    Validate DataFrame schema against expected schema.

    Parameters
    ----------
    df_schema : dict
        Actual schema from DataFrame.
    expected_schema : dict
        Expected schema.
    allow_extra : bool, optional
        Allow extra columns not in expected schema.
    allow_missing : bool, optional
        Allow missing columns from expected schema.

    Returns
    -------
    tuple
        (is_valid, error_messages)

    Examples
    --------
    >>> df = pl.read_parquet("data.parquet")
    >>> valid, errors = validate_schema(df.schema, expected_schema)
    >>> if not valid:
    ...     for err in errors:
    ...         print(f"ERROR: {err}")
    """
    errors = []

    df_cols = set(df_schema.keys())
    expected_cols = set(expected_schema.keys())

    # Check for missing columns
    missing = expected_cols - df_cols
    if missing and not allow_missing:
        errors.append(f"Missing columns: {sorted(missing)}")

    # Check for extra columns
    extra = df_cols - expected_cols
    if extra and not allow_extra:
        errors.append(f"Extra columns: {sorted(extra)}")

    # Check dtypes for common columns
    for col in df_cols & expected_cols:
        if df_schema[col] != expected_schema[col]:
            errors.append(
                f"Column '{col}' dtype mismatch: "
                f"got {df_schema[col]}, expected {expected_schema[col]}"
            )

    return len(errors) == 0, errors


def get_columns_to_cast(
    df_schema: Dict[str, pl.DataType],
    target_schema: Dict[str, pl.DataType]
) -> List[str]:
    """
    Identify columns that need dtype casting.

    Parameters
    ----------
    df_schema : dict
        Current DataFrame schema.
    target_schema : dict
        Target schema with desired dtypes.

    Returns
    -------
    list of str
        Column names that need casting.
    """
    to_cast = []

    for col in set(df_schema.keys()) & set(target_schema.keys()):
        if df_schema[col] != target_schema[col]:
            to_cast.append(col)

    return sorted(to_cast)


def cast_columns(
    df: pl.DataFrame | pl.LazyFrame,
    target_schema: Dict[str, pl.DataType]
) -> pl.DataFrame | pl.LazyFrame:
    """
    Cast DataFrame columns to target dtypes.

    Parameters
    ----------
    df : pl.DataFrame or pl.LazyFrame
        Input DataFrame.
    target_schema : dict
        Target schema with desired dtypes.

    Returns
    -------
    pl.DataFrame or pl.LazyFrame
        DataFrame with cast columns.

    Examples
    --------
    >>> df = pl.read_parquet("data.parquet")
    >>> df_cast = cast_columns(df, DEFAULT_DTYPE_MAP)
    """
    cast_exprs = []

    schema = df.collect_schema() if hasattr(df, 'collect_schema') else df.schema

    for col in df.columns if isinstance(df, pl.DataFrame) else schema.names():
        if col in target_schema and schema[col] != target_schema[col]:
            cast_exprs.append(pl.col(col).cast(target_schema[col]))
        else:
            cast_exprs.append(pl.col(col))

    return df.select(cast_exprs)


def drop_columns(
    df: pl.DataFrame | pl.LazyFrame,
    columns: List[str]
) -> pl.DataFrame | pl.LazyFrame:
    """
    Drop columns from DataFrame if they exist.

    Parameters
    ----------
    df : pl.DataFrame or pl.LazyFrame
        Input DataFrame.
    columns : list of str
        Columns to drop.

    Returns
    -------
    pl.DataFrame or pl.LazyFrame
        DataFrame with columns dropped.
    """
    schema = df.collect_schema() if isinstance(df, pl.LazyFrame) else df.schema
    existing_cols = schema.names() if isinstance(df, pl.LazyFrame) else list(schema.keys())

    to_drop = [col for col in columns if col in existing_cols]
    if not to_drop:
        return df

    return df.drop(to_drop)


def get_schema_diff(
    schema1: Dict[str, pl.DataType],
    schema2: Dict[str, pl.DataType]
) -> Dict[str, Tuple[Optional[pl.DataType], Optional[pl.DataType]]]:
    """
    Compare two schemas and return differences.

    Parameters
    ----------
    schema1 : dict
        First schema.
    schema2 : dict
        Second schema.

    Returns
    -------
    dict
        Dictionary mapping column name to (dtype1, dtype2) for differences.
        dtype1/dtype2 is None if column is missing from that schema.

    Examples
    --------
    >>> diff = get_schema_diff(df1.schema, df2.schema)
    >>> for col, (dt1, dt2) in diff.items():
    ...     print(f"{col}: {dt1} → {dt2}")
    """
    all_cols = set(schema1.keys()) | set(schema2.keys())

    diff = {}

    for col in sorted(all_cols):
        dt1 = schema1.get(col)
        dt2 = schema2.get(col)

        if dt1 != dt2:
            diff[col] = (dt1, dt2)

    return diff


def print_schema_summary(
    schema: Dict[str, pl.DataType],
    label: str = "Schema"
) -> None:
    """
    Print a formatted schema summary.

    Parameters
    ----------
    schema : dict
        Schema to print.
    label : str, optional
        Label for the schema.
    """
    print(f"\n{label}:")
    print("-" * 60)

    for col, dtype in sorted(schema.items()):
        print(f"  {col:<30} {dtype}")

    print(f"  Total columns: {len(schema)}")
    print("-" * 60)


def optimize_dtypes(
    df: pl.DataFrame | pl.LazyFrame,
    aggressive: bool = False
) -> pl.DataFrame | pl.LazyFrame:
    """
    Automatically optimize dtypes for memory efficiency.

    Parameters
    ----------
    df : pl.DataFrame or pl.LazyFrame
        Input DataFrame.
    aggressive : bool, optional
        Use more aggressive optimization (e.g., Float64 → Float32).

    Returns
    -------
    pl.DataFrame or pl.LazyFrame
        DataFrame with optimized dtypes.
    """
    cast_exprs = []

    schema = df.collect_schema() if hasattr(df, 'collect_schema') else df.schema

    for col, dtype in schema.items():
        new_dtype = dtype

        # Downcast floats if aggressive
        if aggressive and dtype == pl.Float64:
            new_dtype = pl.Float32

        # Categorical for low-cardinality strings
        if dtype == pl.String:
            # This would require actual data inspection
            # For now, keep as String
            pass

        if new_dtype != dtype:
            cast_exprs.append(pl.col(col).cast(new_dtype))
        else:
            cast_exprs.append(pl.col(col))

    return df.select(cast_exprs)