# packages/weather_data_processing/src/weather_data_processing/config_schema.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Configuration Schemas for Weather Data Processing
==================================================

Pydantic models for validating configuration files across all pipeline stages.

These schemas provide:
- Type validation
- Default value handling
- Clear error messages for invalid configurations
- Self-documenting configuration structure
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Exclusion Bounding Box
# =============================================================================

class ExclusionBBox(BaseModel):
    """
    Bounding box to exclude from a mask.

    Attributes
    ----------
    name : str
        Human-readable label for the exclusion zone (e.g. "andaman_nicobar").
    lon_min, lon_max : float
        Longitude bounds in degrees East.
    lat_min, lat_max : float
        Latitude bounds in degrees North.
    """

    name: str
    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float


# =============================================================================
# Parallelization Configuration
# =============================================================================

class ParallelizationConfig(BaseModel):
    """
    Parallelization settings.

    Attributes
    ----------
    mode : {'auto', 'manual'}
        Auto-detect environment or use manual worker count.
    manual_workers : int or None
        Number of workers if mode='manual'.
    prefer_mpi : bool
        Prefer MPI over multiprocessing when available.
    """

    mode: Literal["auto", "manual"] = "auto"
    manual_workers: Optional[int] = Field(None, ge=1)
    prefer_mpi: bool = True

    @field_validator("manual_workers")
    @classmethod
    def validate_manual_workers(cls, v, info):
        """Ensure manual_workers is set if mode is manual."""
        if info.data.get("mode") == "manual" and v is None:
            raise ValueError("manual_workers must be set when mode='manual'")
        return v


# =============================================================================
# Logging Configuration
# =============================================================================

class LoggingConfig(BaseModel):
    """
    Logging configuration.

    Attributes
    ----------
    verbose : bool
        Enable verbose console output.
    log_dir : str
        Directory for log files (relative to repo root or absolute).
    log_level : str
        File logging level.
    """

    verbose: bool = False
    log_dir: str = "logs/weather_data_processing"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


# =============================================================================
# Geographic Processing Configuration
# =============================================================================

class BoundaryConfig(BaseModel):
    """
    Geographic boundary configuration.

    Attributes
    ----------
    shapefile_adm0 : str
        Path to ADM0 (country-level) shapefile.
    shapefile_adm1 : str or None
        Path to ADM1 (state/province) shapefile.
    shapefile_adm2 : str or None
        Path to ADM2 (district/county) shapefile.
    country_name : str
        Country to filter (e.g., "India").
    country_field : str
        Field name in shapefile containing country names.
    """

    shapefile_adm0: str = "geoBoundaries/geoBoundariesCGAZ_ADM0.zip"
    shapefile_adm1: Optional[str] = "geoBoundaries/geoBoundariesCGAZ_ADM1.zip"
    shapefile_adm2: Optional[str] = "geoBoundaries/geoBoundariesCGAZ_ADM2.zip"
    country_name: str
    country_field: str = "shapeName"


class MaskConfig(BaseModel):
    """
    Mask generation configuration.

    Attributes
    ----------
    inclusion_mode : {'centroid', 'intersection', 'combined'}
        Method for determining grid cell inclusion.
    fraction_threshold : float
        Minimum fractional overlap for inclusion (used with 'combined' mode).
    dataset_prefix : str
        Prefix for output filenames (e.g., "era5-world").
    mask_dir : str
        Directory to save mask files.
    metadata_dir : str
        Directory to save mask metadata.
    generate_visualization : bool
        Whether to generate diagnostic plots.
    image_dir : str
        Directory for visualization outputs.
    exclusion_bboxes : list of ExclusionBBox
        Bounding boxes to exclude from the mask (e.g. remote islands).
    """

    inclusion_mode: Literal["centroid", "intersection", "combined"] = "combined"
    fraction_threshold: float = Field(0.8, ge=0.0, le=1.0)
    dataset_prefix: str = "era5-world"
    mask_dir: str = "geoBoundaries/masks/era5-world"
    metadata_dir: str = "geoBoundaries/masks/mask_metadata"
    generate_visualization: bool = True
    image_dir: str = "geoBoundaries/images"
    exclusion_bboxes: List[ExclusionBBox] = Field(default_factory=list)


class ADMEnrichmentConfig(BaseModel):
    """
    Administrative boundary enrichment configuration.

    Attributes
    ----------
    enable_adm0 : bool
        Stamp ADM0 (country-level) name/code columns (no spatial join needed).
    enable_adm1 : bool
        Add ADM1 (state/province) columns.
    enable_adm2 : bool
        Add ADM2 (district/county) columns.
    adm0_name_field : str
        Field in ADM0 shapefile for country names.
    adm0_code_field : str or None
        Field in ADM0 shapefile for ISO codes (e.g. shapeGroup for ISO3).
    adm1_name_field : str
        Field in ADM1 shapefile for names.
    adm2_name_field : str
        Field in ADM2 shapefile for names.
    adm1_code_field : str or None
        Field in ADM1 shapefile for ISO codes.
    adm2_code_field : str or None
        Field in ADM2 shapefile for ISO codes.
    undefined_value : str
        Value to use for undefined/missing boundaries.
    """

    enable_adm0: bool = True
    enable_adm1: bool = True
    enable_adm2: bool = True
    adm0_name_field: str = "shapeName"
    adm0_code_field: Optional[str] = "shapeGroup"
    adm1_name_field: str = "shapeName"
    adm2_name_field: str = "shapeName"
    adm1_code_field: Optional[str] = "shapeISO"
    adm2_code_field: Optional[str] = "shapeISO"
    undefined_value: str = "NONE_DEFINED"


class GeographicConfig(BaseModel):
    """Complete geographic processing configuration."""

    boundary: BoundaryConfig
    masks: List[MaskConfig]
    adm_enrichment: ADMEnrichmentConfig


# =============================================================================
# Temporal Processing Configuration
# =============================================================================

class InterpolationConfig(BaseModel):
    """
    Temporal interpolation configuration.

    Attributes
    ----------
    method : {'rate_shaped', 'linear', 'midpoint'}
        Interpolation method for extensive fields.
    datetime_unit : {'ns', 'us', 'ms', 's'}
        Time precision for timestamps.
    clamp_unit_range : bool
        Clamp cloud/vegetation fields to [0, 1].
    """

    method: Literal["rate_shaped", "linear", "midpoint"] = "rate_shaped"
    datetime_unit: Literal["ns", "us", "ms", "s"] = "us"
    clamp_unit_range: bool = True


class TimezoneConfig(BaseModel):
    """
    Timezone conversion configuration.

    Attributes
    ----------
    target_timezone : str
        IANA timezone name (e.g., "Asia/Kolkata").
    keep_utc_column : bool
        Retain original UTC timestamp as separate column.
    """

    target_timezone: str = "UTC"
    keep_utc_column: bool = False


class TemporalConfig(BaseModel):
    """Complete temporal processing configuration."""

    interpolation: InterpolationConfig
    timezone: TimezoneConfig


# =============================================================================
# Aggregation Configuration
# =============================================================================

class SpatialAggregationConfig(BaseModel):
    """
    Spatial aggregation configuration.

    All output is half-hourly — no temporal aggregation is performed.

    Attributes
    ----------
    level : {'ADM0', 'ADM1', 'ADM2'}
        Administrative level for aggregation.
    weight_by_area : bool
        Weight aggregation by cos(latitude).
    output_format : {'parquet', 'csv', 'both'}
        Output file format(s).
    """

    level: Literal["ADM0", "ADM1", "ADM2"] = "ADM0"
    weight_by_area: bool = True
    output_format: Literal["parquet", "csv", "both"] = "parquet"


class ConsolidationConfig(BaseModel):
    """
    File consolidation configuration for Step 3.

    Attributes
    ----------
    modes : list of str
        How to partition consolidated files ('annual', 'biannual', 'quarterly').
        This controls file organization, NOT temporal aggregation.
        All data remains at original hourly resolution until interpolation.
    """

    modes: List[Literal["annual", "biannual", "quarterly"]] = ["annual"]


class AggregationConfig(BaseModel):
    """Complete aggregation configuration (spatial only)."""

    spatial: SpatialAggregationConfig


# =============================================================================
# Data Paths Configuration
# =============================================================================

class DataPathsConfig(BaseModel):
    """
    Data input/output paths.

    Attributes
    ----------
    grib_dir : str
        Directory containing raw GRIB files.
    output_base : str
        Base directory for all outputs.
    interim_dir : str
        Directory for intermediate processing outputs.
    processed_dir : str
        Directory for final processed outputs.
    """

    grib_dir: str = "era5-world/raw"
    output_base: str = "era5-world/processed"
    interim_dir: str = "era5-world/interim"
    processed_dir: str = "era5-world/processed"


# =============================================================================
# Master Pipeline Configuration
# =============================================================================

class PipelineConfig(BaseModel):
    """
    Master configuration for the entire weather data processing pipeline.

    This is the top-level schema that combines all sub-configurations.

    All outputs are half-hourly — no temporal aggregation is performed anywhere
    in the pipeline.

    Attributes
    ----------
    parallelization : ParallelizationConfig
        Parallelization settings.
    logging : LoggingConfig
        Logging configuration.
    data_paths : DataPathsConfig
        Input/output paths.
    geographic : GeographicConfig or None
        Geographic processing settings (None skips this step).
    temporal : TemporalConfig or None
        Temporal processing settings (None skips this step).
    consolidation : ConsolidationConfig or None
        File consolidation settings for Step 3 (controls file partitioning, not
        temporal resolution).
    aggregation : AggregationConfig or None
        Spatial aggregation settings (None skips this step).

    Examples
    --------
    >>> config = PipelineConfig.model_validate_json(json_str)
    >>> print(config.geographic.boundary.country_name)
    India
    """

    parallelization: ParallelizationConfig = ParallelizationConfig()
    logging: LoggingConfig = LoggingConfig()
    data_paths: DataPathsConfig = DataPathsConfig()
    geographic: Optional[GeographicConfig] = None
    temporal: Optional[TemporalConfig] = None
    consolidation: Optional[ConsolidationConfig] = None
    aggregation: Optional[AggregationConfig] = None

    def save_to_file(self, path: Path) -> None:
        """Save configuration to JSON file."""
        path.write_text(self.model_dump_json(indent=2))

    @classmethod
    def load_from_file(cls, path: Path) -> PipelineConfig:
        """Load configuration from JSON file."""
        import json
        data = json.loads(path.read_text())
        return cls.model_validate(data)