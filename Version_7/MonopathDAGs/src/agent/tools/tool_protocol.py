

"""
V1. the first initial appication of tool dev... 

Idea here being that a tool should be a some awaited promise to an agent or llm, 

Tool calls can fail and need to be resolved if that is the case, intermediary message passer is needed if the underlying technique does not implement


"""


from typing import Protocol, Any, Dict, Optional, List, AsyncIterator


class ToolArtifact:
    def __init__(self, content: Any, type: str = "generic", metadata: Optional[Dict[str, Any]] = None):
        self.content = content
        self.type = type
        self.metadata = metadata or {}

    def as_json(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "metadata": self.metadata,
            "content": self.content,
        }


class ToolSession(Protocol):
    async def stream(self) -> AsyncIterator[ToolArtifact]:
        """Yield ToolArtifacts as they become available."""
        ...

    async def push(self, update: Dict[str, Any]) -> None:
        """Push incremental context or input into the tool session."""
        ...


class Tool(Protocol):
    """_summary_

    Args:
        Protocol (_type_): _description_
    """
    name: str
    description: str
    batchable: bool
    parallel_safe: bool
    streamable: bool

    async def resolve(self, **kwargs) -> ToolArtifact:
        """Resolve this tool with input args into a ToolArtifact."""
        ...

    def start_session(self, **kwargs) -> ToolSession:
        """Optional: Return a streamable tool session."""
        ...

    def manifest(self) -> Dict[str, Any]:
        """Return machine-readable metadata about this tool."""
        ...


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def list(self, context: Optional[Dict[str, Any]] = None) -> List[Tool]:
        return list(self._tools.values())

class tool_v1(Protocol):
    """
    Tools should act like artificat messages that can be independent, 

    base version should incllude the following, only the 

    Tools should have some public interface and some public response, and if the tool requires another call

    should resolve with declaration, 
    Args:
        Protocol (_type_): _description_
    """
    def __init__(self):
        pass
    

class tool_artificat():
    def __init__(self):
        pass


#llm -> requests tool use, 
# 



