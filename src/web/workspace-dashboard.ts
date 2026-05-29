import express, { Request, Response } from 'express';

export function setupWorkspaceDashboard(app: express.Application) {
  // HTML for the shareable workspace dashboard
  const html = `
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>Agent Workforce - Shared Workspace</title>
  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">
  <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap\" rel=\"stylesheet\">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    
    :root {
      --primary: #6366f1;
      --primary-dark: #4f46e5;
      --bg-dark: #0f0f1a;
      --bg-card: rgba(30, 30, 50, 0.8);
      --glass: rgba(255, 255, 255, 0.05);
      --glass-border: rgba(255, 255, 255, 0.1);
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --success: #10b981;
      --warning: #f59e0b;
    }
    
    body {
      font-family: 'Inter', -apple-system, sans-serif;
      background: var(--bg-dark);
      color: var(--text);
      min-height: 100vh;
      overflow-x: hidden;
    }
    
    /* Animated background */
    .bg-animation {
      position: fixed;
      inset: 0;
      z-index: -1;
      background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #0f0f1a 100%);
    }
    
    .bg-animation::before {
      content: '';
      position: absolute;
      width: 200%;
      height: 200%;
      top: -50%;
      left: -50%;
      background: radial-gradient(circle at 30% 30%, rgba(99, 102, 241, 0.1) 0%, transparent 50%),
                  radial-gradient(circle at 70% 70%, rgba(16, 185, 129, 0.08) 0%, transparent 50%);
      animation: bgPulse 15s ease-in-out infinite;
    }
    
    @keyframes bgPulse {
      0%, 100% { transform: translate(0, 0) rotate(0deg); }
      50% { transform: translate(-5%, -5%) rotate(180deg); }
    }
    
    /* Header */
    .header {
      background: var(--glass);
      backdrop-filter: blur(20px);
      border-bottom: 1px solid var(--glass-border);
      padding: 16px 32px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    
    .logo {
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 700;
      font-size: 20px;
    }
    
    .logo-icon {
      width: 36px;
      height: 36px;
      background: linear-gradient(135deg, var(--primary), #8b5cf6);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 18px;
    }
    
    .share-section {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    
    .share-btn {
      background: var(--primary);
      color: white;
      border: none;
      padding: 10px 20px;
      border-radius: 8px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .share-btn:hover {
      background: var(--primary-dark);
      transform: translateY(-1px);
    }
    
    /* Main container */
    .container {
      max-width: 1400px;
      margin: 0 auto;
      padding: 32px;
    }
    
    /* Workspace info */
    .workspace-info {
      text-align: center;
      margin-bottom: 32px;
    }
    
    .workspace-name {
      font-size: 32px;
      font-weight: 700;
      margin-bottom: 8px;
      background: linear-gradient(135deg, var(--text), var(--text-muted));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    
    .workspace-meta {
      color: var(--text-muted);
      font-size: 14px;
    }
    
    /* Stats bar */
    .stats-bar {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 16px;
      margin-bottom: 32px;
    }
    
    .stat-card {
      background: var(--bg-card);
      backdrop-filter: blur(10px);
      border: 1px solid var(--glass-border);
      border-radius: 16px;
      padding: 20px;
      text-align: center;
    }
    
    .stat-value {
      font-size: 28px;
      font-weight: 700;
      color: var(--primary);
      margin-bottom: 4px;
    }
    
    .stat-label {
      font-size: 12px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    
    /* Main grid */
    .main-grid {
      display: grid;
      grid-template-columns: 1fr 350px;
      gap: 24px;
    }
    
    @media (max-width: 1024px) {
      .main-grid { grid-template-columns: 1fr; }
    }
    
    /* Chat section */
    .chat-section {
      background: var(--bg-card);
      backdrop-filter: blur(10px);
      border: 1px solid var(--glass-border);
      border-radius: 20px;
      overflow: hidden;
    }
    
    .chat-header {
      padding: 20px 24px;
      border-bottom: 1px solid var(--glass-border);
      display: flex;
      align-items: center;
      gap: 12px;
    }
    
    .chat-status {
      width: 10px;
      height: 10px;
      background: var(--success);
      border-radius: 50%;
      animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    
    .chat-title {
      font-weight: 600;
      font-size: 16px;
    }
    
    .chat-messages {
      height: 400px;
      overflow-y: auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    
    .message {
      display: flex;
      gap: 12px;
      animation: messageIn 0.3s ease;
    }
    
    @keyframes messageIn {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    
    .message.user { flex-direction: row-reverse; }
    
    .message-avatar {
      width: 40px;
      height: 40px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 14px;
      flex-shrink: 0;
    }
    
    .message.hermes .message-avatar {
      background: linear-gradient(135deg, var(--primary), #8b5cf6);
    }
    
    .message.user .message-avatar {
      background: var(--glass-border);
    }
    
    .message-content {
      max-width: 70%;
      padding: 16px 20px;
      border-radius: 16px;
      font-size: 14px;
      line-height: 1.6;
    }
    
    .message.hermes .message-content {
      background: var(--glass);
      border: 1px solid var(--glass-border);
      border-radius: 16px 16px 16px 4px;
    }
    
    .message.user .message-content {
      background: var(--primary);
      border-radius: 16px 16px 4px 16px;
    }
    
    .typing-indicator {
      display: flex;
      gap: 4px;
      padding: 8px 0;
    }
    
    .typing-indicator span {
      width: 8px;
      height: 8px;
      background: var(--text-muted);
      border-radius: 50%;
      animation: typingBounce 1.4s infinite;
    }
    
    .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
    .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
    
    @keyframes typingBounce {
      0%, 60%, 100% { transform: translateY(0); }
      30% { transform: translateY(-6px); }
    }
    
    .chat-input-area {
      padding: 20px 24px;
      border-top: 1px solid var(--glass-border);
      display: flex;
      gap: 12px;
    }
    
    .chat-input {
      flex: 1;
      background: var(--glass);
      border: 1px solid var(--glass-border);
      border-radius: 12px;
      padding: 14px 18px;
      color: var(--text);
      font-size: 14px;
      font-family: inherit;
      resize: none;
      outline: none;
      transition: border-color 0.2s;
    }
    
    .chat-input:focus {
      border-color: var(--primary);
    }
    
    .send-btn {
      background: var(--primary);
      color: white;
      border: none;
      width: 48px;
      height: 48px;
      border-radius: 12px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;
    }
    
    .send-btn:hover {
      background: var(--primary-dark);
      transform: scale(1.05);
    }
    
    .send-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
      transform: none;
    }
    
    /* Sidebar */
    .sidebar {
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    
    .panel {
      background: var(--bg-card);
      backdrop-filter: blur(10px);
      border: 1px solid var(--glass-border);
      border-radius: 16px;
      padding: 20px;
    }
    
    .panel-title {
      font-weight: 600;
      font-size: 14px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .capabilities-list {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    
    .capability-tag {
      background: var(--glass);
      border: 1px solid var(--glass-border);
      padding: 8px 14px;
      border-radius: 20px;
      font-size: 12px;
      color: var(--text-muted);
      transition: all 0.2s;
      cursor: pointer;
    }
    
    .capability-tag:hover {
      background: var(--primary);
      color: white;
      border-color: var(--primary);
    }
    
    .quick-actions {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    
    .quick-action {
      background: var(--glass);
      border: 1px solid var(--glass-border);
      padding: 14px 16px;
      border-radius: 12px;
      color: var(--text);
      font-size: 14px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 12px;
      transition: all 0.2s;
      text-align: left;
      font-family: inherit;
    }
    
    .quick-action:hover {
      background: var(--primary);
      border-color: var(--primary);
      transform: translateX(4px);
    }
    
    .quick-action-icon {
      width: 32px;
      height: 32px;
      background: var(--glass);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    
    /* Toast notification */
    .toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: var(--bg-card);
      backdrop-filter: blur(10px);
      border: 1px solid var(--glass-border);
      padding: 16px 24px;
      border-radius: 12px;
      font-size: 14px;
      display: flex;
      align-items: center;
      gap: 12px;
      transform: translateY(100px);
      opacity: 0;
      transition: all 0.3s;
      z-index: 1000;
    }
    
    .toast.show {
      transform: translateY(0);
      opacity: 1;
    }
    
    .toast-icon {
      color: var(--success);
    }
    
    /* New workspace modal */
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.8);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 200;
    }
    
    .modal-overlay.show {
      display: flex;
    }
    
    .modal {
      background: var(--bg-card);
      border: 1px solid var(--glass-border);
      border-radius: 20px;
      padding: 32px;
      max-width: 400px;
      width: 90%;
    }
    
    .modal-title {
      font-size: 20px;
      font-weight: 700;
      margin-bottom: 20px;
    }
    
    .modal-input {
      width: 100%;
      background: var(--glass);
      border: 1px solid var(--glass-border);
      border-radius: 12px;
      padding: 14px 18px;
      color: var(--text);
      font-size: 14px;
      font-family: inherit;
      margin-bottom: 20px;
      outline: none;
    }
    
    .modal-input:focus {
      border-color: var(--primary);
    }
    
    .modal-actions {
      display: flex;
      gap: 12px;
    }
    
    .modal-btn {
      flex: 1;
      padding: 12px 20px;
      border-radius: 10px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      font-family: inherit;
    }
    
    .modal-btn.primary {
      background: var(--primary);
      color: white;
      border: none;
    }
    
    .modal-btn.primary:hover {
      background: var(--primary-dark);
    }
    
    .modal-btn.secondary {
      background: transparent;
      color: var(--text-muted);
      border: 1px solid var(--glass-border);
    }
    
    .modal-btn.secondary:hover {
      background: var(--glass);
    }
    
    /* Loading state */
    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      height: 200px;
      color: var(--text-muted);
    }
    
    .loading-spinner {
      width: 32px;
      height: 32px;
      border: 3px solid var(--glass-border);
      border-top-color: var(--primary);
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin-right: 12px;
    }
    
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    
    /* Copy input */
    .copy-input-container {
      display: flex;
      gap: 8px;
    }
    
    .copy-input {
      flex: 1;
      background: var(--glass);
      border: 1px solid var(--glass-border);
      border-radius: 8px;
      padding: 10px 14px;
      color: var(--text);
      font-size: 12px;
      font-family: monospace;
    }
    
    .copy-icon-btn {
      background: var(--glass);
      border: 1px solid var(--glass-border);
      border-radius: 8px;
      padding: 10px 14px;
      cursor: pointer;
      transition: all 0.2s;
      color: var(--text-muted);
    }
    
    .copy-icon-btn:hover {
      background: var(--primary);
      color: white;
    }
  </style>
</head>
<body>
  <div class=\"bg-animation\"></div>
  
  <header class=\"header\">
    <div class=\"logo\">
      <div class=\"logo-icon\">H</div>
      <span>Agent Workforce</span>
    </div>
    <div class=\"share-section\">
      <button class=\"share-btn\" onclick=\"createNewWorkspace()\">
        <span>+</span> New Workspace
      </button>
    </div>
  </header>
  
  <div class=\"container\">
    <div class=\"workspace-info\">
      <h1 class=\"workspace-name\" id=\"workspaceName\">Loading...</h1>
      <p class=\"workspace-meta\" id=\"workspaceMeta\"></p>
    </div>
    
    <div class=\"stats-bar\">
      <div class=\"stat-card\">
        <div class=\"stat-value\" id=\"messageCount\">0</div>
        <div class=\"stat-label\">Messages</div>
      </div>
      <div class=\"stat-card\">
        <div class=\"stat-value\" id=\"interactionCount\">0</div>
        <div class=\"stat-label\">Interactions</div>
      </div>
      <div class=\"stat-card\">
        <div class=\"stat-value\" id=\"uptimeDisplay\">0m</div>
        <div class=\"stat-label\">Uptime</div>
      </div>
      <div class=\"stat-card\">
        <div class=\"stat-value\" id=\"statusIndicator\">--</div>
        <div class=\"stat-label\">Status</div>
      </div>
    </div>
    
    <div class=\"main-grid\">
      <div class=\"chat-section\">
        <div class=\"chat-header\">
          <div class=\"chat-status\"></div>
          <div class=\"chat-title\">Hermes AI Assistant</div>
        </div>
        <div class=\"chat-messages\" id=\"chatMessages\">
          <div class=\"loading\">
            <div class=\"loading-spinner\"></div>
            Loading workspace...
          </div>
        </div>
        <div class=\"chat-input-area\">
          <textarea class=\"chat-input\" id=\"chatInput\" placeholder=\"Ask Hermes anything...\" rows=\"1\"></textarea>
          <button class=\"send-btn\" id=\"sendBtn\" onclick=\"sendMessage()\">→</button>
        </div>
      </div>
      
      <div class=\"sidebar\">
        <div class=\"panel\">
          <div class=\"panel-title\">Share Workspace</div>
          <div class=\"copy-input-container\">
            <input type=\"text\" class=\"copy-input\" id=\"shareLink\" readonly value=\"Loading...\">
            <button class=\"copy-icon-btn\" onclick=\"copyShareLink()\" title=\"Copy link\">📋</button>
          </div>
        </div>
        
        <div class=\"panel\">
          <div class=\"panel-title\">Capabilities</div>
          <div class=\"capabilities-list\">
            <span class=\"capability-tag\" onclick=\"quickAction('What can you help me with?')\">Help</span>
            <span class=\"capability-tag\" onclick=\"quickAction('Show me your capabilities')\">Capabilities</span>
            <span class=\"capability-tag\" onclick=\"quickAction('Analyze this code for me')\">Code Analysis</span>
            <span class=\"capability-tag\" onclick=\"quickAction('Explain a concept')\">Explain</span>
            <span class=\"capability-tag\" onclick=\"quickAction('Solve this problem')\">Problem Solve</span>
          </div>
        </div>
        
        <div class=\"panel\">
          <div class=\"panel-title\">Quick Actions</div>
          <div class=\"quick-actions\">
            <button class=\"quick-action\" onclick=\"quickAction('Give me a status update')\">
              <div class=\"quick-action-icon\">📊</div>
              <span>Status Update</span>
            </button>
            <button class=\"quick-action\" onclick=\"quickAction('What have we worked on?')\">
              <div class=\"quick-action-icon\">📝</div>
              <span>Session Summary</span>
            </button>
            <button class=\"quick-action\" onclick=\"quickAction('Reset conversation context')\">
              <div class=\"quick-action-icon\">🔄</div>
              <span>Reset Context</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
  
  <!-- Toast -->
  <div class=\"toast\" id=\"toast\">
    <span class=\"toast-icon\">✓</span>
    <span id=\"toastMessage\">Link copied!</span>
  </div>
  
  <!-- New Workspace Modal -->
  <div class=\"modal-overlay\" id=\"newWorkspaceModal\">
    <div class=\"modal\">
      <h2 class=\"modal-title\">Create New Workspace</h2>
      <input type=\"text\" class=\"modal-input\" id=\"newWorkspaceName\" placeholder=\"Workspace name...\">
      <div class=\"modal-actions\">
        <button class=\"modal-btn secondary\" onclick=\"closeModal()\">Cancel</button>
        <button class=\"modal-btn primary\" onclick=\"confirmNewWorkspace()\">Create</button>
      </div>
    </div>
  </div>
  
  <script>
    // Workspace state
    let currentWorkspace = null;
    let shareId = null;
    let startTime = null;
    let isTyping = false;
    
    // Initialize
    async function init() {
      // Get share ID from URL or create new workspace
      const pathParts = window.location.pathname.split('/');
      const potentialShareId = pathParts[pathParts.length - 1];
      
      if (potentialShareId && potentialShareId.length === 6) {
        shareId = potentialShareId;
        await loadWorkspaceByShareId(shareId);
      } else {
        await createNewWorkspace();
      }
      
      startTime = Date.now();
      setInterval(updateUptime, 60000);
    }
    
    // Load workspace by share ID
    async function loadWorkspaceByShareId(shareId) {
      try {
        const response = await fetch('/api/workspace/share/' + shareId);
        if (!response.ok) throw new Error('Workspace not found');
        currentWorkspace = await response.json();
        renderWorkspace();
      } catch (error) {
        // Create new workspace if not found
        await createNewWorkspace();
      }
    }
    
    // Create new workspace
    async function createNewWorkspace() {
      try {
        const response = await fetch('/api/workspace', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: 'Agent Workforce Workspace' })
        });
        currentWorkspace = await response.json();
        shareId = currentWorkspace.shareId;
        renderWorkspace();
        // Update URL without reload
        window.history.pushState({}, '', '/workspace/' + shareId);
      } catch (error) {
        showToast('Failed to create workspace');
      }
    }
    
    // Render workspace data
    function renderWorkspace() {
      document.getElementById('workspaceName').textContent = currentWorkspace.name;
      document.getElementById('workspaceMeta').textContent = 
        'Created ' + new Date(currentWorkspace.createdAt).toLocaleDateString();
      document.getElementById('shareLink').value = window.location.origin + '/workspace/' + currentWorkspace.shareId;
      document.getElementById('messageCount').textContent = currentWorkspace.metrics.totalMessages;
      document.getElementById('interactionCount').textContent = currentWorkspace.metrics.totalInteractions;
      document.getElementById('statusIndicator').textContent = currentWorkspace.metrics.lastActivity ? 'Active' : 'New';
      
      // Render messages
      const messagesDiv = document.getElementById('chatMessages');
      messagesDiv.innerHTML = '';
      
      if (currentWorkspace.messages.length === 0) {
        messagesDiv.innerHTML = '<div style=\"text-align:center;color:var(--text-muted);padding:40px;\">Start a conversation with Hermes</div>';
      } else {
        currentWorkspace.messages.forEach(msg => addMessageToUI(msg.role, msg.content, false));
      }
    }
    
    // Add message to UI (XSS-safe)
    function addMessageToUI(role, content, animate = true) {
      const messagesDiv = document.getElementById('chatMessages');
      const avatar = role === 'hermes' ? 'H' : 'U';
      const messageDiv = document.createElement('div');
      messageDiv.className = 'message ' + role;
      messageDiv.style.animation = animate ? 'messageIn 0.3s ease' : 'none';
      
      const avatarDiv = document.createElement('div');
      avatarDiv.className = 'message-avatar';
      avatarDiv.textContent = avatar;
      
      const contentDiv = document.createElement('div');
      contentDiv.className = 'message-content';
      contentDiv.textContent = content; // XSS protection: use textContent
      
      messageDiv.appendChild(avatarDiv);
      messageDiv.appendChild(contentDiv);
      messagesDiv.appendChild(messageDiv);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
    
    // Send message
    async function sendMessage() {
      const input = document.getElementById('chatInput');
      const message = input.value.trim();
      if (!message || isTyping) return;
      
      // Add user message
      addMessageToUI('user', message);
      input.value = '';
      
      // Show typing indicator
      isTyping = true;
      const messagesDiv = document.getElementById('chatMessages');
      const typingDiv = document.createElement('div');
      typingDiv.className = 'message hermes';
      typingDiv.id = 'typingIndicator';
      typingDiv.innerHTML = 
        '<div class=\"message-avatar\">H</div>' +
        '<div class=\"message-content\"><div class=\"typing-indicator\"><span></span><span></span><span></span></div></div>';
      messagesDiv.appendChild(typingDiv);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
      
      try {
        // Call Hermes chat API
        const response = await fetch('/api/hermes/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: message, workspaceId: currentWorkspace.id })
        });
        const data = await response.json();
        
        // Remove typing indicator
        document.getElementById('typingIndicator').remove();
        
        // Add Hermes response
        const responseText = data.response || 'Hermes is not available in serverless mode. Run locally for full functionality.';
        addMessageToUI('hermes', responseText);
        
        // Save message to workspace
        await fetch('/api/workspace/' + currentWorkspace.id + '/messages', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role: 'user', content: message })
        });
        await fetch('/api/workspace/' + currentWorkspace.id + '/messages', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role: 'hermes', content: responseText })
        });
        
        // Update stats
        currentWorkspace.metrics.totalMessages += 2;
        currentWorkspace.metrics.totalInteractions++;
        document.getElementById('messageCount').textContent = currentWorkspace.metrics.totalMessages;
        document.getElementById('interactionCount').textContent = currentWorkspace.metrics.totalInteractions;
        document.getElementById('statusIndicator').textContent = 'Active';
        
      } catch (error) {
        document.getElementById('typingIndicator').remove();
        addMessageToUI('hermes', 'Error: Could not reach Hermes. Please try again.');
      }
      
      isTyping = false;
    }
    
    // Quick action
    function quickAction(message) {
      document.getElementById('chatInput').value = message;
      sendMessage();
    }
    
    // Update uptime
    function updateUptime() {
      if (!startTime) return;
      const minutes = Math.floor((Date.now() - startTime) / 60000);
      if (minutes < 60) {
        document.getElementById('uptimeDisplay').textContent = minutes + 'm';
      } else {
        const hours = Math.floor(minutes / 60);
        document.getElementById('uptimeDisplay').textContent = hours + 'h';
      }
    }
    
    // Copy share link
    function copyShareLink() {
      const input = document.getElementById('shareLink');
      navigator.clipboard.writeText(input.value);
      showToast('Link copied to clipboard!');
    }
    
    // Show toast
    function showToast(message) {
      const toast = document.getElementById('toast');
      document.getElementById('toastMessage').textContent = message;
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 3000);
    }
    
    // Modal functions
    function closeModal() {
      document.getElementById('newWorkspaceModal').classList.remove('show');
    }
    
    async function confirmNewWorkspace() {
      const name = document.getElementById('newWorkspaceName').value.trim();
      if (name) {
        currentWorkspace.name = name;
        // Update workspace name via API
        await fetch('/api/workspace/' + currentWorkspace.id, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: name })
        });
        document.getElementById('workspaceName').textContent = name;
      }
      closeModal();
    }
    
    // Handle Enter key in chat
    document.getElementById('chatInput').addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    
    // Initialize on load
    init();
  </script>
</body>
</html>`;

  // Serve the dashboard
  app.get('/workspace/:shareId', (req: Request, res: Response) => {
    res.setHeader('Content-Type', 'text/html');
    res.send(html);
  });

  // Also serve at /workspace for new workspaces
  app.get('/workspace', (req: Request, res: Response) => {
    res.setHeader('Content-Type', 'text/html');
    res.send(html);
  });
}