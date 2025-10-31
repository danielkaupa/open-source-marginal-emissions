
import json
import os
from weather_data_retrieval.utils.data_validation import validate_config


def load_and_validate_config(
        path: str,
        *,
        logger=None,
        run_mode: str = "automatic") -> dict:
    """
    Load JSON config and validate it using the centralized validator.
    This lets the validator log coercions/warnings (e.g., case_by_case → skip_all).

    Parameters
    ----------
    path : str
        Path to JSON config file.
    logger : logging.Logger, optional
        Logger instance for validation messages, by default None.
    run_mode : str, optional
        Run mode, either 'interactive' or 'automatic', by default "automatic".

    Returns
    -------
    dict
        Validated configuration dictionary.
    """
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    # Let validate_config perform normalization/clamping with logging context
    validate_config(config, logger=logger, run_mode=run_mode)
    return config


def load_config(file_path: str) -> dict:
    """
    Load configuration from a JSON requirements file (without validation).

    Parameters
    ----------
    file_path : str
        Path to JSON config file.

    Returns
    -------
    dict
        Configuration dictionary.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
