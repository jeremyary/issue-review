# This project was developed with assistance from AI tools.
"""Content extraction and chunking for RAG indexing.

Implements intelligent chunking that:
- Respects markdown structure (h1 → h2 → h3 hierarchy)
- Preserves code blocks intact
- Adds overlap between chunks for context continuity
- Uses appropriate chunk sizes for embedding models
"""

import os
import re
import hashlib
from dataclasses import dataclass, field
from typing import Iterator


# Chunking configuration
DEFAULT_CHUNK_SIZE = 2500  # chars - larger for better context
DEFAULT_CHUNK_OVERLAP = 200  # chars - overlap for context continuity
MIN_CHUNK_SIZE = 100  # Don't create tiny chunks


@dataclass
class ContentChunk:
    """A chunk of content extracted from a repository."""
    quickstart_id: str
    repo_name: str
    file_path: str
    chunk_index: int
    content: str
    content_type: str  # "readme", "helm_values", "helm_chart"
    heading: str | None = None
    heading_hierarchy: list[str] = field(default_factory=list)  # Full path: ["Getting Started", "Prerequisites"]


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def extract_code_blocks(content: str) -> tuple[str, dict[str, str]]:
    """Extract code blocks and replace with placeholders.
    
    This prevents code blocks from being split during chunking.
    
    Args:
        content: Markdown content with code blocks
    
    Returns:
        Tuple of (content with placeholders, mapping of placeholder -> code block)
    """
    code_blocks = {}
    counter = 0
    
    def replace_block(match):
        nonlocal counter
        placeholder = f"__CODE_BLOCK_{counter}__"
        code_blocks[placeholder] = match.group(0)
        counter += 1
        return placeholder
    
    # Match fenced code blocks (``` or ~~~)
    pattern = r'```[\s\S]*?```|~~~[\s\S]*?~~~'
    modified = re.sub(pattern, replace_block, content)
    
    return modified, code_blocks


def restore_code_blocks(content: str, code_blocks: dict[str, str]) -> str:
    """Restore code blocks from placeholders."""
    for placeholder, code in code_blocks.items():
        content = content.replace(placeholder, code)
    return content


def parse_markdown_sections(content: str) -> list[dict]:
    """Parse markdown into hierarchical sections.
    
    Recognizes h1 (#), h2 (##), h3 (###), and h4 (####) headers.
    
    Args:
        content: Markdown content
    
    Returns:
        List of section dicts with 'level', 'heading', 'content', 'hierarchy'
    """
    # Pattern matches headers at any level (1-4)
    header_pattern = r'^(#{1,4})\s+(.+)$'
    
    lines = content.split('\n')
    sections = []
    current_hierarchy = {1: None, 2: None, 3: None, 4: None}
    current_section = {'level': 0, 'heading': None, 'content': [], 'hierarchy': []}
    
    for line in lines:
        match = re.match(header_pattern, line)
        
        if match:
            # Save previous section if it has content
            if current_section['content']:
                section_text = '\n'.join(current_section['content']).strip()
                if section_text:
                    current_section['content'] = section_text
                    sections.append(current_section)
            
            # Parse new header
            level = len(match.group(1))
            heading = match.group(2).strip()
            
            # Update hierarchy
            current_hierarchy[level] = heading
            # Clear lower levels
            for l in range(level + 1, 5):
                current_hierarchy[l] = None
            
            # Build hierarchy path
            hierarchy = [h for h in [current_hierarchy[l] for l in range(1, level + 1)] if h]
            
            current_section = {
                'level': level,
                'heading': heading,
                'content': [],
                'hierarchy': hierarchy,
            }
        else:
            current_section['content'].append(line)
    
    # Add final section
    if current_section['content']:
        section_text = '\n'.join(current_section['content']).strip()
        if section_text:
            current_section['content'] = section_text
            sections.append(current_section)
    
    return sections


def split_text_with_overlap(
    text: str,
    max_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split text into chunks with overlap, respecting paragraph boundaries.
    
    Args:
        text: Text to split
        max_size: Maximum chunk size in characters
        overlap: Number of characters to overlap between chunks
    
    Returns:
        List of text chunks
    """
    if len(text) <= max_size:
        return [text]
    
    chunks = []
    paragraphs = text.split('\n\n')
    
    current_chunk = []
    current_size = 0
    
    for para in paragraphs:
        para_size = len(para)
        
        # If single paragraph exceeds max, split by sentences
        if para_size > max_size:
            # Flush current chunk first
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
            
            # Split large paragraph by sentences
            sentences = re.split(r'(?<=[.!?])\s+', para)
            sent_chunk = []
            sent_size = 0
            
            for sent in sentences:
                if sent_size + len(sent) > max_size and sent_chunk:
                    chunks.append(' '.join(sent_chunk))
                    # Keep overlap from end of previous chunk
                    overlap_text = ' '.join(sent_chunk)[-overlap:] if overlap else ''
                    sent_chunk = [overlap_text] if overlap_text else []
                    sent_size = len(overlap_text)
                
                sent_chunk.append(sent)
                sent_size += len(sent) + 1
            
            if sent_chunk:
                chunks.append(' '.join(sent_chunk))
            continue
        
        # Check if adding this paragraph exceeds limit
        if current_size + para_size + 2 > max_size and current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            chunks.append(chunk_text)
            
            # Start new chunk with overlap from previous
            if overlap and len(chunk_text) > overlap:
                # Try to find a paragraph boundary for overlap
                overlap_start = chunk_text[-overlap:]
                # Find last paragraph break in overlap region
                last_para_break = overlap_start.rfind('\n\n')
                if last_para_break > 0:
                    overlap_text = overlap_start[last_para_break + 2:]
                else:
                    overlap_text = overlap_start
                current_chunk = [overlap_text] if overlap_text.strip() else []
                current_size = len(overlap_text)
            else:
                current_chunk = []
                current_size = 0
        
        current_chunk.append(para)
        current_size += para_size + 2
    
    # Add final chunk
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    
    return chunks


def split_markdown_by_headers(
    content: str,
    max_chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[tuple[str | None, str, list[str]]]:
    """Split markdown content intelligently by headers with code block preservation.
    
    Args:
        content: Markdown content
        max_chunk_size: Maximum characters per chunk
        chunk_overlap: Characters to overlap between chunks
    
    Returns:
        List of (heading, content, hierarchy) tuples
    """
    # Extract code blocks to protect them from splitting
    content_safe, code_blocks = extract_code_blocks(content)
    
    # Parse into hierarchical sections
    sections = parse_markdown_sections(content_safe)
    
    if not sections:
        # No headers found, treat as single section
        restored = restore_code_blocks(content, code_blocks)
        return [(None, restored, [])]
    
    chunks = []
    
    for section in sections:
        heading = section['heading']
        text = section['content']
        hierarchy = section['hierarchy']
        
        # Restore code blocks in this section
        text = restore_code_blocks(text, code_blocks)
        
        if not text.strip():
            continue
        
        # Split if too large
        if len(text) <= max_chunk_size:
            chunks.append((heading, text, hierarchy))
        else:
            # Split with overlap
            sub_chunks = split_text_with_overlap(text, max_chunk_size, chunk_overlap)
            for i, sub_text in enumerate(sub_chunks):
                if len(sub_text.strip()) >= MIN_CHUNK_SIZE:
                    # Mark continuation chunks
                    chunk_heading = heading if i == 0 else f"{heading} (continued)"
                    chunks.append((chunk_heading, sub_text, hierarchy))
    
    return chunks


def split_yaml_by_sections(
    content: str,
    max_chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[tuple[str | None, str]]:
    """Split YAML content by top-level keys.
    
    Args:
        content: YAML content
        max_chunk_size: Maximum characters per chunk
        chunk_overlap: Characters to overlap between chunks
    
    Returns:
        List of (section_name, content) tuples
    """
    # Find top-level keys (no indentation)
    lines = content.split('\n')
    sections = []
    current_key = None
    current_lines = []
    
    for line in lines:
        # Check if this is a top-level key (no leading whitespace, ends with :)
        if line and not line[0].isspace() and ':' in line:
            # Save previous section
            if current_lines:
                section_content = '\n'.join(current_lines)
                sections.append((current_key, section_content))
            
            current_key = line.split(':')[0].strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    
    # Add final section
    if current_lines:
        section_content = '\n'.join(current_lines)
        sections.append((current_key, section_content))
    
    # If no sections or only one, check size
    if len(sections) <= 1:
        if len(content) <= max_chunk_size:
            return [(None, content)]
        # Fall back to simple splitting
        sub_chunks = split_text_with_overlap(content, max_chunk_size, chunk_overlap)
        return [(None, chunk) for chunk in sub_chunks]
    
    # Merge small sections, split large ones
    final_chunks = []
    current_chunk = []
    current_size = 0
    current_keys = []
    
    for key, section_text in sections:
        section_size = len(section_text)
        
        if section_size > max_chunk_size:
            # Flush current accumulated chunk
            if current_chunk:
                combined_key = ', '.join(current_keys) if current_keys else None
                final_chunks.append((combined_key, '\n'.join(current_chunk)))
                current_chunk = []
                current_size = 0
                current_keys = []
            
            # Split large section
            sub_chunks = split_text_with_overlap(section_text, max_chunk_size, chunk_overlap)
            for i, sub_text in enumerate(sub_chunks):
                chunk_key = key if i == 0 else f"{key} (continued)"
                final_chunks.append((chunk_key, sub_text))
        
        elif current_size + section_size > max_chunk_size and current_chunk:
            # Flush and start new
            combined_key = ', '.join(current_keys) if current_keys else None
            final_chunks.append((combined_key, '\n'.join(current_chunk)))
            current_chunk = [section_text]
            current_size = section_size
            current_keys = [key] if key else []
        
        else:
            current_chunk.append(section_text)
            current_size += section_size
            if key:
                current_keys.append(key)
    
    # Add final accumulated chunk
    if current_chunk:
        combined_key = ', '.join(current_keys) if current_keys else None
        final_chunks.append((combined_key, '\n'.join(current_chunk)))
    
    return final_chunks


def extract_readme_chunks(
    repo_path: str,
    quickstart_id: str,
    repo_name: str,
    max_chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> Iterator[ContentChunk]:
    """Extract chunks from README.md with intelligent splitting.
    
    Uses hierarchical header awareness, code block preservation,
    and chunk overlap for better retrieval quality.
    
    Args:
        repo_path: Path to cloned repository
        quickstart_id: ID from catalog.yaml
        repo_name: GitHub repo name
        max_chunk_size: Maximum characters per chunk
        chunk_overlap: Characters to overlap between chunks
    
    Yields:
        ContentChunk objects
    """
    readme_path = os.path.join(repo_path, "README.md")
    
    if not os.path.exists(readme_path):
        # Try lowercase
        readme_path = os.path.join(repo_path, "readme.md")
    
    if not os.path.exists(readme_path):
        return
    
    with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    chunks = split_markdown_by_headers(content, max_chunk_size, chunk_overlap)
    
    for idx, (heading, text, hierarchy) in enumerate(chunks):
        if text.strip() and len(text.strip()) >= MIN_CHUNK_SIZE:
            yield ContentChunk(
                quickstart_id=quickstart_id,
                repo_name=repo_name,
                file_path="README.md",
                chunk_index=idx,
                content=text.strip(),
                content_type="readme",
                heading=heading,
                heading_hierarchy=hierarchy,
            )


def extract_helm_chunks(
    repo_path: str,
    quickstart_id: str,
    repo_name: str,
    max_chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> Iterator[ContentChunk]:
    """Extract chunks from Helm charts with YAML-aware splitting.
    
    Looks for:
    - helm/*/values.yaml
    - helm/*/Chart.yaml
    - charts/*/values.yaml
    - charts/*/Chart.yaml
    
    Large YAML files are split by top-level keys to preserve
    logical configuration groupings.
    
    Args:
        repo_path: Path to cloned repository
        quickstart_id: ID from catalog.yaml
        repo_name: GitHub repo name
        max_chunk_size: Maximum characters per chunk
        chunk_overlap: Characters to overlap between chunks
    
    Yields:
        ContentChunk objects
    """
    helm_dirs = ["helm", "charts", "deploy/helm", "deploy/charts"]
    
    for helm_base in helm_dirs:
        helm_path = os.path.join(repo_path, helm_base)
        
        if not os.path.exists(helm_path):
            continue
        
        # Find chart directories
        for item in os.listdir(helm_path):
            chart_path = os.path.join(helm_path, item)
            
            if not os.path.isdir(chart_path):
                continue
            
            # Extract values.yaml with YAML-aware chunking
            values_path = os.path.join(chart_path, "values.yaml")
            if os.path.exists(values_path):
                with open(values_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                file_rel_path = f"{helm_base}/{item}/values.yaml"
                
                # Split large YAML files by sections
                yaml_chunks = split_yaml_by_sections(content, max_chunk_size, chunk_overlap)
                
                for idx, (section_name, chunk_text) in enumerate(yaml_chunks):
                    if chunk_text.strip() and len(chunk_text.strip()) >= MIN_CHUNK_SIZE:
                        heading = f"Helm values for {item}"
                        if section_name:
                            heading = f"{heading}: {section_name}"
                        
                        yield ContentChunk(
                            quickstart_id=quickstart_id,
                            repo_name=repo_name,
                            file_path=file_rel_path,
                            chunk_index=idx,
                            content=chunk_text.strip(),
                            content_type="helm_values",
                            heading=heading,
                            heading_hierarchy=[item, section_name] if section_name else [item],
                        )
            
            # Extract Chart.yaml (typically small, no chunking needed)
            chart_yaml_path = os.path.join(chart_path, "Chart.yaml")
            if os.path.exists(chart_yaml_path):
                with open(chart_yaml_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                file_rel_path = f"{helm_base}/{item}/Chart.yaml"
                yield ContentChunk(
                    quickstart_id=quickstart_id,
                    repo_name=repo_name,
                    file_path=file_rel_path,
                    chunk_index=0,
                    content=content.strip(),
                    content_type="helm_chart",
                    heading=f"Helm chart definition for {item}",
                    heading_hierarchy=[item, "Chart.yaml"],
                )


def extract_notebook_chunks(
    repo_path: str,
    quickstart_id: str,
    repo_name: str,
    max_chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> Iterator[ContentChunk]:
    """Extract chunks from Jupyter notebooks.
    
    Notebooks contain valuable context mixing explanations with code.
    Extracts markdown cells (narrative) and code cells, keeping cell
    boundaries as natural chunk points.
    
    Args:
        repo_path: Path to cloned repository
        quickstart_id: ID from catalog.yaml
        repo_name: GitHub repo name
        max_chunk_size: Maximum characters per chunk
        chunk_overlap: Characters to overlap between chunks
    
    Yields:
        ContentChunk objects
    """
    import json
    
    # Common locations for notebooks
    notebook_dirs = [".", "notebooks", "examples", "demo", "docs"]
    processed_notebooks = set()
    
    for nb_dir in notebook_dirs:
        search_path = os.path.join(repo_path, nb_dir) if nb_dir != "." else repo_path
        
        if not os.path.exists(search_path):
            continue
        
        # Find .ipynb files (limit depth to avoid nested venvs)
        for root, dirs, files in os.walk(search_path):
            # Skip hidden dirs, venvs, and deep nesting
            dirs[:] = [d for d in dirs if not d.startswith('.') 
                       and d not in ('venv', 'node_modules', '__pycache__', '.ipynb_checkpoints')]
            
            depth = root[len(search_path):].count(os.sep)
            if depth > 2:
                continue
            
            for fname in files:
                if not fname.endswith('.ipynb'):
                    continue
                
                nb_path = os.path.join(root, fname)
                
                # Avoid processing same notebook twice
                if nb_path in processed_notebooks:
                    continue
                processed_notebooks.add(nb_path)
                
                try:
                    with open(nb_path, "r", encoding="utf-8", errors="ignore") as f:
                        notebook = json.load(f)
                except (json.JSONDecodeError, IOError):
                    continue
                
                cells = notebook.get("cells", [])
                if not cells:
                    continue
                
                # Build relative path
                rel_path = os.path.relpath(nb_path, repo_path)
                
                # Group consecutive cells into chunks
                current_content = []
                current_size = 0
                chunk_idx = 0
                
                for cell in cells:
                    cell_type = cell.get("cell_type", "")
                    source = cell.get("source", [])
                    
                    # Handle source as list or string
                    if isinstance(source, list):
                        cell_content = "".join(source)
                    else:
                        cell_content = source
                    
                    if not cell_content.strip():
                        continue
                    
                    # Format based on cell type
                    if cell_type == "markdown":
                        formatted = cell_content
                    elif cell_type == "code":
                        # Wrap code in markdown code block for context
                        formatted = f"```python\n{cell_content}\n```"
                    else:
                        continue
                    
                    cell_size = len(formatted)
                    
                    # Check if adding this cell exceeds limit
                    if current_size + cell_size > max_chunk_size and current_content:
                        # Emit current chunk
                        chunk_text = "\n\n".join(current_content)
                        if len(chunk_text.strip()) >= MIN_CHUNK_SIZE:
                            yield ContentChunk(
                                quickstart_id=quickstart_id,
                                repo_name=repo_name,
                                file_path=rel_path,
                                chunk_index=chunk_idx,
                                content=chunk_text.strip(),
                                content_type="notebook",
                                heading=f"Notebook: {fname}",
                                heading_hierarchy=[fname, f"cells {chunk_idx + 1}"],
                            )
                            chunk_idx += 1
                        
                        # Start new chunk with overlap
                        if chunk_overlap and current_content:
                            # Keep last cell for context if it fits
                            last_cell = current_content[-1]
                            if len(last_cell) < chunk_overlap:
                                current_content = [last_cell]
                                current_size = len(last_cell)
                            else:
                                current_content = []
                                current_size = 0
                        else:
                            current_content = []
                            current_size = 0
                    
                    current_content.append(formatted)
                    current_size += cell_size + 2  # +2 for \n\n separator
                
                # Emit final chunk
                if current_content:
                    chunk_text = "\n\n".join(current_content)
                    if len(chunk_text.strip()) >= MIN_CHUNK_SIZE:
                        yield ContentChunk(
                            quickstart_id=quickstart_id,
                            repo_name=repo_name,
                            file_path=rel_path,
                            chunk_index=chunk_idx,
                            content=chunk_text.strip(),
                            content_type="notebook",
                            heading=f"Notebook: {fname}",
                            heading_hierarchy=[fname, f"cells {chunk_idx + 1}"],
                        )


def extract_dependency_chunks(
    repo_path: str,
    quickstart_id: str,
    repo_name: str,
) -> Iterator[ContentChunk]:
    """Extract chunks from dependency and configuration files.
    
    These files reveal what libraries and features a quickstart uses,
    which is valuable for comparing against proposed quickstarts.
    
    Extracts:
    - requirements.txt
    - pyproject.toml
    - setup.py (if it defines dependencies)
    - .env.example / .env.template (configuration patterns)
    
    Args:
        repo_path: Path to cloned repository
        quickstart_id: ID from catalog.yaml
        repo_name: GitHub repo name
    
    Yields:
        ContentChunk objects
    """
    # Dependency files to look for
    dependency_files = [
        ("requirements.txt", "dependencies"),
        ("requirements-dev.txt", "dependencies"),
        ("pyproject.toml", "dependencies"),
        ("setup.py", "dependencies"),
        ("Pipfile", "dependencies"),
        ("poetry.lock", None),  # Skip lock files - too verbose
        ("package.json", "dependencies"),
    ]
    
    # Config template files
    config_files = [
        (".env.example", "config"),
        (".env.template", "config"),
        (".env.sample", "config"),
        ("config.yaml.example", "config"),
        ("config.yaml.template", "config"),
    ]
    
    chunk_idx = 0
    
    for filename, content_type in dependency_files + config_files:
        if content_type is None:
            continue
            
        file_path = os.path.join(repo_path, filename)
        
        if not os.path.exists(file_path):
            continue
        
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except IOError:
            continue
        
        if not content.strip() or len(content.strip()) < MIN_CHUNK_SIZE:
            continue
        
        # For pyproject.toml, extract just the relevant sections
        if filename == "pyproject.toml":
            content = _extract_pyproject_deps(content)
            if not content:
                continue
        
        # For setup.py, try to extract install_requires
        if filename == "setup.py":
            content = _extract_setup_deps(content)
            if not content:
                continue
        
        yield ContentChunk(
            quickstart_id=quickstart_id,
            repo_name=repo_name,
            file_path=filename,
            chunk_index=chunk_idx,
            content=content.strip(),
            content_type=content_type,
            heading=f"Dependencies: {filename}" if content_type == "dependencies" else f"Config template: {filename}",
            heading_hierarchy=[filename],
        )
        chunk_idx += 1


def _extract_pyproject_deps(content: str) -> str:
    """Extract dependency-related sections from pyproject.toml."""
    lines = content.split('\n')
    result_lines = []
    in_relevant_section = False
    relevant_sections = [
        '[project]',
        '[project.dependencies]',
        '[project.optional-dependencies',
        '[tool.poetry.dependencies]',
        '[tool.poetry.dev-dependencies]',
        '[tool.poetry.group',
    ]
    
    for line in lines:
        line_stripped = line.strip()
        
        # Check if entering a relevant section
        if line_stripped.startswith('['):
            in_relevant_section = any(
                line_stripped.startswith(sect) or line_stripped == sect.rstrip(']') + ']'
                for sect in relevant_sections
            )
        
        if in_relevant_section:
            result_lines.append(line)
    
    return '\n'.join(result_lines)


def _extract_setup_deps(content: str) -> str:
    """Extract install_requires and related from setup.py."""
    # Look for install_requires, extras_require patterns
    import re
    
    patterns = [
        r'install_requires\s*=\s*\[[\s\S]*?\]',
        r'extras_require\s*=\s*\{[\s\S]*?\}',
        r'dependencies\s*=\s*\[[\s\S]*?\]',
    ]
    
    matches = []
    for pattern in patterns:
        found = re.findall(pattern, content)
        matches.extend(found)
    
    if matches:
        return '\n\n'.join(matches)
    
    # If no matches, return empty (file might not have deps)
    return ""


def extract_all_chunks(
    repo_path: str,
    quickstart_id: str,
    repo_name: str,
) -> list[ContentChunk]:
    """Extract all indexable content from a repository.
    
    Extracts content from multiple sources:
    - README.md (primary documentation)
    - Helm charts (deployment configuration)
    - Jupyter notebooks (tutorials and examples)
    - Dependency files (libraries and features used)
    
    Args:
        repo_path: Path to cloned repository
        quickstart_id: ID from catalog.yaml
        repo_name: GitHub repo name
    
    Returns:
        List of ContentChunk objects
    """
    chunks = []
    
    # Extract README (primary source)
    chunks.extend(extract_readme_chunks(repo_path, quickstart_id, repo_name))
    
    # Extract Helm charts (deployment details)
    chunks.extend(extract_helm_chunks(repo_path, quickstart_id, repo_name))
    
    # Extract Jupyter notebooks (tutorials with code)
    chunks.extend(extract_notebook_chunks(repo_path, quickstart_id, repo_name))
    
    # Extract dependency/config files (feature signals)
    chunks.extend(extract_dependency_chunks(repo_path, quickstart_id, repo_name))
    
    return chunks
