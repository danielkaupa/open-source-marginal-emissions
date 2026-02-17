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
    
    shapefile_adm0: str = "data/geoBoundaries/geoBoundariesCGAZ_ADM0.zip"
    shapefile_adm1: Optional[str] = "data/geoBoundaries/geoBoundariesCGAZ_ADM1.zip"
    shapefile_adm2: Optional[str] = "data/geoBoundaries/geoBoundariesCGAZ_ADM2.zip"
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
    """
    
    inclusion_mode: Literal["centroid", "intersection", "combined"] = "combined"
    fraction_threshold: float = Field(0.8, ge=0.0, le=1.0)
    dataset_prefix: str = "era5-world"
    mask_dir: str = "data/geoBoundaries/masks/era5-world"
    metadata_dir: str = "data/geoBoundaries/masks/mask_metadata"
    generate_visualization: bool = True
    image_dir: str = "data/geoBoundaries/images"


class ADMEnrichmentConfig(BaseModel):
    """
    Administrative boundary enrichment configuration.
    
    Attributes
    ----------
    enable_adm1 : bool
        Add ADM1 (state/province) columns.
    enable_adm2 : bool
        Add ADM2 (district/county) columns.
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
    
    enable_adm1: bool = True
    enable_adm2: bool = True
    adm1_name_field: str = "shapeName"
    adm2_name_field: str = "shapeName"
    adm1_code_field: Optional[str] = "shapeISO"
    adm2_code_field: Optional[str] = "shapeISO"
    undefined_value: str = "NONE_DEFINED"


class GeographicConfig(BaseModel):
    """Complete geographic processing configuration."""
    
    boundary: BoundaryConfig
    mask: MaskConfig
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


class TemporalAggregationConfig(BaseModel):
    """
    Temporal aggregation configuration.
    
    Attributes
    ----------
    modes : list of str
        Aggregation modes (e.g., ['annual', 'monthly', 'quarterly']).
    """
    
    modes: List[Literal["annual", "biannual", "quarterly", "monthly"]] = [
        "annual"
    ]


class AggregationConfig(BaseModel):
    """Complete aggregation configuration."""
    
    spatial: SpatialAggregationConfig
    temporal: TemporalAggregationConfig


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
    
    grib_dir: str = "data/era5-world/raw"
    output_base: str = "data/era5-world/processed"
    interim_dir: str = "data/era5-world/interim"
    processed_dir: str = "data/era5-world/processed"


# =============================================================================
# Master Pipeline Configuration
# =============================================================================

class PipelineConfig(BaseModel):
    """
    Master configuration for the entire weather data processing pipeline.
    
    This is the top-level schema that combines all sub-configurations.
    
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
    aggregation : AggregationConfig or None
        Aggregation settings (None skips this step).
    
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
