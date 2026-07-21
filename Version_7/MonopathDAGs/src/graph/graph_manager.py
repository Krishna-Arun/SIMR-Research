# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see CONTRIBUTORS.md)
#
# SPDX-License-Identifier: Apache-2.0


"""
Graph manager for building and managing graphs."""


from typing import Union,Optional
from .node.node_protocol import NodeProtocol as Node
from .edge.edge_protocol import EdgeProtocol as Edge
from .build_graph import GraphBuilder
from .graph_protocol import Graph 


# confused as to what you are doing here, 

class GraphManager:
    """
    TODO:
    [ ] add support for single graph instance
    [ ] create add node 
    [ ] track pointer0-
        [ ] set_active_pointer
        [ ] build 
    [ ] create_branch
    [ ] single graph instanc
    logic needs to be the followig 
   
    """
    def __init__(self, graph_start: Union[Node, Graph],pointer:Optional[Node]=None):
        """ 
        point, 
        Args:
        start_data: Union[Node,Graph] basically


        """ 
        if type(graph_start) is Node:
            # initialize the graph frome node
            builder=GraphBuilder()
            builder.add_node(graph_start)
            builder.set_root(node=graph_start.id)
            self.graph=builder.build()
        else:
            self.graph=graph_start

        # set pointer
        if pointer:
            self.set_active_pointer(pointer)
        else: 
            # might wanna change to be the most recently added nod
            
            self.set_active_pointer(self.graph.get_root_node())

        self._branches= self.setup_branching()

    def add_node(self,node:Node, edge:Edge, parent:Optional[Node])-> bool:
        "inserts node at parent node, requires node and edge. should return bool indicating success or failure, "
        
        # 
        # inserting node should basically take the take the edge, and insert it from the parent, f
        
    
        
        # planning for this requires, 
        
        return success
    # things to accomplish you need to add the nodes here and then move forard form that and then move onto the next part.... so the next thing you should do in this case is try to get your stuff working
    #what should be done her.e 
    
    def setup_branching(self,):
        """this function should go through the existing graph and construct an initial dictionary of branches with the array of nodes
        of note each time a branch is added without the following, 
        """
        # step wise what is needed for this?
        # bracnching action




    def add_new_conection(self, node:Node,edge:Edge, parent:Node,)-> bool:
        """add a new connection within the node."""
        # get pointer
        assert self.__pointer, "pointer should not be empty"
        # the following should be built in this case and then what 
        

        




    def graph_builder_ver_connect_node(self, node:Node,edge:Edge, parent:Optional[Node] ):
        """
        Basically combining the following and then you should see more on this, 
        the graph builder should 
        
        """
        self.graph_builder.add_node(node)
        # creating a new way to build 



    def set_active_pointer(self, target: Node)->bool:
        """
        This function should update the active pointer. 
        
        """
        # identify current pointer.. in the list of pointers

        # figure out which LRU, 

        # check if pointer for the branch exists if not update the list with the new pointer and place first

        #set as active pointer., 
        # set the active pointer in this case and then  ove onto the other stuff. 
        if target:
            self.__pointer=target
            return True
        else:
            return False

        


class DynamicDataGraphManager(GraphManager):
    """_summary_

    Args:
        GraphManager (_type_): _description_
    """
    def __init__(self, root):
        super().__init__(root)
    
    



    # data

    
def __main__():
    # this script should have a starting point, 
    pass


# the following should be done here, you have the f=

if __name__ == __main__:
    __main__()
    #! initailize the graph manager with some arbitrary graph.. 

    # or start with nothing, ...


    # next add a dumb node to the current pointer... 

    # each additional node should have a new edge added with the source, should update the current node with a single instance of 