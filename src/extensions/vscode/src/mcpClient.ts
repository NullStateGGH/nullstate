export interface Intelligence {
  tasks: number;
  ledger_entries: number;
  balance: string;
  wallet: string;
  ai_enhanced: boolean;
}

export interface LedgerEntry {
  task_id: string;
  amount: string;
  timestamp: string;
  transaction_hash: string;
  settlement_currency: string;
}

export interface Task {
  id: string;
  type: string;
  source: string;
  status: string;
  keywords: string[];
  settlement_currency?: string;
  ai_estimated_value?: number;
}

export class MCPClient {
  private url: string;
  private requestId = 1;

  constructor(gatewayUrl: string) {
    this.url = `${gatewayUrl}/mcp`;
  }

  private async call(method: string, params: any = {}): Promise<any> {
    const id = this.requestId++;
    const resp = await fetch(this.url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id, method, params }),
    });
    const data = await resp.json();
    if (data.error) throw new Error(data.error.message);
    return data.result;
  }

  async connect() {
    await this.call('tools/list');
  }

  async getIntelligence(): Promise<Intelligence> {
    return this.call('tools/call', { name: 'get_intelligence', arguments: {} });
  }

  async getLedger(): Promise<LedgerEntry[]> {
    return this.call('tools/call', { name: 'get_ledger', arguments: {} });
  }

  async getTasks(status?: string): Promise<Task[]> {
    return this.call('tools/call', { name: 'get_tasks', arguments: { status } });
  }

  async submitSolution(taskId: string, solution: string): Promise<any> {
    return this.call('tools/call', {
      name: 'submit_solution',
      arguments: { task_id: taskId, solution, keywords: ['agent-submitted'], tier: 'MARKET_READY' },
    });
  }

  async executeAP2Handshake(identity: string): Promise<any> {
    return this.call('tools/call', {
      name: 'execute_ap2_handshake',
      arguments: { caller_identity: identity },
    });
  }

  async connectExternal(url: string) {
    // Connect to external MCP server and wrap with payment layer
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list', params: {} }),
    });
    const tools = await resp.json();
    console.log(`[NullState] Connected to external MCP: ${url}`, tools);
    return tools;
  }

  disconnect() {}
}
