/**
 * Multi-Agent Orchestration System - Core Types
 * Defines the contract for agents, tasks, messages, and orchestration
 */

// Agent Types
export type AgentRole = 'orchestrator' | 'researcher' | 'coder' | 'reviewer' | 'executor' | 'planner'

export type AgentStatus = 'idle' | 'working' | 'waiting' | 'completed' | 'failed'

export interface AgentCapability {
  name: string
  description: string
  tools: string[]
  maxConcurrentTasks: number
}

export interface AgentConfig {
  id: string
  name: string
  role: AgentRole
  capabilities: AgentCapability[]
  model?: string
  temperature?: number
  maxTokens?: number
}

export interface AgentState {
  agentId: string
  status: AgentStatus
  currentTaskId?: string
  completedTasks: string[]
  failedTasks: string[]
  lastActivity: Date
  metrics: AgentMetrics
}

export interface AgentMetrics {
  tasksCompleted: number
  tasksFailed: number
  averageExecutionTime: number
  totalTokensUsed: number
}

// Task Types
export type TaskStatus = 'pending' | 'assigned' | 'in_progress' | 'completed' | 'failed' | 'blocked'

export type TaskPriority = 'low' | 'medium' | 'high' | 'critical'

export interface TaskDependency {
  taskId: string
  type: 'blocks' | 'depends_on' | 'enhances'
}

export interface TaskResult {
  success: boolean
  output?: unknown
  error?: string
  artifacts?: TaskArtifact[]
  metrics?: {
    duration: number
    tokensUsed?: number
  }
}

export interface TaskArtifact {
  name: string
  type: 'file' | 'data' | 'code' | 'report' | 'evidence'
  path?: string
  content?: string
  metadata?: Record<string, unknown>
}

export interface Task {
  id: string
  type: string
  description: string
  priority: TaskPriority
  status: TaskStatus
  assignedAgent?: string
  dependencies: TaskDependency[]
  context: TaskContext
  result?: TaskResult
  createdAt: Date
  updatedAt: Date
  startedAt?: Date
  completedAt?: Date
  timeout?: number
}

export interface TaskContext {
  userRequest: string
  sessionId: string
  workspace?: string
  variables: Record<string, unknown>
  files?: string[]
  previousResults?: Record<string, unknown>
}

// Plan structure for task variables
export interface PlanStep {
  id: string
  instruction: string
  expectedOutput?: string
  verified?: boolean
}

export interface ExecutionPlan {
  id: string
  taskId: string
  steps: PlanStep[]
  estimatedDuration: number
}

// Message Types for Agent Communication
export type MessageType = 'task' | 'result' | 'status' | 'error' | 'heartbeat' | 'command'

export interface AgentMessage {
  id: string
  type: MessageType
  senderId: string
  recipientId?: string // undefined means broadcast
  taskId?: string
  correlationId: string
  payload: unknown
  timestamp: Date
  priority: 'normal' | 'high' | 'critical'
}

// Orchestration Types
export interface WorkflowDefinition {
  id: string
  name: string
  description: string
  tasks: WorkflowTask[]
  agents: AgentConfig[]
  maxParallelAgents: number
  retryPolicy?: RetryPolicy
  timeout?: number
}

export interface WorkflowTask {
  id: string
  type: string
  agentRole: AgentRole
  instruction: string
  dependencies: string[]
  timeout?: number
  critical?: boolean
}

export interface RetryPolicy {
  maxRetries: number
  backoffMs: number
  exponentialBackoff: boolean
}

export interface OrchestrationResult {
  success: boolean
  workflowId: string
  completedTasks: string[]
  failedTasks: string[]
  artifacts: TaskArtifact[]
  summary: string
  metrics: {
    totalDuration: number
    agentsUsed: string[]
    tasksCompleted: number
  }
}

// Execution Types
export interface ExecutionStep {
  id: string
  instruction: string
  tool?: string
  expectedOutput?: string
  verified?: boolean
}

export interface ExecutionStep {
  id: string
  instruction: string
  tool?: string
  expectedOutput?: string
  verified?: boolean
}

export interface ToolResult {
  tool: string
  success: boolean
  output?: unknown
  error?: string
  duration: number
}

// Event Types for Monitoring
export type EventType = 
  | 'agent:spawned' 
  | 'agent:task_assigned' 
  | 'agent:task_completed' 
  | 'agent:error'
  | 'workflow:started'
  | 'workflow:completed'
  | 'workflow:failed'

export interface SystemEvent {
  type: EventType
  timestamp: Date
  source: string
  data: Record<string, unknown>
}

// API Types
export interface CreateAgentRequest {
  name: string
  role: AgentRole
  capabilities?: Partial<AgentCapability>[]
  model?: string
}

export interface CreateWorkflowRequest {
  name: string
  description: string
  tasks: Omit<WorkflowTask, 'id'>[]
  maxParallelAgents?: number
}

export interface ExecuteTaskRequest {
  taskType: string
  description: string
  priority?: TaskPriority
  context?: Partial<TaskContext>
  agentRole?: AgentRole
}