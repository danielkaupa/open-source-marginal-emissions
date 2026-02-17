# Step 3: Consolidation Pipeline

**Optimize, consolidate, and rename parquet files from Step 2.**

---

## Overview

Step 3 transforms masked monthly parquet files into analysis-ready annual/quarterly datasets through three stages:

1. **Stage 1: Optimize** - Clean monthly files (drop columns, cast dtypes, validate schema)
2. **Stage 2: Consolidate** - Combine monthly files into annual/biannual/quarterly files  
3. **Stage 3: Rename** - Apply metadata-based column renaming

### Key Features

✅ **Three-stage processing** - Modular, resumable pipeline  
✅ **Schema validation** - Ensures data quality and consistency  
✅ **Dtype optimization** - Float64 → Float32, memory efficient  
✅ **Flexible consolidation** - Annual, biannual, or quarterly modes  
✅ **MPI parallelization** - Distributes years across ranks  
✅ **Column renaming** - ERA5 shortNames → human-readable names  

---

## Input Requirements

### From Step 2
- **Monthly parquet files**: `data/era5-world/interim/*.parquet`
  - Format: `era5-world_INDIA_d514a3a3c256_2018_01.parquet`
  - Hourly data with ADM columns
  - ~97 files (8 years × 12 months)

### Metadata (Optional)
- **Metadata JSON**: `data/era5-world/interim/*_metadata.json`
  - Contains column rename mappings
  - shortName → datasetProcessingName
  - Example: `"2t"` → `"temperature_2m"`

---

## Output

### File Structure
```
data/era5-world/processed/
├── era5-world_INDIA_d514a3a3c256_2018.parquet        # Annual
├── era5-world_INDIA_d514a3a3c256_2019.parquet
...
├── era5-world_INDIA_d514a3a3c256_2025.parquet

# Or with quarterly mode:
├── era5-world_INDIA_d514a3a3c256_2018_Q1.parquet
├── era5-world_INDIA_d514a3a3c256_2018_Q2.parquet
├── era5-world_INDIA_d514a3a3c256_2018_Q3.parquet
├── era5-world_INDIA_d514a3a3c256_2018_Q4.parquet
...
```

### Schema Changes

**Before (Step 2 output):**
```
latitude: Float64
longitude: Float64
time: Datetime[μs]
2t: Float64                  ← ERA5 shortName
tp: Float64
10u: Float64
10v: Float64
...
```

**After Step 3:**
```
latitude: Float32            ← Optimized dtype
longitude: Float32
time: Datetime[μs]
temperature_2m: Float32      ← Renamed column
total_precipitation: Float32
wind_u_10m: Float32
wind_v_10m: Float32
adm1_name: String            ← Preserved from Step 2
adm1_code: String
adm2_name: String
adm2_code: String
...
```

### Temporary Files
```
data/era5-world/temp/
├── temp_clean/              # Stage 1 output (optimized monthly files)
└── temp_agg/                # Stage 2 output (consolidated files, before renaming)
```

---

## Usage

### Local (Sequential)

```bash
# Run Step 3
python run_pipeline.py \
    --config configs/pipeline_config.json \
    --step consolidation \
    --verbose
```

### HPC (MPI Parallelization)

```bash
# Submit to PBS scheduler
qsub examples/pbs_step3_consolidation_mpi.sh

# Monitor progress
tail -f logs/weather_step3_consolidation_mpi.o*
```

**Performance:**
- 60 MPI ranks (2 nodes × 30 cores)
- Process ~8 years in 30-60 minutes
- Each rank processes 1-2 years

### Full Pipeline (Steps 1-3)

```bash
# Run all steps together
python run_pipeline.py \
    --config configs/pipeline_config.json \
    --step all \
    --use-mpi
```

---

## Configuration

### Consolidation Modes

```json
{
  "aggregation": {
    "temporal": {
      "modes": ["annual", "quarterly"]     // Choose consolidation modes
    }
  }
}
```

**Available modes:**
- `"annual"` - One file per year (12 months)
- `"biannual"` - Two files per year (H1: Jan-Jun, H2: Jul-Dec)
- `"quarterly"` - Four files per year (Q1-Q4)

### Data Paths

```json
{
  "data_paths": {
    "interim_dir": "data/era5-world/interim",      // Input (Step 2 output)
    "processed_dir": "data/era5-world/processed"    // Output (final files)
  }
}
```

### Advanced Options

```python
# Python API for custom configuration
from weather_data_processing.pipeline.step3_consolidation import ConsolidationPipeline

pipeline = ConsolidationPipeline(
    input_dir=Path("data/era5-world/interim"),
    output_dir=Path("data/era5-world/processed"),
    metadata_file=Path("data/era5-world/interim/metadata.json"),
    modes=["annual", "quarterly"],
    drop_cols=["centroid_in_region", "cell_area_m2"],  # Columns to drop
    overwrite=True,
    cleanup_temp=True  # Remove temporary directories after completion
)

results = pipeline.run(use_mpi=True)
```

---

## How It Works

### Processing Flow

```
┌─────────────────────────────┐
│  Monthly Parquet Files      │
│  (97 files, Step 2 output)  │
└──────────┬──────────────────┘
           │
           ├─ STAGE 1: Optimize
           │  ├─ Drop unwanted columns
           │  ├─ Cast Float64 → Float32
           │  ├─ Validate schema
           │  └─ Write to temp_clean/
           │
           ├─ STAGE 2: Consolidate
           │  ├─ Group by year
           │  ├─ Concatenate monthly files
           │  ├─ Split by mode (annual/quarterly)
           │  └─ Write to temp_agg/
           │
           ├─ STAGE 3: Rename
           │  ├─ Load metadata mapping
           │  ├─ Rename columns (2t → temperature_2m)
           │  └─ Write to processed/
           │
           └─ CLEANUP (optional)
              └─ Remove temp_clean/ and temp_agg/
```

### MPI Distribution

```
8 years × 60 MPI ranks
├─ Rank 0:  Years 2018, 2026, ...
├─ Rank 1:  Years 2019, ...
├─ Rank 2:  Years 2020, ...
...
└─ Rank 7:  Years 2025, ...

Each rank independently:
1. Optimizes its years' monthly files
2. Consolidates into annual/quarterly
3. Renames columns
4. Writes to processed/
```

---

## Performance

### Benchmarks (India, 97 monthly files, 8 years)

| Setup | Time | Throughput |
|-------|------|------------|
| Sequential (8 cores) | ~15 minutes | 6.5 files/min |
| MPI (30 ranks, 1 node) | ~8 minutes | 12 files/min |
| MPI (60 ranks, 2 nodes) | ~5 minutes | 19 files/min |

### Memory Usage

- **Per year**: ~2-3 GB peak (during consolidation)
- **Recommended**: 4 GB RAM per MPI rank

### File Size Reduction

**Example (India, 1 year):**
- Monthly files (12): 12 × 80 MB = 960 MB
- Annual file (1): 950 MB (slightly smaller due to compression)
- Quarterly files (4): 4 × 240 MB = 960 MB

**Compression:**
- All files use zstd compression
- Typical compression ratio: ~3:1

---

## Schema Validation

### Default Dropped Columns

These columns are automatically removed during Stage 1:

```python
DEFAULT_DROP_COLS = [
    "centroid_in_region",  # Intermediate calculation
    "cell_area_m2",        # Not needed after weighting
    "number",              # GRIB artifact
    "step",                # GRIB artifact
    "surface",             # GRIB artifact
    "valid_time",          # Redundant (we use 'time')
]
```

### Dtype Optimization

**Automatic conversions:**
- `Float64` → `Float32` (all ERA5 variables)
- `Int64` → `Int32` (where applicable)
- Datetime precision preserved (`Datetime[μs]`)

**Preserved dtypes:**
- `String` columns (ADM names, codes)
- `Boolean` columns (if any)

### Schema Enforcement

The pipeline ensures:
1. All expected columns are present
2. All dtypes match the global schema
3. Column order is consistent across files
4. No duplicate columns

---

## Column Renaming

### How It Works

**Metadata JSON structure:**
```json
{
  "variables": {
    "2t": {
      "shortName": "2t",
      "fullName": "2 metre temperature",
      "datasetProcessingName": "temperature_2m"
    },
    "tp": {
      "shortName": "tp",
      "fullName": "Total precipitation",
      "datasetProcessingName": "total_precipitation"
    }
  }
}
```

**Rename map generated:**
```python
{
    "2t": "temperature_2m",
    "tp": "total_precipitation",
    "10u": "wind_u_10m",
    "10v": "wind_v_10m",
    ...
}
```

### Custom Renaming

```python
# Provide custom rename map
custom_rename = {
    "2t": "temp_2m",
    "tp": "precip_total"
}

processor = ConsolidationProcessor(
    global_dtype_map=dtype_map,
    metadata_rename=custom_rename  # Override metadata
)
```

---

## Troubleshooting

### "Schema validation failed"

**Problem:** Monthly files have inconsistent schemas

**Solution:**
```bash
# Check schema of a sample file
python -c "
import polars as pl
schema = pl.read_parquet_schema('data/interim/era5-world_INDIA_2018_01.parquet')
for col, dtype in schema.items():
    print(f'{col}: {dtype}')
"

# Common causes:
# - Different dtypes between files
# - Missing columns in some files
# - Extra columns from failed processing
```

### "Missing metadata file"

**Problem:** Column renaming skipped

**Solution:**
```bash
# Check for metadata files
ls data/era5-world/interim/*_metadata.json

# If missing, renaming will be skipped (not critical)
# Files will keep ERA5 shortNames (2t, tp, etc.)
```

### "Memory error during consolidation"

**Problem:** Not enough RAM to consolidate a year

**Solution:**
```python
# Process in smaller chunks
pipeline = ConsolidationPipeline(
    modes=["quarterly"]  # Smaller files than annual
)

# Or increase PBS memory allocation
#PBS -l select=1:ncpus=30:mem=200gb  # Increase from 100gb
```

### "Different number of files per year"

**Problem:** Some years incomplete (missing months)

**Solution:**
- Pipeline will still consolidate available months
- Check logs for warnings about missing files
- Verify Step 2 completed successfully for all months

---

## Integration with Pipeline

### Chained Execution

```bash
# Run Steps 1-3 in sequence
python run_pipeline.py --config configs/pipeline_config.json --step all

# Workflow:
# 1. Step 1: Generate mask
# 2. Step 2: Apply mask, enrich with ADM
# 3. Step 3: Consolidate and rename
```

### Selective Re-run

```bash
# Re-run just Step 3 (e.g., to change consolidation mode)
python run_pipeline.py --step consolidation

# Update config first:
# "modes": ["quarterly"]  # Changed from ["annual"]
```

---

## Next Steps

After Step 3 completes, you have:
- ✅ Annual/quarterly parquet files
- ✅ Optimized dtypes (Float32)
- ✅ Human-readable column names
- ✅ Consistent schema

**Proceed to:**
- **Step 4**: Temporal interpolation (hourly → half-hourly)
- **Step 5**: Spatial aggregation (national/regional time-series)

Or use the outputs directly for analysis:

```python
import polars as pl

# Load annual file
df = pl.read_parquet("data/era5-world/processed/era5-world_INDIA_2018.parquet")

# Aggregate by month
df_monthly = df.group_by(
    pl.col("time").dt.truncate("1mo")
).agg([
    pl.col("temperature_2m").mean(),
    pl.col("total_precipitation").sum()
])

# Aggregate by ADM1 (state)
df_states = df.group_by(["time", "adm1_code"]).agg([
    pl.col("temperature_2m").mean(),
    pl.col("total_precipitation").sum()
])
```

---

## File Naming Convention

All outputs follow the pattern:
```
{prefix}_{uid}_{year}[_{period}].parquet
```

**Examples:**
```
era5-world_INDIA_d514a3a3c256_2018.parquet           # Annual
era5-world_INDIA_d514a3a3c256_2018_Q1.parquet        # Quarterly
era5-world_INDIA_d514a3a3c256_2018_H1.parquet        # Biannual
```

This enables easy:
- Sorting by time
- Filtering by year/period
- Pattern matching for batch operations
