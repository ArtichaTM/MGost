import logging
import sys
from typing import Final

__all__ = (
    'VERBOSITY_LEVELS',
    'init_logging'
)

# Default format: time, level, module, message
_LOG_FORMAT: Final[str] = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"

# Verbosity → logging level mapping
VERBOSITY_LEVELS: Final[dict[int, int]] = {
    -2: logging.CRITICAL,   # --silent
    -1: logging.ERROR,      # -q / --quiet
     0: logging.WARNING,    # default
     1: logging.INFO,       # -v
     2: logging.DEBUG,      # -vv
}

def init_logging(verbosity: int = 0) -> None:
    """
    Configure logging for the MGost CLI.

    Args:
        verbosity: Controls log level
            -2: CRITICAL (--silent)
            -1: ERROR    (-q / --quiet)
             0: WARNING  (default)
             1: INFO     (-v)
            >=2: DEBUG   (-vv)
    """
    level = VERBOSITY_LEVELS.get(verbosity, logging.DEBUG)
    
    # Avoid adding duplicate handlers if called multiple times
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
    
    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
        stream=sys.stderr,
        force=True,
    )
    from mgost.console import Console
    Console.verbosity = verbosity
