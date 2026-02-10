# hx-requests-lsp VS Code Extension

VS Code extension that provides Language Server Protocol support for the [hx-requests](https://github.com/yaakovLowworworthy/hx-requests) Django library.

## Features

- **Autocomplete**: Get suggestions for hx_request names in Django templates
- **Go-to-Definition**: Jump from template usage to the Python class definition (Ctrl/Cmd + Click)
- **Find References**: Find all template usages of an hx_request
- **Diagnostics**: Warnings for undefined hx_request names
- **Hover Information**: View details about an hx_request on hover

## Prerequisites

1. **Node.js 20+** (for building the extension):
   ```bash
   # Using nvm (recommended)
   nvm install 20
   nvm use 20
   ```

2. **hx-requests-lsp Python package** must be installed in your project:
   ```bash
   # In your project directory (e.g., medicaid-application)
   poetry add hx-requests-lsp --group dev
   ```

## Installation

### Build and Install (one-time setup)

```bash
npm install
npm run package
```

Then install the generated `.vsix` file in VS Code:
- Press `Ctrl+Shift+P`
- Type "Install from VSIX" and select it
- Choose the generated `hx-requests-lsp-*.vsix` file

### For Development

1. Open this folder in VS Code
2. Run `npm install`
3. Press `F5` to launch a new VS Code window with the extension loaded

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `hxRequestsLsp.enable` | `true` | Enable/disable the language server |
| `hxRequestsLsp.serverPath` | `""` | Path to hx-requests-lsp executable (auto-detected if empty) |
| `hxRequestsLsp.pythonPath` | `""` | Path to Python interpreter (auto-detected if empty) |
| `hxRequestsLsp.trace.server` | `"off"` | Trace communication with the server (`off`, `messages`, `verbose`) |

## Server Discovery

The extension automatically looks for the language server in this order:

1. Configured `serverPath` setting
2. Workspace virtual environment (`.venv/bin/hx-requests-lsp` or `venv/bin/hx-requests-lsp`)
3. Python module via configured/detected Python interpreter
4. System PATH

## Commands

- **hx-requests: Restart hx-requests Language Server** - Restart the language server

## Troubleshooting

1. **Server not starting**: Check the "hx-requests LSP" output channel for errors
2. **No completions**: Ensure the LSP package is installed in your project's virtual environment
3. **Wrong Python environment**: Configure `hxRequestsLsp.pythonPath` to point to the correct interpreter

## Development

```bash
# Install dependencies
npm install

# Build the extension
npm run compile

# Package for distribution
npm run package
```
