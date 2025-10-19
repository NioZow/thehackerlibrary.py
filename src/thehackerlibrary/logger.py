"""Logging module"""

import logging
import os
from pathlib import Path
from typing import Optional

from colorama import Fore, Style


class Logger:
    """Logging module"""

    def __init__(self, name: str, filepath: Optional[str], debug_enabled: bool):
        self.logger = logging.getLogger(name)
        self.filepath = filepath
        self.debug_enabled = debug_enabled

        self.setup()

    def info(self, message: str):
        """Log an info message"""
        self.logger.info(f"[{Fore.GREEN}{Style.BRIGHT}+{Style.RESET_ALL}] {message}")

    def debug(self, message: str):
        """Log a debug message"""
        self.logger.debug(f"[{Fore.BLUE}{Style.BRIGHT}*{Style.RESET_ALL}] {message}")

    def warning(self, message: str):
        """Log an warning message"""
        self.logger.warning(
            f"[{Fore.YELLOW}{Style.BRIGHT}-{Style.RESET_ALL}] {message}"
        )

    def error(self, message: str):
        """Log an error message"""
        self.logger.error(f"[{Fore.RED}{Style.BRIGHT}!{Style.RESET_ALL}] {message}")

    def fatal_error(self, message: str):
        """Log an error message"""
        self.error(message)
        exit(1)

    def setup(self):
        """Setup the logger with the handlers and the formatter"""
        self.logger.setLevel(logging.DEBUG)

        if self.filepath is not None:
            file_handler = logging.FileHandler(self.filepath)
            file_formatter = logging.Formatter(fmt="%(asctime)s [%(name)s] %(message)s")
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(logging.DEBUG)

            self.logger.addHandler(file_handler)

        std_handler = logging.StreamHandler()
        std_formatter = logging.Formatter(fmt="%(message)s")
        std_handler.setFormatter(std_formatter)
        std_handler.setLevel(logging.INFO)

        if self.debug_enabled:
            std_handler.setLevel(logging.DEBUG)

        self.logger.addHandler(std_handler)
        self.logger.propagate = False


DATA_DIRECTORY = Path("~/.local/share/thehackerlibrary").expanduser()
LOG_FILE = DATA_DIRECTORY / "thehackerlibrary.log"
os.makedirs(str(DATA_DIRECTORY), exist_ok=True)
logger = Logger("thehackerlibrary", str(LOG_FILE), True)
