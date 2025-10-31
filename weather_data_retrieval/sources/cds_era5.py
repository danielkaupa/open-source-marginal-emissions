# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
import os
import time
from typing import Optional, Tuple, List

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from weather_data_retrieval.utils.session_management import (
    SessionState,
    ensure_cds_connection,
    get_cds_dataset_config,
)
from weather_data_retrieval.utils.data_validation import (
    format_duration,
    NORMALIZATION_MAP,
    CDS_DATASETS,
    month_days,
    validate_existing_file_action,
)
from weather_data_retrieval.utils.file_management import find_existing_month_file
from weather_data_retrieval.io.prompts import read_input
from weather_data_retrieval.utils.logging import log_msg


# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------


def prepare_cds_download(
    session: SessionState,
    filename_base: str,
    year: int,
    month: int,
    *,
    logger,
    echo_console: bool,
    allow_prompts: bool,
    dataset_config_mapping: dict = CDS_DATASETS,
) -> Tuple[bool, str]:
    """
    Check if a monthly ERA5 file already exists and decide whether to download.

    Parameters
    ----------
    session : SessionState
        Session containing user configuration.
    filename_base : str
        Base name for the file.
    year : int
        Year of the data to download.
    month : int
        Month of the data to download.
    logger : logging.Logger, optional
        Logger for logging messages.
    echo_console : bool
        Whether to echo prompts to console.
    allow_prompts : bool
        Whether to allow interactive prompts.
    dataset_config_mapping : dict, optional
        Mapping of dataset short names to their configurations.

    Returns
    -------
    tuple: (download: bool, save_path: str)
        download: Whether to perform the download.
        save_path: Full path for the target file.
    """
    cfg = get_cds_dataset_config(session, dataset_config_mapping)
    data_file_format = cfg.get("data_download_format", "grib")

    save_dir = str(session.get("save_dir"))
    policy = session.get("existing_file_action")  # 'overwrite_all' | 'skip_all' | 'case_by_case'
    save_path = os.path.join(save_dir, f"{filename_base}_{year}_{month:02d}.{data_file_format}")
    download = True

    if os.path.exists(save_path):
        if policy == "skip_all":
            log_msg(f"Skipping existing file for {year}-{month:02d}: {save_path}", logger, echo_console=echo_console)
            download = False

        elif policy == "overwrite_all":
            log_msg(f"Overwriting existing file for {year}-{month:02d}: {save_path}", logger, echo_console=echo_console)

        elif policy == "case_by_case":
            if not allow_prompts:
                raise ValueError(
                    "existing_file_action='case_by_case' requires interactive mode. "
                    "Use 'skip_all' or 'overwrite_all' for automatic runs."
                )
            while True:
                user_input = read_input(
                    f"\nFile already exists for {year}-{month:02d}: {save_path}\n"
                    "Do you want to overwrite it? (y/n): ",
                    logger=logger,
                    run_mode="interactive",
                )
                if user_input in NORMALIZATION_MAP["confirmation"]:
                    yn = NORMALIZATION_MAP["confirmation"][user_input]
                    if yn == "yes":
                        log_msg(
                            f"Overwriting existing file for {year}-{month:02d}: {save_path}",
                            logger, echo_console=echo_console
                        )
                        download = True
                    else:
                        log_msg(
                            f"Skipping existing file for {year}-{month:02d}: {save_path}",
                            logger, echo_console=echo_console
                        )
                        download = False
                    break
                log_msg("Invalid input. Please enter 'y' or 'n'.", logger, echo_console=echo_console)
        else:
            log_msg(
                f"Unknown existing_file_action policy '{policy}'; defaulting to 'skip_all'.",
                logger, level="warning", echo_console=echo_console
            )
            session.set("existing_file_action", "skip_all")
            download = False

    return download, save_path

def execute_cds_download(
        session: SessionState,
        save_path: str,
        year: int,
        month: int,
        *,
        logger,
        echo_console: bool,
        dataset_config_mapping: dict = CDS_DATASETS,
        ) -> tuple[int, int, str]:
    """
    Execute a single ERA5 monthly download with retry logic.

    Parameters
    ----------
    session : SessionState
        Session state containing the authenticated CDS API client.
    save_path : str
        Full path to save the downloaded file.
    year : int
        Year of the data to download.
    month : int
        Month of the data to download.
    logger : logging.Logger, optional
        Logger for logging messages.
    echo_console : bool
        Whether to echo prompts to console.
    dataset_config_mapping : dict, optional
        Mapping of dataset short names to their configurations.

    Returns
    -------
    (year, month, status): tuple
        status = "success" | "failed"
    """
    # Pull config fresh from CDS_DATASETS
    cfg = get_cds_dataset_config(session, dataset_config_mapping=dataset_config_mapping)
    dataset_product_name = cfg["dataset_product_name"]
    product_type = cfg["product_type"]
    data_download_format = cfg.get("data_download_format", "grib")
    times = cfg.get("default_times", [f"{h:02d}:00" for h in range(24)])

    variables = session.get("variables")
    grid_area = session.get("region_bounds")
    cds_client_session = session.get("session_client")
    if cds_client_session is None:
        raise ValueError("CDS client not initialized in session")

    retry_conf = session.get("retry_settings") or {"max_retries": 6, "retry_delay_sec": 15}
    max_retries = retry_conf["max_retries"]
    retry_delay_sec = retry_conf["retry_delay_sec"]
    days = month_days(year, month)

    month_start = time.time()
    for attempt in range(1, max_retries + 1):
        try:
            log_msg(f"\tAttempt {attempt} of {max_retries} for {year}-{month:02d}...", logger, echo_console=echo_console)
            cds_client_session.retrieve(
                dataset_product_name,
                {
                    "product_type": [product_type],
                    "variable": variables,
                    "year": str(year),
                    "month": [f"{month:02d}"],
                    "day": days,
                    "time": times,
                    "area": grid_area,
                    "format": data_download_format,
                },
                save_path,
            )
            elapsed = time.time() - month_start
            log_msg(f"SUCCESS: {year}-{month:02d} in {format_duration(elapsed)}", logger, echo_console=echo_console)
            return (year, month, "success")

        except Exception as e:
            log_msg(f"WARNING: Attempt {attempt} failed for {year}-{month:02d}: {e}", logger, level="warning", echo_console=echo_console)
            if attempt < max_retries:
                log_msg(f"\tWaiting {retry_delay_sec} seconds before retrying...", logger, echo_console=echo_console)
                time.sleep(retry_delay_sec)
                try:
                    api_url, api_key = session.get("api_url"), session.get("api_key")
                    creds_dict = {"url": api_url, "key": api_key}
                    cds_client_session_new = ensure_cds_connection(cds_client_session, creds_dict)
                    if cds_client_session_new is None:
                        raise RuntimeError("Re-authentication returned None client.")
                    session.set("session_client", cds_client_session_new)
                    cds_client_session = cds_client_session_new
                    log_msg("\tRe-authenticated CDS API client.", logger, echo_console=echo_console)
                except Exception as auth_e:
                    log_msg(f"\tRe-authentication failed: {auth_e}", logger, level="warning", echo_console=echo_console)
            else:
                log_msg(f"FAILURE: all {max_retries} attempts failed for {year}-{month:02d}.", logger, level="error", echo_console=echo_console)
                return (year, month, "failed")


def download_cds_month(
    session: SessionState,
    filename_base: str,
    year: int,
    month: int,
    *,
    logger,
    echo_console: bool,
    allow_prompts: bool,
    successful_downloads: list,
    failed_downloads: list,
    skipped_downloads: list,
    ) -> Tuple[int, int, str]:
    """
    Orchestrate ERA5 monthly download: handle file checks, then execute download.

    Parameters
    ----------
    Combines parameters from `prepare_download` and `execute_download`.

    Returns
    -------
    (year, month, status): tuple
        status = "success" | "failed" | "skipped"

    """

    proceed, save_path = prepare_cds_download(
        session=session,
        filename_base=filename_base,
        year=year,
        month=month,
        logger=logger,
        echo_console=echo_console,
        allow_prompts=allow_prompts,
        dataset_config_mapping=CDS_DATASETS,
    )

    if not proceed:
        skipped_downloads.append((year, month))
        return (year, month, "skipped")

    y, m, status = execute_cds_download(
        session=session,
        save_path=save_path,
        year=year,
        month=month,
        logger=logger,
        echo_console=echo_console,
        dataset_config_mapping=CDS_DATASETS,
    )

    if status == "success":
        successful_downloads.append((y, m))
    else:
        failed_downloads.append((y, m))
    return (y, m, status)


def plan_cds_months(
    session: SessionState,
    filename_base: str,
    *,
    logger,
    echo_console: bool,
    allow_prompts: bool,
) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int, Path]]]:
    """
    Build the list of months to download and which are being skipped due to existing files.

    Parameters
    ----------
    session : SessionState
        Session containing user configuration.
    filename_base : str
        Base filename (without date or extension).
    logger : logging.Logger, optional
        Logger for logging messages.
    echo_console : bool
        Whether to echo prompts to console.
    allow_prompts : bool
        Whether to allow interactive prompts.

    Returns
    -------
    (months_to_download, months_skipped)
      - months_to_download: list[(year, month)]
      - months_skipped: list[(year, month, path)]
    """
    policy = validate_existing_file_action(session, allow_prompts=allow_prompts, logger=logger, echo_console=echo_console)

    start_date = session.get("start_date")
    end_date = session.get("end_date")
    save_dir = Path(session.get("save_dir"))

    s = datetime.strptime(start_date, "%Y-%m-%d")
    e = datetime.strptime(end_date, "%Y-%m-%d")

    # Build month list
    months: List[Tuple[int, int]] = []
    cur = datetime(s.year, s.month, 1)
    while cur <= e:
        months.append((cur.year, cur.month))
        cur = datetime(cur.year + 1, 1, 1) if cur.month == 12 else datetime(cur.year, cur.month + 1, 1)

    months_to_download: List[Tuple[int, int]] = []
    months_skipped: List[Tuple[int, int, Path]] = []

    for (y, m) in months:
        existing = find_existing_month_file(save_dir, filename_base, y, m)
        if existing is None:
            months_to_download.append((y, m))
            continue

        if policy == "skip_all":
            months_skipped.append((y, m, existing))
        elif policy == "overwrite_all":
            months_to_download.append((y, m))
        else:
            # interactive 'case_by_case'
            while True:
                ans = read_input(
                    f"\nFile already exists for {y}-{m:02d}: {existing}\n"
                    f"Overwrite this one? (y/n): ",
                    logger=logger,
                    run_mode="interactive",
                )
                if ans in NORMALIZATION_MAP["confirmation"]:
                    yn = NORMALIZATION_MAP["confirmation"][ans]
                    if yn == "yes":
                        months_to_download.append((y, m))
                    else:
                        months_skipped.append((y, m, existing))
                    break
                log_msg("Please enter 'y' or 'n'.", logger, echo_console=echo_console)

    # Report
    log_msg("\n=== Existing File Check ===", logger, echo_console=echo_console)
    log_msg(f"Found {len(months_skipped)} existing monthly files.", logger, echo_console=echo_console)
    if months_skipped:
        for y, m, p in months_skipped[:5]:
            log_msg(f"  - {y}-{m:02d}: {p}", logger, echo_console=echo_console)
        if len(months_skipped) > 5:
            log_msg(f"  ... and {len(months_skipped)-5} more.", logger, echo_console=echo_console)
    log_msg(f"Planned downloads: {len(months_to_download)} month(s).", logger, echo_console=echo_console)

    return months_to_download, months_skipped


def orchestrate_cds_downloads(
        session: SessionState,
        filename_base: str,
        successful_downloads: list,
        failed_downloads: list,
        skipped_downloads: list,
        *,
        logger,
        echo_console: bool,
        allow_prompts: bool,
        dataset_config_mapping: dict = CDS_DATASETS,
        ) -> None:
    """
    Handle and orchestrate ERA5 monthly downloads, supporting parallel or sequential execution.

    Parameters
    ----------
    session : SessionState
        Session containing user configuration and authenticated client.
    successful_downloads : list
        Mutable list to collect (year, month) tuples for successful downloads.
    failed_downloads : list
        Mutable list to collect (year, month) tuples for failed downloads.
    skipped_downloads : list
        Mutable list to collect (year, month) tuples for skipped downloads.
    logger : logging.Logger, optional
        Logger for logging messages.
    echo_console : bool
        Whether to echo prompts to console.
    allow_prompts : bool
        Whether to allow interactive prompts.
    dataset_config_mapping : dict, optional
        Mapping of dataset configurations, by default CDS_DATASETS.

    Returns
    -------
    None
    """

    # (Optional) touch cfg to ensure dataset is valid; not stored, just validation side-effect
    _ = get_cds_dataset_config(session, CDS_DATASETS)

    months_to_download, months_skipped = plan_cds_months(
        session=session,
        filename_base=filename_base,
        logger=logger,
        echo_console=echo_console,
        allow_prompts=allow_prompts,
    )

    for (y, m, _) in months_skipped:
        skipped_downloads.append((y, m))

    if not months_to_download:
        log_msg("\nNothing to download (all months skipped).", logger, echo_console=echo_console)
        return

    parallel_conf = session.get("parallel_settings") or {"enabled": False, "max_concurrent": 1}

    if parallel_conf.get("enabled"):
        max_workers = max(2, int(parallel_conf.get("max_concurrent", 2)))
        log_msg(f"\nParallel downloads enabled ({max_workers} concurrent tasks)...", logger, echo_console=echo_console)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            tasks = [
                executor.submit(
                    download_cds_month,
                    session=session,
                    filename_base=filename_base,
                    year=y,
                    month=m,
                    logger=logger,
                    echo_console=echo_console,
                    allow_prompts=allow_prompts,
                    successful_downloads=successful_downloads,
                    failed_downloads=failed_downloads,
                    skipped_downloads=skipped_downloads,
                )
                for (y, m) in months_to_download
            ]
            for _ in as_completed(tasks):
                pass
    else:
        log_msg("\nRunning in sequential download mode...", logger, echo_console=echo_console)
        for (y, m) in months_to_download:
            download_cds_month(
                session=session,
                filename_base=filename_base,
                year=y,
                month=m,
                logger=logger,
                echo_console=echo_console,
                allow_prompts=allow_prompts,
                successful_downloads=successful_downloads,
                failed_downloads=failed_downloads,
                skipped_downloads=skipped_downloads,
            )