#!/bin/bash
# =============================================================================
# Step 2: GRIB Masking (Sequential - for local testing)
# =============================================================================
#
# This script runs Step 2 sequentially on a local machine.
# Suitable for testing or processing small batches.
#
# For HPC with MPI, use pbs_step2_masking_mpi.sh instead.
# =============================================================================

set -euo pipefail

echo "=========================================================================="
echo "STEP 2: GRIB MASKING (Sequential Mode)"
echo "Started: $(date)"
echo "=========================================================================="
echo ""

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
CONFIG_FILE=${CONFIG_FILE:-"configs/weather_data_processing/example_config.json"}

# Optional: Specify mask files explicitly
# (If not provided, auto-detected from Step 1 output)
MASK_FILE=${MASK_FILE:-""}
MASK_METADATA=${MASK_METADATA:-""}

# ------------------------------------------------------------------------------
# Build command
# ------------------------------------------------------------------------------
CMD="python run_pipeline.py --config $CONFIG_FILE --step geographic --verbose"

if [ -n "$MASK_FILE" ]; then
    CMD="$CMD --mask-file $MASK_FILE"
fi

if [ -n "$MASK_METADATA" ]; then
    CMD="$CMD --mask-metadata $MASK_METADATA"
fi

# ------------------------------------------------------------------------------
# Execute
# ------------------------------------------------------------------------------
echo "Command: $CMD"
echo ""

eval $CMD

EXIT_CODE=$?

echo ""
echo "=========================================================================="
echo "COMPLETE"
echo "Exit code: $EXIT_CODE"
echo "Finished: $(date)"
echo "=========================================================================="

exit $EXIT_CODE
