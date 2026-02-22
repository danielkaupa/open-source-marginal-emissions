#!/bin/bash
# =============================================================================
# Step 1: Geographic Processing (HPC - Sequential PBS job)
# Runs Step 1 on a single task/core (no MPI).
# =============================================================================

#PBS -N wdp_step1_geographic
#PBS -l select=1:ncpus=1:mem=8gb
#PBS -l walltime=01:00:00
#PBS -j n
#PBS -V

set -euo pipefail

# ------------------------------------------------------------------------------
# Go to submission directory and set up logging
# ------------------------------------------------------------------------------
cd "${PBS_O_WORKDIR:-$PWD}"

JOBNAME="${PBS_JOBNAME:-wdp_step1_geographic}"
JOBID="${PBS_JOBID:-$$}"
mkdir -p logs

exec 1> "logs/${JOBNAME}.o${JOBID}"
exec 2> "logs/${JOBNAME}.e${JOBID}"

echo "=========================================================================="
echo "STEP 1: GEOGRAPHIC PROCESSING (HPC Sequential PBS)"
echo "Host: $(hostname)"
echo "Workdir: $(pwd)"
echo "Started: $(date)"
echo "=========================================================================="
echo ""

# ------------------------------------------------------------------------------
# Environment / modules (adjust to your cluster)
# ------------------------------------------------------------------------------
module purge || true
module load tools/prod || true
module load miniforge/3 || true

# Activate conda env (adjust paths/env name if needed)
if command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
elif [ -x "$HOME/miniforge3/bin/conda" ]; then
  eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
fi

conda activate osme

# Avoid accidental thread oversubscription
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export POLARS_MAX_THREADS=1
export RAYON_NUM_THREADS=1

# ------------------------------------------------------------------------------
# Configuration (robust default)
# ------------------------------------------------------------------------------
# Preferred location (from repo root based on your zip)
CONFIG_FILE="${CONFIG_FILE:-configs/weather_data_processing/config.json}"

# Fallback if someone runs from inside the package directory
if [ ! -f "$CONFIG_FILE" ] && [ -f "weather_data_processing/config.json" ]; then
  CONFIG_FILE="weather_data_processing/config.json"
fi

if [ ! -f "$CONFIG_FILE" ]; then
  echo "ERROR: Config file not found. Tried:"
  echo "  - configs/weather_data_processing/config.json"
  echo "  - weather_data_processing/config.json"
  echo "Set CONFIG_FILE explicitly when submitting, e.g.:"
  echo "  qsub -v CONFIG_FILE=/path/to/config.json pbs_step1_geographic.sh"
  exit 2
fi

echo "Using config: $CONFIG_FILE"
echo ""

# ------------------------------------------------------------------------------
# Execute (sequential; do NOT use mpiexec for step geographic)
# ------------------------------------------------------------------------------
CMD=(wdp --config "$CONFIG_FILE" --step geographic --verbose)

echo "Command: ${CMD[*]}"
echo ""

set +e
"${CMD[@]}"
EXIT_CODE=$?
set -e

echo ""
echo "=========================================================================="
echo "COMPLETE"
echo "Exit code: $EXIT_CODE"
echo "Finished: $(date)"
echo "=========================================================================="

exit "$EXIT_CODE"
