# This source file is part of the Daneshjou Lab projects
#
# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see AUTHORS.md)
#
# SPDX-License-Identifier: MIT
#

""" This module provides functions to visualize and summarize the results of the benchmarking
pipeline. It includes functions to plot BERTScore F1 scores, t-SNE embeddings, and topology
distributions, as well as to create a summary table of key metrics."""

import os
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from sklearn.manifold import TSNE
import evaluate

FONT_SIZE = 24
PLOTS_DIR = "output/plots"
os.makedirs(PLOTS_DIR, exist_ok=True)


def plot_bertscore_f1(graph_ids, bertscore_f1, export_path=None):
    """
    Histogram of BERTScore F1 values across all graphs.
    Includes visual annotations for mean, median, and interquartile range (IQR).
    Saves summary statistics to CSV if export_path is provided.
    """
    f1_array = np.array(bertscore_f1)
    
    # Calculate summary statistics
    mean_f1 = np.mean(f1_array)
    median_f1 = np.median(f1_array)
    std_f1 = np.std(f1_array)
    q1 = np.percentile(f1_array, 25)
    q3 = np.percentile(f1_array, 75)

    stats = {
        "Mean": mean_f1,
        "Median": median_f1,
        "Standard Deviation": std_f1,
        "25th Percentile (Q1)": q1,
        "75th Percentile (Q3)": q3,
    }

    # Print stats to console
    for k, v in stats.items():
        print(f"{k}: {v:.3f}")

    # Save statistics to CSV if requested
    if export_path is not None:
        pd.DataFrame([stats]).to_csv(export_path, index=False)

    # Plot histogram
    plt.figure(figsize=(8, 6))
    sns.histplot(f1_array, bins=20, kde=True, color="steelblue", edgecolor="black")

    # Plot annotations
    plt.axvline(mean_f1, color="red", linestyle="--", linewidth=2, label=f"Mean = {mean_f1:.2f}")
    plt.axvline(median_f1, color="green", linestyle=":", linewidth=2, label=f"Median = {median_f1:.2f}")
    plt.axvspan(q1, q3, color="orange", alpha=0.2, label=f"IQR = [{q1:.2f}, {q3:.2f}]")

    # Style and labels
    # plt.title("Distribution of BERTScore F1 Scores", fontsize=FONT_SIZE)
    plt.xlabel("F1 Score", fontsize=FONT_SIZE)
    plt.ylabel("Frequency", fontsize=FONT_SIZE)
    plt.xticks(fontsize=FONT_SIZE - 2)
    plt.yticks(fontsize=FONT_SIZE - 2)
    plt.xlim(0, 1)
    plt.legend(fontsize=FONT_SIZE - 3)
    plt.tight_layout()

    # Save to file
    plt.savefig(os.path.join(PLOTS_DIR, "bertscore_f1_histogram.png"), dpi=300)
    plt.close()


def plot_tsne_embeddings(embeddings, graph_ids):
    """2D t-SNE scatterplot for graph embeddings."""
    tsne_results = TSNE(n_components=2, perplexity=2, random_state=42).fit_transform(
        embeddings
    )
    _, ax = plt.subplots()
    sns.scatterplot(
        x=tsne_results[:, 0], y=tsne_results[:, 1], hue=graph_ids, s=100, ax=ax
    )
    # ax.set_title("t-SNE of Trajectory Embeddings")
    ax.set_xlabel("Dimension 1")
    ax.set_ylabel("Dimension 2")
    plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.savefig(os.path.join(PLOTS_DIR, "trajectory_tsne.png"))
    plt.close()


def plot_topology_distributions(node_counts, edge_counts):
    """Histograms for node and edge counts across graphs."""
    _, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    sns.histplot(node_counts, bins=5, ax=ax1, kde=True)
    # ax1.set_title("Node Count Distribution", fontsize=FONT_SIZE)
    ax1.set_xlabel("Number of Nodes", fontsize=FONT_SIZE-2)
    ax1.set_ylabel("Frequency", fontsize=FONT_SIZE-2)
    ax1.tick_params(axis='both', labelsize=FONT_SIZE-2)

    sns.histplot(edge_counts, bins=5, ax=ax2, kde=True)
    # ax2.set_title("Edge Count Distribution", fontsize=FONT_SIZE)
    ax2.set_xlabel("Number of Edges", fontsize=FONT_SIZE-2)
    ax2.set_ylabel("Frequency", fontsize=FONT_SIZE-2)
    ax2.tick_params(axis='both', labelsize=FONT_SIZE-2)
    
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, "topology_distributions.png"))
    plt.close()


def compute_string_similarity(
    reference_texts, candidate_texts, metrics=["rouge", "bleu"]
):
    """Compute string similarity metrics (ROUGE, BLEU) between reference and candidate texts.

    Args:
        reference_texts (list of str): Ground truth strings.
        candidate_texts (list of str): Generated strings.
        metrics (list of str): Metrics to compute (default: ["rouge", "bleu"]).

    Returns:
        dict: Dictionary of metric names and scores.
    """
    results = {}
    if "rouge" in metrics:
        rouge = evaluate.load("rouge")
        rouge_result = rouge.compute(
            predictions=candidate_texts, references=reference_texts
        )
        results.update({f"ROUGE-{k.upper()}": v for k, v in rouge_result.items()})

    if "bleu" in metrics:
        bleu = evaluate.load("bleu")
        bleu_result = bleu.compute(
            predictions=candidate_texts, references=reference_texts
        )
        results["BLEU"] = bleu_result["bleu"]

    return results


def summarize_metrics_table(graph_ids, bertscore_f1, bertscore_precision,
    bertscore_recall, bleu, rouge1, rougeL, node_counts, edge_counts, output_csv_path):
    """Create and return a summary DataFrame of key metrics per graph, and save it as a CSV."""
    df = pd.DataFrame(
        {
            "Graph ID": graph_ids,
            "BERTScore F1": bertscore_f1,
            "BERTScore Precision": bertscore_precision,
            "BERTScore Recall": bertscore_recall,
            "BLEU": bleu,
            "ROUGE-1": rouge1,
            "ROUGE-L": rougeL,
            "Nodes": node_counts,
            "Edges": edge_counts,
        }
    )
    df.to_csv(output_csv_path, index=False)
    return df
