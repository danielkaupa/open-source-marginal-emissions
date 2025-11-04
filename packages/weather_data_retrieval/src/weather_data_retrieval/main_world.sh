#!/usr/bin/env bash
#PBS -l select=1:ncpus=3:mem=10gb
#PBS -l walltime=24:00:00
#PBS -N weather_data_retrieval_world

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
conda activate wdr

# Keep threaded libs tame (I/O-bound job)
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1

echo "=== Job $JOBNAME (ID $JOBID) started on $(hostname) at $(date) ==="

python -c "import weather_data_retrieval as m; print('wdr package OK:', getattr(m,'__version__','(no __version__)'))" || exit 1

# Run non-interactive with JSON config
# Prefer module mode for proper package imports:
python -m weather_data_retrieval --config weather/download_request_world.json --verbose

echo "=== Job $JOBNAME (ID $JOBID) finished on $(hostname) at $(date) ==="
