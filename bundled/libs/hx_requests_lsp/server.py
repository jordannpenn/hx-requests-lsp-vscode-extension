"""hx-requests Language Server implementation using pygls."""

import logging
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from lsprotocol import types as lsp
from pygls.server import LanguageServer

from hx_requests_lsp.index import HxRequestIndex
from hx_requests_lsp.template_parser import get_hx_request_name_at_position

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HxRequestsLanguageServer(LanguageServer):
    """Language Server for hx-requests Django library."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.index = HxRequestIndex()

    def uri_to_path(self, uri: str) -> str:
        """Convert a URI to a file path."""
        parsed = urlparse(uri)
        return unquote(parsed.path)


# Create the server instance
server = HxRequestsLanguageServer("hx-requests-lsp", "v0.1.0")


@server.feature(lsp.INITIALIZE)
def initialize(ls: HxRequestsLanguageServer, params: lsp.InitializeParams):
    """Handle initialization request."""
    logger.info(f"Initializing hx-requests LSP with params: {params.root_uri}")

    if params.root_uri:
        ls.index.workspace_root = ls.uri_to_path(params.root_uri)
    elif params.root_path:
        ls.index.workspace_root = params.root_path

    return lsp.InitializeResult(
        capabilities=lsp.ServerCapabilities(
            text_document_sync=lsp.TextDocumentSyncOptions(
                open_close=True,
                change=lsp.TextDocumentSyncKind.Full,
                save=lsp.SaveOptions(include_text=True),
            ),
            completion_provider=lsp.CompletionOptions(
                trigger_characters=["'", '"'],
                resolve_provider=True,
            ),
            definition_provider=True,
            references_provider=True,
            hover_provider=True,
            diagnostic_provider=lsp.DiagnosticOptions(
                inter_file_dependencies=True,
                workspace_diagnostics=False,
            ),
        ),
        server_info=lsp.ServerInfo(
            name="hx-requests-lsp",
            version="0.1.0",
        ),
    )


@server.feature(lsp.INITIALIZED)
def initialized(ls: HxRequestsLanguageServer, params: lsp.InitializedParams):
    """Handle initialized notification - build the index."""
    logger.info("Server initialized, building index...")
    ls.index.build_full_index()
    logger.info(f"Index built with {len(ls.index.get_all_definition_names())} definitions")


@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: HxRequestsLanguageServer, params: lsp.DidOpenTextDocumentParams):
    """Handle document open event."""
    file_path = ls.uri_to_path(params.text_document.uri)
    logger.debug(f"Document opened: {file_path}")

    # Update index with the opened file
    ls.index.update_file(file_path, params.text_document.text)

    # Publish diagnostics for the opened file
    _publish_diagnostics(ls, params.text_document.uri, params.text_document.text)


@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: HxRequestsLanguageServer, params: lsp.DidChangeTextDocumentParams):
    """Handle document change event."""
    file_path = ls.uri_to_path(params.text_document.uri)
    content = params.content_changes[0].text if params.content_changes else ""

    # Update index with changed content
    ls.index.update_file(file_path, content)

    # Publish diagnostics
    _publish_diagnostics(ls, params.text_document.uri, content)


@server.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: HxRequestsLanguageServer, params: lsp.DidSaveTextDocumentParams):
    """Handle document save event."""
    file_path = ls.uri_to_path(params.text_document.uri)

    # Update index from saved file
    if params.text:
        ls.index.update_file(file_path, params.text)
    else:
        ls.index.update_file(file_path)


@server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: HxRequestsLanguageServer, params: lsp.DidCloseTextDocumentParams):
    """Handle document close event."""
    # We keep the file in the index, just log it
    logger.debug(f"Document closed: {params.text_document.uri}")


@server.feature(lsp.TEXT_DOCUMENT_COMPLETION)
def completions(ls: HxRequestsLanguageServer, params: lsp.CompletionParams) -> lsp.CompletionList | None:
    """Provide completion items for hx_request names."""
    file_path = ls.uri_to_path(params.text_document.uri)

    # Only provide completions for HTML template files
    if not file_path.endswith(".html"):
        return None

    # Get the current line content
    doc = ls.workspace.get_text_document(params.text_document.uri)
    line = doc.lines[params.position.line] if params.position.line < len(doc.lines) else ""

    # Check if we're in an hx_request context
    if not _is_in_hx_request_context(line, params.position.character):
        return None

    # Build completion items from all known definitions
    items = []
    for name in ls.index.get_all_definition_names():
        definition = ls.index.get_definition(name)
        if definition:
            doc_string = definition.docstring or ""
            detail = f"Class: {definition.class_name}"
            if definition.get_template:
                detail += f"\nTemplate: {definition.get_template}"

            items.append(
                lsp.CompletionItem(
                    label=name,
                    kind=lsp.CompletionItemKind.Reference,
                    detail=detail,
                    documentation=lsp.MarkupContent(
                        kind=lsp.MarkupKind.Markdown,
                        value=f"**{definition.class_name}**\n\n"
                        f"File: `{Path(definition.file_path).name}`\n\n"
                        f"Bases: {', '.join(definition.base_classes)}\n\n"
                        f"{doc_string}",
                    ),
                    insert_text=name,
                )
            )

    return lsp.CompletionList(is_incomplete=False, items=items)


@server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
def definition(
    ls: HxRequestsLanguageServer, params: lsp.DefinitionParams
) -> lsp.Location | list[lsp.Location] | None:
    """Provide go-to-definition for hx_request names."""
    file_path = ls.uri_to_path(params.text_document.uri)

    # Get the word at the cursor position
    doc = ls.workspace.get_text_document(params.text_document.uri)
    line = doc.lines[params.position.line] if params.position.line < len(doc.lines) else ""

    # For template files, look for hx_request name at position
    if file_path.endswith(".html"):
        result = get_hx_request_name_at_position(
            doc.source, params.position.line + 1, params.position.character
        )
        if result:
            name, _, _ = result
            hx_def = ls.index.get_definition(name)
            if hx_def:
                return lsp.Location(
                    uri=f"file://{hx_def.file_path}",
                    range=lsp.Range(
                        start=lsp.Position(line=hx_def.line_number - 1, character=0),
                        end=lsp.Position(line=hx_def.end_line_number - 1, character=0),
                    ),
                )

    # For Python files, check if cursor is on a name = "..." attribute
    elif file_path.endswith(".py"):
        name = _get_hx_name_from_python_line(line, params.position.character)
        if name:
            hx_def = ls.index.get_definition(name)
            if hx_def:
                return lsp.Location(
                    uri=f"file://{hx_def.file_path}",
                    range=lsp.Range(
                        start=lsp.Position(line=hx_def.line_number - 1, character=0),
                        end=lsp.Position(line=hx_def.end_line_number - 1, character=0),
                    ),
                )

    return None


@server.feature(lsp.TEXT_DOCUMENT_REFERENCES)
def references(ls: HxRequestsLanguageServer, params: lsp.ReferenceParams) -> list[lsp.Location] | None:
    """Find all references to an hx_request."""
    file_path = ls.uri_to_path(params.text_document.uri)
    doc = ls.workspace.get_text_document(params.text_document.uri)
    line = doc.lines[params.position.line] if params.position.line < len(doc.lines) else ""

    name = None

    # For template files, get name at cursor
    if file_path.endswith(".html"):
        result = get_hx_request_name_at_position(
            doc.source, params.position.line + 1, params.position.character
        )
        if result:
            name = result[0]

    # For Python files, try to get name from line
    elif file_path.endswith(".py"):
        name = _get_hx_name_from_python_line(line, params.position.character)
        if not name:
            # Also check if we're on the class definition line
            definitions = ls.index.get_definitions_in_file(file_path)
            for hx_def in definitions:
                if hx_def.line_number == params.position.line + 1:
                    name = hx_def.name
                    break

    if not name:
        return None

    # Find all usages
    locations = []
    usages = ls.index.get_usages(name)
    for usage in usages:
        locations.append(
            lsp.Location(
                uri=f"file://{usage.file_path}",
                range=lsp.Range(
                    start=lsp.Position(line=usage.line_number - 1, character=usage.column),
                    end=lsp.Position(line=usage.line_number - 1, character=usage.end_column),
                ),
            )
        )

    # Include definition if requested
    if params.context.include_declaration:
        hx_def = ls.index.get_definition(name)
        if hx_def:
            locations.insert(
                0,
                lsp.Location(
                    uri=f"file://{hx_def.file_path}",
                    range=lsp.Range(
                        start=lsp.Position(line=hx_def.line_number - 1, character=0),
                        end=lsp.Position(line=hx_def.end_line_number - 1, character=0),
                    ),
                ),
            )

    return locations if locations else None


@server.feature(lsp.TEXT_DOCUMENT_HOVER)
def hover(ls: HxRequestsLanguageServer, params: lsp.HoverParams) -> lsp.Hover | None:
    """Provide hover information for hx_request names."""
    file_path = ls.uri_to_path(params.text_document.uri)
    doc = ls.workspace.get_text_document(params.text_document.uri)
    line = doc.lines[params.position.line] if params.position.line < len(doc.lines) else ""

    name = None
    hover_range = None

    # For template files
    if file_path.endswith(".html"):
        result = get_hx_request_name_at_position(
            doc.source, params.position.line + 1, params.position.character
        )
        if result:
            name, start_col, end_col = result
            hover_range = lsp.Range(
                start=lsp.Position(line=params.position.line, character=start_col),
                end=lsp.Position(line=params.position.line, character=end_col),
            )

    # For Python files
    elif file_path.endswith(".py"):
        name = _get_hx_name_from_python_line(line, params.position.character)

    if not name:
        return None

    hx_def = ls.index.get_definition(name)
    if not hx_def:
        return lsp.Hover(
            contents=lsp.MarkupContent(
                kind=lsp.MarkupKind.Markdown,
                value=f"**Unknown hx_request:** `{name}`\n\nNo definition found.",
            ),
            range=hover_range,
        )

    # Build hover content
    usages = ls.index.get_usages(name)
    usage_count = len(usages)

    content = f"""**{hx_def.class_name}**

- **Name:** `{hx_def.name}`
- **File:** `{Path(hx_def.file_path).name}:{hx_def.line_number}`
- **Bases:** {", ".join(hx_def.base_classes)}
- **Usages:** {usage_count} template reference(s)
"""

    if hx_def.get_template:
        content += f"- **GET Template:** `{hx_def.get_template}`\n"
    if hx_def.post_template:
        content += f"- **POST Template:** `{hx_def.post_template}`\n"

    if hx_def.docstring:
        content += f"\n---\n\n{hx_def.docstring}"

    return lsp.Hover(
        contents=lsp.MarkupContent(kind=lsp.MarkupKind.Markdown, value=content),
        range=hover_range,
    )


@server.feature(lsp.TEXT_DOCUMENT_DIAGNOSTIC)
def diagnostics(
    ls: HxRequestsLanguageServer, params: lsp.DocumentDiagnosticParams
) -> lsp.DocumentDiagnosticReport:
    """Provide diagnostics for undefined hx_request usages."""
    file_path = ls.uri_to_path(params.text_document.uri)
    doc = ls.workspace.get_text_document(params.text_document.uri)

    items = _compute_diagnostics(ls, file_path, doc.source)

    return lsp.RelatedFullDocumentDiagnosticReport(
        kind=lsp.DocumentDiagnosticReportKind.Full,
        items=items,
    )


def _publish_diagnostics(ls: HxRequestsLanguageServer, uri: str, content: str):
    """Publish diagnostics for a document."""
    file_path = ls.uri_to_path(uri)
    items = _compute_diagnostics(ls, file_path, content)
    ls.publish_diagnostics(uri, items)


def _compute_diagnostics(
    ls: HxRequestsLanguageServer, file_path: str, content: str
) -> list[lsp.Diagnostic]:
    """Compute diagnostics for a file."""
    diagnostics = []

    # Only check template files for now
    if not file_path.endswith(".html"):
        return diagnostics

    usages = ls.index.get_usages_in_file(file_path)
    for usage in usages:
        if not ls.index.get_definition(usage.name):
            diagnostics.append(
                lsp.Diagnostic(
                    range=lsp.Range(
                        start=lsp.Position(line=usage.line_number - 1, character=usage.column),
                        end=lsp.Position(line=usage.line_number - 1, character=usage.end_column),
                    ),
                    message=f"Unknown hx_request: '{usage.name}'",
                    severity=lsp.DiagnosticSeverity.Warning,
                    source="hx-requests-lsp",
                    code="unknown-hx-request",
                )
            )

    return diagnostics


def _is_in_hx_request_context(line: str, column: int) -> bool:
    """Check if the cursor position is in a context where hx_request completion is relevant."""
    prefix = line[:column]

    # Pattern 1: Right after tag, possibly with opening quote (no content yet)
    # {% hx_post ' or {% hx_post " or {% hx_post (space only)
    after_tag_patterns = [
        r"\{%\s*(hx_post|hx_get|hx_request)\s+['\"]?$",
        r"hx_request_name\s*=\s*['\"]?$",
    ]

    for pattern in after_tag_patterns:
        if re.search(pattern, prefix):
            return True

    # Pattern 2: Inside a quoted string (cursor between quotes or typing partial name)
    # {% hx_post "some_na or {% hx_post 'partial
    inside_quotes_patterns = [
        r"\{%\s*(hx_post|hx_get|hx_request)\s+(['\"])([^'\"]*?)$",
        r"hx_request_name\s*=\s*(['\"])([^'\"]*?)$",
    ]

    for pattern in inside_quotes_patterns:
        if re.search(pattern, prefix):
            return True

    return False


def _get_hx_name_from_python_line(line: str, column: int) -> str | None:
    """Extract hx_request name from a Python line like: name = "some_name"."""
    # Match: name = "..." or name = '...'
    match = re.search(r'name\s*=\s*[\'"]([^\'"]+)[\'"]', line)
    if match:
        name = match.group(1)
        # Check if cursor is within the name string
        start = match.start(1)
        end = match.end(1)
        if start <= column <= end:
            return name
    return None


def main():
    """Run the language server."""
    import argparse

    parser = argparse.ArgumentParser(description="hx-requests Language Server")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport")
    parser.add_argument("--tcp", action="store_true", help="Use TCP transport")
    parser.add_argument("--host", default="127.0.0.1", help="TCP host")
    parser.add_argument("--port", type=int, default=2087, help="TCP port")

    args = parser.parse_args()

    if args.tcp:
        server.start_tcp(args.host, args.port)
    else:
        server.start_io()


if __name__ == "__main__":
    main()
