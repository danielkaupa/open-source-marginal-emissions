# A Public-Data Framework Marginal Emissions Factor Estimation
<br>


## Introduction to This Repository

This file provides an overview of the project and its significance, brief context on the subject matter, and an outline of the repository structure.
<br>

Table of Contents:
* [Project Purpose](#project-purpose)
* [Project Context](#project-context)
* [Data](#data)
    * [What Data Does this Project Use?](#what-data-does-this-project-use)
    * [Where is the data coming from?](#where-is-the-data-coming-from)
    * [Similar Resources Available](#similar-resources-available)
* [Project Significance](#project-impact-and-significance)

* [Repository Structure](#repository-structure)

<br>


The codebase is split into four modules that can evolve independently:
•	weather_data_retrieval/ — packaged Python CLI for ERA5/ERA5-Land retrieval (interactive & batch/HPC). ✅ available now
•	grid_data_retrieval/ — stubs/placeholders for grid data connectors. 🚧 planned
•	data_cleaning_and_joining/ — cleaning, de-accumulation, time alignment, memory-efficient storage. 🚧 planned
•	marginal_emissions_modelling/ — exploratory/production models for marginal emission factors. 🚧 planned
See information/core_concepts_and_definitions copy.md for terminology and conceptual background.



License
This project is released under the terms in [LICENSE](./LICENSE).

Citation / Acknowledgements
•	ERA5/ERA5-Land data provided by Copernicus Climate Change Service (C3S).
•	Retrieval uses cdsapi and ECMWF datastores.
If you use this toolkit in research, please cite the ERA5/ERA5-Land dataset and link to this repository.

## Project Purpose

The purpose of this project is to turn publicly available weather and grid data into actionable, household-level carbon reductions by estimating marginal emissions factors (MEFs).
<br>

This objective is achieved through the development of
1. A pipeline to process and combine public weather and grid data (demand and emissions).
2. A methodology for estimating location and time specific marginal emission factors.



<br>

Though this project was developed on data covering households in Delhi and Mumbai, India, the methodologies and framework established here could be applicable to regions around the globe.

<br>

## Project Context

Marginal emissions are an important concept when evaluating the carbon impact of electricity usage, and they differ from the better known and more widely used average emissions. Average emissions tell you the carbon intensity of all electricity generated over some period, while marginal emissions tell you the carbon intensity of the next unit of electricity (or the last unit avoided). When evaluating the specific impacts of electricity usage in a given time and location, marginal emissions become much more relevant.

<br>

<details>
<summary><strong>Average Emissions</strong></summary>
<br>

**Definition:** The emissions associated with *all* of the energy sources that have been used to produce electricity over a given time period.
<br>

**Example:** Say over the course of a day, 100 kWh of electricity was produced from a solar farm, 200 kWh from a coal plant, and 500 kWh from a gas plant. Each of these energy sources has a specific emissions factor, which represents the amount of CO2 emitted per kWh of electricity generated. The average emissions associated with the total 800 kWh consumed would be the weighted average of the emissions factors for each source of energy, based on how much each contributed to the total.
<br>

See the [emission factors](/core_concepts_and_definitions.md) for more detail.

<br>
</details>
<details>
<summary><strong>Marginal Emissions</strong></summary>
<br>


**Definition** The emissions associated with the *next* X amount of electricity consumed (or not consumed), and the energy source that supplies this demand.
<br>

**Example:** Assume that on a daily basis my house consumes 12 kWh of electricity. If I were install an air conditioning unit which consumes on average 9 kWh per day, the local grid  would need to find an energy source which could supply that additional energy when I turn on the AC. Then depending on the sources already being used to generate electricity and operational constraints, this additional demand may result in more coal or gas being burned in an already operating generator, or a new generator(s) switched on to meet the demand. The emissions associated with these energy needed to supply that next 9kWh specifically are the marginal emissions and the impact of that specific action.
<br>

**Additional Notes:**
* *Marginal Emissions and Generator Capacity*: The marginal supply is not always a brand-new unit turning on. Sometimes the cheapest feasible response is to ramp up an alreadyg-running generator from say 50% to 80% output; other times its' starting another unit. Because generator's heat rates (fuel per kWh) can improve or worse with the load, the marginal emissions per kWh can be higher or lower than the average at that moment. Transmission limits, renewable curtailment, and start-up/ramping costs can also shift which unit is marginal. That’s why marginal and average emissions often diverge—and why timing matters. ([AMPS](https://www.amps.org.uk/wp-content/uploads/2023/06/AMPS-Guidance-for-determination-of-thermal-input-power-of-generators-.pdf))
* *Why “unexpected vs. expected” demand matters*. Grid operators plan most generation day-ahead. Marginal emissions describe the incremental adjustment relative to that plan when your behavior changes (using more, less, or shifting in time). That’s the quantity optimization tries to influence. [ISO New England](https://www.iso-ne.com/static-assets/documents/2023/06/imm-markets-primer.pdf)

<br>

Further information about energy, emissions, the grid, and techniques used in this project can be found in the [core_concepts_and_definitions](/core_concepts_and_definitions.md) file.
</details>
<br>

## Methodology - Marginal Emission Factor Estimations


### This project’s approach

This project estimates national marginal emissions factors (MEFs) for India using a generalized additive model (GAM) with a smooth in net load (Q) and smooths for weather, plus simple linear/time controls.
The GAM model was chosen because operationally useful MEFs need not only strong level fit so the model tracks the data, but also stable derivatives so ∂CO₂/∂Q behaves sensibly across regimes.
Smooth GAMs let us learn curvature in dispatch without the wiggle of global polynomials or the edge jumps of binning, yielding stable, monotone-ish marginal effects after light regularization.
We also calibrate the model’s marginal effects so they match the realized slope from short-horizon ramps (units-aligned MEFs).


<br>
<br>



<details>
<summary>Benefits of this approach</summary>
<br>

☑️ **Efficacy**:
* Produces stable MEFs across regimes due to smoothness with units-aligned via calibration.
* Reduces confounding by using weather features as proxies for both demand (heating/cooling) and renewable output (solar/wind); and by including month/hour fixed effects that absorb strong diurnal/seasonal cycles and routine operating patterns.
* Yields more stable MEF estimates by using a quadratic fit in load $Q$ and using the local derivative within each bin.

☑️ **Simplicity**:
* Uses a small set of widely understood signals—demand, emissions, and weather—keeping data needs low and the method accessible to non-experts.


☑️ **Transparency**:
* Provides clear visibility into the model's workings and assumptions with its inspectable smooths and clear calibration step

</details>
<br>

<details>
<summary>Limitations of this approach</summary>
<br>

* Estimates are directional and order-of-magnitude accurate, and should not be interpreted as exact causal effects.
* Residual endogeneity can remain (unobserved outages, transmission congestion, net imports/exports, fuel price shock)
* Less accurate than more complex models that explicitly ingest net imports, renewable curtailment, and network constraints (e.g., dispatch/hybrid approaches).
* Rank correlations improve with ramp size and are **modest overall** (typ. ≤ \~0.55–0.6 at high ramps).
</details>
<br>

## Data

As much of the data used in this project proved to be too large to share via traditional means, it has been stored in


### What Data Does this Project Use?

This project uses 3 categories of data:
 1. Nationwide Electricity and Emissions Data for India from [carbontracker.in](https://carbontracker.in/).
 2. Weather data from [ERA5-Land](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=overview) and [ERA5](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=overview) for locations around Delhi and Mumbai.

Note^ We use both ERA-5 Land and ERA5 global data in order to grab high resolution data for as many key variables as we can and then accept lower resolution data for additional variables or for filling gaps in the higher resolution dataset.

<br>


### Where is the data coming from?


The data used in this project is also being used in projects for the [Hitachi-Imperial Centre for Decarbonisation and Natural Climate Solutions](https://www.imperial.ac.uk/hitachi-centre/about-us/). The [Data Science Institute](https://www.imperial.ac.uk/data-science/) at Imperial, specifically Brython Caley-Davies, assisted in centralising much of the data into a locally hosted postgreSQL database.
As such the carbontracker, ERA5-Land, and customer electricity data is all accessed via this database.
The ERA5 global analysis was downloaded from the [Climate Data Store](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=overview) website.


### Similar Resources Available
<br>

**Electricity Demand & Carbon Emissions**
* [Electricity Maps](https://app.electricitymaps.com/map/72h/hourly )
* [Energy Dashboard (UK)](https://www.energydashboard.co.uk/live)
* [International Energy Agency (IEA)](https://www.iea.org/data-and-statistics/data-tools/real-time-electricity-tracker?from=2025-7-23&to=2025-8-22&category=demand)
* [US Energy Information Administration (EIA)](https://www.eia.gov/electricity/gridmonitor/dashboard/electric_overview/US48/US48)
<br>

**Weather Data**
* [Open Meteo](https://open-meteo.com/)
* [Weather Underground](https://www.wunderground.com/history)

<br>

## Project Impact and Significance

**Why this project is relevant?**

The value of this work can be summarised into three key points:

1. **Filling a geographic gap.** High-quality marginal emissions and methods exist for North America/Europe, but are scarce elsewhere. This project provides location- and time-specific MEFs for Delhi and Mumbai, India, and a replicable path to extend them.

2. **Contributing to the literature.** It adds evidence for data-driven approaches to MEF estimation—showing that a lightweight, public-data specification (weather + demand/emissions with simple temporal controls) is reproducible while retaining reasonable accuracy.

<br>
In short, this work demonstrates a transparent, low-barrier pathway from public signals (weather, demand, emissions) to location- and time-specific marginal emissions and operational scheduling recommendations.

<br>

## Repository Contents


**Important Directories Summary**


**Directory Structure**
* [code_and_analysis](/code_and_analysis/) - contains the final code, files, and data used throughout the course of this project, as well as the results generated.
    * [analysis_guide](/code_and_analysis/analysis_guide.md) provides an overview of the analysis process and steps required to reproduce the results.
    * [data](/code_and_analysis/data/) - contains the various datasets both raw and intermediate used in the analysis.
    * [scripts](/code_and_analysis/scripts/) - contains the various scripts used for data processing and analysis.
<br>

* [emission_rate_methodologies](/emission_rate_methodologies/) - contains data and sample code that were evaluated when developing the methodology for estimating marginal emission factors.
    * [marginal emissions](/emission_rate_methodologies/marginal_emissions/) - contains the code on which the marginal emissions methodology was based (quantile and median binning).

<br>
```
irp-dbk24/
│   ├── 📁 code_and_analysis
│   │   ├── 📄 analysis_guide.md
│   │   ├── 📁 data
│   │   │   ├── 📁 era5
│   │   │   │   ├── 📁 grib_downloads
│   │   │   │   ├── 📁 parquets
│   │   │   │   └── 📁 weights
│   │   │   ├── 📁 hitachi_copy
│   │   │   │   └── 📁 meter_primary_files
│   │   │   ├── 📁 marginal_emissions_development
│   │   │   │   ├── 📁 logs
│   │   │   │   └── 📁 results
│   │   │   ├── 📁 optimisation_development
│   │   │   │   ├── 📁 city_week_shards
│   │   │   │   ├── 📁 full_results
│   │   │   │   ├── 📁 processing_files
│   │   │   │   └── 📁 testing_results
│   │   │   └── 📁 outputs
│   │   │   │   └──  📁 metrics
│   │   ├── 📁 images
│   │   │   ├── 📁 hitachi
│   │   │   │   └──  🎞️ (various images related to hitachi database).png
│   │   │   └── 🎞️ (various images related to analysis).png
│   │   ├── 📁 scripts
│   │   │   ├── 📁 hpc_scripts_development
│   │   │   │   ├── 📁 drafts
│   │   │   │   └── 📁 logs
│   │   │   ├── 📁 processing_logs
│   │   │   ├── 📄 (various python scripts for processing and analysis).py
│   │   │   └── 📄 (various shell scripts for processing and analysis).sh
│   │   └── 📄 (various jupyter notebooks for processing and analysis).ipynb
│   ├── 📁 deliverables
│   │   ├── 📄 dbk24-final-report.pdf
│   │   ├── 📄 dbk24-project-plan.pdf
│   │   └── 📄 README.md
│   ├── 📁 documents_and_drafts
│   │   ├── 📁 final-report
│   │   ├── 📁 project-plan
│   │   └── 📁 sample_reports
│   ├── 📁 emission_rate_methodologies
│   │   ├── 📁 cea_data
│   │   ├── 📁 electricity-maps
│   │   ├── 📁 Marginal Emission Factors for Indian Power Generation
│   │   └── 📁 marginal emissions
│   ├── 📁 logbook
│   │   ├── logbook.md
│   │   └── README.md
│   ├── 📁 title
│   │   ├── README.md
│   │   └── title.toml
│   ├── 📄 README.md
│   └──  📄 core_concepts_and_definitions.md
```

<br>




Data directories

data/raw → untouched downloads (GRIB/NetCDF/CSV/Parquet, etc.)

data/interim → cleaned/resampled; partially joined

data/processed → modelling inputs (aligned tables)

data/exports → final outputs (MEF time series, figures)

data/cache → temporary artifacts

Roadmap & concepts

Project roadmap and module‑level plans: [ROADMAP.md](./information/ROADMAP.md)

Core concepts & definitions (Average vs. Marginal, Grid basics, etc.): [CORE_CONCEPTS.md](./information/core_concepts_and_definitions.md)

Contributing

License

Non‑commercial use only. For commercial licensing, see [LICENSE](./LICENSE).

Acknowledgements

This work extends an MSc thesis at Imperial College London and benefited from support by collaborators and mentors. See
[ACKNOWLEDGEMENTS.md](./information/ACKNOWLEDGEMENTS.md).



> **License:** AGPL-3.0-or-later **OR** Commercial License
> For commercial use without AGPL obligations, email **daniel.kaupa@outlook.com**
> See [COMMERCIAL-TERMS.md](./COMMERCIAL-TERMS.md) and [LICENSE](./LICENSE).