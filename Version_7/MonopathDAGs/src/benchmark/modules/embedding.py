# This source file is part of the Daneshjou Lab projects
#
# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see AUTHORS.md)
#
# SPDX-License-Identifier: MIT
#

"""This module contains the TrajectoryEmbedder class for embedding patient trajectories."""

# Standard library imports
from typing import Optional

# Third-party library imports
import torch
from transformers import AutoTokenizer, AutoModel
import networkx as nx

# Local application imports
from .logging_utils import setup_logger
from .config import TRAJECTORY_EMBEDDING_MODEL

logger = setup_logger(__name__)


class TrajectoryEmbedder:
    """
    Embeds a patient trajectory graph by pooling embeddings of textual node content.
    Uses a transformer model (e.g., Bio_ClinicalBERT) and extracts node-level text
    based on a configurable path (e.g., ["data", "commentary"]).

    Attributes:
        model_name (str): Hugging Face model ID used for embedding.
        text_path (list[str]): Path to the text field in node
            attributes (e.g., ["data", "commentary"]).
        device (str): Computation device ('cuda' or 'cpu').
    """

    def __init__(self, model=TRAJECTORY_EMBEDDING_MODEL, text_field_path="content", device=None):
        """
        Initializes the TrajectoryEmbedder with a specified model and text path.
        Args:
            model_name (str): Hugging Face model ID used for embedding.
            text_path (list[str]): Path to the text field in node
                attributes (e.g., ["data", "commentary"]).
            device (str): Computation device ('cuda' or 'cpu').
        """
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.text_field = text_field_path
        logger.info(f"Loading embedding model: {model} on {self.device}")
        self.tokenizer = AutoTokenizer.from_pretrained(model)
        self.model = AutoModel.from_pretrained(model).to(self.device)
        self.model.eval()

    def _get_nested_text(self, data: dict) -> Optional[str]:
        """Extracts text from a nested dictionary based on the specified path.
        Args:
            data (dict): Node attributes.
        Returns:
            Optional[str]: Extracted text or None if not found.
        """
        try:
            keys = self.text_field.split(".")
            for k in keys:
                data = data[k]
            return data if isinstance(data, str) else None
        except Exception:
            return None
        
    def embed_text(self, text: str) -> torch.Tensor:
        """"Embeds a single text string using the transformer model.
        Args:
            text (str): Text to be embedded.
        Returns:
            torch.Tensor: The embedding of the text.
        """
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=512
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
        return outputs.last_hidden_state[0][0]

    def extract_text(self, data: dict) -> Optional[str]:
        """Extracts text from the node attributes based on the specified path.
        Args:
            data (dict): Node attributes.
        Returns:
            Optional[str]: Extracted text or None if not found.
        """
        try:
            for key in self.text_path:
                data = data[key]
            return data if isinstance(data, str) else None
        except (KeyError, TypeError):
            return None

    def embed_graph(self, graph: nx.DiGraph) -> Optional[torch.Tensor]:
        """Embeds a graph by pooling the embeddings of its nodes.
        Args:
            graph (nx.DiGraph): The graph to be embedded.
        Returns:
            Optional[torch.Tensor]: The pooled embedding of the graph.
        """
        texts = [
            self._get_nested_text(data)
            for _, data in graph.nodes(data=True)
            if self._get_nested_text(data)
        ]
        if not texts:
            logger.warning("No valid node texts found for embedding.")
            return None
        node_embs = torch.stack([self.embed_text(t) for t in texts])
        return node_embs.mean(dim=0).cpu()