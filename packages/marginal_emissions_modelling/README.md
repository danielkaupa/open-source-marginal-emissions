* [Methodology - Marginal Emissions](#methodology---marginal-emission-factor-estimations)
    * [This Project's Approach](#this-projects-approach)
    * [Other Approaches to Emissions Estimation](#other-approaches-to-emissions-estimation)




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

Marginal Emissions Modelling (WIP)

Purpose: Estimate marginal emissions factors (MEFs) from joined weather + grid data, with clear validation and calibration steps.

Approach (summary)

Core idea: learn emissions
𝑌
Y as a function of net load and weather/time covariates; compute
∂
𝑌
^
/
∂
𝑄
∂
Y
^
/∂Q to obtain MEF.

Practical choice: smooth models (e.g., GAM) for stable derivatives, then units alignment via short‑horizon ramp calibration.

Diagnostics: rank correlation between realized slopes
Δ
𝑌
/
Δ
𝑄
ΔY/ΔQ and model ME; performance improves with ramp size.

What lives here

Notebooks: EDA, model training, and diagnostics (templates included/coming).

Helpers for calibration, ramp‑pair construction, and aggregation (e.g., per‑city → national median).

Output: per‑timestamp MEF time series with confidence tags, and optional AEFs.

Roadmap (module)

Now: baseline templates; ramp‑pair diagnostics; finite‑difference derivative utilities.

Next: hyperparameter sweeps; model comparison (ridge/poly, Huber, groupwise OLS, QGAM); logging.

Later: integration with (future) optimisation module; publishable figures.