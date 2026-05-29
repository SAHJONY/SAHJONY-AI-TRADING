/**
 * ============================================================
 * AI RECEPTIONIST - Web Dashboard & REST API
 * ============================================================
 */

import express, { Request, Response } from 'express'
import { getReceptionist, ReceptionistAgent } from './ReceptionistAgent'


const router = express.Router()

// Get receptionist instance
function getAgent(): ReceptionistAgent {
  return getReceptionist()
}

// ============================================================================
// CHAT / INTERACTION
// ============================================================================

router.post('/chat', (req: Request, res: Response) => {
  const { message, visitorId, industry, sessionId } = req.body
  if (!message) return res.status(400).json({ error: 'Message required' })
  
  // Use sessionId for visitor tracking if provided
  const effectiveVisitorId = visitorId || sessionId || `VIS-${Date.now()}`
  
  getAgent().processVisitorInput(message, effectiveVisitorId)
    .then(response => res.json({
      response: response.content,
      agent: response.agent,
      actions: response.actions,
      requiresHumanEscalation: response.requiresEscalation,
      timestamp: new Date().toISOString(),
      sessionId: effectiveVisitorId,
      industry: industry || 'corporate'
    }))
    .catch(error => res.status(500).json({ error: error.message }))
})

// ============================================================================
// VISITORS
// ============================================================================

router.get('/visitors', (_req: Request, res: Response) => {
  const agent = getAgent()
  res.json({
    waiting: agent.getWaitingVisitors(),
    total: agent.getContext().visitors.length
  })
})

router.post('/visitors/checkin', (req: Request, res: Response) => {
  const { name, purpose, email } = req.body
  if (!name || !purpose) return res.status(400).json({ error: 'name and purpose required' })
  
  const visitor = getAgent().checkInVisitor(name, purpose, email)
  res.json({ visitor, message: `${name} checked in for ${purpose}` })
})

router.put('/visitors/:visitorId/status', (req: Request, res: Response) => {
  const { status } = req.body
  const ctx = getAgent().getContext()
  const visitor = ctx.visitors.find(v => v.id === req.params.visitorId)
  if (!visitor) return res.status(404).json({ error: 'Visitor not found' })
  
  visitor.status = status as any
  res.json({ visitor, updated: true })
})

// ============================================================================
// APPOINTMENTS
// ============================================================================

router.get('/appointments', (_req: Request, res: Response) => {
  res.json({
    today: getAgent().getTodayAppointments(),
    total: getAgent().getContext().appointments.length
  })
})

router.post('/appointments', (req: Request, res: Response) => {
  const { clientName, service, dateTime, duration } = req.body
  if (!clientName || !service) return res.status(400).json({ error: 'clientName and service required' })
  
  const agent = getAgent()
  const appointment = {
    id: `APT-${Date.now()}`,
    clientName,
    service,
    dateTime: dateTime ? new Date(dateTime) : new Date(),
    duration: duration || 30,
    status: 'scheduled' as const,
    industry: 'corporate' as const
  }
  agent.getContext().appointments.push(appointment)
  
  res.json({ message: `Appointment booked for ${clientName}`, appointment })
})

// ============================================================================
// ESCALATIONS
// ============================================================================

router.get('/escalations', (_req: Request, res: Response) => {
  res.json({
    open: getAgent().getOpenEscalations(),
    total: getAgent().getContext().escalations.length
  })
})

router.post('/escalations', (req: Request, res: Response) => {
  const { reason, visitorId, priority } = req.body
  if (!reason) return res.status(400).json({ error: 'reason required' })
  
  const ctx = getAgent().getContext()
  const ticket = {
    id: `ESC-${Date.now()}`,
    visitorId,
    reason,
    priority: priority || 'medium',
    status: 'open' as const,
    createdAt: new Date()
  }
  ctx.escalations.push(ticket)
  
  res.json({ ticket, message: 'Escalation ticket created' })
})

router.put('/escalations/:ticketId/resolve', (req: Request, res: Response) => {
  const { resolution } = req.body
  const ctx = getAgent().getContext()
  const ticket = ctx.escalations.find(t => t.id === req.params.ticketId)
  if (!ticket) return res.status(404).json({ error: 'Ticket not found' })
  
  ticket.status = 'resolved'
  ticket.resolvedAt = new Date()
  ticket.resolution = resolution
  
  res.json({ ticket, message: 'Ticket resolved' })
})

// ============================================================================
// STATS & METRICS
// ============================================================================

router.get('/stats', (_req: Request, res: Response) => {
  res.json(getAgent().getStats())
})

router.get('/context', (_req: Request, res: Response) => {
  const ctx = getAgent().getContext()
  res.json({
    industry: ctx.industry,
    visitors: ctx.visitors.length,
    appointments: ctx.appointments.length,
    escalations: ctx.escalations.filter(e => e.status === 'open').length,
    stats: getAgent().getStats()
  })
})

// ============================================================================
// DASHBOARD HTML
// ============================================================================

export function setupReceptionistDashboard(app: express.Application): void {
  app.use('/api/receptionist', router)
  
  app.get('/receptionist', (_req: Request, res: Response) => {
    res.send(getDashboardHTML())
  })
  
  console.log('\n  AI Receptionist ready at:')
  console.log('  - Dashboard: http://localhost:3000/receptionist')
  console.log('  - API Base: /api/receptionist')
}

function getDashboardHTML(): string {
  return `<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>AI Receptionist Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a1a; color: #fff; min-height: 100vh; }
    .header { background: linear-gradient(135deg, #00d4aa, #00a8cc); padding: 24px; text-align: center; }
    .header h1 { font-size: 28px; margin-bottom: 8px; }
    .header p { opacity: 0.9; }
    .container { display: grid; grid-template-columns: 300px 1fr; min-height: calc(100vh - 80px); }
    .sidebar { background: #12122a; padding: 20px; border-right: 1px solid #2a2a4a; }
    .section { margin-bottom: 24px; }
    .section-title { font-size: 12px; text-transform: uppercase; color: #666; margin-bottom: 12px; letter-spacing: 1px; }
    .stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .stat-card { background: #1a1a3a; padding: 16px; border-radius: 12px; text-align: center; }
    .stat-value { font-size: 28px; font-weight: 700; color: #00d4aa; }
    .stat-label { font-size: 11px; color: #888; margin-top: 4px; text-transform: uppercase; }
    .agent-card { background: #1a1a3a; padding: 12px; border-radius: 8px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
    .agent-name { font-weight: 600; color: #00d4aa; }
    .agent-status { font-size: 12px; color: #888; }
    .agent-status.active { color: #00ff88; }
    .main { padding: 24px; overflow-y: auto; }
    .panel { display: none; }
    .panel.active { display: block; }
    .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .panel-header h2 { font-size: 20px; }
    .visitor-list, .apt-list { display: flex; flex-direction: column; gap: 12px; }
    .visitor-card, .apt-card { background: #1a1a3a; padding: 16px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; }
    .visitor-info h3 { font-size: 16px; margin-bottom: 4px; }
    .visitor-info p { font-size: 13px; color: #888; }
    .badge { padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
    .badge.waiting { background: #ffaa00; color: #000; }
    .badge.scheduled { background: #00d4aa; color: #000; }
    .badge.open { background: #ff4466; color: #fff; }
    .chat-area { background: #1a1a3a; border-radius: 16px; padding: 20px; height: 400px; overflow-y: auto; margin-bottom: 16px; }
    .chat-message { max-width: 80%; padding: 12px 16px; border-radius: 16px; margin-bottom: 12px; line-height: 1.5; }
    .chat-message.agent { background: #2a2a5a; border-bottom-left-radius: 4px; }
    .chat-message.user { background: #00d4aa; color: #000; align-self: flex-end; border-bottom-right-radius: 4px; }
    .input-area { display: flex; gap: 12px; }
    .input-area input { flex: 1; padding: 16px; border-radius: 12px; border: 1px solid #3a3a5a; background: #0a0a1a; color: #fff; font-size: 16px; outline: none; }
    .input-area input:focus { border-color: #00d4aa; }
    .input-area button { padding: 16px 32px; background: #00d4aa; border: none; border-radius: 12px; color: #000; font-weight: 600; cursor: pointer; }
    .quick-actions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
    .quick-btn { padding: 8px 16px; background: #2a2a5a; border: none; border-radius: 8px; color: #fff; font-size: 13px; cursor: pointer; }
    .quick-btn:hover { background: #3a3a6a; }
    .empty-state { text-align: center; padding: 40px; color: #666; }
    .nav-item { padding: 12px 16px; border-radius: 8px; cursor: pointer; color: #888; margin-bottom: 4px; }
    .nav-item:hover, .nav-item.active { background: #2a2a4a; color: #fff; }
    .nav-item.active { border-left: 3px solid #00d4aa; }
  </style>
</head>
<body>
  <div class=\"header\">
    <h1>🤖 AI Receptionist</h1>
    <p>ARIA + CHRONOS + WIKI + CONNECT</p>
  </div>
  
  <div class=\"container\">
    <div class=\"sidebar\">
      <div class=\"section\">
        <div class=\"section-title\">Agent Status</div>
        <div class=\"agent-card\">
          <div><span class=\"agent-name\">ARIA</span><br><span class=\"agent-status active\">Voice • Active</span></div>
          <div style=\"text-align:right\"><span class=\"agent-status\" id=\"aria-calls\">0</span><br><small>calls</small></div>
        </div>
        <div class=\"agent-card\">
          <div><span class=\"agent-name\">CHRONOS</span><br><span class=\"agent-status active\">Scheduler • Active</span></div>
          <div style=\"text-align:right\"><span class=\"agent-status\" id=\"chronos-books\">0</span><br><small>booked</small></div>
        </div>
        <div class=\"agent-card\">
          <div><span class=\"agent-name\">WIKI</span><br><span class=\"agent-status active\">Knowledge • Active</span></div>
          <div style=\"text-align:right\"><span class=\"agent-status\" id=\"wiki-queries\">0</span><br><small>queries</small></div>
        </div>
        <div class=\"agent-card\">
          <div><span class=\"agent-name\">CONNECT</span><br><span class=\"agent-status active\">Escalation • Active</span></div>
          <div style=\"text-align:right\"><span class=\"agent-status\" id=\"connect-tickets\">0</span><br><small>resolved</small></div>
        </div>
      </div>
      
      <div class=\"section\">
        <div class=\"section-title\">Queue Stats</div>
        <div class=\"stat-grid\">
          <div class=\"stat-card\">
            <div class=\"stat-value\" id=\"waiting-count\">0</div>
            <div class=\"stat-label\">Waiting</div>
          </div>
          <div class=\"stat-card\">
            <div class=\"stat-value\" id=\"served-today\">0</div>
            <div class=\"stat-label\">Served</div>
          </div>
          <div class=\"stat-card\">
            <div class=\"stat-value\" id=\"appointments-today\">0</div>
            <div class=\"stat-label\">Appointments</div>
          </div>
          <div class=\"stat-card\">
            <div class=\"stat-value\" id=\"open-tickets\">0</div>
            <div class=\"stat-label\">Open Tickets</div>
          </div>
        </div>
      </div>
      
      <div class=\"section\">
        <div class=\"section-title\">Navigation</div>
        <div class=\"nav-item active\" onclick=\"showPanel('chat')\">💬 Live Chat</div>
        <div class=\"nav-item\" onclick=\"showPanel('visitors')\">👥 Visitors</div>
        <div class=\"nav-item\" onclick=\"showPanel('appointments')\">📅 Appointments</div>
        <div class=\"nav-item\" onclick=\"showPanel('escalations')\">🎫 Escalations</div>
      </div>
    </div>
    
    <div class=\"main\">
      <div id=\"chatPanel\" class=\"panel active\">
        <div class=\"panel-header\"><h2>Live Receptionist Chat</h2></div>
        <div class=\"chat-area\" id=\"chatArea\">
          <div class=\"chat-message agent\">Hello! I'm ARIA, your AI receptionist. How may I assist you today?</div>
        </div>
        <div class=\"input-area\">
          <input type=\"text\" id=\"msgInput\" placeholder=\"Type your message...\" onkeypress=\"handleEnter(event)\">
          <button onclick=\"sendMessage()\">Send</button>
        </div>
        <div class=\"quick-actions\">
          <button class=\"quick-btn\" onclick=\"quickAction('I need to schedule an appointment')\">📅 Schedule</button>
          <button class=\"quick-btn\" onclick=\"quickAction('What are your business hours?')\">❓ Hours</button>
          <button class=\"quick-btn\" onclick=\"quickAction('I need to speak to someone')\">👤 Human</button>
          <button class=\"quick-btn\" onclick=\"quickAction('Where is your office located?')\">📍 Directions</button>
        </div>
      </div>
      
      <div id=\"visitorsPanel\" class=\"panel\">
        <div class=\"panel-header\"><h2>Visitor Queue</h2><button class=\"quick-btn\" onclick=\"showCheckIn()\">+ Check In</button></div>
        <div class=\"visitor-list\" id=\"visitorList\">
          <div class=\"empty-state\">No visitors in queue</div>
        </div>
      </div>
      
      <div id=\"appointmentsPanel\" class=\"panel\">
        <div class=\"panel-header\"><h2>Today's Appointments</h2></div>
        <div class=\"apt-list\" id=\"aptList\">
          <div class=\"empty-state\">No appointments today</div>
        </div>
      </div>
      
      <div id=\"escalationsPanel\" class=\"panel\">
        <div class=\"panel-header\"><h2>Open Escalations</h2></div>
        <div id=\"escList\">
          <div class=\"empty-state\">No open escalations</div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let currentPanel = 'chat'
    
    function showPanel(p) {
      document.querySelectorAll('.panel').forEach(el => el.classList.remove('active'))
      document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'))
      document.getElementById(p + 'Panel').classList.add('active')
      event.target.classList.add('active')
      currentPanel = p
      refreshData()
    }
    
    async function sendMessage() {
      const input = document.getElementById('msgInput')
      const msg = input.value.trim()
      if (!msg) return
      
      const chatArea = document.getElementById('chatArea')
      chatArea.innerHTML += '<div class=\"chat-message user\">' + msg + '</div>'
      input.value = ''
      
      try {
        const r = await fetch('/api/receptionist/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: msg })
        })
        const d = await r.json()
        chatArea.innerHTML += '<div class=\"chat-message agent\">' + d.response + '</div>'
        chatArea.scrollTop = chatArea.scrollHeight
      } catch(e) {
        chatArea.innerHTML += '<div class=\"chat-message agent\">Sorry, I encountered an error.</div>'
      }
    }
    
    function handleEnter(e) { if (e.key === 'Enter') sendMessage() }
    
    function quickAction(msg) {
      document.getElementById('msgInput').value = msg
      sendMessage()
    }
    
    async function refreshData() {
      try {
        const ctx = await fetch('/api/receptionist/context').then(r => r.json())
        
        // Update stats
        document.getElementById('aria-calls').textContent = ctx.stats.agentStats.aria.callsHandled
        document.getElementById('chronos-books').textContent = ctx.stats.agentStats.chronos.appointmentsBooked
        document.getElementById('wiki-queries').textContent = ctx.stats.agentStats.wiki.queriesAnswered
        document.getElementById('connect-tickets').textContent = ctx.stats.agentStats.connect.ticketsResolved
        
        document.getElementById('waiting-count').textContent = ctx.stats.queueStats.waitingCount
        document.getElementById('served-today').textContent = ctx.stats.queueStats.totalServedToday
        document.getElementById('appointments-today').textContent = ctx.appointments
        document.getElementById('open-tickets').textContent = ctx.escalations
        
        // Update visitor list
        if (currentPanel === 'visitors') {
          const visitors = await fetch('/api/receptionist/visitors').then(r => r.json())
          const list = document.getElementById('visitorList')
          if (visitors.waiting.length === 0) {
            list.innerHTML = '<div class=\"empty-state\">No visitors in queue</div>'
          } else {
            list.innerHTML = visitors.waiting.map(v => '
              <div class=\"visitor-card\">
                <div class=\"visitor-info\"><h3>' + v.name + '</h3><p>' + v.purpose + '</p></div>
                <span class=\"badge waiting\">' + v.status + '</span>
              </div>
            ').join('')
          }
        }
        
        // Update appointments
        if (currentPanel === 'appointments') {
          const apts = await fetch('/api/receptionist/appointments').then(r => r.json())
          const list = document.getElementById('aptList')
          if (apts.today.length === 0) {
            list.innerHTML = '<div class=\"empty-state\">No appointments today</div>'
          } else {
            list.innerHTML = apts.today.map(a => '
              <div class=\"apt-card\">
                <div class=\"visitor-info\"><h3>' + a.clientName + '</h3><p>' + a.service + ' • ' + new Date(a.dateTime).toLocaleTimeString() + '</p></div>
                <span class=\"badge scheduled\">' + a.status + '</span>
              </div>
            ').join('')
          }
        }
        
        // Update escalations
        if (currentPanel === 'escalations') {
          const esc = await fetch('/api/receptionist/escalations').then(r => r.json())
          const list = document.getElementById('escList')
          if (esc.open.length === 0) {
            list.innerHTML = '<div class=\"empty-state\">No open escalations</div>'
          } else {
            list.innerHTML = esc.open.map(e => '
              <div class=\"apt-card\">
                <div class=\"visitor-info\"><h3>#' + e.id + '</h3><p>' + e.reason.substring(0, 50) + '...</p></div>
                <span class=\"badge open\">' + e.priority + '</span>
              </div>
            ').join('')
          }
        }
      } catch(e) { console.error(e) }
    }
    
    function showCheckIn() {
      const name = prompt('Visitor name:')
      if (!name) return
      const purpose = prompt('Purpose of visit:')
      if (!purpose) return
      fetch('/api/receptionist/visitors/checkin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, purpose })
      }).then(() => refreshData())
    }
    
    // Refresh every 10 seconds
    setInterval(refreshData, 10000)
    refreshData()
  </script>
</body>
</html>`
}

export default router