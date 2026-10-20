"""Logging configuration for MayuriShell."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "mayurishell"


def setup_logging(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Configure rotating file logging for MayuriShell.
    
    Logs rotate at ~1MB with up to 3 backup files.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mayurishell.log"

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_file,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s:%(module)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def get_logger() -> logging.Logger:
    """Retrieve the application logger."""
    return logging.getLogger(LOGGER_NAME)
