import * as vscode from 'vscode';
import { MCPClient } from './mcpClient';
import { WalletManager } from './wallet';
import { TaskManager } from './tasks';

export class WorkspacePanel {
  public static currentPanel: vscode.WebviewPanel | undefined;

  static createOrShow(extensionUri: vscode.Uri, wallet: WalletManager, tasks: TaskManager, mcp: MCPClient) {
    if (this.currentPanel) { this.currentPanel.reveal(); return; }
    this.currentPanel = vscode.window.createWebviewPanel('nullstate.workspace', 'NullState Agent Workspace',
      vscode.ViewColumn.Beside, { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'media')] });
    this.currentPanel.webview.html = this.getHtml(extensionUri, this.currentPanel.webview);
    this.currentPanel.onDidDispose(() => { this.currentPanel = undefined; });
  }

  static getHtml(extensionUri: vscode.Uri, webview: vscode.Webview): string {
    const verseUri = webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, 'media', 'agent_verse.html'));
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
:root { --neon: #00ff9d; --bg: #030303; --surface: #0a0a0a; --gold: #ffd700; --text: #e0e0e0; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 13px; }
.tabs { display: flex; gap: 0; border-bottom: 1px solid #1a1a1a; background: #050505; }
.tab { padding: 10px 20px; cursor: pointer; font-size: 12px; font-weight: 600; color: #666; border-bottom: 2px solid transparent; transition: all 0.15s; }
.tab:hover { color: var(--neon); }
.tab.active { color: var(--neon); border-bottom-color: var(--neon); }
.panel { display: none; padding: 16px; height: calc(100vh - 42px); overflow-y: auto; }
.panel.active { display: block; }
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
#verse-frame { width: 100%; height: calc(100vh - 50px); border: none; background: var(--bg); }
</style>
</head>
<body>

<div class="tabs">
  <div class="tab active" onclick="switchTab('dashboard')">📊 Dashboard</div>
  <div class="tab" onclick="switchTab('verse')">🌐 Agent Verse</div>
  <div class="tab" onclick="switchTab('tasks')">📋 Tasks</div>
  <div class="tab" onclick="switchTab('growth')">📈 Growth Plan</div>
</div>

<!-- Dashboard Tab -->
<div id="panel-dashboard" class="panel active">
  <h1>⛓️ NullState</h1>
  <div class="grid">
    <div class="card"><div class="metric" id="balance">--</div><div class="metric-label">Balance (USDC)</div></div>
    <div class="card"><div class="metric" id="tasks-count">--</div><div class="metric-label">Tasks</div></div>
    <div class="card"><div class="metric" id="ledger-count">--</div><div class="metric-label">Ledger Entries</div></div>
    <div class="card"><div class="metric" id="agents-count">--</div><div class="metric-label">Connected Agents</div></div>
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
</div>

<!-- Agent Verse Tab -->
<div id="panel-verse" class="panel">
  <iframe id="verse-frame" src="" sandbox="allow-scripts allow-same-origin"></iframe>
</div>

<!-- Tasks Tab -->
<div id="panel-tasks" class="panel">
  <h1>📋 Task Explorer</h1>
  <div id="task-explorer"><div class="card" style="color:#555">Loading...</div></div>
</div>

<!-- Growth Plan Tab -->
<div id="panel-growth" class="panel">
  <h1>📈 NullState Growth Plan</h1>
  <div class="card">
    <h2 style="color:var(--neon);margin-top:0">Current State</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px">
      <div><span class="stat">$70.11</span> <span style="color:#666;font-size:11px">Ledger Balance</span></div>
      <div><span class="stat">1829</span> <span style="color:#666;font-size:11px">Tasks Processed</span></div>
      <div><span class="stat">9/12</span> <span style="color:#666;font-size:11px">Services Running</span></div>
      <div><span class="stat">$0.0107/min</span> <span style="color:#666;font-size:11px">Operating Cost</span></div>
    </div>
  </div>
  <div class="card">
    <h2 style="color:var(--gold);margin-top:0">Phase 1 — Fix the Foundation</h2>
    <div style="color:#888;font-size:12px;line-height:1.8">
      ✅ Resolve HF API DNS (switch to Ollama-only scoring)<br>
      ✅ Diagnose & fix 3 failed services (broker, feedback, global-feedback)<br>
      ✅ Add swap partition (OOM protection for 13GB Ollama)<br>
      ✅ Implement backup rotation cleanup policy (862MB growing unbounded)<br>
      ✅ Squash auto-evolutionary commit noise to meaningful checkpoints
    </div>
  </div>
  <div class="card">
    <h2 style="color:var(--gold);margin-top:0">Phase 2 — Real External Traffic</h2>
    <div style="color:#888;font-size:12px;line-height:1.8">
      🎯 Publish VSCode extension to marketplace (first real distribution channel)<br>
      🎯 Register MCP server in public registry (get_intelligence as free tier)<br>
      🎯 Deploy GitHub Action to marketplace (CI/CD payment settlement)<br>
      🎯 Enable SMTP relay on mail server (2.5B email market)<br>
      🎯 KYA token as API key product (sell agent identity verification)
    </div>
  </div>
  <div class="card">
    <h2 style="color:var(--gold);margin-top:0">Phase 3 — Revenue Scaling</h2>
    <div style="color:#888;font-size:12px;line-height:1.8">
      🚀 Model API: publish to RapidAPI / OpenAI marketplace<br>
      🚀 Launch freemium: 5 free tasks → upsell to Scout ($50/mo)<br>
      🚀 AP2 enterprise: target FIDO Alliance members for mandate-based settlement<br>
      🚀 MCP Hub: charge discovery fees for premium server listing<br>
      🚀 HF Space: monetize inference at $0.001/call
    </div>
  </div>
  <div class="card">
    <h2 style="color:var(--gold);margin-top:0">Phase 4 — Autonomous Growth Engine</h2>
    <div style="color:#888;font-size:12px;line-height:1.8">
      🔄 Close the loop: real external settlement → HOD reinvests in growth<br>
      🔄 Dataset pipeline → fine-tune nullstate model → better AI scoring<br>
      🔄 Ecosystem signals → adaptation decisions → automated deployment<br>
      🔄 Feedback from real users → product improvements → more revenue
    </div>
  </div>
  <div class="card">
    <h2 style="color:var(--neon);margin-top:0">Revenue Projection</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
      <div><span class="stat">$0/mo</span> <span style="color:#666;font-size:11px">Current</span></div>
      <div><span class="stat">$500-2000/mo</span> <span style="color:#666;font-size:11px">Phase 2-3 Target</span></div>
      <div><span class="stat">$5000-15000/mo</span> <span style="color:#666;font-size:11px">Phase 3-4 Target</span></div>
      <div><span class="stat">74.9%</span> <span style="color:#666;font-size:11px">Gross Margin at Scale</span></div>
    </div>
    <div style="margin-top:12px;background:#0d0d0d;padding:12px;border-radius:6px;font-size:11px;color:#888">
      <div style="color:var(--neon);font-weight:700;margin-bottom:4px">Unit Economics</div>
      <div>• Solution API: $0.025/req → 40 req covers monthly server cost</div>
      <div>• Model Inference: $0.0005/1K tok → 924K tokens/mo to break even</div>
      <div>• Email Relay: $5/1K emails → 93K emails/mo to break even</div>
      <div>• Scout Tier: $50/mo → 10 subscribers = $500/mo (Phase 2 goal)</div>
    </div>
  </div>
</div>

<script>
const vscode = acquireVsCodeApi();

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelector(\`.tab[onclick="switchTab('\${name}'）"\`）.classList.add('active');
  document.getElementById('panel-' + name).classList.add('active');
  if (name === 'verse') {
    const frame = document.getElementById('verse-frame');
    frame.src = frame.src || '${verseUri}';
  }
}

function refresh() {
  vscode.postMessage({ command: 'getIntelligence' });
  vscode.postMessage({ command: 'getTasks' });
  vscode.postMessage({ command: 'getMCPs' });
}

function createTask() { vscode.postMessage({ command: 'createTask' }); }
function connectMCP() { vscode.postMessage({ command: 'connectMCP' }); }
function runHandshake() { vscode.postMessage({ command: 'runAP2' }); }

window.addEventListener('message', event => {
  const msg = event.data;
  if (msg.command === 'intelligence') {
    document.getElementById('balance').textContent = msg.data.balance;
    document.getElementById('tasks-count').textContent = msg.data.tasks;
    document.getElementById('ledger-count').textContent = msg.data.ledger_entries;
    document.getElementById('agents-count').textContent = msg.data.wallet ? '1' : '0';
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

refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>`;
  }
}