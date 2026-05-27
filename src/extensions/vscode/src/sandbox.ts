import * as vscode from 'vscode';
import * as cp from 'child_process';

export class Sandbox {
  private terminals: Map<string, vscode.Terminal> = new Map();

  createTerminal(name: string, cwd?: string): vscode.Terminal {
    const terminal = vscode.window.createTerminal({
      name: `NullState: ${name}`,
      cwd,
      env: {
        NULLSTATE_ENABLED: 'true',
        NULLSTATE_GATEWAY: vscode.workspace.getConfiguration('nullstate').get<string>('gatewayUrl')!,
      },
    });
    this.terminals.set(name, terminal);
    terminal.show();
    return terminal;
  }

  execInTerminal(name: string, command: string) {
    const term = this.terminals.get(name) || this.createTerminal(name);
    term.sendText(command);
  }

  execSync(command: string, cwd?: string): string {
    return cp.execSync(command, { cwd, encoding: 'utf-8', timeout: 30000 });
  }

  dispose() {
    this.terminals.forEach(t => t.dispose());
    this.terminals.clear();
  }
}
