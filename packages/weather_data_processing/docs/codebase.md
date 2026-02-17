# Codebase Reference

This document provides comprehensive API documentation for all modules in the grid_data_processing package.

## Main Orchestrator

::: grid_data_processing.main.GridDataProcessor
    options:
      show_source: false
      heading_level: 3

## Gap Filling Module

The gap_filling module implements the progressive gap-filling algorithm that is the heart of this pipeline.

::: grid_data_processing.gap_filling.fill_all_gaps_progressive
    options:
      show_source: false
      heading_level: 3

::: grid_data_processing.gap_filling.fill_long_gaps_by_gradient
    options:
      show_source: false
      heading_level: 3

::: grid_data_processing.gap_filling.fill_short_gaps_linear
    options:
      show_source: false
      heading_level: 3

## Input/Output Utilities

### Configuration Loader

::: grid_data_processing.io.config_loader
    options:
      show_source: false
      heading_level: 4

### File Handler

::: grid_data_processing.io.file_handler.FileHandler
    options:
      show_source: false
      heading_level: 4

::: grid_data_processing.io.file_handler.detect_date_range_from_monthly
    options:
      show_source: false
      heading_level: 4

## Pipeline Steps

### Step 1: Combine Monthly Files

::: grid_data_processing.pipeline.step1_combine_monthly.combine_monthly_files
    options:
      show_source: false
      heading_level: 4

### Step 2: Gap Filling

::: grid_data_processing.pipeline.step2_gap_filling.fill_all_gaps
    options:
      show_source: false
      heading_level: 4

### Step 3: Temporal Aggregation

::: grid_data_processing.pipeline.step3_temporal_aggregation.aggregate_to_half_hourly
    options:
      show_source: false
      heading_level: 4

### Step 4: Timezone Setting

::: grid_data_processing.pipeline.step4_timezone.set_timezone
    options:
      show_source: false
      heading_level: 4

## Utilities

### Logging

::: grid_data_processing.utils.logging.setup_logging
    options:
      show_source: false
      heading_level: 4

### Validation

::: grid_data_processing.utils.validation.validate_processed_data
    options:
      show_source: false
      heading_level: 4

::: grid_data_processing.utils.validation.validate_config_compatibility
    options:
      show_source: false
      heading_level: 4