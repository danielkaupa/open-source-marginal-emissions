"""
Configuration loader for grid data processing.

This module handles loading and validating configuration files for the
grid data processing pipeline. It integrates with osme_common.paths to
find configs in standard locations.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional

from osme_common.paths import find_config


def load_config(config_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """
    Load configuration from JSON file.
    
    If no path is provided, attempts to find 'default_processing.json' in
    standard config locations using osme_common.paths.find_config().
    
    Parameters
    ----------
    config_path : Path or str, optional
        Path to configuration file. If None, searches for default_processing.json
        in configs/grid_data_processing/ directory.
        
    Returns
    -------
    dict
        Configuration dictionary with validated structure
        
    Raises
    ------
    FileNotFoundError
        If config file not found in any standard location
    ValueError
        If config file has invalid structure or missing required keys
        
    Examples
    --------
    >>> # Load default config
    >>> config = load_config()
    >>> 
    >>> # Load specific config file
    >>> config = load_config("configs/grid_data_processing/custom.json")
    """
    if config_path is None:
        # Try to find default config using osme_common
        try:
            config_path = find_config(
                "default_processing.json", 
                subdir="grid_data_processing"
            )
        except FileNotFoundError:
            # Fall back to default configuration
            return get_default_config()
    
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Validate and fill in any missing sections with defaults
    config = merge_with_defaults(config)
    validate_config(config)
    
    return config


def get_default_config() -> Dict[str, Any]:
    """
    Get default configuration for grid data processing.
    
    This configuration defines:
    - Data frequency (5-minute intervals)
    - Gap filling parameters (short/long gap thresholds, columns to fill)
    - Aggregation settings (target interval, columns to average/sum)
    - Timezone settings (target timezone for labeling)
    
    Returns
    -------
    dict
        Default configuration dictionary
    """
    return {
        "data_frequency_minutes": 5,
        "gap_filling": {
            "short_gap_threshold_minutes": 80,
            "ref_column": "demand_met",
            "columns_to_fill": [
                "thermal_generation",
                "gas_generation",
                "hydro_generation",
                "nuclear_generation",
                "renewable_generation",
                "tons_co2",
                "total_generation",
                "demand_met",
                "net_demand"
            ],
            "gradient": {
                "max_search_days": 21,
                "smooth_window_slots": 3,
                "prefer_same_weekday": True
            }
        },
        "aggregation": {
            "target_interval_minutes": 30,
            "avg_columns": [
                "thermal_generation",
                "gas_generation",
                "hydro_generation",
                "nuclear_generation",
                "renewable_generation",
                "total_generation",
                "demand_met",
                "net_demand",
                "g_co2_per_kwh",
                "tons_co2_per_mwh"
            ],
            "sum_columns": ["tons_co2"]
        },
        "timezone": {
            "target": "Asia/Kolkata"
        }
    }


def merge_with_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge user config with defaults, filling in missing sections.
    
    This ensures that even partial configs work by inheriting defaults
    for any sections not explicitly provided.
    
    Parameters
    ----------
    config : dict
        User-provided configuration (may be incomplete)
        
    Returns
    -------
    dict
        Complete configuration with defaults filled in
    """
    defaults = get_default_config()
    
    # Deep merge - preserve user values, add defaults for missing keys
    merged = defaults.copy()
    for key, value in config.items():
        if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
            # Recursively merge nested dicts
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    
    return merged


def validate_config(config: Dict[str, Any]) -> None:
    """
    Validate configuration has required structure and keys.
    
    Checks for presence of required sections and their necessary fields.
    Raises descriptive errors if validation fails.
    
    Parameters
    ----------
    config : dict
        Configuration dictionary to validate
        
    Raises
    ------
    ValueError
        If required sections or keys are missing, or if values are invalid
    """
    # Check top-level sections
    required_sections = ["gap_filling", "aggregation", "timezone"]
    for section in required_sections:
        if section not in config:
            raise ValueError(
                f"Config missing required section: '{section}'. "
                f"Required sections: {required_sections}"
            )
    
    # Validate gap_filling section
    gap_config = config["gap_filling"]
    required_gap_keys = ["ref_column", "columns_to_fill", "gradient"]
    for key in required_gap_keys:
        if key not in gap_config:
            raise ValueError(
                f"gap_filling config missing required key: '{key}'. "
                f"Required keys: {required_gap_keys}"
            )
    
    # Validate gradient subsection
    gradient_config = gap_config["gradient"]
    required_gradient_keys = ["max_search_days", "smooth_window_slots", "prefer_same_weekday"]
    for key in required_gradient_keys:
        if key not in gradient_config:
            raise ValueError(
                f"gap_filling.gradient config missing required key: '{key}'. "
                f"Required keys: {required_gradient_keys}"
            )
    
    # Validate aggregation section
    agg_config = config["aggregation"]
    required_agg_keys = ["avg_columns", "sum_columns"]
    for key in required_agg_keys:
        if key not in agg_config:
            raise ValueError(
                f"aggregation config missing required key: '{key}'. "
                f"Required keys: {required_agg_keys}"
            )
    
    # Validate timezone section
    tz_config = config["timezone"]
    if "target" not in tz_config:
        raise ValueError("timezone config missing required key: 'target'")


def save_config(config: Dict[str, Any], output_path: Path | str) -> None:
    """
    Save configuration to JSON file.
    
    Useful for creating template configs or saving modified configurations.
    
    Parameters
    ----------
    config : dict
        Configuration dictionary to save
    output_path : Path or str
        Output file path for the JSON config
        
    Examples
    --------
    >>> config = get_default_config()
    >>> save_config(config, "configs/grid_data_processing/my_config.json")
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)
