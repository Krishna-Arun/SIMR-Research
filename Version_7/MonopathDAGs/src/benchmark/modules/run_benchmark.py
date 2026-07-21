# pylint: disable=broad-exception-caught

# This source file is part of the Daneshjou Lab projects
#
# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see AUTHORS.md)
#
# SPDX-License-Identifier: MIT
#

# pylint: disable=too-many-branches, too-many-statements

"""This modules runs the benchmark pipeline for a single patient graph."""

import json
from typing import Any
import networkx as nx
from networkx.readwrite import json_graph

# Local application imports
from .reconstruction import LLMReconstructor
from .evaluation import BERTScoreEvaluator, StringSimilarityEvaluator, TopologyValidator
from .embedding import TrajectoryEmbedder
from .regex_utils import RegexValidator
from .config import (
    LM_MODEL,
    LM_API_BASE,
    LM_API_KEY,
    TRAJECTORY_EMBEDDING_MODEL,
    Graph,
)
from .logging_utils import setup_logger

logger = setup_logger(__name__)


def run_pipeline(
    graph: Graph, original_text: str, config: dict[str, Any]
) -> dict[str, Any]:
    """
    Benchmark pipeline for a single patient graph.

    Evaluates:
      1. LLM-based narrative reconstruction
      2. BERTScore (fidelity)
      3. BLEU/ROUGE string similarity
      4. Graph topology validation
      5. Optional regex check
      6. Trajectory-level embedding

    Returns:
        dict: Structured results with intermediate metrics.
    """
    
    results = {"status": "success", "errors": []}

    # Validate input types
    if not isinstance(graph, (nx.Graph, nx.DiGraph)):
        msg = f"Invalid graph type: {type(graph)}"
        logger.error(msg)
        return {"status": "error", "errors": [msg]}

    if not isinstance(original_text, str):
        msg = "original_text must be a string"
        logger.error(msg)
        return {"status": "error", "errors": [msg]}

    # LLM Narrative Reconstruction
    narrative = None
    if "reconstruct_params" in config:
        try:
            logger.info("Starting narrative reconstruction")
            reconstructor = LLMReconstructor(
                model_name=LM_MODEL, api_base=LM_API_BASE, api_key=LM_API_KEY
            )
            narrative = reconstructor.reconstruct(graph, **config["reconstruct_params"])
            results["reconstructed_narrative"] = narrative
            logger.info("Narrative reconstruction completed")
        except Exception as e:
            msg = f"Narrative reconstruction failed: {str(e)}"
            logger.error(msg)
            results["status"] = "partial"
            results["errors"].append(msg)

    # print("========= ORIGINAL TEXT =========:", original_text[:100])
    # print("========= NARRATIVE: =========", narrative[:100])

    # Fidelity Evaluation using BERTScore
    if config.get("bertscore") and narrative:
        try:
            logger.info("Starting BERTScore evaluation")
            evaluator = BERTScoreEvaluator(model_type=TRAJECTORY_EMBEDDING_MODEL)
            results["bertscore"] = evaluator.evaluate(
                refs=[original_text], cands=[narrative]
            )
            print(results["bertscore"])
            logger.info("BERTScore evaluation completed")

        except Exception as e:
            msg = f"BERTScore evaluation failed: {str(e)}"
            logger.error(msg)
            results["status"] = "partial"
            results["errors"].append(msg)


    # String Similarity (BLEU / ROUGE)
    if config.get("string_similarity") and narrative and original_text:
        try:
            logger.info("Starting BLEU/ROUGE string similarity evaluation")

            string_evaluator = StringSimilarityEvaluator()
            similarity_scores = string_evaluator.evaluate(
                refs=[original_text], cands=[narrative]
            )

            # Store individual metrics in separate result fields
            results["bleu"] = similarity_scores.get("bleu", 0.0)
            results["rouge1"] = similarity_scores.get("rouge1", 0.0)
            results["rougeL"] = similarity_scores.get("rougeL", 0.0)

            logger.info(f"String similarity evaluation completed: BLEU={results['bleu']:.4f}, "
                        f"ROUGE-1={results['rouge1']:.4f}, ROUGE-L={results['rougeL']:.4f}")
        except Exception as e:
            msg = f"String similarity evaluation failed: {str(e)}"
            logger.error(msg)
            results["status"] = "partial"
            results.setdefault("errors", []).append(msg)


    # Graph Topology Validation
    if config.get("topology"):
        try:
            logger.info("Starting topology validation")
            results["topology"] = TopologyValidator(graph).run()
            logger.info("Topology validation completed")
        except Exception as e:
            msg = f"Topology validation failed: {str(e)}"
            logger.error(msg)
            results["status"] = "partial"
            results["errors"].append(msg)

    # Optional Regex Validation
    if config.get("regex"):
        try:
            logger.info("Starting regex validation")
            json_str = json.dumps(json_graph.node_link_data(graph))
            results["regex"] = RegexValidator(json_str).run()
            logger.info("Regex validation completed")
        except Exception as e:
            msg = f"Regex validation failed: {str(e)}"
            logger.error(msg)
            results["status"] = "partial"
            results["errors"].append(msg)

    # Trajectory Embedding
    if config.get("trajectory_embedding"):
        try:
            logger.info("Starting trajectory embedding")
            embedder = TrajectoryEmbedder()
            emb = embedder.embed_graph(graph)
            results["trajectory_embedding"] = emb.tolist() if emb is not None else None
            logger.info("Trajectory embedding completed")
        except Exception as e:
            msg = f"Embedding failed: {str(e)}"
            logger.error(msg)
            results["status"] = "partial"
            results["errors"].append(msg)

    if results["errors"]:
        if results["status"] == "success":
            results["status"] = "partial"
    else:
        results.pop("errors", None)

    return results
