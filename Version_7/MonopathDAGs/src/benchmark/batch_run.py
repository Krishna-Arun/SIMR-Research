# This source file is part of the Daneshjou Lab projects
#
# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see AUTHORS.md)
#
# SPDX-License-Identifier: MIT
#

"""
Run the full benchmarking pipeline on a batch of graph files in JSON format.
Each graph is benchmarked for information fidelity, topology structure,
and trajectory representation.
"""

from pathlib import Path

# Local application imports
from modules.run_benchmark import run_pipeline
from modules.logging_utils import setup_logger
from modules.io_utils import (
    load_graph_from_file,
    save_results,
    build_graph_to_text_mapping,
    extract_case_presentation_from_file,
)

logger = setup_logger(__name__)


# Input directory: All graph files
GRAPH_INPUT_DIR = Path(__file__).resolve().parents[2] / "webapp/static/graphs/"

# Output directory: Results
RESULTS_OUTPUT_DIR = Path("output/results/")
RESULTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
METRIC_SUMMARY_OUTPUT_DIR = Path("output/results/plots/metric_summary.csv")


# Paths
METADATA_CSV_PATH = Path(__file__).resolve().parents[2] / "webapp/static/graphs/mapping/graph_metadata.csv"
HTML_ROOT_DIR = Path(__file__).resolve().parents[2] / "webapp/static/pmc_htmls"

graph_to_html = build_graph_to_text_mapping(METADATA_CSV_PATH, HTML_ROOT_DIR)

if __name__ == "__main__":
    graph_files = list(GRAPH_INPUT_DIR.glob("*.json"))

    if not graph_files:
        logger.warning("No JSON files found in input directory.")
    else:
        for fpath in graph_files:
            graph_id = fpath.stem
            html_path = graph_to_html.get(graph_id)

            if not html_path:
                logger.warning("No HTML path found for %s", graph_id)
                continue

            reference_case_text = extract_case_presentation_from_file(str(html_path))

            logger.info("Running pipeline on: %s",fpath.name)

            graph, ok = load_graph_from_file(fpath)
            if not ok:
                logger.error("Skipping %s due to load error.", fpath.name)
                continue

            cfg = {
                "reconstruct_params": {"include_nodes": True, "include_edges": True},
                "bertscore": True,
                "string_similarity": True,
                "topology": True,
                "trajectory_embedding": True,
            }

            print(f"Looking for file at: {html_path}")
            results = run_pipeline(graph, reference_case_text, cfg)

            output_path = RESULTS_OUTPUT_DIR / f"results_{graph_id}.json"
            save_results(results, output_path)
        
        
        logger.info("Batch benchmarking completed.")
