# SPDX-FileCopyrightText: 2025 Stanford University and the project authors (see CONTRIBUTORS.md)
#
# SPDX-License-Identifier: Apache-2.0


"""
This file should contian an edge protocol. 

# TODO: implement the following, 

"""
from dataclasses import dataclass, fields, is_dataclass, MISSING,field
from typing import Any, Type, get_origin, get_args
from typing  import Protocol,Union,Optional,Iterable,List,Dict

import copy
from uuid import UUID
from typing_extensions import Self

# A recursive dictionary type that allows scalar values as well as nested dictionaries and lists of nested dictionaries.
RecursiveDict = Dict[str, Union[str, int, float, bool, None, 'RecursiveDict', List['RecursiveDict']]]
@dataclass
class BaseData:
    """
    Base class for dataclasses that want to support construction
    from unstructured dicts via the from_attrs() method.

    Supports:
    - Nested dataclass construction
    - Lists of nested dataclasses
    - Skipping missing fields
    - Ignoring unknown fields

    Pylint-safe: handles missing fields, unused args, and unknown keys gracefully.
    """

    @classmethod
    def from_attrs(cls: Type[Self], attrs: dict[str, Any]) -> Self:
        """
        Create an instance of this dataclass from a dictionary of attributes.

        Args:
            attrs (dict): Input dictionary of attributes.

        Returns:
            Instance of cls constructed from the filtered and typed attributes.

        Notes:
            - Nested dataclass fields are recursively constructed.
            - List fields containing dataclasses are supported.
            - Extra fields not defined in the dataclass are ignored.
        """

        # Dictionary to collect processed, type-safe constructor arguments
        instance_data = {}

        # Iterate over all declared fields of the dataclass
        for field in fields(cls):
            field_name = field.name
            field_type = field.type

            # Attempt to retrieve the value for this field
            value = attrs.get(field_name, MISSING)

            # Skip the field if not present in the input dictionary
            if value is MISSING:
                continue

            # Determine the type origin (e.g., list, Union) and type arguments
            origin = get_origin(field_type)
            args = get_args(field_type)

            # Case 1: Field is a nested dataclass and value is a dict
            if is_dataclass(field_type) and isinstance(value, dict):
                instance_data[field_name] = field_type.from_attrs(value)

            # Case 2: Field is a list of dataclasses (e.g., List[MyType])
            elif origin is list and args and is_dataclass(args[0]):
                nested_type = args[0]
                instance_data[field_name] = [
                    nested_type.from_attrs(v) if isinstance(v, dict) else v
                    for v in value
                ]

            # Case 3: Field is a primitive or already well-formed value
            else:
                instance_data[field_name] = value

        # Return an instance of the dataclass with validated inputs
        return cls(**instance_data)
@dataclass
class NodeData(BaseData):
    """ Class for indicting data stored in node. """
    id: Union[int, UUID]
    
    data: RecursiveDict




class NodeProtocol(Protocol):
    """
    this
    Args:
        Protocol (_type_): _description_
    """
    def __init__(self, node_id:Union[int,UUID],):

        self.id = node_id
        self.neighbors = set()

    def get_data(self)-> Union[dict, None, NodeData]:
        "get the data of the node"
        raise NotImplementedError("every node should be readable")
    def get_parent(self):
        raise NotImplementedError()
    def get_children(self):
        raise NotImplementedError()
    def set_parent(self, parent:Self):
        raise NotImplementedError()
#

@dataclass(frozen=True)
class ImmutableNode(NodeProtocol):
    """Immutable implementation of NodeProtocol."""
    id: Union[int, UUID]
    data: NodeData
    parent: Optional[Self] = None
    children: Iterable[Self]= field(default_factory=list)
    def get_parent(self) -> Optional[Self]:
        return self.parent

    def get_children(self) -> List[Self]:
        return list(self.children)

    def set_parent(self, parent: Self) -> Self:
        """
        Returns a new ImmutableNode instance with the updated parent.
        """
        return ImmutableNode(
            id=self.id,
            data=self.data,
            parent=parent,
            children=self.children
        )
    def get_data(self):
        "read only return of data. "
        return self.data

@dataclass
class MutableNode(NodeProtocol):
    """Mutable implementation of NodeProtocol. Can be extended if mutable behavior is needed."""
    id: Union[int, UUID]
    data: NodeData
    parent: Optional[Self] = None
    children: List[Self] = field(default_factory=list)

    def get_data(self) -> NodeData:
        return self.data

    def get_parent(self) -> Optional[Self]:
        return self.parent

    def get_children(self) -> List[Self]:
        return self.children

    def set_parent(self, parent: Self) -> Self:
        self.parent = parent
        return self
    def set_children(self,children:Optional[List[NodeProtocol]]):
        raise NotImplementedError("make")






class NodeFactory:
    """Factory for creating node instances, 
    default is immutable.. this allows parallel creation and no race issues. 
    """
    def __init__(self, immutable: bool = True) -> None:
        self.immutable = immutable
    def create_node(self, data: NodeData) -> NodeProtocol:
        """
        Create a new node instance with the provided data.
        Generates a new UUID if data.id is None.

        Args:
            data (NodeData): The data for the node.

        Returns:
            NodeProtocol: An instance of a node (immutable by default).
        """
        node_id = data.id if data.id is not None else UUID()
        if self.immutable:
            return ImmutableNode(id=node_id, data=data)
        else:
            return MutableNode(id=node_id, data=data)
        



    def clone_and_modify_node(self, source_node: NodeProtocol, new_node_data: NodeData):
        """Creates a new node based on a source node, applying specified modifications.

        This method initializes the new node's data by taking a copy of the
        `source_node`'s data. It then updates this copied data by overwriting
        any fields that are present in the `new_node_data` structure. Fields
        from the `source_node` that do not have a corresponding entry in
        `new_node_data` are retained in the new node.

        Args:
            source_node (NodeProtocol): The node to use as the base template. Its data
                                       provides the initial values for the new node.
            new_node_data (NodeData): A data structure containing the fields and their
                                      new values that should overwrite the corresponding
                                      fields copied from the `source_node`.

        Returns:
            NodeProtocol: A new node instance resulting from applying the updates
                          in `new_node_data` to the data from `source_node`.
        """
        # Implementation would go here, for example:
        # 1. Extract data from source_node (e.g., source_data = source_node.get_data())
        # 2. Create a mutable copy (e.g., final_data = source_data.copy())
        # 3. Iterate through new_node_data and update final_data
        #    (e.g., for key, value in new_node_data.items(): final_data[key] = value)
        # 4. Create and return the new node using final_data
        #    (e.g., return self.create_node(final_data)) # Assuming create_node exists
        try:
            source_data = source_node.get_data()
        except AttributeError as exc:
            # Raise a more informative AttributeError, chaining the original exception
            raise AttributeError(
                "The provided 'source_node' object does not have the required 'get_data' method."
                                 ) from exc
        # 2. Create a deep copy to avoid modifying the original node's data,
        #    especially important if data contains nested lists/dicts.
        #    Use source_data.copy() if a shallow copy is sufficient and safe.
        final_data = copy.deepcopy(source_data)

        # 3. & 4. Iterate through the new data and update/overwrite the copied data
        try:
            for key, value in new_node_data.items():
                final_data[key] = value
        except AttributeError as exc:
            raise AttributeError(
                 "new_node_data must have an 'items' method (be dict-like)."
                 ) from exc

        # 5. Create and return the new node instance using the final combined data
        try:
            new_node = self.create_node(final_data)
            return new_node
        except Exception as e:
            # Handle or log node creation errors if necessary
            print(f"Error creating new node instance: {e}")
            raise
