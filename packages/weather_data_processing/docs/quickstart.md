# Quick Start Guide

## Installation

```bash
# 1. Copy to your project
cp -r weather_data_processing /path/to/your/open-source-marginal-emissions/packages/

# 2. Add to your Python path (if not using editable install)
export PYTHONPATH="/path/to/your/open-source-marginal-emissions/packages:$PYTHONPATH"
```

## Immediate Usage (What Works Now)

### Test the Configuration

```bash
cd packages/weather_data_processing

# Validate your configuration
python run_pipeline.py --config configs/example_config.json --dry-run
```

**Expected output:**
```
╔═══════════════════════════════════════════════════════════════╗
║      WEATHER DATA PROCESSING PIPELINE                         ║
╚═══════════════════════════════════════════════════════════════╝

DRY RUN MODE: Validating configuration

Configuration valid ✓

Steps configured:
  ✓ Geographic
  ✓ Temporal
  ✓ Aggregation
```

### Run Geographic Processing (Step 1)

```bash
# Update the config with your paths
nano configs/example_config.json

# Run Step 1
python run_pipeline.py \
    --config configs/example_config.json \
    --step geographic \
    --grib-dir ../../../data/era5-world/raw \
    --verbose
```

**What this does:**
1. Extracts India boundary from geoBoundaries ADM0 shapefile
2. Generates spatial mask (combined mode, 80% threshold)
3. Validates ADM1/ADM2 shapefiles are present
4. Creates visualization of the mask
5. Saves metadata

**Outputs:**
```
data/geoBoundaries/
├── extracted/
│   └── India.geojson                           # Country boundary
├── masks/era5-world/
│   └── era5-world_INDIA_mask_combined0.8_*.parquet  # Spatial mask
├── masks/mask_metadata/
│   └── era5-world_INDIA_mask_combined0.8_*.json     # Metadata
└── images/
    └── era5-world_INDIA_mask_combined0.8_*.png      # Visualization
```

### Use ADM Enrichment in Your Existing Code

```python
# Add this to your existing step2a or step3a scripts

from pathlib import Path
from weather_data_processing.processing.admin_enrichment import ADMEnricher
from weather_data_processing.config_schema import ADMEnrichmentConfig

# Configure
config = ADMEnrichmentConfig(
    enable_adm1=True,
    enable_adm2=True,
    undefined_value="NONE_DEFINED"
)

# Create enricher (only once per run)
enricher = ADMEnricher(
    config=config,
    adm1_shapefile=Path("data/geoBoundaries/geoBoundariesCGAZ_ADM1.zip"),
    adm2_shapefile=Path("data/geoBoundaries/geoBoundariesCGAZ_ADM2.zip")
)

# Then for each parquet file you process:
import polars as pl
df = pl.read_parquet("your_masked_file.parquet")
df_enriched = enricher.enrich(df)  # Adds adm1_*, adm2_* columns
df_enriched.write_parquet("your_masked_file_enriched.parquet")
```

## Integration with PBS

### Create a Job Script

```bash
#!/bin/bash
#PBS -l select=1:ncpus=4:mem=32gb
#PBS -l walltime=00:30:00
#PBS -N weather_step1_geographic

cd $PBS_O_WORKDIR
module load miniforge/3
conda activate osme

# The pipeline auto-detects PBS environment
python packages/weather_data_processing/run_pipeline.py \
    --config packages/weather_data_processing/configs/example_config.json \
    --step geographic \
    --grib-dir data/era5-world/raw

echo "Step 1 complete at $(date)"
```

Submit with:
```bash
qsub run_step1_geographic.sh
```

## Configuration Customization

Edit `configs/example_config.json`:

```json
{
  "geographic": {
    "boundary": {
      "country_name": "India",          // Change to your country
      "shapefile_adm0": "data/geoBoundaries/geoBoundariesCGAZ_ADM0.zip"
    },
    "mask": {
      "inclusion_mode": "combined",      // Options: "centroid", "intersection", "combined"
      "fraction_threshold": 0.8,         // For combined mode (0.0 - 1.0)
      "generate_visualization": true     // Set false to skip plots
    },
    "adm_enrichment": {
      "enable_adm1": true,               // State/province boundaries
      "enable_adm2": true                // District/county boundaries
    }
  }
}
```

## Testing Auto-Detection

```python
# Test PBS detection
from weather_data_processing.utils.parallel import detect_environment

env = detect_environment()
print(env)
# Output on PBS:
#   Compute Environment: PBS
#   Total cores: 128
#   MPI ranks: 30
#   Nodes: 2
```

## Next Steps After Phase 1

Once you're comfortable with Step 1:

1. **Continue using your existing scripts for steps 2-5**
2. **Add ADM enrichment** to your step2a output
3. **Gradually migrate** to the new pipeline as Phase 2 components are built

Or wait for Phase 2 completion and switch entirely.

## Troubleshooting

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'weather_data_processing'`

**Solution:**
```bash
# Option 1: Add to PYTHONPATH
export PYTHONPATH="/path/to/packages:$PYTHONPATH"

# Option 2: Install in development mode
cd packages/weather_data_processing
pip install -e .
```

### Config Validation Errors

**Problem:** Pydantic validation fails

**Solution:** Check the error message - it will tell you exactly which field is invalid:
```
ValidationError: 1 validation error for PipelineConfig
geographic.boundary.country_name
  Field required [type=missing, input_value=...]
```

### Shapefile Not Found

**Problem:** `FileNotFoundError: ADM0 shapefile not found`

**Solution:** Use absolute paths or relative to your repo root:
```json
{
  "shapefile_adm0": "/absolute/path/to/geoBoundariesCGAZ_ADM0.zip"
}
```

## Support

Issues? Questions?

1. Check `README.md` for comprehensive documentation
2. Review `IMPLEMENTATION_SUMMARY.md` for architecture details
3. Examine example configuration in `configs/example_config.json`
