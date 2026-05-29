/**
 * Orchestrator Agent
 * Central supervisor that coordinates all other agents
 */

import { v4 as uuid } from 'uuid'
import { BaseAgent } from './base-agent'
import { 
  AgentConfig, 
  Task, 
  TaskResult, 
  TaskContext,
  ExecutionPlan,
  AgentMessage
} from '../types'

export class OrchestratorAgent extends BaseAgent {
  private agentPool: Map<string, BaseAgent> = new Map()
  private maxConcurrentAgents: number

  constructor(config: AgentConfig, maxConcurrentAgents = 5) {
    super(config)
    this.maxConcurrentAgents = maxConcurrentAgents
  }

  getCapabilities(): string[] {
    return [
      'task_planning',
      'task_decomposition',
      'agent_coordination',
      'workflow_orchestration',
      'resource_allocation',
      'error_recovery'
    ]
  }

  // Main entry point for handling requests
  async processRequest(userRequest: string, context: TaskContext): Promise<TaskResult> {
    this.setStatus('working')
    
    try {
      // Step 1: Analyze and decompose the request
      const plan = await this.createExecutionPlan(userRequest, context)
      
      // Step 2: Execute the plan with agent coordination
      const result = await this.executePlan(plan, context)

      this.setStatus('completed')
      return { success: true, output: result }

    } catch (error) {
      this.setStatus('failed')
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error)
      }
    }
  }

  // Create a decomposition plan for the request
  async createExecutionPlan(userRequest: string, context: TaskContext): Promise<ExecutionPlan[]> {
    // Use LLM or rule-based decomposition
    const decomposedTasks = await this.decomposeTask(userRequest, context)
    
    const plans: ExecutionPlan[] = decomposedTasks.map((task, index) => ({
      id: `plan-${uuid()}`,
      taskId: `task-${index}`,
      steps: [
        {
          id: `step-${index}-1`,
          instruction: task.instruction,
          expectedOutput: task.expectedOutput
        }
      ],
      estimatedDuration: task.estimatedDuration || 30000
    }))

    this.emit('planCreated', { plans, taskCount: plans.length })
    return plans
  }

  // Decompose a complex task into subtasks
  private async decomposeTask(
    userRequest: string, 
    context: TaskContext
  ): Promise<Array<{
    instruction: string
    agentRole: string
    expectedOutput?: string
    estimatedDuration?: number
  }>> {
    // Intelligent task decomposition
    const tasks: Array<{
      instruction: string
      agentRole: string
      expectedOutput?: string
      estimatedDuration?: number
    }> = []

    const requestLower = userRequest.toLowerCase()

    // Research phase
    if (requestLower.includes('research') || requestLower.includes('find') || requestLower.includes('analyze')) {
      tasks.push({
        instruction: `Research and gather information about: ${userRequest}`,
        agentRole: 'researcher',
        expectedOutput: 'comprehensive research report',
        estimatedDuration: 60000
      })
    }

    // Coding phase
    if (requestLower.includes('build') || requestLower.includes('create') || requestLower.includes('implement') || requestLower.includes('write')) {
      tasks.push({
        instruction: `Implement the solution based on research findings for: ${userRequest}`,
        agentRole: 'coder',
        expectedOutput: 'working code implementation',
        estimatedDuration: 120000
      })
    }

    // Review phase
    if (requestLower.includes('review') || requestLower.includes('check') || requestLower.includes('validate')) {
      tasks.push({
        instruction: `Review and validate the implementation for: ${userRequest}`,
        agentRole: 'reviewer',
        expectedOutput: 'review report with findings',
        estimatedDuration: 45000
      })
    }

    // Execution phase
    if (requestLower.includes('run') || requestLower.includes('execute') || requestLower.includes('test') || requestLower.includes('deploy')) {
      tasks.push({
        instruction: `Execute and verify the solution for: ${userRequest}`,
        agentRole: 'executor',
        expectedOutput: 'execution results and verification',
        estimatedDuration: 60000
      })
    }

    // Default: if no specific action detected, do full pipeline
    if (tasks.length === 0) {
      tasks.push(
        {
          instruction: `Research and analyze: ${userRequest}`,
          agentRole: 'researcher',
          estimatedDuration: 60000
        },
        {
          instruction: `Implement solution for: ${userRequest}`,
          agentRole: 'coder',
          estimatedDuration: 120000
        },
        {
          instruction: `Review implementation for: ${userRequest}`,
          agentRole: 'reviewer',
          estimatedDuration: 45000
        }
      )
    }

    return tasks
  }

  // Execute the plan with agent coordination
  private async executePlan(plans: ExecutionPlan[], context: TaskContext): Promise<{
    completedPlans: ExecutionPlan[]
    results: TaskResult[]
  }> {
    const completedPlans: ExecutionPlan[] = []
    const results: TaskResult[] = []

    for (const plan of plans) {
      // Find available agent for the task type
      const agent = this.selectAgentForTask(plan)
      
      if (!agent) {
        results.push({
          success: false,
          error: `No available agent for task ${plan.taskId}`
        })
        continue
      }

      // Create task and execute
      const task: Task = {
        id: plan.taskId,
        type: 'orchestrated',
        description: plan.steps.map(s => s.instruction).join(' → '),
        priority: 'medium',
        status: 'in_progress',
        dependencies: [],
        context: { ...context, variables: { ...context.variables, plan } },
        createdAt: new Date(),
        updatedAt: new Date(),
        startedAt: new Date()
      }

      this.emit('taskDelegated', { taskId: task.id, agentId: agent.id })

      const result = await agent.runTask(task)
      results.push(result)

      if (result.success) {
        completedPlans.push(plan)
      }
    }

    return { completedPlans, results }
  }

  // Select the best agent for a task
  private selectAgentForTask(plan: ExecutionPlan): BaseAgent | null {
    // Simple round-robin with role matching
    const taskType = plan.steps[0]?.instruction?.toLowerCase() || ''
    
    let targetRole = 'coder'
    if (taskType.includes('research') || taskType.includes('analyze')) {
      targetRole = 'researcher'
    } else if (taskType.includes('review') || taskType.includes('check')) {
      targetRole = 'reviewer'
    } else if (taskType.includes('execute') || taskType.includes('run') || taskType.includes('deploy')) {
      targetRole = 'executor'
    }

    // Find an available agent with matching role
    for (const [, agent] of this.agentPool) {
      if (agent.role === targetRole && agent.getStatus() === 'idle') {
        return agent
      }
    }

    // If no specific role available, return any idle agent
    for (const [, agent] of this.agentPool) {
      if (agent.getStatus() === 'idle') {
        return agent
      }
    }

    return null
  }

  // Register agents in the pool
  registerAgent(agent: BaseAgent): void {
    this.agentPool.set(agent.id, agent)
    
    // Forward events
    agent.on('taskCompleted', (data: { taskId: string; result: TaskResult }) => {
      this.emit('agentTaskCompleted', { agentId: agent.id, ...data })
    })

    agent.on('taskFailed', (data: { taskId: string; error: string }) => {
      this.emit('agentTaskFailed', { agentId: agent.id, ...data })
    })
  }

  // Message handling for agent communication
  protected async processMessage(message: AgentMessage): Promise<void> {
    switch (message.type) {
      case 'task':
        // Handle task delegation from other agents
        if (message.payload && typeof message.payload === 'object') {
          const taskData = message.payload as { instruction: string; context: TaskContext }
          const result = await this.processRequest(taskData.instruction, taskData.context)
          
          this.sendMessage({
            id: uuid(),
            type: 'result',
            senderId: this.id,
            recipientId: message.senderId,
            taskId: message.taskId,
            correlationId: message.correlationId,
            payload: result,
            timestamp: new Date(),
            priority: 'normal'
          })
        }
        break

      case 'status':
        // Handle status queries
        this.sendMessage({
          id: uuid(),
          type: 'status',
          senderId: this.id,
          recipientId: message.senderId,
          correlationId: message.correlationId,
          payload: { 
            status: this.getStatus(),
            activeAgents: this.agentPool.size
          },
          timestamp: new Date(),
          priority: 'normal'
        })
        break
    }
  }

  // Override executeTask for the orchestrator's main workflow
  async executeTask(task: Task): Promise<TaskResult> {
    const context = task.context
    return this.processRequest(context.userRequest, context)
  }

  // Get orchestrator statistics
  getStats(): {
    activeAgents: number
    completedTasks: number
    failedTasks: number
  } {
    return {
      activeAgents: this.agentPool.size,
      completedTasks: this.state.metrics.tasksCompleted,
      failedTasks: this.state.metrics.tasksFailed
    }
  }
}