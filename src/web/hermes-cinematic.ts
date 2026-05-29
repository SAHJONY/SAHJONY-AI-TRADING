/**
 * Hermes Agent - Cinematic Ultra-Premium Dashboard
 * 8K-ready standalone platform with stunning visual effects
 */

import express, { Request, Response } from 'express'

const router = express.Router()

export function setupHermesCinematic(app: express.Application): void {
  app.get('/hermes-ultimate', (_req: Request, res: Response) => {
    res.send(getCinematicDashboard())
  })
  console.log('  Hermes Cinematic Dashboard: http://localhost:3000/hermes-ultimate')
}

function getCinematicDashboard(): string {
  return `<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>Hermes | Ultimate AI Platform</title>
  <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap\" rel=\"stylesheet\">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    
    :root {
      --hermes-void: #050508;
      --hermes-deep: #0a0a12;
      --hermes-purple: #6366f1;
      --hermes-violet: #8b5cf6;
      --hermes-magenta: #a855f7;
      --hermes-gold: #f59e0b;
      --hermes-cyan: #06b6d4;
      --hermes-neon: #22d3ee;
      --glass-bg: rgba(15, 15, 25, 0.7);
      --glass-border: rgba(139, 92, 246, 0.2);
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
    }
    
    html, body {
      height: 100%;
      overflow-x: hidden;
    }
    
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--hermes-void);
      color: var(--text-primary);
      min-height: 100vh;
      line-height: 1.6;
      overflow-x: hidden;
    }
    
    #particle-canvas {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 0;
      pointer-events: none;
    }
    
    .gradient-orb {
      position: fixed;
      border-radius: 50%;
      filter: blur(120px);
      opacity: 0.4;
      z-index: 0;
      pointer-events: none;
      animation: float 20s ease-in-out infinite;
    }
    
    .orb-1 {
      width: 600px;
      height: 600px;
      background: radial-gradient(circle, var(--hermes-purple) 0%, transparent 70%);
      top: -200px;
      left: -200px;
      animation-delay: 0s;
    }
    
    .orb-2 {
      width: 500px;
      height: 500px;
      background: radial-gradient(circle, var(--hermes-violet) 0%, transparent 70%);
      bottom: -150px;
      right: -150px;
      animation-delay: -5s;
    }
    
    .orb-3 {
      width: 400px;
      height: 400px;
      background: radial-gradient(circle, var(--hermes-magenta) 0%, transparent 70%);
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      animation-delay: -10s;
    }
    
    @keyframes float {
      0%, 100% { transform: translate(0, 0) scale(1); }
      25% { transform: translate(50px, -30px) scale(1.05); }
      50% { transform: translate(-30px, 50px) scale(0.95); }
      75% { transform: translate(30px, 30px) scale(1.02); }
    }
    
    .dashboard-container {
      position: relative;
      z-index: 1;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    
    .hero-section {
      position: relative;
      padding: 80px 40px 60px;
      text-align: center;
      overflow: hidden;
    }
    
    .hero-section::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: linear-gradient(180deg, 
        rgba(99, 102, 241, 0.1) 0%,
        transparent 50%,
        rgba(168, 85, 247, 0.05) 100%);
      pointer-events: none;
    }
    
    .orbital-container {
      position: relative;
      width: 300px;
      height: 300px;
      margin: 0 auto 40px;
    }
    
    .orbital-ring {
      position: absolute;
      border-radius: 50%;
      border: 1px solid;
      animation: spin 30s linear infinite;
    }
    
    .ring-1 {
      width: 300px;
      height: 300px;
      border-color: rgba(99, 102, 241, 0.3);
      top: 0;
      left: 0;
    }
    
    .ring-2 {
      width: 240px;
      height: 240px;
      border-color: rgba(139, 92, 246, 0.4);
      top: 30px;
      left: 30px;
      animation-direction: reverse;
      animation-duration: 25s;
    }
    
    .ring-3 {
      width: 180px;
      height: 180px;
      border-color: rgba(168, 85, 247, 0.5);
      top: 60px;
      left: 60px;
      animation-duration: 20s;
    }
    
    .orbital-core {
      position: absolute;
      width: 100px;
      height: 100px;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: linear-gradient(135deg, var(--hermes-purple), var(--hermes-magenta));
      border-radius: 50%;
      box-shadow: 
        0 0 60px rgba(99, 102, 241, 0.6),
        0 0 120px rgba(139, 92, 246, 0.4),
        inset 0 0 30px rgba(255, 255, 255, 0.1);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 40px;
      animation: pulse-glow 4s ease-in-out infinite;
    }
    
    @keyframes spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
    
    @keyframes pulse-glow {
      0%, 100% { 
        box-shadow: 
          0 0 60px rgba(99, 102, 241, 0.6),
          0 0 120px rgba(139, 92, 246, 0.4);
      }
      50% { 
        box-shadow: 
          0 0 80px rgba(99, 102, 241, 0.8),
          0 0 160px rgba(139, 92, 246, 0.6);
      }
    }
    
    .hero-title {
      font-size: clamp(48px, 8vw, 96px);
      font-weight: 900;
      letter-spacing: -3px;
      margin-bottom: 16px;
      background: linear-gradient(135deg, 
        #fff 0%, 
        var(--hermes-purple) 25%, 
        var(--hermes-magenta) 50%,
        var(--hermes-cyan) 75%,
        #fff 100%);
      background-size: 200% 200%;
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      animation: gradient-shift 8s ease infinite;
    }
    
    @keyframes gradient-shift {
      0%, 100% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
    }
    
    .hero-subtitle {
      font-size: clamp(16px, 2vw, 24px);
      font-weight: 300;
      color: var(--text-secondary);
      letter-spacing: 8px;
      text-transform: uppercase;
      margin-bottom: 32px;
    }
    
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 12px;
      padding: 16px 32px;
      background: var(--glass-bg);
      backdrop-filter: blur(20px);
      border: 1px solid var(--glass-border);
      border-radius: 50px;
      font-size: 14px;
      font-weight: 500;
    }
    
    .status-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: var(--hermes-purple);
      animation: status-pulse 2s ease-in-out infinite;
      box-shadow: 0 0 20px var(--hermes-purple);
    }
    
    .status-badge.connected .status-dot {
      background: #10b981;
      box-shadow: 0 0 20px #10b981;
    }
    
    .status-badge.serverless .status-dot {
      background: var(--hermes-gold);
      box-shadow: 0 0 20px var(--hermes-gold);
      animation: none;
    }
    
    @keyframes status-pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.6; transform: scale(0.9); }
    }
    
    .glass-panel {
      background: var(--glass-bg);
      backdrop-filter: blur(20px);
      border: 1px solid var(--glass-border);
      border-radius: 24px;
      overflow: hidden;
      transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    .glass-panel:hover {
      border-color: rgba(139, 92, 246, 0.4);
      box-shadow: 
        0 8px 40px rgba(99, 102, 241, 0.15),
        0 0 0 1px rgba(139, 92, 246, 0.1);
    }
    
    .main-content {
      flex: 1;
      padding: 0 40px 60px;
      display: grid;
      grid-template-columns: 1fr 420px;
      gap: 32px;
      max-width: 1800px;
      margin: 0 auto;
      width: 100%;
    }
    
    .chat-panel {
      display: flex;
      flex-direction: column;
      height: fit-content;
      max-height: 700px;
    }
    
    .chat-header {
      padding: 28px 32px;
      border-bottom: 1px solid var(--glass-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    
    .chat-title {
      font-size: 20px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    
    .chat-title-icon {
      width: 40px;
      height: 40px;
      background: linear-gradient(135deg, var(--hermes-purple), var(--hermes-magenta));
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
    }
    
    .model-selector {
      display: flex;
      gap: 8px;
    }
    
    .model-btn {
      padding: 10px 20px;
      border-radius: 12px;
      border: 1px solid var(--glass-border);
      background: transparent;
      color: var(--text-secondary);
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.3s;
      font-family: 'JetBrains Mono', monospace;
    }
    
    .model-btn:hover {
      border-color: var(--hermes-purple);
      color: var(--text-primary);
      background: rgba(99, 102, 241, 0.1);
    }
    
    .model-btn.active {
      background: linear-gradient(135deg, var(--hermes-purple), var(--hermes-violet));
      border-color: transparent;
      color: white;
    }
    
    .chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 32px;
      display: flex;
      flex-direction: column;
      gap: 24px;
      min-height: 400px;
      max-height: 450px;
      background: linear-gradient(180deg, 
        rgba(99, 102, 241, 0.03) 0%,
        transparent 100%);
    }
    
    .chat-messages::-webkit-scrollbar { width: 6px; }
    .chat-messages::-webkit-scrollbar-track { background: transparent; }
    .chat-messages::-webkit-scrollbar-thumb { background: var(--glass-border); border-radius: 3px; }
    
    .message {
      max-width: 85%;
      padding: 20px 24px;
      border-radius: 20px;
      line-height: 1.7;
      font-size: 15px;
      animation: message-enter 0.5s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
    }
    
    @keyframes message-enter {
      from { opacity: 0; transform: translateY(30px) scale(0.95); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    
    .message.bot {
      align-self: flex-start;
      background: rgba(30, 30, 50, 0.8);
      border: 1px solid var(--glass-border);
      border-bottom-left-radius: 8px;
    }
    
    .message.user {
      align-self: flex-end;
      background: linear-gradient(135deg, var(--hermes-purple), var(--hermes-violet));
      border-bottom-right-radius: 8px;
      color: white;
    }
    
    .message-avatar {
      position: absolute;
      top: -10px;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      border: 2px solid var(--hermes-void);
    }
    
    .message.bot .message-avatar {
      left: 20px;
      background: linear-gradient(135deg, var(--hermes-purple), var(--hermes-magenta));
    }
    
    .message.user .message-avatar {
      right: 20px;
      background: rgba(255, 255, 255, 0.2);
    }
    
    .message-content {
      padding-top: 20px;
    }
    
    .message.user .message-content {
      padding-top: 0;
      padding-left: 40px;
    }
    
    .message.bot .message-content {
      padding-right: 40px;
    }
    
    .message-meta {
      display: flex;
      gap: 16px;
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 8px;
      font-family: 'JetBrains Mono', monospace;
    }
    
    .message.user .message-meta {
      color: rgba(255, 255, 255, 0.7);
    }
    
    .typing-indicator {
      display: flex;
      gap: 8px;
      padding: 24px;
      background: rgba(30, 30, 50, 0.8);
      border-radius: 20px;
      border-bottom-left-radius: 8px;
      width: fit-content;
      animation: message-enter 0.3s ease;
    }
    
    .typing-dot {
      width: 10px;
      height: 10px;
      background: var(--hermes-purple);
      border-radius: 50%;
      animation: typing-bounce 1.4s infinite;
    }
    
    .typing-dot:nth-child(2) { animation-delay: 0.15s; }
    .typing-dot:nth-child(3) { animation-delay: 0.3s; }
    
    @keyframes typing-bounce {
      0%, 60%, 100% { transform: translateY(0); }
      30% { transform: translateY(-12px); }
    }
    
    .chat-input-area {
      padding: 24px;
      border-top: 1px solid var(--glass-border);
      display: flex;
      gap: 16px;
      background: rgba(10, 10, 18, 0.5);
    }
    
    .chat-input {
      flex: 1;
      padding: 18px 24px;
      border-radius: 16px;
      border: 1px solid var(--glass-border);
      background: rgba(20, 20, 35, 0.8);
      color: var(--text-primary);
      font-size: 15px;
      font-family: 'Inter', sans-serif;
      outline: none;
      transition: all 0.3s;
    }
    
    .chat-input:focus {
      border-color: var(--hermes-purple);
      box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.15);
    }
    
    .chat-input::placeholder {
      color: var(--text-muted);
    }
    
    .send-btn {
      padding: 18px 32px;
      background: linear-gradient(135deg, var(--hermes-purple), var(--hermes-violet));
      border: none;
      border-radius: 16px;
      color: white;
      font-weight: 600;
      font-size: 15px;
      cursor: pointer;
      transition: all 0.3s;
      display: flex;
      align-items: center;
      gap: 10px;
      font-family: 'Inter', sans-serif;
    }
    
    .send-btn:hover {
      transform: translateY(-3px);
      box-shadow: 0 12px 40px rgba(99, 102, 241, 0.4);
    }
    
    .send-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
      transform: none;
    }
    
    .quick-actions {
      padding: 20px 24px;
      border-top: 1px solid var(--glass-border);
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      background: rgba(99, 102, 241, 0.03);
    }
    
    .quick-btn {
      padding: 12px 20px;
      background: rgba(20, 20, 35, 0.8);
      border: 1px solid var(--glass-border);
      border-radius: 12px;
      color: var(--text-secondary);
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.3s;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .quick-btn:hover {
      border-color: var(--hermes-purple);
      color: var(--text-primary);
      background: rgba(99, 102, 241, 0.1);
      transform: translateY(-2px);
    }
    
    .sidebar {
      display: flex;
      flex-direction: column;
      gap: 24px;
    }
    
    .stats-panel {
      padding: 28px;
    }
    
    .panel-header {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 2px;
      color: var(--text-muted);
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
    }
    
    .stat-item {
      background: rgba(10, 10, 18, 0.6);
      border-radius: 16px;
      padding: 20px;
      text-align: center;
      border: 1px solid rgba(99, 102, 241, 0.1);
      transition: all 0.3s;
    }
    
    .stat-item:hover {
      border-color: rgba(99, 102, 241, 0.3);
      transform: translateY(-4px);
    }
    
    .stat-value {
      font-size: 32px;
      font-weight: 800;
      background: linear-gradient(135deg, var(--hermes-purple), var(--hermes-cyan));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      font-family: 'JetBrains Mono', monospace;
    }
    
    .stat-label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--text-muted);
      margin-top: 6px;
    }
    
    .capabilities-panel {
      padding: 28px;
    }
    
    .capabilities-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
    }
    
    .capability-item {
      background: rgba(10, 10, 18, 0.6);
      border-radius: 14px;
      padding: 16px;
      text-align: center;
      border: 1px solid rgba(99, 102, 241, 0.1);
      transition: all 0.3s;
      cursor: pointer;
    }
    
    .capability-item:hover {
      border-color: var(--hermes-purple);
      background: rgba(99, 102, 241, 0.1);
      transform: translateY(-3px);
    }
    
    .capability-icon {
      font-size: 28px;
      margin-bottom: 10px;
    }
    
    .capability-name {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-secondary);
    }
    
    .skills-panel {
      padding: 28px;
    }
    
    .skills-cloud {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    
    .skill-tag {
      padding: 10px 18px;
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(139, 92, 246, 0.1));
      border: 1px solid rgba(99, 102, 241, 0.3);
      border-radius: 20px;
      font-size: 13px;
      font-weight: 500;
      color: var(--text-secondary);
      cursor: pointer;
      transition: all 0.3s;
    }
    
    .skill-tag:hover {
      border-color: var(--hermes-purple);
      color: var(--text-primary);
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.3), rgba(139, 92, 246, 0.2));
      transform: translateY(-2px);
    }
    
    .memory-panel {
      padding: 28px;
    }
    
    .memory-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
      max-height: 200px;
      overflow-y: auto;
    }
    
    .memory-item {
      padding: 16px;
      background: rgba(10, 10, 18, 0.6);
      border-radius: 12px;
      font-size: 13px;
      color: var(--text-secondary);
      border-left: 3px solid var(--hermes-purple);
      transition: all 0.3s;
    }
    
    .memory-item:hover {
      background: rgba(99, 102, 241, 0.1);
    }
    
    .serverless-notice {
      background: linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(245, 158, 11, 0.05));
      border: 1px solid rgba(245, 158, 11, 0.3);
      border-radius: 16px;
      padding: 20px;
      margin: 0 40px 32px;
      text-align: center;
    }
    
    .serverless-notice h3 {
      color: var(--hermes-gold);
      margin-bottom: 8px;
      font-size: 16px;
    }
    
    .serverless-notice p {
      font-size: 14px;
      color: var(--text-secondary);
    }
    
    @media (max-width: 1200px) {
      .main-content {
        grid-template-columns: 1fr;
        padding: 0 24px 40px;
      }
      
      .hero-section {
        padding: 60px 24px 40px;
      }
      
      .orbital-container {
        width: 200px;
        height: 200px;
      }
      
      .ring-1 { width: 200px; height: 200px; }
      .ring-2 { width: 160px; height: 160px; top: 20px; left: 20px; }
      .ring-3 { width: 120px; height: 120px; top: 40px; left: 40px; }
      
      .orbital-core {
        width: 70px;
        height: 70px;
        font-size: 30px;
      }
      
      .capabilities-grid {
        grid-template-columns: repeat(2, 1fr);
      }
    }
    
    @media (max-width: 768px) {
      .hero-title {
        letter-spacing: -1px;
      }
      
      .chat-header {
        flex-direction: column;
        gap: 16px;
      }
      
      .model-selector {
        width: 100%;
        justify-content: center;
      }
      
      .stats-grid {
        grid-template-columns: 1fr 1fr;
      }
      
      .serverless-notice {
        margin: 0 24px 24px;
      }
    }
    
    ::-webkit-scrollbar {
      width: 8px;
    }
    
    ::-webkit-scrollbar-track {
      background: rgba(10, 10, 18, 0.5);
    }
    
    ::-webkit-scrollbar-thumb {
      background: var(--glass-border);
      border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
      background: var(--hermes-purple);
    }
  </style>
</head>
<body>
  <canvas id=\"particle-canvas\"></canvas>
  
  <div class=\"gradient-orb orb-1\"></div>
  <div class=\"gradient-orb orb-2\"></div>
  <div class=\"gradient-orb orb-3\"></div>
  
  <div class=\"dashboard-container\">
    <section class=\"hero-section\">
      <div class=\"orbital-container\">
        <div class=\"orbital-ring ring-1\"></div>
        <div class=\"orbital-ring ring-2\"></div>
        <div class=\"orbital-ring ring-3\"></div>
        <div class=\"orbital-core\">☤</div>
      </div>
      
      <h1 class=\"hero-title\">HERMES</h1>
      <p class=\"hero-subtitle\">Self-Improving AI Agent</p>
      
      <div class=\"status-badge\" id=\"statusBadge\">
        <span class=\"status-dot\"></span>
        <span id=\"statusText\">Initializing Neural Links...</span>
      </div>
    </section>
    
    <div class=\"serverless-notice\" id=\"serverlessNotice\" style=\"display: none;\">
      <h3>⚡ Serverless Environment Detected</h3>
      <p>Hermes CLI subprocess is not available. For full functionality, run the agent-workforce server locally with Hermes installed.</p>
    </div>
    
    <div class=\"main-content\">
      <div class=\"glass-panel chat-panel\">
        <div class=\"chat-header\">
          <div class=\"chat-title\">
            <div class=\"chat-title-icon\">💬</div>
            Neural Interface
          </div>
          <div class=\"model-selector\">
            <button class=\"model-btn active\" onclick=\"setModel('auto', this)\">AUTO</button>
            <button class=\"model-btn\" onclick=\"setModel('claude', this)\">CLAUDE</button>
            <button class=\"model-btn\" onclick=\"setModel('gpt4', this)\">GPT-4</button>
            <button class=\"model-btn\" onclick=\"setModel('nous', this)\">NOUS</button>
          </div>
        </div>
        
        <div class=\"chat-messages\" id=\"chatMessages\">
          <div class=\"message bot\">
            <div class=\"message-avatar\">☤</div>
            <div class=\"message-content\">
              Greetings, I am Hermes — the autonomous AI agent from Nous Research. My neural pathways are primed and ready. I possess self-improvement capabilities, persistent memory across sessions, and access to over 40 integrated tools. How may I augment your capabilities today?
              <div class=\"message-meta\">
                <span>NOUS RESEARCH</span>
                <span>INIT</span>
              </div>
            </div>
          </div>
        </div>
        
        <div class=\"chat-input-area\">
          <input type=\"text\" class=\"chat-input\" id=\"messageInput\" placeholder=\"Transmit your query to Hermes...\" onkeypress=\"handleEnter(event)\">
          <button class=\"send-btn\" onclick=\"sendMessage()\" id=\"sendBtn\">
            <span>TRANSMIT</span>
            <svg width=\"20\" height=\"20\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\">
              <path d=\"M22 2L11 13M22 2L15 22L11 13L2 9L22 2Z\"/>
            </svg>
          </button>
        </div>
        
        <div class=\"quick-actions\">
          <button class=\"quick-btn\" onclick=\"quickAction('What are your core capabilities?')\">🧠 Core</button>
          <button class=\"quick-btn\" onclick=\"quickAction('Show me your available skills')\">⚡ Skills</button>
          <button class=\"quick-btn\" onclick=\"quickAction('What have you learned from our conversations?')\">💾 Memory</button>
          <button class=\"quick-btn\" onclick=\"quickAction('Create a new skill for a specific task')\">🛠️ Create</button>
          <button class=\"quick-btn\" onclick=\"quickAction('Tell me about your self-improvement process')\">🔄 Evolve</button>
        </div>
      </div>
      
      <div class=\"sidebar\">
        <div class=\"glass-panel stats-panel\">
          <div class=\"panel-header\">
            <span>📊</span> System Metrics
          </div>
          <div class=\"stats-grid\">
            <div class=\"stat-item\">
              <div class=\"stat-value\" id=\"sessionCount\">0</div>
              <div class=\"stat-label\">Sessions</div>
            </div>
            <div class=\"stat-item\">
              <div class=\"stat-value\" id=\"messagesToday\">0</div>
              <div class=\"stat-label\">Messages</div>
            </div>
            <div class=\"stat-item\">
              <div class=\"stat-value\" id=\"skillsCreated\">0</div>
              <div class=\"stat-label\">Skills</div>
            </div>
            <div class=\"stat-item\">
              <div class=\"stat-value\" id=\"uptimeDisplay\">--</div>
              <div class=\"stat-label\">Uptime</div>
            </div>
          </div>
        </div>
        
        <div class=\"glass-panel capabilities-panel\">
          <div class=\"panel-header\">
            <span>🚀</span> Capabilities
          </div>
          <div class=\"capabilities-grid\">
            <div class=\"capability-item\" onclick=\"quickAction('Explain your self-improving architecture')\">
              <div class=\"capability-icon\">🧠</div>
              <div class=\"capability-name\">Self-Evolve</div>
            </div>
            <div class=\"capability-item\" onclick=\"quickAction('How does your memory system work?')\">
              <div class=\"capability-icon\">💾</div>
              <div class=\"capability-name\">Memory</div>
            </div>
            <div class=\"capability-item\" onclick=\"quickAction('What tools do you have access to?')\">
              <div class=\"capability-icon\">🔧</div>
              <div class=\"capability-name\">40+ Tools</div>
            </div>
            <div class=\"capability-item\" onclick=\"quickAction('Connect me to Telegram')\">
              <div class=\"capability-icon\">💬</div>
              <div class=\"capability-name\">Messaging</div>
            </div>
            <div class=\"capability-item\" onclick=\"quickAction('Which LLM models can you use?')\">
              <div class=\"capability-icon\">🎯</div>
              <div class=\"capability-name\">Any Model</div>
            </div>
            <div class=\"capability-item\" onclick=\"quickAction('How do you create new skills?')\">
              <div class=\"capability-icon\">⚡</div>
              <div class=\"capability-name\">Skills</div>
            </div>
          </div>
        </div>
        
        <div class=\"glass-panel skills-panel\">
          <div class=\"panel-header\">
            <span>🎯</span> Active Skills
          </div>
          <div class=\"skills-cloud\">
            <span class=\"skill-tag\" onclick=\"quickAction('Use your coding skill to help me')\">💻 Coding</span>
            <span class=\"skill-tag\" onclick=\"quickAction('Use research skill')\">🔍 Research</span>
            <span class=\"skill-tag\" onclick=\"quickAction('Use writing skill')\">✍️ Writing</span>
            <span class=\"skill-tag\" onclick=\"quickAction('Use analysis skill')\">📊 Analysis</span>
            <span class=\"skill-tag\" onclick=\"quickAction('Use memory recall')\">🧠 Recall</span>
            <span class=\"skill-tag\" onclick=\"quickAction('Use web search')\">🌐 Search</span>
          </div>
        </div>
        
        <div class=\"glass-panel memory-panel\">
          <div class=\"panel-header\">
            <span>💾</span> Memory Banks
          </div>
          <div class=\"memory-list\" id=\"memoryList\">
            <div class=\"memory-item\">
              No memory banks initialized yet. Start a conversation to build persistent context.
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const canvas = document.getElementById('particle-canvas');
    const ctx = canvas.getContext('2d');
    let particles = [];
    
    function resizeCanvas() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    
    class Particle {
      constructor() {
        this.reset();
      }
      
      reset() {
        this.x = Math.random() * canvas.width;
        this.y = Math.random() * canvas.height;
        this.size = Math.random() * 2 + 0.5;
        this.speedX = (Math.random() - 0.5) * 0.5;
        this.speedY = (Math.random() - 0.5) * 0.5;
        this.opacity = Math.random() * 0.5 + 0.2;
        this.hue = Math.random() > 0.5 ? 260 : 280;
      }
      
      update() {
        this.x += this.speedX;
        this.y += this.speedY;
        
        if (this.x < 0 || this.x > canvas.width || this.y < 0 || this.y > canvas.height) {
          this.reset();
        }
      }
      
      draw() {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fillStyle = 'hsla(' + this.hue + ', 80%, 60%, ' + this.opacity + ')';
        ctx.fill();
      }
    }
    
    function initParticles() {
      particles = [];
      const particleCount = Math.min(150, Math.floor((canvas.width * canvas.height) / 10000));
      for (let i = 0; i < particleCount; i++) {
        particles.push(new Particle());
      }
    }
    
    function connectParticles() {
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const distance = Math.sqrt(dx * dx + dy * dy);
          
          if (distance < 120) {
            ctx.beginPath();
            ctx.strokeStyle = 'hsla(270, 80%, 60%, ' + (0.15 * (1 - distance / 120)) + ')';
            ctx.lineWidth = 0.5;
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.stroke();
          }
        }
      }
    }
    
    function animateParticles() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      for (let i = 0; i < particles.length; i++) {
        particles[i].update();
        particles[i].draw();
      }
      
      connectParticles();
      requestAnimationFrame(animateParticles);
    }
    
    resizeCanvas();
    initParticles();
    animateParticles();
    window.addEventListener('resize', function() {
      resizeCanvas();
      initParticles();
    });
    
    let currentModel = 'auto';
    let sessionId = 'HERMES-' + Date.now().toString(36);
    let messageCount = 0;
    let startTime = Date.now();
    let isLoading = false;
    let isServerless = false;
    
    checkHermesStatus();
    setInterval(updateUptime, 1000);
    
    async function checkHermesStatus() {
      try {
        const response = await fetch('/api/hermes/status');
        if (response.ok) {
          const data = await response.json();
          updateStatus(data);
        } else {
          setDisconnected('API Unavailable');
        }
      } catch (e) {
        setDisconnected('Connection Failed');
      }
    }
    
    function updateStatus(data) {
      const badge = document.getElementById('statusBadge');
      const text = document.getElementById('statusText');
      const hermesStatus = data.hermesStatus || {};
      
      if (hermesStatus.sessionId && !hermesStatus.initialized) {
        badge.classList.add('serverless');
        badge.classList.remove('connected');
        text.textContent = 'Serverless Mode — Limited';
        document.getElementById('serverlessNotice').style.display = 'block';
        isServerless = true;
      } else if (data.status === 'idle' || data.status === 'working') {
        badge.classList.add('connected');
        text.textContent = 'Neural Link Active — ' + data.name;
        isServerless = false;
      } else {
        text.textContent = 'Status: ' + (data.status || 'Unknown');
      }
      
      document.getElementById('sessionCount').textContent = '1';
    }
    
    function setDisconnected(reason) {
      const badge = document.getElementById('statusBadge');
      badge.classList.remove('connected', 'serverless');
      document.getElementById('statusText').textContent = reason || 'Disconnected';
      document.getElementById('serverlessNotice').style.display = 'block';
      isServerless = true;
    }
    
    function setModel(model, btn) {
      currentModel = model;
      var btns = document.querySelectorAll('.model-btn');
      for (var i = 0; i < btns.length; i++) {
        btns[i].classList.remove('active');
      }
      btn.classList.add('active');
      addMessage('bot', 'Neural pathway configured for ' + model.toUpperCase() + ' mode. Optimal model selection engaged.', 'SYSTEM');
    }
    
    async function sendMessage() {
      if (isLoading) return;
      
      var input = document.getElementById('messageInput');
      var message = input.value.trim();
      if (!message) return;
      
      if (isServerless) {
        addMessage('bot', 'Hermes CLI subprocess is not available in this serverless environment. For full neural capabilities, run the agent-workforce server locally with Hermes installed.', 'SYSTEM');
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
          body: JSON.stringify({ message: message, sessionId: sessionId })
        });
        
        hideTypingIndicator();
        
        if (response.ok) {
          var data = await response.json();
          addMessage('bot', data.response, 'HERMES');
        } else {
          var error = await response.json().catch(function() { return {}; });
          addMessage('bot', 'Transmission error: ' + (error.error || 'Failed to receive neural response'), 'ERROR');
        }
      } catch (e) {
        hideTypingIndicator();
        addMessage('bot', 'Neural link failure. Please verify connection to Hermes core.', 'ERROR');
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
      
      if (type === 'bot') {
        div.innerHTML = '<div class=\"message-avatar\">' + avatar + '</div>' +
          '<div class=\"message-content\">' + text +
          '<div class=\"message-meta\"><span>' + (sender || 'HERMES') + '</span><span>' + time + '</span></div>' +
          '</div>';
      } else {
        div.innerHTML = '<div class=\"message-avatar\">' + avatar + '</div>' +
          '<div class=\"message-content\">' + text +
          '<div class=\"message-meta\"><span>HUMAN</span><span>' + time + '</span></div>' +
          '</div>';
      }
      
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
    }
    
    function showTypingIndicator() {
      var chat = document.getElementById('chatMessages');
      var div = document.createElement('div');
      div.className = 'typing-indicator';
      div.id = 'typingIndicator';
      div.innerHTML = '<div class=\"typing-dot\"></div><div class=\"typing-dot\"></div><div class=\"typing-dot\"></div>';
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
      btn.querySelector('span').textContent = loading ? 'PROCESSING...' : 'TRANSMIT';
    }
    
    function updateUptime() {
      if (startTime) {
        var elapsed = Math.floor((Date.now() - startTime) / 1000);
        var hours = Math.floor(elapsed / 3600);
        var minutes = Math.floor((elapsed % 3600) / 60);
        var seconds = elapsed % 60;
        document.getElementById('uptimeDisplay').textContent = 
          (hours < 10 ? '0' : '') + hours + ':' +
          (minutes < 10 ? '0' : '') + minutes + ':' +
          (seconds < 10 ? '0' : '') + seconds;
      }
    }
  </script>
</body>
</html>`
}

export default router