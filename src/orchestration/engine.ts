/**
 * Orchestration Engine
 * Central coordination system for multi-agent workflows
 */

import { EventEmitter } from 'events'
import { v4 as uuid } from 'uuid'
import {
  AgentRole,
  Task,
  TaskResult,
  TaskContext,
  WorkflowDefinition,
  SystemEvent,
  AgentMessage
} from '../types'
import {
  BaseAgent,
  createAgent,
  registerAgent,
  OrchestratorAgent,
  ResearcherAgent,
  CoderAgent,
  ReviewerAgent,
  ExecutorAgent,
  HermesAgent
} from '../agents'

// Register all agent types
registerAgent('orchestrator', OrchestratorAgent)
registerAgent('researcher', ResearcherAgent)
registerAgent('coder', CoderAgent)
registerAgent('reviewer', ReviewerAgent)
registerAgent('executor', ExecutorAgent)
registerAgent('hermes', HermesAgent)

export interface OrchestratorConfig {
  maxConcurrentAgents: number
  maxQueueSize: number
  defaultTimeout: number
  enableRetry: boolean
  maxRetries: number
  /** When true, skips initializeDefaultAgents() in constructor — caller must call init() manually */
  deferInit?: boolean
}

export class OrchestrationEngine extends EventEmitter {
  private agents: Map<string, BaseAgent> = new Map()
  private taskQueue: Task[] = []
  private activeTasks: Map<string, Task> = new Map()
  private completedTasks: Map<string, Task> = new Map()
  private config: OrchestratorConfig
  private mainOrchestrator?: OrchestratorAgent
  private initialized = false

  constructor(config: Partial<OrchestratorConfig> = {}) {
    super()
    this.config = {
      maxConcurrentAgents: config.maxConcurrentAgents || 5,
      maxQueueSize: config.maxQueueSize || 100,
      defaultTimeout: config.defaultTimeout || 300000,
      enableRetry: config.enableRetry ?? true,
      maxRetries: config.maxRetries || 3,
      deferInit: config.deferInit ?? false
    }

    if (!this.config.deferInit) {
      this.initialized = true
      this.initializeDefaultAgents()
    }
  }

  /** Initialize default agents. Called automatically by constructor unless deferInit is true. */
  init(): void {
    if (this.initialized) {
      return
    }
    this.initialized = true
    this.initializeDefaultAgents()
  }

  private initializeDefaultAgents(): void {
    // Create and register the main orchestrator
    this.mainOrchestrator = new OrchestratorAgent({
      id: 'orchestrator-1',
      name: 'Main Orchestrator',
      role: 'orchestrator',
      capabilities: [{
        name: 'orchestration',
        description: 'Coordinates all agents and workflows',
        tools: ['task_planning', 'agent_coordination', 'error_recovery'],
        maxConcurrentTasks: 10
      }]
    }, this.config.maxConcurrentAgents)

    this.registerAgent(this.mainOrchestrator)

    // Create specialized agents
    const specializations: Array<{ role: AgentRole; name: string; count: number }> = [
      { role: 'researcher', name: 'Research Specialist', count: 2 },
      { role: 'coder', name: 'Code Specialist', count: 3 },
      { role: 'reviewer', name: 'Review Specialist', count: 2 },
      { role: 'executor', name: 'Execution Specialist', count: 2 },
      { role: 'hermes', name: 'Hermes Agent', count: 1 }
    ]

    for (const spec of specializations) {
      for (let i = 0; i < spec.count; i++) {
        const agent = createAgent(spec.role, {
          id: `${spec.role}-${i + 1}`,
          name: `${spec.name} ${i + 1}`,
          role: spec.role,
          capabilities: [{
            name: spec.role,
            description: `${spec.role} tasks`,
            tools: [],
            maxConcurrentTasks: 1
          }]
        })
        this.registerAgent(agent)
      }
    }

    // Register all agents with the orchestrator
    for (const [id, agent] of this.agents) {
      if (id !== 'orchestrator-1') {
        this.mainOrchestrator?.registerAgent(agent)
      }
    }
  }

  // Register an agent with the engine
  registerAgent(agent: BaseAgent): void {
    this.agents.set(agent.id, agent)
    
    // Forward agent events to the engine
    agent.on('taskCompleted', (data: { taskId: string; result: TaskResult }) => {
      this.handleTaskCompleted(data.taskId, data.result)
    })

    agent.on('taskFailed', (data: { taskId: string; error: string }) => {
      this.handleTaskFailed(data.taskId, data.error)
    })

    this.emit('agent:spawned', { agentId: agent.id, role: agent.role })
  }

  // Submit a task for execution
  async submitTask(
    description: string,
    context: TaskContext,
    options?: {
      priority?: 'low' | 'medium' | 'high' | 'critical'
      agentRole?: AgentRole
      timeout?: number
    }
  ): Promise<Task> {
    const task: Task = {
      id: `task-${uuid()}`,
      type: 'generic',
      description,
      priority: options?.priority || 'medium',
      status: 'pending',
      dependencies: [],
      context,
      createdAt: new Date(),
      updatedAt: new Date(),
      timeout: options?.timeout || this.config.defaultTimeout
    }

    if (this.taskQueue.length >= this.config.maxQueueSize) {
      throw new Error('Task queue is full')
    }

    this.taskQueue.push(task)
    this.emit('task:submitted', { taskId: task.id })

    // Start processing if we have capacity
    this.processQueue()

    return task
  }

  // Submit a workflow for execution
  async submitWorkflow(workflow: WorkflowDefinition): Promise<string> {
    const workflowId = `workflow-${uuid()}`
    
    // Create tasks from workflow tasks
    for (const wfTask of workflow.tasks) {
      const task: Task = {
        id: wfTask.id,
        type: wfTask.type,
        description: wfTask.instruction,
        priority: 'medium',
        status: 'pending',
        dependencies: wfTask.dependencies.map(d => ({ taskId: d, type: 'depends_on' })),
        context: {
          userRequest: wfTask.instruction,
          sessionId: workflowId,
          variables: { workflowId, workflowTasks: workflow.tasks }
        },
        createdAt: new Date(),
        updatedAt: new Date()
      }

      this.taskQueue.push(task)
    }

    this.emit('workflow:started', { workflowId, taskCount: workflow.tasks.length })
    this.processQueue()

    return workflowId
  }

  // Process the task queue
  private async processQueue(): Promise<void> {
    const activeCount = Array.from(this.agents.values()).filter(
      a => a.getStatus() === 'working'
    ).length

    if (activeCount >= this.config.maxConcurrentAgents) {
      return // Max capacity reached
    }

    // Find next task that can be executed (dependencies met)
    const availableTask = this.taskQueue.find(task => {
      if (task.status !== 'pending') return false
      
      // Check dependencies
      for (const dep of task.dependencies) {
        const depTask = this.completedTasks.get(dep.taskId)
        if (!depTask || depTask.result?.success === false) {
          return false
        }
      }
      return true
    })

    if (!availableTask) return

    // Find an available agent
    const agent = this.selectAgent(availableTask)
    if (!agent) return

    // Assign and execute
    await this.executeTaskWithAgent(availableTask, agent)
  }

  // Select the best agent for a task
  private selectAgent(task: Task): BaseAgent | null {
    // First try the main orchestrator for complex tasks
    if (this.mainOrchestrator && this.mainOrchestrator.getStatus() === 'idle') {
      return this.mainOrchestrator
    }

    // Find a specialized agent based on task description
    const descriptionLower = task.description.toLowerCase()
    let targetRole: AgentRole | null = null

    if (descriptionLower.includes('research') || descriptionLower.includes('find') || descriptionLower.includes('analyze')) {
      targetRole = 'researcher'
    } else if (descriptionLower.includes('build') || descriptionLower.includes('create') || descriptionLower.includes('implement')) {
      targetRole = 'coder'
    } else if (descriptionLower.includes('review') || descriptionLower.includes('check') || descriptionLower.includes('validate')) {
      targetRole = 'reviewer'
    } else if (descriptionLower.includes('run') || descriptionLower.includes('execute') || descriptionLower.includes('deploy')) {
      targetRole = 'executor'
    }

    // Find available agent with matching role
    if (targetRole) {
      for (const [, agent] of this.agents) {
        if (agent.role === targetRole && agent.getStatus() === 'idle') {
          return agent
        }
      }
    }

    // Fall back to any idle agent
    for (const [, agent] of this.agents) {
      if (agent.getStatus() === 'idle') {
        return agent
      }
    }

    return null
  }

  // Execute a task with a specific agent
  private async executeTaskWithAgent(task: Task, agent: BaseAgent): Promise<void> {
    // Update task status
    task.status = 'assigned'
    task.assignedAgent = agent.id
    task.startedAt = new Date()
    this.activeTasks.set(task.id, task)

    this.emit('agent:task_assigned', { taskId: task.id, agentId: agent.id })

    try {
      const result = await agent.runTask(task)
      this.handleTaskCompleted(task.id, result)
    } catch (error) {
      this.handleTaskFailed(task.id, error instanceof Error ? error.message : String(error))
    }
  }

  // Handle task completion
  private handleTaskCompleted(taskId: string, result: TaskResult): void {
    const task = this.activeTasks.get(taskId)
    if (task) {
      task.status = result.success ? 'completed' : 'failed'
      task.completedAt = new Date()
      task.result = result
      this.completedTasks.set(taskId, task)
      this.activeTasks.delete(taskId)

      this.emit('agent:task_completed', { taskId, result })
    }

    // Continue processing queue
    this.processQueue()
  }

  // Handle task failure
  private handleTaskFailed(taskId: string, error: string): void {
    const task = this.activeTasks.get(taskId)
    if (task) {
      task.status = 'failed'
      task.completedAt = new Date()
      task.result = { success: false, error }
      this.completedTasks.set(taskId, task)
      this.activeTasks.delete(taskId)

      this.emit('agent:error', { taskId, error })

      // Retry logic
      if (this.config.enableRetry && task.result.error) {
        const retryCount = (task.context.variables?.retryCount as number) || 0
        if (retryCount < this.config.maxRetries) {
          // Re-queue for retry
          task.status = 'pending'
          task.context.variables = { ...task.context.variables, retryCount: retryCount + 1 }
          this.taskQueue.push(task)
        }
      }
    }

    // Continue processing queue
    this.processQueue()
  }

  // Get system status
  getStatus(): {
    queueLength: number
    activeTasks: number
    completedTasks: number
    agents: Array<{ id: string; role: AgentRole; status: string }>
  } {
    return {
      queueLength: this.taskQueue.length,
      activeTasks: this.activeTasks.size,
      completedTasks: this.completedTasks.size,
      agents: Array.from(this.agents.values()).map(a => ({
        id: a.id,
        role: a.role,
        status: a.getStatus()
      }))
    }
  }

  // Get task by ID
  getTask(taskId: string): Task | undefined {
    return (
      this.activeTasks.get(taskId) ||
      this.completedTasks.get(taskId) ||
      this.taskQueue.find(t => t.id === taskId)
    )
  }

  // Get all tasks
  getAllTasks(): Task[] {
    return [
      ...this.taskQueue,
      ...Array.from(this.activeTasks.values()),
      ...Array.from(this.completedTasks.values())
    ]
  }

  // Get agent by ID
  getAgent(agentId: string): BaseAgent | undefined {
    return this.agents.get(agentId)
  }

  // Get all agents
  getAllAgents(): BaseAgent[] {
    return Array.from(this.agents.values())
  }

  // Destroy all agents and clean up resources
  destroy(): void {
    for (const [, agent] of this.agents) {
      agent.destroy()
    }
    this.agents.clear()
    this.taskQueue = []
    this.activeTasks.clear()
    this.completedTasks.clear()
    this.removeAllListeners()
  }

  // Send message to agent
  sendMessage(message: AgentMessage): void {
    const agent = this.agents.get(message.recipientId || '')
    if (agent) {
      agent.receiveMessage(message)
    }
  }

  // Broadcast message to all agents
  broadcast(message: Omit<AgentMessage, 'recipientId'>): void {
    const fullMessage = { ...message, recipientId: undefined }
    for (const [, agent] of this.agents) {
      agent.receiveMessage(fullMessage as AgentMessage)
    }
  }

  // Event logging
  logEvent(event: SystemEvent): void {
    this.emit(event.type, event)
  }
}

// Singleton instance for easy access
let engineInstance: OrchestrationEngine | null = null

export function getEngine(): OrchestrationEngine {
  if (!engineInstance) {
    engineInstance = new OrchestrationEngine()
  }
  return engineInstance
}

export function createEngine(config?: Partial<OrchestratorConfig>): OrchestrationEngine {
  engineInstance = new OrchestrationEngine(config)
  return engineInstance
}