graph_data = {
    "nodes": [
        {"id": 1, "label": "Node 1", "customData": "Initial"},
        {"id": 2, "label": "Node 2", "customData": "Initial"}
    ],
    "edges": [
        {"from": 1, "to": 2, "customData": "Initial edge"}
    ]
}

def get_graph():
    return graph_data

def set_graph(new_graph):
    graph_data["nodes"] = new_graph.get("nodes", [])
    graph_data["edges"] = new_graph.get("edges", [])
