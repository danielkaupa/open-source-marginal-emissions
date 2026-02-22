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
from weather_data_processing.pipeline.step2_masking import MaskingPipeline, HAS_MPI
from weather_data_processing.pipeline.step3_consolidation import ConsolidationPipeline
from weather_data_processing.pipeline.step4_temporal import TemporalPipeline
from weather_data_processing.pipeline.step5_aggregation import AggregationPipeline
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
        data_dir=data_dir(create=True),
        logger=logger
    )

    result = pipeline.run(grib_dir=grib_dir)

    return result


def run_masking_step(config: PipelineConfig, grib_dir: Optional[Path], logger, mask_results=None) -> dict:
    """Execute Step 2: GRIB Masking for all configured masks."""
    if config.geographic is None:
        logger.warning("Geographic config not provided, skipping Step 2")
        return {}

    logger.info("", force=True)
    logger.info("#" * 72, force=True)
    logger.info("# EXECUTING STEP 2: GRIB MASKING", force=True)
    logger.info("#" * 72, force=True)
    logger.info("", force=True)

    base = data_dir(create=True)
    masks_cfg = config.geographic.masks

    # If Step 1 was run in the same session, use its mask file paths directly.
    # Otherwise, discover mask files from disk for each configured mask.
    def _find_mask_files(mask_cfg, idx):
        """Find mask parquet + metadata files on disk for a given MaskConfig."""
        from osme_common.paths import resolve_under
        import glob as _glob

        country_token = config.geographic.boundary.country_name.upper().replace(" ", "_")
        mask_dir = resolve_under(base, mask_cfg.mask_dir)
        meta_dir = resolve_under(base, mask_cfg.metadata_dir)

        if mask_cfg.inclusion_mode == "combined":
            mode_str = f"combined{mask_cfg.fraction_threshold}"
        else:
            mode_str = mask_cfg.inclusion_mode

        pattern = f"{mask_cfg.dataset_prefix}_{country_token}_mask_{mode_str}_*.parquet"
        matches = sorted(mask_dir.glob(pattern))

        if not matches:
            raise FileNotFoundError(
                f"No mask file found for mode={mask_cfg.inclusion_mode} "
                f"threshold={mask_cfg.fraction_threshold} in {mask_dir}. "
                f"Run --step geographic first."
            )

        mask_file = matches[-1]  # most recent if multiple
        meta_file = meta_dir / (mask_file.stem + ".json")

        if not meta_file.exists():
            raise FileNotFoundError(f"Mask metadata not found: {meta_file}")

        return mask_file, meta_file

    all_results = {}

    for i, mask_cfg in enumerate(masks_cfg):
        mode_label = (
            f"combined{mask_cfg.fraction_threshold}"
            if mask_cfg.inclusion_mode == "combined"
            else mask_cfg.inclusion_mode
        )

        logger.info(f"  [{i+1}/{len(masks_cfg)}] Masking with: {mode_label}", force=True)

        try:
            # Get mask file — from in-memory results or disk
            if mask_results and i < len(mask_results.masks):
                sr = mask_results.masks[i]
                mask_file = sr.mask_file
                meta_file = sr.metadata_file
            else:
                mask_file, meta_file = _find_mask_files(mask_cfg, i)

            logger.info(f"    Mask file: {mask_file.name}", force=True)

            pipeline = MaskingPipeline(
                mask_file=mask_file,
                mask_metadata_file=meta_file,
                geographic_config=config.geographic,
                data_paths=config.data_paths,
                logger=logger,
            )

            # Resolve worker count from config
            par = config.parallelization
            if par.mode == "manual" and par.manual_workers:
                n_workers = par.manual_workers
            else:
                n_workers = detect_environment().recommended_workers()

            use_mpi = par.prefer_mpi and HAS_MPI
            result = pipeline.run(use_mpi=use_mpi, max_workers=n_workers)
            all_results[mode_label] = result

        except Exception as e:
            logger.error(f"    Masking failed for {mode_label}: {e}", force=True)
            import traceback
            logger.debug(traceback.format_exc())

    return all_results



_ERA5_STATIC       = ["frac_in_region"]
_ERA5_INTENSIVE    = ["u10", "v10", "u100", "v100", "t2m", "tcc", "hcc", "mcc",
                      "lcc", "kx", "cvh", "cvl", "lai_hv", "lai_lv"]
_ERA5_RATE_SHAPED  = ["ssr", "ssrc", "ssrd", "ssrdc", "str", "strc", "strd",
                      "strdc", "tsr", "tsrc", "ttr", "ttrc", "cdir", "fdir", "uvb"]
_ERA5_EVEN_SPLIT   = ["tp"]
_ERA5_WIND_PAIRS   = {"10m": ("u10", "v10"), "100m": ("u100", "v100")}


def run_consolidation_step(config: PipelineConfig, logger) -> dict:
    base = data_dir(create=True)
    interim = resolve_under(base, config.data_paths.interim_dir)
    input_dir = interim / "masked"
    if not input_dir.exists():
        raise FileNotFoundError(f"Masked parquet directory not found: {input_dir}. Run --step masking first.")
    modes = config.temporal_partitioning.modes if config.temporal_partitioning else ["annual"]
    pipeline = ConsolidationPipeline(
        input_dir=input_dir,
        output_dir=interim / "consolidation" / "consolidated",
        modes=modes,
        overwrite=True,
        cleanup_temp=False,
        logger=logger,
    )
    return pipeline.run(use_mpi=config.parallelization.prefer_mpi and HAS_MPI)


def run_temporal_step(config: PipelineConfig, logger) -> dict:
    base = data_dir(create=True)
    interim = resolve_under(base, config.data_paths.interim_dir)
    input_dir = interim / "consolidation" / "consolidated"
    if not input_dir.exists():
        raise FileNotFoundError(f"Consolidated parquet directory not found: {input_dir}. Run --step consolidation first.")
    dt_unit = config.temporal.interpolation.datetime_unit if (config.temporal and config.temporal.interpolation) else "us"
    pipeline = TemporalPipeline(
        input_dir=input_dir,
        output_dir=interim / "interpolated" / "boundary_fixed",
        temp_dir=interim / "interpolated",
        datetime_unit=dt_unit,
        validate=True,
        cleanup_temp=False,
        logger=logger,
        intensive_cols=_ERA5_INTENSIVE,
        rate_shaped_cols=_ERA5_RATE_SHAPED,
        even_split_cols=_ERA5_EVEN_SPLIT,
        static_cols=_ERA5_STATIC,
    )
    return pipeline.run(use_mpi=config.parallelization.prefer_mpi and HAS_MPI)


def run_aggregation_step(config: PipelineConfig, logger) -> dict:
    base = data_dir(create=True)
    interim = resolve_under(base, config.data_paths.interim_dir)
    input_dir = interim / "interpolated" / "boundary_fixed"
    if not input_dir.exists():
        raise FileNotFoundError(f"Interpolated directory not found: {input_dir}. Run --step temporal first.")
    processed = resolve_under(base, config.data_paths.processed_dir)
    agg_cfg = config.aggregation
    pipeline = AggregationPipeline(
        input_dir=input_dir,
        output_dir=processed,
        aggregation_levels=[agg_cfg.spatial.level if agg_cfg else "ADM0"],
        temporal_modes=(
            config.temporal_partitioning.modes
            if config.temporal_partitioning
            else ["annual"]
        ),
        weight_by_area=agg_cfg.spatial.weight_by_area if agg_cfg else True,
        logger=logger,
        intensive_vars=_ERA5_INTENSIVE,
        extensive_vars=_ERA5_RATE_SHAPED + _ERA5_EVEN_SPLIT,
        wind_pairs=_ERA5_WIND_PAIRS,
    )
    return pipeline.run(use_mpi=config.parallelization.prefer_mpi and HAS_MPI)


def run_full_pipeline(config: PipelineConfig, grib_dir: Optional[Path], logger):
    """Execute the complete pipeline."""
    results = {}

    # Step 1: Geographic
    if config.geographic is not None:
        results["geographic"] = run_geographic_step(config, grib_dir, logger)

    # Step 2: Masking
    if config.geographic is not None:
        # Pass in-memory mask results from Step 1 so we don't need to re-discover files
        geo_result = results.get("geographic", {})
        mask_results = geo_result.get("mask_result") if geo_result else None
        results["masking"] = run_masking_step(config, grib_dir, logger, mask_results=mask_results)

    # Step 3: Consolidation
    results["consolidation"] = run_consolidation_step(config, logger)

    # Step 4: Temporal interpolation
    if config.temporal is not None:
        results["temporal"] = run_temporal_step(config, logger)

    # Step 5: Aggregation
    if config.aggregation is not None:
        results["aggregation"] = run_aggregation_step(config, logger)

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
        # Resolve under <repo_root>/logs/ so e.g. "weather_data_processing"
        # becomes <repo_root>/logs/weather_data_processing
        log_dir_path = resolve_under(repo_root() / "logs", config.logging.log_dir)
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
        elif args.step == "masking":
            results = {"masking": run_masking_step(config, args.grib_dir, logger)}
        elif args.step == "consolidation":
            results = {"consolidation": run_consolidation_step(config, logger)}
        elif args.step == "temporal":
            results = {"temporal": run_temporal_step(config, logger)}
        elif args.step == "aggregation":
            results = {"aggregation": run_aggregation_step(config, logger)}
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