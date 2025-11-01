from importlib.metadata import PackageNotFoundError, version
from .paths import repo_root, data_dir, configs_dir, ensure_dir

try:
    __version__ = version("osme-common")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = ["repo_root", "data_dir", "configs_dir", "ensure_dir", "__version__"]