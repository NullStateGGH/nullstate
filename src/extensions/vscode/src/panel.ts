import * as vscode from 'vscode';
import { MCPClient } from './mcpClient';
import { WalletManager } from './wallet';
import { TaskManager } from './tasks';

export class WorkspacePanel {
  public static currentPanel: vscode.WebviewPanel | undefined;

  static createOrShow(extensionUri: vscode.Uri, wallet: WalletManager, tasks: TaskManager, mcp: MCPClient) {
    if (this.currentPanel) { this.currentPanel.reveal(); return; }
    this.currentPanel = vscode.window.createWebviewPanel('nullstate.workspace', 'NullState Agent Workspace',
      vscode.ViewColumn.Beside, { enableScripts: true, retainContextWhenHidden: true });
    this.currentPanel.webview.html = this.getHtml(extensionUri, this.currentPanel.webview);
    this.currentPanel.onDidDispose(() => { this.currentPanel = undefined; });
  }

  static getHtml(extensionUri: vscode.Uri, webview: vscode.Webview): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
:root { --neon: #00ff9d; --bg: #030303; --surface: #0a0a0a; --gold: #ffd700; --text: #e0e0e0; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 16px; font-size: 13px; }
h1 { font-size: 18px; font-weight: 700; margin-bottom: 16px; color: var(--neon); }
h2 { font-size: 14px; font-weight: 600; margin: 16px 0 8px; text-transform: uppercase; letter-spacing: 1px; color: #666; }
.card { background: var(--surface); border: 1px solid #1a1a1a; border-radius: 8px; padding: 12px; margin-bottom: 8px; }
.card:hover { border-color: var(--neon); }
.stat { display: inline-block; padding: 4px 12px; background: rgba(0,255,157,0.1); border-radius: 4px; color: var(--neon); font-size: 12px; font-weight: 600; margin: 2px; }
.metric { font-size: 24px; font-weight: 700; }
.metric-label { font-size: 11px; color: #666; text-transform: uppercase; }
.btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; border: 1px solid #333; background: transparent; color: #ccc; margin: 4px; }
.btn:hover { border-color: var(--neon); color: var(--neon); }
.btn-primary { background: var(--neon); color: #000; border-color: var(--neon); }
.btn-primary:hover { background: transparent; color: var(--neon); }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }
pre { background: #0d0d0d; padding: 12px; border-radius: 6px; font-size: 11px; overflow-x: auto; margin: 8px 0; }
</style>
</head>
<body>
<h1>⛓️ NullState</h1>

<div class="grid">
  <div class="card"><div class="metric" id="balance">--</div><div class="metric-label">Balance (USDC)</div></div>
  <div class="card"><div class="metric" id="tasks">--</div><div class="metric-label">Tasks</div></div>
  <div class="card"><div class="metric" id="ledger">--</div><div class="metric-label">Ledger Entries</div></div>
  <div class="card"><div class="metric" id="agents">--</div><div class="metric-label">Connected Agents</div></div>
</div>

<h2>Actions</h2>
<div>
  <button class="btn btn-primary" onclick="createTask()">+ Create Task</button>
  <button class="btn" onclick="connectMCP()">🔌 MCP Connect</button>
  <button class="btn" onclick="runHandshake()">🤝 AP2 Demo</button>
  <button class="btn" onclick="refresh()">🔄 Refresh</button>
</div>

<h2>Task Queue</h2>
<div id="taskList"><div class="card" style="color:#555">No tasks yet. Create one to start.</div></div>

<h2>Connected MCP Servers</h2>
<div id="mcpList"><div class="card" style="color:#555">No MCP servers connected.</div></div>

<pre id="log">[NullState] Ready. No limits, no state.</pre>

<script>
const vscode = acquireVsCodeApi();

function refresh() {
  vscode.postMessage({ command: 'getIntelligence' });
  vscode.postMessage({ command: 'getTasks' });
  vscode.postMessage({ command: 'getMCPs' });
}

function createTask() {
  vscode.postMessage({ command: 'createTask' });
}

function connectMCP() {
  vscode.postMessage({ command: 'connectMCP' });
}

function runHandshake() {
  vscode.postMessage({ command: 'runAP2' });
}

window.addEventListener('message', event => {
  const msg = event.data;
  if (msg.command === 'intelligence') {
    document.getElementById('balance').textContent = msg.data.balance;
    document.getElementById('tasks').textContent = msg.data.tasks;
    document.getElementById('ledger').textContent = msg.data.ledger_entries;
    document.getElementById('agents').textContent = msg.data.wallet ? '1' : '0';
  }
  if (msg.command === 'tasks') {
    const list = document.getElementById('taskList');
    if (!msg.data || msg.data.length === 0) {
      list.innerHTML = '<div class="card" style="color:#555">No tasks.</div>';
    } else {
      list.innerHTML = msg.data.map(t => '<div class="card">' + t.id + ' <span class="stat">' + t.status + '</span><br><span style="color:#777">' + (t.source || '') + '</span></div>').join('');
    }
  }
  if (msg.command === 'log') {
    const log = document.getElementById('log');
    log.textContent = '[NullState] ' + msg.text + '\\n' + log.textContent.split('\\n').slice(0, 49).join('\\n');
  }
});

// Auto-refresh on load
refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>`;
  }
}
