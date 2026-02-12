# hx-requests-lsp VS Code Extension

VS Code extension that provides Language Server Protocol support for the [hx-requests](https://github.com/yaakovLowenstein/hx-requests) Django library.

## Features

- **Autocomplete**: Get suggestions for hx_request names in Django templates (prioritizes current app, works with or without quotes)
- **Go-to-Definition**: Jump from template usage to the Python class definition (Ctrl/Cmd + Click)
- **Find References**: Find all template usages of an hx_request
- **Diagnostics**: Warnings for undefined hx_request names
- **Hover Information**: View details about an hx_request on hover

## Installation

### From VS Code Marketplace (Recommended)

1. Open VS Code
2. Go to Extensions (`Ctrl+Shift+X`)
3. Search for "hx-requests-lsp"
4. Click Install

The extension bundles the language server - no additional installation required.

### From VSIX File

1. Download the `.vsix` file from [Releases](https://github.com/jordannpenn/hx-requests-lsp-vscode-extension/releases)
2. In VS Code, press `Ctrl+Shift+P`
3. Type "Install from VSIX" and select it
4. Choose the downloaded `.vsix` file

## Usage

Once installed, the extension automatically activates for Django projects. Features work in HTML and Django template files:

| Feature | How to Use |
|---------|------------|
| **Go to Definition** | `F12` or `Ctrl+Click` on an hx_request name |
| **Find References** | `Shift+F12` or right-click → "Find All References" |
| **Hover Info** | Hover over an hx_request name |
| **Autocomplete** | Type `{% hx_get ` or `{% hx_post ` (quotes optional) |
| **Diagnostics** | Undefined hx_request names show warnings |

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `hxRequestsLsp.enable` | `true` | Enable/disable the language server |
| `hxRequestsLsp.serverPath` | `""` | Path to hx-requests-lsp executable (auto-detected if empty) |
| `hxRequestsLsp.pythonPath` | `""` | Path to Python interpreter (auto-detected if empty) |
| `hxRequestsLsp.trace.server` | `"off"` | Trace communication with the server (`off`, `messages`, `verbose`) |

## Server Discovery

The extension includes a bundled language server, but can also use an external installation. It looks for the server in this order:

1. Configured `serverPath` setting
2. Bundled server (included with extension)
3. Workspace virtual environment (`.venv/bin/hx-requests-lsp` or `venv/bin/hx-requests-lsp`)
4. Python module via configured/detected Python interpreter
5. System PATH

## Commands

- **hx-requests: Restart hx-requests Language Server** - Restart the language server

## Dev Containers

To include this extension in your dev container, add it to your `devcontainer.json`:

```json
{
  "customizations": {
    "vscode": {
      "extensions": [
        "jordannpenn.hx-requests-lsp"
      ]
    }
  }
}
```

## Troubleshooting

### Server not starting
Check the "hx-requests LSP" output channel for errors (`View` → `Output` → select "hx-requests LSP")

### No completions
1. Ensure your template files have the correct language mode (HTML or Django HTML)
2. Check that your hx_request classes have a `name` attribute
3. Restart the language server: `Ctrl+Shift+P` → "hx-requests: Restart hx-requests Language Server"

### Wrong Python environment
Configure `hxRequestsLsp.pythonPath` in your workspace settings to point to the correct interpreter.

## Development

### Prerequisites

- Node.js 18+
- Python 3.11+

### Setup

```bash
# Clone the repository
git clone https://github.com/jordannpenn/hx-requests-lsp-vscode-extension
cd hx-requests-lsp-vscode-extension

# Install dependencies
npm install

# Build the extension
npm run compile

# Package for distribution
npm run package
```

### Testing Locally

1. Open this folder in VS Code
2. Press `F5` to launch a new VS Code window with the extension loaded
3. Open a Django project to test the features

## Related

- [hx-requests](https://github.com/yaakovLowenstein/hx-requests) - The Django library this extension supports
- [hx-requests-lsp](https://pypi.org/project/hx-requests-lsp/) - The language server (bundled with this extension)

## License

MIT License - see [LICENSE](LICENSE) file for details
