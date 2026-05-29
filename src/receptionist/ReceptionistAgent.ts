/**
 * ============================================================
 * AI RECEPTIONIST AGENT
 * ============================================================
 * 
 * Integrates ARIA (voice), CHRONOS (scheduling), WIKI (knowledge),
 * and CONNECT (escalation) for a complete AI receptionist solution.
 */

import { EventEmitter } from 'events'
import { v4 as uuid } from 'uuid'
import { IndustryType } from './types'
import { Visitor, Appointment, Message, EscalationTicket, ReceptionistContext, AgentStats, QueueStats } from './types'

// Simulated receptionist agents (in production, would import from frontdesk-agents)
class MockReceptionistTool {
  constructor(
    public name: string,
    public description: string,
    private executeFn: (params: unknown) => Promise<{ success: boolean; output: unknown; duration: number }>
  ) {}
  
  async execute(params: unknown) {
    return this.executeFn(params)
  }
}

export class ReceptionistAgent extends EventEmitter {
  private context: ReceptionistContext
  private tools: Map<string, MockReceptionistTool> = new Map()
  
  constructor(industry: IndustryType = 'corporate') {
    super()
    
    this.context = {
      industry,
      visitors: [],
      appointments: [],
      messages: [],
      escalations: [],
      agentStats: {
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
    
    this.initializeTools()
    console.log(`AI Receptionist initialized for ${industry} industry`)
  }
  
  private initializeTools(): void {
    // ARIA - Voice Receptionist Tools
    this.registerTool(new MockReceptionistTool(
      'aria_greet',
      'Greet visitor warmly',
      async (params: unknown) => {
        const p = params as { visitorName?: string }
        const greetings: Record<IndustryType, string> = {
          healthcare: 'Welcome to our medical facility. How may I assist you today?',
          legal: 'Welcome to our law office. How may I assist you with your legal matters?',
          realestate: 'Welcome to our real estate office. How may I help you find your dream property?',
          hospitality: 'Welcome to our hotel. How may I enhance your stay today?',
          corporate: 'Welcome to our corporate office. How may I assist you today?',
          retail: 'Welcome! How may I assist you with your shopping experience today?',
          education: 'Welcome to our academic institution. How may I assist you today?',
          government: 'Welcome to our government office. How may I serve you today?'
        }
        return {
          success: true,
          output: { greeting: greetings[this.context.industry], visitorName: p.visitorName, agent: 'ARIA' },
          duration: 0
        }
      }
    ))
    
    this.registerTool(new MockReceptionistTool(
      'aria_collect_info',
      'Collect visitor information',
      async (params: unknown) => {
        const p = params as { name: string; purpose: string; email?: string; phone?: string }
        const visitor: Visitor = {
          id: `VIS-${uuid()}`,
          name: p.name,
          email: p.email,
          phone: p.phone,
          purpose: p.purpose,
          checkInTime: new Date(),
          status: 'waiting'
        }
        this.context.visitors.push(visitor)
        this.context.agentStats.aria.callsHandled++
        return { success: true, output: { visitorId: visitor.id, name: visitor.name, purpose: visitor.purpose }, duration: 0 }
      }
    ))
    
    this.registerTool(new MockReceptionistTool(
      'aria_transfer',
      'Transfer to department',
      async (params: unknown) => {
        const p = params as { department: string; reason: string }
        return {
          success: true,
          output: { transferTo: p.department, estimatedWait: '2-3 minutes', position: Math.floor(Math.random() * 5) + 1 },
          duration: 0
        }
      }
    ))
    
    // CHRONOS - Scheduler Tools
    this.registerTool(new MockReceptionistTool(
      'chronos_book',
      'Book appointment',
      async (params: unknown) => {
        const p = params as { clientName: string; service: string; dateTime?: string; duration?: number }
        const apt: Appointment = {
          id: `APT-${uuid()}`,
          clientName: p.clientName,
          service: p.service,
          dateTime: p.dateTime ? new Date(p.dateTime) : new Date(),
          duration: p.duration || 30,
          status: 'scheduled',
          industry: this.context.industry
        }
        this.context.appointments.push(apt)
        this.context.agentStats.chronos.appointmentsBooked++
        return { success: true, output: { appointmentId: apt.id, clientName: apt.clientName, service: apt.service, dateTime: apt.dateTime }, duration: 0 }
      }
    ))
    
    this.registerTool(new MockReceptionistTool(
      'chronos_availability',
      'Check available slots',
      async (params: unknown) => {
        const slots = ['9:00 AM', '10:30 AM', '11:00 AM', '2:00 PM', '3:30 PM', '4:00 PM']
        const available = slots.slice(0, Math.floor(Math.random() * 4) + 2)
        return { success: true, output: { availableSlots: available, date: new Date().toISOString().split('T')[0] }, duration: 0 }
      }
    ))
    
    this.registerTool(new MockReceptionistTool(
      'chronos_reminder',
      'Send appointment reminder',
      async (params: unknown) => {
        const p = params as { appointmentId: string }
        const apt = this.context.appointments.find(a => a.id === p.appointmentId)
        if (apt) apt.reminderSent = true
        return { success: true, output: { reminderId: `REM-${uuid()}`, status: 'sent', appointmentId: p.appointmentId }, duration: 0 }
      }
    ))
    
    // WIKI - Knowledge Tools
    this.registerTool(new MockReceptionistTool(
      'wiki_faq',
      'Look up FAQ',
      async (params: unknown) => {
        const p = params as { query: string }
        const kb = this.getKnowledgeBase()
        const entry = kb.find(e => e.keywords.some(k => p.query.toLowerCase().includes(k)))
        this.context.agentStats.wiki.queriesAnswered++
        return {
          success: true,
          output: entry || { question: p.query, answer: 'I can help you with that. Please provide more details.', category: 'general' },
          duration: 0
        }
      }
    ))
    
    this.registerTool(new MockReceptionistTool(
      'wiki_directions',
      'Provide directions',
      async (_params: unknown) => {
        return {
          success: true,
          output: { directions: 'Take the main elevator to floor 3. Our office is on the left after reception.', floor: 3, room: 'Suite 301' },
          duration: 0
        }
      }
    ))
    
    // CONNECT - Escalation Tools
    this.registerTool(new MockReceptionistTool(
      'connect_ticket',
      'Create escalation ticket',
      async (params: unknown) => {
        const p = params as { reason: string; visitorId?: string; priority?: string }
        const ticket: EscalationTicket = {
          id: `ESC-${uuid()}`,
          visitorId: p.visitorId,
          reason: p.reason,
          priority: (p.priority as any) || 'medium',
          status: 'open',
          createdAt: new Date()
        }
        this.context.escalations.push(ticket)
        return { success: true, output: { ticketId: ticket.id, priority: ticket.priority, status: ticket.status }, duration: 0 }
      }
    ))
    
    this.registerTool(new MockReceptionistTool(
      'connect_resolve',
      'Resolve ticket',
      async (params: unknown) => {
        const p = params as { ticketId: string; resolution?: string }
        const ticket = this.context.escalations.find(t => t.id === p.ticketId)
        if (ticket) {
          ticket.status = 'resolved'
          ticket.resolvedAt = new Date()
          ticket.resolution = p.resolution
          this.context.agentStats.connect.ticketsResolved++
        }
        return { success: true, output: { ticketId: p.ticketId, status: 'resolved' }, duration: 0 }
      }
    ))
  }
  
  private registerTool(tool: MockReceptionistTool): void {
    this.tools.set(tool.name, tool)
  }
  
  private getKnowledgeBase(): Array<{ question: string; answer: string; keywords: string[]; category: string }> {
    const bases: Record<IndustryType, Array<{ question: string; answer: string; keywords: string[]; category: string }>> = {
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
    return bases[this.context.industry] || bases.corporate
  }
  
  // Main processing method
  async processVisitorInput(input: string, visitorId?: string): Promise<{
    content: string
    agent: string
    actions: string[]
    requiresEscalation: boolean
  }> {
    const lower = input.toLowerCase()
    
    // Route to appropriate agent based on intent
    if (lower.includes('schedule') || lower.includes('appointment') || lower.includes('book')) {
      return this.handleScheduling(input)
    }
    
    if (lower.includes('question') || lower.includes('faq') || lower.includes('where') || lower.includes('directions')) {
      return this.handleKnowledge(input)
    }
    
    if (lower.includes('speak') || lower.includes('human') || lower.includes('manager') || lower.includes('complaint')) {
      return this.handleEscalation(input, visitorId)
    }
    
    // Default to ARIA greeting/collection
    return this.handleGreeting(input)
  }
  
  private async handleGreeting(input: string): Promise<{ content: string; agent: string; actions: string[]; requiresEscalation: boolean }> {
    const result = await this.tools.get('aria_greet')?.execute({}) as { success: boolean; output: { greeting?: string } }
    const greeting = result?.output?.greeting || 'Welcome! How may I assist you today?'
    
    // Extract name if provided
    const nameMatch = input.match(/i'?m ([A-Za-z]+)/i) || input.match(/my name is ([A-Za-z]+)/i)
    if (nameMatch) {
      await this.tools.get('aria_collect_info')?.execute({ name: nameMatch[1], purpose: 'general inquiry' })
    }
    
    return {
      content: `${greeting} I'm ARIA, your AI receptionist. How can I help you today?`,
      agent: 'ARIA',
      actions: ['greet_visitor', 'collect_info'],
      requiresEscalation: false
    }
  }
  
  private async handleScheduling(input: string): Promise<{ content: string; agent: string; actions: string[]; requiresEscalation: boolean }> {
    // Extract potential date/time
    const dateMatch = input.match(/\b(tomorrow|next week|\d{1,2}\/\d{1,2}\/\d{2,4})\b/)
    const serviceMatch = input.match(/(?:consultation|appointment|meeting|checkup)/i)
    
    const result = await this.tools.get('chronos_book')?.execute({
      clientName: 'Guest',
      service: serviceMatch?.[0] || 'Consultation',
      dateTime: dateMatch?.[1] || undefined
    }) as { success: boolean; output: { appointmentId?: string; clientName?: string } }
    
    return {
      content: `I've scheduled your appointment, ${result?.output?.clientName || 'Guest'}. You'll receive a confirmation shortly. Anything else I can help with?`,
      agent: 'CHRONOS',
      actions: ['book_appointment', 'send_confirmation'],
      requiresEscalation: false
    }
  }
  
  private async handleKnowledge(input: string): Promise<{ content: string; agent: string; actions: string[]; requiresEscalation: boolean }> {
    const result = await this.tools.get('wiki_faq')?.execute({ query: input }) as { success: boolean; output: { answer?: string } }
    
    return {
      content: result?.output?.answer || 'I can help answer your question. Is there anything specific you would like to know?',
      agent: 'WIKI',
      actions: ['faq_lookup', 'provide_information'],
      requiresEscalation: false
    }
  }
  
  private async handleEscalation(input: string, visitorId?: string): Promise<{ content: string; agent: string; actions: string[]; requiresEscalation: boolean }> {
    const result = await this.tools.get('connect_ticket')?.execute({
      reason: input.substring(0, 200),
      visitorId,
      priority: 'high'
    }) as { success: boolean; output: { ticketId?: string } }
    
    return {
      content: `I've connected you with our team. Your ticket #${result?.output?.ticketId} has been created. A representative will be with you shortly.`,
      agent: 'CONNECT',
      actions: ['create_ticket', 'notify_agent'],
      requiresEscalation: true
    }
  }
  
  // Public API
  getContext(): ReceptionistContext {
    return { ...this.context }
  }
  
  getStats(): { agentStats: AgentStats; queueStats: QueueStats } {
    return {
      agentStats: this.context.agentStats,
      queueStats: this.context.queueStats
    }
  }
  
  checkInVisitor(name: string, purpose: string, email?: string): Visitor {
    const visitor: Visitor = {
      id: `VIS-${uuid()}`,
      name,
      purpose,
      email,
      checkInTime: new Date(),
      status: 'checked_in'
    }
    this.context.visitors.push(visitor)
    this.context.queueStats.totalServedToday++
    return visitor
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
}

// Singleton
let receptionistInstance: ReceptionistAgent | null = null

export function getReceptionist(industry?: IndustryType): ReceptionistAgent {
  if (!receptionistInstance) {
    receptionistInstance = new ReceptionistAgent(industry)
  }
  return receptionistInstance
}

export default ReceptionistAgent