# packages/osme_common/src/osme_common/paths.py
# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache
from typing import Optional

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

# N/A

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# --- Markers that strongly suggest the repo root ---
_MARKERS = {
    ".git",
    "packages",
    "pyproject.toml",
    "LICENSE",
    "LICENSE.MD",
    "environment.yml",
}


def _looks_like_repo_root(p: Path) -> bool:
    """
    Heuristic check if a given path looks like the repo root.
    Checks for key marker files or directories (e.g., `.git`, `pyproject.toml`,
    `packages/`, or `environment.yml`) to decide whether `p` represents the top-level
    project folder

    Parameters
    ----------
    p : Path
        Path to check.

    Returns
    -------
    bool
            True if it looks like the repo root, False otherwise.
    """
    try:
        names = {e.name for e in p.iterdir()}
    except Exception:
        return False
    # Heuristic: either a top-level pyproject+packages OR .git with any of our known files
    if {"pyproject.toml", "packages"} <= names:
        return True
    if ".git" in names and ({"packages", "environment.yml", "LICENSE", "LICENSE.MD"} & names):
        return True
    return False


def _search_upwards(start: Path) -> Optional[Path]:
    """
    Search upwards from the provided start path to find the repo root.
    This is an internal helper for `repo_root()`, which uses it to find the top-level
    project directory regardless of where the code is executed from.

    Parameters
    ----------
    start : Path
        Starting path for the search.

    Returns
    -------
    Optional[Path]
        The path to the repo root if found, None otherwise.
    """
    start = start.resolve()
    for parent in (start, *start.parents):
        if _looks_like_repo_root(parent):
            return parent
    return None


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """
    Determine and return the absolute path to the OSME repository root directory.
    Search order:
        1. OSME_REPO_ROOT environment variable (if set)
        2. Search upward from this file’s location
        3. Search upward from the current working directory
        4. Fallback to `~/.osme` if no repo-like structure is found

    Parameters
    ----------
    None

    Returns
    -------
    Path
        Path to the OSME repository root directory.
    """
    # 1) Explicit override
    env = os.getenv("OSME_REPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()

    # 2) Walk up from this file (works with editable installs)
    here = Path(__file__).resolve()
    found = _search_upwards(here)
    if found:
        return found

    # 3) Walk up from CWD (useful when running from repo root)
    found = _search_upwards(Path.cwd())
    if found:
        return found

    # 4) Final fallback: user-scoped area so installs still work
    return Path.home().joinpath(".osme").resolve()


def _env_or_default(
        env_name: str,
        default_rel: str
        ) -> Path:
    """
    Resolve a directory path from an environment variable or a default relative to the repo root.
    Return ENV path if set, else <repo_root>/<default_rel> (or ~/.osme/<default_rel> in fallback).

    This utility underpins all directory helpers (e.g., `data_dir`, `config_dir`, etc.).
    It ensures consistent resolution logic between environment-variable overrides and
    repo-relative defaults.

    Parameters
    ----------
    env_name : str
        Name of the environment variable to check.
    default_rel : str
        Default relative path under the repo root.

    Returns
    -------
    Path
        Resolved path.
    """
    v = os.getenv(env_name)
    if v:
        return Path(v).expanduser().resolve()
    return (repo_root() / default_rel).resolve()


def data_dir(create: bool = False) -> Path:
    """
    Return the standard data directory path.

    Resolution order:
        1. Environment variable `OSME_DATA_DIR`
        2. `<repo_root>/data`
        3. `~/.osme/data` fallback

    Parameters
    ----------
    create : bool
        Whether to create the directory if it doesn't exist.

    Returns
    -------
    Path
        Path to the data directory.
    """
    p = _env_or_default("OSME_DATA_DIR", "data")
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir(create: bool = False) -> Path:
    """
    Return the standard configuration directory path.

    Resolution order:
        1. Environment variable `OSME_CONFIG_DIR`
        2. `<repo_root>/configs`
        3. `~/.osme/configs` fallback
    Parameters
    ----------
    create : bool
        Whether to create the directory if it doesn't exist.

    Returns
    -------
    Path
        Path to the config directory.
    """
    p = _env_or_default("OSME_CONFIG_DIR", "configs")
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


# Back-compat alias if some code uses the plural
def configs_dir(create: bool = False) -> Path:
    """ Alias for config_dir for backward compatibility."""
    return config_dir(create=create)


def cache_dir(create: bool = False) -> Path:
    """
    Return the cache directory path for intermediate computations.

    Resolution order:
        1. Environment variable `OSME_CACHE_DIR`
        2. `<repo_root>/.cache`
        3. `~/.osme/.cache` fallback

    Parameters
    ----------
    create : bool
        Whether to create the directory if it doesn't exist.

    Returns
    -------
    Path
        Path to the cache directory.
    """
    p = _env_or_default("OSME_CACHE_DIR", ".cache")
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def log_dir(create: bool = False) -> Path:
    """
    Return the log directory path for storing execution and audit logs.

    Resolution order:
        1. Environment variable `OSME_LOG_DIR`
        2. `<repo_root>/logs`
        3. `~/.osme/logs` fallback

    Parameters
    ----------
    create : bool
        Whether to create the directory if it doesn't exist.

    Returns
    -------
    Path
        Path to the log directory.
    """
    p = _env_or_default("OSME_LOG_DIR", "logs")
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_dirs() -> None:
    """Ensure that all standard writable directories exist.

    This includes data, cache, and log directories. Useful for setup
    during initialization or CLI entry points.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    for d in (data_dir(), cache_dir(), log_dir()):
        d.mkdir(parents=True, exist_ok=True)


def resolve_under(
        base: Path,
        maybe_rel: str | Path
        ) -> Path:
    """
    Resolve a path relative to a given base directory if not already absolute.
    If path is absolute, return as-is.

    This helper simplifies path normalization when accepting user input,
    configuration values, or relative file references.

    Parameters
    ----------
    base : Path
        Base directory for relative paths.
    maybe_rel : str | Path
        Path to resolve.

    Returns
    -------
    Path
        Resolved absolute path.
    """
    p = Path(maybe_rel)
    return p if p.is_absolute() else (base / p).resolve()


def find_config(
        filename: str,
        subdir: str | None = None
        ) -> Path:
    """
    Locate a configuration file across standard search locations.

    Search order:
        1. Environment-defined config directory (if set)
        2. `<repo_root>/configs[/subdir]/`
        3. `~/.osme/configs[/subdir]/`

    e.g. >>> find_config("download_request_world.json", subdir="weather")

    Parameters
    ----------
    filename : str
        Name of the config file to find.
    subdir : str | None
        Optional subdirectory under configs/ to look in.

    Returns
    -------
    Path
        Resolved path to the config file.

    Raises
    -------
    FileNotFoundError
        If the config file is not found in any of the standard locations.
    """
    candidates = []
    base = config_dir()  # already resolves ENV or defaults
    if subdir:
        candidates.append(base / subdir / filename)
        candidates.append(base / subdir / filename.lower())
    candidates.append(base / filename)
    candidates.append(base / filename.lower())

    # As a last resort, look in ~/.osme/configs[/subdir]
    home_cfg = Path.home() / ".osme" / "configs"
    if subdir:
        candidates.append(home_cfg / subdir / filename)
        candidates.append(home_cfg / subdir / filename.lower())
    candidates.append(home_cfg / filename)
    candidates.append(home_cfg / filename.lower())

    for c in candidates:
        if c.exists():
            return c.resolve()
    raise FileNotFoundError(f"Config not found. Tried: " + ", ".join(str(c) for c in candidates))
