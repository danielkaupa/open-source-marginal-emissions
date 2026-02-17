#!/usr/bin/env bash
#PBS -l select=1:ncpus=1:mem=10gb
#PBS -l walltime=1:00:00
#PBS -N grid_data_processing

cd "$PBS_O_WORKDIR"
JOBNAME=${PBS_JOBNAME:-wdr}
JOBID=${PBS_JOBID:-$$}
mkdir -p logs
exec 1>logs/${JOBNAME}.o${JOBID}
exec 2>logs/${JOBNAME}.e${JOBID}
set -euo pipefail

module purge
module load tools/prod || true
module load miniforge/3 || true

eval "$(~/miniforge3/bin/conda shell.bash hook)"   # adjust path if needed
conda activate osme

# Keep threaded libs tame (I/O-bound job)
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1

echo "=== Job $JOBNAME (ID $JOBID) started on $(hostname) at $(date) ==="

python -c "import grid_data_processing as g; print('wdr package OK:', getattr(g,'__version__','(no __version__)'))" || exit 1

gdp --input grid_data/raw/carbontracker_grid-data_2018-11_2026-02.parquet --keep-intermediate  --verbose

echo "=== Job $JOBNAME (ID $JOBID) finished on $(hostname) at $(date) ==="
