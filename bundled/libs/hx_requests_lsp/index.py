"""Index manager for caching and looking up hx_request definitions and usages."""

import logging
import threading
from pathlib import Path

from hx_requests_lsp.python_parser import (
    HxRequestDefinition,
    collect_all_hx_requests,
    find_hx_request_files,
    parse_hx_requests_from_file,
    parse_hx_requests_from_source,
)
from hx_requests_lsp.template_parser import (
    HxRequestUsage,
    collect_all_usages,
    find_template_files,
    parse_template_file,
    parse_template_for_hx_requests,
)

logger = logging.getLogger(__name__)


class HxRequestIndex:
    """Manages an index of hx_request definitions and usages.

    This class maintains a cache of all hx_request definitions (from Python files)
    and their usages (from Django templates) for efficient lookup during LSP
    operations.
    """

    def __init__(self, workspace_root: str | Path | None = None):
        """Initialize the index.

        Args:
            workspace_root: Root directory of the workspace to index
        """
        self._workspace_root = Path(workspace_root) if workspace_root else None
        self._lock = threading.RLock()

        # Maps hx_request name -> definition
        self._definitions: dict[str, HxRequestDefinition] = {}

        # Maps hx_request name -> list of usages
        self._usages: dict[str, list[HxRequestUsage]] = {}

        # Maps file path -> list of definitions in that file
        self._definitions_by_file: dict[str, list[HxRequestDefinition]] = {}

        # Maps file path -> list of usages in that file
        self._usages_by_file: dict[str, list[HxRequestUsage]] = {}

        # Track indexed files for incremental updates
        self._indexed_python_files: set[str] = set()
        self._indexed_template_files: set[str] = set()

    @property
    def workspace_root(self) -> Path | None:
        return self._workspace_root

    @workspace_root.setter
    def workspace_root(self, value: str | Path | None):
        self._workspace_root = Path(value) if value else None

    def build_full_index(self) -> None:
        """Build the complete index from the workspace root.

        This scans all hx_requests.py files and template files to build
        the initial index.
        """
        if not self._workspace_root:
            logger.warning("No workspace root set, cannot build index")
            return

        logger.info(f"Building full index from {self._workspace_root}")

        with self._lock:
            # Clear existing index
            self._definitions.clear()
            self._usages.clear()
            self._definitions_by_file.clear()
            self._usages_by_file.clear()
            self._indexed_python_files.clear()
            self._indexed_template_files.clear()

            # Index Python files
            for file_path in find_hx_request_files(self._workspace_root):
                self._index_python_file(file_path)

            # Index template files
            for file_path in find_template_files(self._workspace_root):
                self._index_template_file(file_path)

        logger.info(
            f"Index built: {len(self._definitions)} definitions, "
            f"{sum(len(u) for u in self._usages.values())} usages"
        )

    def _index_python_file(self, file_path: Path) -> None:
        """Index a single Python file.

        Args:
            file_path: Path to the Python file
        """
        file_path_str = str(file_path.resolve())

        definitions = parse_hx_requests_from_file(file_path, self._workspace_root)

        self._definitions_by_file[file_path_str] = definitions
        self._indexed_python_files.add(file_path_str)

        for definition in definitions:
            self._definitions[definition.name] = definition

    def _index_template_file(self, file_path: Path) -> None:
        """Index a single template file.

        Args:
            file_path: Path to the template file
        """
        file_path_str = str(file_path.resolve())

        usages = parse_template_file(file_path)

        self._usages_by_file[file_path_str] = usages
        self._indexed_template_files.add(file_path_str)

        for usage in usages:
            if usage.name not in self._usages:
                self._usages[usage.name] = []
            self._usages[usage.name].append(usage)

    def update_file(self, file_path: str | Path, content: str | None = None) -> None:
        """Update the index for a single file.

        This is called when a file is modified to update the index incrementally.

        Args:
            file_path: Path to the modified file
            content: Optional content of the file (if None, reads from disk)
        """
        file_path = Path(file_path)
        file_path_str = str(file_path.resolve())

        with self._lock:
            if file_path.suffix == ".py":
                self._update_python_file(file_path, file_path_str, content)
            elif file_path.suffix == ".html":
                self._update_template_file(file_path, file_path_str, content)

    def _update_python_file(self, file_path: Path, file_path_str: str, content: str | None) -> None:
        """Update index for a Python file."""
        old_definitions = self._definitions_by_file.get(file_path_str, [])
        for old_def in old_definitions:
            if old_def.name in self._definitions:
                if self._definitions[old_def.name].file_path == file_path_str:
                    del self._definitions[old_def.name]

        if content is not None:
            definitions = parse_hx_requests_from_source(content, file_path_str, self._workspace_root)
        else:
            definitions = parse_hx_requests_from_file(file_path, self._workspace_root)

        self._definitions_by_file[file_path_str] = definitions
        self._indexed_python_files.add(file_path_str)

        for definition in definitions:
            self._definitions[definition.name] = definition

    def _update_template_file(self, file_path: Path, file_path_str: str, content: str | None) -> None:
        """Update index for a template file."""
        # Remove old usages from this file
        old_usages = self._usages_by_file.get(file_path_str, [])
        for old_usage in old_usages:
            if old_usage.name in self._usages:
                self._usages[old_usage.name] = [
                    u for u in self._usages[old_usage.name] if u.file_path != file_path_str
                ]
                if not self._usages[old_usage.name]:
                    del self._usages[old_usage.name]

        # Parse new usages
        if content is not None:
            usages = parse_template_for_hx_requests(content, file_path_str)
        else:
            usages = parse_template_file(file_path)

        # Update index
        self._usages_by_file[file_path_str] = usages
        self._indexed_template_files.add(file_path_str)

        for usage in usages:
            if usage.name not in self._usages:
                self._usages[usage.name] = []
            self._usages[usage.name].append(usage)

    def remove_file(self, file_path: str | Path) -> None:
        """Remove a file from the index.

        Args:
            file_path: Path to the removed file
        """
        file_path = Path(file_path)
        file_path_str = str(file_path.resolve())

        with self._lock:
            if file_path_str in self._indexed_python_files:
                old_definitions = self._definitions_by_file.get(file_path_str, [])
                for old_def in old_definitions:
                    if old_def.name in self._definitions:
                        if self._definitions[old_def.name].file_path == file_path_str:
                            del self._definitions[old_def.name]
                self._definitions_by_file.pop(file_path_str, None)
                self._indexed_python_files.discard(file_path_str)

            if file_path_str in self._indexed_template_files:
                old_usages = self._usages_by_file.get(file_path_str, [])
                for old_usage in old_usages:
                    if old_usage.name in self._usages:
                        self._usages[old_usage.name] = [
                            u for u in self._usages[old_usage.name] if u.file_path != file_path_str
                        ]
                        if not self._usages[old_usage.name]:
                            del self._usages[old_usage.name]
                self._usages_by_file.pop(file_path_str, None)
                self._indexed_template_files.discard(file_path_str)

    def get_definition(self, name: str) -> HxRequestDefinition | None:
        """Get the definition of an hx_request by name.

        Args:
            name: The hx_request name

        Returns:
            The definition if found, None otherwise
        """
        with self._lock:
            return self._definitions.get(name)

    def get_usages(self, name: str) -> list[HxRequestUsage]:
        """Get all usages of an hx_request by name.

        Args:
            name: The hx_request name

        Returns:
            List of usages (may be empty)
        """
        with self._lock:
            return list(self._usages.get(name, []))

    def get_all_definition_names(self) -> list[str]:
        """Get all known hx_request names.

        Returns:
            Sorted list of all hx_request names
        """
        with self._lock:
            return sorted(self._definitions.keys())

    def get_definitions_sorted_by_relevance(
        self, current_file: str | Path | None = None
    ) -> list[HxRequestDefinition]:
        """Get all definitions sorted by relevance to the current file.

        Definitions from the same app (directory) as the current file come first,
        then the rest are sorted alphabetically.

        Args:
            current_file: Path to the current file being edited

        Returns:
            List of definitions sorted by relevance
        """
        with self._lock:
            all_defs = list(self._definitions.values())

            if not current_file:
                return sorted(all_defs, key=lambda d: d.name)

            current_path = Path(current_file).resolve()
            current_app = self._extract_app_name(current_path)

            def sort_key(definition: HxRequestDefinition) -> tuple[int, str]:
                def_app = self._extract_app_name(Path(definition.file_path))
                is_same_app = 0 if def_app == current_app else 1
                return (is_same_app, definition.name)

            return sorted(all_defs, key=sort_key)

    def _extract_app_name(self, file_path: Path) -> str | None:
        """Extract the Django app name from a file path.

        Looks for common patterns like:
        - /app_name/hx_requests/...
        - /app_name/templates/...
        - /app_name/template_partials/...

        Args:
            file_path: Path to the file

        Returns:
            App name or None if not determinable
        """
        parts = file_path.parts
        for i, part in enumerate(parts):
            if part in ("hx_requests", "templates", "template_partials") and i > 0:
                return parts[i - 1]
        return None

    def get_all_definitions(self) -> list[HxRequestDefinition]:
        """Get all hx_request definitions.

        Returns:
            List of all definitions
        """
        with self._lock:
            return list(self._definitions.values())

    def get_definitions_in_file(self, file_path: str | Path) -> list[HxRequestDefinition]:
        """Get all definitions in a specific file.

        Args:
            file_path: Path to the Python file

        Returns:
            List of definitions in that file
        """
        file_path_str = str(Path(file_path).resolve())
        with self._lock:
            return list(self._definitions_by_file.get(file_path_str, []))

    def get_usages_in_file(self, file_path: str | Path) -> list[HxRequestUsage]:
        """Get all usages in a specific file.

        Args:
            file_path: Path to the template file

        Returns:
            List of usages in that file
        """
        file_path_str = str(Path(file_path).resolve())
        with self._lock:
            return list(self._usages_by_file.get(file_path_str, []))

    def find_undefined_usages(self) -> list[HxRequestUsage]:
        """Find all usages that reference undefined hx_requests.

        Returns:
            List of usages that don't have corresponding definitions
        """
        with self._lock:
            undefined = []
            for name, usages in self._usages.items():
                if name not in self._definitions:
                    undefined.extend(usages)
            return undefined

    def find_unused_definitions(self) -> list[HxRequestDefinition]:
        """Find all definitions that are never used.

        Returns:
            List of definitions with no usages
        """
        with self._lock:
            unused = []
            for name, definition in self._definitions.items():
                if name not in self._usages or not self._usages[name]:
                    unused.append(definition)
            return unused
