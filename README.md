# A Public-Data Framework Marginal Emissions Factor Estimation
<br>


## Introduction to This Repository

This file provides an overview of the project and its significance, brief context on the subject matter, and an outline of the repository structure.
<br>

Table of Contents:
* [Project Purpose](#project-purpose)
* [Project Context](#project-context)
* [Methodology - Marginal Emissions](#methodology---marginal-emission-factor-estimations)
    * [This Project's Approach](#this-projects-approach)
    * [Other Approaches to Emissions Estimation](#other-approaches-to-emissions-estimation)
* [Methodology - Optimisation](#methodology---optimisation)
    * [Constraints](#what-are-the-constraints)
    * [Equations](#constraint-equations)
* [Data](#data)
    * [What Data Does this Project Use?](#what-data-does-this-project-use)
    * [Where is the data coming from?](#where-is-the-data-coming-from)
    * [Similar Resources Available](#similar-resources-available)
* [Project Significance](#project-impact-and-significance)

* [Repository Structure](#repository-structure)

<br>

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


**The core equation for this model can be written as follows:**

```math
Y \;=\; \beta_0 \;+\; f_Q\!\big(Q_{\mathrm{std}}\big)
     \;+\; f_T(T) \;+\; f_W(W) \;+\; f_S\!\big(\log(1+S_{\mathrm{raw}})\big)
     \;+\; \mathbf{x}_{\text{lin}}^{\top}\boldsymbol{\beta} \;+\; \varepsilon
```

Where:
* \$Y\$ is tons of \$\mathrm{CO}\_2\$ emitted in the interval.
* \$Q\_{\mathrm{std}}\$ is standardized net load: \$Q\_{\mathrm{std}} = (Q\_{\mathrm{raw}}-\mu\_Q)/\sigma\_Q\$.
    * net load in this case is demand minus renewable generation.
* \$f\_Q,f\_T,f\_W,f\_S\$ are smooth terms learned by pyGAM (splines with curvature penalties).
* \$\mathbf{x}\_{\text{lin}}\$ are linear/context features: hydro_share, wind_dir_sin, wind_dir_cos, is_sunny, doy_sin, doy_cos, hour_sin, hour_cos, is_weekend.
* \$\varepsilon\$ is the error term.


And the **Penalized objective** (second-derivative smoothing to stabilize the ME) is :

```math
\min \sum_{i}\Big(y_i - \beta_0 - f_Q(q_{i}) - f_T(T_i) - f_W(W_i) - f_S(S_i) - \mathbf{x}_{i}^{\top}\boldsymbol{\beta}\Big)^2
\;+\; \lambda_Q\!\int \!\big(f_Q''\big)^2 + \lambda_T\!\int \!\big(f_T''\big)^2
\;+\; \lambda_W\!\int \!\big(f_W''\big)^2 + \lambda_S\!\int \!\big(f_S''\big)^2 .
```

With the following hyperparameters used in the final run:
* $f_Q$: `n_splines=20`, $\lambda_Q=50$ (prioritize a smooth derivative).
* Weather smooths (T, W, S): `n_splines=20`, $\lambda=50$ each.
* Linear/time features as listed above.


<br>
<br>

When calculating the marginal emissions factor (MEF), we take the derivative of the model with respect to the standardized net load. This follows the model:

```math
\widehat{\mathrm{ME}}
\;=\;
\frac{\partial \widehat{Y}}{\partial Q_{\mathrm{raw}}}
\;=\;
\frac{1}{\sigma_Q}\,
\frac{\partial \widehat{Y}}{\partial Q_{\mathrm{std}}}
```

Which then leads to the finite-difference approximation used in code:

```math
\frac{\partial \widehat{Y}}{\partial Q_{\mathrm{std}}}
\;\approx\;
\frac{\widehat{Y}(Q_{\mathrm{std}}+h)-\widehat{Y}(Q_{\mathrm{std}}-h)}{2h}
\qquad (h\ \text{small})
```

<br>
<br>

In order to validate and calibrate the model, we use the following approaches:

**Short-horizon ramp pairs (validation targets)**

```math
s \;=\; \frac{\Delta Y}{\Delta Q},
\qquad
m \;=\; \frac{\widehat{\mathrm{ME}}_{t}+\widehat{\mathrm{ME}}_{t-1}}{2}
```

**Linear calibration (unit alignment)**

```math
s \;\approx\; a \;+\; b\,m
\quad\text{(WLS with weights }|\Delta Q|\text{)}
```

```math
\widehat{\mathrm{ME}}_{\text{cal}} \;=\; a \;+\; b\,\widehat{\mathrm{ME}}
\qquad\text{(chosen: } a \approx -0.583,\; b \approx 2.226\text{)}
```

<br>
<br>

Finally, we aggregate per-city MEFs to a **national** time series (median across cities at each timestamp). We assign a confidence label by mapping the national ramp magnitude $|\Delta Q|$ at that timestamp to the expected Pearson correlation between realized slopes $s=\Delta Y/\Delta Q$ and the model’s ME, estimated from validation ramp-pair diagnostics.


The aggregation can be written as:

```math
\widehat{\mathrm{ME}}_{\text{nat}}(t)
\;=\;
\mathrm{median}_{c}\Big\{\widehat{\mathrm{ME}}_{\text{cal}}^{(c)}(t)\Big\}
```

And the confidence label is assigned based on the correlation:

```math
r(\tau) \;=\; \mathrm{Corr}\!\big(s,\, m \,\big|\, |\Delta Q| \ge \tau\big)
```

* Where each timestamp’s local ramp \$|\Delta Q|(t)\$ is mapped to an expected \$r\$
* This is labeled as **low/medium/high** using target cutoffs (e.g., \$r!\approx!0.40/0.60\$).
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

<details>
<summary>Additional models explored</summary>
<br>

This approach began by following an example created by Dr. Shefali Khana in the [margE_India.Rmd](/emission_rate_methodologies/marginal_emissions/margE_India.Rmd) file, which used a binned regression approach. This approach stratified observations into quantile bins based on local weather conditions (solar irradiance and wind speed). Then within each bin, emissions (tons of CO2)  were regressed on electricity demand (and demand^2 - both in MW), while fixing the effects of temporal variables month and hour.

While the original model produced a high R2, the pearson r was relatively low, indicating that the model may not fully capture the underlying relationships.

To explore other possibilities, we first performed feature engineering to create a more informative set of predictors. We then tested several alternative modeling approaches, performing bootstrapping checks to assess their stability and robustness.

The results can be summarised as follows:
* **Ridge with polynomial bases**
    * Fast, great level $R^2$, analytic derivative, but the global polynomials imposed shape everywhere, leading to wiggly ME at small–medium ramps and ME $r$ typically \~0.02–0.03 lower than QGAM.

* **Huber regression (poly features)**
    * Improved level robustness vs OLS when tails are heavy, but still inherited polynomial wiggle and sometimes attenuates the ME amplitude.

* **Groupwise OLS (binning/piecewise)**
    * Weakest level fit overall the ME ranks looked decent only at very large ramps.

More details on these models can be found in the [code_and_analysis](/code_and_analysis) section.

</details>
<br>

### Other Approaches to Emissions Estimation

<details>
<summary><strong>Traditional Approach: Full Dispatch Modelling:</strong></summary>
<br>

**What is Dispatch Modelling?**
* Grid operators schedule and dispatch generators by solving a (often mixed-integer) optimisation that respects fuel costs, ramp rates, start-up/shut-down constraints, transmission limits, reserves, and more. If you can run that model twice—baseline vs. “+Δ load”—the emissions difference divided by Δ load is the marginal emission factor.

<br>

**Benefits**
* **Accuracy:** Since the model is grounded in the physical and operational realities of the grid, it is by nature robust and with complete data, can be extremely accurate for the modeled system and quantity. This allows it to make causal inferences of emissions impacts from changes in load or generation at high temporal and spatial resolutions. In other words, you can know what electricity came from what specific generator at any time of day.

<br>

**Disadvantages**
* **Data:** Of course this approach requires a significant amount of data. We stated above that the optimisation respects the fuel costs, constraints, ramp rates, etc., but what does that mean in practice? It means you need access to detailed operational data allowing you to answer questions such as: Which power plants are online? How many generators of which type are at that power plant? What % of full capacity are these generators running at? What is their fuel source? How far away are they from the electricity demand (customers)? Can the transmission lines between the closest energy source and the destination sustain the extra load or does a different source need to be found that is maybe farther away? Is there staff available to service these systems if manual intervention is required?
* **Data Processing/Integration:** Since this data comes from many different sources coalescing it into a unified format for analysis can be challenging and time-consuming. Additionally the challenges that come with master data management and buy in from data owners will add significant complexity.
* **Proprietary Nature:** Much of the data required for this approach is proprietary and not publicly available, making it difficult for external stakeholders such as researchers to access the information they need. While governmental agencies often provide related data that can be used to build rough dispatch models, this approach still requires significant data processing, and then also becomes subject to more assumptions and limitations to fill in gaps.
* **Computational Burden:** The computational resources required to run these models can be substantial, particularly as the scale and complexity of the grid increases.
* **Reproducibility:** Due to the specific data and assumptions used in each model, reproducing results across different studies or regions can be challenging.
<br>

**Further Information**: [dispatch modelling](https://www.wartsila.com/docs/default-source/power-plants-documents/downloads/white-papers/general/wartsila-dispatch-modelling-quantifying-long-term-benefits-via-high-resolution-analysis.pdf), [grid operator](http://en.wikipedia.org/wiki/Transmission_system_operator)


</details>
<br>
<details>
<summary><strong>Emerging Appproaches and Existing Research</strong></summary>

<br>
Because full dispatch models are less accessible to external users, researchers have explored empirical and hybrid approaches that approximate marginal emissions using public signals, validation experiments, and targeted structure.
One organisation in particular, [WattTime](https://www.watttime.org/), has done a great job not only developing models but sharing their methodology.

<br>
**Some approaches from their website**:

* *Difference model*
    * Take the ratio of changes across consecutive intervals (Δemissions / Δload across adjacent timesteps).
    * Pros: Extremely simple, highly granular.
    * Cons: High bias when other conditions move with load (e.g., solar rising with load); very noisy when load changes slowly.
        * Completely abandoned in 2014.

* *Binned regression model*
    * Partition history into similar grid conditions bins (hour, season, load level, etc.) and regress emissions on load within each bin. The slope is the MEF for that state.
    * Pros: Much lower bias than simple differencing, and is widely used in academia and by operators (e.g., ISONE/EPA variants).
    * Cons: Still biased if bins miss key confounders (renewables, net imports).
        * Not exclusively used since 2017, but used in combination with other techniques.

* *Heat-rate model*
    * Use locational-marginal pricing and fuel prices to determine what heat rate corresponds to what fuel type and then calculate the marginal emissions.
    * Pros: Highly granular and can capture high variability when one fuel type dominates.
    * Cons: Loses effectiveness when multiple fuel types are present.

* *Experiment-based model*(RCTs & quasi-experiments)
    * Use randomly controlled trials or quasi-random natural experiments to measure emissions response and calculate marginal emissions factors
    * Pros: They provide a good estimate of the [average treatment effect](/core_concepts_and_definitions.md) and have extremely low bias
    * Cons: Low statistical power as they are very specific to the conditions of their experiment, and have difficulty generalising to different conditions. Also require large amounts of data.

* *Marginal Unit Emissions model*
    * Use the grid’s price-setting unit’s emissions rate as the MEF. So if the grid operator uses coal to set the marginal price, the emissions rate of the coal plant would be used as the MEF.
    * Pros: highly intuitive and easy to implement.
    * Cons: Makes use of plants average emissions, and the price setter is not necessarily the demand provider. Only really valid for small shifts if at all. The data is often not public or easily accessible.

* *Hybrid Models (WattTime's Preference)*
    * What they are: Combinations of the methodlogies described above.
    * What they're currently exploring: a multi-stage, grid-conditioned model: regressions within binned “grid states” infer which fuels are marginal, separate CEMS-based regressions estimate fuel-specific marginal intensities, and a curtailment module flags when renewables would not be used.


**Additional Resources**
* [Clean Energy Buyers Institute (CEBI) - Guide to Sourcing Marginal Emissions Factor Data](https://cebi.org/wp-content/uploads/2022/11/Guide-to-Sourcing-Marginal-Emissions-Factor-Data.pdf),
* [Regularization from Economic Constraints: A New Estimator for Marginal Emissions](https://www.nber.org/papers/w32065)
* [Beyond borders: Estimating the marginal emission factor of electricity trade](https://www.sciencedirect.com/science/article/pii/S0140988325004128)

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

3. **Turning estimates into action.** A constraint-aware, lightweight optimization module translates MEFs into practical load-shifting guidance:
    * *Realistic & efficient*: respects comfort/feasibility constraints and runs quickly without heavy compute.
    * *Actionable (not perfect)*: the greedy heuristic doesn’t guarantee a global optimum, but reliably finds useful local improvements that highlight low-disruption opportunities to cut CO₂.

<br>
In short, this work demonstrates a transparent, low-barrier pathway from public signals (weather, demand, emissions) to location- and time-specific marginal emissions and operational scheduling recommendations.

<br>

## Repository Contents


**Important Directories Summary**
* [code_and_analysis](/code_and_analysis/) - contains the final code, files, and data used throughout the course of this project, as well as the results generated.
    * [analysis_guide](/code_and_analysis/analysis_guide.md) provides an overview of the analysis process and steps required to reproduce the results.
    * [data](/code_and_analysis/data/) - contains the various datasets both raw and intermediate used in the analysis.
    * [scripts](/code_and_analysis/scripts/) - contains the various scripts used for data processing and analysis.
<br>

* [emission_rate_methodologies](/emission_rate_methodologies/) - contains data and sample code that were evaluated when developing the methodology for estimating marginal emission factors.
    * [marginal emissions](/emission_rate_methodologies/marginal_emissions/) - contains the code on which the marginal emissions methodology was based (quantile and median binning).

<br>

**Directory Structure**

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