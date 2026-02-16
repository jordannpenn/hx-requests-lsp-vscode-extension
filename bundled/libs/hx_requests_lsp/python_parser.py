"""Parser for extracting HxRequest class definitions from Python files."""

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BaseClassInfo:
    """Information about a base class including its location."""

    name: str  # Class name (e.g., "BaseHxRequest")
    file_path: str | None  # Absolute path to the file where it's defined
    line_number: int | None  # Line number where it's defined (1-based)

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        if not isinstance(other, BaseClassInfo):
            return False
        return self.name == other.name


@dataclass
class HxRequestDefinition:
    """Represents an HxRequest class definition found in Python code."""

    name: str  # The value of the `name` attribute (e.g., "notes_count")
    class_name: str  # The Python class name (e.g., "NotesCount")
    file_path: str  # Absolute path to the file
    line_number: int  # Line where the class is defined (1-based)
    end_line_number: int  # Line where the class ends (1-based)
    column: int  # Column where the class name starts (0-based)
    base_classes: list[str]  # List of base class names
    base_class_info: list[BaseClassInfo]  # Detailed info about base classes with locations
    docstring: str | None  # Class docstring if present
    get_template: str | None  # Value of GET_template attribute if present
    post_template: str | None  # Value of POST_template attribute if present

    def __hash__(self):
        return hash((self.name, self.file_path, self.line_number))

    def __eq__(self, other):
        if not isinstance(other, HxRequestDefinition):
            return False
        return (
            self.name == other.name
            and self.file_path == other.file_path
            and self.line_number == other.line_number
        )


class HxRequestVisitor(ast.NodeVisitor):
    """AST visitor that finds HxRequest class definitions."""

    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.source_lines = source.splitlines()
        self.definitions: list[HxRequestDefinition] = []
        self._imports: dict[str, str] = {}  # Maps imported names to their sources

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Track imports for base class resolution."""
        if node.module:
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                self._imports[name] = node.module
        self.generic_visit(node)

    @property
    def imports(self) -> dict[str, str]:
        """Return the collected imports mapping class names to modules."""
        return self._imports

    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definitions and check if they are HxRequest subclasses."""
        base_class_names = self._get_base_class_names(node)

        is_hx_request = any(
            base.endswith("HxRequest")
            or base.endswith("HxMixin")
            or base.endswith("Hx")
            or base.endswith("TabsRouter")
            for base in base_class_names
        )

        if is_hx_request:
            hx_name = self._extract_name_attribute(node)
            if hx_name:
                definition = HxRequestDefinition(
                    name=hx_name,
                    class_name=node.name,
                    file_path=self.file_path,
                    line_number=node.lineno,
                    end_line_number=node.end_lineno or node.lineno,
                    column=node.col_offset,
                    base_classes=base_class_names,
                    base_class_info=[],  # Populated later by resolver
                    docstring=ast.get_docstring(node),
                    get_template=self._extract_string_attribute(node, "GET_template"),
                    post_template=self._extract_string_attribute(node, "POST_template"),
                )
                self.definitions.append(definition)

        # Continue visiting nested classes
        self.generic_visit(node)

    def _get_base_class_names(self, node: ast.ClassDef) -> list[str]:
        """Extract base class names from a class definition."""
        names = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                names.append(base.id)
            elif isinstance(base, ast.Attribute):
                # Handle cases like module.ClassName
                names.append(base.attr)
            elif isinstance(base, ast.Subscript):
                # Handle generic types like Generic[T]
                if isinstance(base.value, ast.Name):
                    names.append(base.value.id)
        return names

    def _extract_name_attribute(self, node: ast.ClassDef) -> str | None:
        """Extract the value of the `name` class attribute."""
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "name":
                        if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                            return item.value.value
            elif isinstance(item, ast.AnnAssign):
                if isinstance(item.target, ast.Name) and item.target.id == "name":
                    if (
                        item.value
                        and isinstance(item.value, ast.Constant)
                        and isinstance(item.value.value, str)
                    ):
                        return item.value.value
        return None

    def _extract_string_attribute(self, node: ast.ClassDef, attr_name: str) -> str | None:
        """Extract the value of a string class attribute."""
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == attr_name:
                        if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                            return item.value.value
            elif isinstance(item, ast.AnnAssign):
                if isinstance(item.target, ast.Name) and item.target.id == attr_name:
                    if (
                        item.value
                        and isinstance(item.value, ast.Constant)
                        and isinstance(item.value.value, str)
                    ):
                        return item.value.value
        return None


def parse_hx_requests_from_file(
    file_path: str | Path, workspace_root: str | Path | None = None
) -> list[HxRequestDefinition]:
    """Parse a Python file and extract all HxRequest class definitions.

    Args:
        file_path: Path to the Python file to parse
        workspace_root: Root of workspace for resolving local imports

    Returns:
        List of HxRequestDefinition objects found in the file
    """
    from hx_requests_lsp.base_class_resolver import resolve_all_base_classes

    file_path = Path(file_path)
    if not file_path.exists():
        return []

    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    visitor = HxRequestVisitor(str(file_path.resolve()), source)
    visitor.visit(tree)

    workspace_root_str = str(workspace_root) if workspace_root else None
    for definition in visitor.definitions:
        definition.base_class_info = resolve_all_base_classes(
            definition.base_classes,
            definition.file_path,
            visitor.imports,
            workspace_root_str,
        )

    return visitor.definitions


def parse_hx_requests_from_source(
    source: str, file_path: str = "<string>", workspace_root: str | Path | None = None
) -> list[HxRequestDefinition]:
    """Parse Python source code and extract all HxRequest class definitions.

    Args:
        source: Python source code as a string
        file_path: Virtual file path for error messages
        workspace_root: Root of workspace for resolving local imports

    Returns:
        List of HxRequestDefinition objects found in the source
    """
    from hx_requests_lsp.base_class_resolver import resolve_all_base_classes

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return []

    visitor = HxRequestVisitor(file_path, source)
    visitor.visit(tree)

    workspace_root_str = str(workspace_root) if workspace_root else None
    for definition in visitor.definitions:
        definition.base_class_info = resolve_all_base_classes(
            definition.base_classes,
            definition.file_path,
            visitor.imports,
            workspace_root_str,
        )

    return visitor.definitions


def find_hx_request_files(root_dir: str | Path) -> list[Path]:
    """Find all Python files that likely contain HxRequest definitions.

    Args:
        root_dir: Root directory to search

    Returns:
        List of paths to Python files named hx_requests.py or in hx_requests/ directories
    """
    root_dir = Path(root_dir)
    files = []

    # Find files named hx_requests.py
    files.extend(root_dir.rglob("hx_requests.py"))

    # Find Python files in hx_requests/ directories
    for hx_dir in root_dir.rglob("hx_requests"):
        if hx_dir.is_dir():
            files.extend(hx_dir.rglob("*.py"))

    # Deduplicate and filter out __pycache__ etc
    seen = set()
    result = []
    for f in files:
        if f.resolve() not in seen and "__pycache__" not in str(f):
            seen.add(f.resolve())
            result.append(f)

    return sorted(result)


def collect_all_hx_requests(root_dir: str | Path) -> dict[str, HxRequestDefinition]:
    """Collect all HxRequest definitions from a project directory.

    Args:
        root_dir: Root directory of the project

    Returns:
        Dictionary mapping HxRequest names to their definitions
    """
    definitions: dict[str, HxRequestDefinition] = {}

    for file_path in find_hx_request_files(root_dir):
        for definition in parse_hx_requests_from_file(file_path):
            # Note: Later definitions with the same name will override earlier ones
            definitions[definition.name] = definition

    return definitions
