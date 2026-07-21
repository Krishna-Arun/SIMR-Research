# Monopath DAGs: Structuring Patient Trajectories from Clinical Case Reports

DynamicData is a modular pipeline for converting clinical case reports into structured representations of patient trajectories in the form of Monopath Directed Acyclic Graphs (DAGs). These graphs capture temporally ordered clinical states and transitions, supporting semantic modeling, similarity retrieval, and synthetic case generation.

This repository provides the tools used in our paper, including:

- A DSPy-driven pipeline for extracting DAGs from PubMed Central (PMC) HTML case reports
- Ontology-grounded node and edge generation using large language models
- A synthetic generation module for producing realistic case narratives
- Evaluation utilities for assessing semantic fidelity and structural correctness
- The full dataset of Monopath DAGs, extracted metadata, and synthetic cases

We release this framework and dataset to support research on clinically grounded trajectory modeling and structured patient representation.

---

##  Installation

### Clone the Repository

```
git clone https://github.com/DaneshjouLab/DynamicData.git <project_directory>


cd <project_directory>
```

### Create and Activate a Virtual Environment

```
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### Install Dependencies

```
pip install -r requirements.txt
```

---

##  Configuration

Create a `.env` file to store API keys and model names.

**Example `.config/.env`:**
```
DSPY_MODEL="gemini/gemini-2.0-flash"
GEMINI_APIKEY="your-gemini-api-key"
GPTKEY="your-openai-api-key"

```

**Recommended `.gitignore`:**
```
.config/.env
```

---

## Graph Generation Pipeline

Converts PMC HTML case reports into dynamic DAGs.

### Input

Place your HTML files in:
```
./pmc_htmls/
```

### Run the pipeline

```
python main.py generate-graphs --input_dir ./pmc_htmls --output_dir ./webapp/static/graphs
```

### Output

- Graph JSONs: `webapp/static/graphs/`
- Metadata: `webapp/static/graphs/graph_metadata.csv`

---

##  Synthetic Case Generation

Generates synthetic narratives from graph paths using LLMs.

### Prerequisites

Ensure graph metadata CSV exists:
```
webapp/static/graphs/graph_metadata.csv
```

### Run generation

```
python main.py generate-synthetic \
  --csv webapp/static/graphs/graph_metadata.csv \
  --output_dir synthetic_outputs \
  --model gemini/gemini-2.0-flash
```

### Output

- Text outputs: `synthetic_outputs/*.txt`
- Metadata index: `synthetic_outputs/index.jsonl`

---

##  Run Web Server

Serve the interface locally using FastAPI + Uvicorn:

```
python main.py run-server
```

Access at:
```
http://127.0.0.1:8000
```

---

## Project Structure

```
DynamicData/
├── .config/                      # API keys and model config
├── webapp/
│   ├── static/
│   │   ├── pmc_htmls/            # Input HTML articles
│   │   ├── graphs/               # Output graph JSONs and metadata
│   │   ├── synthetic_outputs/    # Output synthetic case reports
│   │   └── user_data/            # Temporary user data
├── src/
│   ├── pipeline/                 # Main execution scripts
│   ├── agent/                    # DSPy programs
│   ├── data/                     # Preprocessing logic
│   └── benchmark/modules/        # Graph reconstruction + utils
├── requirements.txt
└── README.md
```

---

## 🧪 Citation

```
@misc{zhou2025monopath,
title = {Monopath DAGs: Structuring Patient Trajectories from Clinical Case Reports},
author = {Zhou, Anson and Fanous, Aaron and Bikia, Vasiliki and Xu, Sonnet and Agarwal, Ank A. and Fanous, Noah and Huang, Lyndon and Luu, Jonathan and Tolbert, Preston and Alsentzer, Emily and Daneshjou, Roxana},
note = {Manuscript under review},
year = {2025},
url = {https://github.com/DaneshjouLab/DynamicData}
}

---

## 📜 License

This project is licensed under the Apache License 2.0. See the `LICENSE` file for details.
