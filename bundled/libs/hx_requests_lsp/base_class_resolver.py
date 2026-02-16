"""Resolver for finding base class file locations."""

import ast
from functools import lru_cache
from pathlib import Path

from hx_requests_lsp.python_parser import BaseClassInfo


@lru_cache(maxsize=1)
def _find_hx_requests_package_path() -> Path | None:
    """Find the installed hx-requests package location."""
    try:
        import hx_requests

        return Path(hx_requests.__file__).parent
    except ImportError:
        return None


@lru_cache(maxsize=256)
def _parse_file_for_classes(file_path: str) -> dict[str, int]:
    """Parse a Python file and return a map of class names to line numbers."""
    try:
        source = Path(file_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError, OSError):
        return {}

    classes = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes[node.name] = node.lineno
    return classes


def _find_class_in_module(module_path: Path, class_name: str) -> tuple[str, int] | None:
    """Find a class definition in a module file or package."""
    if module_path.is_file():
        classes = _parse_file_for_classes(str(module_path))
        if class_name in classes:
            return (str(module_path), classes[class_name])

    elif module_path.is_dir():
        init_file = module_path / "__init__.py"
        if init_file.exists():
            classes = _parse_file_for_classes(str(init_file))
            if class_name in classes:
                return (str(init_file), classes[class_name])

        for py_file in module_path.glob("*.py"):
            classes = _parse_file_for_classes(str(py_file))
            if class_name in classes:
                return (str(py_file), classes[class_name])

    return None


@lru_cache(maxsize=64)
def _find_class_in_hx_requests_package(class_name: str) -> tuple[str, int] | None:
    """Find a class in the hx-requests package (cached for performance)."""
    hx_pkg_path = _find_hx_requests_package_path()
    if not hx_pkg_path:
        return None

    for py_file in hx_pkg_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        classes = _parse_file_for_classes(str(py_file))
        if class_name in classes:
            return (str(py_file.resolve()), classes[class_name])

    return None


def resolve_base_class(
    class_name: str,
    source_file: str,
    imports: dict[str, str],
    workspace_root: str | None = None,
) -> BaseClassInfo:
    """
    Resolve a base class name to its file location.

    Resolution priority:
    1. Same file
    2. hx-requests library
    3. Workspace imports
    """
    source_path = Path(source_file)

    # 1. Check if class is defined in the same file
    classes = _parse_file_for_classes(source_file)
    if class_name in classes:
        return BaseClassInfo(
            name=class_name,
            file_path=str(source_path.resolve()),
            line_number=classes[class_name],
        )

    # 2. Check if it's from hx-requests library (cached)
    hx_result = _find_class_in_hx_requests_package(class_name)
    if hx_result:
        return BaseClassInfo(
            name=class_name,
            file_path=hx_result[0],
            line_number=hx_result[1],
        )

    # 3. Check imports and try to resolve from workspace
    if class_name in imports and workspace_root:
        module_path_str = imports[class_name]
        module_parts = module_path_str.split(".")
        workspace = Path(workspace_root)

        possible_paths = [
            workspace / "/".join(module_parts) / "__init__.py",
            workspace / ("/".join(module_parts) + ".py"),
        ]
        if len(module_parts) > 1:
            possible_paths.append(workspace / "/".join(module_parts[:-1]) / (module_parts[-1] + ".py"))

        for path in possible_paths:
            if path.exists():
                result = _find_class_in_module(
                    path.parent if path.name == "__init__.py" else path, class_name
                )
                if result:
                    return BaseClassInfo(
                        name=class_name,
                        file_path=result[0],
                        line_number=result[1],
                    )

    return BaseClassInfo(name=class_name, file_path=None, line_number=None)


def resolve_all_base_classes(
    base_class_names: list[str],
    source_file: str,
    imports: dict[str, str],
    workspace_root: str | None = None,
) -> list[BaseClassInfo]:
    """Resolve all base classes for an HxRequest definition."""
    return [resolve_base_class(name, source_file, imports, workspace_root) for name in base_class_names]
