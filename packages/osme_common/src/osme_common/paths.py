# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

# N/A

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# Marker names that likely exist at the repo root
_MARKERS = {
    ".git",
    "LICENSE",
    "LICENSE.MD",
    "packages",
    "information",
    "environment.yml",
}

# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------


def _find_upwards(start: Path) -> Optional[Path]:
    """
    Walk parents from `start` to filesystem root and return the first dir containing repo markers.

    Parameters
    ----------
    start : Path
        The starting directory for the upwards search.

    Returns
    -------
    Optional[Path]
        The path to the repository root if found; otherwise, None.
    """
    p = start.resolve()
    for parent in (p, *p.parents):
        try:
            entries = {e.name for e in parent.iterdir()}
        except Exception:
            continue
        if _MARKERS & entries:
            return parent
    return None


def repo_root(start: Optional[Path] = None) -> Path:
    """
    Best-effort repo root discovery.
    Priority:
      1) OSME_REPO_ROOT env
      2) Walk upwards from `start` (or CWD) until a directory with known markers is found
      3) Fallback: user home / '.osme'

    Parameters
    ----------
    start : Optional[Path]
        Starting directory for upwards search. If None, uses current working directory.

    Returns
    -------
    Path
        The resolved repository root path.
    """
    env = os.getenv("OSME_REPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    base = Path.cwd() if start is None else Path(start)
    found = _find_upwards(base)
    if found:
        return found
    # Final fallback to a user-scoped directory so package works outside the monorepo
    return Path.home().joinpath(".osme").resolve()


def _resolve_dir(
        env_var: str,
        default_subdir: str,
        create: bool
    ) -> Path:
    """
    Resolve a canonical directory path based on environment variable, repo root, or user home.

    Parameters
    ----------
    env_var : str
        Environment variable name to check first.
    default_subdir : str
        Subdirectory name under repo root or user home.
    create : bool
        Whether to create the directory if it does not exist.

    Returns
    -------
    Path
        The resolved directory path.
        This will be the environment variable value, or the repo root path, or the user home path.
    """
    # 1) explicit env
    env_val = os.getenv(env_var)
    if env_val:
        p = Path(env_val).expanduser().resolve()
    else:
        # 2) repo_root/<subdir>
        p = repo_root().joinpath(default_subdir).resolve()
        # 3) if repo root fallback was ~/.osme, keep that convention for subdirs
        if str(p).startswith(str(Path.home().joinpath(".osme").resolve())):
            p = p  # already under ~/.osme/<subdir>
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir(create: bool = False) -> Path:
    """
    Returns the canonical data directory.
    Resolution precedence:
      OSME_DATA_DIR env > <repo_root>/data > ~/.osme/data

    Parameters
    ----------
    create : bool
        Whether to create the directory if it does not exist.

    Returns
    -------
    Path
        The resolved directory path.
        This will be the environment variable value, or the repo root path, or the user home path.
    """
    return _resolve_dir("OSME_DATA_DIR", "data", create)


def configs_dir(create: bool = False) -> Path:
    """
    Returns the canonical configs directory.
    Resolution precedence:
      OSME_CONFIGS_DIR env > <repo_root>/configs (or 'config') > ~/.osme/configs

    Parameters
    ----------
    create : bool
        Whether to create the directory if it does not exist.

    Returns
    -------
    Path
        The resolved directory path.
        This will be the environment variable value, or the repo root path, or the user home path.
    """
    # Prefer 'configs', fall back to 'config' if it exists
    root = repo_root()
    env = os.getenv("OSME_CONFIGS_DIR")
    if env:
        p = Path(env).expanduser().resolve()
    else:
        p = (root / "configs")
        if not p.exists():
            p = (root / "config")
        p = p.resolve()
        if str(root).startswith(str(Path.home().joinpath(".osme").resolve())):
            p = Path.home().joinpath(".osme", "configs").resolve()
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_dir(path: Path) -> Path:
    """
    Create a directory (parents ok) and return it.

    Parameters
    ----------
    path : Path
        The directory path to create.

    Returns
    -------
    Path
        The created directory path.
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
