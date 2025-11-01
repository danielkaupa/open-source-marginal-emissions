Roadmap

The roadmap tracks Now / Next / Later priorities by module. It summarises the detailed notes from the thesis‑extension planning.

Platform (cross‑cutting)

Now: Solidify weather retrieval (CDS), local runs, JSON configs, logging.

Next: Provider expansions (Open‑Meteo; Electricity Maps; IEA). Harmonise schemas. Robust completeness/gap‑fill playbook.

Later: Optional webform UI; Azure/AWS workflows for at‑scale runs; HPC/local parity.

Module 1.1 — Weather Data Retrieval & Transformations

MVP: retrieve ERA5‑World for India; process; crop to national bounds; export (per‑year, ~<75MB when committed); ensure de‑accumulation correctness; optional national aggregate.

Desired requirements: provider selection (CDS/Open‑Meteo), variable selection with vetted lists; smart existing‑file prompts/skip; optional gap‑fill via fallback dataset; re‑gridding options; reliable parallel + retry; GitHub‑friendly chunking; CLI + JSON + HPC scripts.

Wishlist: simple webform for config; documentation on variable nuances and gap‑filling; fool‑proof duplicate‑download logic; multi‑region presets (India, Argentina, Greece, South Africa, Costa Rica, Panama).

Now/Next/Later:

Now: CDS flows, variable lists, de‑accum checks, JSON schema validation, parallel & retries.

Next: Open‑Meteo provider; fallback gap‑fill; re‑grid hooks; rock‑solid existing‑file handling.

Later: UI; presets; cloud workflows; performance tuning.

Module 1.2 — Grid Data Retrieval & Transformations

MVP: CarbonTracker India retrieval with known gap fixes; export joinable tables.

Desired requirements: provider selection (Electricity Maps, IEA, country‑specific); completeness checks; notebook‑guided gap‑fill (user chooses method, standard naming); year‑split, size‑aware exports; join with weather.

Now/Next/Later:

Now: IN provider, gap fixes, joinability tests.

Next: add EM + IEA; completeness thresholds & actions; country expansion.

Later: harmonised schemas; richer metadata.

Module 1.3 — Combining Grid & Weather

MVP: disaggregate weather to 30‑min; aggregate grid to 30‑min; join; export national and native‑resolution products.

Desired requirements: choose temporal frequency (15/30/60m); perform required (dis)aggregations; export both national and native resolutions; size‑aware partitioning.

Now/Next/Later:

Now: 30‑min target pipeline + joins.

Next: configurable freq; robust gap‑fill; national/native outputs.

Later: storage‑saving partitions; schema/versioning & data dictionary.

Module 2 — Marginal Emissions Modelling

MVP: notebooks for EDA and model generation; templated steps to sift variables/transformations/models and evaluate accuracy.

Desired requirements: programmatic runs for predefined variable sets and models; options for sweeps vs. single‑model deep dives; logging; expected outputs (datetime, MEF, AEF). Hooks for adding contextual weights (e.g., regional generation shares) and exploring their effects.

Now/Next/Later:

Now: templates + diagnostics + calibration helpers.

Next: automated sweeps; hyperparameters; logging; comparisons.

Later: advanced weighting schemes; publishable outputs.

Module 3 — Optimisation (future)

MVP: run optimisation for predefined constraints/time windows (e.g., weekly); support one solver (greedy or MILP); validate inputs; export schedules + diagnostics.

Desired requirements: configurable constraints; continuous vs. MILP; local vs. HPC execution; resource estimation; modular inputs (Polars or similar); reproducible outputs.

Beyond MVP: web UI; expanded solver library; automated run logging & comparisons; plug‑and‑play constraints; memory/runtimes safeguards.