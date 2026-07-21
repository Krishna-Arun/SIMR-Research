# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see CONTRIBUTORS.md)
#
# SPDX-License-Identifier: Apache-2.0


"""
File for some graph procotols including the DAG one, 
  

"""


from typing import Protocol, Iterable,runtime_checkable,Set,List,Optional,Union,Dict
from collections import defaultdict
from uuid import UUID
from .node.node_protocol import NodeProtocol as Node
from .edge.edge_protocol import EdgeProtocol as Edge


__all__ = [ "Graph", "DAG"]


@runtime_checkable
class Graph(Protocol):
    """Protocol representing a directed or undirected graph structure."""

    def nodes(self) -> Iterable[Node]:
        """Return all nodes in the graph."""
        raise NotImplementedError

    def edges(self) -> Iterable[Edge]:
        """Return all edges in the graph as (source, target) pairs."""
        raise NotImplementedError

    def has_node(self, node: Node) -> bool:
        """Check if the graph contains the given node."""
        raise NotImplementedError

    def has_edge(self, source: Node, target: Node) -> bool:
        """Check if an edge exists from source to target."""
        raise NotImplementedError

    def neighbors(self, node: Node) -> Iterable[Node]:
        """Return all directly connected neighbors of the given node."""
        raise NotImplementedError

class GraphImplemented(Graph):
    def __init__(self,
                 nodes: Optional[Iterable[Node]] = None,
                 edges: Optional[Iterable[Edge]] = None,
                 root: Optional[Union[int, UUID]] = None):
        self._nodes: Dict[Union[int, UUID], Node] = {}
        self._edges: Dict[Union[int, UUID], Edge] = {}
        self._adjacency: Dict[Union[int, UUID], List[Node]] = defaultdict(list)
        self._root = root

        if nodes:
            for node in nodes:
                
                self._nodes[node.id] = node

        if edges:
            for edge in edges:
                edge_id = edge.id
                self._edges[edge_id] = edge
                self._adjacency[edge.source.id].append(edge.target)

    def nodes(self) -> Iterable[Node]:
        return self._nodes.values()

    def edges(self) -> Iterable[Edge]:
        return self._edges

    def has_node(self, node: Node) -> bool:
        return node.id in self._nodes

    def has_edge(self, source: Node, target: Node) -> bool:
        return target in self._adjacency.get(source.id, [])

    def neighbors(self, node: Node) -> Iterable[Node]:
        return self._adjacency.get(node.id, [])
    def get_root_id(self):
        "get the roo id"
        return self._root
    def get_root_node(self):
        " get the root node"
        return self._nodes[self._root]

class DAG(Graph, Protocol):
    """Protocol representing a directed acyclic graph (DAG).
    ALL FUNCTIONS SHOULD BE READ ONLY, GRa
    
    """

    def topological_sort(self) -> List[Node]:
        """Return nodes in a valid topological order."""
        raise NotImplementedError

    def ancestors(self, node: Node) -> Set[Node]:
        """Return all nodes with a path to the given node (its ancestors)."""
        raise NotImplementedError

    def descendants(self, node: Node) -> Set[Node]:
        """Return all nodes reachable from the given node (its descendants)."""
        raise NotImplementedError

    def roots(self) -> Set[Node]:
        """Return all nodes with no incoming edges."""
        raise NotImplementedError

    def leaves(self) -> Set[Node]:
        """Return all nodes with no outgoing edges."""
        raise NotImplementedError
    

class DAG_Implemented(DAG):
    def __init__(self, root: Node, edge):
        """init the graph, 


        """