/**
 * ============================================================
 * PERSONAL AI AGENT - Web Dashboard
 * ============================================================
 */

import express, { Request, Response } from 'express'
import { v4 as uuid } from 'uuid'
import { getPersonalAgent, PersonalAgent } from './PersonalAgent'
import { PersonalContext } from './types'

const router = express.Router()
const userSessions: Map<string, { agent: PersonalAgent; lastActive: Date }> = new Map()

function getOrCreateAgent(userId: string, userName: string): PersonalAgent {
  if (!userSessions.has(userId)) {
    const agent = getPersonalAgent(userId, userName)
    userSessions.set(userId, { agent, lastActive: new Date() })
  }
  userSessions.get(userId)!.lastActive = new Date()
  return userSessions.get(userId)!.agent
}

function getContext(agent: PersonalAgent): PersonalContext {
  return agent.getContext()
}

// ============================================================================
// CHAT
// ============================================================================

router.post('/chat', (req: Request, res: Response) => {
  const { userId, userName, message } = req.body
  if (!userId || !message) return res.status(400).json({ error: 'userId and message required' })

  getOrCreateAgent(userId, userName || 'User').processMessage(message)
    .then(response => res.json({
      response: response.content,
      confidence: response.confidence,
      actions: response.actions,
      suggestedActions: response.suggestedActions,
      timestamp: new Date().toISOString()
    }))
    .catch(error => res.status(500).json({ error: error.message }))
})

router.get('/history/:userId', (req: Request, res: Response) => {
  res.json({ messages: getOrCreateAgent(req.params.userId, 'User').getConversationHistory() })
})

// ============================================================================
// CONTEXT & STATS
// ============================================================================

router.get('/context/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const now = new Date()
  res.json({
    userId: ctx.userId, name: ctx.name, email: ctx.email, timezone: ctx.timezone,
    preferences: ctx.preferences,
    stats: {
      pendingTasks: ctx.tasks.filter(t => t.status === 'pending').length,
      todayMeetings: ctx.calendar.filter(e => new Date(e.startTime).toDateString() === now.toDateString() && e.status !== 'cancelled').length,
      totalNotes: ctx.notes.length,
      activeReminders: ctx.reminders.filter(r => r.status === 'active').length,
      memoriesStored: ctx.memory.length,
      totalEmails: ctx.emails.length,
      unreadEmails: ctx.emails.filter(e => !e.isRead).length,
      totalContacts: ctx.contacts.length,
      totalTravelPlans: ctx.travel.length,
      healthEntries: ctx.health.length
    }
  })
})

// ============================================================================
// TASKS
// ============================================================================

router.get('/tasks/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  let tasks = ctx.tasks
  if (req.query.status) tasks = tasks.filter(t => t.status === req.query.status)
  res.json({ tasks, total: tasks.length })
})

router.post('/tasks/:userId', (req: Request, res: Response) => {
  const { title, description, dueDate, priority } = req.body
  if (!title) return res.status(400).json({ error: 'Title required' })
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const task = { id: uuid(), title, description: description || '', dueDate: dueDate ? new Date(dueDate) : undefined, priority: priority || 'medium', status: 'pending' as const, createdAt: new Date(), tags: [], subtasks: [], attachments: [] }
  ctx.tasks.push(task)
  res.json({ task, message: `Task created: ${title}` })
})

router.put('/tasks/:userId/:taskId/complete', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const task = ctx.tasks.find(t => t.id === req.params.taskId)
  if (!task) return res.status(404).json({ error: 'Task not found' })
  task.status = 'completed'
  task.completedAt = new Date()
  res.json({ taskId: task.id, status: 'completed' })
})

router.delete('/tasks/:userId/:taskId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const idx = ctx.tasks.findIndex(t => t.id === req.params.taskId)
  if (idx === -1) return res.status(404).json({ error: 'Task not found' })
  ctx.tasks.splice(idx, 1)
  res.json({ deleted: true })
})

// ============================================================================
// CALENDAR
// ============================================================================

router.get('/calendar/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  res.json({ events: ctx.calendar, total: ctx.calendar.length })
})

router.post('/calendar/:userId', (req: Request, res: Response) => {
  const { title, startTime, endTime, location, attendees } = req.body
  if (!title || !startTime) return res.status(400).json({ error: 'Title and startTime required' })
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const event = { id: uuid(), title, description: '', startTime: new Date(startTime), endTime: endTime ? new Date(endTime) : new Date(new Date(startTime).getTime() + 3600000), location: location || '', attendees: attendees || [], reminders: [{ minutesBefore: 15, sent: false }], status: 'confirmed' as const }
  ctx.calendar.push(event)
  res.json({ event, message: `Event created: ${title}` })
})

router.delete('/calendar/:userId/:eventId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const idx = ctx.calendar.findIndex(e => e.id === req.params.eventId)
  if (idx === -1) return res.status(404).json({ error: 'Event not found' })
  ctx.calendar.splice(idx, 1)
  res.json({ deleted: true })
})

// ============================================================================
// NOTES
// ============================================================================

router.get('/notes/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  res.json({ notes: ctx.notes, total: ctx.notes.length })
})

router.post('/notes/:userId', (req: Request, res: Response) => {
  const { title, content, tags } = req.body
  if (!content) return res.status(400).json({ error: 'Content required' })
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const note = { id: uuid(), title: title || 'Untitled', content, createdAt: new Date(), updatedAt: new Date(), tags: tags || [], isPinned: false, isArchived: false }
  ctx.notes.push(note)
  res.json({ note, message: 'Note created' })
})

router.delete('/notes/:userId/:noteId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const idx = ctx.notes.findIndex(n => n.id === req.params.noteId)
  if (idx === -1) return res.status(404).json({ error: 'Note not found' })
  ctx.notes.splice(idx, 1)
  res.json({ deleted: true })
})

// ============================================================================
// REMINDERS
// ============================================================================

router.get('/reminders/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  res.json({ reminders: ctx.reminders.filter(r => r.status === 'active'), total: ctx.reminders.length })
})

router.post('/reminders/:userId', (req: Request, res: Response) => {
  const { title, message, triggerTime, repeat } = req.body
  if (!title || !triggerTime) return res.status(400).json({ error: 'Title and triggerTime required' })
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const reminder = { id: uuid(), title, message: message || '', triggerTime: new Date(triggerTime), status: 'active' as const, repeat }
  ctx.reminders.push(reminder)
  res.json({ reminder, message: `Reminder set: ${title}` })
})

router.delete('/reminders/:userId/:reminderId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const idx = ctx.reminders.findIndex(r => r.id === req.params.reminderId)
  if (idx === -1) return res.status(404).json({ error: 'Reminder not found' })
  ctx.reminders.splice(idx, 1)
  res.json({ deleted: true })
})

// ============================================================================
// EMAILS
// ============================================================================

router.get('/emails/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  res.json({ emails: ctx.emails, total: ctx.emails.length })
})

router.post('/emails/:userId', (req: Request, res: Response) => {
  const { to, subject, body } = req.body
  if (!to || !subject || !body) return res.status(400).json({ error: 'to, subject, body required' })
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const email = { id: uuid(), from: { email: ctx.email || 'assistant@personal.ai', name: ctx.name }, to: Array.isArray(to) ? to : [{ email: to }], subject, body, timestamp: new Date(), isRead: true, isStarred: false, isArchived: false, labels: [], attachments: [], priority: 'normal' as const }
  ctx.emails.push(email)
  res.json({ email, message: 'Email drafted' })
})

// ============================================================================
// CONTACTS
// ============================================================================

router.get('/contacts/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  res.json({ contacts: ctx.contacts, total: ctx.contacts.length })
})

router.post('/contacts/:userId', (req: Request, res: Response) => {
  const { firstName, lastName, company, emails } = req.body
  if (!firstName || !lastName) return res.status(400).json({ error: 'firstName and lastName required' })
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const contact = { id: uuid(), firstName, lastName, company, emails: emails || [], phones: [], addresses: [], tags: [], relationship: 'other' as const, socialProfiles: [] }
  ctx.contacts.push(contact)
  res.json({ contact, message: `Contact added: ${firstName} ${lastName}` })
})

// ============================================================================
// FILES
// ============================================================================

router.get('/files/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  res.json({ files: ctx.files, total: ctx.files.length })
})

router.post('/files/:userId', (req: Request, res: Response) => {
  const { filename, mimeType, size } = req.body
  if (!filename) return res.status(400).json({ error: 'filename required' })
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const file = { id: uuid(), filename, mimeType: mimeType || 'application/octet-stream', size: size || 0, uploadedAt: new Date(), tags: [], folder: 'root' }
  ctx.files.push(file)
  res.json({ file, message: 'File added' })
})

// ============================================================================
// FINANCES
// ============================================================================

router.get('/finances/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const total = ctx.finances.reduce((s: number, a: any) => s + a.balance, 0)
  res.json({ accounts: ctx.finances, totalBalance: total, total: ctx.finances.length })
})

router.post('/finances/:userId/accounts', (req: Request, res: Response) => {
  const { name, type, balance, institution } = req.body
  if (!name || !type) return res.status(400).json({ error: 'name and type required' })
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const account = { id: uuid(), name, type, institution: institution || '', balance: balance || 0, currency: 'USD', lastSynced: new Date() }
  ctx.finances.push(account)
  res.json({ account, message: `Account added: ${name}` })
})

// ============================================================================
// TRAVEL
// ============================================================================

router.get('/travel/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  res.json({ plans: ctx.travel, total: ctx.travel.length })
})

router.post('/travel/:userId', (req: Request, res: Response) => {
  const { type, startDate, endDate } = req.body
  if (!type || !startDate) return res.status(400).json({ error: 'type and startDate required' })
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const plan = { id: uuid(), type, status: 'planned' as const, startDate: new Date(startDate), endDate: endDate ? new Date(endDate) : new Date(startDate), details: {} as any }
  ctx.travel.push(plan)
  res.json({ plan, message: `Travel plan added: ${type}` })
})

// ============================================================================
// HEALTH
// ============================================================================

router.get('/health/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  res.json({ metrics: ctx.health, total: ctx.health.length })
})

router.post('/health/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const metrics = { id: uuid(), date: new Date(), weight: req.body.weight, heartRate: req.body.heartRate, sleepHours: req.body.sleepHours, mood: req.body.mood }
  ctx.health.push(metrics)
  res.json({ metrics, message: 'Health metrics logged' })
})

// ============================================================================
// RESEARCH
// ============================================================================

router.get('/research/:userId', (req: Request, res: Response) => {
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  res.json({ items: ctx.research, total: ctx.research.length })
})

router.post('/research/:userId', (req: Request, res: Response) => {
  const { topic, summary, sourceUrl } = req.body
  if (!topic) return res.status(400).json({ error: 'topic required' })
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const item = { id: uuid(), topic, summary: summary || '', sourceUrl, keyPoints: [], createdAt: new Date(), updatedAt: new Date(), tags: [] }
  ctx.research.push(item)
  res.json({ item, message: `Research saved: ${topic}` })
})

// ============================================================================
// MEMORY
// ============================================================================

router.post('/remember/:userId', (req: Request, res: Response) => {
  const { content, type, importance } = req.body
  if (!content) return res.status(400).json({ error: 'Content required' })
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  ctx.memory.push({ id: uuid(), timestamp: new Date(), type: type || 'fact', content, importance: importance || 'medium', tags: [] })
  res.json({ message: 'Memory stored' })
})

router.get('/recall/:userId', (req: Request, res: Response) => {
  const q = (req.query.q as string) || ''
  const ctx = getContext(getOrCreateAgent(req.params.userId, 'User'))
  const memories = ctx.memory.filter(m => m.content.toLowerCase().includes(q.toLowerCase())).slice(-20)
  res.json({ memories, total: memories.length })
})

// ============================================================================
// SESSION
// ============================================================================

router.delete('/session/:userId', (req: Request, res: Response) => {
  userSessions.delete(req.params.userId)
  res.json({ loggedOut: true })
})

// ============================================================================
// DASHBOARD HTML
// ============================================================================

export function setupPersonalAgentDashboard(app: express.Application): void {
  app.use('/api/personal-agent', router)

  app.get('/personal-assistant', (_req: Request, res: Response) => {
    res.send(getDashboardHTML())
  })

  console.log('\n  Personal AI Assistant ready at:')
  console.log('  - Dashboard: http://localhost:3000/personal-assistant')
  console.log('  - API Base: /api/personal-agent')
}

function getDashboardHTML(): string {
  return `<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>Personal AI Assistant</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f0f1a; color: #fff; height: 100vh; overflow: hidden; }
    .container { display: flex; height: 100vh; }
    .sidebar { width: 280px; background: #1a1a2e; padding: 20px; border-right: 1px solid #2a2a4a; display: flex; flex-direction: column; overflow-y: auto; }
    .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
    .header { padding: 20px; background: #1a1a2e; border-bottom: 1px solid #2a2a4a; }
    .header h1 { font-size: 24px; background: linear-gradient(135deg, #667eea, #764ba2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .chat-area { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; }
    .input-area { padding: 20px; background: #1a1a2e; border-top: 1px solid #2a2a4a; }
    .input-area input { width: 100%; padding: 16px; border-radius: 12px; border: 1px solid #3a3a5a; background: #0f0f1a; color: #fff; font-size: 16px; outline: none; }
    .input-area input:focus { border-color: #667eea; }
    .message { max-width: 70%; padding: 12px 16px; border-radius: 16px; line-height: 1.5; white-space: pre-wrap; }
    .message.user { background: #667eea; align-self: flex-end; border-bottom-right-radius: 4px; }
    .message.agent { background: #2a2a4a; align-self: flex-start; border-bottom-left-radius: 4px; }
    .nav-item { display: flex; align-items: center; gap: 12px; padding: 12px; border-radius: 8px; cursor: pointer; color: #888; transition: all 0.2s; margin-bottom: 4px; }
    .nav-item:hover, .nav-item.active { background: #2a2a4a; color: #fff; }
    .nav-section { font-size: 11px; text-transform: uppercase; color: #666; margin: 16px 0 8px 12px; letter-spacing: 1px; }
    .stats { margin-top: auto; padding: 16px; background: #2a2a4a; border-radius: 12px; }
    .stat-item { display: flex; justify-content: space-between; margin-bottom: 8px; color: #aaa; font-size: 13px; }
    .stat-value { color: #667eea; font-weight: 600; }
    .panel { display: none; padding: 20px; overflow-y: auto; flex: 1; }
    .panel.active { display: block; }
    .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .panel-header h2 { font-size: 20px; }
    .panel-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
    .card { background: #2a2a4a; border-radius: 12px; padding: 16px; }
    .card-title { font-weight: 600; margin-bottom: 8px; }
    .card-meta { font-size: 12px; color: #888; }
    .card-content { font-size: 14px; color: #ccc; margin-top: 8px; }
    .empty-state { text-align: center; padding: 40px; color: #666; }
    .quick-btn { padding: 8px 16px; background: #667eea; border: none; border-radius: 8px; color: #fff; font-size: 14px; cursor: pointer; }
    .quick-btn:hover { background: #764ba2; }
  </style>
</head>
<body>
  <div class=\"container\">
    <div class=\"sidebar\">
      <h2 style=\"margin-bottom: 20px;\">My AI Assistant</h2>
      <div class=\"nav-item active\" data-panel=\"chat\" onclick=\"showPanel(this)\"><span>💬</span> Chat</div>
      <div class=\"nav-section\">Productivity</div>
      <div class=\"nav-item\" data-panel=\"tasks\" onclick=\"showPanel(this)\"><span>✅</span> Tasks</div>
      <div class=\"nav-item\" data-panel=\"calendar\" onclick=\"showPanel(this)\"><span>📅</span> Calendar</div>
      <div class=\"nav-item\" data-panel=\"notes\" onclick=\"showPanel(this)\"><span>📝</span> Notes</div>
      <div class=\"nav-item\" data-panel=\"reminders\" onclick=\"showPanel(this)\"><span>⏰</span> Reminders</div>
      <div class=\"nav-section\">Communication</div>
      <div class=\"nav-item\" data-panel=\"emails\" onclick=\"showPanel(this)\"><span>📧</span> Email</div>
      <div class=\"nav-item\" data-panel=\"contacts\" onclick=\"showPanel(this)\"><span>👥</span> Contacts</div>
      <div class=\"nav-item\" data-panel=\"files\" onclick=\"showPanel(this)\"><span>📁</span> Files</div>
      <div class=\"nav-section\">Life</div>
      <div class=\"nav-item\" data-panel=\"finances\" onclick=\"showPanel(this)\"><span>💰</span> Finances</div>
      <div class=\"nav-item\" data-panel=\"travel\" onclick=\"showPanel(this)\"><span>✈️</span> Travel</div>
      <div class=\"nav-item\" data-panel=\"health\" onclick=\"showPanel(this)\"><span>🏥</span> Health</div>
      <div class=\"nav-section\">Knowledge</div>
      <div class=\"nav-item\" data-panel=\"research\" onclick=\"showPanel(this)\"><span>🔍</span> Research</div>
      <div class=\"nav-item\" data-panel=\"memory\" onclick=\"showPanel(this)\"><span>🧠</span> Memory</div>
      <div class=\"stats\">
        <div class=\"stat-item\"><span>Tasks</span><span class=\"stat-value\" id=\"s-tasks\">0</span></div>
        <div class=\"stat-item\"><span>Meetings</span><span class=\"stat-value\" id=\"s-meetings\">0</span></div>
        <div class=\"stat-item\"><span>Emails</span><span class=\"stat-value\" id=\"s-emails\">0</span></div>
        <div class=\"stat-item\"><span>Notes</span><span class=\"stat-value\" id=\"s-notes\">0</span></div>
      </div>
    </div>
    <div class=\"main\">
      <div class=\"header\"><h1>🤖 Personal AI Assistant</h1><p style=\"color:#888;margin-top:4px;\">Full-service AI secretary</p></div>
      <div id=\"chatPanel\" class=\"panel active\">
        <div class=\"chat-area\" id=\"chatArea\">
          <div class=\"message agent\">Hello! I am your personal AI assistant. I help with: email, calendar, tasks, notes, reminders, contacts, finances, travel, health, and research. What can I do for you?</div>
        </div>
        <div class=\"input-area\"><input type=\"text\" id=\"msgInput\" placeholder=\"Ask me anything...\" onkeypress=\"handleKey(event)\"></div>
      </div>
      <div id=\"tasksPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Tasks</h2></div><div class=\"panel-grid\" id=\"tasksList\"><div class=\"empty-state\">No tasks yet</div></div></div>
      <div id=\"calendarPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Calendar</h2></div><div class=\"panel-grid\" id=\"calendarList\"><div class=\"empty-state\">No events</div></div></div>
      <div id=\"notesPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Notes</h2></div><div class=\"panel-grid\" id=\"notesList\"><div class=\"empty-state\">No notes</div></div></div>
      <div id=\"remindersPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Reminders</h2></div><div class=\"panel-grid\" id=\"remindersList\"><div class=\"empty-state\">No reminders</div></div></div>
      <div id=\"emailsPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Email</h2></div><div class=\"panel-grid\" id=\"emailsList\"><div class=\"empty-state\">No emails</div></div></div>
      <div id=\"contactsPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Contacts</h2></div><div class=\"panel-grid\" id=\"contactsList\"><div class=\"empty-state\">No contacts</div></div></div>
      <div id=\"filesPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Files</h2></div><div class=\"panel-grid\" id=\"filesList\"><div class=\"empty-state\">No files</div></div></div>
      <div id=\"financesPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Finances</h2></div><div class=\"panel-grid\" id=\"financesList\"><div class=\"empty-state\">No accounts</div></div></div>
      <div id=\"travelPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Travel</h2></div><div class=\"panel-grid\" id=\"travelList\"><div class=\"empty-state\">No travel plans</div></div></div>
      <div id=\"healthPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Health</h2></div><div class=\"panel-grid\" id=\"healthList\"><div class=\"empty-state\">No health data</div></div></div>
      <div id=\"researchPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Research</h2></div><div class=\"panel-grid\" id=\"researchList\"><div class=\"empty-state\">No research</div></div></div>
      <div id=\"memoryPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Memory</h2></div><div class=\"panel-grid\" id=\"memoryList\"><div class=\"empty-state\">Memories appear here</div></div></div>
    </div>
  </div>
  <script>
    const uid = 'u' + Math.random().toString(36).substr(2, 9);
    let curPanel = 'chat';
    
    async function sendMsg(msg) {
      const area = document.getElementById('chatArea');
      area.innerHTML += '<div class=\"message user\">' + msg + '</div>';
      try {
        const r = await fetch('/api/personal-agent/chat', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({userId: uid, userName: 'User', message: msg}) });
        const d = await r.json();
        area.innerHTML += '<div class=\"message agent\">' + d.response + '</div>';
        area.scrollTop = area.scrollHeight;
        loadStats();
        if (curPanel !== 'chat') loadPanel(curPanel);
      } catch(e) { console.error(e); }
    }
    
    function handleKey(e) { if (e.key === 'Enter') { const v = document.getElementById('msgInput').value.trim(); if (v) { sendMsg(v); document.getElementById('msgInput').value = ''; } } }
    
    function showPanel(el) {
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      el.classList.add('active');
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      document.getElementById(el.dataset.panel + 'Panel').classList.add('active');
      curPanel = el.dataset.panel;
      loadPanel(curPanel);
    }
    
    async function loadStats() {
      try {
        const d = await fetch('/api/personal-agent/context/' + uid).then(r => r.json());
        document.getElementById('s-tasks').textContent = d.stats.pendingTasks;
        document.getElementById('s-meetings').textContent = d.stats.todayMeetings;
        document.getElementById('s-emails').textContent = d.stats.unreadEmails;
        document.getElementById('s-notes').textContent = d.stats.totalNotes;
      } catch(e) {}
    }
    
    async function loadPanel(p) {
      const apis = {tasks:'/api/personal-agent/tasks/',calendar:'/api/personal-agent/calendar/',notes:'/api/personal-agent/notes/',reminders:'/api/personal-agent/reminders/',emails:'/api/personal-agent/emails/',contacts:'/api/personal-agent/contacts/',files:'/api/personal-agent/files/',finances:'/api/personal-agent/finances/',travel:'/api/personal-agent/travel/',health:'/api/personal-agent/health/',research:'/api/personal-agent/research/',memory:'/api/personal-agent/recall/'};
      const ids = {tasks:'tasksList',calendar:'calendarList',notes:'notesList',reminders:'remindersList',emails:'emailsList',contacts:'contactsList',files:'filesList',finances:'financesList',travel:'travelList',health:'healthList',research:'researchList',memory:'memoryList'};
      try {
        const d = await fetch(apis[p] + uid).then(r => r.json());
        const list = document.getElementById(ids[p]);
        if (!d.total || d.total === 0) { list.innerHTML = '<div class=\"empty-state\">No data</div>'; return; }
        let html = '';
        const items = d.tasks || d.events || d.notes || d.reminders || d.emails || d.contacts || d.files || d.accounts || d.plans || d.metrics || d.items || d.memories || [];
        items.forEach(item => {
          const title = item.title || item.subject || item.topic || item.name || item.firstName ? (item.title || item.subject || item.topic || item.name || (item.firstName + ' ' + item.lastName)) : 'Item';
          const meta = item.status || item.priority || (item.startTime ? new Date(item.startTime).toLocaleDateString() : '') || '';
          html += '<div class=\"card\"><div class=\"card-title\">' + title + '</div><div class=\"card-meta\">' + meta + '</div></div>';
        });
        list.innerHTML = html || '<div class=\"empty-state\">No data</div>';
      } catch(e) { console.error(e); }
    }
    
    loadStats();
  </script>
</body>
</html>`
}

export default router