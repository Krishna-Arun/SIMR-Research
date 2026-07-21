
from __future__ import annotations
import csv
import random
import dspy
import json
import time
from typing import List, Dict
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

from pprint import pprint
from tqdm import tqdm
from dspy import Example
from dspy.teleprompt import BootstrapFewShot
from dspy.evaluate import Evaluate
from src.data.data_processors.pdf_to_text import extract_text_from_pdf
from src.agent.dspy.testing_more import (extract_paragraphs, recursively_decompose_to_atomic_sentences)

import pandas as pd
import configparser
import json
import requests
import os
import json
import csv
import os
from pathlib import Path
from dotenv import load_dotenv
from testing_more import (
    preprocess_pmc_article_text,
    split_into_sentences,
    PatientTimeline
)
# =====================================
# DOCSTRING CONTENT
# =====================================

docstring_dict = {
    "dag_primer":
        """
    You are an assistant that converts clinical case narratives into dynamic Directed Acyclic Graphs (DAGs).

    Each DAG consists of:
    - Nodes = snapshots of the patient's state.
    - Edges = transitions between those states.

    Terminology guidance:
    - Use UMLS-standard concepts when possible for consistency and interoperability.
    - If a concept isn't covered by UMLS, use clear, logical labeling.

    Text extraction guidance:
    - When looking at the case report input, ignore the references, background, conclusions etc. sections
    - We only want to extract on content relating to the specific patient discussed in the case report


    """,

    "node_instructions":
    """
    You are given a clinical case report. Your task is to extract a sequence of nodes representing the patient's evolving clinical state.

    Guidelines:
    - Create one node per clinically meaningful state.
    - Combine co-occurring labs/imaging into the same node.
    - Use separate nodes for clearly sequential or distinct events.
    - Do not return anything outside the list format. Should be in JSON compatible style.
    - Keep imaging content packaged in one node if no clear temporal change is indicated
    - Keep pathology / histology content packaged in one node if no clear temporal change is indicated
    - node_memory is a running memory that updates as we add new nodes; use it to preserve context, merge overlapping details, and avoid redundant or stale states

    Output format:
    Return a list of node dictionaries, in this order from top to bottom, each with:
    - node_id (In ascending alphabetical order, e.g., "A", "B", "C")
    - node_step_index (integer for order)
    - content (exhuastive clinical content, include all relevant details for the given node)
    - timestamp (optional, ISO8601)

    Example:
    [±
      {
        "node_id": "A",
        "node_step_index": 0,
        "content": "The patient presented with bilateral painless testicular masses."
      }
    ]


    """,

    "edge_instructions": 
        """
    Each edge represents a change from one node to another. There should be one edge in between every pair of adjacent nodes.

    Guidelines for edges:
    - Create edges only when there is a clear clinical progression or change between nodes.
    - Maintain narrative or logical order — edges should flow from earlier to later events.
    - Combine co-occurring findings into the same node, not across multiple edges.

    Output format:
    Return a list of edge dictionaries, in this order, each with:
    - edge_id: Unique identifier (Use format "node_id"_to_"node_id", such that the first "node_id" is the upstream node and the second "node_id" is the downstream node bounding the edge)
    - branch_flag: Boolean if this starts a side branch, default = True
    - content: Exhuastive clinical content, include all relevant details for the given node

    Optional structured field for edge-level transitions:
    transition_event = {
        "trigger_type": "procedure | lab_change | medication_change | symptom_onset | interpretation | spontaneous",
        "trigger_entities": ["UMLS_CUI_1", "UMLS_CUI_2"],  # e.g., C0025598 = Metformin, C0011581 = Chest Pain
        "change_type": "addition | discontinuation | escalation | deescalation | reinterpretation | resolution | progression | other",  # Nature of the change
        "target_domain": "medication | symptom | diagnosis | lab | imaging | procedure | functional_status | vital_sign",  # What category was affected
        "timestamp": "ISO 8601 datetime (e.g., "2025-03-01T10:00:00Z"), only include if explicitly given and can be converted to datetime"
    }

    """,

    "node_clinical_data_instructions": 
        """
    Each node includes an optional structured field `clinical_data`, formatted as a dictionary with categories mapping to lists of dictionaries. Values should only be included if matched to the UMLS Metathesaurus; otherwise, omit and do not print/store it.
    
    clinical_data = {
        "medications": [
            {
                "drug": "UMLS_CUI or string",
                "dosage": "string",
                "frequency": "string",
                "modality": "oral | IV | IM | subcutaneous | transdermal | inhaled | other",
                "start_date": "ISO8601",
                "end_date": "ISO8601 or null",
                "indication": "UMLS_CUI or string"
            }
        ],
        "vitals": [
            {
                "type": "UMLS_CUI or string",
                "value": "numeric or string",
                "unit": "string",
                "timestamp": "ISO8601"
            }
        ],
        "labs": [
            {
                "test": "UMLS_CUI or string",
                "value": "numeric or string",
                "unit": "string",
                "flag": "normal | abnormal | critical | borderline | unknown",
                "reference_range": "string",
                "timestamp": "ISO8601"
            }
        ],
        "imaging": [
            {
                "type": "UMLS_CUI or string",
                "body_part": "UMLS_CUI or string",
                "modality": "X-ray | CT | MRI | Ultrasound | PET | other",
                "finding": "string",
                "impression": "string",
                "date": "ISO8601"
            }
        ],
        "procedures": [
            {
                "name": "UMLS_CUI or string",
                "approach": "open | laparoscopic | endoscopic | percutaneous | other",
                "date": "ISO8601",
                "location": "string",
                "performed_by": "string or provider ID",
                "outcome": "string or UMLS_CUI"
            }
        ],
        "HPI": [
            {
                "summary": "string",
                "duration": "string or ISO8601",
                "onset": "string or ISO8601",
                "progression": "gradual | sudden | fluctuating | unknown",
                "associated_symptoms": ["UMLS_CUI or strings"],
                "alleviating_factors": ["UMLS_CUI or strings"],
                "exacerbating_factors": ["UMLS_CUI or strings"]
            }
        ],
        "ROS": [
            {
                "system": "constitutional | cardiovascular | respiratory | GI | GU | neuro | psych | etc.",
                "findings": ["UMLS_CUI or strings"]
            }
        ],
        "functional_status": [
            {
                "domain": "mobility | cognition | ADLs | IADLs | speech | hearing | vision",
                "description": "string",
                "score": "numeric (if validated scale used)",
                "scale": "Barthel Index | MMSE | MoCA | other"
            }
        ],
        "mental_status": [
            {
                "domain": "orientation | memory | judgment | mood | speech",
                "finding": "UMLS_CUI or string",
                "timestamp": "ISO8601"
            }
        ],
        "social_history": [
            {
                "category": "smoking | alcohol | drug use | housing | employment | caregiver | support",
                "status": "current | past | never | unknown",
                "description": "string"
            }
        ],
        "allergies": [
            {
                "substance": "UMLS_CUI or string",
                "reaction": "UMLS_CUI or string",
                "severity": "mild | moderate | severe | anaphylaxis",
                "date_recorded": "ISO8601"
            }
        ],
        "diagnoses": [
            {
                "code": "ICD10 or SNOMED or UMLS_CUI",
                "label": "string",
                "status": "active | resolved | historical | suspected",
                "onset_date": "ISO8601 or null"
            }
        ]

    """,
    
    "branch_instructions":
        """
    Branches arise when physiologic changes or complications aren't part of the main pathway but impact patient states. Specifically, we are thinking of ephemeral changes.

    Mark side branches clearly:
    - Edge initiating a new branch: branch_flag = True
    """
}
# remove and place in an n

def load_docstrings_from_ini(file_path):
    config = configparser.ConfigParser()
    config.read(file_path)

    docstring_dict.update({
        "dag_primer": config.get("Docstrings", "dag_primer"),
        "node_instructions": config.get("Docstrings", "node_instructions"),
        "edge_instructions": config.get("Docstrings", "edge_instructions"),
        "node_clinical_data_instructions": config.get("Docstrings", "node_clinical_data_instructions"),
        "branch_instructions": config.get("Docstrings", "branch_instructions")
    })

# Example usage
load_docstrings_from_ini("/path/to/your/docstrings.ini")
# i would still fix this up because the docstring can be too long, 

# =====================================
# SELECTED LLM
# =====================================









# =====================================
# DSPY SIGNATURES
# =====================================

class nodeConstruct(dspy.Signature):
    text_input: str = dspy.InputField(desc="body of text extracted from a case report")
    node_memory: list[dict] = dspy.InputField(optional=True, desc="List of nodes generated so far (memory). Use as context when generating new nodes so there is no duplication.") # Sliding window, grows as we make new nodes
    node_output = dspy.OutputField(type=list[dict], desc="A list of node dictionaries with node_id, node_step_index, content, optional timestamp and clinical_data")


class edgeConstruct(dspy.Signature):
    #text_input: str = dspy.InputField(desc="body of text extracted from a case report")
    node_input: list[dict] = dspy.InputField(desc="Ordered list of node dictionaries as generated by nodeConstruct")
    edge_output: list[dict] = dspy.OutputField(desc="A list of edge dictionaries with edge_id, branch_flag, content, and optional transition event. There should be one edge in between every adjacent node.")

class nodeClinicalDataExtract(dspy.Signature):
    # Optional: You can comment this out to rely only on atomic_sentences
    content: str = dspy.InputField(desc="Narrative clinical content from a node")
    atomic_sentences: list[str] = dspy.InputField(desc="List of atomic-level clinical statements derived from the node content")
    clinical_data: dict = dspy.OutputField(desc="Structured clinical data dictionary with fields like medications, labs, imaging, etc.")

class branchClassify(dspy.Signature):
    content: str = dspy.InputField(desc="content section from either a node or an edge")
    branch_bool: bool = dspy.OutputField()

# =====================================
# FORM AND APPLY DOCSTRINGS
# =====================================

nodeConstruct.__doc__ = docstring_dict["dag_primer"] + docstring_dict['node_instructions']
edgeConstruct.__doc__ = docstring_dict["dag_primer"] + docstring_dict['edge_instructions']
nodeClinicalDataExtract.__doc__ = docstring_dict["dag_primer"] + docstring_dict["node_clinical_data_instructions"]
branchClassify.__doc__ = docstring_dict["dag_primer"] + docstring_dict['branch_instructions']

# =====================================
# MODULES
# =====================================


class NodeEdgeGenerate(dspy.Module):
    def __init__(self):
        super().__init__()
        self.node_module = dspy.Predict(nodeConstruct)
        #self.edge_module = dspy.Predict(edgeConstruct)
        self.edge_module = dspy.Predict(edgeConstruct, examples=edge_fewshot_examples) # With some examples to reinforce structure


    def generate_node(self, text_input, node_memory=None):
        # Call the LLM to get raw nodes
        result = self.node_module(
            text_input=text_input,
            node_memory=node_memory or []
        )
        nodes = result.get("node_output", [])

        # If the LLM returns a JSON string, parse it
        if isinstance(nodes, str):
            try:
                parsed = json.loads(nodes)
                if isinstance(parsed, list):
                    nodes = parsed
                else:
                    raise ValueError("Parsed node output is not a list.")
            except Exception as e:
                print(f"Warning: Node output not valid JSON. Error: {e}")
                nodes = []

        # If have prior memory, merge new with old
        if node_memory:
            nodes = merge_memory_nodes(node_memory, nodes)

        # Return the unified list under the same key
        return {"node_output": nodes}


    def generate_edge(self, node_input):
        # For edge generation, the node_input is the dict of nodes that are output from generate_node
        result = self.edge_module(node_input=node_input)
        edges = result.get("edge_output", [])

        # Handle stringified JSON if returned as text
        if isinstance(edges, str):
            try:
                parsed = json.loads(edges)
                if isinstance(parsed, list):
                    edges = parsed
                else:
                    raise ValueError("Parsed edge output is not a list.")
            except Exception as e:
                print(f"Warning: Edge output not valid JSON. Error: {e}")
                edges = []

        return {"edge_output": edges}



class ClinicalDataExtractor(dspy.Module):
    def __init__(self, max_retries: int = 2):
        super().__init__()
        self.extractor = dspy.Predict(nodeClinicalDataExtract)
        self.max_retries = max_retries

    def forward(self, content: str = "", atomic_sentences: list[str] = []):
        attempt = 0
        clinical_data = None

        while attempt <= self.max_retries:
            result = self.extractor(content=content, atomic_sentences=atomic_sentences)
            raw_output = result.get("clinical_data", {})

            print(f"\n=== Attempt {attempt + 1}: Raw clinical_data output ===")
            print(raw_output)

            # --- FIX: unwrap list if needed ---
            if isinstance(raw_output, list):
                # Take first dict if exists
                clinical_data = next((item for item in raw_output if isinstance(item, dict)), None)
            elif isinstance(raw_output, dict):
                clinical_data = raw_output
            else:
                clinical_data = None

            # If we got valid dict → DONE
            if isinstance(clinical_data, dict):
                return clinical_data

            print(f"⚠️ Attempt {attempt + 1}: clinical_data invalid → retrying...")
            attempt += 1

        # After retries failed → fallback
        print(f"❌ Failed to obtain valid clinical_data after {self.max_retries + 1} attempts. Returning empty dict.")
        return {}



class BranchClassifier(dspy.Module):
    def __init__(self):
        super().__init__()
        self.program = dspy.Predict(branchClassify)

    def forward(self, content):
        return self.program(content=content)




# ---------------------------------------
# FEW-SHOT EXAMPLES - EDGE CONSTRUCTION
# ---------------------------------------

# Structure not coming out right with edges so doing these to reinforce output

edge_example_1 = dspy.Example(
    node_input=[{"node_id": "A"}, {"node_id": "B"}],
    edge_output=[{
        "edge_id": "A_to_B",
        "branch_flag": True,
        "content": "Severe headache led to CT finding of subdural hematoma.",
        "transition_event": {
            "trigger_type": "symptom_onset",
            "trigger_entities": ["C0018681", "C0038454"],  # e.g., UMLS CUIs
            "change_type": "progression",
            "target_domain": "imaging"
        }
    }]
).with_inputs("node_input")

edge_example_2 = dspy.Example(
    node_input=[{"node_id": "B"}, {"node_id": "C"}],
    edge_output=[{
        "edge_id": "B_to_C",
        "branch_flag": True,
        "content": "Rash developed after antibiotics.",
        "transition_event": {
            "trigger_type": "medication_change",
            "trigger_entities": ["C0003232", "C0037274"],  # Antibiotics, Rash
            "change_type": "adverse_effect",
            "target_domain": "symptom"
        }
    }]
).with_inputs("node_input")

edge_example_3 = dspy.Example(
    node_input=[{"node_id": "C"}, {"node_id": "D"}],
    edge_output=[{
        "edge_id": "C_to_D",
        "branch_flag": False,
        "content": "PET-CT showed regression of disease.",
        "transition_event": {
            "trigger_type": "interpretation",
            "trigger_entities": ["C0151744"],  # Regression
            "change_type": "resolution",
            "target_domain": "diagnosis"
        }
    }]
).with_inputs("node_input")

edge_fewshot_examples = [edge_example_1, edge_example_2, edge_example_3]



# =====================================
# FEW-SHOT EXAMPLES - BRANCH CLASSIFY
# =====================================

# Pull examples from csv file

def load_branch_examples_from_csv(csv_path):
    examples = []
    with open(csv_path, newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        
        for idx, row in enumerate(reader):

            bool_val = row["branch_bool"].strip().upper() == "TRUE"

            # Fully DSPy-compliant example
            ex = dspy.Example(content = row["content"], branch_bool = bool_val).with_inputs("content")
            # ex.input_keys = ["content"]
            # ex.output_keys = ["branch_bool"]
            # ex = ex.with_inputs(content=row["content"])
            # ex = ex.with_outputs(branch_bool=bool_val)

            if idx < 2:
                print(f"Loaded example {idx}")
                print("  Inputs:", ex.inputs())
                print("  Outputs:", ex.labels())

            examples.append(ex)
    return examples


def branching_accuracy(gold, pred,trace=None):
    return int(gold.branch_bool == pred.branch_bool)


# Calling CSV with examples of content and bool pairs
branch_examples = load_branch_examples_from_csv("./src/data/branch_data.csv")
random.shuffle(branch_examples)

trainset = branch_examples[:85]
devset   = branch_examples[85:]

# Search labeled examples to select best demos for few-shot prompts
teleprompter = BootstrapFewShot(
    metric=branching_accuracy,
    max_bootstrapped_demos=4,
    max_labeled_demos=40,
    max_rounds=1
)



# Try bootstrapping few-shot examples
teleprompter.compile(
    dspy.Predict(branchClassify),  # compile only returns optimized Predict, not needed here
    trainset=trainset
)

# Extract selected demos
selected_demos = teleprompter.get_params().get("demos", [])

if selected_demos:
    print("\nSelected few-shot demonstrations:") # Check if any selected via bootstrap
    for i, ex in enumerate(selected_demos):
        print(f"Example {i+1}:")
        print("  Inputs:", ex.inputs)
        print("  Outputs:", ex.outputs)
else: # if none selected, just select the first X examples
    num_examples = 2
    print("No few-shot demonstrations found.")
    print(f"Using fallback: selecting the first {num_examples} examples from trainset.")
    selected_demos = trainset[:num_examples]

# Final classifier using selected or fallback examples
optimizedBranchClassifier = dspy.Predict(branchClassify, examples=selected_demos)
    

# =====================================
# EXTRACTION PROCESS AND ORG FUNCTIONS
# =====================================


def decompose_content_to_atomic_statements(content_block: str) -> list[str]:
    """
    Given a content string from a node or edge, decompose it into atomic clinical statements.

    Intended for use *after* nodes or edges are generated from the full case report.

    Parameters:
    - content_block (str): A single content string from a node or edge.

    Returns:
    - List of atomic clinical sentences (List[str])
    """
    atomic_statements = []

    for sentence in content_block.split(". "):
        if sentence.strip():
            decomposed = recursively_decompose_to_atomic_sentences(sentence.strip())
            atomic_statements.extend(decomposed)

    return atomic_statements




class ChunkedNodeGenerator(dspy.Signature):
    case_report: str = dspy.InputField(desc="Full clinical case report text")
    max_words_per_chunk: int = dspy.InputField(desc="Maximum number of words per chunk", default=250)
    max_chunks: int = dspy.InputField(desc="Maximum number of chunks to process (optional)", default=None)
    node_output: list[dict] = dspy.OutputField(desc="List of generated node dictionaries")


class ChunkingNodeModule(dspy.Module):
    def __init__(self, generator: NodeEdgeGenerate):
        super().__init__()
        self.generator = generator

    def forward(self, case_report: str, max_chunks: int = None) -> Dict[str, List[Dict]]:
        """
        Processes each sentence individually through the generator.

        Args:
            case_report (str): Input case report text.
            max_chunks (int, optional): Maximum number of sentences to process.

        Returns:
            Dict[str, List[Dict]]: Generated node outputs.
        """
        sentences = split_into_sentences(case_report,4)  # List[str]

        if max_chunks is not None:
            sentences = sentences[:max_chunks]

        memory_nodes: List[Dict] = []
        failed_chunks = 0
        start_time = time.time()

        for sentence in tqdm(sentences, desc="Generating nodes", unit="sentence"):
            try:
                text_input = sentence.strip()
                output = self.generator.generate_node(
                    text_input=text_input,
                    node_memory=memory_nodes
                )
                memory_nodes = output["node_output"]
            except Exception as exc:
                print(f"Warning: node generation failed on sentence. Error: {exc}")
                failed_chunks += 1

        elapsed_time = time.time() - start_time
        print(f"\nNode generation completed in {elapsed_time:.2f} seconds.")
        print(f"Failed sentences: {failed_chunks}/{len(sentences)}")

        return {"node_output": memory_nodes}


# Creates a dynamic memory to give nodes context as it is constructing

def merge_memory_nodes(prev_nodes: List[Dict], new_nodes: List[Dict]) -> List[Dict]:
    """
    Merge `new_nodes` into `prev_nodes` by:
      1. Appending truly new nodes.
      2. For matching node_ids, concatenating content and merging clinical_data.
      3. Re-assigning node_ids (“A”, “B”, …) and step_indices.
    """
    # shallow-copy previous
    merged = [n.copy() for n in prev_nodes]
    #lookup dictionary for merged. 
    lookup = {n["node_id"]: n for n in merged}
    # for cand in new nodes, 
    for cand in new_nodes:
        # candidate id
        cid = cand["node_id"]
        # if this in lookup
        if cid in lookup:
            # set base to the node
            base = lookup[cid]
            # merge content... if the content not in base you add it in. 
            if cand["content"] not in base["content"]:
                base["content"] += " " + cand["content"]
            # merge clinical_data->> close basically you take the cat and item
            for cat, items in cand.get("clinical_data", {}).items():
                bucket = base.setdefault("clinical_data", {}).setdefault(cat, [])
                for itm in items:
                    if itm not in bucket:
                        bucket.append(itm)
        else:
            merged.append(cand.copy())

    # re-index
    for idx, node in enumerate(merged):
        node["node_step_index"] = idx
        node["node_id"] = chr(ord("A") + idx)

    return merged


# Does final pass through completed sequence of nodes and helps to organize them
# problems with thios, we make heavy assumptions on the Node_ID being correct, which is close, 


class ReorganizeNodes(dspy.Signature):
    """
    Take a full list of extracted nodes, deduplicate or merge any
    overlapping/fragmented entries, then reindex them cleanly.
    """
    nodes_sequence: List[Dict] = dspy.InputField(
        desc="List of node dicts to be cleaned and merged"
    )
    node_output: List[Dict] = dspy.OutputField(
        desc="Reorganized list of nodes (deduped, merged, re‐indexed A, B, C…)"
    )

# lets try it this way
# 1: take in the text generated by the case, identify 



# =====================================
# RUN PIPELINE
# =====================================






def extract_case_report_text(pdf_path: str) -> str:
    """Extract text from a PDF case report."""
    return extract_text_from_pdf(pdf_path)


def preprocess_html_article(html_path: str) -> str:
    """Preprocess a PMC HTML article."""
    return preprocess_pmc_article_text(html_path)


def generate_paragraphs(raw_text: str, split_length: int = 10) -> List[str]:
    """Split preprocessed text into sentences/paragraphs."""
    return split_into_sentences(raw_text, split_length)


def generate_patient_timeline(paragraphs: List[str]) -> str:
    """Run DSPy patient timeline predictor across paragraphs."""
    predict_patient_timeline = dspy.Predict(PatientTimeline)
    prev_memory: List[str] = [""]

    for paragraph in paragraphs:
        output = predict_patient_timeline(
            paragraph=paragraph,
            previous_memory=prev_memory[-3:]
        )
        prev_memory.append(output.pt_timeline)
        print("-" * 30, output.pt_timeline)

    return prev_memory[-1]  # Final case report timeline


def run_node_generation(case_report: str) -> List[Dict[str, Any]]:
    """Run node generation pipeline."""
    generator = NodeEdgeGenerate()
    chunked_node_module = ChunkingNodeModule(generator)

    node_result = chunked_node_module(
        case_report=case_report,
        max_chunks=None
    )
    nodes_obj = node_result["node_output"]
    nodes_obj = merge_memory_nodes([], nodes_obj)

    nodes_obj = dspy.Predict(ReorganizeNodes)(nodes_sequence=nodes_obj).node_output
    return nodes_obj


def run_edge_generation(nodes_obj: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run edge generation pipeline."""
    generator = NodeEdgeGenerate()
    edge_result = generator.generate_edge(node_input=nodes_obj)
    return edge_result["edge_output"]


def annotate_nodes_with_clinical_data(nodes_obj: List[Dict[str, Any]]) -> None:
    """Append clinical data extraction to each node."""
    clinical_data_extractor = ClinicalDataExtractor()
    for node in nodes_obj:
        content_str = node.get("content", "")
        clinical_data = clinical_data_extractor(
            content=content_str,
            atomic_sentences=None
        )
        node["clinical_data"] = clinical_data


def evaluate_branching(edges_obj: List[Dict[str, Any]]) -> None:
    """Evaluate branching conditions and set branch_flag on first qualifying edge."""
    if not edges_obj:
        print("No edges available to evaluate.")
        return

    for edge in edges_obj:
        transition_content = edge.get("content", "")
        if not transition_content:
            continue

        branch_result = optimizedBranchClassifier(content=transition_content)
        print(f"\nEvaluating edge: {edge.get('edge_id', 'unknown')}")
        print(f"Content: {transition_content}")
        print(f"Branch decision: {branch_result.branch_bool}")

        if branch_result.branch_bool:
            print(f"Branch triggered — setting branch_flag = True on edge {edge['edge_id']}")
            edge['branch_flag'] = True
            return

    print("No edges met branching criteria.")


def print_nodes(nodes_obj: List[Dict[str, Any]]) -> None:
    """Pretty print all nodes."""
    print("=" * 60)
    print("Nodes (with clinical data):")
    print("=" * 60)

    for i, node in enumerate(nodes_obj):
        print(f"\n Node {i + 1}:")
        pprint(node)
        print("-" * 60)


def print_edges(edges_obj: List[Dict[str, Any]]) -> None:
    """Pretty print all edges."""
    print("=" * 60)
    print("Edges:")
    print("=" * 60)

    for i, edge in enumerate(edges_obj):
        print(f"\n Edge {i + 1}: edge_id = {edge.get('edge_id', 'N/A')}")
        pprint(edge)
        print("-" * 60)


def run_pipeline(html_path: str) -> tuple[list[dict], list[dict]]:
    """Main orchestrator function for running the entire pipeline.

    Returns:
        nodes_obj: List of node dictionaries
        edges_obj: List of edge dictionaries
    """
    global_start = time.time()

    # STEP 1: Extract and preprocess text
    
    raw_text = preprocess_html_article(html_path)
    paragraphs = generate_paragraphs(raw_text, split_length=10)

    # STEP 2: Patient timeline prediction
    case_report = generate_patient_timeline(paragraphs)

    print("\n🧹 Cleaned Case Report (filtered output):")
    print("=" * 60)
    print(case_report)
    print("=" * 60)

    # STEP 3: Node and edge generation
    nodes_obj = run_node_generation(case_report)
    annotate_nodes_with_clinical_data(nodes_obj)

    edges_obj = run_edge_generation(nodes_obj)
    evaluate_branching(edges_obj)

    # STEP 4: Print outputs
    print_nodes(nodes_obj)
    print_edges(edges_obj)

    global_end = time.time()
    print(f"\n=== Full DAG generation pipeline completed in {global_end - global_start:.2f} seconds ===")

    return nodes_obj, edges_obj



















def format_nodes(raw_nodes):
    """
    Format node list for storage, including custom data.
    """
    return [
        {
            "id": f"N{idx + 1}",
            "label": f"Step {idx + 1}",
            "customData": node
        }
        for idx, node in enumerate(raw_nodes)
    ]

def format_edges(raw_edges, node_lookup):
    """
    Format directed edge list for storage, including full edge data.
    """
    formatted = []
    for edge in raw_edges:
        source, target = edge["edge_id"].split("_to_")
        formatted.append({
            "from": f"N{node_lookup[source] + 1}",
            "to": f"N{node_lookup[target] + 1}",
            "data": edge
        })
    return formatted

def save_json_file(data, output_path):
    """
    Save dictionary data as a JSON file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"✅ Saved graph JSON: {output_path}")

def append_csv_row(csv_path, row, header):
    """
    Append a row to a CSV file, creating the file if it doesn't exist.
    """
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.is_file()

    with csv_path.open('a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
    print(f"✅ Updated CSV: {csv_path}")

def process_and_save_graph(raw_nodes, raw_edges, graph_id, source_file, output_dir):
    """
    Process raw graph data, save JSON, and log metadata.
    

    """
    

    node_lookup = {
    node["node_id"]: idx
    for idx, node in enumerate(raw_nodes)
    if node and "node_id" in node
}
    valid_raw_nodes = [node for node in raw_nodes if node and "node_id" in node]
    formatted_nodes = format_nodes(valid_raw_nodes)
    formatted_edges = format_edges(raw_edges, node_lookup)

    graph_filename = f"{graph_id}.json"
    graph_path = Path(output_dir) / graph_filename
    metadata_csv = Path(output_dir) / "graph_metadata.csv"

    save_json_file({"nodes": formatted_nodes, "edges": formatted_edges}, graph_path)

    metadata_row = {
        "graph_id": graph_id,
        "json_path": str(graph_path),
        "source_file": source_file
    }
    append_csv_row(metadata_csv, metadata_row, header=["graph_id", "json_path", "source_file"])








def generate_all_graphs(input_folder: str, output_dir: str):

    DSPY_MODEL = os.environ.get("DSPY_MODEL", "gemini/gemini-2.0-flash") 
    gemini_api_key = os.environ.get("GEMINIAPIKEY")


    if "ollama" in DSPY_MODEL:
        lm = dspy.LM(DSPY_MODEL, api_base='http://localhost:11434', api_key='')
    else:
        lm = dspy.LM(DSPY_MODEL, api_key=gemini_api_key, temperature=0.21, cache=False)

    dspy.configure(lm=lm, adapter=dspy.ChatAdapter())

    os.makedirs(output_dir, exist_ok=True)
    graph_counter = 1

    for html_filename in os.listdir(input_folder):
        if not html_filename.lower().endswith(".html"):
            continue

        html_path = os.path.join(input_folder, html_filename)
        graph_id = f"graph_{graph_counter:03d}"
        graph_json_path = os.path.join(output_dir, f"{graph_id}.json")

        if os.path.exists(graph_json_path):
            print(f"✅ Skipping {html_filename} → {graph_id} already exists.")
            graph_counter += 1
            continue

        print(f"\n=== Processing {html_filename} as {graph_id} ===")

        nodes_obj, edges_obj = run_pipeline(html_path)

        process_and_save_graph(
            raw_nodes=nodes_obj,
            raw_edges=edges_obj,
            graph_id=graph_id,
            source_file=html_path,
            output_dir=output_dir
        )

        graph_counter += 1


if __name__ == "__main__":
    env_path = os.environ.get("config_path")
    load_dotenv(env_path)
    generate_all_graphs(
        input_folder="./pmc_htmls",
        output_dir="./webapp/static/graphs"
    )





