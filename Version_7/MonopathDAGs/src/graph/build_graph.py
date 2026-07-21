"""
    
    This file should be responsible for graph creation in the initial state, 


"""


from typing import Optional, Dict, List, Callable, Sequence, Union
from .node.node_protocol import NodeProtocol as Node
from .edge.edge_protocol import EdgeProtocol as Edge

from .graph_protocol import Graph, GraphImplemented

# the following should be don ein this you hsould have the following things, a graph that elts you build the folloinw,g 
class GraphBuilder: 
    """
    Constructs a graph from Node and Edge objects before handing off
    to a read-only Graph instance.

    
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        self._edges: Dict[str,Edge] = {}
        self._root: Optional[str] = None

    def set_root(self, node: Node) -> None:
        """Set the root node."""
        
        self._root = node.id
        # this is dumb why is it adding the thing to a dict, 
        self._nodes[node.id] = node

    def add_node(self, node: Node) -> None:
        """Add a node to the graph. adds it arbitrarily, to the graph, no connection,"""
        self._nodes[node.id] = node
    def add_edge(self, edge:Edge)-> None:
        
        self._edges[edge.id]=edge

    # def attach_edge(self, edge: Edge, source:Node, target:Node) -> None:
    #     """Attach an edge to the graph."""
    #     if edge.source not in self._nodes or edge.target not in self._nodes:
    #         raise ValueError("Both source and target nodes must be added before attaching an edge.")
    #     self._edges.append(edge)
        
    
    def build(self) -> Graph:
        """Return an immutable Graph object."""

        return GraphImplemented(nodes=self._nodes.values(), edges=self._edges.values(), root=self._root)
    


    def build_from_adjacency_matrix(self, matrix: Sequence[Sequence[Union[int, float]]], graph_validation_callback: Callable[[Graph], Graph]) -> Graph:
        """ builds graph from adjacency matrix, 
         Most functions assume that adjacency matrices are complete in terms of correctneess or rather nodes are complete with informaiton, 
         but that is not guaranteed so you might need a callback to verify from root, as you store graph... this should be a callback when graph has been completed. 
         
"""         
        # implement the logic in this should build the entire matrix from the adjacency be aware that the edges might not be complete and also might need to flag nodes for updates

        # adjacency matrices are built through
        # each adjacency matrix[i][j]
     
        num_nodes = len(matrix)
        for row in range(num_nodes):
            for col in range(num_nodes):
                # for each entry of adjacency it sis
                matrix[row][col]
                

        if graph_validation_callback:
            graph = graph_validation_callback(graph)

        
        return Graph
    #REMOVE
    # def build_from_adjacency_list(
    #     self,
    #     adj_list: Dict[str, List[str]],
    #     node_factory: Callable[[str], Node],
    #     edge_factory: Callable[[str, str], Edge],
    #     graph_validation_callback: Optional[Callable[[Graph], Graph]] = None,
    # ) -> Graph:
    #     """
    #     Build a graph from an adjacency list representation.
    #     Each key in adj_list is a node ID; its list contains the IDs of connected nodes.
    #     """
    #     # Create all nodes
    #     for node_id in adj_list.keys():
    #         if node_id not in self._nodes:
    #             self._nodes[node_id] = node_factory(node_id)
    #         for target_id in adj_list[node_id]:
    #             if target_id not in self._nodes:
    #                 self._nodes[target_id] = node_factory(target_id)

    #     # Create all edges
    #     for source_id, targets in adj_list.items():
    #         for target_id in targets:
    #             edge = edge_factory(source_id, target_id)
    #             self._edges.append(edge)

    #     graph = Graph(nodes=self._nodes, edges=self._edges, root=self._root)
    #     return graph_validation_callback(graph) if graph_validation_callback else graph

    # def build_graph_from_edge_list(
    #     self,
    #     edge_list: List[tuple],
    #     node_factory: Callable[[str], Node],
    #     edge_factory: Callable[[str, str], Edge],
    #     graph_validation_callback: Optional[Callable[[Graph], Graph]] = None,
    # ) -> Graph:
    #     """
    #     Build a graph from an edge list representation.
    #     Each tuple contains (source_id, target_id)
    #     """
    #     for source_id, target_id in edge_list:
    #         if source_id not in self._nodes:
    #             self._nodes[source_id] = node_factory(source_id)
    #         if target_id not in self._nodes:
    #             self._nodes[target_id] = node_factory(target_id)
    #         edge = edge_factory(source_id, target_id)
    #         self._edges.append(edge)

    #     graph = Graph(nodes=self._nodes, edges=self._edges, root=self._root)
    #     return graph_validation_callback(graph) if graph_validation_callback else graph
    

# the follwoing should be built next in this case, 
# ok the folloiwng should be done in this case, 

# implmenting the adjacency list

