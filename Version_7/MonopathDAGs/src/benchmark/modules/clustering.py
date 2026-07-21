# This source file is part of the Daneshjou Lab projects
#
# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see AUTHORS.md)
#
# SPDX-License-Identifier: MIT
#

"""This modules compares the clustering of graph embeddings and text embeddings.
It loads the graph and text embeddings, reduces their dimensions using PCA or UMAP,
clusters them using KMeans, and evaluates the clustering performance using various metrics.
It also visualizes the clusters using t-SNE and generates a summary of the clusters with metadata.
"""

# Standard library imports
import os
import json
import numpy as np
import pandas as pd
import sys
from pathlib import Path

# Add src/ to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

# Third-party library imports
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
from sklearn.metrics import adjusted_rand_score
from sklearn.manifold import TSNE
import matplotlib.pyplot as plt
import seaborn as sns
import umap
from sklearn.metrics import adjusted_rand_score
from collections import Counter

# Local application imports
from modules.embedding import TrajectoryEmbedder

FONT_SIZE = 22

RESULTS_DIR = Path("output/results")
METADATA_CSV = RESULTS_DIR / "graph_html_metadata_final.csv"
PLOTS_DIR = Path("output/plots")
PLOTS_DIR.mkdir(parents=True, exist_ok=True)


def load_graph_embeddings():
    graph_embeddings = {}
    for file in RESULTS_DIR.glob("results_graph_*.json"):
        graph_id = file.stem.replace("results_graph_", "")
        with open(file) as f:
            data = json.load(f)
            if "trajectory_embedding" in data:
                graph_embeddings[graph_id] = data["trajectory_embedding"]
    return graph_embeddings


def load_text_embeddings(embedder, metadata_csv, results_dir="output/results"):
    """
    Loads text embeddings using reconstructed narratives from results JSON files.

    Args:
        embedder: An object with an `embed_text(text)` method.
        metadata_csv (str): Path to the metadata CSV file.
        results_dir (str): Directory where results_graph_XXX.json files are located.

    Returns:
        dict: A dictionary mapping graph_id (e.g., "001") to its embedding.
    """
    df = pd.read_csv(metadata_csv, encoding='ISO-8859-1')
    text_embeddings = {}

    for _, row in df.iterrows():
        graph_id_full = row["graph_id"]  # e.g., graph_001
        graph_id = graph_id_full.replace("graph_", "")
        json_path = os.path.join(results_dir, f"results_graph_{graph_id}.json")

        if not os.path.exists(json_path):
            print(f"Missing file: {json_path}")
            continue

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            text = data.get("reconstructed_narrative", "").strip()
            if not text:
                print(f"No reconstructed narrative for graph {graph_id}")
                continue

            emb = embedder.embed_text(text).cpu().numpy()
            text_embeddings[graph_id] = emb

        except Exception as e:
            print(f"Failed to process graph {graph_id}: {e}")

    return text_embeddings

def load_metadata_features(shared_ids):
    df = pd.read_csv(METADATA_CSV, encoding='ISO-8859-1')
    df = df[df["graph_id"].str.startswith("graph_")]
    df["graph_id"] = df["graph_id"].str.replace("graph_", "")
    df = df[df["graph_id"].isin(shared_ids)].set_index("graph_id")

    # Flatten list-like strings to strings for encoding
    def flatten_list_column(col):
        return col.apply(lambda x: "|".join(eval(x)) if pd.notna(x) and x.startswith("[") else "unknown")

    df["cancers"] = flatten_list_column(df["cancers"])
    df["specific_cancers"] = flatten_list_column(df["specific_cancers"])
    df["has_metastasis"] = df["has_metastasis"].fillna("unknown").astype(str)

    from sklearn.preprocessing import OneHotEncoder
    encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    encoded = encoder.fit_transform(df[["cancers", "specific_cancers", "has_metastasis"]])
    return encoded


def reduce_dimensions(data, method="pca", n_components=10):
    if method == "pca":
        reducer = PCA(n_components=n_components)
    elif method == "umap":
        reducer = umap.UMAP(n_components=n_components, random_state=42)
    else:
        raise ValueError("Unsupported reduction method: choose 'pca' or 'umap'")
    return reducer.fit_transform(data)


def cluster_and_evaluate(embedding_matrix, method_label):
    best_k = None
    best_score = -1
    best_labels = None
    best_scores = {}
    n_samples = embedding_matrix.shape[0]
    for k in range(2, min(11, n_samples)):
        kmeans = KMeans(n_clusters=k, random_state=4)
        labels = kmeans.fit_predict(embedding_matrix)
        sil = silhouette_score(embedding_matrix, labels)
        ch = calinski_harabasz_score(embedding_matrix, labels)
        db = davies_bouldin_score(embedding_matrix, labels)
        best_scores[k] = (sil, ch, db)
        if sil > best_score:
            best_score = sil
            best_k = k
            best_labels = labels
    print(f"[{method_label}] Best k={best_k}, Silhouette={best_score:.4f}")
    return best_k, best_labels, best_scores

def plot_tsne_cancer_type(embeddings, labels, shared_ids, label_type="graph"):
    meta_df = pd.read_csv(METADATA_CSV)
    meta_df["graph_id"] = meta_df["graph_id"].str.replace("graph_", "")
    meta_df = meta_df[meta_df["graph_id"].isin(shared_ids)]

    tsne = TSNE(n_components=2, perplexity=min(5, len(shared_ids)-1), random_state=42)
    reduced = tsne.fit_transform(embeddings)

    cluster_df = pd.DataFrame({
        "graph_id": shared_ids,
        "x": reduced[:, 0],
        "y": reduced[:, 1],
        "cluster": labels
    })
    joined = cluster_df.merge(meta_df, on="graph_id")

    def extract_first_category(val):
        if pd.isna(val): return "unknown"
        try:
            items = eval(val) if val.startswith("[") else [val]
            return items[0] if items else "unknown"
        except:
            return "unknown"

    joined["cancer"] = joined["cancers"].apply(extract_first_category)
    cancer_palette = sns.color_palette("tab10", n_colors=joined["cancer"].nunique())
    cancer_colors = dict(zip(joined["cancer"].unique(), cancer_palette))

    plt.figure(figsize=(10, 8))
    for cancer, group in joined.groupby("cancer"):
        plt.scatter(group["x"], group["y"], label=cancer,
                    color=cancer_colors[cancer], alpha=0.75, edgecolor="k")

    plt.title(f"t-SNE of {label_type.capitalize()} Embeddings\nColored by Cancer Type")
    plt.xlabel("t-SNE-1")
    plt.ylabel("t-SNE-2")
    plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize="small")
    plt.tight_layout()
    out_path = PLOTS_DIR / f"tsne_{label_type}_cancer_type.png"
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"✅ Saved: {out_path}")


def plot_tsne_metastasis(embeddings, labels, shared_ids, label_type="graph"):
    meta_df = pd.read_csv(METADATA_CSV)
    meta_df["graph_id"] = meta_df["graph_id"].str.replace("graph_", "")
    meta_df = meta_df[meta_df["graph_id"].isin(shared_ids)]

    tsne = TSNE(n_components=2, perplexity=min(5, len(shared_ids)-1), random_state=42)
    reduced = tsne.fit_transform(embeddings)

    cluster_df = pd.DataFrame({
        "graph_id": shared_ids,
        "x": reduced[:, 0],
        "y": reduced[:, 1],
        "cluster": labels
    })
    joined = cluster_df.merge(meta_df, on="graph_id")

    joined["metastasis"] = joined["has_metastasis"].map({True: True, "TRUE": True, False: False, "FALSE": False})
    metastasis_palette = {True: "red", False: "blue"}

    plt.figure(figsize=(10, 8))
    for status, group in joined.groupby("metastasis"):
        label = "Met+" if status else "Met-"
        plt.scatter(group["x"], group["y"], label=label,
                    color=metastasis_palette[status], alpha=0.75, edgecolor="k")

    plt.title(f"t-SNE of {label_type.capitalize()} Embeddings\nColored by Metastasis Status")
    plt.xlabel("t-SNE-1")
    plt.ylabel("t-SNE-2")
    plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize="small")
    plt.tight_layout()
    out_path = PLOTS_DIR / f"tsne_{label_type}_metastasis.png"
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"✅ Saved: {out_path}")

def summarize_cluster_metadata(shared_ids, glabels, label_type="graph"):
    meta_df = pd.read_csv(METADATA_CSV, encoding='ISO-8859-1')
    meta_df["graph_id"] = meta_df["graph_id"].str.replace("graph_", "")
    meta_df = meta_df[meta_df["graph_id"].isin(shared_ids)]
    cluster_df = pd.DataFrame({
        "graph_id": shared_ids,
        "graph_cluster": glabels,
    })
    joined = cluster_df.merge(meta_df, on="graph_id")

    summary_rows = []
    for cluster_id, group in joined.groupby("graph_cluster"):
        print(f"Cluster {cluster_id} Summary:")
        metastasis_dist = group["has_metastasis"].value_counts(normalize=True).to_dict()
        cancers = Counter(" | ".join(group["cancers"].dropna().astype(str)).split(" | "))
        specific = Counter(" | ".join(group["specific_cancers"].dropna().astype(str)).split(" | "))
        top_cancers = ", ".join([f"{k} ({v})" for k, v in cancers.most_common(3)])
        top_specific = ", ".join([f"{k} ({v})" for k, v in specific.most_common(3)])

        print("  has_metastasis:", metastasis_dist)
        print("  Top cancers:", top_cancers)
        print("  Top specific cancers:", top_specific)

        summary_rows.append({
            "cluster": cluster_id,
            "has_metastasis": json.dumps(metastasis_dist),
            "top_cancers": top_cancers,
            "top_specific_cancers": top_specific,
        })

    summary_df = pd.DataFrame(summary_rows)
    summary_path = RESULTS_DIR / "cluster_metadata_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"✅ Cluster metadata summary saved to {summary_path}")

    # Optional: Barplot of has_metastasis composition
    expanded = []
    for _, row in summary_df.iterrows():
        for status, pct in json.loads(row["has_metastasis"]).items():
            expanded.append({
                "Cluster": f"{label_type}-{row['cluster']}",
                "Metastasis": status,
                "Proportion": pct
            })
    bar_df = pd.DataFrame(expanded)
    plt.figure(figsize=(6, 4))
    sns.barplot(data=bar_df, x="Cluster", y="Proportion", hue="Metastasis")
    # plt.title(f"{label_type.capitalize()} Clusters by Metastasis Status", fontsize=FONT_SIZE)
    plt.xlabel("Cluster", fontsize=FONT_SIZE)
    plt.ylabel("Proportion", fontsize=FONT_SIZE)
    plt.xticks(fontsize=FONT_SIZE-2)
    plt.yticks(fontsize=FONT_SIZE-2)
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / f"{label_type}_cluster_metastasis_barplot.png")
    plt.close()
    print(f"✅ Bar plot saved to {PLOTS_DIR / f'{label_type}_cluster_metastasis_barplot.png'}")

    # Optional: Heatmap of top cancer types
    cancer_counts = {}
    specific_counts = {}
    for cluster_id, group in joined.groupby("graph_cluster"):
        cancer_list = []
        specific_list = []
        for val in group["cancers"].dropna():
            try:
                items = eval(val) if isinstance(val, str) and val.startswith("[") else [val]
                cancer_list.extend([item.strip() for item in items if item.strip()])
            except:
                continue
        for val in group["specific_cancers"].dropna():
            try:
                items = eval(val) if isinstance(val, str) and val.startswith("[") else [val]
                specific_list.extend([item.strip() for item in items if item.strip()])
            except:
                continue
        for val in group["cancers"].dropna():
            try:
                items = eval(val) if isinstance(val, str) and val.startswith("[") else [val]
                cancer_list.extend([item.strip() for item in items if item.strip()])
            except Exception as e:
                continue
        counts = Counter(cancer_list)
        specific = Counter(specific_list)
        cancer_counts[cluster_id] = counts
        specific_counts[cluster_id] = specific

    all_cancers = sorted({cancer for counts in cancer_counts.values() for cancer in counts})
    heatmap_data = pd.DataFrame(index=sorted(cancer_counts.keys()), columns=all_cancers).fillna(0.0)
    for cluster_id, counts in cancer_counts.items():
        for cancer, count in counts.items():
            heatmap_data.at[cluster_id, cancer] = count / sum(counts.values())  # normalize to proportion

    plt.figure(figsize=(12, 6))
    sns.heatmap(heatmap_data, annot=True, fmt=".2f", cmap="YlGnBu")
    plt.title(f"Top Cancer Types per Cluster ({label_type})")
    plt.ylabel("Cluster")
    plt.xlabel("Cancer Type")
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / f"{label_type}_cancer_type_heatmap.png")
    plt.close()
    print(f"✅ Cancer type heatmap saved to {PLOTS_DIR / f'{label_type}_cancer_type_heatmap.png'}")

    # Specific cancer heatmap
    all_specifics = sorted({c for s in specific_counts.values() for c in s})
    specific_data = pd.DataFrame(index=sorted(specific_counts.keys()), columns=all_specifics).fillna(0.0)
    for cluster_id, counts in specific_counts.items():
        for name, count in counts.items():
            specific_data.at[cluster_id, name] = count / sum(counts.values())

    plt.figure(figsize=(12, 6))
    sns.heatmap(specific_data, annot=True, fmt=".2f", cmap="OrRd")
    plt.title(f"Top Specific Cancers per Cluster ({label_type})")
    plt.ylabel("Cluster")
    plt.xlabel("Specific Cancer Type")
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / f"{label_type}_specific_cancer_type_heatmap.png")
    plt.close()
    print(f"✅ Specific cancer heatmap saved to {PLOTS_DIR / f'{label_type}_specific_cancer_type_heatmap.png'}")


def plot_score_comparison(score_dicts, shared_ids, glabels, tlabels):
    summarize_cluster_metadata(shared_ids, glabels, label_type="graph")
    summarize_cluster_metadata(shared_ids, tlabels, label_type="text")

    # Cluster agreement
    ari_pca = adjusted_rand_score(glabels, tlabels)
    print(f"✅ Adjusted Rand Index (PCA-reduced Graph vs Text): {ari_pca:.4f}")

    # Cluster label CSV
    meta_df = pd.read_csv(METADATA_CSV)
    meta_df["graph_id"] = meta_df["graph_id"].str.replace("graph_", "")
    meta_df = meta_df[meta_df["graph_id"].isin(shared_ids)]
    cluster_df = pd.DataFrame({
        "graph_id": shared_ids,
        "graph_cluster": glabels,
        "text_cluster": tlabels,
    })
    output_df = cluster_df.merge(meta_df, on="graph_id")
    output_path = RESULTS_DIR / "cluster_labels_with_metadata.csv"
    output_df.to_csv(output_path, index=False)
    print(f"✅ Cluster labels with metadata saved to {output_path}")

    # Updated metrics (excluding Davies-Bouldin)
    metrics = ["Silhouette", "Calinski-Harabasz"]
    data = []
    for label, scores in score_dicts.items():
        for metric, value in zip(metrics, scores):  # Expecting only 2 values per label
            data.append({"Metric": metric, "Type": label, "Score": value})

    df = pd.DataFrame(data)
    plot_path = PLOTS_DIR / "clustering_score_comparison.png"
    csv_path = RESULTS_DIR / "clustering_score_comparison.csv"

    # Save the barplot
    plt.figure(figsize=(8, 5))
    sns.barplot(x="Metric", y="Score", hue="Type", data=df)
    plt.title("Clustering Score Comparison")
    plt.tight_layout()
    plt.savefig(plot_path)
    plt.close()
    print(f"✅ Clustering score comparison plot saved to {plot_path}")

    # Save the score data as CSV
    df.to_csv(csv_path, index=False)
    print(f"✅ Clustering score comparison CSV saved to {csv_path}")



def main():
    print("Loading graph embeddings...")
    graph_embs = load_graph_embeddings()

    print("Loading text embeddings...")
    embedder = TrajectoryEmbedder()
    text_embs = load_text_embeddings(embedder, METADATA_CSV)

    shared_ids = list(set(graph_embs) & set(text_embs))
    print(f"Found {len(shared_ids)} shared graph/text pairs")

    graph_matrix = np.array([graph_embs[i] for i in shared_ids])
    metadata_features = load_metadata_features(shared_ids)
    graph_matrix = np.concatenate([graph_matrix, metadata_features], axis=1)
    text_matrix = np.array([text_embs[i] for i in shared_ids])

    score_dicts = {}

    # --- No Dimensionality Reduction ---
    gk_raw, glabels_raw, g_scores_raw = cluster_and_evaluate(graph_matrix, method_label="Graph-Raw")
    tk_raw, tlabels_raw, t_scores_raw = cluster_and_evaluate(text_matrix, method_label="Text-Raw")

    # plot_tsne_cancer_type(graph_matrix, glabels_raw, shared_ids, label_type="Graph-Raw")
    # plot_tsne_metastasis(graph_matrix, glabels_raw, shared_ids, label_type="Graph-Raw")
    # plot_tsne_cancer_type(text_matrix, tlabels_raw, shared_ids, label_type="Text-Raw")
    # plot_tsne_metastasis(text_matrix, tlabels_raw, shared_ids, label_type="Text-Raw")

    # Save metrics
    score_dicts["Graph-Raw"] = g_scores_raw[gk_raw]
    score_dicts["Text-Raw"] = t_scores_raw[tk_raw]

    for method in ["pca", "umap"]:
        reduced_graph = reduce_dimensions(graph_matrix, method=method)
        reduced_text = reduce_dimensions(text_matrix, method=method)

        gk, glabels, g_scores = cluster_and_evaluate(reduced_graph, f"Graph-{method.upper()}")
        tk, tlabels, t_scores = cluster_and_evaluate(reduced_text, f"Text-{method.upper()}")

        # plot_tsne_cancer_type(reduced_graph, glabels, shared_ids, label_type=f"Graph-{method.upper()}")
        # plot_tsne_metastasis(reduced_graph, glabels, shared_ids, label_type=f"Graph-{method.upper()}")
        # plot_tsne_cancer_type(reduced_text, tlabels, shared_ids, label_type=f"Text-{method.upper()}")
        # plot_tsne_metastasis(reduced_text, tlabels, shared_ids, label_type=f"Text-{method.upper()}")

        score_dicts[f"Graph-{method.upper()}"] = g_scores[gk]
        score_dicts[f"Text-{method.upper()}"] = t_scores[tk]

    plot_score_comparison(score_dicts, shared_ids, glabels, tlabels)


if __name__ == "__main__":
    main()
