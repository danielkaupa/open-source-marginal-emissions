#!/bin/bash
#PBS -l select=2:ncpus=30:mpiprocs=30:mem=100gb
#PBS -l walltime=02:00:00
#PBS -N weather_step2_masking_mpi

# =============================================================================
# Step 2: GRIB Masking with MPI Parallelization
# =============================================================================
#
# This job script processes GRIB files in parallel using MPI.
# Each MPI rank processes a subset of the files.
#
# Resources:
#   - 2 nodes × 30 cores = 60 MPI ranks
#   - Each rank processes ~1-2 files
#   - Memory: 100GB per node
#
# Expected runtime: 1-2 hours for ~100 monthly GRIB files
# =============================================================================

cd "$PBS_O_WORKDIR"
JOBNAME=${PBS_JOBNAME:-weather_step2_masking_mpi}
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

# Optional: Override mask files (auto-detected if not provided)
# MASK_FILE=${MASK_FILE:-""}
# MASK_METADATA=${MASK_METADATA:-""}

# ------------------------------------------------------------------------------
# Thread Control (avoid over-threading)
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

# The --use-mpi flag tells the pipeline to use MPI parallelization
# The pipeline automatically detects the PBS environment
mpiexec -n "$NP" python run_pipeline.py \
    --config "$CONFIG_FILE" \
    --step masking \
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
