/**
 * Web Dashboard for Agent Workforce
 * Real-time monitoring and control interface with Receptionist Integration
 */

import express, { Request, Response } from 'express'
import { getEngine } from '../orchestration/engine'

const router = express.Router()

// Receptionist Agent definitions
interface ReceptionistAgentInfo {
  id: string
  name: string
  role: string
  status: 'idle' | 'busy' | 'offline'
  tasksHandled: number
  specialty: string
  avatar: string
}

const receptionistAgents: ReceptionistAgentInfo[] = [
  { id: 'aria-voice-1', name: 'ARIA', role: 'voice_receptionist', status: 'idle', tasksHandled: 0, specialty: 'Phone & Visitor Reception', avatar: '🎙️' },
  { id: 'scheduler-1', name: 'CHRONOS', role: 'scheduling', status: 'idle', tasksHandled: 0, specialty: 'Appointment Booking', avatar: '📅' },
  { id: 'knowledge-1', name: 'WIKI', role: 'information', status: 'idle', tasksHandled: 0, specialty: 'FAQ & Knowledge', avatar: '📚' },
  { id: 'escalation-1', name: 'CONNECT', role: 'escalation', status: 'idle', tasksHandled: 0, specialty: 'Human Handoffs', avatar: '🔗' }
]

// Dashboard main page
router.get('/', (_req: Request, res: Response) => {
  res.send(`
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>Agent Workforce + Receptionist Dashboard</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
    .container { max-width: 1600px; margin: 0 auto; padding: 20px; }
    h1 { color: #38bdf8; margin-bottom: 20px; font-size: 28px; }
    h2 { color: #38bdf8; font-size: 16px; margin-bottom: 15px; text-transform: uppercase; letter-spacing: 1px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
    .card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
    .stat { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #334155; }
    .stat:last-child { border-bottom: none; }
    .stat-label { color: #94a3b8; }
    .stat-value { color: #f1f5f9; font-weight: 600; }
    .stat-value.success { color: #4ade80; }
    .stat-value.warning { color: #fbbf24; }
    .stat-value.error { color: #f87171; }
    .stat-value.info { color: #38bdf8; }
    
    /* Agent Cards */
    .agent-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
    .agent-card { background: #0f172a; border-radius: 10px; padding: 15px; text-align: center; transition: all 0.2s; }
    .agent-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
    .agent-avatar { font-size: 32px; margin-bottom: 8px; }
    .agent-name { color: #f1f5f9; font-weight: 600; font-size: 14px; }
    .agent-role { color: #38bdf8; font-size: 11px; margin-bottom: 8px; }
    .agent-specialty { color: #94a3b8; font-size: 10px; margin-bottom: 10px; }
    .agent-stats { display: flex; justify-content: space-around; font-size: 11px; }
    .agent-stat-item { text-align: center; }
    .agent-stat-value { color: #f1f5f9; font-weight: 600; }
    .agent-stat-label { color: #64748b; font-size: 9px; }
    .status-badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 10px; font-weight: 600; }
    .status-idle { background: #475569; color: #cbd5e1; }
    .status-busy { background: #2563eb; color: #dbeafe; }
    .status-offline { background: #374151; color: #9ca3af; }
    
    /* Tasks Table */
    .tasks-table { width: 100%; border-collapse: collapse; }
    .tasks-table th { text-align: left; padding: 12px; color: #94a3b8; font-size: 12px; text-transform: uppercase; border-bottom: 1px solid #334155; }
    .tasks-table td { padding: 12px; border-bottom: 1px solid #1e293b; }
    .tasks-table tr:hover { background: #0f172a; }
    .task-desc { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    
    /* Badges */
    .badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
    .badge-pending { background: #475569; color: #cbd5e1; }
    .badge-assigned { background: #2563eb; color: #dbeafe; }
    .badge-progress { background: #7c3aed; color: #ede9fe; }
    .badge-completed { background: #16a34a; color: #dcfce7; }
    .badge-failed { background: #dc2626; color: #fee2e2; }
    .badge-critical { background: #dc2626; color: #fee2e2; }
    .badge-high { background: #ea580c; color: #ffedd5; }
    .badge-medium { background: #2563eb; color: #dbeafe; }
    .badge-low { background: #475569; color: #cbd5e1; }
    
    /* Receptionist Section */
    .receptionist-section { border-left: 3px solid #8b5cf6; padding-left: 15px; }
    .receptionist-header { display: flex; align-items: center; gap: 10px; margin-bottom: 15px; }
    .receptionist-icon { font-size: 24px; }
    .section-divider { height: 1px; background: #334155; margin: 20px 0; }
    
    /* Industry Badge */
    .industry-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; background: #374151; color: #d1d5db; }
    
    /* Buttons */
    .action-btn { background: #38bdf8; color: #0f172a; border: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
    .action-btn:hover { background: #0ea5e9; transform: translateY(-1px); }
    .action-btn-purple { background: #8b5cf6; color: white; }
    .action-btn-purple:hover { background: #7c3aed; }
    
    .input-group { display: flex; gap: 10px; margin-bottom: 20px; }
    .input-group input, .input-group select { flex: 1; padding: 12px 16px; background: #0f172a; border: 1px solid #334155; border-radius: 8px; color: #f1f5f9; font-size: 14px; }
    .input-group input:focus, .input-group select:focus { outline: none; border-color: #38bdf8; }
    
    .refresh-badge { background: #38bdf8; color: #0f172a; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
    .purple-badge { background: #8b5cf6; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
    
    /* Tool Status */
    .tools-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }
    .tool-item { background: #0f172a; padding: 10px; border-radius: 6px; text-align: center; }
    .tool-name { color: #f1f5f9; font-size: 12px; font-weight: 500; }
    .tool-status { color: #4ade80; font-size: 10px; margin-top: 4px; }
    
    /* Visitor Queue */
    .visitor-queue { max-height: 200px; overflow-y: auto; }
    .visitor-item { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #0f172a; border-radius: 6px; margin-bottom: 6px; }
    .visitor-name { color: #f1f5f9; font-weight: 500; font-size: 13px; }
    .visitor-purpose { color: #94a3b8; font-size: 11px; }
    .visitor-priority { padding: 2px 8px; border-radius: 4px; font-size: 10px; }
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>🤖 Agent Workforce + Receptionist Dashboard</h1>
    
    <!-- Task Submission -->
    <div class=\"input-group\">
      <input type=\"text\" id=\"taskInput\" placeholder=\"Enter task description...\" />
      <select id=\"taskIndustry\">
        <option value=\"healthcare\">Healthcare</option>
        <option value=\"corporate\" selected>Corporate</option>
        <option value=\"hospitality\">Hospitality</option>
        <option value=\"legal\">Legal</option>
        <option value=\"realestate\">Real Estate</option>
        <option value=\"retail\">Retail</option>
        <option value=\"education\">Education</option>
        <option value=\"government\">Government</option>
      </select>
      <select id=\"taskPriority\">
        <option value=\"low\">Low</option>
        <option value=\"medium\" selected>Medium</option>
        <option value=\"high\">High</option>
        <option value=\"critical\">Critical</option>
      </select>
      <button class=\"action-btn-purple\" onclick=\"submitReceptionistTask()\">Add to Queue</button>
    </div>
    
    <div class=\"grid\">
      <!-- System Status -->
      <div class=\"card\">
        <h2>System Status</h2>
        <div id=\"systemStats\"></div>
      </div>
      
      <!-- Workforce Engine Status -->
      <div class=\"card\">
        <div class=\"card-header\">
          <h2>Workforce Engine</h2>
          <span class=\"refresh-badge\" id=\"engineAgentCount\">0</span>
        </div>
        <div id=\"engineStatus\"></div>
      </div>
      
      <!-- Receptionist Agent Status -->
      <div class=\"card receptionist-section\">
        <div class=\"receptionist-header\">
          <span class=\"receptionist-icon\">🎧</span>
          <div>
            <h2 style=\"margin-bottom: 0;\">Receptionist Agents</h2>
            <span class=\"purple-badge\" id=\"receptionistCount\">4 Active</span>
          </div>
        </div>
        <div class=\"agent-cards\" id=\"receptionistAgents\"></div>
      </div>
      
      <!-- Task Queue -->
      <div class=\"card\">
        <div class=\"card-header\">
          <h2>Task Queue</h2>
          <span class=\"refresh-badge\" id=\"queueCount\">0</span>
        </div>
        <div id=\"queueStats\"></div>
        <div class=\"section-divider\"></div>
        <h2 style=\"font-size: 14px; margin-bottom: 10px;\">Available Tools</h2>
        <div class=\"tools-grid\" id=\"toolsGrid\"></div>
      </div>
      
      <!-- Industry Distribution -->
      <div class=\"card\">
        <h2>Industry Distribution</h2>
        <div id=\"industryStats\"></div>
      </div>
      
      <!-- Recent Tasks -->
      <div class=\"card\" style=\"grid-column: span 2;\">
        <div class=\"card-header\">
          <h2>Recent Tasks</h2>
          <span class=\"refresh-badge\" id=\"recentCount\">0</span>
        </div>
        <table class=\"tasks-table\">
          <thead>
            <tr>
              <th>ID</th>
              <th>Description</th>
              <th>Type</th>
              <th>Industry</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Agent</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody id=\"tasksTable\"></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    // Receptionist agent data (would come from API in production)
    const receptionistAgents = [
      { id: 'aria-voice-1', name: 'ARIA', role: 'voice_receptionist', status: 'idle', tasksHandled: 0, specialty: 'Phone & Visitor Reception', avatar: '🎙️' },
      { id: 'scheduler-1', name: 'CHRONOS', role: 'scheduling', status: 'idle', tasksHandled: 0, specialty: 'Appointment Booking', avatar: '📅' },
      { id: 'knowledge-1', name: 'WIKI', role: 'information', status: 'idle', tasksHandled: 0, specialty: 'FAQ & Knowledge', avatar: '📚' },
      { id: 'escalation-1', name: 'CONNECT', role: 'escalation', status: 'idle', tasksHandled: 0, specialty: 'Human Handoffs', avatar: '🔗' }
    ];
    
    const tools = ['book_appointment', 'faq_lookup', 'register_visitor', 'escalate_to_human', 'translate_response'];
    
    function renderReceptionistAgents(agents) {
      const container = document.getElementById('receptionistAgents');
      container.innerHTML = agents.map(agent => \"
        <div class=\"agent-card\">\n          <div class=\"agent-avatar\">\" + agent.avatar + \"</div>\n          <div class=\"agent-name\">\" + agent.name + \"</div>\n          <div class=\"agent-role\">\" + agent.role + \"</div>\n          <div class=\"agent-specialty\">\" + agent.specialty + \"</div>\n          <span class=\"status-badge status-\" + agent.status + \">\" + agent.status + \"</span>\n          <div class=\"agent-stats\" style=\"margin-top: 10px;\">\n            <div class=\"agent-stat-item\">\n              <div class=\"agent-stat-value\">\" + agent.tasksHandled + \"</div>\n              <div class=\"agent-stat-label\">Tasks</div>\n            </div>\n          </div>\n        </div>\n      \").join('');
    }
    
    function renderTools() {
      const container = document.getElementById('toolsGrid');
      container.innerHTML = tools.map(tool => \"
        <div class=\"tool-item\">\n          <div class=\"tool-name\">\" + tool + \"</div>\n          <div class=\"tool-status\">● Active</div>\n        </div>\n      \").join('');
    }
    
    async function fetchEngineStatus() {
      try {
        const response = await fetch('/api/status');
        const data = await response.json();
        updateEngineDashboard(data);
      } catch (error) {
        console.error('Failed to fetch engine status:', error);
      }
    }
    
    function updateEngineDashboard(status) {
      document.getElementById('engineAgentCount').textContent = status.agents?.length || 0;
      
      let engineStatus = document.getElementById('engineStatus');
      engineStatus.innerHTML = \"
        <div class='stat'><span class='stat-label'>Queue Length</span><span class='stat-value'>\" + status.queueLength + \"</span></div>\n        <div class='stat'><span class='stat-label'>Active Tasks</span><span class='stat-value warning'>\" + status.activeTasks + \"</span></div>\n        <div class='stat'><span class='stat-label'>Completed</span><span class='stat-value success'>\" + status.completedTasks + \"</span></div>\n      \";
      
      // Render agents list
      let agentsList = document.getElementById('engineAgentsList');
      if (status.agents && status.agents.length > 0) {
        agentsList.innerHTML = status.agents.slice(0, 5).map(agent => \"
          <div class=\"agent-item\" style=\"display: flex; justify-content: space-between; padding: 8px; background: #0f172a; border-radius: 6px; margin-bottom: 4px;\">\n            <span style=\"color: #f1f5f9;\">\" + agent.id + \"</span>\n            <span class=\"status-badge status-\" + agent.status + \">\" + agent.status + \"</span>\n          </div>\n        \").join('');
      }
    }
    
    async function fetchTasks() {
      try {
        const response = await fetch('/api/tasks');
        const data = await response.json();
        updateTasks(data.tasks || []);
      } catch (error) {
        console.error('Failed to fetch tasks:', error);
      }
    }
    
    function updateTasks(tasks) {
      document.getElementById('recentCount').textContent = tasks.length;
      document.getElementById('queueCount').textContent = tasks.filter(t => t.status === 'pending').length;
      
      // Task metrics
      let queueStats = document.getElementById('queueStats');
      const pending = tasks.filter(t => t.status === 'pending').length;
      const inProgress = tasks.filter(t => t.status === 'in_progress' || t.status === 'assigned').length;
      const completed = tasks.filter(t => t.status === 'completed').length;
      const failed = tasks.filter(t => t.status === 'failed').length;
      
      queueStats.innerHTML = \"
        <div class='stat'><span class='stat-label'>Pending</span><span class='stat-value'>\" + pending + \"</span></div>\n        <div class='stat'><span class='stat-label'>In Progress</span><span class='stat-value info'>\" + inProgress + \"</span></div>\n        <div class='stat'><span class='stat-label'>Completed</span><span class='stat-value success'>\" + completed + \"</span></div>\n        <div class='stat'><span class='stat-label'>Failed</span><span class='stat-value error'>\" + failed + \"</span></div>\n      \";
      
      // System stats
      let systemStats = document.getElementById('systemStats');
      systemStats.innerHTML = \"
        <div class='stat'><span class='stat-label'>Total Tasks</span><span class='stat-value'>\" + tasks.length + \"</span></div>\n        <div class='stat'><span class='stat-label'>Success Rate</span><span class='stat-value success'>\" + (tasks.length > 0 ? (completed / tasks.length * 100).toFixed(1) + '%' : 'N/A') + \"</span></div>\n        <div class='stat'><span class='stat-label'>Workforce Agents</span><span class='stat-value'>\" + (window.engineAgentCount || 0) + \"</span></div>\n        <div class='stat'><span class='stat-label'>Receptionist Agents</span><span class='stat-value purple'>4</span></div>\n      \";
      
      // Industry stats (mock data for demo)
      let industryStats = document.getElementById('industryStats');
      industryStats.innerHTML = \"
        <div class='stat'><span class='stat-label'>Healthcare</span><span class='stat-value'>\" + Math.floor(Math.random() * 5) + \"</span></div>\n        <div class='stat'><span class='stat-label'>Corporate</span><span class='stat-value'>\" + Math.floor(Math.random() * 8) + \"</span></div>\n        <div class='stat'><span class='stat-label'>Hospitality</span><span class='stat-value'>\" + Math.floor(Math.random() * 4) + \"</span></div>\n        <div class='stat'><span class='stat-label'>Retail</span><span class='stat-value'>\" + Math.floor(Math.random() * 3) + \"</span></div>\n      \";
      
      // Tasks table
      let tasksTable = document.getElementById('tasksTable');
      const recentTasks = tasks.slice(-15).reverse();
      
      if (recentTasks.length > 0) {
        tasksTable.innerHTML = recentTasks.map(task => \"
          <tr>\n            <td style=\"color: #38bdf8; font-size: 11px;\">\" + (task.id || '').substring(0, 12) + \"</td>\n            <td class=\"task-desc\" title=\"/\" + (task.description || '') + \"/\">\" + (task.description || 'No description').substring(0, 40) + \"</td>\n            <td><span class=\"industry-badge\">\" + (task.type || 'generic') + \"</span></td>\n            <td><span class=\"industry-badge\">\" + ((task.context?.variables?.industry) || 'corporate') + \"</span></td>\n            <td><span class=\"badge badge-\" + (task.status || 'pending') + \">\" + (task.status || 'pending') + \"</span></td>\n            <td><span class=\"badge badge-\" + (task.priority || 'medium') + \">\" + (task.priority || 'medium') + \"</span></td>\n            <td style=\"color: #94a3b8; font-size: 11px;\">\" + (task.assignedAgent || '-') + \"</td>\n            <td style=\"color: #64748b; font-size: 11px;\">\" + (task.createdAt ? new Date(task.createdAt).toLocaleTimeString() : '-') + \"</td>\n          </tr>\n        \").join('');
      } else {
        tasksTable.innerHTML = '<tr><td colspan=\"8\" style=\"text-align: center; color: #94a3b8;\">No tasks yet. Submit one above!</td></tr>';
      }
    }
    
    async function submitReceptionistTask() {
      const input = document.getElementById('taskInput');
      const industry = document.getElementById('taskIndustry').value;
      const priority = document.getElementById('taskPriority').value;
      const description = input.value.trim();
      
      if (!description) {
        alert('Please enter a task description');
        return;
      }
      
      try {
        const response = await fetch('/api/tasks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            description, 
            priority,
            context: {
              industry,
              purpose: description,
              visitorLanguage: 'English',
              sentiment: 'neutral',
              urgency: priority,
              sessionId: 'dashboard-' + Date.now()
            }
          })
        });
        
        const data = await response.json();
        console.log('Task submitted:', data);
        input.value = '';
        setTimeout(() => { fetchEngineStatus(); fetchTasks(); }, 500);
      } catch (error) {
        console.error('Failed to submit task:', error);
        alert('Failed to submit task');
      }
    }
    
    document.getElementById('taskInput').addEventListener('keypress', (e) => {
      if (e.key === 'Enter') submitReceptionistTask();
    });
    
    // Initial render
    renderReceptionistAgents(receptionistAgents);
    renderTools();
    
    // Initial fetch
    fetchEngineStatus();
    fetchTasks();
    
    // Track submitted tasks for realistic agent simulation
    let submittedTasks = [];
    
    // Override task submission to track for simulation
    const originalSubmit = submitReceptionistTask;
    window.submitReceptionistTask = async function() {
      await originalSubmit();
      submittedTasks.push({ time: Date.now(), agent: ['ARIA', 'CHRONOS', 'WIKI', 'CONNECT'][Math.floor(Math.random() * 4)] });
      // Clean up old tasks to prevent memory leak - keep only last 50
      if (submittedTasks.length > 50) {
        submittedTasks = submittedTasks.filter(t => Date.now() - t.time < 30000);
      }
    };
    
    // Auto-refresh every 3 seconds
    setInterval(() => { 
      fetchEngineStatus(); 
      fetchTasks();
      
      // Simulate agent activity based on actual task load
      receptionistAgents.forEach(agent => {
        // Find tasks assigned to this agent type
        const agentTaskCount = submittedTasks.filter(t => {
          if (t.agent === 'ARIA' && agent.name === 'ARIA') return true;
          if (t.agent === 'CHRONOS' && agent.name === 'CHRONOS') return true;
          if (t.agent === 'WIKI' && agent.name === 'WIKI') return true;
          if (t.agent === 'CONNECT' && agent.name === 'CONNECT') return true;
          return false;
        }).length;
        
        // If there are recent tasks, agent is busy
        const recentTasks = submittedTasks.filter(t => Date.now() - t.time < 10000);
        if (recentTasks.length > 0 && Math.random() > 0.3) {
          agent.status = 'busy';
        } else {
          agent.status = 'idle';
        }
        agent.tasksHandled = agentTaskCount;
      });
      renderReceptionistAgents(receptionistAgents);
    }, 3000);
  </script>
</body>
</html>
  `)
})

// Mount dashboard routes
export function setupDashboard(app: express.Application): void {
  app.use('/dashboard', router)
  
  // Also serve at root
  app.get('/', (_req: Request, res: Response) => {
    res.redirect('/dashboard')
  })
}