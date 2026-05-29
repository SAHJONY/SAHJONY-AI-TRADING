/**
 * AI Receptionist Demo Page
 * Interactive demo showcasing ARIA, CHRONOS, WIKI, and CONNECT agents
 */

import express, { Request, Response } from 'express'

const router = express.Router()

export function setupReceptionistDemo(app: express.Application): void {
  // Demo page at /ai-receptionist
  app.get('/ai-receptionist', (_req: Request, res: Response) => {
    res.send(getDemoHTML())
  })
  
  console.log('  AI Receptionist Demo: http://localhost:3000/ai-receptionist')
}

function getDemoHTML(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Receptionist - Interactive Demo</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    
    :root {
      --primary: #6366f1;
      --primary-dark: #4f46e5;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --bg-dark: #0f172a;
      --bg-card: #1e293b;
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
      background: linear-gradient(135deg, var(--primary), #8b5cf6);
      padding: 32px 24px;
      text-align: center;
    }
    
    .header h1 { font-size: 32px; margin-bottom: 8px; }
    .header p { opacity: 0.9; font-size: 18px; }
    
    .connection-status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 16px;
      background: rgba(255,255,255,0.1);
      border-radius: 20px;
      font-size: 14px;
      margin-top: 16px;
    }
    
    .connection-status .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--danger);
    }
    
    .connection-status.connected .dot { background: var(--success); }
    
    .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
    
    .agent-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 16px;
      margin: 24px 0;
    }
    
    .agent-card {
      background: var(--bg-card);
      border-radius: 16px;
      padding: 20px;
      border: 2px solid var(--border);
      cursor: pointer;
      transition: all 0.2s;
    }
    
    .agent-card:hover { border-color: var(--primary); }
    .agent-card.active { border-color: var(--primary); background: rgba(99, 102, 241, 0.1); }
    
    .agent-icon { font-size: 32px; margin-bottom: 12px; }
    .agent-name { font-size: 18px; font-weight: 600; margin-bottom: 4px; }
    .agent-role { color: var(--primary); font-size: 14px; margin-bottom: 8px; }
    .agent-desc { color: var(--text-secondary); font-size: 13px; }
    .agent-card.active .agent-desc { color: var(--text-primary); }
    
    .main-grid {
      display: grid;
      grid-template-columns: 1fr 350px;
      gap: 24px;
    }
    
    @media (max-width: 900px) {
      .main-grid { grid-template-columns: 1fr; }
    }
    
    .chat-section {
      background: var(--bg-card);
      border-radius: 16px;
      overflow: hidden;
    }
    
    .chat-header {
      padding: 16px 20px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    
    .chat-header h2 { font-size: 16px; }
    
    .industry-selector {
      display: flex;
      gap: 8px;
    }
    
    .industry-btn {
      padding: 6px 12px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: transparent;
      color: var(--text-secondary);
      font-size: 12px;
      cursor: pointer;
      transition: all 0.2s;
    }
    
    .industry-btn:hover { border-color: var(--primary); color: var(--text-primary); }
    .industry-btn.active { background: var(--primary); border-color: var(--primary); color: white; }
    
    .chat-messages {
      height: 400px;
      overflow-y: auto;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    
    .message {
      max-width: 80%;
      padding: 12px 16px;
      border-radius: 16px;
      line-height: 1.5;
      animation: fadeIn 0.3s ease;
    }
    
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    
    .message.bot { align-self: flex-start; background: var(--bg-dark); border-bottom-left-radius: 4px; }
    .message.user { align-self: flex-end; background: var(--primary); color: white; border-bottom-right-radius: 4px; }
    
    .message .sender { font-size: 12px; color: var(--primary); margin-bottom: 4px; font-weight: 600; }
    .message.bot .sender { color: var(--success); }
    
    .typing-indicator {
      display: flex;
      gap: 4px;
      padding: 12px 16px;
      background: var(--bg-dark);
      border-radius: 16px;
      border-bottom-left-radius: 4px;
      width: fit-content;
    }
    
    .typing-indicator span {
      width: 8px;
      height: 8px;
      background: var(--text-secondary);
      border-radius: 50%;
      animation: bounce 1.4s infinite;
    }
    
    .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
    .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
    
    @keyframes bounce {
      0%, 60%, 100% { transform: translateY(0); }
      30% { transform: translateY(-6px); }
    }
    
    .chat-input-area {
      padding: 16px 20px;
      border-top: 1px solid var(--border);
      display: flex;
      gap: 12px;
    }
    
    .chat-input-area input {
      flex: 1;
      padding: 12px 16px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: var(--bg-dark);
      color: var(--text-primary);
      font-size: 15px;
      outline: none;
      transition: border-color 0.2s;
    }
    
    .chat-input-area input:focus { border-color: var(--primary); }
    .chat-input-area input::placeholder { color: var(--text-secondary); }
    
    .chat-input-area button {
      padding: 12px 24px;
      background: var(--primary);
      border: none;
      border-radius: 12px;
      color: white;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }
    
    .chat-input-area button:hover { background: var(--primary-dark); }
    .chat-input-area button:disabled { opacity: 0.5; cursor: not-allowed; }
    
    .quick-actions {
      padding: 12px 20px;
      border-top: 1px solid var(--border);
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    
    .quick-btn {
      padding: 8px 14px;
      background: var(--bg-dark);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text-secondary);
      font-size: 13px;
      cursor: pointer;
      transition: all 0.2s;
    }
    
    .quick-btn:hover {
      border-color: var(--primary);
      color: var(--text-primary);
    }
    
    .sidebar { display: flex; flex-direction: column; gap: 16px; }
    
    .stats-panel, .queue-panel {
      background: var(--bg-card);
      border-radius: 16px;
      padding: 20px;
    }
    
    .panel-title {
      font-size: 14px;
      text-transform: uppercase;
      color: var(--text-secondary);
      letter-spacing: 1px;
      margin-bottom: 16px;
    }
    
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }
    
    .stat-item {
      text-align: center;
      padding: 16px;
      background: var(--bg-dark);
      border-radius: 12px;
    }
    
    .stat-value {
      font-size: 28px;
      font-weight: 700;
      color: var(--primary);
    }
    
    .stat-label {
      font-size: 11px;
      color: var(--text-secondary);
      text-transform: uppercase;
      margin-top: 4px;
    }
    
    .visitor-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px;
      background: var(--bg-dark);
      border-radius: 8px;
      margin-bottom: 8px;
    }
    
    .visitor-info h4 { font-size: 14px; margin-bottom: 2px; }
    .visitor-info p { font-size: 12px; color: var(--text-secondary); }
    
    .visitor-status {
      padding: 4px 10px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
    }
    
    .visitor-status.waiting { background: var(--warning); color: black; }
    .visitor-status.served { background: var(--success); color: white; }
    
    .empty-state {
      text-align: center;
      padding: 24px;
      color: var(--text-secondary);
      font-size: 14px;
    }
    
    .empty-state span { display: block; font-size: 32px; margin-bottom: 8px; opacity: 0.5; }
  </style>
</head>
<body>
  <div class="header">
    <h1>🤖 AI Receptionist</h1>
    <p>Multi-Agent Intelligent Receptionist System</p>
    <div class="connection-status" id="connectionStatus">
      <span class="dot"></span>
      <span id="connectionText">Checking API...</span>
    </div>
  </div>
  
  <div class="container">
    <div class="agent-grid">
      <div class="agent-card active" data-agent="aria" onclick="selectAgent('aria')">
        <div class="agent-icon">🎙️</div>
        <div class="agent-name">ARIA</div>
        <div class="agent-role">Voice & Greeting Agent</div>
        <div class="agent-desc">Warm welcome, visitor check-in, information collection</div>
      </div>
      <div class="agent-card" data-agent="chronos" onclick="selectAgent('chronos')">
        <div class="agent-icon">📅</div>
        <div class="agent-name">CHRONOS</div>
        <div class="agent-role">Scheduling Agent</div>
        <div class="agent-desc">Appointment booking, availability check, reminders</div>
      </div>
      <div class="agent-card" data-agent="wiki" onclick="selectAgent('wiki')">
        <div class="agent-icon">📚</div>
        <div class="agent-name">WIKI</div>
        <div class="agent-role">Knowledge Agent</div>
        <div class="agent-desc">FAQ answers, directions, business information</div>
      </div>
      <div class="agent-card" data-agent="connect" onclick="selectAgent('connect')">
        <div class="agent-icon">🔗</div>
        <div class="agent-name">CONNECT</div>
        <div class="agent-role">Escalation Agent</div>
        <div class="agent-desc">Human handoff, complaint handling, ticket creation</div>
      </div>
    </div>
    
    <div class="main-grid">
      <div class="chat-section">
        <div class="chat-header">
          <h2>💬 Chat with AI Receptionist</h2>
          <div class="industry-selector">
            <button class="industry-btn active" onclick="setIndustry('corporate', this)">Corporate</button>
            <button class="industry-btn" onclick="setIndustry('healthcare', this)">Healthcare</button>
            <button class="industry-btn" onclick="setIndustry('hospitality', this)">Hospitality</button>
          </div>
        </div>
        
        <div class="chat-messages" id="chatMessages">
          <div class="message bot">
            <div class="sender">ARIA</div>
            Hello! I'm ARIA, your AI receptionist. How may I assist you today?
          </div>
        </div>
        
        <div class="chat-input-area">
          <input type="text" id="messageInput" placeholder="Type your message..." onkeypress="handleEnter(event)">
          <button onclick="sendMessage()" id="sendBtn">Send</button>
        </div>
        
        <div class="quick-actions" id="quickActions">
          <button class="quick-btn" onclick="quickAction('I need to schedule an appointment')">📅 Schedule</button>
          <button class="quick-btn" onclick="quickAction('What are your business hours?')">❓ Hours</button>
          <button class="quick-btn" onclick="quickAction('I need to speak to someone')">👤 Human</button>
          <button class="quick-btn" onclick="quickAction('Where is your office?')">📍 Directions</button>
        </div>
      </div>
      
      <div class="sidebar">
        <div class="stats-panel">
          <div class="panel-title">📊 Today's Stats</div>
          <div class="stats-grid">
            <div class="stat-item">
              <div class="stat-value" id="visitorsToday">0</div>
              <div class="stat-label">Visitors</div>
            </div>
            <div class="stat-item">
              <div class="stat-value" id="appointmentsToday">0</div>
              <div class="stat-label">Appointments</div>
            </div>
            <div class="stat-item">
              <div class="stat-value" id="queriesAnswered">0</div>
              <div class="stat-label">Queries</div>
            </div>
            <div class="stat-item">
              <div class="stat-value" id="resolutionRate">100%</div>
              <div class="stat-label">Resolution</div>
            </div>
          </div>
        </div>
        
        <div class="queue-panel">
          <div class="panel-title">👥 Visitor Queue</div>
          <div id="visitorQueue">
            <div class="empty-state">
              <span>👻</span>
              No visitors waiting
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    var currentAgent = 'aria';
    var currentIndustry = 'corporate';
    var visitorId = 'DEMO-' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
    var isLoading = false;
    
    // Initialize
    checkApiConnection();
    refreshStats();
    setInterval(refreshStats, 30000);
    
    async function checkApiConnection() {
      try {
        var response = await fetch('/api/receptionist/stats');
        if (response.ok) {
          document.getElementById('connectionStatus').classList.add('connected');
          document.getElementById('connectionText').textContent = 'Connected to API';
        } else {
          setDisconnected();
        }
      } catch (e) {
        setDisconnected();
      }
    }
    
    function setDisconnected() {
      document.getElementById('connectionStatus').classList.remove('connected');
      document.getElementById('connectionText').textContent = 'Demo Mode (API unavailable)';
    }
    
    function selectAgent(agent) {
      currentAgent = agent;
      document.querySelectorAll('.agent-card').forEach(function(card) {
        card.classList.remove('active');
      });
      document.querySelector('.agent-card[data-agent="' + agent + '"]').classList.add('active');
      
      var agentNames = { aria: 'ARIA', chronos: 'CHRONOS', wiki: 'WIKI', connect: 'CONNECT' };
      addMessage('bot', 'Switched to ' + agentNames[agent] + ' agent. How can I help you?', agentNames[agent]);
    }
    
    function setIndustry(industry, btn) {
      currentIndustry = industry;
      document.querySelectorAll('.industry-btn').forEach(function(b) {
        b.classList.remove('active');
      });
      btn.classList.add('active');
      addMessage('bot', 'Industry context set to: ' + industry.charAt(0).toUpperCase() + industry.slice(1) + '. How may I assist you?', 'ARIA');
    }
    
    async function sendMessage() {
      if (isLoading) return;
      
      var input = document.getElementById('messageInput');
      var message = input.value.trim();
      if (!message) return;
      
      addMessage('user', message);
      input.value = '';
      setLoading(true);
      showTypingIndicator();
      
      try {
        var response = await fetch('/api/receptionist/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: message,
            sessionId: visitorId,
            industry: currentIndustry
          })
        });
        
        hideTypingIndicator();
        
        if (response.ok) {
          var data = await response.json();
          addMessage('bot', data.response, data.agent);
          
          if (data.requiresHumanEscalation || data.requiresEscalation) {
            setTimeout(function() {
              addMessage('bot', 'A human agent will be with you shortly.', 'SYSTEM');
            }, 1500);
          }
        } else {
          addMessage('bot', 'Sorry, I encountered an error. Please try again.', 'ERROR');
        }
      } catch (e) {
        hideTypingIndicator();
        addMessage('bot', 'Unable to connect to the AI service. Please check your connection.', 'ERROR');
      }
      
      setLoading(false);
      refreshStats();
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
      
      if (type === 'bot' && sender) {
        div.innerHTML = '<div class="sender">' + sender + '</div>' + text;
      } else {
        div.innerHTML = text;
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
    }
    
    async function refreshStats() {
      try {
        var response = await fetch('/api/receptionist/context');
        if (response.ok) {
          var data = await response.json();
          document.getElementById('visitorsToday').textContent = data.visitors || 0;
          document.getElementById('appointmentsToday').textContent = data.appointments || 0;
          document.getElementById('queriesAnswered').textContent = data.stats ? data.stats.agentStats.wiki.queriesAnswered : 0;
        }
      } catch (e) {
        // Silently fail - stats are optional
      }
      
      try {
        var visitorsRes = await fetch('/api/receptionist/visitors');
        if (visitorsRes.ok) {
          var visitorsData = await visitorsRes.json();
          updateVisitorQueue(visitorsData);
        }
      } catch (e) {
        // Silently fail
      }
    }
    
    function updateVisitorQueue(data) {
      var queue = document.getElementById('visitorQueue');
      if (data.waiting && data.waiting.length > 0) {
        queue.innerHTML = data.waiting.map(function(v) {
          return '<div class="visitor-item">' +
            '<div class="visitor-info"><h4>' + v.name + '</h4><p>' + v.purpose + '</p></div>' +
            '<span class="visitor-status ' + v.status + '">' + v.status + '</span>' +
          '</div>';
        }).join('');
      } else {
        queue.innerHTML = '<div class="empty-state"><span>👻</span>No visitors waiting</div>';
      }
    }
  </script>
</body>
</html>`
}

export default router