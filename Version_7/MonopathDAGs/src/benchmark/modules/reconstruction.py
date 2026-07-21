# This source file is part of the Daneshjou Lab projects
#
# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see AUTHORS.md)
#
# SPDX-License-Identifier: MIT
#

"""This module provides functionality to reconstruct a clinical narrative from
a graph using a DSPy-compatible LLM."""

# pylint: disable=(broad-exception-caught, too-few-public-methods, too-many-arguments, too-many-positional-arguments)

# Standard library imports
import json
from typing import Any, Optional

# Third-party imports
import networkx as nx
import dspy

# Local application imports
from .config import Graph
from .logging_utils import setup_logger

logger = setup_logger(__name__)

"""This module provides functionality to reconstruct a clinical narrative from
a graph using a DSPy-compatible LLM.
"""


class LLMReconstructor:
    """
    Uses a DSPy-compatible LLM to reconstruct a narrative from selected parts of a graph.

    Usage:
        reconstructor = LLMReconstructor(
            model_name = LM_MODEL,
            api_base = LM_API_BASE,
            api_key= LM_API_KEY
        )
        narrative = reconstructor.reconstruct(
            graph,
            include_nodes=True,
            include_edges=False,
            node_ids=["n1", "n2"],
            node_attrs=["content"],
        )
    """

    def __init__(
    self,
    model_name: str,
    api_key: str,
    api_base: str = None,
    prompt_tpl: str = (
        "Reconstruct the clinical case report from this data:\n\n{payload}\n\n"
        "Write a coherent narrative including patient demographics, "
        "timeline of diagnoses, treatments, and outcomes."
    ),
    max_retries: int = 3,):
        try:
            if api_base:
                self.lm = dspy.LM(model_name, api_base=api_base, api_key=api_key)
            else:
                self.lm = dspy.LM(model_name, api_key=api_key)
            self.prompt_tpl = prompt_tpl
            self.max_retries = max_retries
        except Exception as e:
            logger.error("Error initializing LLM: %s", e)
            raise


    def _build_payload(
        self,
        graph: Graph,
        include_nodes: bool,
        include_edges: bool,
        node_ids: Optional[list[str]],
        node_attrs: Optional[list[str]],
        edge_attrs: Optional[list[str]],
    ) -> dict[str, Any]:
        """Build a structured payload from the graph."""
        payload: dict[str, Any] = {}

        if include_nodes:
            payload["nodes"] = []
            for nid, attrs in graph.nodes(data=True):
                if node_ids and nid not in node_ids:
                    continue
                entry = {"id": nid}
                for k in node_attrs or list(attrs.keys()):
                    if k in attrs:  # Only include existing attributes
                        entry[k] = attrs[k]
                payload["nodes"].append(entry)

        if include_edges:
            payload["edges"] = []
            for src, tgt, attrs in graph.edges(data=True):
                # Skip edges if we're filtering nodes and either endpoint is filtered out
                if node_ids and (src not in node_ids or tgt not in node_ids):
                    continue
                entry = {"source": src, "target": tgt}
                for k in edge_attrs or list(attrs.keys()):
                    if k in attrs:  # Only include existing attributes
                        entry[k] = attrs[k]
                payload["edges"].append(entry)

        return payload

    def reconstruct(
        self,
        graph: Graph,
        *,
        include_nodes: bool = True,
        include_edges: bool = True,
        node_ids: Optional[list[str]] = None,
        node_attrs: Optional[list[str]] = None,
        edge_attrs: Optional[list[str]] = None,
    ) -> str:
        """
        Build a custom payload from the graph and call the LLM.

        Args:
          graph: networkx.DiGraph with node/edge attributes.
          include_nodes: include a list of nodes in the payload.
          include_edges: include a list of edges in the payload.
          node_ids: list of node IDs to include (default: all).
          node_attrs: list of node attribute names to include (default: all).
          edge_attrs: list of edge attribute names to include (default: all).

        Returns:
          A string containing the reconstructed clinical narrative.
        """
        if not graph:
            logger.warning("Empty graph provided")
            return "No data available to reconstruct narrative."

        # Verify graph is a DiGraph
        if not isinstance(graph, nx.DiGraph):
            logger.warning("Expected DiGraph, got %s", type(graph))
            if isinstance(graph, nx.Graph):
                logger.info("Converting undirected graph to directed")
                graph = nx.DiGraph(graph)
            else:
                raise TypeError("Input must be a networkx Graph or DiGraph")

        payload = self._build_payload(
            graph, include_nodes, include_edges, node_ids, node_attrs, edge_attrs
        )

        if not payload.get("nodes") and not payload.get("edges"):
            logger.warning("No nodes or edges in payload")
            return "Insufficient data to reconstruct narrative."

        payload_json = json.dumps(payload, indent=2)
        prompt = self.prompt_tpl.format(payload=payload_json)

        # Retry mechanism
        for attempt in range(self.max_retries):
            try:
                resp_list = self.lm(messages=[{"role": "user", "content": prompt}])
                # dspy returns a list type of responses;
                # by default that list contains exactly one completion,
                # so resp_list[0] is the single response you want
                return resp_list[0].strip()
            except Exception as e:
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                if attempt == self.max_retries - 1:
                    logger.error("All LLM call attempts failed")
                    raise

        # This should never be reached due to the exception above, but added for completeness
        return "Failed to reconstruct narrative due to LLM service errors."
    