


"""
Class is done too early come back when you want fully extensible..


"""
from typing import Protocol
from .message import Message #TODO need to implement, 
from .response import AgentResponse #TODO need to implment
from .tool import ToolCall #TODO need tto implment, copy anthropics mcp? or just go to base data and extend class. 



class AgentProtocol(Protocol):
    """
    A generic, pluggable agent interface supporting LLMs, scripted agents, or tool-using systems.

    Distinctlky seperate the send and return to ensure asynchronous behavior later or threading, 
    """

    def send_message(self, message: Message) -> None:
        """
        Accepts a message for the agent to process.
        

        Args:
            message (Message): The structured message input.
        """
        raise NotImplementedError("This is a required interface method")

    def return_message(self) -> AgentResponse:
        """
        Returns the agent's output or decision as a structured response.

        Returns:
            AgentResponse: The agent's reply or action.
        """
        raise NotImplementedError("this is a required implemented to handle async returns.  ")

    def can_use_tools(self) -> bool:
        """
        Indicates whether this agent is capable of tool use., might be dumb but should

        Returns:
            bool: True if tool use is supported.
        """
        raise NotImplementedError("mandatory implmentation and logic for anything agentic")

    def execute(self, tool_call: ToolCall) -> AgentResponse:
        """
        # TODO REMOVE THIS AND PLACE IN SOMETHING THAT MAKES SENSE IE A TOOL ORCHESTRATOR + MANAGER, shoudl be detached from process. 
        Optionally execute a tool invocation..... THIS SHOULD ACTUALLY BE IN A DIFFERENT CLASS AS TOOL EXECUTION SHOULD BE something else. 

        Args:
            tool_call (ToolCall): A structured tool call description.

        Returns:
            AgentResponse: The result of the tool invocation.
        """
        ...

    