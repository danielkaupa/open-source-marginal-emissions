# Project Roadmap

This page tracks the rough priorities for each package in the `open-source-marginal-emissions` monorepo as well as the overall platform.
It summarises the plan for extending the [MSc thesis](https://github.com/danielkaupa/MSc-Thesis-OptimisingDemandResponseStrategiesForCarbonIntelligentLoadShifting) codebase into a modular, reproducible platform that supports multiple data providers, scalable computation, and transparent data-processing pipelines.

---

## `weather_data_retrieval`

**Goal:** Automated retrieval of weather datasets from APIs including ERA5 from the [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/) and [Open-Meteo](https://open-meteo.com/).

#### MVP Deliverable:
* Reproducible retrieval of ERA5-world and ERA5-land data from the Copernicus CDS API for user-defined regions and date ranges.
* Allows for both interactive CLI and batch JSON config usage.

#### Future Development:
* Implement Open-Meteo data retrieval.
* Increase robustness of dataset validation for variable availability.
* Implement functionality that allows users to view the data variables available for their selected dataset prior to selection for download.
* Improve logging output and consistency between interactive and batch modes.
* Increase robustness of estimated file size calculations prior to download.
* Add functionality for further splitting data into larger or smaller chunks based on user preference.
  * Specifically with the goal of having some files 'github compatible' (<100MB).
* Ensure that the “You already have this dataset downloaded, are you sure you want to proceed with the new download?” functionality is foolproof / optimised.

## `grid_data_retrieval`

**Goal:** Automated retrieval of electricity grid datasets from APIs including [Electricity Maps](https://portal.electricitymaps.com/data-explorer/overview), [International Energy Agency](https://www.iea.org/data-and-statistics/data-tools/real-time-electricity-tracker), and country-specific sources such as [CarbonTracker India](https://carbontracker.in/).

#### MVP Deliverable:
* Reproducible retrieval of electricity grid data from carbontracker.in for user-defined date ranges.
* Allows for both interactive CLI and batch JSON config usage.
* Attempt to use existing library for CLI (different strategy from weather_data_retrieval)

#### Future Development:
* Implement Electricity Maps data retrieval.
* Implement IEA data retrieval.
* Implement country-specific data retrieval for additional countries beyond India.
    * Desired test regions: Argentina, Greece, South Africa, Costa Rica, Panama.
* Increase robustness of dataset validation for variable availability.
* Implement functionality that allows users to view the data variables available for their selected dataset prior to selection for download.
* Improve logging output and consistency between interactive and batch modes.
* Increase robustness of estimated file size calculations prior to download.
* Add functionality for further splitting data into larger or smaller chunks based on user preference.
  * Specifically with the goal of having some files 'github compatible' (<100MB).
* Ensure that the “You already have this dataset downloaded, are you sure you want to proceed with the new download?” functionality is foolproof / optimised.


## `data_cleaning_and_joining`

**Goal:** Automated cleaning of raw weather and grid datasets including:
* Profiling and filling gaps where needed.
* Aligning datasets to common temporal frequencies (e.g., 30-minutely).
* De-accumulating weather variables where necessary (e.g., ERA5 precipitation).
* Aggregating or disaggregating grid data to common temporal frequencies.
* Joining weather and grid datasets on common axes (time, region).

#### MVP Deliverable:
* Process weather and grid data to export analysis-ready tables at 30-minutely frequency.
    * Includes gap filling, aligning of geospatial/temporal axes, de-accumulation of weather data, and aggregation/disaggregation of grid data.
* Include national average of weather data as well as data at native resolution.
* (Trim data to national boundaries - India)

#### Future Development:
* Select and trim data to national boundaries
* Allow for configurable temporal frequencies (60, 120 first - maybe 15 as final)
* Allow for configurable geospatial resolutions (regrid to coarser (aggregate) or finer (disaggregate) grids)
* Allow for export options of one master file, split files by year, size aware chunking (and github compatible files <100MB)
* Implement CLI and batch JSON config for data cleaning and joining.
* Allow for user-defined gap filling strategies when completeness is below a certain threshold.



## `marginal_emissions_modelling`

**Goal:** Allow users to develop a model for marginal emissions factors using the weather and grid data available

#### MVP Deliverable:
* Notebook style development with one for EDA and one for generating models
* Template for how to sift through data, transformations, models, and evaluation of accuracy
* Expected end results and format: datetime, MEF, AEF

#### Future Development
* Show how to incorporate additional data beyond the weather and grid information:
    * For example, it may be interesting to do weightings for the weather data based on the region it originates from.
    * This could be useful in terms of tying the weights to variables such as percentage of national electricity generation or consumption, sources of electricity generation, sources of electricity consumption (industry vs residential), population, living quality indices, or other.
* This of course brings up related questions of how does this additional data tie into the existing data we have and relate to it?
    * For example – if there is more solar production in one region – should we weight the solar radiation variables more heavily? And if so – how do we ensure that we weight it in a way that it doesn’t discount the others? Similar questions can be asked of precipitation and hydro power.
* Tie model runs to weights and biases to allow for comprehensive model and results evaluation
* Programmatically run multiple models for a basic set of variables and predefined transformations.
    * User would choose
        * Which models to be included / run
        * Which variables to use (predefined transformations)
        * Hyperparameters would revert to their defaults
        * The best result(s) would be returned to the user.
* Programmatically run all combinations of predefined variable and hyperparameter sets for a given model
    * User would choose:
        * 1 model to be run
        * Set of variables to use and test combinations of (predefined transformations)
        * Set of hyperparameters to use and test combinations of
    * Would show the user all of the different results.
* Incorporate ChatGPT or other tool to be able to look into your code and recommend what the next steps would be / what model they would recommend.
* Provide a few different potential transformations – or links to resources for where to learn about which ones would be appropriate under these circumstances.
    * Pursue data transformations (replacing originals)



## `residential_electricity_data_retrieval`

**Goal:** Automated retrieval of open-source residential electricity consumption datasets from APIs. Potential sources include [Energy Dashboard UK](https://www.energydashboard.co.uk/live) and country-specific sources.

#### MVP Deliverable:
* Reproducible retrieval of residential electricity consumption data from any open-source API.

#### Future Development
* CLI interface for user interaction showing available datasets, variables, date ranges.
* Batch JSON config for automated retrieval.
* Data validation and completeness checks.
* Gap filling strategies for missing data.


## `optimisation`

**Goal:** Module for running optimisation processes that determine the most efficient scheduling or allocation of electricity demand, based on marginal emissions and operational constraints.

#### MVP Deliverable:
* Module that performs optimisation for a predefined set of constraints and time periods (e.g., weekly or monthly).
* Accepts and validates all required inputs (constraints, data sources, solver selection).
* Produces a reproducible output containing the optimised schedule or decision variables, as well as summary statistics and diagnostics.
* Support one solver (greedy or MILP).

#### Future Development
* Implement new solvers with predefined constraints
    * Greedy, MILP, continuous solvers, and potentially heuristic/metaheuristic algorithms.
    * Automated logging of optimisation runs, constraints used, and computational statistics to allow for comparison of solver performance across constraints and datasets.
* Allow for user-defined constraints and solvers
    * Enhanced modularity to allow plug-and-play functionality for new solvers or constraint sets without affecting the broader pipeline
    * Must handle both continuous and mixed-integer constraint definitions.
    * Implement clear error handling and validation if incompatible constraints or solvers are chosen.
* Enables modular inclusion of input metrics and variables.
  * Provides scripts to flexibly pre-compute necessary inputs based on user input (e.g., city-week shards, household floors, regional demand factors).
  * Validates that required inputs exist before running optimisation.
  * Needed because these may require significant processing to determine
* Allow user to select execution mode:
  * Local (small dataset or short time horizon such as a week or month).
  * HPC (large-scale or full-period optimisation).
* Provides estimates of required computational resources (RAM, runtime) before execution, based on dataset size and solver selection.
* Supports efficient data handling through Polars or other lazy computation backends (potential C++ integration if performance critical).
* Allows user to define optimisation periods (e.g., week, month) and perform proportional scaling for data that spans larger intervals (e.g., city/quarter).
* Web-based form or graphical interface for defining optimisation constraints, solver selection, and execution parameters (building upon the command-line interface).
* Implementation should include memory warnings and dynamic scaling for dataset size.
* Develop a comprehensive reference list of all possible constraint and variable types, with example definitions and sample input files.
* Potential future requirement: automatic retrieval of regional electricity usage or consumption profiles to feed regional-level optimisation scenarios.


---

## Overall Platform

**Goal:** To provide a unified, user-friendly entry point and a robust technical foundation for the entire open-source-marginal-emissions platform. This involves creating intuitive user interfaces, seamless workflows, and shared infrastructure that enables modularity, reproducibility, and scalability.

#### 1. User Journey & Orchestration (osme-orchestrator)
This is a new, high-level package that guides users through the platform's capabilities, acting as the main entry point.

##### MVP Deliverable:
* A Command-Line Interface (CLI) wizard that interactively guides the user through the primary use cases:
    * "I want to download data." -> Guides user through weather_data_retrieval and grid_data_retrieval configuration.
    * "I have data and want to build a Marginal Emissions model." -> Guides user through data_cleaning_and_joining and then into the marginal_emissions_modelling notebook templates.
    * "I have a model and data, and I want to run an optimisation." -> Guides user through the optimisation module setup.
* The wizard generates the necessary JSON configuration files for batch execution in other modules.

##### Future Development:
* Web-based UI: A simple Streamlit or Dash application that provides the same guided experience as the CLI wizard, with forms for data selection, model parameters, and optimisation constraints.
* "Recipe" System: Pre-defined, end-to-end JSON configurations for common scenarios (e.g., "India 2023 MEF Model," "UK Demand Shifting Optimisation").
* Project Scaffolding: Automatically creates a well-structured project directory with data/raw, data/processed, models/, config/ folders.

#### 2. Shared Infrastructure & Core Utilities (osme-core)
This package contains the shared code that all other modules depend on.

##### MVP Deliverable:
* Unified Configuration Management: A single, validated JSON schema for all module configurations. Handles credentials (via environment variables or a secure vault), data directories, and execution parameters.
* Standardized Logging: A common logging format and lifecycle (info, debug, warning, error) across all modules, with structured logging for easy parsing.
* Common Data Types & Models: Pydantic models or Python dataclasses for core concepts like TemporalRange, GeographicalRegion, DataSource.
* Base Classes for Retrieval: Abstract base classes that define the interface for any data retrieval module, ensuring consistency.

##### Future Development:
* Plugin Architecture: A formal system for adding new data providers, solvers, or gap-filling methods without modifying the core code.
* Health & Performance Monitoring: Utilities for tracking memory usage, runtime, and data validation metrics across modules.
* Serialization Utilities: Standardized methods for saving/loading models, optimisation results, and large datasets (e.g., using joblib or Apache Parquet).

#### 3. Execution & Compute Layer (osme-compute)
This component abstracts the computational environment, enabling both local development and scalable cloud/HPC execution.

##### MVP Deliverable:
* Local Execution Engine: The default mode, running all processes on the user's local machine. Includes the resource estimation warnings mentioned in the optimisation roadmap.

##### Future Development:
* Workflow Orchestration: Integration with workflow engines like Prefect or Dagster to define the entire data pipeline (retrieve -> clean -> model -> optimise) as a single, monitored, and re-runnable DAG (Directed Acyclic Graph).

* Cloud & HPC Abstraction:
    * Azure/AWS Batch Integration: Package and submit jobs to cloud batch services for at-scale runs.
    * Slurm/HPC Support: Script generation and job submission for High-Performance Computing clusters.
    * Data & Result Caching: A smart caching layer to avoid re-downloading or re-processing data that has not changed.