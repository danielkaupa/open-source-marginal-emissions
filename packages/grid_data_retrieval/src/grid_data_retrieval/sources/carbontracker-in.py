import os
import time
import json
import requests
from tqdm.auto import tqdm
from datetime import datetime, timedelta
from urllib.parse import quote as escape

# ---------- config ----------
# Expect a config.json in the same folder, but allow defaults.
CONFIG_PATH = os.getenv("CONFIG_PATH", "config.json")

DEFAULTS = {
    "GRID_DATA_URL": "",
    "START_DATE": "2023-01-01 00:00:00",
    "END_DATE": "2023-01-07 23:55:00",
    "OUTPUT_DIR": "./grid_data",
    "SAVE_FORMAT": "json",   # fixed to json by your request
    "SLEEP_SECONDS": 5
}

def load_config(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Config file not found at '{path}'. Create it (example below)."
        )
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    merged = {**DEFAULTS, **cfg}
    if not merged["GRID_DATA_URL"]:
        raise ValueError("GRID_DATA_URL is required in config.json")
    # parse dates
    merged["START_DATE"] = datetime.strptime(merged["START_DATE"], "%Y-%m-%d %H:%M:%S")
    merged["END_DATE"]   = datetime.strptime(merged["END_DATE"], "%Y-%m-%d %H:%M:%S")
    return merged

cfg = load_config(CONFIG_PATH)
GRID_DATA_URL = cfg["GRID_DATA_URL"]
START_DATE = cfg["START_DATE"]
END_DATE = cfg["END_DATE"]
OUTPUT_DIR = cfg["OUTPUT_DIR"]
SLEEP_SECONDS = int(cfg["SLEEP_SECONDS"])

os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"Fetching data from {START_DATE} to {END_DATE}")

# ---------- week ranges ----------
delta = END_DATE - START_DATE
no_weeks = delta.days // 7 + (1 if delta.days % 7 != 0 else 0)

def out_name(start_dt, end_dt):
    return f"grid_readings_{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}.json"

for i in tqdm(range(no_weeks)):
    week_start_dt = START_DATE + timedelta(days=i * 7)
    week_end_dt = min(END_DATE, START_DATE + timedelta(days=(i + 1) * 7))

    # skip if file already exists (resume)
    outfile = os.path.join(OUTPUT_DIR, out_name(week_start_dt, week_end_dt))
    if os.path.exists(outfile):
        print(f"Skipping existing file: {outfile}")
        continue

    week_start = escape(week_start_dt.strftime("%Y-%m-%d %H:%M:%S"), safe=":")
    week_end = escape(week_end_dt.strftime("%Y-%m-%d %H:%M:%S"), safe=":")
    url = f"{GRID_DATA_URL}?start_time={week_start}&end_time={week_end}&corrected_values=true"

    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        data = r.json()

        # Build list of records (pure stdlib, no pandas/polars)
        ts = data["timeseries_values"]["timestamps"]
        vals = data["timeseries_values"]

        records = []
        for j in range(len(ts)):
            try:
                records.append({
                    "timestamp": ts[j],  # keep as string for JSON friendliness
                    "thermal_generation": vals["thermal_generation"][j],
                    "gas_generation": vals["gas_generation"][j],
                    "g_co2_per_kwh": vals["g_co2_per_kwh"][j],
                    "hydro_generation": vals["hydro_generation"][j],
                    "nuclear_generation": vals["nuclear_generation"][j],
                    "renewable_generation": vals["renewable_generation"][j],
                    "tons_co2": vals["tons_co2"][j],
                    "total_generation": vals["total_generation"][j],
                    "tons_co2_per_mwh": vals["tons_co2_per_mwh"][j],
                    "demand_met": vals["demand_met"][j],
                    "net_demand": vals["net_demand"][j],
                })
            except Exception as inner_e:
                print(f"row {j} error: {inner_e}")

        # Save JSON array for the week
        with open(outfile, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)

        print(f"Saved: {outfile}")

    except Exception as e:
        print(f"Error on week {i + 1}/{no_weeks}: {e}")

    time.sleep(SLEEP_SECONDS)

print("✅ done.")
