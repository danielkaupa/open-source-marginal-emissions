from importlib.metadata import PackageNotFoundError, version


from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("osme-common")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = ["__version__"]


from .paths import (
    repo_root,
    data_dir,
    config_dir,
    configs_dir,
    cache_dir,
    log_dir,
    ensure_dirs,
)
ensure_dir = ensure_dirs        # backward compatibility alias

from .version_utils import get_repo_version

__version__ = get_repo_version("osme-common")

__all__ = [
    "repo_root",
    "data_dir",
    "config_dir",
    "configs_dir",
    "cache_dir",
    "log_dir",
    "ensure_dirs",
    "__version__",
]