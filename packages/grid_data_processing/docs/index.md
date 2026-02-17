# Grid Data Processing

Welcome to the Grid Data Processing pipeline documentation. This package processes Indian national grid electricity data from raw monthly files into cleaned, validated, half-hourly time series.

## What This Package Does

The Grid Data Processing pipeline handles the complete workflow for transforming raw electricity grid data into analysis-ready format. Starting from monthly parquet files containing five-minute resolution measurements, the pipeline combines files, fills gaps intelligently, aggregates to half-hourly intervals, and applies proper timezone labeling.

The most sophisticated component is the progressive gap-filling system, which uses domain knowledge about electricity demand patterns to fill missing data in a way that preserves realistic temporal dynamics. Rather than using simple linear interpolation everywhere (which creates unrealistic straight lines through periods that should show natural cycles), the pipeline employs a multi-stage strategy that progressively tackles harder gaps as the dataset becomes cleaner.

## Key Features

- **Automatic File Combination**: Merges monthly parquet files with proper sorting and deduplication
- **Progressive Gap Filling**: Multi-stage approach using linear interpolation for short gaps and gradient-based donor day matching for long gaps
- **Temporal Aggregation**: Converts five-minute data to half-hourly using appropriate statistical methods (mean for rates, sum for totals)
- **Timezone Management**: Properly labels timestamps with Asia/Kolkata timezone
- **Comprehensive Validation**: Ensures output quality with detailed checks and reporting
- **Production-Ready Logging**: Complete audit trail in files, optional console output
- **Smart Path Resolution**: Integrates with osme_common for automatic config and data directory detection

## Quick Navigation

- **[Quickstart Guide](quickstart.md)** - Get up and running in minutes
- **[Codebase Reference](codebase.md)** - Detailed API documentation for all modules

## Installation
```bash
cd packages/grid_data_processing
pip install -e .
```

This creates command-line tools: `gdp`, `griddataprocessing`, `gridprocessing`, and `gridproc` (all equivalent).

## Basic Usage

Process monthly files with default settings:
```bash
gdp --monthly-dir grid_data/raw/monthly
```

Process with verbose output to see progress:
```bash
gdp --monthly-dir grid_data/raw/monthly --verbose
```

Keep intermediate files for analysis:
```bash
gdp --monthly-dir grid_data/raw/monthly --keep-intermediate --verbose
```

## Architecture Overview

The pipeline is organized into several modules:

- **main.py**: GridDataProcessor orchestrator that coordinates the entire workflow
- **gap_filling.py**: Progressive gap-filling implementation with linear and gradient methods
- **io/**: Configuration loading and file management utilities
- **pipeline/**: Individual processing steps (combine, gap fill, aggregate, timezone)
- **utils/**: Logging and validation utilities

The design emphasizes separation of concerns, with reusable algorithms in dedicated modules and pipeline orchestration logic kept separate.

## Next Steps

New users should start with the [Quickstart Guide](quickstart.md) for a hands-on introduction. Developers extending the pipeline should review the [Codebase Reference](codebase.md) for detailed API documentation.