# Weather Data Retrieval

Welcome! The `weather_data_retrieval` package makes it easy to download weather and climate reanalysis data for your marginal emissions modeling projects.

## What Does This Package Do?

This package helps you retrieve large-scale weather datasets from public sources with minimal hassle. Whether you need a few months of data for a pilot study or years of global coverage for production models, we've got you covered.

**Currently supported:**
- **ERA5** (global reanalysis, 0.25° resolution, hourly)
- **ERA5-Land** (land-focused, 0.1° resolution, hourly)

Both are accessed via the Copernicus Climate Data Store (CDS) API.

!!! note "Expansion Coming Soon"
    Open-Meteo and additional providers are on the roadmap! See the [project roadmap](../../PROJECT_ROADMAP/) for details.

## Key Features

✨ **Two ways to work**: Interactive wizard for exploration, or JSON configs for reproducible pipelines

📦 **Smart downloads**: Automatically chunks data by month, handles retries, and skips files you already have

⚡ **Parallel downloads**: Speed up large requests with concurrent downloads

📝 **Production-ready logging**: Every download is logged with timestamps, configurations, and any issues

🔧 **HPC-friendly**: Includes batch scripts and settings optimized for high-performance computing environments

## Quick Example

### Interactive Mode
```bash
# Just run the command and follow the prompts
osme-weather
```

### Batch Mode
```bash
# Use a configuration file for reproducible downloads
osme-weather --config my_download.json
```

## What You'll Need

1. **Python 3.11+** (we recommend using conda or mamba)
2. **A CDS account** (free registration at [https://cds.climate.copernicus.eu](https://cds.climate.copernicus.eu))
3. **Your CDS API key** (found in your CDS profile after registration)
4. **Disk space** (varies by region and date range; the tool estimates this for you)

## Installation

The weather data retrieval package is part of the `open-source-marginal-emissions` monorepo. 

From the repository root:

```bash
# Install in development mode
pip install -e packages/weather_data_retrieval

# Or install the full project with all packages
pip install -e .
```

This makes the `osme-weather` and `wdr` commands available in your terminal.

## Next Steps

- **New to this package?** Start with the [Quickstart Guide](quickstart.md) for a step-by-step first download
- **Ready to automate?** Check out the [User Guide](user-guide.md) for batch configurations
- **Need specific config details?** See the [Configuration Reference](configuration.md)
- **Running into issues?** Visit [Troubleshooting](troubleshooting.md) for common problems and solutions
- **Want to understand the code?** Browse the [API Reference](codebase.md)

## How This Fits Into Your Workflow

The weather data retrieval package is the **first step** in the OSME pipeline:

1. **weather_data_retrieval** ← *You are here* – Download raw weather data
2. **grid_data_retrieval** – Download electricity grid data  
3. **data_cleaning_and_joining** – Align and integrate datasets  
4. **marginal_emissions_modelling** – Build your MEF models

The data you download here gets saved to `data/<dataset_short_name>/raw/` and is ready for the next steps in your analysis.

## Getting Help

- Check the [Troubleshooting](troubleshooting.md) page for common issues
- Review the examples in the [User Guide](user-guide.md)
- Open an issue on [GitHub](https://github.com/danielkaupa/open-source-marginal-emissions/issues)
- Read the detailed [API documentation](codebase.md) for advanced usage

---

*Let's get started! Head to the [Quickstart Guide](quickstart.md) →*
