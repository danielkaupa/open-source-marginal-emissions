# packages/weather_data_processing/src/weather_data_processing/run_pipeline.py
# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Weather Data Processing Pipeline - Main CLI
============================================

Command-line interface for running the complete weather data processing pipeline.

Usage
-----
    # Run full pipeline
    python run_pipeline.py --config configs/example_config.json

    # Run specific step only
    python run_pipeline.py --config configs/example_config.json --step geographic

    # Verbose mode
    python run_pipeline.py --config configs/example_config.json --verbose

    # Dry run (validate config without executing)
    python run_pipeline.py --config configs/example_config.json --dry-run
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from weather_data_processing.config_schema import PipelineConfig
from weather_data_processing.pipeline.step1_geographic import GeographicPipeline
from weather_data_processing.utils.parallel import detect_environment
from weather_data_processing.utils.logging import setup_logger

from osme_common.paths import data_dir, log_dir, resolve_under, repo_root


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Weather Data Processing Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full pipeline
  python run_pipeline.py --config configs/example_config.json

  # Run geographic step only
  python run_pipeline.py --config configs/example_config.json --step geographic

  # Verbose logging to console
  python run_pipeline.py --config configs/example_config.json --verbose

  # Validate configuration without running
  python run_pipeline.py --config configs/example_config.json --dry-run
        """
    )

    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to pipeline configuration JSON file"
    )

    parser.add_argument(
        "--step",
        choices=["geographic", "masking", "consolidation", "temporal", "aggregation", "all"],
        default="all",
        help="Pipeline step to run (default: all)"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose console logging (overrides config)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without executing pipeline"
    )

    parser.add_argument(
        "--grib-dir",
        type=Path,
        help="Override GRIB directory from config"
    )

    return parser.parse_args()


def print_banner(logger):
    """Print pipeline banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║      WEATHER DATA PROCESSING PIPELINE                         ║
║      ERA5 → Half-Hourly → Aggregated Time-Series             ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """
    logger.info(banner, force=True)


def print_environment_info(logger):
    """Print compute environment information."""
    env = detect_environment()

    logger.info("", force=True)
    logger.info("=" * 72, force=True)
    logger.info("COMPUTE ENVIRONMENT", force=True)
    logger.info("=" * 72, force=True)

    for line in str(env).split("\n"):
        logger.info(f"  {line}", force=True)

    workers = env.recommended_workers()
    logger.info(f"  Recommended workers: {workers}", force=True)
    logger.info("=" * 72, force=True)
    logger.info("", force=True)


def run_geographic_step(config: PipelineConfig, grib_dir: Optional[Path], logger) -> dict:
    """Execute Step 1: Geographic Processing."""
    if config.geographic is None:
        logger.warning("Geographic config not provided, skipping Step 1")
        return {}

    logger.info("", force=True)
    logger.info("#" * 72, force=True)
    logger.info("# EXECUTING STEP 1: GEOGRAPHIC PROCESSING", force=True)
    logger.info("#" * 72, force=True)
    logger.info("", force=True)

    # Resolve GRIB directory
    base = data_dir(create=True)

    if grib_dir is None:
        grib_dir = resolve_under(base, config.data_paths.grib_dir)
    else:
        grib_dir = resolve_under(base, grib_dir)

    if not grib_dir.exists():
        raise FileNotFoundError(f"GRIB directory not found: {grib_dir}")

    # Run pipeline
    pipeline = GeographicPipeline(
        config=config.geographic,
        data_base=data_dir(create=True),
        logger=logger
    )

    result = pipeline.run(grib_dir=grib_dir)

    return result


def run_full_pipeline(config: PipelineConfig, grib_dir: Optional[Path], logger):
    """Execute the complete pipeline."""
    results = {}

    # Step 1: Geographic
    if config.geographic is not None:
        results["geographic"] = run_geographic_step(config, grib_dir, logger)

    # TODO: Steps 2-5 will be added in the next phase
    logger.info("", force=True)
    logger.info("=" * 72, force=True)
    logger.info("PIPELINE STATUS", force=True)
    logger.info("=" * 72, force=True)
    logger.info("  ✓ Step 1: Geographic Processing", force=True)
    logger.info("  ⚠ Step 2: Masking (not yet implemented)", force=True)
    logger.info("  ⚠ Step 3: Consolidation (not yet implemented)", force=True)
    logger.info("  ⚠ Step 4: Temporal (not yet implemented)", force=True)
    logger.info("  ⚠ Step 5: Aggregation (not yet implemented)", force=True)
    logger.info("=" * 72, force=True)
    logger.info("", force=True)

    return results


def main():
    """Main entry point."""
    args = parse_args()
    t_start = time.perf_counter()

    # ------------------------------------------------------------------
    # Load and validate configuration
    # ------------------------------------------------------------------
    # Resolve config path: try as-is first, then under configs/ in repo root,
    # then under configs/weather_data_processing/ in repo root.
    def _resolve_config(raw: Path) -> Optional[Path]:
        candidates = [
            raw.expanduser().resolve(),
            resolve_under(repo_root(), raw),
            resolve_under(repo_root() / "configs", raw),
            resolve_under(repo_root() / "configs" / "weather_data_processing", raw),
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    config_path = _resolve_config(args.config)

    if config_path is None:
            root = repo_root()
            searched = [
                str(args.config.expanduser().resolve()),
                str(resolve_under(root, args.config)),
                str(resolve_under(root / "configs", args.config)),
                str(resolve_under(root / "configs" / "weather_data_processing", args.config)),
            ]
            print(
                f"Error: Configuration file not found: {args.config}\n"
                f"Searched:\n" + "\n".join(f"  {p}" for p in searched),
                file=sys.stderr
            )
            return 1

    try:
        config = PipelineConfig.load_from_file(config_path)
    except Exception as e:
        print(f"Error: Failed to load configuration: {e}", file=sys.stderr)
        return 1


    # Override verbose mode if specified
    if args.verbose:
        config.logging.verbose = True

    # ------------------------------------------------------------------
    # Setup logging
    # ------------------------------------------------------------------

    if config.logging.log_dir is not None:
        log_dir_path = resolve_under(repo_root(), config.logging.log_dir)
        log_dir_path.mkdir(parents=True, exist_ok=True)
    else:
        log_dir_path = log_dir(create=True)

    logger = setup_logger(
        name="pipeline",
        save_dir=log_dir_path,
        verbose=config.logging.verbose,
        module_name="weather_data_processing"
    )

    print_banner(logger)

    # ------------------------------------------------------------------
    # Dry run: validate and exit
    # ------------------------------------------------------------------
    if args.dry_run:
        logger.info("DRY RUN MODE: Validating configuration", force=True)
        logger.info("", force=True)
        logger.info("Configuration valid ✓", force=True)
        logger.info("", force=True)
        logger.info("Steps configured:", force=True)
        if config.geographic:
            logger.info("  ✓ Geographic", force=True)
        if config.temporal:
            logger.info("  ✓ Temporal", force=True)
        if config.aggregation:
            logger.info("  ✓ Aggregation", force=True)
        logger.info("", force=True)
        logger.info("Dry run complete (no processing executed)", force=True)
        return 0

    # ------------------------------------------------------------------
    # Print environment info
    # ------------------------------------------------------------------
    print_environment_info(logger)

    # ------------------------------------------------------------------
    # Execute pipeline
    # ------------------------------------------------------------------
    try:
        if args.step == "all":
            results = run_full_pipeline(config, args.grib_dir, logger)
        elif args.step == "geographic":
            results = {"geographic": run_geographic_step(config, args.grib_dir, logger)}
        else:
            logger.error(f"Step '{args.step}' not yet implemented", force=True)
            return 1

    except Exception as e:
        logger.error("", force=True)
        logger.error("=" * 72, force=True)
        logger.error("PIPELINE FAILED", force=True)
        logger.error("=" * 72, force=True)
        logger.error(f"Error: {e}", force=True)
        logger.error("=" * 72, force=True)

        import traceback
        logger.debug(traceback.format_exc())

        return 1

    # ------------------------------------------------------------------
    # Success
    # ------------------------------------------------------------------
    t_elapsed = time.perf_counter() - t_start

    logger.info("", force=True)
    logger.info("=" * 72, force=True)
    logger.info("PIPELINE COMPLETE", force=True)
    logger.info("=" * 72, force=True)
    logger.info(f"  Total time: {t_elapsed:.2f}s", force=True)
    logger.info("  Status: SUCCESS ✓", force=True)
    logger.info("=" * 72, force=True)
    logger.info("", force=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
