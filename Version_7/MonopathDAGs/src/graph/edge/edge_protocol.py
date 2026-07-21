# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see CONTRIBUTORS.md)
#
# SPDX-License-Identifier: Apache-2.0


"""
This file should contian an edge protocol. 

"""

from typing import Union,Protocol,List
from ..node.node_protocol import NodeProtocol, BaseData,RecursiveDict
from dataclasses import dataclass
from uuid import UUID,uuid4




# TODO: deprecate this, 
@dataclass
class EdgeData(BaseData):
    """ Class for indicting data stored in node. """
    id: Union[int, UUID]
    data: RecursiveDict



class EdgeProtocol(Protocol):
    "Edge Protocol"
    def __init__(self,edge_id:Union[int, UUID], source:Union[NodeProtocol,List[NodeProtocol]], destination:Union[NodeProtocol]):
        self.id=edge_id
        self.source = source
        self.target = destination
    
    def __repr__(self) -> str:
        return f"Edge({self.source}, {self.target})"

class DynamicDataEdge(EdgeProtocol):
    """Dynamic Data Edge, a read only edge, with the ability 

    Args:
        EdgeProtocol (_type_): _description_
    """
    def __init__(self, source:Union[NodeProtocol], destination:Union[NodeProtocol],data:Union[EdgeData,dict],**kwargs):
        """
        Summary 

        Args:
            source (Union[NodeProtocol]): 
            destination (Union[NodeProtocol]): _description_
            data (Union[EdgeData,dict]): _description_
        """
        self.id = kwargs.pop("edge_id", uuid4())  # required, but fallback-safe
        self.source = source
        self.target = destination
        self.data = data
    
    def get_data(self) -> Union[EdgeData, dict, None]:
        "getter function for data"
        return self.data
    

class OrderedEdge(EdgeProtocol):
    "Ordered Edge"
    def __init__(self, source:Union[NodeProtocol],
                 destination:Union[NodeProtocol],
                 order_index:Union[int]):
        super().__init__(source, destination)
        self.order_index = order_index
    def get_data(self) -> Union[dict, None]:
        pass
    def __repr__(self) -> str:
        return f"OrderedEdge({self.source}, {self.target}, {self.order_index})"

