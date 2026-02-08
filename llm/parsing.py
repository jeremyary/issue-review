# This project was developed with assistance from AI tools.
"""Shared utilities for parsing LLM responses."""

import json
import re


def extract_json_block(content: str) -> str | None:
    """Extract JSON from LLM response using multiple strategies.
    
    Tries these approaches in order:
    1. Regex match for ```json ... ``` blocks
    2. Regex match for ``` ... ``` blocks  
    3. Find the last { ... } block in the content
    
    Args:
        content: Raw LLM response that may contain JSON
    
    Returns:
        Extracted JSON string, or None if no JSON found
    """
    if not content:
        return None
    
    # Strategy 1: Look for ```json ... ``` block
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if json_match:
        return json_match.group(1)
    
    # Strategy 2: Look for ```json array
    json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', content, re.DOTALL)
    if json_match:
        return json_match.group(1)
    
    # Strategy 3: Find the outermost { ... } or [ ... ] block
    # Use first opening brace and last closing brace to capture full nested JSON
    start_brace = content.find('{')
    end_brace = content.rfind('}')
    if start_brace != -1 and end_brace > start_brace:
        return content[start_brace:end_brace + 1]
    
    start_bracket = content.find('[')
    end_bracket = content.rfind(']')
    if start_bracket != -1 and end_bracket > start_bracket:
        return content[start_bracket:end_bracket + 1]
    
    return None


def parse_json_response(content: str, default: dict | None = None) -> dict:
    """Parse JSON dict from LLM response, handling various formats.
    
    Handles common LLM output patterns:
    - Raw JSON
    - JSON wrapped in ```json ... ``` blocks
    - JSON at the end of a longer text response
    
    Args:
        content: The raw LLM response content
        default: Default value to return if parsing fails (default: empty dict)
    
    Returns:
        Parsed dict from the JSON response, or default value on parse failure
    """
    if default is None:
        default = {}
    
    json_str = extract_json_block(content)
    if json_str:
        try:
            result = json.loads(json_str)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
    
    # Fallback: try parsing the entire content
    try:
        result = json.loads(content.strip())
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    
    return default


