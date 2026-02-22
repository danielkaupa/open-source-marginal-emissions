#!/bin/bash
#PBS -N weather_step2_masking_mpi
#PBS -l select=2:ncpus=16:mpiprocs=16:mem=100gb
#PBS -l walltime=02:00:00
#PBS -l place=scatter
#PBS -j n

# =============================================================================
# Step 2: GRIB Masking with MPI Parallelization
# =============================================================================
# Resources:
#   - 2 nodes × 16 MPI ranks per node = 32 ranks total
#   - Memory: 100GB per node (NOT pooled across nodes)
# =============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# Workdir + logging
# ------------------------------------------------------------------------------
cd "${PBS_O_WORKDIR:-$PWD}"

JOBNAME="${PBS_JOBNAME:-weather_step2_masking_mpi}"
JOBID="${PBS_JOBID:-$$}"

mkdir -p logs
exec 1> "logs/${JOBNAME}.o${JOBID}"
exec 2> "logs/${JOBNAME}.e${JOBID}"

echo "=========================================================================="
echo "JOB: $JOBNAME"
echo "ID: $JOBID"
echo "Started: $(date)"
echo "Host (script): $(hostname)"
echo "Workdir: $(pwd)"
echo "=========================================================================="
echo ""

# ------------------------------------------------------------------------------
# Load Environment
# ------------------------------------------------------------------------------
module purge || true
module load tools/prod || true

# Use your user-installed miniforge (avoid mixing with module miniforge)
if [ -x "$HOME/miniforge3/bin/conda" ]; then
  eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
elif command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
else
  echo "ERROR: conda not found (neither ~/miniforge3/bin/conda nor conda on PATH)."
  exit 2
fi

conda activate osme

# IMPORTANT: load system OpenMPI AFTER conda activate (so it wins in PATH)
OMPI_MODULE="${OMPI_MODULE:-OpenMPI/4.1.6-GCC-13.2.0}"
module load "$OMPI_MODULE"

echo "Python:  $(command -v python)"
echo "mpiexec: $(command -v mpiexec)"
mpiexec --version | head -n 2
echo ""

# ------------------------------------------------------------------------------
# Configuration (repo-root default + fallback)
# ------------------------------------------------------------------------------
CONFIG_FILE="${CONFIG_FILE:-configs/weather_data_processing/config.json}"
if [ ! -f "$CONFIG_FILE" ] && [ -f "weather_data_processing/config.json" ]; then
  CONFIG_FILE="weather_data_processing/config.json"
fi
if [ ! -f "$CONFIG_FILE" ]; then
  echo "ERROR: Config file not found. Tried:"
  echo "  - configs/weather_data_processing/config.json"
  echo "  - weather_data_processing/config.json"
  echo "Set CONFIG_FILE explicitly when submitting, e.g.:"
  echo "  qsub -v CONFIG_FILE=/path/to/config.json pbs_step2_masking_mpi.sh"
  exit 2
fi

echo "Configuration: $CONFIG_FILE"
echo ""

# ------------------------------------------------------------------------------
# Thread Control (avoid over-threading per rank)
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
# MPI allocation info
# ------------------------------------------------------------------------------
if [ -z "${PBS_NODEFILE:-}" ] || [ ! -f "${PBS_NODEFILE:-}" ]; then
  echo "ERROR: PBS_NODEFILE is missing; cannot determine rank count."
  exit 2
fi

echo "Node allocation (uniq -c PBS_NODEFILE):"
uniq -c "$PBS_NODEFILE"
echo ""

NP="$(wc -l < "$PBS_NODEFILE")"
echo "Total MPI ranks (from PBS_NODEFILE): $NP"
echo ""

# ------------------------------------------------------------------------------
# Optional MPI smoke test (comment out if you want less log noise)
# ------------------------------------------------------------------------------
mpiexec -n "$NP" python -c "from mpi4py import MPI; import socket; \
print('rank', MPI.COMM_WORLD.rank, 'of', MPI.COMM_WORLD.size, 'on', socket.gethostname())"

echo ""
echo "--------------------------------------------------------------------------"
echo "Running Step 2 (masking) under MPI"
echo "--------------------------------------------------------------------------"
echo ""

# ------------------------------------------------------------------------------
# Run Step 2 (no --use-mpi flag; MPI is enabled by launching with mpiexec)
# ------------------------------------------------------------------------------
mpiexec -n "$NP" wdp \
  --config "$CONFIG_FILE" \
  --step masking \
  --verbose

EXIT_CODE=$?

echo ""
echo "=========================================================================="
echo "JOB COMPLETE"
echo "Exit code: $EXIT_CODE"
echo "Finished: $(date)"
echo "=========================================================================="

exit "$EXIT_CODE"
