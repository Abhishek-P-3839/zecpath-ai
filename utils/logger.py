"""Simple logging setup for all AI activities.

Usage:
    from utils.logger import get_logger
    log = get_logger(__name__)
    log.info("Resume parsed")

Logs are printed on the screen and saved in logs/ai_activity.log
"""
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "ai_activity.log")
FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def get_logger(name):
    """Return a logger that writes to console and to the log file."""
    logger = logging.getLogger(name)
    if logger.handlers:  # already set up, do not add handlers twice
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(FORMAT)

    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
