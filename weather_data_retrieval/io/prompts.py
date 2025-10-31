# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

from getpass import getpass
from pathlib import Path

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from weather_data_retrieval.utils.session_management import SessionState
from weather_data_retrieval.utils.data_validation import (
    normalize_input,
    validate_data_provider,
    validate_dataset_short_name,
    NORMALIZATION_MAP,
    validate_directory,
    validate_date,
    parse_date_with_defaults,
    clamp_era5_available_end_date,
    validate_coordinates,
    validate_variables
)
from weather_data_retrieval.utils.logging import log_msg


# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------

# Core centralised input handler
def read_input(
        prompt: str,
        *,
        logger=None,
        ) -> str:
    """
    Centralized input handler with built-in 'exit' and 'back' controls.

    Parameters:
    ----------
    prompt : str
        The prompt to display to the user.
    logger : logging.Logger, optional
        Logger to log the prompt message.
    run_mode : str
        Run mode, either 'interactive' or 'automatic'.

    Returns:
    -------
    str
        The user input, or special command indicators.
    """

    log_msg(prompt, logger)

    # strip leading/trailing whitespace and convert to lower case for command checks
    raw = input(prompt).strip()
    lower = raw.lower()

    # check for special commands
    if lower in ("exit","quit"): return "__EXIT__"
    if lower == "back": return "__BACK__"

    # return input cleaned of leading/trailing whitespace and lowercased
    return lower


def say(
        text: str,
        *,
        logger=None
        ) -> None:
    """
    Centralized output handler to log and print messages.

    Parameters:
    ----------
    text : str
        The message to display.
    logger : logging.Logger, optional
        Logger to log the message.

    Returns:
    -------
    None

    """
    log_msg(text, logger)



# 1 - DATA PROVIDER (data_provider: "cds" or "open-meteo")
def prompt_data_provider(
        session: SessionState,
        *,
        logger=None,
        ) -> str:
    """
    Prompt user for which data provider to use (CDS or Open-Meteo).

    Parameters
    ----------
    session : SessionState
        Current session state to store selected data provider.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "interactive".

    Returns
    -------
    str
        Normalized provider name ("cds" or "open-meteo"),
        or special control token "__BACK__" or "__EXIT__".

    """

    say("-"*30 + "\nData Provider Selection:\n" + '-'*30, logger=logger)
    say("Available data providers:\n\t1. Copernicus Climate Data Store (CDS)\n\t2. Open-Meteo", logger=logger)

    while True:
        raw = read_input("\nPlease enter the data provider you would like to use (name or number): ",
                         logger=logger)

        if raw in ("__EXIT__", "__BACK__"):
            return raw

        data_provider = normalize_input(raw, "data_provider")

        if not validate_data_provider(data_provider):
            say("\nERROR: Invalid provider. Please enter '1' for CDS or '2' for Open-Meteo", logger=logger)
            continue
        if data_provider == "open-meteo":
            say("\nERROR: Open-Meteo support is not yet implemented. Please select CDS.", logger=logger)
            continue

        say(f"\nYou selected: {data_provider.upper()}\n", logger=logger)

        session.set("data_provider", data_provider)

        return data_provider


# 2 - DATASET SHORT NAME (dataset_short_name: e.g. "era5-land", "era5-world")
def prompt_dataset_short_name(
        session: SessionState,
        provider: str,
        *,
        logger=None,
        run_mode: str = "interactive") -> str:
    """
    Prompt for dataset choice.

    Parameters
    ----------
    session: SessionState
        Current session state to store selected dataset.
    provider : str
        Data provider name.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "interactive".

    Returns
    -------
        str: Normalized dataset name or 'exit' / 'back'.

    """
    if provider != "cds":
        say("\nCurrently only CDS datasets are supported.", logger=logger)
        return "__BACK__"

    say("-"*30 + "\nDataset Selection:\n" + '-'*30, logger=logger)
    say("Available CDS datasets:\n\t1. ERA5-Land\n\t2. ERA5-World", logger=logger)

    while True:
        raw = read_input("\nPlease enter the dataset you would like to use (name or number): ",
                         logger=logger, run_mode=run_mode)
        if raw in ("__EXIT__", "__BACK__"):
            return raw

        dataset_short_name = normalize_input(raw, "era5_dataset_short_name")
        if not validate_dataset_short_name(dataset_short_name, provider):
            say("Invalid or unsupported dataset. Try again.", logger=logger)
            continue

        if dataset_short_name != "era5-world":
            say("Only ERA5-World dataset is implemented in this version. Please select ERA5-World.", logger=logger)
            continue

        say(f"\nYou selected: {dataset_short_name.upper()}\n", logger=logger)
        session.set("dataset_short_name", dataset_short_name)
        return dataset_short_name


# 3 - API URL (api_url)
def prompt_cds_url(
        session: SessionState,
        api_url_default: str = "https://cds.climate.copernicus.eu/api",
        *,
        logger=None,
        run_mode: str = "interactive"
        ) -> str:
    """
    Prompt for CDS API URL.

    Parameters
    ----------
    session : SessionState
        Current session state to store API URL.
    api_url_default : str
        Default CDS API URL. https://cds.climate.copernicus.eu/api

    Returns
    -------
        str: CDS API URL or 'exit' / 'back'.

    """
    say("-"*30 + "\nCDS API url:\n" + '-'*30, logger=logger)
    say(f"Default: {api_url_default}", logger=logger)
    while True:
        raw = read_input("\nEnter the CDS API url (or press Enter to keep default): ",
                         logger=logger)
        if raw in ("__EXIT__", "__BACK__"):
            return raw
        url = raw or api_url_default
        session.set("api_url", url)
        say(f"\nYou entered the url : {url}\n", logger=logger)
        return url


# 4 - API KEY (api_key)
def prompt_cds_api_key(
        session: SessionState,
        *,
        logger=None,
        run_mode: str = "interactive"
        ) -> str:
    """
    Prompt only for the CDS API key (hidden input).

    Parameters
    ----------
    session : SessionState
        Current session state to store API key.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "interactive".

    Returns
    -------
    str
        CDS API key or 'exit' / 'back'.
    """
    say("-"*30 + "\nCDS API key:\n" + '-'*30, logger=logger)
    while True:
        key = getpass("\nEnter your CDS API key: ")
        # getpass cannot log input value; we just log the action
        low = key.lower()
        if low in ("exit", "quit"):
            return "__EXIT__"
        if low == "back":
            return "__BACK__"
        if not key:
            say("No API key entered. Please try again.", logger=logger)
            continue
        session.set("api_key", key)
        say(f"\nYou entered an API key of length {len(key)} characters.\n", logger=logger)
        return key


# 5 - SAVE DIRECTORY (save_dir)
def prompt_save_directory(
        session: SessionState,
        default_dir: Path,
        *,
        logger=None,
        run_mode: str = "interactive"
    ) -> Path | str:

    """
    Ask for save directory, create if necessary.

    Parameters
    ----------
    session : SessionState
        Current session state to store save directory.
    default_dir : Path
        Default directory to suggest.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "interactive".

    Returns
    -------
    Path | str
        Path to save directory, or control token "__BACK__" / "__EXIT__".

    """
    say("-"*30 + "\nData Save Directory Selection:\n" + '-'*30, logger=logger)
    say(f"Default: {default_dir}", logger=logger, run_mode=run_mode)
    while True:
        raw = read_input("\nEnter a path (or press Enter to use default): ", logger=logger)
        if raw in ("__EXIT__", "__BACK__"):
            return raw
        path = Path(raw or default_dir).expanduser().resolve()
        if validate_directory(str(path)):
            say(f"\nYou set the save directory to: {path}\n", logger=logger, run_mode=run_mode)
            session.set("save_dir", path)
            return path
        say(f"Directory [{path}] could not be created or accessed. Try another path.", logger=logger)


# 6 & 7 - DATE RANGE (start_date, end_date)
def prompt_date_range(
        session: SessionState,
        *,
        logger=None,
        run_mode: str = "interactive"
        ) -> tuple[str, str]:
    """
    Ask user for start and end date, with validation.
    Accepts formats: YYYY-MM-DD or YYYY-MM
    - Start dates without day default to first day of month (YYYY-MM-01)
    - End dates without day default to last day of month (YYYY-MM-[last day])

    Parameters
    ----------
    session : SessionState
        Current session state to store date range.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "interactive".

    Returns
    -------
    tuple[str, str]
        (start_date_str, end_date_str) in ISO format (YYYY-MM-DD),
        or ("__EXIT__", "__EXIT__") / ("__BACK__", "__BACK__")
    """
    say("-"*30 + "\nDate Range Selection:\n" + '-'*30, logger=logger)
    say("Enter dates as YYYY-MM-DD or YYYY-MM\n(YYYY-MM will default to first day for start, last day for end)", logger=logger)

    while True:
        start_raw = read_input("\nEnter start date: ", logger=logger)
        if start_raw in ("__EXIT__", "__BACK__"): return start_raw, start_raw
        end_raw = read_input("\nEnter end date: ", logger=logger)
        if end_raw in ("__EXIT__", "__BACK__"): return end_raw, end_raw

        if not validate_date(start_raw, allow_month_only=True):
            say("\nERROR: Invalid start date format. Use YYYY-MM-DD or YYYY-MM.", logger=logger)
            continue
        if not validate_date(end_raw, allow_month_only=True):
            say("\nERROR: Invalid end date format. Use YYYY-MM-DD or YYYY-MM.", logger=logger)
            continue

        try:
            start, start_str = parse_date_with_defaults(start_raw, default_to_month_end=False)
            if len(start_raw) == 7:
                say(f"\n\tStart date set to: {start_str} (first day of month)", logger=logger)
            end, end_str = parse_date_with_defaults(end_raw, default_to_month_end=True)
            if len(end_raw) == 7:
                say(f"\tEnd date set to: {end_str} (last day of month)\n", logger=logger)
        except ValueError as e:
            say(f"\nERROR: Could not parse dates: {e}", logger=logger)
            continue

        if end <= start:
            say("\nERROR: End date must be after start date.", logger=logger)
            continue

        if session.get("data_provider") == "cds":
            end = clamp_era5_available_end_date(end)
            end_str = end.date().isoformat()

        say(f"\nYou selected a date range of start [{start.date().isoformat()}] → end [{end.date().isoformat()}]\n",
            logger=logger, run_mode=run_mode)
        session.set("start_date", start.date().isoformat())
        session.set("end_date", end.date().isoformat())
        return start.date().isoformat(), end.date().isoformat()


# 8 - GEOGRAPHIC BOUNDARIES (region_bounds)
def prompt_coordinates(
        session: SessionState,
        *,
        logger=None,
        run_mode: str = "interactive"
        ) -> list[float]:
    """
    Prompt user for geographic boundaries (N, S, W, E) with validation.

    Parameters
    ----------
    session : SessionState
        Current session state to store geographic boundaries.

    Returns
    -------
    list[float]
        [north, west, south, east] boundaries or special tokens "__EXIT__" / "__BACK__".
    """
    say('-'*30 + "\nGrid Area Selection (ESPG: 4326):\n" + '-'*30, logger=logger)
    while True:
        entries = {}
        for label, key in [("Northern latitude", "north"),
                           ("Southern latitude", "south"),
                           ("Western longitude", "west"),
                           ("Eastern longitude", "east")]:
            value = read_input(f"\nEnter {label} boundary: ", logger=logger)
            if value in ("__BACK__", "__EXIT__"):
                return value
            entries[key] = value

        try:
            n, s, w, e = (
                float(entries["north"]),
                float(entries["south"]),
                float(entries["west"]),
                float(entries["east"]),
            )
        except ValueError:
            say("\nPlease enter numeric values for all coordinates.", logger=logger)
            continue

        if not validate_coordinates(n, s, e, w):
            say("Invalid bounds. Check that -90 ≤ lat ≤ 90, -180 ≤ lon ≤ 180, and North > South.", logger=logger)
            continue

        bounds = [n, w, s, e]
        say(f"You entered boundaries of: N{n}, W{w}, S{s}, E{e}", logger=logger)
        session.set("region_bounds", bounds)
        return bounds


# 9 - VARIABLES (variables)
def prompt_variables(
        session: SessionState,
        variable_restrictions_list: list[str],
        *args,
        restriction_allow: bool = False,
        logger=None,
        run_mode: str = "interactive"
        ) -> list[str] | str:
    """
    Ask for variables to download, validate each against allowed/disallowed list,
    and only update session if the full set is valid.

    Parameters
    ----------
    session : SessionState
        Current session state to store selected variables.
    variable_restrictions_list : list[str]
        List of variables that are either allowed or disallowed.
    restriction_allow : bool
        If True, variable_restrictions_list is an allowlist (i.e. in).
        If False, it's a denylist (i.e. not in)
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "interactive".

    Returns
    -------
    list[str] | str
        List of selected variable names, or control token "__BACK__" / "__EXIT__".
    """
    say("-" * 30 + f"\nVariable Selection [{session.get('dataset_short_name')}]:\n" + "-" * 30, logger=logger)
    say("(Type 'back' to return to previous step or 'exit' to quit.)", logger=logger)

    while True:
        raw = read_input("\nEnter variable names (comma-separated): ", logger=logger)
        if raw in ("__EXIT__", "__BACK__"):
            return raw

        variable_list = [ v.strip().lower().strip('"').strip("'") for v in raw.split(",") if v.strip() ]
        if not variable_list:
            say("\nERROR: Please enter at least one variable name.", logger=logger)
            continue

        all_valid = validate_variables(variable_list, variable_restrictions_list, restriction_allow)

        if not all_valid:
            if restriction_allow:
                valid_vars = [v for v in variable_list if v in variable_restrictions_list]
                invalid_vars = [v for v in variable_list if v not in variable_restrictions_list]
                say("\nERROR: Some variables are not recognized or not available for this dataset:", logger=logger)
                for iv in invalid_vars:
                    say(f"   - {iv}", logger=logger, run_mode=run_mode)
            else:
                valid_vars = [v for v in variable_list if v not in variable_restrictions_list]
                invalid_vars = [v for v in variable_list if v in variable_restrictions_list]
                say("\nERROR: The following variables are known to cause issues or are disallowed for this dataset:", logger=logger)
                for iv in invalid_vars:
                    say(f"   - {iv}", logger=logger, run_mode=run_mode)
                say("\nPlease edit the invalid variable list for this dataset if you believe this is an error.", logger=logger)

            if valid_vars:
                proceed = read_input(
                    f"\nWould you like to proceed with only the valid variables ({', '.join(valid_vars)})? (y/n): ",
                    logger=logger, run_mode=run_mode
                ).strip().lower()
                if proceed in NORMALIZATION_MAP["confirmation"] and NORMALIZATION_MAP["confirmation"][proceed] == "yes":
                    say("\nProceeding with valid subset.\n", logger=logger)
                    session.set("variables", valid_vars)
                    return valid_vars
                else:
                    say("\nLet's try again.\n", logger=logger)
                    continue
            else:
                say("\nERROR: No valid variables remain. Please try again.\n", logger=logger)
                continue

        say(f"\nYou selected {len(variable_list)} valid variables:\n{', '.join(variable_list)}", logger=logger)
        confirm = read_input("\nConfirm selection? (y/n): ", logger=logger)
        if confirm in NORMALIZATION_MAP["confirmation"] and NORMALIZATION_MAP["confirmation"][confirm] == "yes":
            session.set("variables", variable_list)
            return variable_list
        else:
            say("\nLet's try again.\n", logger=logger)


# 10 - EXISTING FILE POLICY (existing_file_action)
def prompt_skip_overwrite_files(
        session: SessionState,
        *,
        logger=None,
        run_mode: str = "interactive"
        ) -> str:
    """
    Prompt user to choose skip/overwrite/case-by-case for existing files.

    Parameters
    ----------
    session : SessionState
        Session state to store user choice.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "interactive".

    Returns
    -------
    str
        One of "overwrite_all", "skip_all", "case_by_case"
    """

    say("\nChoose how to proceed with existing files:\n", logger=logger)
    say("\t1. Overwrite all existing files\n\t2. Skip all existing files\n\t3. Case-by-case confirmation", logger=logger)

    while True:
        choice = read_input("\nEnter choice (1/2/3): ", logger=logger)
        if choice in ("__EXIT__", "__BACK__"):
            return choice
        if choice in ["1", "2", "3"]:
            break
        say("Invalid input. Please enter 1, 2, or 3.", logger=logger)

    if choice == "1":
        session.set("existing_file_action", "overwrite_all")
    elif choice == "2":
        session.set("existing_file_action", "skip_all")
    else:
        session.set("existing_file_action", "case_by_case")

    say(f"You selected option {choice} - {session.get('existing_file_action')}", logger=logger)
    return session.get("existing_file_action")



# 11 - PARALLELISATION SETTINGS (parallel_settings)
def prompt_parallelisation_settings(
        session: SessionState,
        *,
        logger=None,
        run_mode: str = "interactive"
        ) -> dict | str:
    """
    Ask user about parallel downloads and concurrency cap.

    Parameters
    ----------
    session : SessionState
        Current session state to store parallelisation settings.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "interactive".

    Returns
    -------
    dict | str
        Dictionary with parallelisation settings, or control token "__BACK__" / "__EXIT__".
    """
    say("-"*30 + "\nParallelisation Settings:\n" + '-'*30, logger=logger, run_mode=run_mode)
    say("You can enable multiple parallel downloads to speed up retrieval.\nNote: The CDS API may throttle or reject requests if too many are opened concurrently.\n",
        logger=logger, run_mode=run_mode)

    while True:
        raw = read_input("\nEnable parallel downloads? (y/n) [default y]: ", logger=logger)
        if raw in ("__EXIT__", "__BACK__"):
            return raw

        if raw == "":
            user_choice = "yes"
        elif raw in NORMALIZATION_MAP["confirmation"]:
            user_choice = NORMALIZATION_MAP["confirmation"][raw]
        else:
            say("\nInvalid input. Please enter 'y' or 'n'.", logger=logger)
            continue

        if user_choice == "no":
            settings = {"enabled": False, "max_concurrent": 1}
            session.set("parallel_settings", settings)
            say("\nYou have disabled parallel downloads (single-threaded mode).", logger=logger)
            return settings

        while True:
            mc = read_input("\nEnter the maximum number of concurrent downloads you would like to allow (integer ≥ 2) [default 2]: ",
                            logger=logger)
            if mc in ("__EXIT__", "__BACK__"):
                return mc
            try:
                mc = int(mc) if mc else 2
            except ValueError:
                say("\nERROR: Please enter a valid integer.", logger=logger)
                continue
            if mc < 2:
                say("\nERROR: Parallel mode requires at least 2 concurrent downloads.", logger=logger)
                continue
            if mc > 2:
                say("\nWARNING: Using more than 2 parallel CDS downloads may cause throttling or request failures.", logger=logger)
                while True:
                    confirm = read_input("\nDo you still want to continue? (y/n): ", logger=logger)
                    if confirm in ("__EXIT__", "__BACK__"):
                        return confirm
                    if confirm in NORMALIZATION_MAP["confirmation"]:
                        confirm_choice = NORMALIZATION_MAP["confirmation"][confirm]
                        break
                    say("\nInvalid input. Please enter 'y' or 'n'.", logger=logger)
                if confirm_choice == "no":
                    continue

            settings = {"enabled": True, "max_concurrent": mc}
            session.set("parallel_settings", settings)
            say(f"\nYou have enabled parallel downloads with a maximum of [{mc}] concurrent downloads.", logger=logger)
            return settings


# 12 - RETRY SETTINGS (retry_settings)
def prompt_retry_settings(
        session: SessionState,
        default_retries: int = 6,
        default_delay: int = 15,
        *,
        logger=None,
        run_mode: str = "interactive"
        ) -> dict | str:
    """
    Ask user for retry limits.

    Parameters
    ----------
    session : SessionState
        Current session state to store retry settings.
    default_retries : int
        Default number of retry attempts (default = 6).
    default_delay : int
        Default delay (in seconds) between retries (default = 15).
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "interactive".

    Returns
    -------
    dict | str
        Dictionary with 'max_retries' and 'retry_delay_sec', or control token "__BACK__" / "__EXIT__".
    """
    say("-"*30 + "\nRetry Settings:\n" + '-'*30, logger=logger, run_mode=run_mode)
    say("These settings control how the program handles failed download attempts.", logger=logger)
    say(f"Default values → Retries: {default_retries}, Delay: {default_delay}s", logger=logger)

    while True:
        user_input = read_input("\nWould you like to use the default retry settings? (y/n) [default y]: ",
                                logger=logger)
        if user_input in ("__EXIT__", "__BACK__"):
            return user_input

        if user_input == "":
            normalized = "yes"
        elif user_input in NORMALIZATION_MAP["confirmation"]:
            normalized = NORMALIZATION_MAP["confirmation"][user_input]
        else:
            say("\nERROR: Invalid input. Please enter 'y' or 'n'.", logger=logger)
            continue

        if normalized == "yes":
            settings = {"max_retries": default_retries, "retry_delay_sec": default_delay}
            session.set("retry_settings", settings)
            say(f"\nUsing default retry settings of max_retries: {default_retries}, retry_delay_sec: {default_delay}", logger=logger)
            return settings

        while True:
            max_retries_raw = read_input("\nEnter maximum number of retries (integer ≥ 0): ", logger=logger)
            if max_retries_raw in ("__EXIT__", "__BACK__"):
                return max_retries_raw
            delay_raw = read_input("\nEnter delay between retries (seconds, integer ≥ 0): ", logger=logger)
            if delay_raw in ("__EXIT__", "__BACK__"):
                return delay_raw

            try:
                max_retries = int(max_retries_raw) if max_retries_raw else default_retries
                retry_delay_sec = int(delay_raw) if delay_raw else default_delay
                if max_retries < 0 or retry_delay_sec < 0:
                    say("\nERROR: Values must be non-negative integers.", logger=logger)
                    continue
                settings = {"max_retries": max_retries, "retry_delay_sec": retry_delay_sec}
                session.set("retry_settings", settings)
                say(f"\nYou set max_retries={max_retries}, retry_delay_sec={retry_delay_sec}.", logger=logger)
                return settings
            except ValueError:
                say("Please enter valid integer values for retries and delay.", logger=logger)


# 13 - DOWNLOAD SUMMARY AND CONFIRMATION
def prompt_continue_confirmation(
        summary_text: str | SessionState,
        *,
        logger=None,
        run_mode: str = "interactive"
        ) -> bool | str:
    """
    Display a formatted download summary and confirm before starting downloads.

    Parameters
    ----------
    summary_text : str | SessionState
        Formatted summary of the download configuration or session state to summarise.
    logger : logging.Logger, optional
        Logger for logging messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "interactive".

    Returns
    -------
    bool | str
        True if user confirms, False if user declines,
        or control token "__BACK__" / "__EXIT__".
    """
    if isinstance(summary_text, SessionState):
        text = summary_text.summary()
    else:
        text = summary_text
    say(text, logger=logger, run_mode=run_mode)
    while True:
        user_input = read_input("\nProceed with download? (y/n): ", logger=logger)
        if user_input in ("__EXIT__", "__BACK__"):
            return user_input
        if user_input in NORMALIZATION_MAP["confirmation"]:
            choice = NORMALIZATION_MAP["confirmation"][user_input]
            if choice == "yes":
                say("\nProceeding with download...\n", logger=logger)
                return True
            say("\nDownload cancelled by user.", logger=logger)
            return False
        say("\nERROR: Invalid input. Please enter 'y' or 'n'.", logger=logger)
