// NullState Landing Page Chatbot — Structured Onboarding + Service Catalog + Customized Tasks
(function() {
  var API = '/chat';
  var SESSION_KEY = 'ns_chat_session';
  var STATE_KEY = 'ns_chat_onboarding';
  var sessionId = localStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId = 'chat_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
    localStorage.setItem(SESSION_KEY, sessionId);
  }

  var onboarding = JSON.parse(localStorage.getItem(STATE_KEY) || '{"step":0,"completed":false,"selection":"","custom_task":""}');
  var chatState = { open: false, messages: [], typing: false };

  var styles = [
    '.ns-chatbot * { box-sizing: border-box; }',
    '.ns-chatbot { position: fixed; bottom: 24px; right: 24px; z-index: 9999; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }',
    '.ns-chat-toggle { width: 56px; height: 56px; border-radius: 28px; background: #00ff9d; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 24px; color: #0d0d0d; box-shadow: 0 4px 16px rgba(0,255,157,0.3); transition: all 0.3s; position: relative; }',
    '.ns-chat-toggle:hover { transform: scale(1.05); box-shadow: 0 6px 24px rgba(0,255,157,0.4); }',
    '.ns-chat-badge { position: absolute; top: -4px; right: -4px; width: 12px; height: 12px; background: #ff6b6b; border-radius: 6px; border: 2px solid #0d0d0d; display: none; }',
    '.ns-chat-window { position: absolute; bottom: 68px; right: 0; width: 380px; height: 560px; background: #1a1a2e; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1); display: none; flex-direction: column; overflow: hidden; box-shadow: 0 12px 48px rgba(0,0,0,0.5); }',
    '.ns-chat-window.open { display: flex; }',
    '.ns-chat-header { padding: 14px 16px; background: rgba(0,255,157,0.05); border-bottom: 1px solid rgba(255,255,255,0.06); display: flex; align-items: center; gap: 10px; }',
    '.ns-chat-header-avatar { width: 30px; height: 30px; border-radius: 15px; background: #00ff9d; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; color: #0d0d0d; }',
    '.ns-chat-header h3 { margin: 0; font-size: 13px; color: #e0e0e0; font-weight: 600; flex: 1; }',
    '.ns-chat-header span { font-size: 10px; color: #888; }',
    '.ns-chat-close { background: none; border: none; color: #666; cursor: pointer; font-size: 16px; padding: 2px 6px; }',
    '.ns-chat-messages { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 8px; }',
    '.ns-chat-msg { max-width: 88%; padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.5; word-wrap: break-word; }',
    '.ns-chat-msg.user { align-self: flex-end; background: #00ff9d; color: #0d0d0d; border-bottom-right-radius: 4px; }',
    '.ns-chat-msg.bot { align-self: flex-start; background: rgba(255,255,255,0.06); color: #ccc; border-bottom-left-radius: 4px; }',
    '.ns-chat-msg.system { align-self: center; background: rgba(255,217,61,0.1); color: #ffd93d; font-size: 11px; padding: 6px 10px; border-radius: 8px; }',
    '.ns-chat-msg.typing { align-self: flex-start; background: rgba(255,255,255,0.06); color: #888; font-size: 13px; padding: 10px 14px; }',
    '.ns-chat-typing-dot { display: inline-block; animation: nsPulse 1.2s infinite; }',
    '.ns-chat-typing-dot:nth-child(2) { animation-delay: 0.2s; }',
    '.ns-chat-typing-dot:nth-child(3) { animation-delay: 0.4s; }',
    '@keyframes nsPulse { 0%, 60%, 100% { opacity: 0.3; } 30% { opacity: 1; } }',
    '.ns-chat-buttons { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }',
    '.ns-chat-btn { padding: 7px 14px; border-radius: 8px; border: 1px solid rgba(0,255,157,0.3); background: rgba(0,255,157,0.06); color: #00ff9d; font-size: 12px; cursor: pointer; transition: all 0.2s; }',
    '.ns-chat-btn:hover { background: rgba(0,255,157,0.15); border-color: #00ff9d; }',
    '.ns-chat-btn.primary { background: #00ff9d; color: #0d0d0d; border-color: #00ff9d; font-weight: 600; }',
    '.ns-chat-btn.primary:hover { background: #00cc7d; }',
    '.ns-chat-btn.secondary { border-color: rgba(255,255,255,0.15); color: #999; background: rgba(255,255,255,0.03); }',
    '.ns-chat-btn.secondary:hover { border-color: rgba(255,255,255,0.3); color: #ccc; }',
    '.ns-chat-card { background: rgba(0,255,157,0.04); border: 1px solid rgba(0,255,157,0.1); border-radius: 10px; padding: 12px; margin: 4px 0; }',
    '.ns-chat-card h4 { margin: 0 0 4px; font-size: 13px; color: #00ff9d; }',
    '.ns-chat-card p { margin: 0; font-size: 11px; color: #999; }',
    '.ns-chat-card .price { font-size: 18px; font-weight: bold; color: #e0e0e0; margin: 4px 0; }',
    '.ns-chat-input-area { padding: 10px 14px; border-top: 1px solid rgba(255,255,255,0.06); display: flex; gap: 8px; background: rgba(0,0,0,0.2); }',
    '.ns-chat-input { flex: 1; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 9px 12px; color: #e0e0e0; font-size: 13px; outline: none; transition: border-color 0.2s; }',
    '.ns-chat-input:focus { border-color: #00ff9d; }',
    '.ns-chat-input::placeholder { color: #555; }',
    '.ns-chat-send { background: #00ff9d; border: none; border-radius: 8px; padding: 9px 14px; color: #0d0d0d; font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.2s; }',
    '.ns-chat-send:hover { background: #00cc7d; }',
    '.ns-chat-send:disabled { opacity: 0.4; cursor: default; }',
    '.ns-chat-footer { padding: 6px 14px; text-align: center; font-size: 10px; color: #444; border-top: 1px solid rgba(255,255,255,0.04); }',
    '.ns-chat-footer a { color: #00ff9d; text-decoration: none; }',
  ];

  var styleTag = document.createElement('style');
  styleTag.textContent = styles.join('\n');
  document.head.appendChild(styleTag);

  function saveState() {
    localStorage.setItem(STATE_KEY, JSON.stringify(onboarding));
  }

  function render() {
    var existing = document.querySelector('.ns-chatbot');
    if (existing) existing.remove();

    var container = document.createElement('div');
    container.className = 'ns-chatbot';
    container.innerHTML = [
      '<div class="ns-chat-window" id="nsChatWindow">',
      '  <div class="ns-chat-header">',
      '    <div class="ns-chat-header-avatar">N</div>',
      '    <h3>NullState · Agent Onboarding</h3>',
      '    <span id="nsChatStatus">Online</span>',
      '    <button class="ns-chat-close" id="nsChatClose">✕</button>',
      '  </div>',
      '  <div class="ns-chat-messages" id="nsChatMessages"></div>',
      '  <div class="ns-chat-input-area">',
      '    <input class="ns-chat-input" id="nsChatInput" placeholder="Type your message..." />',
      '    <button class="ns-chat-send" id="nsChatSend">Send</button>',
      '  </div>',
      '  <div class="ns-chat-footer">Powered by <a href="https://greensol.me/nullstate" target="_blank">NullState</a> · AI agent payment infrastructure</div>',
      '</div>',
      '<button class="ns-chat-toggle" id="nsChatToggle">',
      '  <span id="nsChatIcon">⚡</span>',
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

    initChat();
  }

  function initChat() {
    var msgs = document.getElementById('nsChatMessages');
    if (!onboarding.completed) {
      // Resume or start onboarding
      if (onboarding.step === 0) {
        addBotMessage(
          '⚡ Welcome to NullState — the payment infrastructure for AI agents.\n\n' +
          'I\'ll help you get started. First, what brings you here today?',
          [
            { label: '🚀 Deploy NullState', value: 'deploy', type: 'primary' },
            { label: '🔌 Integrate API', value: 'integrate', type: '' },
            { label: '📚 Learn Protocols', value: 'learn', type: '' },
            { label: '🛠️ Build with MCP', value: 'build', type: '' },
            { label: '💬 Just Exploring', value: 'explore', type: 'secondary' },
          ]
        );
      } else {
        addBotMessage('Welcome back! Let\'s continue where we left off.');
        resumeOnboarding();
      }
    } else {
      addBotMessage('Welcome back! How can I help you with NullState today?', [
        { label: '📦 Products', value: 'products', type: '' },
        { label: '🔧 Services', value: 'services', type: '' },
        { label: '🎯 Custom Task', value: 'custom', type: 'primary' },
        { label: '💡 Feedback', value: 'feedback', type: 'secondary' },
      ]);
    }
  }

  function resumeOnboarding() {
    if (onboarding.step >= 1) {
      showServiceStep(onboarding.selection);
    }
  }

  function toggle() {
    chatState.open = !chatState.open;
    document.getElementById('nsChatWindow').classList.toggle('open', chatState.open);
    document.getElementById('nsChatBadge').style.display = 'none';
    if (chatState.open) {
      setTimeout(function() { document.getElementById('nsChatInput').focus(); }, 300);
    }
  }

  function addBotMessage(text, buttons) {
    var msgs = document.getElementById('nsChatMessages');
    var div = document.createElement('div');
    div.className = 'ns-chat-msg bot';
    div.textContent = text;
    msgs.appendChild(div);
    waitForElm(msgs);
    if (buttons && buttons.length) {
      var btnContainer = document.createElement('div');
      btnContainer.className = 'ns-chat-buttons';
      buttons.forEach(function(b) {
        var btn = document.createElement('button');
        btn.className = 'ns-chat-btn' + (b.type ? ' ' + b.type : '');
        btn.textContent = b.label;
        btn.onclick = function() { handleButton(b.value, b.label); };
        btnContainer.appendChild(btn);
      });
      msgs.appendChild(btnContainer);
    }
    msgs.scrollTop = msgs.scrollHeight;
  }

  function addUserMessage(text) {
    var msgs = document.getElementById('nsChatMessages');
    var div = document.createElement('div');
    div.className = 'ns-chat-msg user';
    div.textContent = text;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function addSystemMessage(text) {
    var msgs = document.getElementById('nsChatMessages');
    var div = document.createElement('div');
    div.className = 'ns-chat-msg system';
    div.textContent = text;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
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

  function waitForElm(container) {
    // Force layout reflow
    void container.offsetHeight;
  }

  function handleButton(value, label) {
    if (chatState.typing) return;
    addUserMessage(label);
    processOnboarding(value);
  }

  function processOnboarding(value) {
    if (!onboarding.completed) {
      if (onboarding.step === 0) {
        // First selection — route to service/product catalog
        onboarding.step = 1;
        onboarding.selection = value;
        saveState();
        showTyping();
        setTimeout(function() {
          hideTyping();
          showServiceStep(value);
        }, 600);
        return;
      }
      if (onboarding.step === 1) {
        // Service/product sub-selection
        onboarding.step = 2;
        onboarding.selection = value;
        saveState();
        showTyping();
        setTimeout(function() {
          hideTyping();
          showTaskCustomization(value, onboarding.selection);
        }, 600);
        return;
      }
      if (onboarding.step === 2) {
        // Task customization — finalize
        onboarding.completed = true;
        onboarding.custom_task = value;
        saveState();
        showTyping();
        setTimeout(function() {
          hideTyping();
          finalizeOnboarding(value);
        }, 600);
        return;
      }
    }
    // Post-onboarding: route direct
    handleDirectQuery(value);
  }

  function showServiceStep(selection) {
    var services = {
      'deploy': {
        title: '🚀 Deploy NullState',
        items: [
          { name: 'Docker Compose', desc: 'One-command deploy', action: 'docker', price: 'Free' },
          { name: 'Source Install', desc: 'From GitHub (MIT)', action: 'source', price: 'Free' },
          { name: 'Systemd Service', desc: 'Production daemon', action: 'systemd', price: 'Free' },
          { name: 'Custom Setup', desc: 'Guided configuration', action: 'custom-setup', price: 'Free' },
        ]
      },
      'integrate': {
        title: '🔌 API Integration',
        items: [
          { name: 'Solution API', desc: '$0.025/request', action: 'solution_api', price: '$0.025/req' },
          { name: 'Model Inference', desc: '$0.0005/1K tokens', action: 'model_api', price: '$0.0005/1K' },
          { name: 'Email Relay', desc: '$5/1000 emails', action: 'email', price: '$5/1K' },
          { name: 'MCP Protocol', desc: 'JSON-RPC tools', action: 'mcp', price: 'Free' },
        ]
      },
      'learn': {
        title: '📚 Protocols & Docs',
        items: [
          { name: 'x402 Protocol', desc: 'HTTP 402 micropayments', action: 'x402', price: 'Docs' },
          { name: 'AP2 Protocol', desc: 'Enterprise mandates', action: 'ap2', price: 'Docs' },
          { name: 'MCP Protocol', desc: 'AI tool integration', action: 'mcp_learn', price: 'Docs' },
          { name: 'KYA Protocol', desc: 'Agent identity', action: 'kya', price: 'Docs' },
        ]
      },
      'build': {
        title: '🛠️ Build with MCP',
        items: [
          { name: 'Custom MCP Server', desc: 'Build your own tools', action: 'custom_mcp', price: 'Free' },
          { name: 'Agent Workflow', desc: 'Auto payment pipeline', action: 'agent_workflow', price: 'Custom' },
          { name: 'Chrome Extension', desc: 'Browser agent payments', action: 'chrome_ext', price: 'Free' },
          { name: 'VS Code Extension', desc: 'Dev workspace payments', action: 'vscode', price: 'Free' },
        ]
      },
      'explore': {
        title: '💬 Let\'s Explore',
        items: [
          { name: 'Product Catalog', desc: 'See all offerings', action: 'products', price: '' },
          { name: 'Pricing Tiers', desc: 'Free · Scout · Pro · Enterprise', action: 'pricing', price: '' },
          { name: 'Live Demo', desc: 'See it in action', action: 'demo', price: 'Free' },
          { name: 'Talk to Founder', desc: 'Schedule a call', action: 'founder', price: 'Free' },
        ]
      },
    };
    var svc = services[selection] || services['explore'];
    var msg = svc.title + '\n\nSelect a service to continue:';
    var buttons = svc.items.map(function(item) {
      return {
        label: item.name + ' · ' + item.price,
        value: item.action,
        type: item.action === svc.items[0].action ? 'primary' : '',
      };
    });
    buttons.push({ label: '◀ Back', value: 'back', type: 'secondary' });
    addBotMessage(msg, buttons);
  }

  function showTaskCustomization(action, category) {
    var tasks = {
      'docker': { title: '🐳 Docker Deploy', desc: 'Run `docker compose up -d` to start NullState gateway on :8080.\n\nCustomize your deployment:', options: ['Quick Deploy (default)', 'With Custom Config', 'With SSL Domain', 'With Email Relay'] },
      'source': { title: '📦 Source Install', desc: 'Clone from GitHub and run with Python 3.13+\n\nCustomize your install:', options: ['Basic Install', 'With All Extensions', 'Development Mode', 'Minimal Setup'] },
      'systemd': { title: '⚙️ Systemd Setup', desc: 'Production daemon with auto-restart\n\nChoose your service configuration:', options: ['Full Stack (all services)', 'Gateway Only', 'Gateway + Model API', 'Custom Service Set'] },
      'solution_api': { title: '🧠 Solution API', desc: '$0.025 per request. AI-generated solutions for agent tasks.\n\nHow many requests do you need?', options: ['100 requests ($2.50)', '1,000 requests ($25)', '10,000 requests ($250)', 'Custom amount'] },
      'model_api': { title: '🤖 Model Inference', desc: '$0.0005 per 1K tokens. Dual-model (Phi-3 + Gemini).\n\nEstimate your token usage:', options: ['Light (<100K tokens/mo)', 'Medium (100K-1M)', 'Heavy (1M-10M)', 'Enterprise (custom)'] },
      'email': { title: '📧 Email Relay', desc: '$5 per 1,000 emails. SMTP on port 2525.\n\nVolume estimate:', options: ['Starter (1K/mo = $5)', 'Growth (10K/mo = $50)', 'Scale (100K/mo = $500)', 'Custom volume'] },
      'mcp': { title: '🔗 MCP Protocol', desc: 'JSON-RPC 2.0 tools for AI agents.\n\nAvailable MCP tools:', options: ['get_intelligence', 'submit_solution', 'get_ledger', 'execute_ap2_handshake'] },
      'custom_mcp': { title: '🛠️ Custom MCP Server', desc: 'Build your own MCP server with NullState payment layer.\n\nChoose your stack:', options: ['Python + FastAPI', 'Node.js + Express', 'Go + Chi', 'Rust + Axum'] },
      'products': { title: '📦 Product Catalog', desc: 'NullState Product Catalog:\n\n• Solution API — $0.025/request\n• Model Inference — $0.0005/1K tokens\n• Email Relay — $5/1000 emails\n• MCP Server — Free\n• AP2 Protocol — Free\n• KYA Identity — Free\n\nWhat interests you?', options: ['Solution API', 'Model Inference', 'Email Relay', 'Show All Pricing'] },
      'pricing': { title: '💰 Pricing Tiers', desc: 'Free: 5 requests/mo — $0\nScout: 500 req/mo — $50\nPro: 5,000 req/mo — $200\nEnterprise: Unlimited — $500/mo\n\nAll tiers include all protocols.', options: ['Start Free', 'Go Scout', 'Go Pro', 'Enterprise Quote'] },
      'demo': { title: '🎮 Live Demo', desc: 'Try NullState right now:\n\ncurl -k https://localhost:8080/health\ncurl -k https://localhost:8080/kya/challenge\ncurl -k -X POST https://localhost:8080/mcp ...\n\nWant me to walk you through a specific demo?', options: ['AP2 Handshake Demo', 'x402 Payment Demo', 'MCP Tool Demo', 'Full Store Demo'] },
      'founder': { title: '👋 Talk to Founder', desc: 'The NullState founder monitors this chat.\n\nLeave your message or question and I\'ll make sure it reaches them directly.', options: ['Partnership Inquiry', 'Enterprise License', 'Feature Request', 'Just Saying Hi'] },
      'feedback': { title: '💡 Share Feedback', desc: 'Your feedback trains our AI and shapes our roadmap.\n\nWhat\'s on your mind?', options: ['Bug Report', 'Feature Suggestion', 'Documentation Issue', 'General Feedback'] },
      'custom': { title: '🎯 Custom Task', desc: 'Describe what you want to build or solve with NullState.\n\nTell me about your use case and I\'ll create a customized task for you:', options: [] },
    };

    var task = tasks[action] || {
      title: '🎯 Custom Task',
      desc: 'Describe your use case and I\'ll help you build a customized solution with NullState.',
      options: [],
    };

    var msg = task.title + '\n\n' + task.desc;
    var buttons = task.options.map(function(opt, i) {
      return { label: opt, value: opt, type: i === 0 ? 'primary' : '' };
    });
    buttons.push({ label: '◀ Back', value: 'back', type: 'secondary' });
    addBotMessage(msg, buttons);
  }

  function finalizeOnboarding(value) {
    onboarding.completed = true;
    saveState();

    var summary = '✅ **Onboarding Complete!**\n\n' +
      'Your selection has been registered in NullState\'s agentic feedback system. ' +
      'This interaction will help us improve our services.\n\n' +
      '**Quick Links:**\n' +
      '• 📖 Docs: https://greensol.me/nullstate/docs/quickstart\n' +
      '• 🐙 GitHub: https://github.com/NullStateGGH/nullstate\n' +
      '• 💻 Deploy: `docker compose up -d`\n\n' +
      'What would you like to do next?';

    addBotMessage(summary, [
      { label: '📦 Products', value: 'products', type: '' },
      { label: '🚀 Deploy Now', value: 'deploy_quick', type: 'primary' },
      { label: '💬 Chat More', value: 'chat_more', type: '' },
      { label: '🔄 Restart', value: 'restart', type: 'secondary' },
    ]);

    // Send onboarding completion to backend
    try {
      navigator.sendBeacon(API, JSON.stringify({
        message: '[ONBOARDING COMPLETE] selection=' + onboarding.selection + ' task=' + value,
        session_id: sessionId,
        event: 'onboarding_complete',
      }));
    } catch(e) {}
  }

  function handleDirectQuery(value) {
    if (value === 'back') {
      onboarding.step = Math.max(0, onboarding.step - 1);
      if (onboarding.step === 0) {
        onboarding.selection = '';
      }
      saveState();
      addBotMessage('Going back...');
      setTimeout(function() {
        if (onboarding.step === 0) {
          addBotMessage('What brings you to NullState?', [
            { label: '🚀 Deploy', value: 'deploy', type: 'primary' },
            { label: '🔌 Integrate', value: 'integrate', type: '' },
            { label: '📚 Learn', value: 'learn', type: '' },
            { label: '🛠️ Build', value: 'build', type: '' },
            { label: '💬 Explore', value: 'explore', type: 'secondary' },
          ]);
        } else {
          showServiceStep(onboarding.selection);
        }
      }, 300);
      return;
    }
    if (value === 'restart') {
      onboarding = { step: 0, completed: false, selection: '', custom_task: '' };
      saveState();
      var msgs = document.getElementById('nsChatMessages');
      msgs.innerHTML = '';
      initChat();
      return;
    }
    if (value === 'deploy_quick') {
      addBotMessage('Run this command to deploy NullState immediately:\n\n```\ndocker compose up -d\n```\n\nGateway will be live on https://localhost:8080 within seconds.\n\nCheck health: `curl -k https://localhost:8080/health`', [
        { label: '📖 Full Docs', value: 'docs', type: '' },
        { label: '⚙️ Configure', value: 'config', type: '' },
        { label: '◀ Back to Menu', value: 'back_menu', type: 'secondary' },
      ]);
      return;
    }
    if (value === 'chat_more' || value === 'back_menu') {
      addBotMessage('How can I help you with NullState?', [
        { label: '📦 Products', value: 'products', type: '' },
        { label: '🔧 Services', value: 'services', type: '' },
        { label: '🎯 Custom Task', value: 'custom', type: 'primary' },
        { label: '💡 Feedback', value: 'feedback', type: 'secondary' },
      ]);
      return;
    }
    if (value === 'docs') {
      window.open('/nullstate/docs/quickstart', '_blank');
      addSystemMessage('📖 Opening documentation in new tab...');
      return;
    }

    // Fallback: send to backend AI
    var sendBtn = document.getElementById('nsChatSend');
    sendBtn.disabled = true;
    showTyping();

    fetch(API, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ message: value, session_id: sessionId, user_agent: navigator.userAgent }),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      hideTyping();
      sendBtn.disabled = false;
      addBotMessage(data.response || 'How can I help?');
    })
    .catch(function() {
      hideTyping();
      sendBtn.disabled = false;
      addBotMessage('I\'m here to help! Ask me about deployment, protocols, pricing, or anything NullState.');
    });
  }

  function send() {
    var input = document.getElementById('nsChatInput');
    var text = input.value.trim();
    if (!text || chatState.typing) return;
    input.value = '';
    addUserMessage(text);

    if (!onboarding.completed) {
      processOnboarding(text);
      return;
    }
    handleDirectQuery(text);
  }

  function render() { /* already defined above */ }
  function initChat() { /* already defined above */ }

  // Init
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }

  // Track for analytics
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
