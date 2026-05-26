/**
 * ============================================================
 * AI RECEPTIONIST - TypeScript Interfaces
 * ============================================================
 */

// Industry type - defined locally to avoid cross-module import issues
export type IndustryType = 'healthcare' | 'legal' | 'realestate' | 'hospitality' | 'corporate' | 'retail' | 'education' | 'government'
export type AgentType = 'greeting' | 'scheduling' | 'information' | 'escalation' | 'multilingual'

// Visitor types
export interface Visitor {
  id: string
  name: string
  email?: string
  phone?: string
  company?: string
  purpose: string
  checkInTime?: Date
  status: 'waiting' | 'checked_in' | 'with_agent' | 'completed' | 'no_show'
  language?: string
  sentiment?: 'positive' | 'neutral' | 'negative'
  notes?: string
}

export interface Appointment {
  id: string
  clientName: string
  service: string
  dateTime: Date
  duration: number // minutes
  status: 'scheduled' | 'confirmed' | 'in_progress' | 'completed' | 'cancelled' | 'no_show'
  industry: IndustryType
  reminderSent?: boolean
  notes?: string
}

export interface Message {
  id: string
  from: string
  to?: string
  content: string
  timestamp: Date
  status: 'pending' | 'delivered' | 'read'
  priority?: 'low' | 'normal' | 'high' | 'urgent'
}

export interface EscalationTicket {
  id: string
  visitorId?: string
  reason: string
  priority: 'low' | 'medium' | 'high' | 'critical'
  status: 'open' | 'assigned' | 'in_progress' | 'resolved' | 'closed'
  assignedAgent?: string
  createdAt: Date
  resolvedAt?: Date
  resolution?: string
}

export interface KnowledgeBaseEntry {
  question: string
  answer: string
  keywords: string[]
  category: string
}

// Receptionist Context
export interface ReceptionistContext {
  industry: IndustryType
  visitors: Visitor[]
  appointments: Appointment[]
  messages: Message[]
  escalations: EscalationTicket[]
  agentStats: AgentStats
  queueStats: QueueStats
}

export interface AgentStats {
  aria: { callsHandled: number; avgResponseTime: number; status: string }
  chronos: { appointmentsBooked: number; avgBookingTime: number; status: string }
  wiki: { queriesAnswered: number; accuracy: number; status: string }
  connect: { ticketsResolved: number; avgResolutionTime: number; status: string }
}

export interface QueueStats {
  waitingCount: number
  avgWaitTime: number
  totalServedToday: number
  peakHour: string
  satisfactionScore: number
}

// AI Response
export interface ReceptionistResponse {
  agentId: string
  agentName: string
  content: string
  confidence: number
  actions: string[]
  requiresHumanEscalation: boolean
  suggestedActions?: string[]
  nextActions?: string[]
}

// Industry configurations
export interface IndustryConfig {
  name: string
  greeting: string
  specialties: string[]
  peakHours: string[]
  commonQuestions: string[]
}