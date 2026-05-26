/**
 * ============================================================
 * PERSONAL AI RECEPTIONIST - Unified Types
 * ============================================================
 * 
 * Combines Personal AI Agent + AI Receptionist capabilities:
 * - Personal: Email, Calendar, Tasks, Notes, Files, Finance, Travel, Health, Research
 * - Receptionist: Visitor greeting, Appointment scheduling, Knowledge base, Escalations
 */

export type AgentTier = 'basic' | 'pro' | 'executive'

// ============================================================================
// INDUSTRY TYPES (for receptionist)
// ============================================================================

export type IndustryType = 'healthcare' | 'legal' | 'realestate' | 'hospitality' | 'corporate' | 'retail' | 'education' | 'government' | 'personal'
export type AgentType = 'greeting' | 'scheduling' | 'information' | 'escalation' | 'multilingual'

// ============================================================================
// CORE CONTEXT & USER
// ============================================================================

export interface UserPreferences {
  language: string
  timezone: string
  communicationStyle: 'formal' | 'casual' | 'friendly'
  workingHours: { start: string; end: string }
  defaultCalendar?: string
  emailProvider?: string
  theme?: 'light' | 'dark'
  notifications: NotificationPrefs
}

export interface NotificationPrefs {
  email: boolean
  push: boolean
  sms: boolean
  desktop: boolean
  quietHours: { start: string; end: string }
}

export interface ConversationMemory {
  id: string
  timestamp: Date
  type: 'conversation' | 'task' | 'calendar' | 'email' | 'note' | 'preference' | 'fact' | 'preference_change'
  content: string
  importance: 'low' | 'medium' | 'high' | 'critical'
  metadata?: Record<string, unknown>
  tags: string[]
}

// ============================================================================
// TASKS & PROJECTS
// ============================================================================

export interface Task {
  id: string
  title: string
  description?: string
  dueDate?: Date
  priority: 'low' | 'medium' | 'high' | 'urgent'
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled' | 'deferred'
  createdAt: Date
  completedAt?: Date
  tags: string[]
  projectId?: string
  subtasks: SubTask[]
  attachments: string[]
  notes?: string
  estimatedHours?: number
  actualHours?: number
}

export interface SubTask {
  id: string
  title: string
  status: 'pending' | 'completed'
  completedAt?: Date
}

export interface Project {
  id: string
  name: string
  description?: string
  status: 'active' | 'completed' | 'on_hold' | 'cancelled'
  startDate: Date
  targetDate?: Date
  tasks: string[]
  progress: number
  teamMembers: string[]
}

// ============================================================================
// CALENDAR & SCHEDULING
// ============================================================================

export interface CalendarEvent {
  id: string
  title: string
  description?: string
  startTime: Date
  endTime: Date
  location?: string
  attendees: Attendee[]
  reminders: ReminderConfig[]
  status: 'confirmed' | 'tentative' | 'cancelled' | 'needs_action'
  recurrence?: RecurrenceRule
  meetingLink?: string
  notes?: string
  color?: string
  category?: 'meeting' | 'appointment' | 'reminder' | 'personal' | 'travel' | 'deadline'
}

export interface Attendee {
  name: string
  email: string
  status: 'pending' | 'accepted' | 'declined' | 'tentative'
}

export interface ReminderConfig {
  minutesBefore: number
  sent: boolean
}

export interface RecurrenceRule {
  frequency: 'daily' | 'weekly' | 'monthly' | 'yearly'
  interval: number
  endDate?: Date
  count?: number
}

export interface AvailabilitySlot {
  start: string
  end: string
  available: boolean
}

// ============================================================================
// NOTES & REMINDERS
// ============================================================================

export interface Note {
  id: string
  title: string
  content: string
  createdAt: Date
  updatedAt: Date
  tags: string[]
  isPinned: boolean
  isArchived: boolean
  color?: string
  folder?: string
}

export interface Reminder {
  id: string
  title: string
  message: string
  triggerTime: Date
  status: 'active' | 'completed' | 'dismissed'
  repeat?: 'daily' | 'weekly' | 'monthly'
  snoozeMinutes?: number
  linkedEntityType?: 'task' | 'calendar' | 'email' | 'note'
  linkedEntityId?: string
}

// ============================================================================
// EMAIL & COMMUNICATION
// ============================================================================

export interface Email {
  id: string
  threadId?: string
  from: EmailAddress
  to: EmailAddress[]
  cc?: EmailAddress[]
  bcc?: EmailAddress[]
  subject: string
  body: string
  bodyHtml?: string
  timestamp: Date
  isRead: boolean
  isStarred: boolean
  isArchived: boolean
  labels: string[]
  attachments: EmailAttachment[]
  priority: 'low' | 'normal' | 'high' | 'urgent'
  sensitivity?: 'normal' | 'personal' | 'private' | 'confidential'
}

export interface EmailAddress {
  name?: string
  email: string
}

export interface EmailAttachment {
  id: string
  filename: string
  mimeType: string
  size: number
  url?: string
}

export interface EmailDraft {
  to: EmailAddress[]
  cc?: EmailAddress[]
  bcc?: EmailAddress[]
  subject: string
  body: string
  attachments?: string[]
  priority?: 'low' | 'normal' | 'high'
}

// ============================================================================
// FILES & DOCUMENTS
// ============================================================================

export interface FileAttachment {
  id: string
  filename: string
  mimeType: string
  size: number
  url?: string
  uploadedAt: Date
  modifiedAt?: Date
  tags: string[]
  folder?: string
  sharedWith?: string[]
  thumbnail?: string
}

// ============================================================================
// CONTACTS & CRM
// ============================================================================

export interface Contact {
  id: string
  firstName: string
  lastName: string
  company?: string
  jobTitle?: string
  emails: EmailAddress[]
  phones: PhoneNumber[]
  addresses: Address[]
  birthday?: Date
  anniversary?: Date
  tags: string[]
  notes?: string
  lastContacted?: Date
  relationship: 'client' | 'prospect' | 'partner' | 'vendor' | 'colleague' | 'family' | 'friend' | 'other'
  socialProfiles: SocialProfile[]
}

export interface PhoneNumber {
  type: 'mobile' | 'home' | 'work' | 'fax'
  number: string
  isPrimary: boolean
}

export interface Address {
  type: 'home' | 'work' | 'other'
  street: string
  city: string
  state: string
  zipCode: string
  country: string
}

export interface SocialProfile {
  platform: 'linkedin' | 'twitter' | 'facebook' | 'instagram' | 'github' | 'other'
  url: string
}

// ============================================================================
// FINANCES
// ============================================================================

export interface FinanceAccount {
  id: string
  name: string
  type: 'checking' | 'savings' | 'credit_card' | 'investment' | 'loan' | 'mortgage' | 'other'
  institution: string
  balance: number
  currency: string
  lastSynced?: Date
  accountNumber?: string
}

export interface Transaction {
  id: string
  accountId: string
  date: Date
  description: string
  amount: number
  currency: string
  category: string
  merchant?: string
  pending: boolean
  tags: string[]
}

export interface Budget {
  id: string
  name: string
  category: string
  limit: number
  spent: number
  period: 'weekly' | 'monthly' | 'yearly'
  startDate: Date
}

export interface Invoice {
  id: string
  number: string
  clientName: string
  clientEmail: string
  amount: number
  dueDate: Date
  status: 'draft' | 'sent' | 'paid' | 'overdue' | 'cancelled'
  items: InvoiceItem[]
}

export interface InvoiceItem {
  description: string
  quantity: number
  rate: number
  amount: number
}

// ============================================================================
// TRAVEL
// ============================================================================

export interface TravelPlan {
  id: string
  type: 'flight' | 'hotel' | 'car_rental' | 'train' | 'other'
  status: 'planned' | 'booked' | 'completed' | 'cancelled'
  startDate: Date
  endDate: Date
  details: FlightDetails | HotelDetails | CarRentalDetails | TrainDetails
  confirmationNumber?: string
  cost?: number
  currency?: string
  notes?: string
}

export interface FlightDetails {
  airline: string
  flightNumber: string
  departure: { airport: string; city: string; time: Date }
  arrival: { airport: string; city: string; time: Date }
  seat?: string
  class?: 'economy' | 'business' | 'first'
  terminal?: string
  gate?: string
}

export interface HotelDetails {
  hotelName: string
  address: string
  roomType: string
  checkIn: Date
  checkOut: Date
  confirmationNumber?: string
  amenities: string[]
}

export interface CarRentalDetails {
  company: string
  vehicleType: string
  pickupLocation: string
  dropoffLocation?: string
  pickupTime: Date
  dropoffTime: Date
  confirmationNumber?: string
}

export interface TrainDetails {
  railway: string
  trainNumber: string
  departure: { station: string; city: string; time: Date }
  arrival: { station: string; city: string; time: Date }
  seat?: string
  class?: string
}

export interface TravelItinerary {
  id: string
  name: string
  startDate: Date
  endDate: Date
  destinations: string[]
  plans: TravelPlan[]
  totalCost?: number
  notes?: string
}

// ============================================================================
// HEALTH & WELLNESS
// ============================================================================

export interface HealthMetrics {
  id: string
  date: Date
  weight?: number
  bloodPressureSystolic?: number
  bloodPressureDiastolic?: number
  heartRate?: number
  sleepHours?: number
  sleepQuality?: 1 | 2 | 3 | 4 | 5
  steps?: number
  caloriesBurned?: number
  waterIntake?: number
  mood?: 1 | 2 | 3 | 4 | 5
  notes?: string
}

export interface HealthGoal {
  id: string
  name: string
  type: 'fitness' | 'nutrition' | 'sleep' | 'stress' | 'general'
  target: number
  current: number
  unit: string
  deadline?: Date
  progress: number
}

export interface Medication {
  id: string
  name: string
  dosage: string
  frequency: string
  startDate: Date
  endDate?: Date
  reminderTime?: string
  prescribedBy?: string
  notes?: string
}

// ============================================================================
// RESEARCH & KNOWLEDGE
// ============================================================================

export interface ResearchItem {
  id: string
  topic: string
  summary: string
  sourceUrl?: string
  sourceName?: string
  keyPoints: string[]
  createdAt: Date
  updatedAt: Date
  tags: string[]
  notes?: string
  savedBy?: string
}

export interface WebSearch {
  id: string
  query: string
  results: SearchResult[]
  createdAt: Date
}

export interface SearchResult {
  title: string
  url: string
  snippet: string
  relevanceScore?: number
}

export interface Bookmark {
  id: string
  url: string
  title: string
  description?: string
  favicon?: string
  tags: string[]
  createdAt: Date
  lastVisited?: Date
  visitCount: number
}

// ============================================================================
// VISITOR & RECEPTIONIST TYPES
// ============================================================================

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
  hostName?: string  // Who they're visiting
}

export interface Appointment {
  id: string
  clientName: string
  service: string
  dateTime: Date
  duration: number
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

// ============================================================================
// UNIFIED CONTEXT
// ============================================================================

export interface PersonalReceptionistContext {
  // User identity
  userId: string
  name: string
  email?: string
  phone?: string
  timezone: string
  tier: AgentTier
  
  // User preferences
  preferences: UserPreferences
  
  // Personal capabilities data
  memory: ConversationMemory[]
  tasks: Task[]
  calendar: CalendarEvent[]
  notes: Note[]
  reminders: Reminder[]
  emails: Email[]
  files: FileAttachment[]
  contacts: Contact[]
  finances: FinanceAccount[]
  travel: TravelPlan[]
  health: HealthMetrics[]
  research: ResearchItem[]
  
  // Receptionist data
  industry: IndustryType
  visitors: Visitor[]
  appointments: Appointment[]
  messages: Message[]
  escalations: EscalationTicket[]
  
  // Agent stats
  agentStats: AgentStats
  queueStats: QueueStats
}

export interface AgentStats {
  // Personal agent stats
  messagesProcessed: number
  tasksCompleted: number
  emailsHandled: number
  
  // Receptionist agent stats
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

// ============================================================================
// AI RESPONSE & TOOLS
// ============================================================================

export interface AIAgentResponse {
  agentId: string
  content: string
  confidence: number
  actions: string[]
  contextUpdates?: Partial<PersonalReceptionistContext>
  suggestedActions?: string[]
  nextActions?: string[]
  requiresConfirmation?: boolean
  quickReplies?: string[]
  entitiesExtracted?: ExtractedEntity[]
}

export interface ExtractedEntity {
  type: 'person' | 'organization' | 'date' | 'time' | 'location' | 'email' | 'phone' | 'money' | 'event'
  value: string
  confidence: number
}

export interface ConversationMessage {
  id: string
  role: 'user' | 'agent' | 'system'
  content: string
  timestamp: Date
  attachments?: MessageAttachment[]
  entities?: ExtractedEntity[]
}

export interface MessageAttachment {
  type: 'file' | 'image' | 'link' | 'calendar' | 'task' | 'email'
  name: string
  url?: string
  metadata?: Record<string, unknown>
}

export interface ToolResult {
  success: boolean
  output?: unknown
  error?: string
  data?: Record<string, unknown>
  actionDescription?: string
}

// Industry configurations
export interface IndustryConfig {
  name: string
  greeting: string
  specialties: string[]
  peakHours: string[]
  commonQuestions: string[]
}