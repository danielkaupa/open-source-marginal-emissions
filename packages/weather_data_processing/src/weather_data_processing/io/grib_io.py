# packages/weather_data_processing/src/weather_data_processing/io/grib_io.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
GRIB File I/O Utilities
========================

Functions for reading and extracting data from ERA5 GRIB files using xarray.

Key Features
------------
- Variable metadata extraction
- Grid extraction
- Multi-variable dataset loading
- Memory-efficient lazy loading
- cfgrib backend integration
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
import polars as pl
import xarray as xr
from eccodes import (
    codes_grib_new_from_file,
    codes_get,
    codes_release,
    CodesInternalError,
)


def extract_variable_metadata(grib_file: Path) -> Dict[str, Dict[str, Any]]:
    """
    Extract metadata for all variables in a GRIB file.

    Parameters
    ----------
    grib_file : Path
        Path to GRIB file.

    Returns
    -------
    dict
        Dictionary mapping paramId to metadata:
        - paramId: int
        - shortName: str
        - fullName: str (if available)

    Examples
    --------
    >>> metadata = extract_variable_metadata(Path("era5_2018-01.grib"))
    >>> print(metadata[167])
    {'paramId': 167, 'shortName': '2t', 'fullName': '2 metre temperature'}
    """
    metadata = {}

    with open(grib_file, "rb") as f:
        while True:
            try:
                gid = codes_grib_new_from_file(f)
            except CodesInternalError:
                break

            if gid is None:
                break

            try:
                param_id = codes_get(gid, "paramId")
                short_name = codes_get(gid, "shortName")

                # Try to get full name (may not always be available)
                try:
                    full_name = codes_get(gid, "name")
                except Exception:
                    full_name = short_name

                # Decode bytes if needed
                if isinstance(short_name, bytes):
                    short_name = short_name.decode("utf-8")
                if isinstance(full_name, bytes):
                    full_name = full_name.decode("utf-8")

                metadata[int(param_id)] = {
                    "paramId": int(param_id),
                    "shortName": short_name,
                    "fullName": full_name,
                }
            finally:
                codes_release(gid)

    return metadata


def load_grib_dataset(
    grib_file: Path,
    variables: Optional[List[str]] = None,
    squeeze: bool = True
) -> xr.Dataset:
    """
    Load GRIB file as xarray Dataset.

    Parameters
    ----------
    grib_file : Path
        Path to GRIB file.
    variables : list of str, optional
        If provided, only load these variables (by shortName).
        If None, load all variables.
    squeeze : bool, optional
        Squeeze singleton dimensions (default True).

    Returns
    -------
    xr.Dataset
        Loaded dataset with all requested variables.

    Examples
    --------
    >>> ds = load_grib_dataset(
    ...     Path("era5_2018-01.grib"),
    ...     variables=["2t", "tp"]
    ... )
    >>> print(ds.data_vars)
    """
    if variables is None:
        # Load all variables
        ds = xr.open_dataset(
            grib_file,
            engine="cfgrib",
            backend_kwargs={"indexpath": ""}
        )
    else:
        # Load specific variables
        datasets = []
        for var in variables:
            try:
                ds_var = xr.open_dataset(
                    grib_file,
                    engine="cfgrib",
                    backend_kwargs={
                        "indexpath": "",
                        "filter_by_keys": {"shortName": var}
                    }
                )
                datasets.append(ds_var)
            except Exception:
                # Variable not in file, skip
                continue

        if not datasets:
            raise ValueError(f"None of the requested variables found in {grib_file}")

        # Merge all variables
        ds = xr.merge(datasets)

    if squeeze:
        ds = ds.squeeze(drop=True)

    return ds


def extract_grid_coordinates(
    grib_file: Path,
    sample_variable: Optional[str] = None
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extract latitude and longitude grid from a GRIB file.

    Parameters
    ----------
    grib_file : Path
        Path to GRIB file.
    sample_variable : str, optional
        Variable to use for extracting grid. If None, uses first available.

    Returns
    -------
    tuple of ndarray
        (latitudes, longitudes) as 1D arrays.

    Examples
    --------
    >>> lats, lons = extract_grid_coordinates(Path("era5_2018-01.grib"))
    >>> print(f"Grid: {len(lats)} x {len(lons)}")
    """
    if sample_variable:
        ds = xr.open_dataset(
            grib_file,
            engine="cfgrib",
            backend_kwargs={
                "indexpath": "",
                "filter_by_keys": {"shortName": sample_variable}
            }
        )
    else:
        ds = xr.open_dataset(
            grib_file,
            engine="cfgrib",
            backend_kwargs={"indexpath": ""}
        )

    lats = ds["latitude"].values
    lons = ds["longitude"].values

    ds.close()

    return lats, lons


def grib_to_dataframe(
    ds: xr.Dataset,
    mask: Optional[pl.DataFrame] = None,
    timestamp: Optional[Any] = None
) -> pl.DataFrame:
    """
    Convert xarray Dataset to Polars DataFrame, optionally applying a spatial mask.

    Parameters
    ----------
    ds : xr.Dataset
        Input dataset (should have lat, lon, and data variables).
    mask : pl.DataFrame, optional
        Spatial mask with 'latitude' and 'longitude' columns.
        Only grid cells in the mask will be retained.
    timestamp : datetime-like, optional
        Timestamp to assign to the 'time' column.

    Returns
    -------
    pl.DataFrame
        DataFrame with columns: latitude, longitude, time, and all data variables.

    Examples
    --------
    >>> ds = load_grib_dataset(grib_file)
    >>> mask = pl.read_parquet("mask.parquet")
    >>> df = grib_to_dataframe(ds, mask=mask, timestamp=pd.Timestamp("2018-01-01 00:00"))
    """
    # Extract coordinates
    if "latitude" in ds.dims:
        lats = ds["latitude"].values
        lons = ds["longitude"].values
    else:
        # Handle broadcasted grids
        lon2d, lat2d = xr.broadcast(ds["longitude"], ds["latitude"])
        lats = lat2d.values.ravel()
        lons = lon2d.values.ravel()

    # Create coordinate grid
    if lats.ndim == 1 and lons.ndim == 1:
        # Regular grid
        lon_grid, lat_grid = np.meshgrid(lons, lats)
        lats_flat = lat_grid.ravel()
        lons_flat = lon_grid.ravel()
    else:
        # Already flattened
        lats_flat = lats.ravel()
        lons_flat = lons.ravel()

    # Build DataFrame
    data_dict = {
        "latitude": lats_flat,
        "longitude": lons_flat,
    }

    # Add timestamp if provided
    if timestamp is not None:
        data_dict["time"] = [timestamp] * len(lats_flat)

    # Extract data variables
    for var_name in ds.data_vars:
        var_data = ds[var_name].values

        # Handle different dimensionalities
        if var_data.ndim == 0:
            # Scalar
            data_dict[var_name] = [float(var_data)] * len(lats_flat)
        elif var_data.ndim == 1:
            # 1D - broadcast
            data_dict[var_name] = np.repeat(var_data, len(lats_flat) // len(var_data))
        elif var_data.ndim == 2:
            # 2D - flatten
            data_dict[var_name] = var_data.ravel()
        else:
            # Higher dimensions - take first time slice if needed
            data_dict[var_name] = var_data.reshape(-1, var_data.shape[-1]).ravel()

    df = pl.DataFrame(data_dict)

    # Apply mask if provided
    if mask is not None:
        df = df.join(
            mask.select(["latitude", "longitude"]),
            on=["latitude", "longitude"],
            how="inner"
        )

        # Add frac_in_region if available in mask
        if "frac_in_region" in mask.columns:
            mask_fracs = mask.select(["latitude", "longitude", "frac_in_region"])
            df = df.join(mask_fracs, on=["latitude", "longitude"], how="left")

    return df


def estimate_grib_size_mb(grib_file: Path) -> float:
    """
    Estimate GRIB file size in megabytes.

    Parameters
    ----------
    grib_file : Path
        Path to GRIB file.

    Returns
    -------
    float
        File size in MB.
    """
    size_bytes = grib_file.stat().st_size
    return size_bytes / (1024 ** 2)


def count_messages_in_grib(grib_file: Path) -> int:
    """
    Count the number of GRIB messages in a file.

    Parameters
    ----------
    grib_file : Path
        Path to GRIB file.

    Returns
    -------
    int
        Number of GRIB messages.
    """
    count = 0
    with open(grib_file, "rb") as f:
        while True:
            try:
                gid = codes_grib_new_from_file(f)
            except CodesInternalError:
                break

            if gid is None:
                break

            count += 1
            codes_release(gid)

    return count
