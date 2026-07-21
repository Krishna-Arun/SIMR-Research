# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see CONTRIBUTORS.md)
#
# SPDX-License-Identifier: Apache-2.0



from typing import List,Dict, Any, Optional
from configparser import ConfigParser

from pathlib import Path
import os
import logging

import csv
import uuid
import json

from networkx import DiGraph
from dotenv import load_dotenv
from dspy import LM
from ...benchmark.modules.io_utils import load_graph_from_file
from ...benchmark.modules.reconstruction import LLMReconstructor
logging.basicConfig(level=logging.WARNING)
class SyntheticConstructor():
    """
    Constructs and generates synthetic case reports from either text or graph. 

    functions:

    init
    generate_synthetic_

    drop x or y node, 
    only can drop end to end, 



    """
    def __init__(self, graph, ini_path="./.config/prompts.ini"):
        

        self.graph = graph
       
        self.loader = PromptLoader(ini_path)


    def generate_paths(self) -> List[Dict[str, Any]]:
        """
        Returns:
            List[Dict[str, Any]]: each with keys:
                - 'path': list of node IDs from root to leaf
                - 'skipped': list of skipped node IDs due to forward edges
        """
        
        graph: DiGraph = self.graph
        if not isinstance(graph, DiGraph):
            raise TypeError("Graph must be a networkx.DiGraph")

        roots = [n for n in graph.nodes if graph.in_degree(n) == 0]
        if len(roots) != 1:
            raise ValueError("Graph must have exactly one root node")
        root = roots[0]

        paths: List[Dict[str, Any]] = []

        def dfs(node: str, path: List[str], skipped: List[str], visited: set):
            path.append(node)
            visited.add(node)

            children = list(graph.successors(node))
            if not children:
                paths.append({"path": path.copy(), "skipped": skipped.copy()})
                return

            for child in children:
                if child in visited:
                    continue

                if self.is_forward_edge(node, child):
                    # heuristic: other non-forward children are skipped
                    skipped_nodes = [
                        c for c in children
                        if c != child and not self.is_forward_edge(node, c)
                    ]
                    paths.append({
                        "path": path + [child],
                        "skipped": skipped + skipped_nodes
                    })
                else:
                    dfs(child, path.copy(), skipped.copy(), visited.copy())

        dfs(root, [], [], set())
        return paths
    def is_forward_edge(self, node: str, child: str) -> bool:
        """
        Checks if any edge between node → child is a 'forward' edge.
        Required for MultiDiGraph, where multiple edges may exist.
        """
        edge_bundle = self.graph.get_edge_data(node, child)
        if not edge_bundle:
            return False
        for edge_attrs in edge_bundle.values():
            if edge_attrs.get("type") == "forward":
                return True
        return False


    def pre_process_html(self,html):
        """_summary_

        Args:
            html (_type_): _description_
        """
        pass
    
    def generate_control_nodes(self,path,lm, pre_process):
        """
        Generates the controlnodes
        

        Args:
            path (_type_): _description_
            lm (_type_): _description_
        Returns:

        """
        
        # load html
        text_2_use=load_html_from_path(path)

        
        # pre-process the html if you need to 
        # processed_html=self.pre_process_html(text_2_use)
        prompt_control_nodes = self.loader.get("generate_control_nodes")
        rendered_prompt = prompt_control_nodes.replace("{{ html }}", text_2_use)
        lm_output_nodes_control=lm(rendered_prompt)
        print(lm_output_nodes_control)
        path_2_text = self.loader.get("path2text")
        rendered_path_2_text = path_2_text.replace("{{ path }}", str(lm_output_nodes_control))
        lm_output_case_report_control=lm(rendered_path_2_text)
        print(lm_output_case_report_control)

        

        
        # 3: naively create nodes
        # node creation is prompting to a single chat interface,. 
        # the other 



        # 4:  create the following things in this case the onl
        # create the follwoign f
        pass
     
    def path2structured(self, graph_path: list[str]) -> list[dict]:
        """
        Returns a flat ordered list of nodes and edges from the path.
        Each item preserves exact original structure.

        Assumes only one edge exists between each consecutive node pair.
        """
        graph = self.graph
        result = []

        for i, node_id in enumerate(graph_path):
            result.append({
                "type": "node",
                "node_id": node_id,
                "data": graph.nodes[node_id]
            })

            if i < len(graph_path) - 1:
                src = node_id
                dst = graph_path[i + 1]

                edge_dict = graph.get_edge_data(src, dst)
                if not edge_dict:
                    raise ValueError(f"No edge between {src} and {dst}")
                if len(edge_dict) != 1:
                    raise ValueError(f"Multiple edges found between {src} and {dst}; edge key disallowed")

                # Take the only edge, discard key
                edge_data = next(iter(edge_dict.values()))

                result.append({
                    "type": "edge",
                    "source": src,
                    "target": dst,
                    "data": edge_data
                })

        return result
   

class PromptLoader:
    """A class for loading prompts from a configuration file.

    This class reads a configuration file to load and retrieve prompt strings
    based on section names. It ensures that the case of the section names is preserved
    during the reading process.

    """
    def __init__(self, config_path: str):
        self.config = ConfigParser()
        self.config.optionxform = str  # preserve case
        self.config.read(Path(config_path), encoding='utf-8')

    def get(self, key: str) -> str:
        if key not in self.config:
            raise KeyError(f"Prompt section '{key}' not found.")
        return self.config[key]['prompt'].strip()





def load_html_from_path(path: str) -> Optional[str]:
    """
    Loads HTML content from the specified file path.

    Args:
        path (str): Path to the HTML file.

    Returns:
        Optional[str]: File content as a string, or None if the file is missing or unreadable.
    """
    if not os.path.isfile(path):
        logging.warning("File not found: %s", path)
        return None

    try:
        with open(path, 'r', encoding='utf-8') as file:
            return file.read()
    except (OSError, UnicodeDecodeError) as error:
        logging.warning("Failed to read file %s: %s", path, error)
        return None

# if __name__=="__main__":
#     from dotenv import load_dotenv
#     import dspy


#     load_dotenv(".config/.env")
#     gemini_api_key = os.environ.get("GEMINI_APIKEY")
#     gpt_key = os.environ.get("GPTKEY")
#     api_base_gemini="gemini/gemini-2.0-flash"
#     practice_file_path ="webapp/static/user_data/graph_test.json"
#     html_path="pmc_htmls/A_Case_Report_of_Intravitreal_Aflibercept_for_Iris_Metastasis_from_Small_Cell_Lu_PMC11919313.html"

#     lm = dspy.LM(api_base_gemini,api_key=gemini_api_key)
    
    
  
#     graph2use=load_graph_from_file(practice_file_path)

#     constructor=SyntheticConstructor(graph2use[0])
#     paths=constructor.generate_paths()
#     # print(constructor.path2structured(paths[0]["path"]))

#     reconstructor=LLMReconstructor(model_name='gemini/gemini-2.0-flash',api_key=gemini_api_key,prompt_tpl = (
#         "Reconstruct the clinical case report from this data:\n\n{payload}\n\n"
#         "Write a coherent narrative including patient demographics, "
#         "timeline of diagnoses, treatments, and outcomes."
#         "Do not include anything else other than the full case"
#     ))
#     narrative = reconstructor.reconstruct(
#     graph2use[0],
#     include_nodes=True,
#     include_edges=True,
#     node_ids=paths[0]["path"],
#     node_attrs=["content"]
# )
#     print(constructor.generate_control_nodes(html_path, lm))



def save_text_and_metadata(text: str, metadata: dict, output_dir: Path):
    """
    Saves the synthetic narrative text and appends metadata to index.jsonl.

    Args:
        text (str): The generated narrative.
        metadata (dict): Metadata including model, graph ID, etc.
        output_dir (Path): Directory to save output files.
    """
    uid = str(uuid.uuid4())[:8]
    metadata["uid"] = uid

    fname = f"{metadata['graph_id']}__{'control' if metadata['is_control'] else 'sample'}__{uid}.txt"
    metadata["text_file"] = fname

    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / fname, 'w', encoding='utf-8') as f:
        f.write(text)

    with open(output_dir / "index.jsonl", 'a', encoding='utf-8') as f:
        f.write(json.dumps(metadata) + "\n")


from glob import glob

def resolve_graph_path(original_path: str, fallback_root: str = "webapp/static/graphs") -> Optional[str]:
    if os.path.exists(original_path):
        return original_path
    filename = os.path.basename(original_path)
    matches = glob(f"{fallback_root}/**/{filename}", recursive=True)
    return matches[0] if matches else None


def run_batch(csv_path: str, models: list[dict], output_dir: str):
    """
    Run synthetic narrative generation for control and sample modes.

    Args:
        csv_path (str): Path to the input CSV.
        models (list[dict]): List of models with 'model_name' and 'api_key'.
        output_dir (str): Where to store output txt and metadata.
    """
    output_path = Path(output_dir)
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            graph_id = row["graph_id"]
            original_path = row["json_path"]
            html_path = row["source_file"]

            graph_path = resolve_graph_path(original_path)
            if not graph_path:
                print(f"⚠️ Could not resolve graph file: {original_path}")
                continue

            graph_list = load_graph_from_file(graph_path)
            if not graph_list:
                print(f"⚠️ Graph not loaded: {graph_path}")
                continue
            graph = graph_list[0]
            constructor = SyntheticConstructor(graph)

            html_content = load_html_from_path(html_path)
            if not html_content:
                print(f"⚠️ HTML not loaded: {html_path}")
                continue

            for model_entry in models:
                model_name = model_entry["model_name"]
                api_key = model_entry["api_key"]

                # === CONTROL ===
                control_lm = LM(model_name, api_key=api_key)

                try:
                    control_nodes = control_lm(
                        constructor.loader.get("generate_control_nodes").replace("{{ html }}", html_content)
                    )
                    control_prompt = constructor.loader.get("path2text").replace("{{ path }}", str(control_nodes))
                    control_text = control_lm(control_prompt)
                    if isinstance(control_text, list):
                        control_text = control_text[0]

                    save_text_and_metadata(
                        control_text,
                        {
                            "graph_id": graph_id,
                            "html_file": html_path,
                            "is_control": True,
                            "model": model_name,
                            "node_path_used": None,
                            "node_path_true": None
                        },
                        output_dir=output_path
                    )
                except Exception as e:
                    print(f"⚠️ Error in control generation for {graph_id} with {model_name}: {e}")
                    continue

                # === SAMPLE ===
                try:
                    reconstructor = LLMReconstructor(
                        model_name=model_name,
                        api_key=api_key,
                        prompt_tpl=(
                            "Reconstruct the clinical case report from this data:\n\n{payload}\n\n"
                            "Write a coherent narrative including patient demographics, "
                            "timeline of diagnoses, treatments, and outcomes. "
                            "Do not include anything else other than the full case."
                        )
                    )

                    paths = constructor.generate_paths()
                    if not paths:
                        print(f"⚠️ No valid paths in graph: {graph_id}")
                        continue
                    path = paths[0]

                    sample_text = reconstructor.reconstruct(
                        graph,
                        include_nodes=True,
                        include_edges=True,
                        node_ids=path["path"],
                        node_attrs=["content"]
                    )

                    save_text_and_metadata(
                        sample_text,
                        {
                            "graph_id": graph_id,
                            "html_file": html_path,
                            "is_control": False,
                            "model": model_name,
                            "node_path_used": path["path"],
                            "node_path_true": None
                        },
                        output_dir=output_path
                    )
                except Exception as e:
                    print(f"⚠️ Error in sample generation for {graph_id} with {model_name}: {e}")
                    continue



if __name__ == "__main__":

    
    load_dotenv(".config/.env")

    models = [
        {
            "model_name": "gemini/gemini-2.0-flash",
            "api_key": os.environ["GEMINI_APIKEY"]
        },
        # You can add more models here
    ]

    run_batch(
        csv_path="webapp/static/graphs/mapping/graph_metadata.csv",
        models=models,
        output_dir="./webapp/static/synthetic_outputs"
    )
