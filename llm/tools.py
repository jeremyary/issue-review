# This project was developed with assistance from AI tools.
"""Tool-calling infrastructure for agentic LLM interactions."""

import json
import logging
from dataclasses import dataclass
from typing import Callable


logger = logging.getLogger(__name__)


@dataclass
class Tool:
    """Definition of a tool that can be called by an LLM."""
    name: str
    description: str
    parameters: dict  # JSON Schema for parameters
    function: Callable[..., str]  # Function that returns JSON string
    
    def to_openai_format(self) -> dict:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


@dataclass
class ToolCall:
    """A tool call request from the LLM."""
    id: str
    name: str
    arguments: dict


@dataclass
class ToolResult:
    """Result of executing a tool."""
    tool_call_id: str
    result: str


def tools_to_openai_format(tools: list[Tool]) -> list[dict]:
    """Convert tools to OpenAI function calling format."""
    return [tool.to_openai_format() for tool in tools]


def parse_tool_calls(response) -> list[ToolCall]:
    """Parse tool calls from an OpenAI API response."""
    tool_calls = []
    message = response.choices[0].message
    
    if hasattr(message, 'tool_calls') and message.tool_calls:
        for tc in message.tool_calls:
            try:
                arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                arguments = {}
            
            tool_calls.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=arguments,
            ))
    
    return tool_calls


def execute_tool(tool_call: ToolCall, available_tools: list[Tool]) -> ToolResult:
    """Execute a tool call and return the result."""
    # Find the tool
    tool = None
    for t in available_tools:
        if t.name == tool_call.name:
            tool = t
            break
    
    if tool is None:
        return ToolResult(
            tool_call_id=tool_call.id,
            result=json.dumps({"error": f"Unknown tool: {tool_call.name}"})
        )
    
    try:
        result = tool.function(**tool_call.arguments)
        result_str = result if isinstance(result, str) else json.dumps(result)
        return ToolResult(tool_call_id=tool_call.id, result=result_str)
    except Exception as e:
        return ToolResult(
            tool_call_id=tool_call.id,
            result=json.dumps({"error": str(e)})
        )


def execute_tools(tool_calls: list[ToolCall], available_tools: list[Tool]) -> list[ToolResult]:
    """Execute multiple tool calls."""
    return [execute_tool(tc, available_tools) for tc in tool_calls]


def tool_results_to_messages(results: list[ToolResult]) -> list[dict]:
    """Convert tool results to message format for continuing the conversation."""
    return [
        {
            "role": "tool",
            "tool_call_id": result.tool_call_id,
            "content": result.result,
        }
        for result in results
    ]


def chat_with_tools(
    client,
    model: str,
    messages: list[dict],
    tools: list[Tool],
    max_iterations: int = 15,
    temperature: float = 0.3,
) -> tuple[str, list[dict]]:
    """Run a chat completion with tool calling, handling the tool loop.
    
    LLM calls are automatically traced by Langfuse if the client uses the wrapper.
    Session ID from context is automatically included for trace grouping.
    
    Args:
        client: OpenAI client
        model: Model name
        messages: Initial messages
        tools: Available tools
        max_iterations: Maximum tool-calling iterations
        temperature: Temperature for generation
    
    Returns:
        Tuple of (final_content, full_message_history)
    """
    messages = messages.copy()
    openai_tools = tools_to_openai_format(tools)
    
    for iteration in range(max_iterations):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=openai_tools if openai_tools else None,
            temperature=temperature,
        )
        
        message = response.choices[0].message
        
        # Check if we got tool calls
        tool_calls = parse_tool_calls(response)
        
        if not tool_calls:
            # No tool calls, we're done
            return message.content or "", messages
        
        # Add assistant message with tool calls
        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    }
                }
                for tc in tool_calls
            ]
        })
        
        # Execute tools
        results = execute_tools(tool_calls, tools)
        
        # Add tool results
        messages.extend(tool_results_to_messages(results))
    
    # Max iterations reached - make one final call WITHOUT tools to force a response
    logger.warning(
        "Tool loop hit max_iterations (%d), forcing final response without tools",
        max_iterations,
    )
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    final_content = response.choices[0].message.content or ""
    return final_content, messages
