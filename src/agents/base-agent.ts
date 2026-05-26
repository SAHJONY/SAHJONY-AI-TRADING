/**
 * Base Agent Class
 * Abstract foundation for all specialized agents
 */

import { EventEmitter } from 'events'
import { 
  AgentConfig, 
  AgentState, 
  AgentStatus, 
  AgentRole,
  Task, 
  TaskResult,
  AgentMessage,
  TaskContext
} from '../types'

// Tool definitions for agents
export interface AgentTool {
  name: string
  description: string
  execute: (params: unknown) => Promise<ToolResult>
}

export interface ToolResult {
  success: boolean
  output?: unknown
  error?: string
  duration: number
}

// Base class for all agents
export abstract class BaseAgent extends EventEmitter {
  protected config: AgentConfig
  protected state: AgentState
  protected tools: Map<string, AgentTool> = new Map()
  protected messageQueue: AgentMessage[] = []
  
  constructor(config: AgentConfig) {
    super()
    this.config = config
    this.state = {
      agentId: config.id,
      status: 'idle',
      completedTasks: [],
      failedTasks: [],
      lastActivity: new Date(),
      metrics: {
        tasksCompleted: 0,
        tasksFailed: 0,
        averageExecutionTime: 0,
        totalTokensUsed: 0
      }
    }
  }

  // Abstract methods that subclasses must implement
  abstract executeTask(task: Task): Promise<TaskResult>
  abstract getCapabilities(): string[]

  // Common functionality
  get id(): string {
    return this.config.id
  }

  get role(): AgentRole {
    return this.config.role
  }

  get name(): string {
    return this.config.name
  }

  getStatus(): AgentStatus {
    return this.state.status
  }

  getState(): AgentState {
    return { ...this.state }
  }

  setStatus(status: AgentStatus): void {
    this.state.status = status
    this.state.lastActivity = new Date()
    this.emit('statusChange', { agentId: this.id, status })
  }

  // Tool management
  registerTool(tool: AgentTool): void {
    this.tools.set(tool.name, tool)
    this.emit('toolRegistered', { agentId: this.id, tool: tool.name })
  }

  async executeTool(toolName: string, params: unknown): Promise<ToolResult> {
    const tool = this.tools.get(toolName)
    if (!tool) {
      return { success: false, error: `Tool ${toolName} not found`, duration: 0 }
    }

    const startTime = Date.now()
    try {
      const result = await tool.execute(params)
      return { ...result, duration: Date.now() - startTime }
    } catch (error) {
      return { 
        success: false, 
        error: error instanceof Error ? error.message : String(error), 
        duration: Date.now() - startTime 
      }
    }
  }

  // Message handling
  sendMessage(message: AgentMessage): void {
    this.messageQueue.push(message)
    this.emit('messageSent', message)
  }

  receiveMessage(message: AgentMessage): void {
    this.emit('messageReceived', message)
    this.processMessage(message)
  }

  protected async processMessage(message: AgentMessage): Promise<void> {
    // Override in subclasses for specific message handling
  }

  // Task execution with lifecycle hooks
  async runTask(task: Task): Promise<TaskResult> {
    this.setStatus('working')
    this.state.currentTaskId = task.id

    const startTime = Date.now()
    
    try {
      // Pre-execution hooks
      await this.onTaskStart(task)

      // Execute the task
      const result = await this.executeTask(task)

      // Post-execution hooks
      await this.onTaskComplete(task, result)

      // Update metrics
      const duration = Date.now() - startTime
      this.updateMetrics(true, duration)

      this.state.completedTasks.push(task.id)
      this.setStatus('completed')

      this.emit('taskCompleted', { taskId: task.id, result, duration })

      return result

    } catch (error) {
      const duration = Date.now() - startTime
      const errorResult: TaskResult = {
        success: false,
        error: error instanceof Error ? error.message : String(error)
      }

      await this.onTaskFailed(task, errorResult)
      this.updateMetrics(false, duration)
      this.state.failedTasks.push(task.id)
      this.setStatus('failed')

      this.emit('taskFailed', { taskId: task.id, error: errorResult.error })

      return errorResult
    } finally {
      this.state.currentTaskId = undefined
    }
  }

  // Lifecycle hooks (can be overridden)
  protected async onTaskStart(task: Task): Promise<void> {
    this.emit('taskStarted', { taskId: task.id, task })
  }

  protected async onTaskComplete(task: Task, result: TaskResult): Promise<void> {
    this.emit('taskCompleted', { taskId: task.id, result })
  }

  protected async onTaskFailed(task: Task, result: TaskResult): Promise<void> {
    this.emit('taskFailed', { taskId: task.id, error: result.error })
  }

  // Metrics update
  private updateMetrics(success: boolean, duration: number): void {
    if (success) {
      this.state.metrics.tasksCompleted++
    } else {
      this.state.metrics.tasksFailed++
    }

    // Rolling average for execution time
    const currentAvg = this.state.metrics.averageExecutionTime
    const totalTasks = this.state.metrics.tasksCompleted + this.state.metrics.tasksFailed
    this.state.metrics.averageExecutionTime = 
      (currentAvg * (totalTasks - 1) + duration) / totalTasks
  }

  // Cleanup
  destroy(): void {
    this.removeAllListeners()
    this.tools.clear()
    this.messageQueue = []
  }
}

// Factory function to create agents
export type AgentConstructor = new (config: AgentConfig) => BaseAgent

export const agentRegistry: Map<AgentRole, AgentConstructor> = new Map()

export function registerAgent(role: AgentRole, constructor: AgentConstructor): void {
  agentRegistry.set(role, constructor)
}

export function createAgent(role: AgentRole, config: AgentConfig): BaseAgent {
  const constructor = agentRegistry.get(role)
  if (!constructor) {
    throw new Error(`No agent registered for role: ${role}`)
  }
  return new constructor(config)
}