Grid Data Retrieval (WIP)

Purpose: Programmatically retrieve electricity demand/generation/emissions data aligned to user‑selected geography, period, resolution, and fields. First target: CarbonTracker India; planned: Electricity Maps, IEA, and country‑specific sources.

Planned features

Interactive CLI and JSON configs (mirroring weather module).

Provider selection: electricitymaps | iea | country‑specific (IN first).

Smart existing‑file checks; retries; parallel.

Gap checks + guided fill workflow/notebook when completeness < threshold.

Clean exports compatible with weather joins.

Inputs/outputs

Inputs: provider creds/keys (as required), date range, region(s), frequency.

Outputs: tidy CSV/Parquet to data/raw then data/interim after basic cleaning.

Roadmap (module)

Now: CarbonTracker India retrieval + known gap fixes; export and joinability tests.

Next: add Electricity Maps and IEA; completeness checks; standard gap‑fill playbook.

Later: additional countries; harmonised schemas.

Path: data_cleaning_and_joining/README.md
Data Cleaning & Joining (WIP)

Purpose: Turn raw weather + grid inputs into aligned, analysis‑ready tables.

Responsibilities

Weather: de‑accumulate where needed (e.g., ERA precipitation), resample (→ 30‑min suggested), and trim to geography.

Grid: aggregate/disaggregate as needed (→ 30‑min suggested), validate completeness.

Join: align on time (and location if spatial), memory‑efficient file layout, export Parquet.

Suggested pipeline

Ingest data/raw → standardise columns/units.

Weather transforms (de‑accum., resample); grid transforms (agg/disagg).

Join on common axes (time, region); write to data/processed.

Persist logs + simple data‑quality metrics.

Roadmap (module)

Now: implement 30‑min target frequency; ERA de‑accumulation; join prototype.

Next: configurable frequencies (15/30/60m); robust gap‑fill strategies; national averages + chosen native resolution.

Later: storage‑saving strategy (chunking/partitioning); schema/versioning.