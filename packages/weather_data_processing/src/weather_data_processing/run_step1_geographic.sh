#!/bin/bash
# =============================================================================
# Step 1: Geographic Processing (HPC - Sequential PBS job)
# Runs Step 1 on a single task/core (no MPI).
# =============================================================================

#PBS -N wdp_step1_geographic
# Request 1 chunk (node), 1 CPU, 1 process, 8 GB RAM
#PBS -l select=1:ncpus=1:mpiprocs=1:mem=8gb
#PBS -l walltime=01:00:00
#PBS -j n


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
# Environment / modules
# ------------------------------------------------------------------------------
module purge || true
module load tools/prod || true
# IMPORTANT: since you want to rely on your own miniforge, do NOT load the module miniforge.
# module load miniforge/3 || true

# Use your user-installed miniforge
if [ -x "$HOME/miniforge3/bin/conda" ]; then
  eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
elif command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
else
  echo "ERROR: conda not found (neither ~/miniforge3/bin/conda nor conda on PATH)."
  exit 2
fi

conda activate osme

# ------------------------------------------------------------------------------
# Thread Control (ensure you truly only use the 1 CPU you requested)
# ------------------------------------------------------------------------------
export OMP_NUM_THREADS=1
export OMP_DYNAMIC=FALSE
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_MAX_THREADS=1
export POLARS_MAX_THREADS=1
export RAYON_NUM_THREADS=1

# ------------------------------------------------------------------------------
# Configuration (robust default)
# ------------------------------------------------------------------------------
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
