"""
    



    this file is for the minimal example from graph gen to end


"""
from ..data.data_processors.pdf_to_text import extract_text_from_pdf
from ..graph.graph_manager import GraphManager
from ..graph.graph_protocol import Graph
from .. graph.build_graph import GraphBuilder
from uuid import uuid4


from dataclasses import dataclass
from typing import Dict, Any

from dataclasses import dataclass, field
from typing import Union, Set, Optional
from uuid import  UUID
from ..graph.node.node_protocol import NodeProtocol
from ..graph.edge.edge_protocol import EdgeProtocol

@dataclass
class NodeData:
    id: Union[int, UUID]
    data: dict  # assuming RecursiveDict is just nested dicts for mockup

class FakeNode(NodeProtocol):
    def __init__(self, node_id: Union[int, UUID], data: Optional[dict] = None):
        self.id = node_id
        self._data = NodeData(id=node_id, data=data or {})
        self.neighbors: Set[FakeNode] = set()
        self._parent: Optional[FakeNode] = None
        self._children: Set[FakeNode] = set()
    
    def get_data(self) -> NodeData:
        return self._data

    def get_parent(self):
        return self._parent

    def set_parent(self, parent: 'FakeNode'):
        self._parent = parent
        parent._children.add(self)

    def get_children(self):
        return self._children


@dataclass
class FakeEdgeData:
    type: str
    confidence: float
    metadata: dict
class FakeEdge:
    def __init__(self, edge_id:Union[int, UUID],source: NodeProtocol, target: NodeProtocol, data: dict):
        self.id=edge_id
        self.source = source
        self.target = target
        self.data = data

    def get_data(self) -> dict:
        return self.data
def node_factory(node_id: Union[int, UUID]) -> FakeNode:
    return FakeNode(node_id, data={"label": f"Node-{node_id}", "created": True})

def edge_factory(edge_id:Union[int, UUID],source: NodeProtocol, target: NodeProtocol, attrs: dict) -> FakeEdge:
    return FakeEdge(edge_id,source, target, data=attrs)
def __main__():
     

    # 0 
    # TODO: finish loading configs. 


    # 1 load in the data from pdf and configs. 
    # semi done, 
    # filePath = path_from_config()
    # filePath = "./samples/pdfs/am_journal_case_reports_2024.pdf"

    # text = pdf().... done 
    # text = extract_text_from_pdf(filePath)
    # actually get the edges and nodes, 
    


    # 2 initialize all the lm and more stuff. 
    #   done 
    # does not work right now, sooo lets assume we get a fake combo of nodes.  or outputs for any and all steps. 
    

    # 3 get the nodes-->>> lets assume you have perfect nodes... for each node, or response ensure it is 
    #nodes in this case
    
    singleNode=node_factory(1)
   
    node2 = node_factory(2)
    fake_one=edge_factory(edge_id=uuid4(),source=singleNode, target=node2, attrs={"data":"main"})
    # should update the nodes they touch 
    builder=GraphBuilder()

    builder.add_node(singleNode)
    builder.add_node(node2)
    builder.set_root(singleNode)
    builder.add_edge(fake_one)
    
    print(builder._nodes)
    print(builder._edges)
    # the following lets see, th e
    
    #breaks here... lets see
    
    graph_struct=builder.build()#implement should produce a graph, 

    print(graph_struct.edges())
    root_node=graph_struct.get_root_node()
    print(root_node.get_children())
    # What would you 


    # ok cool you have the graph struct, then you need to construct the 
    
    # process that you need to do 
    # construct the graph, then move on from this, 
    


    # the follwoing should be done and in this case, 
    # rules for branching
    # inner branch resolves, 
    
    # time to build the follow
    # lets assume perfection then move onto the next things, 

    # manager=GraphManager(graph_struct)
    
    
    # start with this structure then move into building the rest of it, 


    # iteration practice 1: need a 
    

    
    # time to build the followingm df
    
    #ok now that you have the builder nodes going lets move onto the next part, what else should you be building into this, fg;,k f
    # things it should do is reconnect and build the entire node based structure. 
    # simple node =

        #notes: each node is not gauranteed to be complete... TODO include a function to verify causal compliance of information... hard when you have semantic transitions... willl need to figure out.. ie "Patient pulled out iv, "-> no longer active drug administration... relevant in notes. not in case repoerts. 
    # 4 the following things should be doing int h

    # the following should be done in this case, 


    # trial run assume perfect nodes and edges... edge first based construction build adjacency matrix

    # adjacency_matrix(edge_list)-> [[]]

    # construct_from_adjacency_matrix()->Graph || Error :
 
    # Ok so you have the following things that need to be done, and then more... lets keep it going, 
    # 5 The following thing should be loooked into the following shoudl sfk df 
    

    # 6 
    
if __name__ == "__main__":
    __main__()