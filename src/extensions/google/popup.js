// NullState Chrome Extension — Popup Script

document.addEventListener('DOMContentLoaded', async () => {
  // Get status from background
  const status = await sendMessage({ action: 'getStatus' });

  document.getElementById('gatewayUrl').textContent = status?.gateway || 'unknown';

  if (status?.kyaToken) {
    document.getElementById('status').textContent = '✓ KYA Connected — Payments Ready';
    document.getElementById('status').className = 'status ok';
    document.getElementById('tokenStatus').textContent = 'Active';
  } else {
    document.getElementById('status').textContent = '⚠ KYA Disconnected — Click to refresh';
    document.getElementById('status').className = 'status warn';
    document.getElementById('tokenStatus').textContent = 'Missing';
  }

  // Get tab log
  const tabLog = await sendMessage({ action: 'getTabLog' });
  document.getElementById('tabCount').textContent = tabLog?.length || '0';

  // Agent count from recent tabs (last hour)
  const recent = tabLog?.filter(t => Date.now() - t.timestamp < 3600000) || [];
  document.getElementById('agentCount').textContent = recent.length;

  // Buttons
  document.getElementById('refreshKYA').addEventListener('click', async () => {
    await sendMessage({ action: 'refreshKYA' });
    document.getElementById('status').textContent = '✓ KYA Refreshed';
    document.getElementById('status').className = 'status ok';
    document.getElementById('tokenStatus').textContent = 'Active';
  });

  document.getElementById('openDashboard').addEventListener('click', () => {
    chrome.tabs.create({ url: 'https://greensol.me/nullstate' });
  });

  document.getElementById('payThisTab').addEventListener('click', async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const taskId = `chrome_tab_${tab.id}_${Date.now()}`;
    await fetch('https://greensol.me/nullstate/api/v1/ap2/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mandate_id: taskId,
        buyer_identity: 'chrome_extension',
        amount: 0.025,
        description: `Payment for tab: ${tab.url}`
      })
    });
    document.getElementById('status').textContent = `✓ Charged 0.025 USDC for this tab`;
    document.getElementById('status').className = 'status ok';
  });
});

function sendMessage(msg) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (response) => {
      resolve(response);
    });
  });
}
