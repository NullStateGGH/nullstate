export class WalletManager {
  private gatewayUrl: string;
  private kyaToken: string | null = null;

  constructor(gatewayUrl: string) {
    this.gatewayUrl = gatewayUrl;
  }

  async getKYAToken(): Promise<string> {
    if (this.kyaToken) return this.kyaToken;
    const resp = await fetch(`${this.gatewayUrl}/kya/challenge`);
    const data = await resp.json();
    this.kyaToken = `${data.challenge}:${data.signature}`;
    return this.kyaToken;
  }

  async getBalance(): Promise<string> {
    try {
      const resp = await fetch(`${this.gatewayUrl}/balance`);
      const data = await resp.json();
      return data.balance || '0.00';
    } catch {
      return 'gateway_unreachable';
    }
  }

  async sendPayment(taskId: string, amount: number): Promise<any> {
    const token = await this.getKYAToken();
    const resp = await fetch(`${this.gatewayUrl}/api/v1/ap2/charge`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-KYA-Token': token,
      },
      body: JSON.stringify({
        mandate_id: `vscode_${taskId}_${Date.now()}`,
        buyer_signature: 'vscode_agent_signed',
        tx_hash: null,
      }),
    });
    return resp.json();
  }
}
