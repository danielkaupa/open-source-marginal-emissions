"""
Main Grid Data Processor
========================

Orchestrates the complete grid data processing pipeline with:
- Automatic date range detection from input files
- Non-interactive operation by default
- Optional cleanup of intermediate files
- Complete logging to file with optional console output
- Integration with osme_common for paths
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

import polars as pl

from osme_common.paths import data_dir, log_dir, resolve_under

from grid_data_processing.io.config_loader import load_config
from grid_data_processing.io.file_handler import (
    FileHandler,
    detect_date_range_from_monthly,
    detect_date_range_from_combined
)
from grid_data_processing.pipeline.step1_combine_monthly import combine_monthly_files
from grid_data_processing.pipeline.step2_gap_filling import fill_all_gaps
from grid_data_processing.pipeline.step3_temporal_aggregation import aggregate_to_half_hourly
from grid_data_processing.pipeline.step4_timezone import set_timezone
from grid_data_processing.utils.logging import setup_logging
from grid_data_processing.utils.validation import validate_processed_data


class GridDataProcessor:
    """
    Main processor for grid data pipeline.

    This class orchestrates the complete processing workflow:
    1. Optional: Combine monthly files (if monthly_dir provided)
    2. Create full time grid and identify gaps
    3. Fill short gaps (linear interpolation)
    4. Fill long gaps (gradient method)
    5. Aggregate to half-hourly
    6. Convert timezone
    7. Optional: Clean up intermediate files

    The processor operates in non-interactive mode by default, automatically
    proceeding through all steps. All operations are logged to file, with
    optional console output controlled by the verbose flag.

    Parameters
    ----------
    input_path : str or Path, optional
        Path to input parquet file (combined file). If provided, skips step 1.
    monthly_dir : str or Path, optional
        Directory containing monthly parquet files. If provided (and input_path
        is not), will combine these files as step 1.
    output_dir : str or Path, optional
        Directory for output files. Defaults to data_dir()/grid_data/processed
    config_path : str or Path, optional
        Path to configuration JSON. If not provided, searches for
        default_processing.json in configs/grid_data_processing/
    verbose : bool, optional
        If True, echo INFO+ messages to console. If False, console is silent
        (file logging always enabled). Default: False
    keep_intermediate : bool, optional
        If True, keep intermediate step files (step 1, 2, 3). If False, remove
        them after successful completion. Default: False

    Examples
    --------
    >>> # Process from monthly files, silent mode, auto-cleanup
    >>> processor = GridDataProcessor(
    ...     monthly_dir="data/grid_data/raw/monthly",
    ...     verbose=False,
    ...     keep_intermediate=False
    ... )
    >>> final_file = processor.run_full_pipeline()

    >>> # Process from existing combined file, verbose mode
    >>> processor = GridDataProcessor(
    ...     input_path="data/grid_data/raw/combined.parquet",
    ...     verbose=True
    ... )
    >>> final_file = processor.run_full_pipeline()
    """

    def __init__(
        self,
        input_path: Optional[Path | str] = None,
        monthly_dir: Optional[Path | str] = None,
        output_dir: Optional[Path | str] = None,
        config_path: Optional[Path | str] = None,
        verbose: bool = False,
        keep_intermediate: bool = False,
    ):
        # Resolve input paths relative to data_dir() for relative paths
        # This allows users to provide paths like "grid_data/raw/file.parquet"
        # which will automatically resolve to "<data_dir>/grid_data/raw/file.parquet"
        base_data_dir = data_dir()

        if input_path:
            self.input_path = resolve_under(base_data_dir, input_path)
        else:
            self.input_path = None

        if monthly_dir:
            self.monthly_dir = resolve_under(base_data_dir, monthly_dir)
        else:
            self.monthly_dir = None

        self.keep_intermediate = keep_intermediate

        # Use osme_common.paths for output directory
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = data_dir() / "grid_data" / "processed"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load configuration using osme_common.paths integration
        self.config = load_config(config_path)

        # Setup logging
        self.logger = setup_logging(
            name="grid_data_processing",
            log_subdir="grid_data_processing",
            verbose=verbose
        )

        # Determine base filename for outputs
        base_filename = self._determine_base_filename()

        # File handler for managing intermediate outputs
        self.file_handler = FileHandler(
            output_dir=self.output_dir,
            base_filename=base_filename
        )

        # Track processing state
        self.state: Dict[str, Any] = {
            "combined_file": None,
            "gapfilled_file": None,
            "half_hourly_file": None,
            "final_file": None,
        }

        self.logger.info(f"Output directory: {self.output_dir}")
        self.logger.info(f"Base filename: {base_filename}")
        self.logger.info(f"Keep intermediate files: {keep_intermediate}")
        self.logger.info("")

    def _determine_base_filename(self) -> str:
        """
        Determine the base filename stem for output files.

        This automatically detects the date range from either:
        - Monthly files in monthly_dir, or
        - Existing combined file in input_path

        Returns the stem following pattern: carbontracker_grid-data_YYYY-MM_YYYY-MM
        """
        if self.monthly_dir and self.monthly_dir.exists():
            self.logger.info("Detecting date range from monthly files...")
            base = detect_date_range_from_monthly(self.monthly_dir)
            self.logger.info(f"Detected: {base}")
            return base

        if self.input_path and self.input_path.exists():
            self.logger.info("Detecting date range from combined file...")
            base = detect_date_range_from_combined(self.input_path)
            self.logger.info(f"Detected: {base}")
            return base

        # Fallback - will be set later when files are actually processed
        return "carbontracker_grid-data"

    def run_full_pipeline(self) -> Path:
        """
        Run the complete processing pipeline.

        This executes all steps in sequence:
        1. Combine monthly files (if needed)
        2. Fill gaps
        3. Aggregate to half-hourly
        4. Set timezone
        5. Validate output
        6. Clean up intermediate files (if keep_intermediate=False)

        Returns
        -------
        Path
            Path to final processed file

        Raises
        ------
        ValueError
            If neither input_path nor monthly_dir is provided
        """
        self.logger.info("=" * 80)
        self.logger.info("STARTING GRID DATA PROCESSING PIPELINE")
        self.logger.info("=" * 80)
        self.logger.info("")

        start_time = datetime.now()

        # Step 0: Determine input file (combine monthly if needed)
        input_file = self._get_or_create_combined_file()

        # Step 1: Fill gaps
        self.logger.info("=" * 80)
        self.logger.info("STEP 1: GAP FILLING")
        self.logger.info("=" * 80)
        gapfilled_file = self.fill_gaps(input_file)

        # Step 2: Aggregate to half-hourly
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info("STEP 2: HALF-HOURLY AGGREGATION")
        self.logger.info("=" * 80)
        half_hourly_file = self.aggregate_half_hourly(gapfilled_file)

        # Step 3: Set timezone
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info("STEP 3: TIMEZONE LABELING")
        self.logger.info("=" * 80)
        final_file = self.set_timezone(half_hourly_file)

        # Final validation
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info("FINAL VALIDATION")
        self.logger.info("=" * 80)
        self._validate_final_output(final_file)

        # Clean up intermediate files if requested
        if not self.keep_intermediate:
            self.logger.info("")
            self.logger.info("=" * 80)
            self.logger.info("CLEANING UP INTERMEDIATE FILES")
            self.logger.info("=" * 80)
            self.file_handler.cleanup_intermediate_files(logger=self.logger)

        elapsed = datetime.now() - start_time
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info(f"PIPELINE COMPLETE - Elapsed time: {elapsed}")
        self.logger.info("=" * 80)
        self.logger.info(f"Final output: {final_file}")
        self.logger.info(f"Logs: {log_dir() / 'grid_data_processing'}")
        self.logger.info("=" * 80)

        return final_file

    def _get_or_create_combined_file(self) -> Path:
        """
        Get input file, combining monthly files if needed.

        Returns
        -------
        Path
            Path to combined/input file for processing
        """
        if self.input_path and self.input_path.exists():
            self.logger.info(f"Using existing combined file: {self.input_path}")
            return self.input_path

        if self.monthly_dir and self.monthly_dir.exists():
            self.logger.info(f"Combining monthly files from: {self.monthly_dir}")
            return self.combine_monthly_files()

        raise ValueError(
            "Must provide either input_path (combined file) or monthly_dir (monthly files)"
        )

    def combine_monthly_files(
        self,
        monthly_dir: Optional[Path] = None,
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Combine monthly parquet files into a single file.

        Parameters
        ----------
        monthly_dir : Path, optional
            Directory containing monthly files. Uses self.monthly_dir if not provided.
        output_path : Path, optional
            Output file path. Auto-generates if not provided.

        Returns
        -------
        Path
            Path to combined file
        """
        monthly_dir = monthly_dir or self.monthly_dir

        if output_path is None:
            output_path = self.file_handler.get_step_output_path("step0_combined")

        self.logger.info(f"Input directory: {monthly_dir}")
        self.logger.info(f"Output file: {output_path}")
        self.logger.info("")

        combined_path = combine_monthly_files(
            monthly_dir=monthly_dir,
            output_path=output_path,
            logger=self.logger
        )

        self.state["combined_file"] = combined_path

        # Mark as intermediate unless keep_intermediate is True
        if not self.keep_intermediate:
            self.file_handler.mark_as_intermediate(combined_path)

        return combined_path

    def fill_gaps(
        self,
        input_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        use_progressive: bool = True
    ) -> Path:
        """
        Fill missing data gaps using progressive multi-stage approach.

        The progressive approach runs multiple passes with decreasing linear
        interpolation thresholds, allowing the gradient method to work with
        progressively cleaner reference data. This produces better results
        than a single-pass approach.

        Checkpoints are saved after each stage in the output directory, allowing
        detailed analysis of which gaps were filled at which stage.

        Parameters
        ----------
        input_path : Path, optional
            Input file. Uses state if not provided.
        output_path : Path, optional
            Output file path for final result. Auto-generates if not provided.
        use_progressive : bool
            If True, use progressive multi-stage filling (recommended).
            If False, use simple 3-step filling for backward compatibility.

        Returns
        -------
        Path
            Path to gap-filled file
        """
        input_path = input_path or self.state.get("combined_file") or self.input_path

        if output_path is None:
            output_path = self.file_handler.get_step_output_path("step1_gapfilled")

        self.logger.info(f"Input file: {input_path}")
        self.logger.info(f"Output file: {output_path}")
        self.logger.info("")

        if use_progressive:
            # Import the progressive gap filling function
            from grid_data_processing.gap_filling import fill_all_gaps_progressive

            # Create checkpoint directory
            checkpoint_dir = self.output_dir / "gap_filling_checkpoints"
            checkpoint_dir.mkdir(parents=True, exist_ok=True)

            self.logger.info(f"Using progressive gap filling strategy")
            self.logger.info(f"Checkpoints will be saved to: {checkpoint_dir}")
            self.logger.info("")

            # Run progressive gap filling pipeline
            filled_df, stats = fill_all_gaps_progressive(
                input_path=input_path,
                config=self.config["gap_filling"],
                output_dir=checkpoint_dir,
                logger=self.logger,
                interactive=False  # Always non-interactive
            )

            # Save final gap-filled data
            self.logger.info(f"\nSaving final gap-filled data to: {output_path}")
            filled_df.write_parquet(output_path, compression="snappy", statistics=True)
            self.logger.info(f"✓ Gap-filled data saved ({filled_df.height:,} rows)")

            # Save comprehensive statistics
            import json
            log_base_dir = log_dir() / "grid_data_processing"
            stats_path = log_base_dir / f"gap_filling_progressive_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(stats_path, 'w') as f:
                json.dump(stats, f, indent=2)
            self.logger.info(f"✓ Statistics saved: {stats_path}")
            self.logger.info("")

        else:
            # Use simple gap filling for backward compatibility
            from grid_data_processing.gap_filling import fill_all_gaps

            self.logger.info(f"Using simple 3-step gap filling")
            self.logger.info("")

            filled_df, audit_df, stats = fill_all_gaps(
                input_path=input_path,
                config=self.config["gap_filling"],
                logger=self.logger,
                interactive=False
            )

            # Save gap-filled data
            self.logger.info(f"Saving gap-filled data to: {output_path}")
            filled_df.write_parquet(output_path, compression="snappy", statistics=True)
            self.logger.info(f"✓ Gap-filled data saved ({filled_df.height:,} rows)")

            # Save audit log to logs directory
            log_base_dir = log_dir() / "grid_data_processing"
            audit_path = log_base_dir / f"gap_filling_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"

            if not audit_df.is_empty():
                audit_df.write_parquet(audit_path)
                self.logger.info(f"✓ Audit log saved: {audit_path}")

            # Save stats to logs directory
            import json
            stats_path = log_base_dir / f"gap_filling_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(stats_path, 'w') as f:
                stats_json = {k: v for k, v in stats.items() if k != "gap_analysis"}
                json.dump(stats_json, f, indent=2)
            self.logger.info(f"✓ Statistics saved: {stats_path}")
            self.logger.info("")

        self.state["gapfilled_file"] = output_path

        # Mark as intermediate unless keep_intermediate is True
        if not self.keep_intermediate:
            self.file_handler.mark_as_intermediate(output_path)

        return output_path

    def aggregate_half_hourly(
        self,
        input_path: Optional[Path] = None,
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Aggregate to half-hourly intervals.

        Parameters
        ----------
        input_path : Path, optional
            Input file. Uses state if not provided.
        output_path : Path, optional
            Output file path. Auto-generates if not provided.

        Returns
        -------
        Path
            Path to aggregated file
        """
        input_path = input_path or self.state.get("gapfilled_file")

        if output_path is None:
            output_path = self.file_handler.get_step_output_path("step2_half-hourly")

        self.logger.info(f"Input file: {input_path}")
        self.logger.info(f"Output file: {output_path}")
        self.logger.info("")

        half_hourly_df = aggregate_to_half_hourly(
            input_path=input_path,
            config=self.config["aggregation"],
            step_minutes=self.config["data_frequency_minutes"],
            logger=self.logger
        )

        half_hourly_df.write_parquet(output_path, compression="snappy", statistics=True)
        self.logger.info(f"✓ Half-hourly data saved: {output_path}")
        self.logger.info("")

        self.state["half_hourly_file"] = output_path

        # Mark as intermediate unless keep_intermediate is True
        if not self.keep_intermediate:
            self.file_handler.mark_as_intermediate(output_path)

        return output_path

    def set_timezone(
        self,
        input_path: Optional[Path] = None,
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Set (label) timezone on timestamps.

        IMPORTANT: This does NOT convert times. The data is already in the target
        timezone; this step just adds the timezone label to naive timestamps.

        Parameters
        ----------
        input_path : Path, optional
            Input file. Uses state if not provided.
        output_path : Path, optional
            Output file path. Auto-generates if not provided.

        Returns
        -------
        Path
            Path to timezone-labeled file (final output)
        """
        input_path = input_path or self.state.get("half_hourly_file")

        if output_path is None:
            output_path = self.file_handler.get_step_output_path("step3_final")

        self.logger.info(f"Input file: {input_path}")
        self.logger.info(f"Output file: {output_path}")
        self.logger.info("")

        tz_df = set_timezone(
            input_path=input_path,
            target_tz=self.config["timezone"]["target"],
            logger=self.logger
        )

        tz_df.write_parquet(output_path, compression="snappy", statistics=True)
        self.logger.info(f"✓ Timezone-labeled data saved: {output_path}")
        self.logger.info("")

        self.state["final_file"] = output_path

        # Final output is NEVER marked as intermediate

        return output_path

    def _validate_final_output(self, file_path: Path) -> None:
        """
        Run validation checks on final output.

        Saves validation report to logs directory alongside log files.
        """
        self.logger.info("Running final validation checks...")
        self.logger.info("")

        df = pl.read_parquet(file_path)

        validation_report = validate_processed_data(
            df=df,
            expected_interval_minutes=self.config["aggregation"]["target_interval_minutes"],
            logger=self.logger
        )

        # Save validation report to logs directory
        log_base_dir = log_dir() / "grid_data_processing"
        report_path = log_base_dir / f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        with open(report_path, "w") as f:
            f.write("GRID DATA PROCESSING - VALIDATION REPORT\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"File: {file_path}\n")
            f.write(f"Generated: {datetime.now()}\n\n")
            for key, value in validation_report.items():
                f.write(f"{key}: {value}\n")

        self.logger.info(f"✓ Validation report saved: {report_path}")
        self.logger.info("")