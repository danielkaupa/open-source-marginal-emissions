#!/bin/bash
#PBS -l select=1:ncpus=8:mpiprocs=8:mem=100gb
#PBS -l walltime=02:00:00
#PBS -N weather_step4_temporal_mpi

# =============================================================================
# Step 4: Temporal Interpolation with MPI Parallelization
# =============================================================================
#
# This job script interpolates hourly data to half-hourly resolution using MPI.
# Files are distributed across MPI ranks for parallel processing.
#
# Resources:
#   - 1 node × 8 cores = 8 MPI ranks
#   - Each rank processes 1-2 files
#   - Memory: 100GB per node
#
# Expected runtime: 1-2 hours for ~8 annual files
# =============================================================================

cd "$PBS_O_WORKDIR"
JOBNAME=${PBS_JOBNAME:-weather_step4_temporal_mpi}
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

# Verify MPI availability
mpiexec -n "$NP" python -c "from mpi4py import MPI; print('Hello from', MPI.COMM_WORLD.Get_rank(), 'of', MPI.COMM_WORLD.Get_size())"

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
export POLARS_MAX_THREADS=1
export RAYON_NUM_THREADS=1


# ------------------------------------------------------------------------------
# Run Pipeline
# ------------------------------------------------------------------------------
echo "Configuration: $CONFIG_FILE"
echo ""
echo "Node allocation:"
cat $PBS_NODEFILE | uniq -c
echo ""

NP=$(wc -l < "$PBS_NODEFILE")
echo "Total MPI ranks: $NP"
echo ""

# Run Step 4 with MPI parallelization
mpiexec -n "$NP" wdp \
    --config "$CONFIG_FILE" \
    --step temporal \
    --verbose

EXIT_CODE=$?

echo ""
echo "=========================================================================="
echo "JOB COMPLETE"
echo "Exit code: $EXIT_CODE"
echo "Finished: $(date)"
echo "=========================================================================="

exit $EXIT_CODE
