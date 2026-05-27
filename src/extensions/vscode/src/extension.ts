import * as vscode from 'vscode';
import { MCPClient } from './mcpClient';
import { WorkspacePanel } from './panel';
import { WalletManager } from './wallet';
import { TaskManager } from './tasks';
import { Sandbox } from './sandbox';

let mcpClient: MCPClient;
let wallet: WalletManager;
let tasks: TaskManager;
let sandbox: Sandbox;

export function activate(context: vscode.ExtensionContext) {
  const gatewayUrl = vscode.workspace.getConfiguration('nullstate').get<string>('gatewayUrl')!;

  wallet = new WalletManager(gatewayUrl);
  tasks = new TaskManager(gatewayUrl);
  mcpClient = new MCPClient(gatewayUrl);
  sandbox = new Sandbox();

  context.subscriptions.push(
    vscode.commands.registerCommand('nullstate.openWorkspace', () => {
      WorkspacePanel.createOrShow(context.extensionUri, wallet, tasks, mcpClient);
    }),
    vscode.commands.registerCommand('nullstate.showLedger', async () => {
      const ledger = await mcpClient.getLedger();
      const panel = vscode.window.createOutputChannel('NullState Ledger');
      panel.clear();
      panel.appendLine('=== NullState Revenue Ledger ===\n');
      for (const entry of ledger) {
        panel.appendLine(`${entry.task_id} | ${entry.amount} USDC | ${entry.timestamp}`);
      }
      panel.show();
    }),
    vscode.commands.registerCommand('nullstate.createTask', async () => {
      const source = vscode.window.activeTextEditor?.document.getText() || 'clipboard';
      const task = await tasks.create({ source, type: 'lead', keywords: ['vscode-agent'] });
      vscode.window.showInformationMessage(`NullState: Task ${task.id} created`);
    }),
    vscode.commands.registerCommand('nullstate.connectMCP', async () => {
      const url = await vscode.window.showInputBox({ prompt: 'MCP server URL' });
      if (url) {
        await mcpClient.connectExternal(url);
        vscode.window.showInformationMessage(`NullState: Connected to MCP ${url}`);
      }
    }),
    vscode.commands.registerCommand('nullstate.showWallet', async () => {
      const balance = await wallet.getBalance();
      vscode.window.showInformationMessage(`NullState Wallet: ${balance} USDC`);
    })
  );

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('nullstate.workspace', {
      resolveWebviewView(webviewView) {
        webviewView.webview.html = WorkspacePanel.getHtml(context.extensionUri, webviewView.webview);
        webviewView.webview.onDidReceiveMessage(async (msg) => {
          if (msg.command === 'getIntelligence') {
            webviewView.webview.postMessage({ command: 'intelligence', data: await mcpClient.getIntelligence() });
          }
        });
      }
    })
  );

  // Auto-connect to MCP proxy on startup
  mcpClient.connect().then(() => {
    vscode.window.setStatusBarMessage('NullState: Connected', 3000);
  });

  console.log('[NullState] Extension activated — no limits, no state.');
}

export function deactivate() {
  sandbox.dispose();
  mcpClient.disconnect();
}
