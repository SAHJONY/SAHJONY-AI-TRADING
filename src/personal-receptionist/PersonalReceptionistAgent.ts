/**
 * ============================================================
 * PERSONAL AI RECEPTIST - Unified Agent
 * ============================================================
 * 
 * Combines Personal AI Agent + AI Receptionist into one assistant:
 * - Personal: Email, Calendar, Tasks, Notes, Files, Finance, Travel, Health
 * - Receptionist: Visitor greeting, Appointment scheduling, Knowledge FAQ, Escalations
 */

import { v4 as uuid } from 'uuid'
import { EventEmitter } from 'events'
import {
  PersonalReceptionistContext,
  UserPreferences,
  Task,
  CalendarEvent,
  Note,
  Reminder,
  Email,
  Contact,
  FinanceAccount,
  TravelPlan,
  HealthMetrics,
  Visitor,
  Appointment,
  EscalationTicket,
  AIAgentResponse,
  ConversationMessage,
  AgentTier,
  IndustryType
} from './types'

export class PersonalReceptionistAgent extends EventEmitter {
  private context: PersonalReceptionistContext
  private conversationHistory: ConversationMessage[] = []
  private reminderInterval: NodeJS.Timeout | null = null

  constructor(userId: string, name: string, tier: AgentTier = 'basic', industry: IndustryType = 'personal') {
    super()
    this.context = this.initializeContext(userId, name, tier, industry)
    this.startReminderScheduler()
    console.log(`Personal AI Receptionist initialized for ${name} (${industry})`)
  }

  private initializeContext(userId: string, name: string, tier: AgentTier, industry: IndustryType): PersonalReceptionistContext {
    return {
      userId,
      name,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      tier,
      preferences: {
        language: 'en',
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        communicationStyle: 'friendly',
        workingHours: { start: '09:00', end: '18:00' },
        notifications: {
          email: true,
          push: true,
          sms: false,
          desktop: true,
          quietHours: { start: '22:00', end: '08:00' }
        }
      },
      memory: [],
      tasks: [],
      calendar: [],
      notes: [],
      reminders: [],
      emails: [],
      files: [],
      contacts: [],
      finances: [],
      travel: [],
      health: [],
      research: [],
      industry,
      visitors: [],
      appointments: [],
      messages: [],
      escalations: [],
      agentStats: {
        messagesProcessed: 0,
        tasksCompleted: 0,
        emailsHandled: 0,
        aria: { callsHandled: 0, avgResponseTime: 0, status: 'idle' },
        chronos: { appointmentsBooked: 0, avgBookingTime: 0, status: 'idle' },
        wiki: { queriesAnswered: 0, accuracy: 0, status: 'idle' },
        connect: { ticketsResolved: 0, avgResolutionTime: 0, status: 'idle' }
      },
      queueStats: {
        waitingCount: 0,
        avgWaitTime: 0,
        totalServedToday: 0,
        peakHour: '10:00 AM',
        satisfactionScore: 95
      }
    }
  }

  private startReminderScheduler(): void {
    this.reminderInterval = setInterval(() => {
      const now = new Date()
      this.context.reminders.forEach((reminder: Reminder) => {
        if (reminder.status === 'active' && new Date(reminder.triggerTime) <= now) {
          this.emit('reminder', { reminderId: reminder.id, title: reminder.title, message: reminder.message })
          if (reminder.repeat) {
            const next = new Date(reminder.triggerTime)
            if (reminder.repeat === 'daily') next.setDate(next.getDate() + 1)
            else if (reminder.repeat === 'weekly') next.setDate(next.getDate() + 7)
            else if (reminder.repeat === 'monthly') next.setMonth(next.getMonth() + 1)
            reminder.triggerTime = next
          } else {
            reminder.status = 'dismissed'
          }
        }
      })
    }, 60000)
  }

  async processMessage(userMessage: string): Promise<AIAgentResponse> {
    this.context.agentStats.messagesProcessed++
    
    this.conversationHistory.push({
      id: uuid(),
      role: 'user',
      content: userMessage,
      timestamp: new Date()
    })

    const response = await this.generateResponse(userMessage)

    this.conversationHistory.push({
      id: uuid(),
      role: 'agent',
      content: response.content,
      timestamp: new Date()
    })

    this.learnFromConversation(userMessage)

    return {
      agentId: `personal-receptionist-${this.context.userId}`,
      content: response.content,
      confidence: 0.9,
      actions: response.actions,
      suggestedActions: response.suggestedActions,
      nextActions: response.nextActions,
      quickReplies: response.quickReplies
    }
  }

  async processVisitorInput(input: string, visitorId?: string): Promise<{
    content: string
    agent: string
    actions: string[]
    requiresEscalation: boolean
    quickReplies?: string[]
  }> {
    const lower = input.toLowerCase()
    
    if (lower.includes('schedule') || lower.includes('appointment') || lower.includes('book')) {
      return this.handleScheduling(input)
    }
    
    if (lower.includes('question') || lower.includes('faq') || lower.includes('where') || lower.includes('hours')) {
      return this.handleKnowledge(input)
    }
    
    if (lower.includes('speak') || lower.includes('human') || lower.includes('real person') || lower.includes('manager')) {
      return this.handleEscalation(input, visitorId)
    }
    
    if (lower.includes('check') || lower.includes('in ') || lower.includes('meeting with')) {
      return this.handleCheckIn(input)
    }
    
    return this.handleGreeting(input)
  }

  private async generateResponse(message: string): Promise<{
    content: string
    actions: string[]
    suggestedActions?: string[]
    nextActions?: string[]
    quickReplies?: string[]
  }> {
    const lower = message.toLowerCase()

    if (lower.includes('visitor') || lower.includes('check in') || lower.includes('guest')) {
      return this.handleVisitorManagement(message, lower)
    }
    
    if (lower.includes('appointment') || lower.includes('schedule') || lower.includes('book')) {
      return this.handleAppointmentBooking(message, lower)
    }

    if (lower.includes('email') || lower.includes('send ')) {
      return this.handleEmail(message, lower)
    }
    if (lower.includes('calendar') || lower.includes('meeting') || lower.includes('schedule')) {
      return this.handleCalendar(message, lower)
    }
    if (lower.includes('task') || lower.includes('todo')) {
      return this.handleTask(message, lower)
    }
    if (lower.includes('note') || lower.includes('remember')) {
      return this.handleNote(message, lower)
    }
    if (lower.includes('remind')) {
      return this.handleReminder(message, lower)
    }
    if (lower.includes('contact') || lower.includes('call')) {
      return this.handleContact(message, lower)
    }
    if (lower.includes('budget') || lower.includes('money') || lower.includes('expense')) {
      return this.handleFinance(message, lower)
    }
    if (lower.includes('travel') || lower.includes('flight') || lower.includes('hotel')) {
      return this.handleTravel(message, lower)
    }
    if (lower.includes('health') || lower.includes('weight') || lower.includes('sleep')) {
      return this.handleHealth(message, lower)
    }
    if (lower.includes('search') || lower.includes('research')) {
      return this.handleResearch(message, lower)
    }
    if (lower.includes('what do i have') || lower.includes('my schedule') || lower.includes('overview')) {
      return this.handleDailyOverview()
    }
    if (lower.includes('remember') && (lower.includes('what') || lower.includes('earlier'))) {
      return this.handleRecall(message, lower)
    }

    return this.handleDefault(message)
  }

  // =========================================================================
  // RECEPTIONIST HANDLERS
  // =========================================================================

  private async handleGreeting(_input: string): Promise<{ content: string; agent: string; actions: string[]; requiresEscalation: boolean; quickReplies?: string[] }> {
    this.context.agentStats.aria.callsHandled++
    const greetings: Record<IndustryType, string> = {
      personal: 'Hello! I am your personal AI assistant and receptionist. How may I help you today?',
      healthcare: 'Welcome to our medical facility. How may I assist you today?',
      legal: 'Welcome to our law office. How may I assist you with your legal matters?',
      realestate: 'Welcome to our real estate office. How may I help you find your dream property?',
      hospitality: 'Welcome to our establishment. How may I enhance your experience today?',
      corporate: 'Welcome to our corporate office. How may I assist you today?',
      retail: 'Welcome! How may I assist you with your shopping experience today?',
      education: 'Welcome to our academic institution. How may I assist you today?',
      government: 'Welcome to our government office. How may I serve you today?'
    }
    
    return {
      content: greetings[this.context.industry] || greetings.personal,
      agent: 'ARIA',
      actions: ['greet_visitor', 'collect_info'],
      requiresEscalation: false,
      quickReplies: ['I need to schedule an appointment', 'I have a question', 'I need to speak to someone', 'Where is your office?']
    }
  }

  private async handleCheckIn(input: string): Promise<{ content: string; agent: string; actions: string[]; requiresEscalation: boolean; quickReplies?: string[] }> {
    const nameMatch = input.match(/i'?m ([A-Za-z]+)/i) || input.match(/my name is ([A-Za-z]+)/i)
    const hostMatch = input.match(/meeting with ([A-Za-z]+)/i) || input.match(/seeing ([A-Za-z]+)/i)
    
    const visitor: Visitor = {
      id: uuid(),
      name: nameMatch ? nameMatch[1] : 'Guest',
      purpose: 'Check-in',
      checkInTime: new Date(),
      status: 'checked_in',
      hostName: hostMatch ? hostMatch[1] : undefined
    }
    this.context.visitors.push(visitor)
    this.context.queueStats.totalServedToday++
    
    const hostMsg = visitor.hostName ? `I'll let ${visitor.hostName} know you've arrived.` : 'Please have a seat and I will assist you.'
    return {
      content: `Welcome, ${visitor.name}! ${hostMsg}`,
      agent: 'ARIA',
      actions: ['check_in_visitor', 'notify_host'],
      requiresEscalation: false,
      quickReplies: ['What is the status of my appointment?', 'How long is the wait?', 'I need to reschedule']
    }
  }

  private async handleScheduling(input: string): Promise<{ content: string; agent: string; actions: string[]; requiresEscalation: boolean; quickReplies?: string[] }> {
    this.context.agentStats.chronos.appointmentsBooked++
    
    const dateMatch = input.match(/\b(\\d+\/\n?\/\n?)\b/) || input.match(/\b(tomorrow|next week)\b/i)
    const serviceMatch = input.match(/(?:consultation|appointment|meeting|checkup|review)/i)
    
    const dateVal = dateMatch && !isNaN(Date.parse(dateMatch[1])) ? new Date(dateMatch[1]) : new Date()
    
    const apt: Appointment = {
      id: `APT-${uuid().substring(0, 8)}`,
      clientName: this.context.name,
      service: serviceMatch ? serviceMatch[0] : 'Consultation',
      dateTime: dateVal,
      duration: 30,
      status: 'scheduled',
      industry: this.context.industry
    }
    this.context.appointments.push(apt)
    
    return {
      content: `I've scheduled your ${apt.service} for ${new Date(apt.dateTime).toLocaleString()}. You'll receive a confirmation shortly. Is there anything else I can help with?`,
      agent: 'CHRONOS',
      actions: ['book_appointment', 'send_confirmation'],
      requiresEscalation: false,
      quickReplies: ['Add attendees', 'Set reminder', 'View all appointments']
    }
  }

  private async handleKnowledge(input: string): Promise<{ content: string; agent: string; actions: string[]; requiresEscalation: boolean; quickReplies?: string[] }> {
    this.context.agentStats.wiki.queriesAnswered++
    
    const kb = this.getKnowledgeBase()
    const entry = kb.find(e => e.keywords.some(k => input.toLowerCase().includes(k)))
    
    return {
      content: entry?.answer || 'I can help answer your question. Could you provide more details?',
      agent: 'WIKI',
      actions: ['faq_lookup', 'provide_information'],
      requiresEscalation: false,
      quickReplies: ['What are your hours?', 'Where are you located?', 'Can I schedule online?']
    }
  }

  private async handleEscalation(input: string, visitorId?: string): Promise<{ content: string; agent: string; actions: string[]; requiresEscalation: boolean; quickReplies?: string[] }> {
    this.context.agentStats.connect.ticketsResolved++
    
    const ticket: EscalationTicket = {
      id: `ESC-${uuid().substring(0, 8)}`,
      visitorId,
      reason: input.substring(0, 200),
      priority: 'high',
      status: 'open',
      createdAt: new Date()
    }
    this.context.escalations.push(ticket)
    
    return {
      content: `I've connected you with our team. A representative will be with you shortly. Your ticket reference is ${ticket.id}.`,
      agent: 'CONNECT',
      actions: ['create_ticket', 'notify_agent'],
      requiresEscalation: true,
      quickReplies: ['What is my ticket status?', 'I need to update my request']
    }
  }

  private async handleVisitorManagement(message: string, lower: string): Promise<{ content: string; agent: string; actions: string[]; suggestedActions?: string[]; nextActions?: string[]; quickReplies?: string[] }> {
    if (lower.includes('add') || lower.includes('check in') || lower.includes('register')) {
      const visitor: Visitor = {
        id: uuid(),
        name: 'New Visitor',
        purpose: 'General inquiry',
        checkInTime: new Date(),
        status: 'checked_in'
      }
      this.context.visitors.push(visitor)
      this.context.queueStats.totalServedToday++
      return {
        content: 'Visitor checked in successfully. How else can I assist?',
        agent: 'ARIA',
        actions: ['check_in_visitor'],
        quickReplies: ['Show waiting visitors', 'Schedule appointment', 'Answer common questions']
      }
    }
    
    if (lower.includes('list') || lower.includes('waiting')) {
      const waiting = this.context.visitors.filter(v => v.status === 'waiting' || v.status === 'checked_in')
      return {
        content: waiting.length > 0 
          ? `Current waiting: ${waiting.map(v => v.name).join(', ')}`
          : 'No visitors currently waiting.',
        agent: 'ARIA',
        actions: ['list_visitors'],
        quickReplies: ['Check in new visitor', 'View appointments']
      }
    }
    
    return {
      content: 'I manage visitor check-ins and queues. Would you like to check in a visitor or see who is waiting?',
      agent: 'ARIA',
      actions: ['visitor_management'],
      quickReplies: ['Check in visitor', 'View waiting list']
    }
  }

  private async handleAppointmentBooking(_message: string, _lower: string): Promise<{ content: string; agent: string; actions: string[]; suggestedActions?: string[]; nextActions?: string[]; quickReplies?: string[] }> {
    const apt: Appointment = {
      id: `APT-${uuid().substring(0, 8)}`,
      clientName: this.context.name,
      service: 'Scheduled Meeting',
      dateTime: new Date(Date.now() + 86400000),
      duration: 30,
      status: 'scheduled',
      industry: this.context.industry
    }
    this.context.appointments.push(apt)
    this.context.agentStats.chronos.appointmentsBooked++
    
    return {
      content: `Appointment booked for ${new Date(apt.dateTime).toLocaleString()}. Would you like me to add attendees or set reminders?`,
      agent: 'CHRONOS',
      actions: ['book_appointment'],
      quickReplies: ['Add attendees', 'Set reminder', 'View calendar']
    }
  }

  // =========================================================================
  // PERSONAL ASSISTANT HANDLERS
  // =========================================================================

  private handleEmail(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[]; quickReplies?: string[] } {
    this.context.agentStats.emailsHandled++
    
    if (lower.includes('compose') || lower.includes('send') || lower.includes('new email')) {
      const email: Email = {
        id: uuid(),
        from: { email: this.context.email || 'assistant@personal.ai', name: this.context.name },
        to: [{ email: 'recipient@example.com' }],
        subject: message.substring(0, 50),
        body: message,
        timestamp: new Date(),
        isRead: true,
        isStarred: false,
        isArchived: false,
        labels: [],
        attachments: [],
        priority: 'normal'
      }
      this.context.emails.push(email)
      return {
        content: `I've drafted an email: \"${email.subject}\". Would you like me to send it or make changes?`,
        actions: ['email_draft'],
        quickReplies: ['Send email', 'Add attachment', 'Edit draft']
      }
    }

    if (lower.includes('inbox') || lower.includes('unread')) {
      const unread = this.context.emails.filter(e => !e.isRead).length
      return {
        content: `You have ${unread} unread email${unread !== 1 ? 's' : ''}.`,
        actions: ['email_check'],
        quickReplies: ['Show inbox', 'Mark all read', 'Compose new']
      }
    }

    return {
      content: 'I help with emails - composing, reading, and organizing. What would you like?',
      actions: ['email_processing'],
      quickReplies: ['Compose email', 'Check inbox', 'Send draft']
    }
  }

  private handleCalendar(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[]; quickReplies?: string[] } {
    if (lower.includes('schedule') || lower.includes('book') || lower.includes('new meeting')) {
      const event: CalendarEvent = {
        id: uuid(),
        title: 'New Meeting',
        startTime: new Date(Date.now() + 3600000),
        endTime: new Date(Date.now() + 7200000),
        attendees: [],
        reminders: [{ minutesBefore: 15, sent: false }],
        status: 'confirmed'
      }
      this.context.calendar.push(event)
      return {
        content: `I've scheduled: ${event.title} for ${event.startTime.toLocaleString()}. Would you like to add attendees?`,
        actions: ['calendar_management'],
        quickReplies: ['Add attendees', 'Set reminder', 'View calendar']
      }
    }

    if (lower.includes('next') || lower.includes('upcoming')) {
      const upcoming = this.context.calendar.filter(e => new Date(e.startTime) > new Date()).slice(0, 5)
      if (upcoming.length === 0) return { content: 'You have no upcoming events.', actions: ['calendar_check'] }
      return {
        content: `Upcoming: ${upcoming.map(e => `${new Date(e.startTime).toLocaleDateString()} - ${e.title}`).join(', ')}`,
        actions: ['calendar_check'],
        quickReplies: ['View full calendar', 'Schedule meeting', 'Cancel event']
      }
    }

    return {
      content: 'I manage your calendar - scheduling meetings, checking availability, and more.',
      actions: ['calendar_management'],
      quickReplies: ['Schedule meeting', 'Check availability', 'View today']
    }
  }

  private handleTask(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[]; quickReplies?: string[] } {
    if (lower.includes('create') || lower.includes('add') || lower.includes('new task')) {
      const task: Task = {
        id: uuid(),
        title: message.replace(/create|add|task|todo/gi, '').trim() || 'New Task',
        priority: 'medium',
        status: 'pending',
        createdAt: new Date(),
        tags: [],
        subtasks: [],
        attachments: []
      }
      this.context.tasks.push(task)
      return {
        content: `Created task: \"${task.title}\" with ${task.priority} priority.`,
        actions: ['task_creation'],
        quickReplies: ['Set due date', 'Add subtask', 'View tasks']
      }
    }

    if (lower.includes('list') || lower.includes('show') || lower.includes('my tasks')) {
      const pending = this.context.tasks.filter(t => t.status === 'pending')
      if (pending.length === 0) return { content: 'You have no pending tasks!', actions: ['task_check'] }
      return {
        content: `Your tasks: ${pending.map(t => t.title).join(', ')}`,
        actions: ['task_check'],
        quickReplies: ['View all tasks', 'Complete task', 'Create task']
      }
    }

    return {
      content: 'I manage tasks - creating, tracking, and completing.',
      actions: ['task_management'],
      quickReplies: ['Create task', 'List tasks', 'Complete task']
    }
  }

  private handleNote(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[]; quickReplies?: string[] } {
    if (lower.includes('create') || lower.includes('add') || lower.includes('new note')) {
      const note: Note = {
        id: uuid(),
        title: 'Quick Note',
        content: message.replace(/note|remember|write down/gi, '').trim(),
        createdAt: new Date(),
        updatedAt: new Date(),
        tags: [],
        isPinned: false,
        isArchived: false
      }
      this.context.notes.push(note)
      return {
        content: `Created note: \"${note.title}\"`,
        actions: ['note_creation'],
        quickReplies: ['View notes', 'Search notes', 'Edit note']
      }
    }

    return {
      content: 'I manage your notes. Would you like to create one or view existing notes?',
      actions: ['note_management'],
      quickReplies: ['Create note', 'List notes', 'Search notes']
    }
  }

  private handleReminder(message: string, _lower: string): { content: string; actions: string[]; suggestedActions?: string[]; quickReplies?: string[] } {
    const reminder: Reminder = {
      id: uuid(),
      title: message.replace(/remind|alert/gi, '').trim() || 'Reminder',
      message: '',
      triggerTime: new Date(Date.now() + 3600000),
      status: 'active'
    }
    this.context.reminders.push(reminder)
    return {
      content: `I've set a reminder: \"${reminder.title}\" in 1 hour.`,
      actions: ['reminder_creation'],
      quickReplies: ['View reminders', 'Cancel reminder', 'Set repeat']
    }
  }

  private handleContact(_message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[]; quickReplies?: string[] } {
    if (lower.includes('add') || lower.includes('new contact')) {
      const contact: Contact = {
        id: uuid(),
        firstName: 'New',
        lastName: 'Contact',
        emails: [],
        phones: [],
        addresses: [],
        tags: [],
        relationship: 'other',
        socialProfiles: []
      }
      this.context.contacts.push(contact)
      return {
        content: 'Added new contact. Would you like to add details?',
        actions: ['contact_creation'],
        quickReplies: ['View contacts', 'Edit contact', 'Add phone/email']
      }
    }

    return {
      content: 'I manage your contacts. Would you like to add a contact or search existing ones?',
      actions: ['contact_management'],
      quickReplies: ['Add contact', 'Search contacts', 'View all']
    }
  }

  private handleFinance(_message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[]; quickReplies?: string[] } {
    if (lower.includes('summary') || lower.includes('balance')) {
      const total = this.context.finances.reduce((sum: number, acc: FinanceAccount) => sum + acc.balance, 0)
      return {
        content: `Total balance: $${total.toFixed(2)} across ${this.context.finances.length} account(s).`,
        actions: ['finance_summary'],
        quickReplies: ['View accounts', 'Add account', 'Set budget']
      }
    }

    return {
      content: 'I help track finances - accounts, budgets, and expenses.',
      actions: ['finance_tracking'],
      quickReplies: ['Add account', 'View balance', 'Set budget']
    }
  }

  private handleTravel(_message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[]; quickReplies?: string[] } {
    if (lower.includes('plan') || lower.includes('book') || lower.includes('trip')) {
      const plan: TravelPlan = {
        id: uuid(),
        type: 'other',
        status: 'planned',
        startDate: new Date(),
        endDate: new Date(),
        details: {} as any
      }
      this.context.travel.push(plan)
      return {
        content: 'Added new travel plan. Would you like to add flight or hotel details?',
        actions: ['travel_planning'],
        quickReplies: ['Add flight', 'Add hotel', 'View itinerary']
      }
    }

    return {
      content: 'I help plan travel - flights, hotels, and itineraries.',
      actions: ['travel_planning'],
      quickReplies: ['Plan trip', 'View itinerary', 'Add flight']
    }
  }

  private handleHealth(_message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[]; quickReplies?: string[] } {
    if (lower.includes('log') || lower.includes('track')) {
      const metrics: HealthMetrics = { id: uuid(), date: new Date() }
      this.context.health.push(metrics)
      return {
        content: 'Logged your health metrics.',
        actions: ['health_tracking'],
        quickReplies: ['View trends', 'Set goals', 'Log weight']
      }
    }

    return {
      content: 'I track health metrics - weight, sleep, mood, and more.',
      actions: ['health_tracking'],
      quickReplies: ['Log metrics', 'View trends', 'Set goals']
    }
  }

  private handleResearch(message: string, _lower: string): { content: string; actions: string[]; suggestedActions?: string[]; quickReplies?: string[] } {
    const query = message.replace(/search|research|look up/gi, '').trim()
    return {
      content: `Search results for \"${query}\": This is a placeholder. In production, would call web search API.`,
      actions: ['web_research'],
      quickReplies: ['Save result', 'Search more', 'Open first result']
    }
  }

  private handleDailyOverview(): { content: string; actions: string[]; quickReplies?: string[] } {
    const now = new Date()
    const todayEvents = this.context.calendar.filter(e => new Date(e.startTime).toDateString() === now.toDateString() && e.status !== 'cancelled')
    const pendingTasks = this.context.tasks.filter(t => t.status === 'pending')
    const unreadEmails = this.context.emails.filter(e => !e.isRead).length
    const waitingVisitors = this.context.visitors.filter(v => v.status === 'waiting' || v.status === 'checked_in').length

    let response = `Your Day Overview - ${now.toLocaleDateString()}\n`
    response += `Meetings: ${todayEvents.length}\n`
    response += `Tasks: ${pendingTasks.length}\n`
    response += `Unread Emails: ${unreadEmails}\n`
    if (this.context.industry !== 'personal') {
      response += `Visitors Waiting: ${waitingVisitors}\n`
    }
    response += `\nHow can I help?`

    return {
      content: response,
      actions: ['daily_overview'],
      quickReplies: ['Schedule meeting', 'Create task', 'Check visitors', 'Send email']
    }
  }

  private handleRecall(message: string, _lower: string): { content: string; actions: string[]; quickReplies?: string[] } {
    const query = message.replace(/remember|what|earlier|previously/gi, '').trim()
    const memories = this.context.memory.filter(m => m.content.toLowerCase().includes(query.toLowerCase())).slice(-5)

    if (memories.length === 0) {
      return {
        content: `I don't have memories about \"${query}\".`,
        actions: ['memory_recall'],
        quickReplies: ['Store memory', 'Show recent', 'Clear old']
      }
    }

    return {
      content: `From memory: ${memories.map(m => `[${new Date(m.timestamp).toLocaleDateString()}] ${m.content}`).join(' | ')}`,
      actions: ['memory_recall'],
      quickReplies: ['Store more', 'Show all', 'Search different']
    }
  }

  private handleDefault(_message: string): { content: string; actions: string[]; suggestedActions?: string[]; quickReplies?: string[] } {
    return {
      content: 'I am your unified Personal AI Assistant and Receptionist. I can help with:\n\n- Scheduling & Calendar\n- Tasks & Projects\n- Email & Communication\n- Notes & Reminders\n- Visitors & Check-ins\n- Appointments\n- Finances\n- Travel\n- Health\n- Research\n\nWhat would you like?',
      actions: ['general_assistance'],
      quickReplies: ['Schedule meeting', 'Create task', 'Check visitors', 'Send email', 'View my day']
    }
  }

  private learnFromConversation(message: string): void {
    if (this.context.memory.length === 0 || Math.random() > 0.8) {
      this.context.memory.push({
        id: uuid(),
        timestamp: new Date(),
        type: 'conversation',
        content: message.substring(0, 200),
        importance: 'medium',
        tags: []
      })
    }
    if (this.context.memory.length > 200) {
      this.context.memory = this.context.memory.slice(-200)
    }
  }

  private getKnowledgeBase(): Array<{ question: string; answer: string; keywords: string[]; category: string }> {
    const bases: Record<IndustryType, Array<{ question: string; answer: string; keywords: string[]; category: string }>> = {
      personal: [
        { question: 'Hours?', answer: 'I am available 24/7 for your personal assistance.', keywords: ['hours', 'available', 'time'], category: 'general' },
        { question: 'Schedule?', answer: 'I can help you schedule appointments and meetings.', keywords: ['schedule', 'appointment', 'book'], category: 'scheduling' }
      ],
      healthcare: [
        { question: 'Hours?', answer: 'Mon-Fri 8am-6pm, Sat 9am-1pm', keywords: ['hours', 'open', 'time'], category: 'general' },
        { question: 'Appointments?', answer: 'Call (555) 123-4567 or book online', keywords: ['schedule', 'appointment', 'book'], category: 'scheduling' }
      ],
      corporate: [
        { question: 'Meeting rooms?', answer: 'Floors 3-5', keywords: ['meeting', 'room', 'location'], category: 'directions' },
        { question: 'WiFi?', answer: 'GuestNetwork / Welcome2024', keywords: ['wifi', 'internet', 'password'], category: 'facilities' }
      ],
      hospitality: [
        { question: 'Check-in?', answer: '3:00 PM standard', keywords: ['checkin', 'check-in', 'time'], category: 'rooms' },
        { question: 'WiFi?', answer: 'Free WiFi - GuestWiFi', keywords: ['wifi', 'internet'], category: 'amenities' }
      ],
      realestate: [
        { question: 'Listings?', answer: 'Browse our website for current listings', keywords: ['listing', 'property', 'home'], category: 'properties' }
      ],
      legal: [
        { question: 'Consultation?', answer: 'Schedule a consultation by calling our office', keywords: ['consult', 'lawyer', 'attorney'], category: 'services' }
      ],
      retail: [
        { question: 'Products?', answer: 'Visit our store or browse online', keywords: ['product', 'buy', 'shop'], category: 'shopping' }
      ],
      education: [
        { question: 'Admissions?', answer: 'Contact admissions office for enrollment info', keywords: ['admission', 'enroll', 'student'], category: 'academic' }
      ],
      government: [
        { question: 'Services?', answer: 'Visit our website for available services', keywords: ['service', 'permit', 'license'], category: 'services' }
      ]
    }
    return bases[this.context.industry] || bases.personal
  }

  // =========================================================================
  // PUBLIC API
  // =========================================================================

  getContext(): PersonalReceptionistContext {
    return { ...this.context }
  }

  getConversationHistory(): ConversationMessage[] {
    return [...this.conversationHistory]
  }

  updatePreferences(prefs: Partial<UserPreferences>): void {
    this.context.preferences = { ...this.context.preferences, ...prefs }
  }

  getWaitingVisitors(): Visitor[] {
    return this.context.visitors.filter(v => v.status === 'waiting' || v.status === 'checked_in')
  }

  getTodayAppointments(): Appointment[] {
    const today = new Date().toDateString()
    return this.context.appointments.filter(a => new Date(a.dateTime).toDateString() === today)
  }

  getOpenEscalations(): EscalationTicket[] {
    return this.context.escalations.filter(e => e.status === 'open' || e.status === 'assigned')
  }

  checkInVisitor(name: string, purpose: string, email?: string, hostName?: string): Visitor {
    const visitor: Visitor = {
      id: uuid(),
      name,
      purpose,
      email,
      checkInTime: new Date(),
      status: 'checked_in',
      hostName
    }
    this.context.visitors.push(visitor)
    this.context.queueStats.totalServedToday++
    return visitor
  }

  destroy(): void {
    if (this.reminderInterval) {
      clearInterval(this.reminderInterval)
      this.reminderInterval = null
    }
  }
}

// Singleton manager
const agentInstances: Map<string, PersonalReceptionistAgent> = new Map()

export function getPersonalReceptionist(userId: string, name: string, tier?: AgentTier, industry?: IndustryType): PersonalReceptionistAgent {
  if (!agentInstances.has(userId)) {
    agentInstances.set(userId, new PersonalReceptionistAgent(userId, name, tier, industry))
  }
  return agentInstances.get(userId)!
}

export function removePersonalReceptionist(userId: string): void {
  const agent = agentInstances.get(userId)
  if (agent) {
    agent.destroy()
    agentInstances.delete(userId)
  }
}

export default PersonalReceptionistAgent