# This source file is part of the Daneshjou Lab projects
#
# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see AUTHORS.md)
#
# SPDX-License-Identifier: MIT
#

# pylint: disable=too-few-public-methods

"""This module contains evaluation classes for BERTScore and graph topology validation."""
from typing import Any, Optional
from transformers import AutoTokenizer, AutoModel
import networkx as nx
from bert_score import score as bert_score_fn
from nltk.tokenize import RegexpTokenizer
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from rouge_score import rouge_scorer
import numpy as np


# Local application imports
from .config import Graph
from .logging_utils import setup_logger

logger = setup_logger(__name__)

MAX_BERT_TOKENS = 512

class BERTScoreEvaluator:
    """
    Computes BERTScore (precision, recall, F1) using a custom model (e.g., Bio_ClinicalBERT),
    truncating inputs longer than the model's max input length (512 tokens).
    """

    def __init__(self, model_type: str, device: Optional[str] = None):
        self.model_type = model_type
        self.device = device or "cpu"

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_type)
            AutoModel.from_pretrained(self.model_type)  # ensure model download
            logger.info(f"Model {self.model_type} loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not preload model: {self.model_type} — {e}")

    def truncate(self, text: str, max_tokens: int = MAX_BERT_TOKENS) -> str:
        """
        Truncates a text to the first `max_tokens` tokens using the model's tokenizer.
        """
        tokens = self.tokenizer.tokenize(text)
        truncated_tokens = tokens[:max_tokens - 2]  # Reserve 2 tokens for [CLS] and [SEP]
        return self.tokenizer.convert_tokens_to_string(truncated_tokens)

    def evaluate(self, refs: list[str], cands: list[str]) -> dict[str, float]:
        """
        Computes BERTScore (mean) between reference and candidate texts.

        Args:
            refs (list of str): Reference texts.
            cands (list of str): Candidate/generated texts.

        Returns:
            dict[str, float]: Average precision, recall, and F1 scores.
        """
        if not refs or not cands:
            logger.warning("Empty references or candidates list.")
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

        if len(refs) != len(cands):
            logger.warning(f"Mismatched list lengths: refs={len(refs)}, cands={len(cands)}")
            min_len = min(len(refs), len(cands))
            refs = refs[:min_len]
            cands = cands[:min_len]

        # Truncate long sequences to avoid tensor mismatch
        refs = [self.truncate(r) for r in refs]
        cands = [self.truncate(c) for c in cands]

        try:
            model_kwargs = {
                "model_type": self.model_type,
                "device": self.device,
                "lang": "en",
                "rescale_with_baseline": False,
                "verbose": False,
                "num_layers": 12  # Required for Bio_ClinicalBERT
            }

            precision, recall, f1 = bert_score_fn(cands, refs, **model_kwargs)

            return {
                "precision": float(precision.mean().item()),
                "recall": float(recall.mean().item()),
                "f1": float(f1.mean().item()),
            }

        except Exception as e:
            logger.error(f"BERTScore evaluation failed: {e}")
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0}


class TopologyValidator:
    """
    Validates DAG properties: acyclicity, timestamp order, connectivity stats.

    Usage:
        validator = TopologyValidator(graph)
        stats = validator.run()
        # stats -> {"is_acyclic": bool, "timestamps_in_order": bool, ...}
    """

    def __init__(self, graph: Graph):
        self.graph_s = graph

    def run(self) -> dict[str, Any]:
        """
        Returns:
          A dict with structural validation results.
        """
        if not self.graph_s or self.graph_s.number_of_nodes() == 0:
            logger.warning("Empty graph in topology validator")
            return {
                "is_acyclic": True,  # Empty graphs are technically acyclic
                "timestamps_in_order": True,
                "weakly_connected_components": 0,
                "avg_in_degree": 0.0,
                "node_count": 0,
                "edge_count": 0,
                "density": 0.0,
            }

        is_acyclic = nx.is_directed_acyclic_graph(self.graph_s)

        # Check if timestamps exist in all nodes
        timestamp_attr = "timestamp"
        all_have_timestamps = all(
            timestamp_attr in data for _, data in self.graph_s.nodes(data=True)
        )

        timestamps_ok = False
        if all_have_timestamps:
            try:
                topo_nodes = list(nx.topological_sort(self.graph_s))
                timestamps = [self.graph_s.nodes[n][timestamp_attr] for n in topo_nodes]
                timestamps_ok = timestamps == sorted(timestamps)
            except nx.NetworkXUnfeasible:
                # Graph has cycles, can't do topological sort
                logger.warning("Cannot check timestamp order: graph has cycles")
                timestamps_ok = False
        else:
            logger.warning("Not all nodes have timestamp attributes")

        components = nx.number_weakly_connected_components(self.graph_s)
        node_count = self.graph_s.number_of_nodes()
        edge_count = self.graph_s.number_of_edges()

        avg_in_deg = sum(dict(self.graph_s.in_degree()).values()) / max(1, node_count)
        density = nx.density(self.graph_s)

        return {
            "is_acyclic": is_acyclic,
            "timestamps_in_order": timestamps_ok,
            "all_nodes_have_timestamps": all_have_timestamps,
            "weakly_connected_components": components,
            "node_count": node_count,
            "edge_count": edge_count,
            "avg_in_degree": avg_in_deg,
            "density": density,
        }


class StringSimilarityEvaluator:
    def __init__(self):
        self.smoothie = SmoothingFunction().method4
        self.rouge = rouge_scorer.RougeScorer(['rouge1', 'rougeL'], use_stemmer=True)
        self.tokenizer = RegexpTokenizer(r'\w+')

    def evaluate(self, refs, cands):
        if not refs or not cands or len(refs) != len(cands):
            raise ValueError("References and candidates must be non-empty lists of equal length.")

        bleu_scores = []
        rouge1_scores = []
        rougeL_scores = []

        for ref, cand in zip(refs, cands):
            ref_tokens = self.tokenizer.tokenize(ref.lower().strip())
            cand_tokens = self.tokenizer.tokenize(cand.lower().strip())

            if not ref_tokens or not cand_tokens:
                bleu_scores.append(0.0)
                rouge1_scores.append(0.0)
                rougeL_scores.append(0.0)
                continue

            bleu = sentence_bleu([ref_tokens], cand_tokens, smoothing_function=self.smoothie)
            scores = self.rouge.score(ref, cand)

            bleu_scores.append(bleu)
            rouge1_scores.append(scores['rouge1'].fmeasure)
            rougeL_scores.append(scores['rougeL'].fmeasure)

            print(f"BLEU: {bleu}, ROUGE-1: {scores['rouge1'].fmeasure}, ROUGE-L: {scores['rougeL'].fmeasure}")

        return {
            "bleu": float(np.mean(bleu_scores)),
            "rouge1": float(np.mean(rouge1_scores)),
            "rougeL": float(np.mean(rougeL_scores))
        }