# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

from typing import Optional
import time
import requests
import cdsapi
from pathlib import Path

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from weather_data_retrieval.utils.data_validation import (
    validate_data_provider,
    validate_dataset_short_name,
    validate_cds_api_key,
    validate_coordinates,
    validate_directory,
    clamp_era5_available_end_date,
    parse_date_with_defaults,
    invalid_era5_world_variables,
    normalize_input,
    default_save_dir,
)
from weather_data_retrieval.utils.logging import format_duration
from weather_data_retrieval.utils.file_management import default_save_dir

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------


class SessionState:
    def __init__(self):
        # Order matters – matches prompt flow
        self.fields = {
            "data_provider": {"value": None, "filled": False},          # 1
            "dataset_short_name": {"value": None, "filled": False},     # 2
            "api_url": {"value": None, "filled": False},                # 3
            "api_key": {"value": None, "filled": False},                # 4
            "session_client": {"value": None, "filled": False},         # -
            "save_dir": {"value": None, "filled": False},               # 5
            "start_date": {"value": None, "filled": False},             # 6
            "end_date": {"value": None, "filled": False},               # 7
            "region_bounds": {"value": None, "filled": False},          # 8
            "variables": {"value": None, "filled": False},              # 9
            "existing_file_action": {"value": None, "filled": False},   # 10
            "parallel_settings": {"value": None, "filled": False},      # 11
            "retry_settings": {"value": None, "filled": False},         # 12
            "inputs_confirmed": {"value": None, "filled": False},       # 13
        }

    def set(self, key, value):
        if key in self.fields:
            self.fields[key]["value"] = value
            self.fields[key]["filled"] = True

    def unset(self, key):
        if key in self.fields:
            self.fields[key]["value"] = None
            self.fields[key]["filled"] = False

    def get(self, key):
        return self.fields[key]["value"] if key in self.fields else None

    def previous_key(self, current_key):
        keys = list(self.fields.keys())
        idx = keys.index(current_key)
        return keys[idx - 1] if idx > 0 else None

    def first_unfilled_key(self):
        """
        Return the first key in the ordered fields that is not filled.
        This enables a simple wizard-like progression and supports
        backtracking by clearing fields with `unset(key)`.
        """
        for key, entry in self.fields.items():
            if not entry["filled"]:
                return key
        return None

    def summary(self):
        """Return a nice printable summary of all fields in a tabular format."""
        lines = []

        # Define column widths
        FIELD_WIDTH = 25
        STATUS_WIDTH = 10
        VALUE_WIDTH = 40

        # Header
        lines.append("-" * (FIELD_WIDTH + STATUS_WIDTH + VALUE_WIDTH + 4))
        lines.append(f"{'Variable':<{FIELD_WIDTH}} {'Status':<{STATUS_WIDTH}} {'Values':<{VALUE_WIDTH}}")
        lines.append("-" * (FIELD_WIDTH + STATUS_WIDTH + VALUE_WIDTH + 4))

        # Define sensitive fields that should be redacted
        SENSITIVE_FIELDS = ['api_key']

        for k, v in self.fields.items():
            val = v["value"]
            status = "Filled" if v["filled"] else "Empty"

            if k in SENSITIVE_FIELDS:
                if v["filled"]:
                    display_val = "*** REDACTED ***"
                else:
                    display_val = "None"
            else:
                # Format the value for display
                if val is None:
                    display_val = "None"
                elif isinstance(val, list):
                    # Truncate long lists
                    if len(val) > 3:
                        display_val = f"[{', '.join(str(x) for x in val[:3])}...]"
                    else:
                        display_val = f"[{', '.join(str(x) for x in val)}]"
                elif isinstance(val, dict):
                    # Truncate long dictionaries
                    items = list(val.items())[:2]
                    display_val = f"{{{', '.join(f'{k}:{v}' for k, v in items)}}}{'...' if len(val) > 2 else ''}"
                else:
                    # Truncate long strings
                    str_val = str(val)
                    display_val = str_val[:VALUE_WIDTH-3] + "..." if len(str_val) > VALUE_WIDTH else str_val

            # Use fixed-width formatting
            lines.append(f"{k:<{FIELD_WIDTH}} {status:<{STATUS_WIDTH}} {display_val:<{VALUE_WIDTH}}")

        return "\n".join(lines)

def get_cds_dataset_config(
        session: SessionState,
        dataset_config_mapping: dict
        ) -> dict:
    """
    Return dataset configuration dictionary based on session short name.

    Parameters
    ----------
    session : SessionState
        The current session state containing user selections.
    dataset_config_mapping : dict
        The mapping of dataset short names to their configurations.
    Returns
    -------
    dict
        The configuration dictionary for the selected dataset.

    """
    short_name = session.get("dataset_short_name")
    if short_name not in dataset_config_mapping:
        raise KeyError(
            f"Dataset short name '{short_name}' not found in {dataset_config_mapping} configuration."
        )
    return dataset_config_mapping[short_name]


def map_config_to_session(
        cfg: dict,
        session: SessionState
        ) -> tuple[bool, list[str]]:
    """
    Validate and map a loaded JSON config into SessionState.

    Parameters
    ----------
    cfg : dict
        Loaded configuration dictionary.
    session : SessionState
        The session state to populate.

    Returns:
    --------
    tuple : (bool, list[str])
        (ok, messages): ok=False if any hard error prevents continuing.
    """
    messages: list[str] = []
    errors: list[str] = []

    # ---------- Provider ----------
    raw_provider = cfg.get("data_provider", "cds")
    provider = normalize_input(str(raw_provider), "data_provider")
    if not validate_data_provider(provider):
        errors.append(f"Invalid data_provider: {raw_provider!r}. Allowed: 'cds'.")
    elif provider != "cds":
        errors.append("Only 'cds' is supported in this version.")
    else:
        session.set("data_provider", provider)
        messages.append(f"data_provider = {provider}")

    # ---------- Dataset ----------
    raw_ds = cfg.get("dataset_short_name", cfg.get("dataset", "era5-world"))
    ds = normalize_input(str(raw_ds), "era5_dataset_short_name")
    if not validate_dataset_short_name(ds, "cds"):
        errors.append(f"Invalid dataset_short_name for CDS: {raw_ds!r}. Try 'era5-world'.")
    elif ds != "era5-world":
        errors.append("Only 'era5-world' is implemented in this version.")
    else:
        session.set("dataset_short_name", ds)
        messages.append(f"dataset_short_name = {ds}")

    # ---------- API ----------
    api_url = cfg.get("api_url", "https://cds.climate.copernicus.eu/api")
    api_key = cfg.get("api_key", "")
    if not api_key:
        errors.append("Missing 'api_key' in config.")
    else:
        session.set("api_url", api_url)
        session.set("api_key", api_key)
        client = validate_cds_api_key(api_url, api_key)
        if client is None:
            errors.append("CDS authentication failed with provided api_url/api_key.")
        else:
            session.set("session_client", client)
            messages.append("CDS authentication successful.")

    # ---------- Dates ----------
    # Accept: start_date/end_date or start/end; allow YYYY-MM or YYYY-MM-DD
    start_in = cfg.get("start_date", cfg.get("start"))
    end_in   = cfg.get("end_date",   cfg.get("end"))
    if not start_in or not end_in:
        errors.append("Both 'start_date' and 'end_date' are required in config.")
    else:
        try:
            s_dt, s_str = parse_date_with_defaults(str(start_in), default_to_month_end=False)
            e_dt, e_str = parse_date_with_defaults(str(end_in),   default_to_month_end=True)
            if e_dt <= s_dt:
                errors.append(f"end_date ({e_str}) must be after start_date ({s_str}).")
            # Clamp for ERA5 availability
            e_dt = clamp_era5_available_end_date(e_dt)
            session.set("start_date", s_dt.date().isoformat())
            session.set("end_date",   e_dt.date().isoformat())
            messages.append(f"date range = {s_dt.date().isoformat()} → {e_dt.date().isoformat()}")
        except Exception as e:
            errors.append(f"Invalid dates: {e}")

    # ---------- Region bounds ----------
    # Accept keys: region_bounds / bounds / area / {"north","south","west","east"} / list [N,W,S,E]
    bounds = None

    def try_extract_bounds(obj) -> Optional[list[float]]:
        if obj is None:
            return None
        # dict forms
        if isinstance(obj, dict):
            # Allow many aliases
            keys = {k.lower(): v for k, v in obj.items()}
            candidates = [
                ("north", "west", "south", "east"),
                ("n", "w", "s", "e"),
            ]
            for n, w, s, e in candidates:
                if all(k in keys for k in (n, w, s, e)):
                    try:
                        N = float(keys[n]); W = float(keys[w]); S = float(keys[s]); E = float(keys[e])
                        return [N, W, S, E]
                    except Exception:
                        return None
            return None
        # list/tuple forms
        if isinstance(obj, (list, tuple)) and len(obj) == 4:
            # Try to detect order:
            # If it looks like [N,W,S,E] or [N,S,W,E]—we enforce [N,W,S,E].
            try:
                vals = [float(x) for x in obj]
            except Exception:
                return None
            # Heuristic: if the 2nd value looks like longitude (|<=180) and 3rd latitude (|<=90) and N>S
            # assume [N,W,S,E]. If not, trust it's already [N,W,S,E].
            # (You can simplify—this is just a safeguard.)
            return [vals[0], vals[1], vals[2], vals[3]]
        return None

    bounds = (
        try_extract_bounds(cfg.get("region_bounds")) or
        try_extract_bounds(obj=cfg.get("bounds")) or
        try_extract_bounds(cfg.get("area")) or
        try_extract_bounds({
            "north": cfg.get("north"),
            "south": cfg.get("south"),
            "west":  cfg.get("west"),
            "east":  cfg.get("east"),
        })
    )

    if not bounds:
        errors.append("Missing or invalid region bounds. Provide [north, west, south, east] or dict with those keys.")
    else:
        N, W, S, E = bounds
        if not validate_coordinates(N, W, S, E):
            errors.append(f"Invalid region bounds: {bounds}.")
        else:
            session.set("region_bounds", [N, W, S, E])
            messages.append(f"region_bounds = N{N}, W{W}, S{S}, E{E}")

    # ---------- Variables ----------
    raw_vars = cfg.get("variables")
    variables: list[str] = []
    if isinstance(raw_vars, str):
        variables = [v.strip().lower().strip('"').strip("'") for v in raw_vars.split(",") if v.strip()]
    elif isinstance(raw_vars, (list, tuple)):
        variables = [str(v).strip().lower().strip('"').strip("'") for v in raw_vars if str(v).strip()]
    else:
        errors.append("Missing 'variables' (list or comma-separated string).")

    if variables:
        # Apply denylist for ERA5-world
        deny = invalid_era5_world_variables
        valid = [v for v in variables if v not in deny]
        invalid = [v for v in variables if v in deny]
        if invalid:
            messages.append(f"Filtering out disallowed variables: {', '.join(invalid)}")
        if not valid:
            errors.append("After filtering disallowed variables, no variables remain.")
        else:
            session.set("variables", valid)
            messages.append(f"variables = {', '.join(valid)}")

    # ---------- Save directory ----------
    save_dir = cfg.get("save_dir", str(default_save_dir))
    if not validate_directory(save_dir):
        errors.append(f"Cannot access/create save_dir: {save_dir}")
    else:
        session.set("save_dir", Path(save_dir))
        messages.append(f"save_dir = {save_dir}")

    # ---------- Existing file policy ----------
    efa_raw = cfg.get("existing_file_action", cfg.get("file_policy", "case_by_case"))
    efa_norm = str(efa_raw).strip().lower()
    if efa_norm in ("overwrite_all", "skip_all", "case_by_case"):
        session.set("existing_file_action", efa_norm)
        messages.append(f"existing_file_action = {efa_norm}")
    elif efa_norm in ("1", "2", "3"):
        mapped = {"1": "overwrite_all", "2": "skip_all", "3": "case_by_case"}[efa_norm]
        session.set("existing_file_action", mapped)
        messages.append(f"existing_file_action = {mapped}")
    else:
        # default to case_by_case; the wizard can still re-prompt if needed
        session.set("existing_file_action", "case_by_case")
        messages.append("existing_file_action not recognized; defaulting to 'case_by_case'.")

    # ---------- Retry settings ----------
    retries = cfg.get("retry_settings", {})
    max_retries = int(retries.get("max_retries", 6))
    retry_delay = int(retries.get("retry_delay_sec", retries.get("retry_delay", 15)))
    if max_retries < 0 or retry_delay < 0:
        errors.append("retry_settings must be non-negative.")
    else:
        session.set("retry_settings", {"max_retries": max_retries, "retry_delay_sec": retry_delay})
        messages.append(f"retry_settings = {{'max_retries': {max_retries}, 'retry_delay_sec': {retry_delay}}}")

    # ---------- Parallel settings ----------
    parallel = cfg.get("parallel_settings", cfg.get("parallel", {}))
    # Accept booleans ('enabled') or integer 'max_concurrent'
    enabled = parallel.get("enabled", True)
    if isinstance(enabled, str):
        enabled = normalize_input(enabled, "boolean")
    enabled = bool(enabled)
    mc = parallel.get("max_concurrent", 2)
    try:
        mc = int(mc)
    except Exception:
        mc = 2
    if not enabled:
        session.set("parallel_settings", {"enabled": False, "max_concurrent": 1})
        messages.append("parallel_settings = disabled")
    else:
        if mc < 2:
            mc = 2
        session.set("parallel_settings", {"enabled": True, "max_concurrent": mc})
        messages.append(f"parallel_settings = enabled, max_concurrent={mc}")

    # ---------- Done ----------
    if errors:
        for e in errors:
            print("CONFIG ERROR:", e)
        return False, messages + errors
    return True, messages


def ensure_cds_connection(
        client: cdsapi.Client,
        creds: dict,
        max_reauth_attempts: int = 6,
        wait_between_attempts: int = 15
    ) -> cdsapi.Client | None:
    """
    Ensure a valid CDS API client. Re-authenticate automatically if the connection drops.

    Parameters
    ----------
    client : cdsapi.Client
        Current CDS API client.
    creds : dict
        {'url': str, 'key': str} stored from initial login.
    max_reauth_attempts : int
        Maximum reconnection attempts before aborting.
    wait_between_attempts : int
        Wait time (seconds) between re-auth attempts.

    Returns
    -------
    cdsapi.Client | None
        Valid client or None if re-authentication ultimately fails.
    """
    for attempt in range(1, max_reauth_attempts + 1):
        try:
            # test if still alive (by touching internal session)
            _ = client.session
            return client
        except Exception as e:
            print(f"Lost connection to CDS API ({e}). Attempting re-authentication {attempt}/{max_reauth_attempts}...")
            try:
                new_client = cdsapi.Client(url=creds["url"], key=creds["key"], quiet=True)
                print("\tRe-authentication successful!")
                return new_client
            except Exception as reauth_e:
                print(f"\tRe-authentication failed! : {reauth_e}")
                if attempt < max_reauth_attempts:
                    print(f"Retrying in {wait_between_attempts} seconds...")
                    time.sleep(wait_between_attempts)
                else:
                    print("\tMaximum reconnection attempts reached. Aborting process.")
                    return None


def internet_speedtest(
        test_urls: list[str] | None = None,
        max_seconds: int = 15,
        ) -> float:
    """
    Download ~100MB test file from a fast CDN to estimate speed (MB/s).

    Parameters
    ----------
    test_urls : list[str], optional
        List of URLs of the test files.
    max_seconds : int, optional
        Maximum time to wait for a response, by default 15 seconds.

    Returns
    -------
        float: Estimated download speed in Mbps.
    """
    if test_urls is None:
        test_urls = [
            "https://speedtest.london.linode.com/100MB-london.bin",
            "https://mirror.de.leaseweb.net/speedtest/100mb.bin",
            "https://ipv4.download.thinkbroadband.com/100MB.zip",
        ]
    print("="*40)
    print(f"Internet speed test\n" + "="*40)
    print("\n")
    for url in test_urls:
        try:
            print(f"Testing {url}\n\tMay take up to ~{max_seconds}s...")
            t0 = time.time()
            downloaded = 0
            with requests.get(url, stream=True, timeout=max_seconds) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1 MB chunks
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if (time.time() - t0) > max_seconds or downloaded >= 50_000_000:
                        break
            elapsed = max(1e-6, time.time() - t0)
            mbps = (downloaded * 8 / 1e6) / elapsed
            print(f"\tRESULT: SUCCESS — {mbps:.1f} Mbps (based on {downloaded/1e6:.1f} MB in {elapsed:.1f}s)")
            return float(mbps)
        except Exception as e:
            print(f"\tRESULT: FAILURE on {url}: {e}")
    print("All tests failed. Assuming 25 Mbps.")
    return 25.0
