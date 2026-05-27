// NullState Chrome Extension — Background Service Worker
// Intercepts Google API calls, injects NullState payment layer

const GATEWAY = 'https://greensol.me/nullstate';
const NULLSTATE_API = 'https://generativelanguage.googleapis.com';

// Store KYA token in chrome.storage
let kyaToken = null;
let kyaExpiry = 0;

// Auto-get KYA token on install
chrome.runtime.onInstalled.addListener(() => {
  console.log('[NullState] Extension installed');
  refreshKYAToken();
  setupAlarms();
});

function setupAlarms() {
  // Refresh KYA token every 45 minutes (tokens expire in 1 hour)
  chrome.alarms.create('refreshKYA', { periodInMinutes: 45 });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'refreshKYA') {
    refreshKYAToken();
  }
});

async function refreshKYAToken() {
  try {
    const resp = await fetch(`${GATEWAY}/kya/challenge`, { cache: 'no-store' });
    const data = await resp.json();
    // Store the challenge data as token
    kyaToken = `${data.challenge}:${data.signature}`;
    kyaExpiry = Date.now() + 55 * 60 * 1000; // 55 min
    await chrome.storage.local.set({ kyaToken, kyaExpiry });
    console.log('[NullState] KYA token refreshed');
  } catch (e) {
    console.error('[NullState] KYA refresh failed:', e);
  }
}

// Intercept Gemini API calls and inject payment header
chrome.webRequest.onBeforeRequest.addListener(
  async (details) => {
    // Check if KYA token is valid
    if (Date.now() > kyaExpiry) {
      await refreshKYAToken();
    }
    return {}; // Continue request
  },
  { urls: [`${NULLSTATE_API}/*`] },
  ['requestBody']
);

// Inject X-KYA-Token into Gemini API requests
chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    const headers = details.requestHeaders || [];
    if (kyaToken) {
      headers.push({
        name: 'X-KYA-Token',
        value: kyaToken
      });
    }
    headers.push({
      name: 'X-NullState-Enabled',
      value: 'true'
    });
    return { requestHeaders: headers };
  },
  { urls: [`${NULLSTATE_API}/*`] },
  ['requestHeaders', 'extraHeaders']
);

// Tab tracking for agent billing
chrome.tabs.onCreated.addListener((tab) => {
  console.log(`[NullState] Tab opened: ${tab.id} — ${tab.url}`);
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    // Track agent tab usage for billing
    chrome.storage.local.get(['tabLog'], (data) => {
      const tabLog = data.tabLog || [];
      tabLog.push({
        tabId,
        url: tab.url,
        timestamp: Date.now()
      });
      // Keep last 100 entries
      if (tabLog.length > 100) tabLog.shift();
      chrome.storage.local.set({ tabLog });
    });
  }
});

// Message handler for popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getStatus') {
    sendResponse({
      kyaToken: !!kyaToken,
      kyaExpiry: kyaExpiry,
      gateway: GATEWAY
    });
  }
  if (request.action === 'refreshKYA') {
    refreshKYAToken().then(() => sendResponse({ success: true }));
    return true; // Keep channel open for async
  }
  if (request.action === 'getTabLog') {
    chrome.storage.local.get(['tabLog'], (data) => {
      sendResponse(data.tabLog || []);
    });
    return true;
  }
});
