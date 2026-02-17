# Weather Data Processing Module

**Production-ready pipeline for processing ERA5 gridded weather data with geographic masking, temporal interpolation, and administrative boundary enrichment.**

---

## Overview

This module transforms raw ERA5 GRIB files into analysis-ready datasets through a series of automated processing steps:

1. **Geographic Processing**: Filter data to specific countries and add administrative boundaries
2. **Temporal Processing**: Interpolate hourly data to half-hourly resolution
3. **Aggregation**: Compute national/regional averages and time-series

### Key Features

✅ **Auto-detection of compute environment** (local, PBS, SLURM, MPI)  
✅ **Geographic mask generation** with multiple inclusion modes  
✅ **ADM1/ADM2 boundary enrichment** for hierarchical aggregation  
✅ **Energy-conserving interpolation** for radiation fields  
✅ **Year-boundary handling** for continuous time-series  
✅ **Audit trail** with diagnostic visualizations  
✅ **HPC-ready** with MPI parallelization support  

---

## Architecture

```
weather_data_processing/
├── config_schema.py          # Pydantic configuration schemas
├── pipeline/
│   ├── step1_geographic.py   # Country masking + ADM setup
│   ├── step2_masking.py      # Apply mask to GRIB files
│   ├── step3_consolidation.py # Optimize & consolidate
│   ├── step4_temporal.py     # Half-hourly interpolation
│   └── step5_aggregation.py  # Spatial/temporal aggregation
├── processing/
│   ├── mask_builder.py       # Geographic mask generation
│   ├── admin_enrichment.py   # ADM1/ADM2 column addition
│   ├── interpolation.py      # Temporal downsampling
│   └── aggregation.py        # Aggregation logic
├── io/
│   ├── grib_io.py           # xarray GRIB operations
│   ├── parquet_io.py        # Polars operations
│   └── boundary_io.py       # Shapefile handling
└── utils/
    ├── parallel.py          # Compute environment auto-detection
    ├── logging.py           # Verbose/quiet logging
    ├── validation.py        # Data validation
    └── visualization.py     # Diagnostic plots
```

---

## Configuration

### Example Configuration

```json
{
  "parallelization": {
    "mode": "auto",              // Auto-detect or manual
    "prefer_mpi": true           // Use MPI when available
  },
  "logging": {
    "verbose": false,            // Console verbosity
    "log_level": "INFO"
  },
  "geographic": {
    "boundary": {
      "shapefile_adm0": "data/geoBoundaries/geoBoundariesCGAZ_ADM0.zip",
      "country_name": "India",
      "country_field": "shapeName"
    },
    "mask": {
      "inclusion_mode": "combined",
      "fraction_threshold": 0.8
    },
    "adm_enrichment": {
      "enable_adm1": true,
      "enable_adm2": true
    }
  }
}
```

### Configuration Schema

All configuration is validated using **Pydantic** models in `config_schema.py`. This provides:

- Type checking
- Default values
- Clear error messages
- Self-documenting structure

---

## Usage

### Step 1: Geographic Processing

```python
from pathlib import Path
from weather_data_processing.config_schema import GeographicConfig, PipelineConfig
from weather_data_processing.pipeline.step1_geographic import GeographicPipeline

# Load configuration
config = PipelineConfig.load_from_file(Path("configs/pipeline_config.json"))

# Run geographic pipeline
pipeline = GeographicPipeline(
    config=config.geographic,
    data_dir=Path("data")
)

result = pipeline.run(grib_dir=Path("data/era5-world/raw"))

print(f"Boundary: {result['boundary_file']}")
print(f"Mask: {result['mask_result'].mask_file}")
print(f"Grid cells: {result['mask_result'].row_count:,}")
```

**Outputs:**
- `data/geoBoundaries/extracted/{country}.geojson` - Extracted boundary
- `data/geoBoundaries/masks/era5-world/era5-world_{COUNTRY}_mask_*.parquet` - Spatial mask
- `data/geoBoundaries/masks/mask_metadata/era5-world_{COUNTRY}_mask_*.json` - Metadata
- `data/geoBoundaries/images/era5-world_{COUNTRY}_mask_*.png` - Visualization

---

## Administrative Boundary Enrichment (NEW)

The pipeline now supports hierarchical administrative boundaries:

### How It Works

1. **Filter at ADM0**: Data outside the country is discarded
2. **Enrich with ADM1/ADM2**: Each (lat, lon) pair is assigned administrative codes

### Example

```python
from weather_data_processing.processing.admin_enrichment import ADMEnricher

# Configure enrichment
enricher = ADMEnricher(
    config=config.geographic.adm_enrichment,
    adm1_shapefile=Path("data/geoBoundaries/geoBoundariesCGAZ_ADM1.zip"),
    adm2_shapefile=Path("data/geoBoundaries/geoBoundaries CGAZ_ADM2.zip")
)

# Enrich data
df_enriched = enricher.enrich(df)

# Result has new columns:
# - adm1_name, adm1_code
# - adm2_name, adm2_code
```

### Downstream Aggregation

After enrichment, you can aggregate at any administrative level:

```python
# Aggregate at ADM2 level (districts)
df_adm2 = df_enriched.group_by(["time", "adm2_code"]).agg([
    pl.col("t2m").mean().alias("t2m_mean"),
    pl.col("total_precipitation").sum().alias("precip_total")
])

# Aggregate at ADM1 level (states) - ADM2 codes are discarded
df_adm1 = df_enriched.group_by(["time", "adm1_code"]).agg([
    pl.col("t2m").mean().alias("t2m_mean"),
    pl.col("total_precipitation").sum().alias("precip_total")
])
```

**Note**: Island nations or offshore points without defined boundaries receive `"NONE_DEFINED"` as their ADM code.

---

## Parallelization

The module **automatically detects** your compute environment:

### Local Machine
```bash
# Auto-caps at 75% of CPU cores
python run_pipeline.py --config configs/example_config.json
```

### PBS Cluster (your HPC)
```bash
#!/bin/bash
#PBS -l select=2:ncpus=30:mpiprocs=30:mem=100gb
#PBS -l walltime=02:00:00

cd $PBS_O_WORKDIR
conda activate osme

# Automatically detects 60 MPI ranks
python run_pipeline.py --config configs/example_config.json
```

### SLURM
```bash
#!/bin/bash
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=32

# Automatically detects 64 tasks
python run_pipeline.py --config configs/example_config.json
```

### Manual Override
```json
{
  "parallelization": {
    "mode": "manual",
    "manual_workers": 16
  }
}
```

---

## Logging

### Verbose Mode (Development)
```json
{"logging": {"verbose": true}}
```
**All** messages go to console and file.

### Quiet Mode (Production)
```json
{"logging": {"verbose": false}}
```
Only **warnings, errors, and forced messages** go to console.  
Everything still logged to file at DEBUG level.

### Log Files
```
logs/weather_data_processing/
├── geographic_pipeline_20250217_143052.log
├── mask_builder_20250217_143105.log
└── adm_enricher_20250217_143120.log
```

---

## Data Flow

```
Raw GRIB (hourly, ~700MB/month, 97 files)
  ↓ Step 1: Geographic
Boundary + Mask (spatial filter)
  ↓ Step 2: Masking
Masked Parquet (hourly, country only)
  ↓ + ADM Enrichment
With ADM1/ADM2 columns
  ↓ Step 3: Consolidation
Consolidated (optimized, cleaned)
  ↓ Step 4: Temporal
Half-hourly (interpolated, year boundaries fixed)
  ↓ Step 5: Aggregation
National/Regional Time-Series
```

---

## Interpolation Methods

### Intensive Fields (Temperature, Clouds, Winds)
**Method**: Midpoint average

```
T(t+30min) = 0.5 × [T(t) + T(t+1hr)]
```

### Radiative Extensives (Solar/Thermal)
**Method**: Energy-conserving rate-shaped split

- Assumes piecewise-linear rate across the hour
- Guarantees exact conservation: `E₁ + E₂ = E_total`
- Physically realistic diurnal patterns

### Precipitation
**Method**: Even-split via cumulative midpoint

```
P(t→t+30min) + P(t+30min→t+1hr) = P_hourly
```

---

## Year Boundary Handling

**Problem**: Interpolating Dec 31 23:30 requires Jan 1 00:00 from the next year.

**Solution**: Two-pass approach
1. **Pass 1 (step4a)**: Process each year independently, create placeholder rows
2. **Pass 2 (step4c)**: Fix boundary rows using adjacent years' data

This allows parallel processing of years while handling edge cases correctly.

---

## File Naming Conventions

All outputs follow a consistent pattern:

```
{dataset_prefix}_{COUNTRY}_{hash}_{year}_{stage}.parquet
```

Examples:
```
era5-world_INDIA_d514a3a3c256_2018.parquet                   # Hourly masked
era5-world_INDIA_d514a3a3c256_2018_half-hourly.parquet      # Interpolated
era5-world_INDIA_d514a3a3c256_2018_half-hourly_srtd_fixed.parquet  # Final
era5-world_INDIA_d514a3a3c256_2018_national_half-hourly.parquet    # Aggregated
```

---

## Testing

```bash
# Run geographic pipeline only
python -m weather_data_processing.pipeline.step1_geographic \
    --config configs/example_config.json

# Validate output masks
python -m weather_data_processing.utils.validation \
    --mask data/geoBoundaries/masks/era5-world/era5-world_INDIA_mask_*.parquet
```

---

## Dependencies

```
Core:
  - polars >= 0.19.0        # Lazy DataFrame operations
  - geopandas >= 0.14.0     # Spatial operations
  - xarray >= 2023.1.0      # GRIB file handling
  - cfgrib                  # GRIB backend for xarray
  - pydantic >= 2.0         # Configuration validation

Optional:
  - mpi4py                  # MPI parallelization (HPC)
  - psutil                  # Memory monitoring
  - matplotlib              # Visualizations
  - tqdm                    # Progress bars
```

---

## Troubleshooting

### "No GRIB files found"
**Check**: `data_paths.grib_dir` in config points to correct directory

### "Country not found in shapefile"
**Check**: `boundary.country_name` matches field values exactly (case-sensitive)  
**Try**: Use `boundary.country_field` to specify correct field name

### "ADM enrichment produces all NONE_DEFINED"
**Check**: ADM shapefiles cover your country of interest  
**Check**: CRS is EPSG:4326 in all shapefiles

### "Year boundary fix creates duplicates"
**Check**: Input files are sorted by time  
**Solution**: Run step4b (sorting and cleanup) before step4c

---

## Citation

If you use this pipeline in research, please cite:

```bibtex
@software{weather_data_processing_2025,
  author = {Kaupa, Daniel},
  title = {Weather Data Processing Pipeline},
  year = {2025},
  license = {AGPL-3.0-or-later}
}
```

---

## License

AGPL-3.0-or-later

Copyright © 2025 Daniel Kaupa
