export class TaskManager {
  private gatewayUrl: string;

  constructor(gatewayUrl: string) {
    this.gatewayUrl = gatewayUrl;
  }

  async create(params: { source: string; type: string; keywords: string[] }): Promise<any> {
    const resp = await fetch(`${this.gatewayUrl}/webhook/payment_settled`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: `task_vscode_${Date.now()}`,
        source: params.source,
        type: params.type,
        keywords: params.keywords,
      }),
    });
    return resp.json();
  }

  async list(status?: string): Promise<any[]> {
    const resp = await fetch(`${this.gatewayUrl}/get_solution?id=list`);
    return resp.json();
  }
}
