"""Parser for finding hx_request usages in Django templates."""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HxRequestUsage:
    """Represents a usage of an hx_request in a Django template."""

    name: str  # The hx_request name used (e.g., "notes_count")
    file_path: str  # Absolute path to the template file
    line_number: int  # Line where the usage is found (1-based)
    column: int  # Column where the name starts (0-based)
    end_column: int  # Column where the name ends (0-based)
    tag_type: str  # Type of tag: "hx_post", "hx_vals", "hx_request", "hx_get"
    full_match: str  # The full matched template tag content

    def __hash__(self):
        return hash((self.name, self.file_path, self.line_number, self.column))

    def __eq__(self, other):
        if not isinstance(other, HxRequestUsage):
            return False
        return (
            self.name == other.name
            and self.file_path == other.file_path
            and self.line_number == other.line_number
            and self.column == other.column
        )


# Regex patterns for different hx_request template tag usages
# Matches: {% hx_post 'name' ... %}, {% hx_post "name" ... %}, {% hx_post name ... %}
# Also matches: {% hx_vals hx_request_name='name' ... %}

# Pattern for hx_post, hx_get, hx_request tags with name as first argument
HX_TAG_PATTERN = re.compile(
    r"""\{%\s*                           # Opening tag
    (hx_post|hx_get|hx_request)          # Tag name (captured)
    \s+                                   # Whitespace
    (?:
        ['"]([^'"]+)['"]                  # Quoted string name (captured)
        |
        ([a-zA-Z_][a-zA-Z0-9_.]*)         # Variable name (captured)
    )
    """,
    re.VERBOSE,
)

# Pattern for hx_vals with hx_request_name keyword argument
HX_VALS_PATTERN = re.compile(
    r"""\{%\s*                           # Opening tag
    hx_vals                              # Tag name
    \s+                                   # Whitespace
    .*?                                   # Any content before
    hx_request_name\s*=\s*               # Keyword argument
    (?:
        ['"]([^'"]+)['"]                  # Quoted string name (captured)
        |
        ([a-zA-Z_][a-zA-Z0-9_.]*)         # Variable name (captured)
    )
    """,
    re.VERBOSE | re.DOTALL,
)

# Pattern specifically for finding the hx_request name within any tag
# This helps with go-to-definition by finding exact positions
HX_NAME_IN_TAG = re.compile(
    r"""
    (?:
        # hx_post/hx_get/hx_request 'name' or "name"
        (?:hx_post|hx_get|hx_request)\s+['"]([^'"]+)['"]
        |
        # hx_vals ... hx_request_name='name' or ="name"
        hx_request_name\s*=\s*['"]([^'"]+)['"]
    )
    """,
    re.VERBOSE,
)


def parse_template_for_hx_requests(content: str, file_path: str = "<string>") -> list[HxRequestUsage]:
    """Parse a Django template and find all hx_request usages.

    Args:
        content: Template content as a string
        file_path: Path to the template file (for position information)

    Returns:
        List of HxRequestUsage objects found in the template
    """
    usages: list[HxRequestUsage] = []
    lines = content.splitlines()

    for line_num, line in enumerate(lines, start=1):
        # Find hx_post, hx_get, hx_request tags
        for match in HX_TAG_PATTERN.finditer(line):
            tag_type = match.group(1)
            name = match.group(2) or match.group(3)  # Quoted or unquoted name

            if name:
                # Skip variable references (containing dots or starting with view.)
                if "." in name and not name.startswith("view."):
                    # It's a variable reference like some_var.name, skip it
                    pass
                elif name.startswith("view."):
                    # It's a view attribute reference, we could potentially resolve it
                    # For now, skip it
                    pass
                else:
                    # Find the exact position of the name in the line
                    name_start = _find_name_position(line, match.start(), name)
                    usages.append(
                        HxRequestUsage(
                            name=name,
                            file_path=file_path,
                            line_number=line_num,
                            column=name_start,
                            end_column=name_start + len(name),
                            tag_type=tag_type,
                            full_match=match.group(0),
                        )
                    )

        # Find hx_vals with hx_request_name
        for match in HX_VALS_PATTERN.finditer(line):
            name = match.group(1) or match.group(2)  # Quoted or unquoted name

            if name and "." not in name:
                # Find the exact position of the name in the line
                name_start = _find_name_position(line, match.start(), name)
                usages.append(
                    HxRequestUsage(
                        name=name,
                        file_path=file_path,
                        line_number=line_num,
                        column=name_start,
                        end_column=name_start + len(name),
                        tag_type="hx_vals",
                        full_match=match.group(0),
                    )
                )

    return usages


def _find_name_position(line: str, search_start: int, name: str) -> int:
    """Find the exact column position of a name within a line.

    Args:
        line: The line of text
        search_start: Position to start searching from
        name: The name to find

    Returns:
        Column position (0-based) of the name
    """
    # Look for quoted version first
    for quote in ["'", '"']:
        quoted_name = f"{quote}{name}{quote}"
        pos = line.find(quoted_name, search_start)
        if pos != -1:
            return pos + 1  # +1 to skip the quote

    # Fall back to unquoted search
    pos = line.find(name, search_start)
    return pos if pos != -1 else search_start


def parse_template_file(file_path: str | Path) -> list[HxRequestUsage]:
    """Parse a Django template file and find all hx_request usages.

    Args:
        file_path: Path to the template file

    Returns:
        List of HxRequestUsage objects found in the template
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return []

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    return parse_template_for_hx_requests(content, str(file_path.resolve()))


def find_template_files(root_dir: str | Path) -> list[Path]:
    """Find all Django template files in a directory.

    Args:
        root_dir: Root directory to search

    Returns:
        List of paths to template files (.html)
    """
    root_dir = Path(root_dir)
    templates = []

    # Find .html files in templates/ and template_partials/ directories
    for pattern in ["**/templates/**/*.html", "**/template_partials/**/*.html"]:
        templates.extend(root_dir.glob(pattern))

    # Deduplicate
    seen = set()
    result = []
    for f in templates:
        if f.resolve() not in seen and "__pycache__" not in str(f):
            seen.add(f.resolve())
            result.append(f)

    return sorted(result)


def collect_all_usages(root_dir: str | Path) -> dict[str, list[HxRequestUsage]]:
    """Collect all hx_request usages from template files in a project.

    Args:
        root_dir: Root directory of the project

    Returns:
        Dictionary mapping hx_request names to lists of usages
    """
    usages: dict[str, list[HxRequestUsage]] = {}

    for file_path in find_template_files(root_dir):
        for usage in parse_template_file(file_path):
            if usage.name not in usages:
                usages[usage.name] = []
            usages[usage.name].append(usage)

    return usages


def get_hx_request_name_at_position(content: str, line: int, column: int) -> tuple[str, int, int] | None:
    """Get the hx_request name at a specific position in template content.

    Args:
        content: Template content
        line: Line number (1-based)
        column: Column number (0-based)

    Returns:
        Tuple of (name, start_column, end_column) or None if not found
    """
    lines = content.splitlines()
    if line < 1 or line > len(lines):
        return None

    line_content = lines[line - 1]

    # Find all usages on this line
    usages = parse_template_for_hx_requests(line_content, "<cursor>")

    for usage in usages:
        # Adjust for this being a single line (line_number will be 1)
        if usage.column <= column < usage.end_column:
            return (usage.name, usage.column, usage.end_column)

    return None
