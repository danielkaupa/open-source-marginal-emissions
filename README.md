# A Public-Data Framework for Marginal Emissions Factor Estimation
<br>

Table of Contents:
- [Repository Overview](#repository-overview)
- [Project Context and Overview](#project-context-and-overview)
- [Project Purpose](#project-purpose)
- [Repository Structure and Contents](#repository-structure-and-contents)
    - [Module Overview](#module-overview)
    - [Repository Structure](#repository-structure)
- [Additional Information](#additional-information)
    - [Acknowledgements](#acknowledgements)
    - [License](#license)

<br>

## Repository Overview

The purpose of this project is to develop an open-source framework that transforms publicly available weather and grid data into directionally accurate marginal emissions factors (MEFs).

This project is currently under development, and this repository will be updated as new code is developed.

The status of the various modules can be found in the [Repository Structure and Contents](#repository-structure-and-contents) section below.


<br>

## Project Context and Overview

Marginal emissions are an important concept when evaluating the carbon impact of electricity usage, and they differ from the better known and more widely used average emissions. Average emissions tell you the carbon intensity of all electricity generated over some period, while marginal emissions tell you the carbon intensity of the next unit of electricity (or the last unit avoided). When evaluating the specific impacts of electricity usage in a given time and location, marginal emissions become much more relevant.

In order to truly calculate marginal emissions factors, one needs access to detailed grid data traditionally only held by grid operators. However, there is a growing body of research exploring the possibility of estimating marginal emissions factors using publicly available data sources, such as weather data and aggregate grid demand and emissions data.

<br>

## Project Purpose

The goal of this project is to provide a transparent, reproducible framework for estimating marginal emissions factors (MEFs) using only publicly available data sources.
In doing so, this work aims to make meaningful, time- and location-specific carbon insights available in regions where access to grid dispatch data is limited.

This framework focuses on two core capabilities:
1. **Data Acquisition and Preparation** - A pipeline to retrieve, clean, and integrate large-scale weather and generation/emissions datasets in a consistent, analysis-ready format.
<br>

2. **Marginal Emissions Estimation** - A modeling workflow for estimating MEFs that are:
    * directionally accurate,
    * stable across seasonal and diurnal conditions, and
    * transparent to inspect and extend.

While this project currently develops use cases for India, the workflow is intended to be generalizable, enabling users to adapt the approach to other regions with publicly available data.

The documentation for this repository contains more information and definitions for the core concepts of energy, emissions, the grid, and techniques used in this project.

<br>

## Repository Structure and Contents

This repository is designed as a modular framework, where each module can evolve or be replaced independently.
The top-level modules are packaged for long-term maintainability and distributed development.

<br>

### Module Overview
| Module | Description | Status |
|--------|-------------|--------|
| **weather_data_retrieval**       | Fully packaged CLI + batch utilities to download ERA5 and ERA5-Land data from ECMWF CDS. Open-Meteo under development                          | ✅ Available       |
| **grid_data_retrieval**       | CLI + batch utilities to download demand, generation, and emissions data from public grid sources.                                   | 🚧 Under Development |
| **data_cleaning_and_joining**    | Spatial alignment, temporal resampling, and integration of grid + weather datasets with memory-efficient formats. | 🚧 Under Development |
| **marginal_emissions_modelling** | Methods for estimating MEFs and evaluating models. Designed to accommodate several modelling approaches.          | 🚧 Under Development |

<br>

### Repository Structure
```
.open-source-marginal-emissions/
    ├── configs                 # Configuration files for data retrieval and processing
    │   ├── grid                    # Grid data retrieval configurations
    │   ├── pipelines               # Data processing pipeline configurations
    │   └── weather                 # Weather data retrieval configurations
    │
    ├── information             # Documentation and additional information
    │
    ├── notebooks               # Jupyter notebooks for exploration and analysis
    │
    ├── packages                                # Modular packages for different components of the framework [Run order]
    │   ├── data_cleaning_and_joining               # Data cleaning, spatial alignment, and integration [3]
    │   ├── grid_data_retrieval                     # Public grid data retrieval utilities [2]
    │   ├── marginal_emissions_modelling            # MEF estimation methods and evaluation [4]
    │   ├── osme_common                             # Common utilities and functions for the framework [All]
    │   └── weather_data_retrieval                  # ERA5 (from CDS) and Open-Meteo data retrieval [1]
    │
    └── README.md       # you are here
```

<br>

## Additional information

### Acknowledgements
This work extends an MSc thesis at Imperial College London and benefited from support by collaborators and mentors. See
[ACKNOWLEDGEMENTS](./information/ACKNOWLEDGEMENTS.md).


### License
This project is released under the terms in [LICENSE](./LICENSE).
> **License:** AGPL-3.0-or-later **OR** Commercial License
> For commercial use without AGPL obligations, email **daniel.kaupa@outlook.com**
> See [COMMERCIAL-TERMS](./COMMERCIAL-TERMS.md) and [LICENSE](./LICENSE).
