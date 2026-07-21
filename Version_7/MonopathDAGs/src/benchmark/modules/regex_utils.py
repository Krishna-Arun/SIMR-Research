# pylint: disable=broad-exception-caught,too-few-public-methods

# This source file is part of the Daneshjou Lab projects
#
# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see AUTHORS.md)
#
# SPDX-License-Identifier: MIT
#

"""
Provides lightweight regex-based validation for JSON-encoded graph data.
Used to catch structural formatting issues before processing.
"""

import re
import logging

logger = logging.getLogger(__name__)


class RegexValidator:
    """
    Lightweight regex checks on the raw JSON string to catch common formatting issues.

    Usage:
        json_str = json.dumps(json_graph.node_link_data(graph))
        validator = RegexValidator(json_str)
        results = validator.run()
    """

    PATTERNS = {
        "nodes_array": r'"nodes"\s*:\s*\[',
        "edges_array": r'"edges"\s*:\s*\[',
        "no_trailing_commas": r",\s*\]",
        "node_entry": r'\{\s*"id".+?\}',
        "edge_entry": r'\{\s*"source".+?"label".+?\}',
    }

    def __init__(self, json_str: str):
        self.s = json_str

    def run(self) -> dict[str, bool]:
        """
        Returns:
            Dict[str, bool]: Mapping of pattern checks to pass/fail status.
        """
        if not self.s or not isinstance(self.s, str):
            logger.warning("Invalid input to RegexValidator: %s", type(self.s))
            return {name: False for name in self.PATTERNS}

        results: dict[str, bool] = {}
        for name, pat in self.PATTERNS.items():
            try:
                found = bool(re.search(pat, self.s))
                results[name] = not found if name == "no_trailing_commas" else found
            except Exception as e:
                logger.error("Regex check '%s' failed: %s", name, str(e))
                results[name] = False
        return results
