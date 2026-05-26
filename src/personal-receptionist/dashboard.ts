/**
 * ============================================================
 * PERSONAL AI RECEPTIONIST - Web Dashboard & REST API
 * ============================================================
 */

import express, { Request, Response } from 'express'
import { v4 as uuid } from 'uuid'
import { getPersonalReceptionist, PersonalReceptionistAgent } from './PersonalReceptionistAgent'
import { IndustryType } from './types'

const router = express.Router()
const userSessions: Map<string, { agent: PersonalReceptionistAgent; lastActive: Date }> = new Map()

function getOrCreateAgent(userId: string, userName: string, industry?: IndustryType): PersonalReceptionistAgent {
  if (!userSessions.has(userId)) {
    const agent = getPersonalReceptionist(userId, userName, 'pro', industry || 'personal')
    userSessions.set(userId, { agent, lastActive: new Date() })
  }
  userSessions.get(userId)!.lastActive = new Date()
  return userSessions.get(userId)!.agent
}

// ============================================================================
// CHAT (Personal Assistant Mode)
// ============================================================================

router.post('/chat', (req: Request, res: Response) => {
  const { userId, userName, message, industry } = req.body
  if (!userId || !message) return res.status(400).json({ error: 'userId and message required' })

  getOrCreateAgent(userId, userName || 'User', industry).processMessage(message)
    .then(response => res.json({
      response: response.content,
      confidence: response.confidence,
      actions: response.actions,
      suggestedActions: response.suggestedActions,
      quickReplies: response.quickReplies,
      timestamp: new Date().toISOString()
    }))
    .catch(error => res.status(500).json({ error: error.message }))
})

router.get('/history/:userId', (req: Request, res: Response) => {
  res.json({ messages: getOrCreateAgent(req.params.userId, 'User').getConversationHistory() })
})

// ============================================================================
// VISITOR CHAT (Receptionist Mode)
// ============================================================================

router.post('/visitor/chat', (req: Request, res: Response) => {
  const { message, visitorId, industry } = req.body
  if (!message) return res.status(400).json({ error: 'Message required' })

  const agent = getOrCreateAgent('receptionist', 'Front Desk', industry || 'corporate')
  agent.processVisitorInput(message, visitorId)
    .then(response => res.json({
      response: response.content,
      agent: response.agent,
      actions: response.actions,
      requiresHumanEscalation: response.requiresEscalation,
      quickReplies: response.quickReplies,
      timestamp: new Date().toISOString()
    }))
    .catch(error => res.status(500).json({ error: error.message }))
})

// ============================================================================
// CONTEXT & STATS
// ============================================================================

router.get('/context/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const now = new Date()
  res.json({
    userId: ctx.userId,
    name: ctx.name,
    email: ctx.email,
    timezone: ctx.timezone,
    industry: ctx.industry,
    preferences: ctx.preferences,
    stats: {
      // Personal stats
      pendingTasks: ctx.tasks.filter(t => t.status === 'pending').length,
      todayMeetings: ctx.calendar.filter(e => new Date(e.startTime).toDateString() === now.toDateString() && e.status !== 'cancelled').length,
      totalNotes: ctx.notes.length,
      activeReminders: ctx.reminders.filter(r => r.status === 'active').length,
      memoriesStored: ctx.memory.length,
      totalEmails: ctx.emails.length,
      unreadEmails: ctx.emails.filter(e => !e.isRead).length,
      totalContacts: ctx.contacts.length,
      totalTravelPlans: ctx.travel.length,
      healthEntries: ctx.health.length,
      // Receptionist stats
      waitingVisitors: ctx.visitors.filter(v => v.status === 'waiting' || v.status === 'checked_in').length,
      todayAppointments: ctx.appointments.filter(a => new Date(a.dateTime).toDateString() === now.toDateString()).length,
      openEscalations: ctx.escalations.filter(e => e.status === 'open').length
    },
    agentStats: ctx.agentStats,
    queueStats: ctx.queueStats
  })
})

// ============================================================================
// PERSONAL: TASKS
// ============================================================================

router.get('/tasks/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  let tasks = ctx.tasks
  if (req.query.status) tasks = tasks.filter(t => t.status === req.query.status)
  res.json({ tasks, total: tasks.length })
})

router.post('/tasks/:userId', (req: Request, res: Response) => {
  const { title, description, dueDate, priority } = req.body
  if (!title) return res.status(400).json({ error: 'Title required' })
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const task = {
    id: uuid(),
    title,
    description: description || '',
    dueDate: dueDate ? new Date(dueDate) : undefined,
    priority: priority || 'medium',
    status: 'pending' as const,
    createdAt: new Date(),
    tags: [],
    subtasks: [],
    attachments: []
  }
  ctx.tasks.push(task)
  res.json({ task, message: `Task created: ${title}` })
})

router.put('/tasks/:userId/:taskId/complete', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const task = ctx.tasks.find(t => t.id === req.params.taskId)
  if (!task) return res.status(404).json({ error: 'Task not found' })
  task.status = 'completed'
  task.completedAt = new Date()
  res.json({ taskId: task.id, status: 'completed' })
})

router.delete('/tasks/:userId/:taskId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const idx = ctx.tasks.findIndex(t => t.id === req.params.taskId)
  if (idx === -1) return res.status(404).json({ error: 'Task not found' })
  ctx.tasks.splice(idx, 1)
  res.json({ deleted: true })
})

// ============================================================================
// PERSONAL: CALENDAR
// ============================================================================

router.get('/calendar/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  res.json({ events: ctx.calendar, total: ctx.calendar.length })
})

router.post('/calendar/:userId', (req: Request, res: Response) => {
  const { title, startTime, endTime, location, attendees } = req.body
  if (!title || !startTime) return res.status(400).json({ error: 'Title and startTime required' })
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const event = {
    id: uuid(),
    title,
    description: '',
    startTime: new Date(startTime),
    endTime: endTime ? new Date(endTime) : new Date(new Date(startTime).getTime() + 3600000),
    location: location || '',
    attendees: attendees || [],
    reminders: [{ minutesBefore: 15, sent: false }],
    status: 'confirmed' as const
  }
  ctx.calendar.push(event)
  res.json({ event, message: `Event created: ${title}` })
})

router.delete('/calendar/:userId/:eventId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const idx = ctx.calendar.findIndex(e => e.id === req.params.eventId)
  if (idx === -1) return res.status(404).json({ error: 'Event not found' })
  ctx.calendar.splice(idx, 1)
  res.json({ deleted: true })
})

// ============================================================================
// PERSONAL: NOTES
// ============================================================================

router.get('/notes/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  res.json({ notes: ctx.notes, total: ctx.notes.length })
})

router.post('/notes/:userId', (req: Request, res: Response) => {
  const { title, content, tags } = req.body
  if (!content) return res.status(400).json({ error: 'Content required' })
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const note = {
    id: uuid(),
    title: title || 'Untitled',
    content,
    createdAt: new Date(),
    updatedAt: new Date(),
    tags: tags || [],
    isPinned: false,
    isArchived: false
  }
  ctx.notes.push(note)
  res.json({ note, message: 'Note created' })
})

router.delete('/notes/:userId/:noteId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const idx = ctx.notes.findIndex(n => n.id === req.params.noteId)
  if (idx === -1) return res.status(404).json({ error: 'Note not found' })
  ctx.notes.splice(idx, 1)
  res.json({ deleted: true })
})

// ============================================================================
// PERSONAL: REMINDERS
// ============================================================================

router.get('/reminders/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  res.json({ reminders: ctx.reminders.filter(r => r.status === 'active'), total: ctx.reminders.length })
})

router.post('/reminders/:userId', (req: Request, res: Response) => {
  const { title, message, triggerTime, repeat } = req.body
  if (!title || !triggerTime) return res.status(400).json({ error: 'Title and triggerTime required' })
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const reminder = { id: uuid(), title, message: message || '', triggerTime: new Date(triggerTime), status: 'active' as const, repeat }
  ctx.reminders.push(reminder)
  res.json({ reminder, message: `Reminder set: ${title}` })
})

router.delete('/reminders/:userId/:reminderId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const idx = ctx.reminders.findIndex(r => r.id === req.params.reminderId)
  if (idx === -1) return res.status(404).json({ error: 'Reminder not found' })
  ctx.reminders.splice(idx, 1)
  res.json({ deleted: true })
})

// ============================================================================
// PERSONAL: EMAILS
// ============================================================================

router.get('/emails/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  res.json({ emails: ctx.emails, total: ctx.emails.length })
})

router.post('/emails/:userId', (req: Request, res: Response) => {
  const { to, subject, body } = req.body
  if (!to || !subject || !body) return res.status(400).json({ error: 'to, subject, body required' })
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const email = {
    id: uuid(),
    from: { email: ctx.email || 'assistant@personal.ai', name: ctx.name },
    to: Array.isArray(to) ? to : [{ email: to }],
    subject,
    body,
    timestamp: new Date(),
    isRead: true,
    isStarred: false,
    isArchived: false,
    labels: [],
    attachments: [],
    priority: 'normal' as const
  }
  ctx.emails.push(email)
  res.json({ email, message: 'Email drafted' })
})

// ============================================================================
// PERSONAL: CONTACTS
// ============================================================================

router.get('/contacts/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  res.json({ contacts: ctx.contacts, total: ctx.contacts.length })
})

router.post('/contacts/:userId', (req: Request, res: Response) => {
  const { firstName, lastName, company, emails } = req.body
  if (!firstName || !lastName) return res.status(400).json({ error: 'firstName and lastName required' })
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const contact = { id: uuid(), firstName, lastName, company, emails: emails || [], phones: [], addresses: [], tags: [], relationship: 'other' as const, socialProfiles: [] }
  ctx.contacts.push(contact)
  res.json({ contact, message: `Contact added: ${firstName} ${lastName}` })
})

// ============================================================================
// PERSONAL: FILES
// ============================================================================

router.get('/files/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  res.json({ files: ctx.files, total: ctx.files.length })
})

router.post('/files/:userId', (req: Request, res: Response) => {
  const { filename, mimeType, size } = req.body
  if (!filename) return res.status(400).json({ error: 'filename required' })
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const file = { id: uuid(), filename, mimeType: mimeType || 'application/octet-stream', size: size || 0, uploadedAt: new Date(), tags: [], folder: 'root' }
  ctx.files.push(file)
  res.json({ file, message: 'File added' })
})

// ============================================================================
// PERSONAL: FINANCES
// ============================================================================

router.get('/finances/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const total = ctx.finances.reduce((s: number, a: any) => s + a.balance, 0)
  res.json({ accounts: ctx.finances, totalBalance: total, total: ctx.finances.length })
})

router.post('/finances/:userId/accounts', (req: Request, res: Response) => {
  const { name, type, balance, institution } = req.body
  if (!name || !type) return res.status(400).json({ error: 'name and type required' })
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const account = { id: uuid(), name, type, institution: institution || '', balance: balance || 0, currency: 'USD', lastSynced: new Date() }
  ctx.finances.push(account)
  res.json({ account, message: `Account added: ${name}` })
})

// ============================================================================
// PERSONAL: TRAVEL
// ============================================================================

router.get('/travel/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  res.json({ plans: ctx.travel, total: ctx.travel.length })
})

router.post('/travel/:userId', (req: Request, res: Response) => {
  const { type, startDate, endDate } = req.body
  if (!type || !startDate) return res.status(400).json({ error: 'type and startDate required' })
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const plan = { id: uuid(), type, status: 'planned' as const, startDate: new Date(startDate), endDate: endDate ? new Date(endDate) : new Date(startDate), details: {} as any }
  ctx.travel.push(plan)
  res.json({ plan, message: `Travel plan added: ${type}` })
})

// ============================================================================
// PERSONAL: HEALTH
// ============================================================================

router.get('/health/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  res.json({ metrics: ctx.health, total: ctx.health.length })
})

router.post('/health/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const metrics = { id: uuid(), date: new Date(), weight: req.body.weight, heartRate: req.body.heartRate, sleepHours: req.body.sleepHours, mood: req.body.mood }
  ctx.health.push(metrics)
  res.json({ metrics, message: 'Health metrics logged' })
})

// ============================================================================
// PERSONAL: RESEARCH
// ============================================================================

router.get('/research/:userId', (req: Request, res: Response) => {
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  res.json({ items: ctx.research, total: ctx.research.length })
})

router.post('/research/:userId', (req: Request, res: Response) => {
  const { topic, summary, sourceUrl } = req.body
  if (!topic) return res.status(400).json({ error: 'topic required' })
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const item = { id: uuid(), topic, summary: summary || '', sourceUrl, keyPoints: [], createdAt: new Date(), updatedAt: new Date(), tags: [] }
  ctx.research.push(item)
  res.json({ item, message: `Research saved: ${topic}` })
})

// ============================================================================
// PERSONAL: MEMORY
// ============================================================================

router.post('/remember/:userId', (req: Request, res: Response) => {
  const { content, type, importance } = req.body
  if (!content) return res.status(400).json({ error: 'Content required' })
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  ctx.memory.push({ id: uuid(), timestamp: new Date(), type: type || 'fact', content, importance: importance || 'medium', tags: [] })
  res.json({ message: 'Memory stored' })
})

router.get('/recall/:userId', (req: Request, res: Response) => {
  const q = (req.query.q as string) || ''
  const ctx = getOrCreateAgent(req.params.userId, 'User').getContext()
  const memories = ctx.memory.filter(m => m.content.toLowerCase().includes(q.toLowerCase())).slice(-20)
  res.json({ memories, total: memories.length })
})

// ============================================================================
// RECEPTIONIST: VISITORS
// ============================================================================

router.get('/visitors', (_req: Request, res: Response) => {
  const agent = getOrCreateAgent('receptionist', 'Front Desk')
  res.json({
    waiting: agent.getWaitingVisitors(),
    total: agent.getContext().visitors.length
  })
})

router.post('/visitors/checkin', (req: Request, res: Response) => {
  const { name, purpose, email, phone, hostName } = req.body
  if (!name || !purpose) return res.status(400).json({ error: 'name and purpose required' })

  const agent = getOrCreateAgent('receptionist', 'Front Desk')
  const visitor = agent.checkInVisitor(name, purpose, email, hostName)
  res.json({ visitor, message: `${name} checked in for ${purpose}` })
})

router.put('/visitors/:visitorId/status', (req: Request, res: Response) => {
  const { status } = req.body
  const agent = getOrCreateAgent('receptionist', 'Front Desk')
  const visitor = agent.getContext().visitors.find(v => v.id === req.params.visitorId)
  if (!visitor) return res.status(404).json({ error: 'Visitor not found' })

  visitor.status = status as any
  res.json({ visitor, updated: true })
})

// ============================================================================
// RECEPTIONIST: APPOINTMENTS
// ============================================================================

router.get('/appointments', (_req: Request, res: Response) => {
  const agent = getOrCreateAgent('receptionist', 'Front Desk')
  res.json({
    today: agent.getTodayAppointments(),
    total: agent.getContext().appointments.length
  })
})

router.post('/appointments', (req: Request, res: Response) => {
  const { clientName, service, dateTime, duration } = req.body
  if (!clientName || !service) return res.status(400).json({ error: 'clientName and service required' })

  const agent = getOrCreateAgent('receptionist', 'Front Desk')
  const appointment = {
    id: `APT-${Date.now()}`,
    clientName,
    service,
    dateTime: dateTime ? new Date(dateTime) : new Date(),
    duration: duration || 30,
    status: 'scheduled' as const,
    industry: 'corporate' as IndustryType
  }
  agent.getContext().appointments.push(appointment)

  res.json({ message: `Appointment booked for ${clientName}`, appointment })
})

// ============================================================================
// RECEPTIONIST: ESCALATIONS
// ============================================================================

router.get('/escalations', (_req: Request, res: Response) => {
  const agent = getOrCreateAgent('receptionist', 'Front Desk')
  res.json({
    open: agent.getOpenEscalations(),
    total: agent.getContext().escalations.length
  })
})

router.post('/escalations', (req: Request, res: Response) => {
  const { reason, visitorId, priority } = req.body
  if (!reason) return res.status(400).json({ error: 'reason required' })

  const ctx = getOrCreateAgent('receptionist', 'Front Desk').getContext()
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
  const ctx = getOrCreateAgent('receptionist', 'Front Desk').getContext()
  const ticket = ctx.escalations.find(t => t.id === req.params.ticketId)
  if (!ticket) return res.status(404).json({ error: 'Ticket not found' })

  ticket.status = 'resolved'
  ticket.resolvedAt = new Date()
  ticket.resolution = resolution

  res.json({ ticket, message: 'Ticket resolved' })
})

// ============================================================================
// RECEPTIONIST: STATS
// ============================================================================

router.get('/stats', (_req: Request, res: Response) => {
  const ctx = getOrCreateAgent('receptionist', 'Front Desk').getContext()
  res.json({ agentStats: ctx.agentStats, queueStats: ctx.queueStats })
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

export function setupPersonalReceptionistDashboard(app: express.Application): void {
  app.use('/api/personal-receptionist', router)

  app.get('/personal-receptionist', (_req: Request, res: Response) => {
    res.send(getDashboardHTML())
  })

  console.log('\n  Personal AI Receptionist ready at:')
  console.log('  - Dashboard: http://localhost:3000/personal-receptionist')
  console.log('  - API Base: /api/personal-receptionist')
}

function getDashboardHTML(): string {
  return `<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>Personal AI Receptionist</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a1a; color: #fff; height: 100vh; overflow: hidden; }
    .container { display: flex; height: 100vh; }
    .sidebar { width: 300px; background: #12122a; padding: 20px; border-right: 1px solid #2a2a4a; display: flex; flex-direction: column; overflow-y: auto; }
    .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
    .header { padding: 20px; background: linear-gradient(135deg, #667eea, #764ba2); border-bottom: 1px solid #2a2a4a; }
    .header h1 { font-size: 24px; }
    .header p { color: rgba(255,255,255,0.8); margin-top: 4px; font-size: 14px; }
    .chat-area { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; }
    .input-area { padding: 20px; background: #12122a; border-top: 1px solid #2a2a4a; }
    .input-area input { width: 100%; padding: 16px; border-radius: 12px; border: 1px solid #3a3a5a; background: #0a0a1a; color: #fff; font-size: 16px; outline: none; }
    .input-area input:focus { border-color: #667eea; }
    .message { max-width: 75%; padding: 12px 16px; border-radius: 16px; line-height: 1.5; white-space: pre-wrap; }
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
    .quick-replies { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    .quick-reply { padding: 6px 12px; background: #3a3a5a; border: none; border-radius: 16px; color: #aaa; font-size: 12px; cursor: pointer; }
    .quick-reply:hover { background: #4a4a6a; color: #fff; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
    .badge.waiting { background: #ffaa00; color: #000; }
    .badge.scheduled { background: #00d4aa; color: #000; }
    .badge.pending { background: #667eea; color: #fff; }
    .badge.completed { background: #00ff88; color: #000; }
    .mode-toggle { display: flex; gap: 8px; margin-bottom: 16px; }
    .mode-btn { flex: 1; padding: 12px; border: none; border-radius: 8px; font-size: 13px; cursor: pointer; background: #2a2a4a; color: #888; }
    .mode-btn.active { background: #667eea; color: #fff; }
    .agent-status { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
    .agent-chip { padding: 4px 10px; background: #1a1a3a; border-radius: 12px; font-size: 11px; color: #00d4aa; }
  </style>
</head>
<body>
  <div class=\"container\">
    <div class=\"sidebar\">
      <h2 style=\"margin-bottom: 16px;\">🤖 AI Receptionist</h2>
      
      <div class=\"mode-toggle\">
        <button class=\"mode-btn active\" id=\"assistantMode\" onclick=\"setMode('assistant')\">Personal</button>
        <button class=\"mode-btn\" id=\"receptionistMode\" onclick=\"setMode('receptionist')\">Receptionist</button>
      </div>
      
      <div class=\"nav-item active\" data-panel=\"chat\" onclick=\"showPanel(this)\"><span>💬</span> Chat</div>
      
      <div id=\"assistantNav\">
        <div class=\"nav-section\">Productivity</div>
        <div class=\"nav-item\" data-panel=\"tasks\" onclick=\"showPanel(this)\"><span>✅</span> Tasks</div>
        <div class=\"nav-item\" data-panel=\"calendar\" onclick=\"showPanel(this)\"><span>📅</span> Calendar</div>
        <div class=\"nav-item\" data-panel=\"notes\" onclick=\"showPanel(this)\"><span>📝</span> Notes</div>
        <div class=\"nav-item\" data-panel=\"reminders\" onclick=\"showPanel(this)\"><span>⏰</span> Reminders</div>
        <div class=\"nav-section\">Communication</div>
        <div class=\"nav-item\" data-panel=\"emails\" onclick=\"showPanel(this)\"><span>📧</span> Email</div>
        <div class=\"nav-item\" data-panel=\"contacts\" onclick=\"showPanel(this)\"><span>👥</span> Contacts</div>
        <div class=\"nav-section\">Life</div>
        <div class=\"nav-item\" data-panel=\"finances\" onclick=\"showPanel(this)\"><span>💰</span> Finances</div>
        <div class=\"nav-item\" data-panel=\"travel\" onclick=\"showPanel(this)\"><span>✈️</span> Travel</div>
        <div class=\"nav-item\" data-panel=\"health\" onclick=\"showPanel(this)\"><span>🏥</span> Health</div>
      </div>
      
      <div id=\"receptionistNav\" style=\"display:none;\">
        <div class=\"nav-section\">Reception</div>
        <div class=\"nav-item\" data-panel=\"visitors\" onclick=\"showPanel(this)\"><span>👥</span> Visitors</div>
        <div class=\"nav-item\" data-panel=\"appointments\" onclick=\"showPanel(this)\"><span>📋</span> Appointments</div>
        <div class=\"nav-item\" data-panel=\"escalations\" onclick=\"showPanel(this)\"><span>🎫</span> Escalations</div>
      </div>
      
      <div class=\"stats\">
        <div class=\"stat-item\"><span>Tasks</span><span class=\"stat-value\" id=\"s-tasks\">0</span></div>
        <div class=\"stat-item\"><span>Meetings</span><span class=\"stat-value\" id=\"s-meetings\">0</span></div>
        <div class=\"stat-item\"><span>Visitors</span><span class=\"stat-value\" id=\"s-visitors\">0</span></div>
        <div class=\"stat-item\"><span>Emails</span><span class=\"stat-value\" id=\"s-emails\">0</span></div>
        <div class=\"agent-status\">
          <span class=\"agent-chip\">ARIA</span>
          <span class=\"agent-chip\">CHRONOS</span>
          <span class=\"agent-chip\">WIKI</span>
          <span class=\"agent-chip\">CONNECT</span>
        </div>
      </div>
    </div>
    
    <div class=\"main\">
      <div class=\"header\">
        <h1 id=\"headerTitle\">🤖 Personal AI Assistant</h1>
        <p id=\"headerSub\">Your unified assistant + receptionist</p>
      </div>
      
      <div id=\"chatPanel\" class=\"panel active\">
        <div class=\"chat-area\" id=\"chatArea\">
          <div class=\"message agent\">Hello! I'm your unified Personal AI Assistant and Receptionist. I can help you with scheduling, tasks, emails, visitor check-ins, and more. What can I do for you today?</div>
        </div>
        <div class=\"input-area\">
          <input type=\"text\" id=\"msgInput\" placeholder=\"Ask me anything...\" onkeypress=\"handleKey(event)\">
        </div>
        <div class=\"quick-replies\" id=\"quickReplies\">
          <button class=\"quick-reply\" onclick=\"quickReply('What do I have today?')\">What's my schedule?</button>
          <button class=\"quick-reply\" onclick=\"quickReply('Create a new task')\">New Task</button>
          <button class=\"quick-reply\" onclick=\"quickReply('Check in a visitor')\">Check In Visitor</button>
          <button class=\"quick-reply\" onclick=\"quickReply('Schedule appointment')\">Book Appointment</button>
        </div>
      </div>
      
      <div id=\"tasksPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Tasks</h2></div><div class=\"panel-grid\" id=\"tasksList\"><div class=\"empty-state\">No tasks yet</div></div></div>
      <div id=\"calendarPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Calendar</h2></div><div class=\"panel-grid\" id=\"calendarList\"><div class=\"empty-state\">No events</div></div></div>
      <div id=\"notesPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Notes</h2></div><div class=\"panel-grid\" id=\"notesList\"><div class=\"empty-state\">No notes</div></div></div>
      <div id=\"remindersPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Reminders</h2></div><div class=\"panel-grid\" id=\"remindersList\"><div class=\"empty-state\">No reminders</div></div></div>
      <div id=\"emailsPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Email</h2></div><div class=\"panel-grid\" id=\"emailsList\"><div class=\"empty-state\">No emails</div></div></div>
      <div id=\"contactsPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Contacts</h2></div><div class=\"panel-grid\" id=\"contactsList\"><div class=\"empty-state\">No contacts</div></div></div>
      <div id=\"financesPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Finances</h2></div><div class=\"panel-grid\" id=\"financesList\"><div class=\"empty-state\">No accounts</div></div></div>
      <div id=\"travelPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Travel</h2></div><div class=\"panel-grid\" id=\"travelList\"><div class=\"empty-state\">No travel plans</div></div></div>
      <div id=\"healthPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Health</h2></div><div class=\"panel-grid\" id=\"healthList\"><div class=\"empty-state\">No health data</div></div></div>
      <div id=\"visitorsPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Visitor Queue</h2></div><div class=\"panel-grid\" id=\"visitorsList\"><div class=\"empty-state\">No visitors</div></div></div>
      <div id=\"appointmentsPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Appointments</h2></div><div class=\"panel-grid\" id=\"appointmentsList\"><div class=\"empty-state\">No appointments</div></div></div>
      <div id=\"escalationsPanel\" class=\"panel\"><div class=\"panel-header\"><h2>Escalations</h2></div><div class=\"panel-grid\" id=\"escalationsList\"><div class=\"empty-state\">No open escalations</div></div></div>
    </div>
  </div>

  <script>
    const uid = 'u' + Math.random().toString(36).substr(2, 9);
    let currentMode = 'assistant';
    let currentPanel = 'chat';
    
    function setMode(mode) {
      currentMode = mode;
      document.getElementById('assistantMode').classList.toggle('active', mode === 'assistant');
      document.getElementById('receptionistMode').classList.toggle('active', mode === 'receptionist');
      document.getElementById('assistantNav').style.display = mode === 'assistant' ? 'block' : 'none';
      document.getElementById('receptionistNav').style.display = mode === 'receptionist' ? 'block' : 'none';
      document.getElementById('headerTitle').textContent = mode === 'assistant' ? '🤖 Personal AI Assistant' : '🤖 AI Receptionist';
      document.getElementById('headerSub').textContent = mode === 'assistant' ? 'Your personal secretary' : 'Visitor management & scheduling';
      showPanel(document.querySelector('.nav-item[data-panel=\"chat\"]'));
    }
    
    async function sendMsg(msg) {
      const area = document.getElementById('chatArea');
      area.innerHTML += '<div class=\"message user\">' + msg + '</div>';
      try {
        const api = currentMode === 'assistant' ? '/api/personal-receptionist/chat' : '/api/personal-receptionist/visitor/chat';
        const body = currentMode === 'assistant' 
          ? { userId: uid, userName: 'User', message: msg }
          : { message: msg };
        const r = await fetch(api, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
        const d = await r.json();
        area.innerHTML += '<div class=\"message agent\">' + d.response + '</div>';
        if (d.quickReplies && d.quickReplies.length > 0) {
          const repliesDiv = document.getElementById('quickReplies');
          repliesDiv.innerHTML = d.quickReplies.map(r => '<button class=\"quick-reply\" onclick=\"quickReply(\\'' + r.replace(/'/g, '\\\u0027') + '\\')\">' + r + '</button>').join('');
        }
        area.scrollTop = area.scrollHeight;
        loadStats();
        if (currentPanel !== 'chat') loadPanel(currentPanel);
      } catch(e) { console.error(e); }
    }
    
    function handleKey(e) { if (e.key === 'Enter') { const v = document.getElementById('msgInput').value.trim(); if (v) { sendMsg(v); document.getElementById('msgInput').value = ''; } } }
    
    function quickReply(msg) {
      document.getElementById('msgInput').value = msg;
      sendMsg(msg);
      document.getElementById('msgInput').value = '';
    }
    
    function showPanel(el) {
      if (!el) return;
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      el.classList.add('active');
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      const panelName = el.dataset.panel;
      const panelEl = document.getElementById(panelName + 'Panel');
      if (panelEl) {
        panelEl.classList.add('active');
        currentPanel = panelName;
        loadPanel(panelName);
      }
    }
    
    async function loadStats() {
      try {
        const d = await fetch('/api/personal-receptionist/context/' + uid).then(r => r.json());
        document.getElementById('s-tasks').textContent = d.stats.pendingTasks;
        document.getElementById('s-meetings').textContent = d.stats.todayMeetings;
        document.getElementById('s-visitors').textContent = d.stats.waitingVisitors;
        document.getElementById('s-emails').textContent = d.stats.unreadEmails;
      } catch(e) {}
    }
    
    async function loadPanel(p) {
      const apis = {
        tasks: '/api/personal-receptionist/tasks/',
        calendar: '/api/personal-receptionist/calendar/',
        notes: '/api/personal-receptionist/notes/',
        reminders: '/api/personal-receptionist/reminders/',
        emails: '/api/personal-receptionist/emails/',
        contacts: '/api/personal-receptionist/contacts/',
        finances: '/api/personal-receptionist/finances/',
        travel: '/api/personal-receptionist/travel/',
        health: '/api/personal-receptionist/health/',
        visitors: '/api/personal-receptionist/visitors',
        appointments: '/api/personal-receptionist/appointments',
        escalations: '/api/personal-receptionist/escalations'
      };
      const ids = {
        tasks: 'tasksList', calendar: 'calendarList', notes: 'notesList', reminders: 'remindersList',
        emails: 'emailsList', contacts: 'contactsList', finances: 'financesList', travel: 'travelList',
        health: 'healthList', visitors: 'visitorsList', appointments: 'appointmentsList', escalations: 'escalationsList'
      };
      try {
        let d, items = [];
        if (p === 'visitors') {
          d = await fetch(apis[p]).then(r => r.json());
          items = d.waiting || [];
        } else if (p === 'appointments') {
          d = await fetch(apis[p]).then(r => r.json());
          items = d.today || [];
        } else if (p === 'escalations') {
          d = await fetch(apis[p]).then(r => r.json());
          items = d.open || [];
        } else {
          d = await fetch(apis[p] + uid).then(r => r.json());
          items = d.tasks || d.events || d.notes || d.reminders || d.emails || d.contacts || d.accounts || d.plans || d.metrics || [];
        }
        const list = document.getElementById(ids[p]);
        if (!items || items.length === 0) { list.innerHTML = '<div class=\"empty-state\">No data</div>'; return; }
        let html = '';
        items.forEach(item => {
          const title = item.title || item.subject || item.topic || item.name || item.clientName || (item.firstName ? item.firstName + ' ' + item.lastName : 'Item'));
          const meta = item.status || item.priority || (item.startTime ? new Date(item.startTime).toLocaleDateString() : '') || (item.dateTime ? new Date(item.dateTime).toLocaleDateString() : '');
          const badge = item.status ? '<span class=\"badge ' + item.status + '\">' + item.status + '</span>' : '';
          html += '<div class=\"card\"><div class=\"card-title\">' + title + '</div><div class=\"card-meta\">' + meta + ' ' + badge + '</div></div>';
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