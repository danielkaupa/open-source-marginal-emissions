"""
Command-line runner for grid data processing pipeline.

This module provides the CLI entry point for the grid data processing pipeline.
It supports multiple command aliases (gdp, griddataprocessing, etc.) and provides
a clean interface for both interactive and automated use.
"""

import argparse
import sys
from pathlib import Path

from grid_data_processing.main import GridDataProcessor


def parse_args():
    """
    Parse command-line arguments for the grid data processing pipeline.
    
    Returns
    -------
    argparse.Namespace
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="grid-data-processing",
        description="Grid Data Processing Pipeline for Indian grid electricity data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process monthly files with default settings (silent, auto-cleanup)
  %(prog)s --monthly-dir data/grid_data/raw/monthly

  # Process existing combined file with verbose output
  %(prog)s --input data/grid_data/raw/combined.parquet --verbose

  # Keep intermediate files and use custom config
  %(prog)s --monthly-dir data/grid_data/raw/monthly --keep-intermediate --config my_config.json

  # Specify custom output directory
  %(prog)s --input data/combined.parquet --output data/custom_output --verbose

Command aliases: gdp, griddataprocessing, gridprocessing, gridproc
        """
    )

    # Input options (mutually exclusive in practice, but both can be provided)
    input_group = parser.add_argument_group('input options')
    input_group.add_argument(
        "--input", "-i",
        type=Path,
        help="Path to combined parquet file (skips monthly file combination step)"
    )
    input_group.add_argument(
        "--monthly-dir", "-m",
        type=Path,
        help="Directory containing monthly parquet files (will be combined as first step)"
    )

    # Output options
    output_group = parser.add_argument_group('output options')
    output_group.add_argument(
        "--output", "-o",
        type=Path,
        help="Output directory for processed files (default: <data_dir>/grid_data/processed)"
    )
    output_group.add_argument(
        "--keep-intermediate", "-k",
        action="store_true",
        help="Keep intermediate step files (by default, only final output is kept)"
    )

    # Configuration
    config_group = parser.add_argument_group('configuration')
    config_group.add_argument(
        "--config", "-c",
        type=Path,
        help="Path to configuration JSON file (default: auto-detect from configs/grid_data_processing/)"
    )

    # Behavior options
    behavior_group = parser.add_argument_group('behavior options')
    behavior_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Echo INFO+ messages to console (file logging always enabled)"
    )
    behavior_group.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress all console output (file logging still enabled). Opposite of --verbose."
    )

    args = parser.parse_args()
    
    # Handle quiet vs verbose conflict
    if args.quiet and args.verbose:
        parser.error("Cannot use both --quiet and --verbose")
    
    # Ensure at least one input is provided
    if not args.input and not args.monthly_dir:
        parser.error("Must provide either --input or --monthly-dir")
    
    return args


def run_pipeline():
    """
    Main entry point for the CLI.
    
    This function is called when the user runs any of the command aliases:
    - gdp
    - griddataprocessing
    - gridprocessing
    - gridproc
    
    It sets up the processor and runs the full pipeline with the provided arguments.
    """
    args = parse_args()
    
    # Determine verbose mode (default is False unless --verbose is set)
    verbose = args.verbose and not args.quiet
    
    # Show startup banner if verbose
    if verbose:
        print("\n" + "=" * 80)
        print("GRID DATA PROCESSING PIPELINE")
        print("=" * 80)
        print(f"\nInput: {args.input or args.monthly_dir}")
        if args.output:
            print(f"Output: {args.output}")
        if args.config:
            print(f"Config: {args.config}")
        print(f"Keep intermediate files: {args.keep_intermediate}")
        print(f"Verbose mode: {verbose}")
        print("\nStarting pipeline...\n")
    
    # Create processor
    try:
        processor = GridDataProcessor(
            input_path=args.input,
            monthly_dir=args.monthly_dir,
            output_dir=args.output,
            config_path=args.config,
            verbose=verbose,
            keep_intermediate=args.keep_intermediate
        )
        
        # Run pipeline
        final_file = processor.run_full_pipeline()
        
        # Show completion message if verbose
        if verbose:
            print("\n" + "=" * 80)
            print("✓ PIPELINE COMPLETE")
            print("=" * 80)
            print(f"\nFinal output: {final_file}")
            print(f"Logs: Check {processor.logger.handlers[0].baseFilename if processor.logger.handlers else 'log directory'}")
            print()
        
        sys.exit(0)
        
    except KeyboardInterrupt:
        if verbose:
            print("\n\nPipeline cancelled by user.")
        sys.exit(130)
        
    except Exception as e:
        if verbose:
            print(f"\n\nERROR: {e}")
            import traceback
            traceback.print_exc()
        else:
            # Even in quiet mode, show critical errors
            print(f"ERROR: {e}", file=sys.stderr)
        
        sys.exit(1)


if __name__ == "__main__":
    run_pipeline()
