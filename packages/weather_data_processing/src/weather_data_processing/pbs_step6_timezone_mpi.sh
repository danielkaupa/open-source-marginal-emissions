#!/bin/bash
#PBS -l select=1:ncpus=2:mem=320gb
#PBS -l walltime=00:25:00
#PBS -N weather_step6_timezone

# =============================================================================
# Step 6: Timezone Conversion (Sequential)
# =============================================================================
#
# This job converts UTC timestamps to the target timezone (e.g., Asia/Kolkata)
# for the single consolidated half-hourly file from Step 5.
#
# No MPI needed - just one file to process.
#
# Resources:
#   - 1 node × 2 cores
#   - Memory: 32GB (file fits in memory)
#
# Expected runtime: 2-5 minutes
# =============================================================================

cd "$PBS_O_WORKDIR"
JOBNAME=${PBS_JOBNAME:-weather_step6_timezone}
JOBID=${PBS_JOBID:-$$}

# Create logs directory
mkdir -p logs
exec 1>logs/${JOBNAME}.o${JOBID}
exec 2>logs/${JOBNAME}.e${JOBID}

set -euo pipefail

echo "=========================================================================="
echo "JOB: $JOBNAME"
echo "ID: $JOBID"
echo "Started: $(date)"
echo "Host: $(hostname)"
echo "=========================================================================="
echo ""

# ------------------------------------------------------------------------------
# Load Environment
# ------------------------------------------------------------------------------
module purge
module load tools/prod || true
module load miniforge/3 || true

eval "$(~/miniforge3/bin/conda shell.bash hook)"
conda activate osme

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
CONFIG_FILE=${CONFIG_FILE:-"weather_data_processing/config.json"}

# ------------------------------------------------------------------------------
# Thread Control
# ------------------------------------------------------------------------------
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export POLARS_MAX_THREADS=2
export RAYON_NUM_THREADS=2

# ------------------------------------------------------------------------------
# Run Pipeline (sequential - single file)
# ------------------------------------------------------------------------------
echo "Configuration: $CONFIG_FILE"
echo ""

wdp \
    --config "$CONFIG_FILE" \
    --step timezone \
    --verbose

EXIT_CODE=$?

echo ""
echo "=========================================================================="
echo "JOB COMPLETE"
echo "Exit code: $EXIT_CODE"
echo "Finished: $(date)"
echo "=========================================================================="

exit $EXIT_CODE
