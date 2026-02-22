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


def _open_single_variable(grib_file: Path, shortname: str) -> xr.Dataset:
    """
    Open one variable from a GRIB file via cfgrib, correctly flattening
    forecast-style (time, step, valid_time) to a plain time dimension.

    This mirrors the reference implementation in step2a_mask_and_process_grib.py
    and is the only safe way to load ERA5 variables that may have a step
    dimension (e.g. accumulated fields or UV indices).

    Parameters
    ----------
    grib_file : Path
    shortname : str

    Returns
    -------
    xr.Dataset with dims (time, latitude, longitude)
    """
    import warnings
    import pandas as pd

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning)
        ds = xr.open_dataset(
            grib_file,
            engine="cfgrib",
            backend_kwargs={
                "indexpath": "",
                "filter_by_keys": {"shortName": shortname},
            },
        )

    # Forecast-style: (time, step) → flatten to a single time axis using valid_time
    if "step" in ds.dims and "valid_time" in ds.coords:
        other_dims = [d for d in ds.dims if d not in ("time", "step")]
        stacked = ds.stack(time_step=("time", "step"))
        flat_time = pd.to_datetime(stacked["valid_time"].values.ravel())

        vars_out = {}
        for var_name, da in stacked.data_vars.items():
            data = da.transpose("time_step", *other_dims).values
            vars_out[var_name] = (["time", *other_dims], data)

        coords = {"time": flat_time}
        for dim in other_dims:
            coords[dim] = ds[dim]

        out = xr.Dataset(vars_out, coords=coords)
        ds.close()
        return out

    # Analysis-style: ensure time is pandas DatetimeIndex
    if "time" in ds.coords:
        ds = ds.assign_coords(time=pd.to_datetime(ds["time"].values))

    return ds


def load_grib_dataset(
    grib_file: Path,
    variables: Optional[List[str]] = None,
    squeeze: bool = True,
) -> xr.Dataset:
    """
    Load GRIB file as xarray Dataset.

    Each variable is opened separately via ``filter_by_keys`` (which is the
    only reliable way to handle ERA5 files that mix instantaneous and
    forecast/accumulated fields with different time axes). The resulting
    per-variable datasets are then merged.

    Parameters
    ----------
    grib_file : Path
        Path to GRIB file.
    variables : list of str, optional
        Specific shortNames to load.  If ``None``, all variables found in
        the file are loaded (discovered via eccodes scan).
    squeeze : bool, optional
        Squeeze singleton dimensions after loading (default True).

    Returns
    -------
    xr.Dataset
        Merged dataset with all requested variables sharing a common
        (time, latitude, longitude) structure.

    Examples
    --------
    >>> ds = load_grib_dataset(Path("era5_2018-01.grib"))
    >>> print(list(ds.data_vars))
    """
    if variables is None:
        # Discover all shortNames present in the file
        meta = extract_variable_metadata(grib_file)
        variables = sorted({v["shortName"] for v in meta.values()})

    datasets = []
    skipped = []
    for shortname in variables:
        try:
            ds_var = _open_single_variable(grib_file, shortname)
            datasets.append(ds_var)
        except Exception as e:
            skipped.append((shortname, str(e)))

    if skipped:
        import warnings
        for sn, reason in skipped:
            warnings.warn(
                f"load_grib_dataset: skipping '{sn}' from {grib_file.name}: {reason}",
                stacklevel=2,
            )

    if not datasets:
        raise ValueError(f"No variables could be loaded from {grib_file}")

    if len(datasets) == 1:
        ds = datasets[0]
    else:
        ds = xr.merge(
            datasets,
            combine_attrs="override",
            compat="override",
            join="outer",
        )
        for d in datasets:
            d.close()

    # Note: do NOT squeeze here. Squeezing can collapse the time dimension
    # on single-timestep files, turning (time, lat, lon) → (lat, lon) and
    # making ds.to_dataframe() produce a flat table with no time index.
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

    n_cells = len(lats_flat)

    # Extract data variables — skip any whose shape is inconsistent with the
    # spatial grid (e.g. 6-hourly accumulated fields mixed into a mostly
    # hourly dataset after cfgrib merging).
    skipped_vars = []
    for var_name in ds.data_vars:
        var_data = ds[var_name].values

        # Handle different dimensionalities
        if var_data.ndim == 0:
            # Scalar — broadcast to all cells
            data_dict[var_name] = [float(var_data)] * n_cells

        elif var_data.ndim == 1:
            if len(var_data) == n_cells:
                data_dict[var_name] = var_data
            else:
                skipped_vars.append((var_name, var_data.shape, "1D length mismatch"))

        elif var_data.ndim == 2:
            flat = var_data.ravel()
            if len(flat) == n_cells:
                data_dict[var_name] = flat
            else:
                skipped_vars.append((var_name, var_data.shape, "2D flat length mismatch"))

        else:
            # ≥3D: the last two dims should be (lat, lon), first dim(s) are time/level.
            # Take only the slice that matches the spatial grid.
            spatial_size = var_data.shape[-2] * var_data.shape[-1]
            if spatial_size == n_cells:
                # Reshape to (n_time_levels, n_cells) and take first slice
                data_dict[var_name] = var_data.reshape(-1, spatial_size)[0]
            else:
                skipped_vars.append((var_name, var_data.shape, "3D+ spatial mismatch"))

    if skipped_vars:
        import warnings
        for vname, vshape, reason in skipped_vars:
            warnings.warn(
                f"grib_to_dataframe: skipping variable '{vname}' "
                f"(shape={vshape}, reason={reason}, grid_cells={n_cells})",
                stacklevel=2,
            )

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