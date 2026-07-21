# This source file is part of the Daneshjou Lab projects
#
# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see AUTHORS.md)
#
# SPDX-License-Identifier: MIT
#

"""This module generates visualizations for the results of the benchmark pipeline."""

import os
import json
import numpy as np
import pandas as pd

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))  # Adds 'src' to sys.path


from benchmark.modules.visualization_utils import (
    plot_bertscore_f1,
    plot_tsne_embeddings,
    plot_topology_distributions,
    summarize_metrics_table
)

RESULTS_DIR = "output/results/"
PLOTS_DIR = "output/plots"
os.makedirs(PLOTS_DIR, exist_ok=True)

# Lists to collect metrics
graph_ids = []
bertscore_f1s = []
bertscore_precisions = []
bertscore_recalls = []
bleu_scores = []
rouge1_scores = []
rougeL_scores = []
trajectory_embeddings = []
node_counts = []
edge_counts = []

# To store skipped graphs
skipped_graphs = []

# Iterate over each result file
for fname in os.listdir(RESULTS_DIR):
    if fname.endswith(".json"):
        graph_id = fname.replace(".json", "")
        with open(os.path.join(RESULTS_DIR, fname), "r", encoding="utf-8") as f:
            result = json.load(f)

        

        # Get BERTScore F1
        bertscore = result.get("bertscore", {})

        f1 = bertscore.get("f1", np.nan)
        precision = bertscore.get("precision", np.nan)
        recall = bertscore.get("recall", np.nan)

        # Skip graphs with any zero BERTScore value
        if (f1 == 0.0 or precision == 0.0 or recall == 0.0):
            skipped_graphs.append(graph_id)
            continue
            
        graph_ids.append(graph_id)
        bertscore_f1s.append(f1)
        bertscore_precisions.append(precision)
        bertscore_recalls.append(recall)


        # Get BLEU
        bleu = result.get("bleu", np.nan)
        bleu_scores.append(bleu)

        # Get ROUGE
        rouge1 = result.get("rouge1", np.nan)
        rougel = result.get("rougeL", np.nan)
        rouge1_scores.append(rouge1)
        rougeL_scores.append(rougel)

        # Get embedding
        emb = result.get("trajectory_embedding")
        if emb:
            trajectory_embeddings.append(emb)
        else:
            # To keep everything aligned, we must remove the last added entries
            graph_ids.pop()
            bertscore_f1s.pop()
            bertscore_precisions.pop()
            bertscore_recalls.pop()
            bleu_scores.pop()
            rouge1_scores.pop()
            rougeL_scores.pop()
            node_counts.pop()
            edge_counts.pop()

        # Get topology stats
        topo = result.get("topology", {})
        node_counts.append(topo.get("node_count", 0))
        edge_counts.append(topo.get("edge_count", 0))

# Save skipped graph IDs to Excel
if skipped_graphs:
    skipped_df = pd.DataFrame({"skipped_graph_id": skipped_graphs})
    skipped_df.to_csv(os.path.join(PLOTS_DIR, "skipped_due_to_bertscore_zero.csv"), index=False)


# Convert embedding list to numpy array if not empty
if trajectory_embeddings:
    trajectory_embeddings = np.array(trajectory_embeddings)

# Generate Visualizations
plot_bertscore_f1(graph_ids, bertscore_f1s)

# if len(trajectory_embeddings) > 1:
#     plot_tsne_embeddings(trajectory_embeddings, graph_ids)

plot_topology_distributions(node_counts, edge_counts)

# Create and save summary table
summary_df = summarize_metrics_table(
    graph_ids,
    bertscore_f1s,
    bertscore_precisions,
    bertscore_recalls,
    bleu_scores,
    rouge1_scores,
    rougeL_scores,
    node_counts,
    edge_counts,
    output_csv_path=os.path.join(PLOTS_DIR, "metrics_summary.csv")
)
print("\n=== Summary Table ===")
print(summary_df)
if skipped_graphs:
    print(f"\nSkipped {len(skipped_graphs)} graphs due to zero BERTScore values.")