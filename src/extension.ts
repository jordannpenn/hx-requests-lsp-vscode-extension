import * as path from 'path';
import * as fs from 'fs';
import {
    workspace,
    ExtensionContext,
    window,
    commands,
    OutputChannel,
    WorkspaceConfiguration,
    extensions,
} from 'vscode';

import {
    LanguageClient,
    LanguageClientOptions,
    ServerOptions,
    TransportKind,
} from 'vscode-languageclient/node';

let client: LanguageClient | undefined;
let outputChannel: OutputChannel;

export async function activate(context: ExtensionContext): Promise<void> {
    outputChannel = window.createOutputChannel('hx-requests LSP');
    outputChannel.appendLine('hx-requests LSP extension activating...');

    const config = workspace.getConfiguration('hxRequestsLsp');
    
    if (!config.get<boolean>('enable', true)) {
        outputChannel.appendLine('Extension is disabled via configuration');
        return;
    }

    // Register restart command
    context.subscriptions.push(
        commands.registerCommand('hxRequestsLsp.restart', async () => {
            outputChannel.appendLine('Restarting language server...');
            if (client) {
                await client.stop();
            }
            await startLanguageServer(context);
        })
    );

    await startLanguageServer(context);
}

async function startLanguageServer(context: ExtensionContext): Promise<void> {
    const config = workspace.getConfiguration('hxRequestsLsp');
    
    // Try to find the server executable
    const serverPath = await findServerPath(config);
    
    if (!serverPath) {
        window.showErrorMessage(
            'hx-requests LSP: Could not find the language server. ' +
            'Please install it with: pip install hx-requests-lsp'
        );
        return;
    }

    outputChannel.appendLine(`Using server: ${serverPath}`);

    // Determine how to run the server
    const serverOptions: ServerOptions = await createServerOptions(serverPath, config, context);

    // Options to control the language client
    const clientOptions: LanguageClientOptions = {
        // Register the server for HTML and Python files
        documentSelector: [
            { scheme: 'file', language: 'html' },
            { scheme: 'file', language: 'django-html' },
            { scheme: 'file', language: 'python' },
        ],
        synchronize: {
            // Notify the server about file changes to relevant files
            fileEvents: [
                workspace.createFileSystemWatcher('**/hx_requests.py'),
                workspace.createFileSystemWatcher('**/hx_requests/**/*.py'),
                workspace.createFileSystemWatcher('**/templates/**/*.html'),
                workspace.createFileSystemWatcher('**/template_partials/**/*.html'),
            ],
        },
        outputChannel: outputChannel,
        traceOutputChannel: outputChannel,
    };

    // Create the language client
    client = new LanguageClient(
        'hxRequestsLsp',
        'hx-requests Language Server',
        serverOptions,
        clientOptions
    );

    // Start the client (also starts the server)
    outputChannel.appendLine('Starting language client...');
    
    try {
        await client.start();
        outputChannel.appendLine('Language client started successfully');
    } catch (error) {
        outputChannel.appendLine(`Failed to start language client: ${error}`);
        window.showErrorMessage(`hx-requests LSP failed to start: ${error}`);
    }

    context.subscriptions.push(client);
}

async function findServerPath(config: WorkspaceConfiguration): Promise<string | null> {
    // 1. Check if explicitly configured
    const configuredPath = config.get('serverPath', '');
    if (configuredPath) {
        if (fs.existsSync(configuredPath)) {
            return configuredPath;
        }
        outputChannel.appendLine(`Configured server path not found: ${configuredPath}`);
    }

    // 2. Try to find in workspace's virtual environment
    const workspaceFolders = workspace.workspaceFolders;
    if (workspaceFolders) {
        for (const folder of workspaceFolders) {
            const venvPaths = [
                path.join(folder.uri.fsPath, '.venv', 'bin', 'hx-requests-lsp'),
                path.join(folder.uri.fsPath, 'venv', 'bin', 'hx-requests-lsp'),
                path.join(folder.uri.fsPath, '.venv', 'Scripts', 'hx-requests-lsp.exe'),
                path.join(folder.uri.fsPath, 'venv', 'Scripts', 'hx-requests-lsp.exe'),
            ];
            
            for (const venvPath of venvPaths) {
                if (fs.existsSync(venvPath)) {
                    outputChannel.appendLine(`Found server in virtual environment: ${venvPath}`);
                    return venvPath;
                }
            }
        }
    }

    // 3. Try to use Python to run the module
    const pythonPath = await findPythonPath(config);
    if (pythonPath) {
        // Check if the module is installed
        try {
            const { execSync } = require('child_process');
            execSync(`"${pythonPath}" -c "import hx_requests_lsp"`, { stdio: 'pipe' });
            outputChannel.appendLine(`Found hx_requests_lsp module, will use: ${pythonPath} -m hx_requests_lsp.server`);
            return pythonPath;
        } catch {
            outputChannel.appendLine('hx_requests_lsp module not found in Python environment');
        }
    }

    // 4. Try system PATH
    try {
        const { execSync } = require('child_process');
        const which = process.platform === 'win32' ? 'where' : 'which';
        const result = execSync(`${which} hx-requests-lsp`, { stdio: 'pipe' }).toString().trim();
        if (result) {
            outputChannel.appendLine(`Found server in PATH: ${result}`);
            return result.split('\n')[0];
        }
    } catch {
        outputChannel.appendLine('hx-requests-lsp not found in PATH');
    }

    return null;
}

async function findPythonPath(config: WorkspaceConfiguration): Promise<string | null> {
    // 1. Check extension configuration
    const configuredPython = config.get('pythonPath', '');
    if (configuredPython && fs.existsSync(configuredPython)) {
        return configuredPython;
    }

    // 2. Try to get from Python extension
    try {
        const pythonExtension = extensions.getExtension('ms-python.python');
        if (pythonExtension) {
            if (!pythonExtension.isActive) {
                await pythonExtension.activate();
            }
            const pythonApi = pythonExtension.exports;
            const envPath = await pythonApi.settings.getExecutionDetails(workspace.workspaceFolders?.[0]?.uri);
            if (envPath?.execCommand?.[0]) {
                outputChannel.appendLine(`Got Python path from Python extension: ${envPath.execCommand[0]}`);
                return envPath.execCommand[0];
            }
        }
    } catch (error) {
        outputChannel.appendLine(`Could not get Python path from extension: ${error}`);
    }

    // 3. Try workspace virtual environments
    const workspaceFolders = workspace.workspaceFolders;
    if (workspaceFolders) {
        for (const folder of workspaceFolders) {
            const venvPaths = [
                path.join(folder.uri.fsPath, '.venv', 'bin', 'python'),
                path.join(folder.uri.fsPath, 'venv', 'bin', 'python'),
                path.join(folder.uri.fsPath, '.venv', 'Scripts', 'python.exe'),
                path.join(folder.uri.fsPath, 'venv', 'Scripts', 'python.exe'),
            ];
            
            for (const venvPath of venvPaths) {
                if (fs.existsSync(venvPath)) {
                    return venvPath;
                }
            }
        }
    }

    // 4. Fall back to system python
    return 'python';
}

function isPythonInterpreter(executablePath: string): boolean {
    const baseName = path.basename(executablePath).toLowerCase();
    return [
        'python',
        'python3',
        'python.exe',
        'python3.exe',
    ].includes(baseName);
}

async function createServerOptions(
    serverPath: string,
    config: WorkspaceConfiguration,
    context: ExtensionContext
): Promise<ServerOptions> {
    // Try bundled LSP first
    const bundledLibsPath = context.asAbsolutePath(path.join('bundled', 'libs'));
    const useBundled = fs.existsSync(path.join(bundledLibsPath, 'hx_requests_lsp'));

    // Check if serverPath is a Python interpreter or executable
    const isPython = isPythonInterpreter(serverPath);

    if (useBundled) {
        outputChannel.appendLine(`Using bundled LSP from: ${bundledLibsPath}`);
        
        const pythonCommand = (await findPythonPath(config)) ?? 'python';
        
        return {
            command: pythonCommand,
            args: ['-m', 'hx_requests_lsp.server', '--stdio'],
            options: {
                env: {
                    ...process.env,
                    PYTHONPATH: bundledLibsPath,
                },
            },
            transport: TransportKind.stdio,
        };
    }

    if (isPython) {
        return {
            command: serverPath,
            args: ['-m', 'hx_requests_lsp.server', '--stdio'],
            transport: TransportKind.stdio,
        };
    }

    // It's the direct executable
    return {
        command: serverPath,
        args: ['--stdio'],
        transport: TransportKind.stdio,
    };
}

export async function deactivate(): Promise<void> {
    if (client) {
        await client.stop();
    }
}
