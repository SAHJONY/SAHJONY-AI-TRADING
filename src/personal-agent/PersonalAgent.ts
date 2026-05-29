/**
 * ============================================================
 * PERSONAL AI AGENT - Full Autonomous Assistant
 * ============================================================
 * 
 * Comprehensive AI agent that serves as a complete personal
 * secretary/assistant for individuals.
 */

import { v4 as uuid } from 'uuid'
import { EventEmitter } from 'events'
import {
  PersonalContext,
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
  AIAgentResponse,
  ConversationMessage,
  AgentTier
} from './types'

export class PersonalAgent extends EventEmitter {
  private context: PersonalContext
  private conversationHistory: ConversationMessage[] = []
  private reminderInterval: NodeJS.Timeout | null = null

  constructor(userId: string, name: string, tier: AgentTier = 'basic') {
    super()
    this.context = this.initializeContext(userId, name, tier)
    this.startReminderScheduler()
    console.log(`Personal AI Agent initialized for ${name}`)
  }

  private initializeContext(userId: string, name: string, tier: AgentTier): PersonalContext {
    return {
      userId,
      name,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
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
      research: []
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
      agentId: `personal-agent-${this.context.userId}`,
      content: response.content,
      confidence: 0.9,
      actions: response.actions,
      suggestedActions: response.suggestedActions,
      nextActions: response.nextActions
    }
  }

  private async generateResponse(message: string): Promise<{
    content: string
    actions: string[]
    suggestedActions?: string[]
    nextActions?: string[]
  }> {
    const lower = message.toLowerCase()

    // Email handling
    if (lower.includes('email') || lower.includes('send ')) {
      return this.handleEmail(message, lower)
    }
    // Calendar handling
    if (lower.includes('schedule') || lower.includes('meeting') || lower.includes('calendar')) {
      return this.handleCalendar(message, lower)
    }
    // Task handling
    if (lower.includes('task') || lower.includes('todo')) {
      return this.handleTask(message, lower)
    }
    // Note handling
    if (lower.includes('note') || lower.includes('remember')) {
      return this.handleNote(message, lower)
    }
    // Reminder handling
    if (lower.includes('remind')) {
      return this.handleReminder(message, lower)
    }
    // Contact handling
    if (lower.includes('contact') || lower.includes('call')) {
      return this.handleContact(message, lower)
    }
    // Finance handling
    if (lower.includes('budget') || lower.includes('money') || lower.includes('expense')) {
      return this.handleFinance(message, lower)
    }
    // Travel handling
    if (lower.includes('travel') || lower.includes('flight') || lower.includes('hotel')) {
      return this.handleTravel(message, lower)
    }
    // Health handling
    if (lower.includes('health') || lower.includes('weight') || lower.includes('sleep')) {
      return this.handleHealth(message, lower)
    }
    // Research handling
    if (lower.includes('search') || lower.includes('research')) {
      return this.handleResearch(message, lower)
    }
    // Daily overview
    if (lower.includes('what do i have') || lower.includes('my schedule') || lower.includes('overview')) {
      return this.handleDailyOverview()
    }
    // Memory recall
    if (lower.includes('remember') && (lower.includes('what') || lower.includes('earlier'))) {
      return this.handleRecall(message, lower)
    }

    return this.handleDefault(message)
  }

  private handleEmail(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[] } {
    if (lower.includes('compose') || lower.includes('send') || lower.includes('new email')) {
      const email: Email = {
        id: uuid(),
        from: { email: this.context.email || 'assistant@personal.ai' },
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
      return { content: `I've drafted an email with subject: \"${email.subject}\". Would you like me to send it?`, actions: ['Email processing'], suggestedActions: ['Send email', 'Edit draft', 'Cancel'] }
    }

    if (lower.includes('inbox') || lower.includes('unread')) {
      const unread = this.context.emails.filter(e => !e.isRead).length
      return { content: `You have ${unread} unread email${unread !== 1 ? 's' : ''}.`, actions: ['Email processing'], suggestedActions: ['Check inbox', 'Mark all read'] }
    }

    return { content: 'I can help you with emails - composing, reading, and organizing.', actions: ['Email processing'], suggestedActions: ['Compose email', 'Check inbox'] }
  }

  private handleCalendar(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[] } {
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
      return { content: `I've scheduled: ${event.title} for ${event.startTime.toLocaleString()}`, actions: ['Calendar management'], suggestedActions: ['Add attendees', 'Set reminder', 'View calendar'] }
    }

    if (lower.includes('next') || lower.includes('upcoming')) {
      const upcoming = this.context.calendar.filter(e => new Date(e.startTime) > new Date()).slice(0, 5)
      if (upcoming.length === 0) return { content: 'You have no upcoming events.', actions: ['Calendar management'] }
      return { content: `Your upcoming: ${upcoming.map(e => `${new Date(e.startTime).toLocaleDateString()} - ${e.title}`).join(', ')}`, actions: ['Calendar management'] }
    }

    return { content: 'I manage your calendar - scheduling meetings, checking availability, and more.', actions: ['Calendar management'], suggestedActions: ['Schedule meeting', 'Check availability', 'View today'] }
  }

  private handleTask(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[] } {
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
      return { content: `Created task: \"${task.title}\" with ${task.priority} priority.`, actions: ['Task management'], suggestedActions: ['Set due date', 'Add subtask', 'View tasks'] }
    }

    if (lower.includes('list') || lower.includes('show') || lower.includes('my tasks')) {
      const pending = this.context.tasks.filter(t => t.status === 'pending')
      if (pending.length === 0) return { content: 'You have no pending tasks!', actions: ['Task management'] }
      return { content: `Your tasks: ${pending.map(t => t.title).join(', ')}`, actions: ['Task management'], suggestedActions: ['View all', 'Complete task', 'Create task'] }
    }

    return { content: 'I manage tasks - creating, tracking, and completing.', actions: ['Task management'], suggestedActions: ['Create task', 'List tasks', 'Complete task'] }
  }

  private handleNote(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[] } {
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
      return { content: `Created note: \"${note.title}\"`, actions: ['Note management'], suggestedActions: ['View notes', 'Search notes'] }
    }

    return { content: 'I manage your notes.', actions: ['Note management'], suggestedActions: ['Create note', 'List notes'] }
  }

  private handleReminder(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[] } {
    const reminder: Reminder = {
      id: uuid(),
      title: message.replace(/remind|alert/gi, '').trim() || 'Reminder',
      message: '',
      triggerTime: new Date(Date.now() + 3600000),
      status: 'active'
    }
    this.context.reminders.push(reminder)
    return { content: `I've set a reminder: \"${reminder.title}\" in 1 hour.`, actions: ['Reminder management'], suggestedActions: ['View reminders', 'Cancel'] }
  }

  private handleContact(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[] } {
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
      return { content: 'Added new contact.', actions: ['Contact management'], suggestedActions: ['View contacts', 'Edit contact'] }
    }

    return { content: 'I manage your contacts.', actions: ['Contact management'], suggestedActions: ['Add contact', 'Search contacts'] }
  }

  private handleFinance(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[] } {
    if (lower.includes('summary') || lower.includes('balance')) {
      const total = this.context.finances.reduce((sum: number, acc: FinanceAccount) => sum + acc.balance, 0)
      return { content: `Total balance: $${total.toFixed(2)} across ${this.context.finances.length} account(s).`, actions: ['Finance tracking'], suggestedActions: ['View accounts', 'Add account', 'Set budget'] }
    }

    return { content: 'I help track finances - accounts, budgets, and expenses.', actions: ['Finance tracking'], suggestedActions: ['Add account', 'View balance', 'Set budget'] }
  }

  private handleTravel(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[] } {
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
      return { content: 'Added new travel plan.', actions: ['Travel planning'], suggestedActions: ['Add flight', 'Add hotel', 'View itinerary'] }
    }

    return { content: 'I help plan travel - flights, hotels, and itineraries.', actions: ['Travel planning'], suggestedActions: ['Plan trip', 'View itinerary'] }
  }

  private handleHealth(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[] } {
    if (lower.includes('log') || lower.includes('track')) {
      const metrics: HealthMetrics = { id: uuid(), date: new Date() }
      this.context.health.push(metrics)
      return { content: 'Logged your health metrics.', actions: ['Health tracking'], suggestedActions: ['View trends', 'Set goals'] }
    }

    return { content: 'I track health metrics - weight, sleep, mood, and more.', actions: ['Health tracking'], suggestedActions: ['Log metrics', 'View trends', 'Set goals'] }
  }

  private handleResearch(message: string, lower: string): { content: string; actions: string[]; suggestedActions?: string[] } {
    const query = message.replace(/search|research|look up/gi, '').trim()
    return { content: `Search results for \"${query}\": This is a placeholder. In production, would call web search API.`, actions: ['Web research'], suggestedActions: ['Save result', 'Search more'] }
  }

  private handleDailyOverview(): { content: string; actions: string[] } {
    const now = new Date()
    const todayEvents = this.context.calendar.filter(e => new Date(e.startTime).toDateString() === now.toDateString() && e.status !== 'cancelled')
    const pendingTasks = this.context.tasks.filter(t => t.status === 'pending')
    const unreadEmails = this.context.emails.filter(e => !e.isRead).length

    let response = `Your Day Overview - ${now.toLocaleDateString()}\n`
    response += `Meetings: ${todayEvents.length}\n`
    response += `Tasks: ${pendingTasks.length}\n`
    response += `Unread Emails: ${unreadEmails}\n`
    response += `\nHow can I help?`

    return { content: response, actions: ['Daily overview'] }
  }

  private handleRecall(message: string, lower: string): { content: string; actions: string[] } {
    const query = message.replace(/remember|what|earlier|previously/gi, '').trim()
    const memories = this.context.memory.filter(m => m.content.toLowerCase().includes(query.toLowerCase())).slice(-5)

    if (memories.length === 0) {
      return { content: `I don't have memories about \"${query}\".`, actions: ['Memory recall'] }
    }

    return { content: `From memory: ${memories.map(m => `[${new Date(m.timestamp).toLocaleDateString()}] ${m.content}`).join(' | ')}`, actions: ['Memory recall'] }
  }

  private handleDefault(message: string): { content: string; actions: string[]; suggestedActions?: string[] } {
    return {
      content: 'I am your personal AI assistant. I can help with: scheduling, tasks, notes, reminders, email, contacts, finances, travel, health, and research. What would you like?',
      actions: ['General assistance'],
      suggestedActions: ['Schedule meeting', 'Create task', 'Check my day', 'Research topic']
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

  // Public API
  getContext(): PersonalContext {
    return { ...this.context }
  }

  getConversationHistory(): ConversationMessage[] {
    return [...this.conversationHistory]
  }

  updatePreferences(prefs: Partial<UserPreferences>): void {
    this.context.preferences = { ...this.context.preferences, ...prefs }
  }

  destroy(): void {
    if (this.reminderInterval) {
      clearInterval(this.reminderInterval)
      this.reminderInterval = null
    }
  }
}

// Singleton manager
const agentInstances: Map<string, PersonalAgent> = new Map()

export function getPersonalAgent(userId: string, name: string, tier?: AgentTier): PersonalAgent {
  if (!agentInstances.has(userId)) {
    agentInstances.set(userId, new PersonalAgent(userId, name, tier))
  }
  return agentInstances.get(userId)!
}

export function removePersonalAgent(userId: string): void {
  const agent = agentInstances.get(userId)
  if (agent) {
    agent.destroy()
    agentInstances.delete(userId)
  }
}

export default PersonalAgent