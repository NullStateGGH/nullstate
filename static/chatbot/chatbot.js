// NullState Landing Page Chatbot — customer service + feedback + agentic data
(function() {
  var API = '/chat';
  var SESSION_KEY = 'ns_chat_session';
  var sessionId = localStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId = 'chat_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
    localStorage.setItem(SESSION_KEY, sessionId);
  }

  var chatState = {
    open: false,
    messages: [],
    typing: false,
  };

  var ASSETS = '/nullstate/chatbot';

  var styles = [
    '.ns-chatbot * { box-sizing: border-box; }',
    '.ns-chatbot { position: fixed; bottom: 24px; right: 24px; z-index: 9999; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }',
    '.ns-chat-toggle { width: 56px; height: 56px; border-radius: 28px; background: #00ff9d; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 24px; color: #0d0d0d; box-shadow: 0 4px 16px rgba(0,255,157,0.3); transition: all 0.3s; position: relative; }',
    '.ns-chat-toggle:hover { transform: scale(1.05); box-shadow: 0 6px 24px rgba(0,255,157,0.4); }',
    '.ns-chat-badge { position: absolute; top: -4px; right: -4px; width: 12px; height: 12px; background: #ff6b6b; border-radius: 6px; border: 2px solid #0d0d0d; display: none; }',
    '.ns-chat-window { position: absolute; bottom: 68px; right: 0; width: 360px; height: 520px; background: #1a1a2e; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1); display: none; flex-direction: column; overflow: hidden; box-shadow: 0 12px 48px rgba(0,0,0,0.5); }',
    '.ns-chat-window.open { display: flex; }',
    '.ns-chat-header { padding: 16px; background: rgba(0,255,157,0.05); border-bottom: 1px solid rgba(255,255,255,0.06); display: flex; align-items: center; gap: 10px; }',
    '.ns-chat-header-avatar { width: 32px; height: 32px; border-radius: 16px; background: #00ff9d; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: bold; color: #0d0d0d; }',
    '.ns-chat-header h3 { margin: 0; font-size: 14px; color: #e0e0e0; font-weight: 600; flex: 1; }',
    '.ns-chat-header span { font-size: 11px; color: #888; }',
    '.ns-chat-close { background: none; border: none; color: #666; cursor: pointer; font-size: 18px; padding: 4px; }',
    '.ns-chat-messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; }',
    '.ns-chat-msg { max-width: 85%; padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.5; word-wrap: break-word; }',
    '.ns-chat-msg.user { align-self: flex-end; background: #00ff9d; color: #0d0d0d; border-bottom-right-radius: 4px; }',
    '.ns-chat-msg.bot { align-self: flex-start; background: rgba(255,255,255,0.06); color: #ccc; border-bottom-left-radius: 4px; }',
    '.ns-chat-msg.system { align-self: center; background: rgba(255,217,61,0.1); color: #ffd93d; font-size: 11px; padding: 6px 10px; border-radius: 8px; }',
    '.ns-chat-msg.typing { align-self: flex-start; background: rgba(255,255,255,0.06); color: #888; font-size: 13px; padding: 10px 14px; }',
    '.ns-chat-typing-dot { display: inline-block; animation: nsPulse 1.2s infinite; }',
    '.ns-chat-typing-dot:nth-child(2) { animation-delay: 0.2s; }',
    '.ns-chat-typing-dot:nth-child(3) { animation-delay: 0.4s; }',
    '@keyframes nsPulse { 0%, 60%, 100% { opacity: 0.3; } 30% { opacity: 1; } }',
    '.ns-chat-input-area { padding: 12px 16px; border-top: 1px solid rgba(255,255,255,0.06); display: flex; gap: 8px; background: rgba(0,0,0,0.2); }',
    '.ns-chat-input { flex: 1; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 10px 12px; color: #e0e0e0; font-size: 13px; outline: none; transition: border-color 0.2s; }',
    '.ns-chat-input:focus { border-color: #00ff9d; }',
    '.ns-chat-input::placeholder { color: #555; }',
    '.ns-chat-send { background: #00ff9d; border: none; border-radius: 8px; padding: 10px 16px; color: #0d0d0d; font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.2s; }',
    '.ns-chat-send:hover { background: #00cc7d; }',
    '.ns-chat-send:disabled { opacity: 0.4; cursor: default; }',
    '.ns-chat-footer { padding: 8px 16px; text-align: center; font-size: 10px; color: #444; border-top: 1px solid rgba(255,255,255,0.04); }',
    '.ns-chat-footer a { color: #00ff9d; text-decoration: none; }',
  ];

  var styleTag = document.createElement('style');
  styleTag.textContent = styles.join('\n');
  document.head.appendChild(styleTag);

  function render() {
    var existing = document.querySelector('.ns-chatbot');
    if (existing) existing.remove();

    var container = document.createElement('div');
    container.className = 'ns-chatbot';
    container.innerHTML = [
      '<div class="ns-chat-window" id="nsChatWindow">',
      '  <div class="ns-chat-header">',
      '    <div class="ns-chat-header-avatar">N</div>',
      '    <h3>NullState Agent</h3>',
      '    <span>Online</span>',
      '    <button class="ns-chat-close" id="nsChatClose">✕</button>',
      '  </div>',
      '  <div class="ns-chat-messages" id="nsChatMessages">',
      '    <div class="ns-chat-msg bot">Hi! I\'m NullState\'s AI assistant. Ask me about our payment infrastructure, protocols, deployment — or share your feedback!</div>',
      '  </div>',
      '  <div class="ns-chat-input-area">',
      '    <input class="ns-chat-input" id="nsChatInput" placeholder="Type a message..." />',
      '    <button class="ns-chat-send" id="nsChatSend">Send</button>',
      '  </div>',
      '  <div class="ns-chat-footer">Powered by <a href="https://greensol.me/nullstate" target="_blank">NullState</a> · Data trains our AI</div>',
      '</div>',
      '<button class="ns-chat-toggle" id="nsChatToggle">',
      '  <span id="nsChatIcon">💬</span>',
      '  <span class="ns-chat-badge" id="nsChatBadge"></span>',
      '</button>',
    ].join('\n');
    document.body.appendChild(container);

    document.getElementById('nsChatToggle').onclick = toggle;
    document.getElementById('nsChatClose').onclick = toggle;
    document.getElementById('nsChatSend').onclick = send;
    document.getElementById('nsChatInput').onkeydown = function(e) {
      if (e.key === 'Enter') send();
    };
  }

  function toggle() {
    chatState.open = !chatState.open;
    document.getElementById('nsChatWindow').classList.toggle('open', chatState.open);
    document.getElementById('nsChatBadge').style.display = 'none';
    if (chatState.open) {
      setTimeout(function() {
        document.getElementById('nsChatInput').focus();
      }, 300);
    }
  }

  function addMessage(text, role) {
    var msgs = document.getElementById('nsChatMessages');
    var div = document.createElement('div');
    div.className = 'ns-chat-msg ' + role;
    div.textContent = text;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    chatState.messages.push({role: role, text: text});
  }

  function showTyping() {
    var msgs = document.getElementById('nsChatMessages');
    var div = document.createElement('div');
    div.className = 'ns-chat-msg typing';
    div.id = 'nsChatTyping';
    div.innerHTML = '<span class="ns-chat-typing-dot">●</span> <span class="ns-chat-typing-dot">●</span> <span class="ns-chat-typing-dot">●</span>';
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    chatState.typing = true;
  }

  function hideTyping() {
    var el = document.getElementById('nsChatTyping');
    if (el) el.remove();
    chatState.typing = false;
  }

  function send() {
    var input = document.getElementById('nsChatInput');
    var text = input.value.trim();
    if (!text || chatState.typing) return;

    input.value = '';
    addMessage(text, 'user');

    var sendBtn = document.getElementById('nsChatSend');
    sendBtn.disabled = true;
    showTyping();

    var payload = JSON.stringify({
      message: text,
      session_id: sessionId,
      user_agent: navigator.userAgent,
    });

    fetch(API, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: payload,
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      hideTyping();
      sendBtn.disabled = false;
      var reply = data.response || data.reply || 'Sorry, I encountered an error.';
      addMessage(reply, 'bot');
    })
    .catch(function() {
      hideTyping();
      sendBtn.disabled = false;
      addMessage('I apologize but I\'m having a temporary issue connecting. Please try again.', 'bot');
    });
  }

  // Init
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }

  // Track pageview for analytics
  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/v1/analytics/track', JSON.stringify({
        event: 'chatbot_loaded',
        path: window.location.pathname,
        session_id: sessionId,
      }));
    }
  } catch(e) {}
})();
