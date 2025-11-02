"""Version management for the OSME project."""

try:
    from ._version import __version__
except ImportError:
    # Fallback for when _version.py doesn't exist (editable installs, etc.)
    __version__ = "0.0.0+unknown"

# Re-export for all subpackages to use
__all__ = ["__version__"]