#!/bin/bash
#PBS -l select=2:ncpus=30:mpiprocs=30:mem=100gb
#PBS -l walltime=01:00:00
#PBS -N weather_step3_consolidation_mpi

# =============================================================================
# Step 3: Consolidation with MPI Parallelization
# =============================================================================
#
# This job script optimizes, consolidates, and renames parquet files using MPI.
# Years are distributed across MPI ranks for parallel processing.
#
# Resources:
#   - 2 nodes × 30 cores = 60 MPI ranks
#   - Each rank processes 1-2 years
#   - Memory: 100GB per node
#
# Expected runtime: 30-60 minutes for ~100 monthly files (8 years)
# =============================================================================

cd "$PBS_O_WORKDIR"
JOBNAME=${PBS_JOBNAME:-weather_step3_consolidation_mpi}
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
python -c "from mpi4py import MPI; print(f'MPI OK: {MPI.COMM_WORLD.Get_size()} ranks')" || exit 1

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
CONFIG_FILE=${CONFIG_FILE:-"configs/pipeline_config.json"}

# ------------------------------------------------------------------------------
# Thread Control
# ------------------------------------------------------------------------------
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

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

# Run Step 3 with MPI parallelization
mpiexec -n "$NP" python run_pipeline.py \
    --config "$CONFIG_FILE" \
    --step consolidation \
    --use-mpi \
    --verbose

EXIT_CODE=$?

echo ""
echo "=========================================================================="
echo "JOB COMPLETE"
echo "Exit code: $EXIT_CODE"
echo "Finished: $(date)"
echo "=========================================================================="

exit $EXIT_CODE
