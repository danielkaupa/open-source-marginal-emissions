Weather Data Retrieval

Purpose: Retrieve ERA5‑Land and ERA5 weather data (Open‑Meteo planned), interactively or via JSON config, with validation, logging, retries, and HPC‑friendly scripts.

Features

Interactive prompts or non‑interactive --config JSON.

Supports providers: CDS (ERA5‑Land, ERA5); Open‑Meteo planned.

Retry/parallel settings, skip existing files logic.

Exports to ./data/raw by default; integrates with downstream cleaning/joining.

Shell scripts for HPC batch runs (land/world variants).

Directory layout
weather_data_retrieval/
├─ __init__.py
├─ __main__.py                 # python -m weather_data_retrieval
├─ cli.py                      # user prompts / argument parsing
├─ config_loader.py            # JSON parsing & validation
├─ prompts.py                  # interactive flow
├─ main.py                     # entrypoint (also exposes CLI)
├─ runner.py                   # orchestrates downloads
├─ io/
├─ sources/
│  ├─ cds_era5.py              # CDS ERA5/ERA5-Land provider
│  └─ open_meteo.py            # (planned/early) Open‑Meteo provider
└─ utils/
   ├─ data_validation.py
   ├─ file_management.py       # existing file checks, paths
   ├─ logging.py               # simple logging
   └─ session_management.py    # provider sessions, auth
Install (package)

From repo root:

pip install -e .[dev]

This exposes the console script wdr.

Usage

Interactive:

wdr              # or: python -m weather_data_retrieval

Batch via JSON config:

wdr --config input/download_request_land.json
# or
wdr --config input/download_request_world.json

Config schema (examples in input/):

{
  "data_provider": "cds",                    // cds | open-meteo (planned)
  "dataset_short_name": "era5-land",         // e.g., era5-land | era5-world
  "api_url": "https://cds.climate.copernicus.eu/api",
  "api_key": "YOUR_API_KEY_HERE",            // for CDS: <uid>:<key>
  "start_date": "YYYY-MM",
  "end_date":   "YYYY-MM",
  "region_bounds": [N, W, S, E],               // lat/lon bounds
  "variables": ["..."],                       // list of ERA variables
  "save_dir": "./data/raw",                  // output dir
  "existing_file_action": "skip_all",        // skip_all | overwrite | prompt
  "retry_settings": {"max_retries": 6, "retry_delay_sec": 15},
  "parallel_settings": {"enabled": true, "max_concurrent": 2}
}

HPC scripts:

bash weather_data_retrieval/main_land.sh
bash weather_data_retrieval/main_world.sh
Notes & tips

Some ERA variables are accumulated (e.g., precipitation); downstream cleaning handles de‑accumulation.

Keep individual output files < ~75 MB if committing; otherwise store under data/ and exclude via .gitignore.

Roadmap (module)

Now: solidify CDS flows; robust existing‑file checks; retries/parallel; JSON schema validation.

Next: Open‑Meteo provider; documented variable lists; fool‑proof "you already have this" logic.

Later: Webform UI; richer processing hooks; region presets (India, AR, GR, ZA, CR, PA); HPC/local parity.