# Step 2: GRIB Masking Pipeline

**Apply spatial masks to ERA5 GRIB files and convert to Parquet with ADM enrichment.**

---

## Overview

Step 2 transforms raw ERA5 GRIB files into analysis-ready Parquet datasets by:

1. **Applying the spatial mask** from Step 1 (filters to country boundaries)
2. **Converting to Parquet** (memory-efficient columnar format)
3. **Enriching with ADM boundaries** (adds ADM1/ADM2 columns for each grid point)

### Key Features

✅ **Lazy xarray loading** - Memory-efficient GRIB processing  
✅ **Spatial filtering** - Only grid cells within country boundaries  
✅ **ADM enrichment** - Hierarchical administrative boundaries added  
✅ **MPI parallelization** - Process 60-100 files in parallel on HPC  
✅ **Automatic detection** - Finds mask files from Step 1  
✅ **Metadata preservation** - Tracks variables and processing history  

---

## Input Requirements

### From Step 1
- **Mask file**: `masks/era5-world_{COUNTRY}_mask_*.parquet`
- **Mask metadata**: `masks/mask_metadata/era5-world_{COUNTRY}_mask_*.json`
- **ADM shapefiles** (if enrichment enabled):
  - `geoBoundariesCGAZ_ADM1.zip`
  - `geoBoundariesCGAZ_ADM2.zip`

### Raw Data
- **GRIB files**: `data/era5-world/raw/*.grib`
  - Hourly ERA5 data
  - ~700MB per month
  - Standard ERA5 variable names

---

## Output

### File Structure
```
data/era5-world/interim/
├── era5-world_INDIA_2018-01.parquet
├── era5-world_INDIA_2018-02.parquet
├── era5-world_INDIA_2018-03.parquet
...
└── era5-world_INDIA_2025-12.parquet
```

### Output Schema

**Without ADM enrichment:**
```
├── latitude: Float64
├── longitude: Float64
├── time: Datetime[μs]
├── frac_in_region: Float64        # From mask
├── t2m: Float32                    # Temperature
├── total_precipitation: Float32
├── u10: Float32                    # Wind U component at 10m
├── v10: Float32                    # Wind V component at 10m
... (all ERA5 variables)
```

**With ADM enrichment (NEW):**
```
├── latitude: Float64
├── longitude: Float64
├── time: Datetime[μs]
├── frac_in_region: Float64
├── adm1_name: String               # State/Province name
├── adm1_code: String               # State/Province ISO code
├── adm2_name: String               # District/County name
├── adm2_code: String               # District/County ISO code
├── t2m: Float32
├── total_precipitation: Float32
... (all ERA5 variables)
```

---

## Usage

### Local (Sequential)

```bash
# Run Step 2 after Step 1
python run_pipeline.py \
    --config configs/pipeline_config.json \
    --step masking \
    --verbose

# Or use the helper script
bash examples/run_step2_sequential.sh
```

### HPC (MPI Parallelization)

```bash
# Submit to PBS scheduler
qsub examples/pbs_step2_masking_mpi.sh

# Monitor progress
tail -f logs/weather_step2_masking_mpi.o*
```

**Performance:**
- 60 MPI ranks (2 nodes × 30 cores)
- Process ~100 monthly files in 1-2 hours
- Each rank processes 1-2 files

### Specify Mask Files Explicitly

```bash
python run_pipeline.py \
    --config configs/pipeline_config.json \
    --step masking \
    --mask-file data/geoBoundaries/masks/era5-world/era5-world_INDIA_mask_combined0.8_264612.parquet \
    --mask-metadata data/geoBoundaries/masks/mask_metadata/era5-world_INDIA_mask_combined0.8_264612.json
```

---

## Configuration

### Enable/Disable ADM Enrichment

```json
{
  "geographic": {
    "adm_enrichment": {
      "enable_adm1": true,           // Add state/province columns
      "enable_adm2": true,            // Add district/county columns
      "adm1_name_field": "shapeName",
      "adm1_code_field": "shapeISO",
      "adm2_name_field": "shapeName",
      "adm2_code_field": "shapeISO",
      "undefined_value": "NONE_DEFINED"
    }
  }
}
```

### Data Paths

```json
{
  "data_paths": {
    "grib_dir": "data/era5-world/raw",          // Input GRIB files
    "interim_dir": "data/era5-world/interim"    // Output Parquet files
  }
}
```

---

## How It Works

### Processing Flow

```
┌─────────────────┐
│  GRIB File      │
│  (700MB, hourly)│
└────────┬────────┘
         │
         ├─> Load with xarray (lazy)
         │
         ├─> Extract all variables
         │
         ├─> For each timestep:
         │   ├─> Convert to DataFrame
         │   ├─> Apply spatial mask
         │   └─> Keep only country grid cells
         │
         ├─> Concatenate timesteps
         │
         ├─> ADM Enrichment:
         │   ├─> Spatial join (lat,lon) → ADM1
         │   ├─> Spatial join (lat,lon) → ADM2
         │   └─> Add name + code columns
         │
         └─> Save to Parquet
             (compressed, with statistics)
```

### ADM Spatial Join

```python
# For each unique (lat, lon) in the data:
1. Create Point geometry
2. Spatial join with ADM1 shapefile → adm1_name, adm1_code
3. Spatial join with ADM2 shapefile → adm2_name, adm2_code
4. Assign "NONE_DEFINED" for undefined regions (islands, offshore)
```

### MPI Distribution

```
60 GRIB files × 60 MPI ranks
├─ Rank 0:  Files 0, 60, 120, ...
├─ Rank 1:  Files 1, 61, 121, ...
├─ Rank 2:  Files 2, 62, 122, ...
...
└─ Rank 59: Files 59, 119, ...

Each rank independently:
1. Loads its assigned files
2. Applies mask
3. Enriches with ADM
4. Saves to Parquet
```

---

## Performance

### Benchmarks (India, 97 monthly files)

| Setup | Time | Throughput |
|-------|------|------------|
| Local sequential (8 cores) | ~6 hours | 16 files/hour |
| HPC MPI (30 ranks, 1 node) | ~3 hours | 32 files/hour |
| HPC MPI (60 ranks, 2 nodes) | ~1.5 hours | 65 files/hour |

**With ADM enrichment:** +10-15% processing time

### Memory Usage

- **Per GRIB file**: ~2-4 GB peak
- **ADM shapefiles**: ~500 MB (loaded once per rank)
- **Recommended**: 3-4 GB RAM per MPI rank

---

## Troubleshooting

### "No mask files found"

**Problem:** Step 2 cannot find mask from Step 1

**Solution:**
```bash
# Option 1: Run Step 1 first
python run_pipeline.py --config configs/pipeline_config.json --step geographic

# Option 2: Specify mask files explicitly
python run_pipeline.py \
    --step masking \
    --mask-file path/to/mask.parquet \
    --mask-metadata path/to/mask.json
```

### "ADM enrichment produces all NONE_DEFINED"

**Problem:** ADM shapefiles don't cover your country

**Solution:**
1. Check shapefile paths in config
2. Verify shapefiles contain your country
3. Check CRS is EPSG:4326
4. Disable ADM enrichment if not needed:
   ```json
   {"adm_enrichment": {"enable_adm1": false, "enable_adm2": false}}
   ```

### "MPI not available"

**Problem:** `mpi4py` not installed

**Solution:**
```bash
# Install mpi4py
conda install -c conda-forge mpi4py

# Or use sequential mode
python run_pipeline.py --step masking  # No --use-mpi flag
```

### "Variable not found in GRIB"

**Problem:** Expected variable missing from GRIB file

**Solution:**
- Check GRIB file with `grib_ls`
- Verify variable names match ERA5 standard
- Missing variables are automatically skipped

---

## Next Steps

After Step 2 completes, you have:
- ✅ Masked Parquet files (hourly data, country-filtered)
- ✅ ADM1/ADM2 columns (for hierarchical aggregation)
- ✅ Compressed, query-optimized format

**Proceed to:**
- **Step 3**: Consolidation (optimize and clean)
- **Step 4**: Temporal interpolation (hourly → half-hourly)
- **Step 5**: Aggregation (national/regional time-series)

Or use the outputs directly for analysis:

```python
import polars as pl

# Load masked data
df = pl.read_parquet("data/era5-world/interim/era5-world_INDIA_2018-01.parquet")

# Aggregate by ADM2 (districts)
df_districts = df.group_by(["time", "adm2_code"]).agg([
    pl.col("t2m").mean().alias("temperature_avg"),
    pl.col("total_precipitation").sum().alias("precipitation_total")
])

# Compute national average
df_national = df.group_by("time").agg([
    (pl.col("t2m") * pl.col("frac_in_region").cos()).sum() / 
    pl.col("frac_in_region").cos().sum()
]).alias("temperature_weighted_avg")
```

---

## Advanced: Custom Processing

### Process Specific Variables Only

```python
from weather_data_processing.processing.grib_masking import GRIBMaskingProcessor

processor = GRIBMaskingProcessor(
    mask_file=mask_path,
    mask_metadata=metadata,
    adm_enricher=enricher
)

# Only extract temperature and wind
result = processor.process_file(
    grib_file=Path("era5_2018-01.grib"),
    output_file=Path("output.parquet"),
    variables=["2t", "u10", "v10"]  # Subset of variables
)
```

### Batch Processing

```python
results = processor.process_batch(
    grib_files=[Path(f"era5_2018-{m:02d}.grib") for m in range(1, 13)],
    output_dir=Path("outputs"),
    output_pattern="india_{stem}.parquet"
)

# Check results
for r in results:
    print(f"{r.input_file.name}: {r.rows_after_adm:,} rows in {r.processing_time_s:.1f}s")
```

---

## File Naming Convention

All outputs follow the pattern:
```
{dataset_prefix}_{COUNTRY}_{YYYY-MM}.parquet
```

Examples:
```
era5-world_INDIA_2018-01.parquet
era5-world_INDIA_2018-02.parquet
era5-world_BRAZIL_2020-06.parquet
```

This enables easy:
- Sorting by time
- Filtering by country
- Pattern matching for batch operations
