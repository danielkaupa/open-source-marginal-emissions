# Quickstart Guide

This guide will get you processing grid data in minutes. We'll walk through installation, basic usage, and common scenarios.

## Prerequisites

You need Python 3.10 or later and access to the open-source-marginal-emissions repository with the osme_common package installed.

## Installation

Navigate to the grid_data_processing package directory and install in editable mode. This creates all the command-line entry points.
```bash
cd packages/grid_data_processing
pip install -e .
```

Verify installation by checking that the command is available. Running it with no arguments will show you the help message.
```bash
gdp --help
```

You should see comprehensive help output listing all available options and showing examples of common usage patterns.

## Processing Your First Dataset

Let's process some grid data. The simplest case is when you have monthly parquet files in a directory. The pipeline will automatically combine them, fill gaps, aggregate to half-hourly, and label timezones.
```bash
gdp --monthly-dir grid_data/raw/monthly --verbose
```

The verbose flag makes the pipeline show progress on your console so you can watch what's happening. Without it, the pipeline runs silently with all output going to log files.

This command will process through several stages. First, it combines your monthly files into a single chronological dataset. Then it analyzes gaps in the data and fills them using a progressive strategy that starts with simple linear interpolation for short gaps and progressively employs more sophisticated gradient-based methods for longer gaps. After gap filling completes, the data is aggregated from five-minute to half-hourly intervals. Finally, timestamps are labeled with the Asia/Kolkata timezone.

## Understanding the Output

When the pipeline completes, you'll find several files in your output directory, which defaults to data/grid_data/processed unless you specify otherwise.

The final output is a file named something like carbontracker_grid-data_2018-11_2026-02_step3_final.parquet. The date range in the filename indicates what time period the data covers. This is your analysis-ready dataset with all gaps filled, proper aggregation, and timezone labeling.

Unless you specified keep-intermediate, the pipeline automatically cleaned up intermediate files to save disk space. However, all the logs and audit trails are preserved in the logs/grid_data_processing directory.

Check the log file to see exactly what the pipeline did. The filename includes a timestamp showing when the processing ran. Inside, you'll find complete DEBUG-level information about every step.
```bash
cat logs/grid_data_processing/grid_processing_YYYYMMDD_HHMMSS.log
```

The gap-filling statistics file provides aggregate metrics about how many gaps were found and filled at each stage.
```bash
cat logs/grid_data_processing/gap_filling_stats_YYYYMMDD_HHMMSS.json
```

## Common Scenarios

### Processing a Single Combined File

If you already have a combined parquet file from a previous run or another source, you can process it directly without the combination step.
```bash
gdp --input grid_data/raw/combined.parquet --verbose
```

This skips step zero and begins directly with gap filling.

### Keeping Intermediate Files for Analysis

During development or when you want to analyze what happens at each stage, keep all the intermediate outputs.
```bash
gdp --monthly-dir grid_data/raw/monthly --keep-intermediate --verbose
```

This preserves the combined file, the gap-filled file, and the aggregated file in addition to the final output. You can load these files to see exactly how the data evolved through the pipeline.

### Using Custom Configuration

The default configuration has been tuned for typical grid data, but you might want different parameters for your specific dataset.
```bash
gdp --monthly-dir grid_data/raw/monthly \
    --config configs/grid_data_processing/custom.json \
    --verbose
```

Copy the default configuration from the package and modify the parameters you want to change. The most commonly adjusted parameters are the gap-filling thresholds and the gradient method search window.

### Silent Operation for Automation

In production or automated workflows, you typically want the pipeline to run silently with all output going to logs.
```bash
gdp --monthly-dir grid_data/raw/monthly
```

This is the default behavior. The pipeline processes your data without any console output, logging everything to timestamped files in the logs directory. If something goes wrong, error details will appear on stderr.

## Troubleshooting

If you get a "command not found" error when trying to run gdp, the package installation didn't complete successfully or your Python scripts directory is not in your PATH. Verify that pip install completed without errors and that you can see the grid-data-processing package when you run pip list.

If the pipeline complains about not finding configuration files, check that you have a configs/grid_data_processing directory at your repository root. The pipeline searches for default_processing.json there. Alternatively, you can explicitly specify a config file path with the config option.

If processing seems very slow, this is often normal for datasets with many long gaps because the gradient method does sophisticated pattern matching. You can watch detailed progress in the log file to see exactly what stage is taking time.

## Next Steps

Now that you've processed your first dataset, you might want to understand what's happening under the hood. The [Codebase Reference](codebase.md) provides detailed documentation of all modules and functions.

If you want to customize the gap-filling behavior, start by examining the default configuration to understand what parameters control each aspect of processing. The configuration file is well-commented and explains the purpose of each setting.

For advanced usage like integrating the pipeline into larger workflows or customizing processing logic, review the Python API documentation in the Codebase Reference. The GridDataProcessor class provides programmatic control over all aspects of the pipeline.