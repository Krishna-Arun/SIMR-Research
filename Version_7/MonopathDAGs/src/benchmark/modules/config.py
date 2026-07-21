# This source file is part of the Daneshjou Lab projects
#
# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see AUTHORS.md)
#
# SPDX-License-Identifier: MIT
#

"""This module contains configuration settings for the DSPy LLM and BERTScore models."""

import networkx as nx

# Graph type alias
Graph = nx.DiGraph

# Let's change this to GEMINI
# DSPy LLM settings
LM_MODEL     = "ollama/llama3.2"
LM_API_BASE  = "http://localhost:11434"
LM_API_KEY   = ""  # or your local key if required

# Trajectory Embedding settings
TRAJECTORY_EMBEDDING_MODEL = "emilyalsentzer/Bio_ClinicalBERT"
TEXT_FIELD_PATH = ["data", "commentary"]  # e.g., node["data"]["commentary"]
