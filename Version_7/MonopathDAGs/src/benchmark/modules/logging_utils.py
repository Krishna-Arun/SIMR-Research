# This source file is part of the Daneshjou Lab projects
#
# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see AUTHORS.md)
#
# SPDX-License-Identifier: MIT
#

"""This module contains logging utilities for standardized logging across the application."""

import logging

def setup_logger(name: str) -> logging.Logger:
    """
    Initializes and returns a logger with standardized settings.

    Args:
        name: Usually __name__ from the calling module.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
