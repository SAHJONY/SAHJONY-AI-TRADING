/**
 * Hermes Agent Web Dashboard
 * Interactive dashboard for the Nous Research Hermes Agent
 */

import express, { Request, Response } from 'express'

const router = express.Router()

export function setupHermesDashboard(app: express.Application): void {
  // Dashboard page at /hermes
  app.get('/hermes', (_req: Request, res: Response) => {
    res.send(getDashboardHTML())
  })
  
  console.log('  Hermes Agent Dashboard: http://localhost:3000/hermes')
}

function getDashboardHTML(): string {
  return `<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>Hermes Agent - Nous Research AI</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    
    :root {
      --hermes-primary: #6366f1;
      --hermes-secondary: #8b5cf6;
      --hermes-accent: #a855f7;
      --hermes-success: #10b981;
      --hermes-warning: #f59e0b;
      --hermes-danger: #ef4444;
      --bg-dark: #0f172a;
      --bg-card: #1e293b;
      --bg-hover: #334155;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --border: #334155;
    }
    
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: var(--bg-dark);
      color: var(--text-primary);
      min-height: 100vh;
      line-height: 1.6;
    }
    
    .header {
      background: linear-gradient(135deg, var(--hermes-primary), var(--hermes-accent));
      padding: 32px 24px;
      text-align: center;
      position: relative;
      overflow: hidden;
    }
    
    .header::before {
      content: '';
      position: absolute;
      top: -50%;
      left: -50%;
      width: 200%;
      height: 200%;
      background: radial-gradient(circle, rgba(139, 92, 246, 0.15) 0%, transparent 50%);
      animation: pulse 8s ease-in-out infinite;
    }
    
    @keyframes pulse {
      0%, 100% { transform: scale(1); opacity: 0.5; }
      50% { transform: scale(1.1); opacity: 0.8; }
    }
    
    .header-content { position: relative; z-index: 1; }
    
    .header h1 { font-size: 36px; margin-bottom: 8px; }
    .header h1 span { background: linear-gradient(135deg, #ffd700, #ffaa00); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .header p { opacity: 0.9; font-size: 18px; }
    
    .status-bar {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 20px;
      background: rgba(255,255,255,0.1);
      border-radius: 24px;
      font-size: 14px;
      margin-top: 16px;
      backdrop-filter: blur(10px);
    }
    
    .status-bar .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--hermes-danger);
      animation: pulse-dot 2s infinite;
    }
    
    @keyframes pulse-dot {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    
    .status-bar.connected .dot { 
      background: var(--hermes-success);
      box-shadow: 0 0 10px var(--hermes-success);
    }
    
    .status-bar.serverless .dot {
      background: var(--hermes-warning);
      animation: none;
    }
    
    .container { max-width: 1400px; margin: 0 auto; padding: 24px; }
    
    .capabilities-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin: 24px 0;
    }
    
    .capability-card {
      background: var(--bg-card);
      border-radius: 16px;
      padding: 20px;
      border: 1px solid var(--border);
      text-align: center;
      transition: all 0.3s;
    }
    
    .capability-card:hover {
      border-color: var(--hermes-primary);
      transform: translateY(-4px);
      box-shadow: 0 8px 30px rgba(99, 102, 241, 0.15);
    }
    
    .capability-icon { font-size: 36px; margin-bottom: 12px; }
    .capability-name { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
    .capability-desc { color: var(--text-secondary); font-size: 13px; }
    
    .main-layout {
      display: grid;
      grid-template-columns: 1fr 400px;
      gap: 24px;
    }
    
    @media (max-width: 1100px) {
      .main-layout { grid-template-columns: 1fr; }
    }
    
    .chat-section {
      background: var(--bg-card);
      border-radius: 20px;
      overflow: hidden;
      border: 1px solid var(--border);
    }
    
    .chat-header {
      padding: 20px 24px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    
    .chat-header h2 { font-size: 18px; display: flex; align-items: center; gap: 8px; }
    
    .model-selector {
      display: flex;
      gap: 8px;
    }
    
    .model-btn {
      padding: 6px 14px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: transparent;
      color: var(--text-secondary);
      font-size: 12px;
      cursor: pointer;
      transition: all 0.2s;
    }
    
    .model-btn:hover { border-color: var(--hermes-primary); color: var(--text-primary); }
    .model-btn.active { background: var(--hermes-primary); border-color: var(--hermes-primary); color: white; }
    
    .chat-messages {
      height: 450px;
      overflow-y: auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      background: linear-gradient(180deg, rgba(99, 102, 241, 0.03) 0%, transparent 100%);
    }
    
    .message {
      max-width: 85%;
      padding: 16px 20px;
      border-radius: 18px;
      line-height: 1.6;
      animation: messageIn 0.4s ease;
    }
    
    @keyframes messageIn {
      from { opacity: 0; transform: translateY(20px) scale(0.95); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    
    .message.bot { 
      align-self: flex-start; 
      background: var(--bg-hover);
      border-bottom-left-radius: 6px;
    }
    
    .message.user { 
      align-self: flex-end; 
      background: linear-gradient(135deg, var(--hermes-primary), var(--hermes-secondary));
      color: white;
      border-bottom-right-radius: 6px;
    }
    
    .message .avatar {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--hermes-primary), var(--hermes-accent));
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 14px;
      margin-right: 8px;
      vertical-align: middle;
    }
    
    .message.user .avatar { background: rgba(255,255,255,0.2); }
    
    .message .meta {
      font-size: 11px;
      color: var(--text-secondary);
      margin-top: 6px;
      display: flex;
      gap: 12px;
    }
    
    .message.user .meta { color: rgba(255,255,255,0.7); }
    
    .typing-indicator {
      display: flex;
      gap: 6px;
      padding: 16px 20px;
      background: var(--bg-hover);
      border-radius: 18px;
      border-bottom-left-radius: 6px;
      width: fit-content;
    }
    
    .typing-indicator span {
      width: 8px;
      height: 8px;
      background: var(--hermes-primary);
      border-radius: 50%;
      animation: typingBounce 1.4s infinite;
    }
    
    .typing-indicator span:nth-child(2) { animation-delay: 0.15s; }
    .typing-indicator span:nth-child(3) { animation-delay: 0.3s; }
    
    @keyframes typingBounce {
      0%, 60%, 100% { transform: translateY(0); }
      30% { transform: translateY(-8px); }
    }
    
    .chat-input-area {
      padding: 20px 24px;
      border-top: 1px solid var(--border);
      display: flex;
      gap: 12px;
      background: var(--bg-card);
    }
    
    .chat-input-area input {
      flex: 1;
      padding: 14px 20px;
      border-radius: 14px;
      border: 1px solid var(--border);
      background: var(--bg-dark);
      color: var(--text-primary);
      font-size: 15px;
      outline: none;
      transition: all 0.2s;
    }
    
    .chat-input-area input:focus { 
      border-color: var(--hermes-primary);
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
    }
    
    .chat-input-area input::placeholder { color: var(--text-secondary); }
    
    .chat-input-area button {
      padding: 14px 28px;
      background: linear-gradient(135deg, var(--hermes-primary), var(--hermes-secondary));
      border: none;
      border-radius: 14px;
      color: white;
      font-weight: 600;
      font-size: 15px;
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .chat-input-area button:hover { 
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(99, 102, 241, 0.35);
    }
    
    .chat-input-area button:disabled { 
      opacity: 0.5; 
      cursor: not-allowed;
      transform: none;
      box-shadow: none;
    }
    
    .quick-actions {
      padding: 16px 24px;
      border-top: 1px solid var(--border);
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      background: rgba(99, 102, 241, 0.03);
    }
    
    .quick-btn {
      padding: 10px 18px;
      background: var(--bg-dark);
      border: 1px solid var(--border);
      border-radius: 10px;
      color: var(--text-secondary);
      font-size: 13px;
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    
    .quick-btn:hover {
      border-color: var(--hermes-primary);
      color: var(--text-primary);
      background: rgba(99, 102, 241, 0.1);
    }
    
    .sidebar { display: flex; flex-direction: column; gap: 20px; }
    
    .info-panel, .skills-panel, .memory-panel {
      background: var(--bg-card);
      border-radius: 16px;
      padding: 20px;
      border: 1px solid var(--border);
    }
    
    .panel-title {
      font-size: 13px;
      text-transform: uppercase;
      color: var(--text-secondary);
      letter-spacing: 1.5px;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .info-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }
    
    .info-item {
      background: var(--bg-dark);
      padding: 14px;
      border-radius: 12px;
      text-align: center;
    }
    
    .info-value {
      font-size: 24px;
      font-weight: 700;
      background: linear-gradient(135deg, var(--hermes-primary), var(--hermes-accent));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    
    .info-label {
      font-size: 11px;
      color: var(--text-secondary);
      text-transform: uppercase;
      margin-top: 4px;
    }
    
    .skill-tag {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 14px;
      background: var(--bg-dark);
      border-radius: 20px;
      font-size: 13px;
      margin: 4px;
      border: 1px solid var(--border);
      cursor: pointer;
      transition: all 0.2s;
    }
    
    .skill-tag:hover {
      border-color: var(--hermes-primary);
      background: rgba(99, 102, 241, 0.1);
    }
    
    .memory-item {
      padding: 12px;
      background: var(--bg-dark);
      border-radius: 10px;
      margin-bottom: 8px;
      font-size: 13px;
      color: var(--text-secondary);
      border-left: 3px solid var(--hermes-primary);
    }
    
    .memory-item:last-child { margin-bottom: 0; }
    
    .empty-state {
      text-align: center;
      padding: 30px;
      color: var(--text-secondary);
    }
    
    .empty-state span { 
      display: block; 
      font-size: 40px; 
      margin-bottom: 12px;
      opacity: 0.5;
    }
    
    .serverless-notice {
      background: linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(245, 158, 11, 0.05));
      border: 1px solid rgba(245, 158, 11, 0.3);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 20px;
      text-align: center;
    }
    
    .serverless-notice h3 { color: var(--hermes-warning); margin-bottom: 8px; }
    .serverless-notice p { font-size: 14px; color: var(--text-secondary); }
  </style>
</head>
<body>
  <div class=\"header\">
    <div class=\"header-content\">
      <h1>☤ <span>Hermes</span> Agent</h1>
      <p>Self-Improving AI from Nous Research</p>
      <div class=\"status-bar\" id=\"statusBar\">
        <span class=\"dot\"></span>
        <span id=\"statusText\">Initializing...</span>
      </div>
    </div>
  </div>
  
  <div class=\"container\">
    <div class=\"serverless-notice\" id=\"serverlessNotice\" style=\"display: none;\">
      <h3>⚡ Serverless Mode</h3>
      <p>Hermes CLI is not available in this environment. For full functionality, run the agent-workforce server locally with Hermes installed.</p>
    </div>
    
    <div class=\"capabilities-grid\">
      <div class=\"capability-card\">
        <div class=\"capability-icon\">🧠</div>
        <div class=\"capability-name\">Self-Improving</div>
        <div class=\"capability-desc\">Learns and improves from each interaction</div>
      </div>
      <div class=\"capability-card\">
        <div class=\"capability-icon\">💾</div>
        <div class=\"capability-name\">Memory</div>
        <div class=\"capability-desc\">Persistent memory across sessions</div>
      </div>
      <div class=\"capability-card\">
        <div class=\"capability-icon\">⚡</div>
        <div class=\"capability-name\">Skills</div>
        <div class=\"capability-desc\">Creates and improves skills dynamically</div>
      </div>
      <div class=\"capability-card\">
        <div class=\"capability-icon\">🔧</div>
        <div class=\"capability-name\">40+ Tools</div>
        <div class=\"capability-desc\">Built-in tools for various tasks</div>
      </div>
      <div class=\"capability-card\">
        <div class=\"capability-icon\">💬</div>
        <div class=\"capability-name\">Multi-Platform</div>
        <div class=\"capability-desc\">Telegram, Discord, Slack & more</div>
      </div>
      <div class=\"capability-card\">
        <div class=\"capability-icon\">🎯</div>
        <div class=\"capability-name\">Any Model</div>
        <div class=\"capability-desc\">OpenAI, Anthropic, Nous Portal & more</div>
      </div>
    </div>
    
    <div class=\"main-layout\">
      <div class=\"chat-section\">
        <div class=\"chat-header\">
          <h2>💬 Chat with Hermes</h2>
          <div class=\"model-selector\">
            <button class=\"model-btn active\" onclick=\"setModel('auto', this)\">Auto</button>
            <button class=\"model-btn\" onclick=\"setModel('claude', this)\">Claude</button>
            <button class=\"model-btn\" onclick=\"setModel('gpt-4', this)\">GPT-4</button>
          </div>
        </div>
        
        <div class=\"chat-messages\" id=\"chatMessages\">
          <div class=\"message bot\">
            <span class=\"avatar\">☤</span>
            Greetings! I am Hermes, the self-improving AI agent from Nous Research. I have built-in memory, can create skills from experience, and I'm connected to 40+ tools. How may I assist you today?
            <div class=\"meta\">
              <span>Nous Research</span>
              <span>Just now</span>
            </div>
          </div>
        </div>
        
        <div class=\"chat-input-area\">
          <input type=\"text\" id=\"messageInput\" placeholder=\"Ask Hermes anything...\" onkeypress=\"handleEnter(event)\">
          <button onclick=\"sendMessage()\" id=\"sendBtn\">Send</button>
        </div>
        
        <div class=\"quick-actions\">
          <button class=\"quick-btn\" onclick=\"quickAction('What can you help me with?')\">❓ Help</button>
          <button class=\"quick-btn\" onclick=\"quickAction('Show me your skills')\">🎯 Skills</button>
          <button class=\"quick-btn\" onclick=\"quickAction('What have you learned about me?')\">💾 Memory</button>
          <button class=\"quick-btn\" onclick=\"quickAction('Create a skill for me')\">⚡ Create Skill</button>
          <button class=\"quick-btn\" onclick=\"quickAction('Tell me about your capabilities')\">🔧 Capabilities</button>
        </div>
      </div>
      
      <div class=\"sidebar\">
        <div class=\"info-panel\">
          <div class=\"panel-title\">📊 Agent Status</div>
          <div class=\"info-grid\">
            <div class=\"info-item\">
              <div class=\"info-value\" id=\"sessionCount\">0</div>
              <div class=\"info-label\">Sessions</div>
            </div>
            <div class=\"info-item\">
              <div class=\"info-value\" id=\"messagesToday\">0</div>
              <div class=\"info-label\">Messages</div>
            </div>
            <div class=\"info-item\">
              <div class=\"info-value\" id=\"skillsCreated\">0</div>
              <div class=\"info-label\">Skills</div>
            </div>
            <div class=\"info-item\">
              <div class=\"info-value\" id=\"uptime\">--</div>
              <div class=\"info-label\">Uptime</div>
            </div>
          </div>
        </div>
        
        <div class=\"skills-panel\">
          <div class=\"panel-title\">🎯 Available Skills</div>
          <div id=\"skillsList\">
            <span class=\"skill-tag\" onclick=\"quickAction('Use coding skill')\">💻 Coding</span>
            <span class=\"skill-tag\" onclick=\"quickAction('Use research skill')\">🔍 Research</span>
            <span class=\"skill-tag\" onclick=\"quickAction('Use writing skill')\">✍️ Writing</span>
            <span class=\"skill-tag\" onclick=\"quickAction('Use analysis skill')\">📊 Analysis</span>
            <span class=\"skill-tag\" onclick=\"quickAction('Use memory skill')\">🧠 Memory</span>
          </div>
        </div>
        
        <div class=\"memory-panel\">
          <div class=\"panel-title\">💾 Recent Memory</div>
          <div id=\"memoryList\">
            <div class=\"empty-state\">
              <span>🧠</span>
              No memories yet
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    var currentModel = 'auto';
    var sessionId = 'HERMES-' + Date.now().toString(36);
    var messageCount = 0;
    var startTime = Date.now();
    var isLoading = false;
    var isServerless = false;
    
    // Initialize
    checkHermesStatus();
    setInterval(updateUptime, 1000);
    
    async function checkHermesStatus() {
      try {
        var response = await fetch('/api/hermes/status');
        if (response.ok) {
          var data = await response.json();
          updateStatus(data);
        } else {
          setDisconnected('API Error');
        }
      } catch (e) {
        setDisconnected('Unavailable');
      }
    }
    
    function updateStatus(data) {
      var statusBar = document.getElementById('statusBar');
      var statusText = document.getElementById('statusText');
      
      // Check if Hermes is actually available (not serverless)
      var hermesStatus = data.hermesStatus || {};
      
      if (hermesStatus.sessionId && !hermesStatus.initialized) {
        // Serverless mode
        statusBar.classList.add('serverless');
        statusBar.classList.remove('connected');
        statusText.textContent = 'Serverless Mode';
        document.getElementById('serverlessNotice').style.display = 'block';
        isServerless = true;
      } else if (data.status === 'idle' || data.status === 'working') {
        statusBar.classList.add('connected');
        statusText.textContent = 'Connected - ' + data.name;
        isServerless = false;
      } else {
        statusBar.classList.remove('connected');
        statusText.textContent = 'Status: ' + data.status;
      }
      
      // Update stats
      document.getElementById('sessionCount').textContent = '1';
    }
    
    function setDisconnected(reason) {
      var statusBar = document.getElementById('statusBar');
      statusBar.classList.remove('connected', 'serverless');
      document.getElementById('statusText').textContent = reason || 'Disconnected';
      document.getElementById('serverlessNotice').style.display = 'block';
      isServerless = true;
    }
    
    function setModel(model, btn) {
      currentModel = model;
      document.querySelectorAll('.model-btn').forEach(function(b) {
        b.classList.remove('active');
      });
      btn.classList.add('active');
      addMessage('bot', 'Model preference set to ' + model + '. I will use the best available model for your task.', 'SYSTEM');
    }
    
    async function sendMessage() {
      if (isLoading) return;
      
      var input = document.getElementById('messageInput');
      var message = input.value.trim();
      if (!message) return;
      
      if (isServerless) {
        addMessage('bot', 'Hermes CLI is not available in this serverless environment. For full functionality, please run the agent-workforce server locally.', 'SYSTEM');
        return;
      }
      
      addMessage('user', message);
      input.value = '';
      setLoading(true);
      showTypingIndicator();
      messageCount++;
      document.getElementById('messagesToday').textContent = messageCount;
      
      try {
        var response = await fetch('/api/hermes/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: message,
            sessionId: sessionId
          })
        });
        
        hideTypingIndicator();
        
        if (response.ok) {
          var data = await response.json();
          addMessage('bot', data.response, 'HERMES');
        } else {
          var errorData = await response.json().catch(function() { return {}; });
          addMessage('bot', 'Error: ' + (errorData.error || 'Failed to get response from Hermes'), 'ERROR');
        }
      } catch (e) {
        hideTypingIndicator();
        addMessage('bot', 'Unable to connect to Hermes service. Please check your connection.', 'ERROR');
      }
      
      setLoading(false);
    }
    
    function quickAction(message) {
      document.getElementById('messageInput').value = message;
      sendMessage();
    }
    
    function handleEnter(e) {
      if (e.key === 'Enter') sendMessage();
    }
    
    function addMessage(type, text, sender) {
      var chat = document.getElementById('chatMessages');
      var div = document.createElement('div');
      div.className = 'message ' + type;
      
      var avatar = type === 'bot' ? '☤' : '👤';
      var time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      
      if (type === 'bot' && sender) {
        div.innerHTML = 
          '<span class=\"avatar\">' + avatar + '</span>' + 
          text +
          '<div class=\"meta\"><span>' + sender + '</span><span>' + time + '</span></div>';
      } else if (type === 'bot') {
        div.innerHTML = '<span class=\"avatar\">' + avatar + '</span>' + text;
      } else {
        div.innerHTML = 
          '<span class=\"avatar\">' + avatar + '</span>' + 
          text +
          '<div class=\"meta\"><span>You</span><span>' + time + '</span></div>';
      }
      
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
    }
    
    function showTypingIndicator() {
      var chat = document.getElementById('chatMessages');
      var div = document.createElement('div');
      div.className = 'typing-indicator';
      div.id = 'typingIndicator';
      div.innerHTML = '<span></span><span></span><span></span>';
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
    }
    
    function hideTypingIndicator() {
      var indicator = document.getElementById('typingIndicator');
      if (indicator) indicator.remove();
    }
    
    function setLoading(loading) {
      isLoading = loading;
      var btn = document.getElementById('sendBtn');
      var input = document.getElementById('messageInput');
      btn.disabled = loading;
      input.disabled = loading;
      btn.textContent = loading ? 'Thinking...' : 'Send';
    }
    
    function updateUptime() {
      if (startTime) {
        var elapsed = Math.floor((Date.now() - startTime) / 1000);
        var hours = Math.floor(elapsed / 3600);
        var minutes = Math.floor((elapsed % 3600) / 60);
        var seconds = elapsed % 60;
        document.getElementById('uptime').textContent = 
          hours.toString().padStart(2, '0') + ':' + 
          minutes.toString().padStart(2, '0') + ':' + 
          seconds.toString().padStart(2, '0');
      }
    }
  </script>
</body>
</html>`
}

export default router