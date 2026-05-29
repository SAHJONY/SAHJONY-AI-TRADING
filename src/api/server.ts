/**
 * REST API Server for Agent Workforce
 * Programmatic access to the multi-agent orchestration system
 */

import express, { Request, Response, NextFunction } from 'express'
import cors from 'cors'
import { v4 as uuid } from 'uuid'
import { createEngine, OrchestrationEngine } from '../orchestration/engine'
import {
  CreateAgentRequest,
  CreateWorkflowRequest,
  ExecuteTaskRequest,
  TaskContext
} from '../types'

// Import AI Receptionist Dashboard
import { setupReceptionistDashboard } from '../receptionist/dashboard'

// Import Personal AI Agent Dashboard
import { setupPersonalAgentDashboard } from '../personal-agent/dashboard'

// Import Personal AI Receptionist (Unified Personal Assistant + Receptionist)
import { setupPersonalReceptionistDashboard } from '../personal-receptionist/dashboard'

// Import AI Receptionist Demo Page
import { setupReceptionistDemo } from '../web/receptionist-demo'

// Import Hermes Agent
import { HermesAgent } from '../agents/hermes-agent'

// Import Hermes Dashboard
import { setupHermesDashboard } from '../web/hermes-dashboard'

// Import Hermes Cinematic Dashboard
import { setupHermesCinematic } from '../web/hermes-cinematic'

// Import Workspace Dashboard
import { setupWorkspaceDashboard } from '../web/workspace-dashboard'

// Import Workspace Routes
import workspaceRoutes, { setWorkspaceStore } from './workspace-routes'
import { workspaceStore } from '../shared/workspace-store'

// Connect workspace store to routes
setWorkspaceStore(workspaceStore)

// Import WorkforceBridge from frontdesk-agents
// Note: In production, this would be a proper module import
// For now, we'll define the interface and create a mock integration
interface WorkforceBridgeStatus {
  queueLength: number
  activeTasks: number
  completedTasks: number
  tools: string[]
}

interface WorkforceTask {
  id: string
  type: string
  description: string
  priority: string
  status: string
  context: {
    industry: string
    visitorId?: string
    visitorName?: string
    visitorLanguage: string
    purpose: string
    sentiment: string
    urgency: string
    sessionId: string
  }
  result?: {
    success: boolean
    output?: unknown
    error?: string
    agentUsed: string
    duration: number
  }
  createdAt: Date
  assignedAgent?: string
}

// Simulated workforce bridge for demonstration
// In production, this would import from frontdesk-agents
const simulatedWorkforceBridge = {
  tasks: new Map<string, WorkforceTask>(),
  taskQueue: [] as WorkforceTask[],
  activeTasks: new Map<string, WorkforceTask>(),
  completedTasks: new Map<string, WorkforceTask>(),
  tools: ['book_appointment', 'faq_lookup', 'register_visitor', 'escalate_to_human', 'translate_response'],
  
  getStatus(): WorkforceBridgeStatus {
    return {
      queueLength: this.taskQueue.length,
      activeTasks: this.activeTasks.size,
      completedTasks: this.completedTasks.size,
      tools: this.tools
    }
  },
  
  getTask(taskId: string): WorkforceTask | undefined {
    return this.tasks.get(taskId)
  },
  
  getAllTasks(): WorkforceTask[] {
    return Array.from(this.tasks.values())
  },
  
  submitTask(context: any): WorkforceTask {
    const task: WorkforceTask = {
      id: `wf-task-${uuid()}`,
      type: this.determineTaskType(context),
      description: `[${context.industry}] ${context.visitorName || 'Visitor'} needs: ${context.purpose}`,
      priority: this.determinePriority(context),
      status: 'pending',
      context: {
        industry: context.industry || 'corporate',
        visitorId: context.visitorId,
        visitorName: context.visitorName,
        visitorLanguage: context.visitorLanguage || 'English',
        purpose: context.purpose,
        sentiment: context.sentiment || 'neutral',
        urgency: context.urgency || 'medium',
        sessionId: context.sessionId || `session-${uuid()}`
      },
      createdAt: new Date()
    }
    
    this.tasks.set(task.id, task)
    this.taskQueue.push(task)
    
    // Simulate immediate processing
    this.processTask(task)
    
    return task
  },
  
  determineTaskType(context: any): string {
    const purpose = (context.purpose || '').toLowerCase()
    if (purpose.includes('appointment') || purpose.includes('schedule')) return 'scheduling'
    if (purpose.includes('speak') || purpose.includes('human') || context.sentiment === 'frustrated') return 'escalation'
    if (purpose.includes('info') || purpose.includes('faq')) return 'information'
    return 'receptionist'
  },
  
  determinePriority(context: any): string {
    if (context.urgency === 'emergency' || context.urgency === 'high') return 'critical'
    if (context.sentiment === 'frustrated') return 'high'
    return 'medium'
  },
  
  processTask(task: WorkforceTask): void {
    task.status = 'in_progress'
    this.activeTasks.set(task.id, task)
    
    // Simulate task completion after a short delay
    setTimeout(() => {
      task.status = 'completed'
      task.result = {
        success: true,
        output: { message: 'Task processed successfully', agentUsed: this.getAgentForType(task.type) },
        agentUsed: this.getAgentForType(task.type),
        duration: Math.floor(Math.random() * 500) + 100
      }
      this.completedTasks.set(task.id, task)
      this.activeTasks.delete(task.id)
    }, 500)
  },
  
  getAgentForType(type: string): string {
    const agents: Record<string, string> = {
      scheduling: 'CHRONOS',
      information: 'WIKI',
      escalation: 'CONNECT',
      receptionist: 'ARIA'
    }
    return agents[type] || 'ARIA'
  }
}

// Re-export workforce bridge for use in endpoints
const workforceBridge = simulatedWorkforceBridge

const app = express()
const PORT = parseInt(String(process.env.PORT || '3001'), 10)

app.use(cors())
app.use(express.json())

let engine: OrchestrationEngine

app.use((req: Request, _res: Response, next: NextFunction) => {
  console.log(`[API] ${req.method} ${req.path}`)
  next()
})

app.get('/health', (_req: Request, res: Response) => {
  res.json({ status: 'healthy', timestamp: new Date().toISOString() })
})

app.get('/api/agents', (_req: Request, res: Response) => {
  const agents = engine.getAllAgents().map(a => ({
    id: a.id,
    name: a.name,
    role: a.role,
    status: a.getStatus(),
    capabilities: a.getCapabilities()
  }))
  res.json({ agents })
})

app.get('/api/agents/:id', (req: Request, res: Response) => {
  const agent = engine.getAgent(req.params.id)
  if (!agent) {
    return res.status(404).json({ error: 'Agent not found' })
  }
  res.json({
    id: agent.id,
    name: agent.name,
    role: agent.role,
    status: agent.getStatus(),
    capabilities: agent.getCapabilities(),
    state: agent.getState()
  })
})

app.post('/api/agents', (req: Request, res: Response) => {
  const { name, role } = req.body as CreateAgentRequest
  
  if (!name || !role) {
    return res.status(400).json({ error: 'Name and role are required' })
  }

  try {
    const agent = engine.getAgent(name.toLowerCase().replace(/\\s+/g, '-'))
    if (agent) {
      return res.status(409).json({ error: 'Agent with this name already exists' })
    }
    res.status(501).json({ error: 'Dynamic agent creation not yet implemented - use default agents' })
  } catch (error) {
    res.status(500).json({ error: error instanceof Error ? error.message : 'Failed to create agent' })
  }
})

app.post('/api/tasks', async (req: Request, res: Response) => {
  const { description, priority, context, agentRole } = req.body as ExecuteTaskRequest

  if (!description) {
    return res.status(400).json({ error: 'Description is required' })
  }

  try {
    const taskContext: TaskContext = {
      userRequest: description,
      sessionId: `api-${uuid()}`,
      variables: context?.variables || {},
      ...context
    }

    const task = await engine.submitTask(description, taskContext, {
      priority: priority || 'medium',
      agentRole
    })

    res.status(201).json({
      taskId: task.id,
      status: task.status,
      message: 'Task submitted successfully'
    })

  } catch (error) {
    res.status(500).json({ 
      error: error instanceof Error ? error.message : 'Failed to submit task' 
    })
  }
})

app.get('/api/tasks', (req: Request, res: Response) => {
  const tasks = engine.getAllTasks()
  const status = req.query.status as string | undefined
  
  const filtered = status 
    ? tasks.filter(t => t.status === status)
    : tasks

  res.json({ 
    tasks: filtered,
    total: filtered.length 
  })
})

app.get('/api/tasks/:id', (req: Request, res: Response) => {
  const task = engine.getTask(req.params.id)
  if (!task) {
    return res.status(404).json({ error: 'Task not found' })
  }
  res.json(task)
})

app.delete('/api/tasks/:id', (_req: Request, res: Response) => {
  res.status(501).json({ error: 'Task cancellation not yet implemented' })
})

app.post('/api/workflows', async (req: Request, res: Response) => {
  const { name, description, tasks, maxParallelAgents } = req.body as CreateWorkflowRequest

  if (!name || !tasks || tasks.length === 0) {
    return res.status(400).json({ error: 'Name and tasks are required' })
  }

  try {
    const workflowId = await engine.submitWorkflow({
      id: `wf-${uuid()}`,
      name,
      description: description || '',
      tasks: tasks.map((t, i) => ({
        id: `wf-task-${uuid()}`,
        type: t.type || 'generic',
        agentRole: t.agentRole,
        instruction: t.instruction,
        dependencies: t.dependencies || []
      })),
      agents: [],
      maxParallelAgents: maxParallelAgents || 5
    })

    res.status(201).json({
      workflowId,
      message: 'Workflow submitted successfully'
    })

  } catch (error) {
    res.status(500).json({ 
      error: error instanceof Error ? error.message : 'Failed to submit workflow' 
    })
  }
})

app.get('/api/workflows/:id', (req: Request, res: Response) => {
  const tasks = engine.getAllTasks()
  const workflowTasks = tasks.filter(t => 
    t.context.sessionId?.includes(req.params.id)
  )

  if (workflowTasks.length === 0) {
    return res.status(404).json({ error: 'Workflow not found' })
  }

  const completed = workflowTasks.filter(t => t.status === 'completed').length
  const failed = workflowTasks.filter(t => t.status === 'failed').length

  res.json({
    workflowId: req.params.id,
    totalTasks: workflowTasks.length,
    completed,
    failed,
    tasks: workflowTasks
  })
})

app.get('/api/status', (_req: Request, res: Response) => {
  const status = engine.getStatus()
  res.json({
    ...status,
    timestamp: new Date().toISOString()
  })
})

app.get('/api/metrics', (_req: Request, res: Response) => {
  const agents = engine.getAllAgents()
  const tasks = engine.getAllTasks()

  const completedTasks = tasks.filter(t => t.status === 'completed')
  const failedTasks = tasks.filter(t => t.status === 'failed')

  res.json({
    agents: {
      total: agents.length,
      byRole: agents.reduce((acc, a) => {
        acc[a.role] = (acc[a.role] || 0) + 1
        return acc
      }, {} as Record<string, number>),
      byStatus: agents.reduce((acc, a) => {
        acc[a.getStatus()] = (acc[a.getStatus()] || 0) + 1
        return acc
      }, {} as Record<string, number>)
    },
    tasks: {
      total: tasks.length,
      pending: tasks.filter(t => t.status === 'pending').length,
      active: tasks.filter(t => t.status === 'in_progress').length,
      completed: completedTasks.length,
      failed: failedTasks.length
    },
    performance: {
      successRate: tasks.length > 0 
        ? (completedTasks.length / (completedTasks.length + failedTasks.length) * 100).toFixed(2) + '%'
        : 'N/A'
    }
  })
})

// ============================================================================
// WORKFORCE BRIDGE METRICS & TASK STATUS ENDPOINTS
// ============================================================================

app.get('/api/workforce/status', (_req: Request, res: Response) => {
  const status = workforceBridge.getStatus()
  res.json({
    ...status,
    timestamp: new Date().toISOString()
  })
})

app.get('/api/workforce/metrics', (_req: Request, res: Response) => {
  const allTasks = workforceBridge.getAllTasks()
  const completedTasks = allTasks.filter(t => t.status === 'completed')
  const failedTasks = allTasks.filter(t => t.status === 'failed')
  const activeTasks = allTasks.filter(t => t.status === 'in_progress')
  const pendingTasks = allTasks.filter(t => t.status === 'pending')

  // Calculate agent performance
  const agentMetrics: Record<string, {
    completed: number
    failed: number
    averageDuration: number
    totalTasks: number
  }> = {}
  
  completedTasks.forEach(task => {
    const agent = task.result?.agentUsed || 'UNKNOWN'
    if (!agentMetrics[agent]) {
      agentMetrics[agent] = { completed: 0, failed: 0, averageDuration: 0, totalTasks: 0 }
    }
    agentMetrics[agent].completed++
    agentMetrics[agent].totalTasks++
    if (task.result?.duration) {
      agentMetrics[agent].averageDuration = 
        (agentMetrics[agent].averageDuration * (agentMetrics[agent].completed - 1) + task.result.duration) 
        / agentMetrics[agent].completed
    }
  })

  // Task type distribution
  const taskTypeDistribution = allTasks.reduce((acc, task) => {
    acc[task.type] = (acc[task.type] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  // Priority distribution
  const priorityDistribution = allTasks.reduce((acc, task) => {
    acc[task.priority] = (acc[task.priority] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  // Industry distribution
  const industryDistribution = allTasks.reduce((acc, task) => {
    const industry = task.context?.industry || 'unknown'
    acc[industry] = (acc[industry] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  res.json({
    summary: {
      totalTasks: allTasks.length,
      pending: pendingTasks.length,
      active: activeTasks.length,
      completed: completedTasks.length,
      failed: failedTasks.length,
      successRate: completedTasks.length + failedTasks.length > 0
        ? ((completedTasks.length / (completedTasks.length + failedTasks.length)) * 100).toFixed(2) + '%'
        : 'N/A'
    },
    agents: agentMetrics,
    taskTypes: taskTypeDistribution,
    priorities: priorityDistribution,
    industries: industryDistribution,
    timestamp: new Date().toISOString()
  })
})

app.get('/api/workforce/tasks', (req: Request, res: Response) => {
  const allTasks = workforceBridge.getAllTasks()
  const status = req.query.status as string | undefined
  const type = req.query.type as string | undefined
  const industry = req.query.industry as string | undefined

  let filtered = allTasks

  if (status) {
    filtered = filtered.filter(t => t.status === status)
  }
  if (type) {
    filtered = filtered.filter(t => t.type === type)
  }
  if (industry) {
    filtered = filtered.filter(t => t.context?.industry === industry)
  }

  res.json({
    tasks: filtered,
    total: filtered.length,
    filters: { status, type, industry }
  })
})

app.get('/api/workforce/tasks/:id', (req: Request, res: Response) => {
  const task = workforceBridge.getTask(req.params.id)
  if (!task) {
    return res.status(404).json({ error: 'Task not found' })
  }
  res.json(task)
})

app.post('/api/workforce/tasks', (req: Request, res: Response) => {
  const { industry, visitorName, visitorLanguage, purpose, sentiment, urgency, visitorId } = req.body

  if (!purpose) {
    return res.status(400).json({ error: 'Purpose is required' })
  }

  try {
    const task = workforceBridge.submitTask({
      industry: industry || 'corporate',
      visitorName: visitorName || 'Anonymous Visitor',
      visitorLanguage: visitorLanguage || 'English',
      purpose,
      sentiment: sentiment || 'neutral',
      urgency: urgency || 'medium',
      visitorId,
      sessionId: `api-${uuid()}`,
      variables: {}
    })

    res.status(201).json({
      taskId: task.id,
      type: task.type,
      priority: task.priority,
      status: task.status,
      description: task.description,
      message: 'Workforce task submitted successfully'
    })
  } catch (error) {
    res.status(500).json({
      error: error instanceof Error ? error.message : 'Failed to submit workforce task'
    })
  }
})

app.get('/api/workforce/agents', (_req: Request, res: Response) => {
  // Return receptionist agent status
  const agents = [
    { id: 'aria-voice-1', name: 'ARIA', role: 'voice_receptionist', type: 'receptionist' },
    { id: 'scheduler-1', name: 'CHRONOS', role: 'scheduling', type: 'scheduling' },
    { id: 'knowledge-1', name: 'WIKI', role: 'information', type: 'information' },
    { id: 'escalation-1', name: 'CONNECT', role: 'escalation', type: 'escalation' }
  ]
  
  const allTasks = workforceBridge.getAllTasks()
  
  const agentsWithMetrics = agents.map(agent => {
    const agentTasks = allTasks.filter(t => 
      t.result?.agentUsed?.toLowerCase().includes(agent.name.toLowerCase())
    )
    const completed = agentTasks.filter(t => t.status === 'completed').length
    const failed = agentTasks.filter(t => t.status === 'failed').length
    const active = agentTasks.filter(t => t.status === 'in_progress').length
    
    return {
      ...agent,
      status: active > 0 ? 'working' : 'idle',
      metrics: {
        totalTasks: agentTasks.length,
        completed,
        failed,
        active,
        successRate: completed + failed > 0 
          ? ((completed / (completed + failed)) * 100).toFixed(2) + '%' 
          : 'N/A'
      }
    }
  })

  res.json({ agents: agentsWithMetrics })
})

// ============================================================================
// HERMES AGENT ENDPOINTS
// ============================================================================

// Hermes instance management
let hermesAgentInstance: HermesAgent | null = null

function getHermesAgent(): HermesAgent {
  if (!hermesAgentInstance) {
    hermesAgentInstance = new HermesAgent({
      id: 'hermes-1',
      name: 'Hermes',
      role: 'hermes',
      capabilities: [{
        name: 'ai_assistant',
        description: 'Self-improving AI agent from Nous Research with memory and skills',
        tools: [],
        maxConcurrentTasks: 3
      }]
    })
  }
  return hermesAgentInstance
}

app.get('/api/hermes/status', (_req: Request, res: Response) => {
  const agent = getHermesAgent()
  res.json({
    id: agent.id,
    name: agent.name,
    role: agent.role,
    status: agent.getStatus(),
    capabilities: agent.getCapabilities(),
    hermesStatus: agent.getHermesStatus()
  })
})

app.post('/api/hermes/chat', async (req: Request, res: Response) => {
  const { message } = req.body
  if (!message) return res.status(400).json({ error: 'Message is required' })
  
  try {
    const agent = getHermesAgent()
    const response = await agent.chat(message)
    res.json({
      response,
      agent: 'Hermes',
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    res.status(500).json({ 
      error: error instanceof Error ? error.message : 'Hermes request failed',
      agent: 'Hermes'
    })
  }
})

app.post('/api/hermes/skill', async (req: Request, res: Response) => {
  const { skillName, params } = req.body
  if (!skillName) return res.status(400).json({ error: 'Skill name is required' })
  
  try {
    const agent = getHermesAgent()
    const result = await agent.executeSkill(skillName, params)
    res.json({
      result,
      agent: 'Hermes',
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    res.status(500).json({ 
      error: error instanceof Error ? error.message : 'Skill execution failed',
      agent: 'Hermes'
    })
  }
})

app.post('/api/hermes/task', async (req: Request, res: Response) => {
  const { instruction, context } = req.body
  if (!instruction) return res.status(400).json({ error: 'Instruction is required' })
  
  try {
    const agent = getHermesAgent()
    const taskContext = context || {
      userRequest: instruction,
      sessionId: `hermes-${uuid()}`,
      variables: {}
    }
    
    const result = await agent.executeTask({
      id: `hermes-task-${uuid()}`,
      type: 'hermes-task',
      description: instruction,
      priority: 'medium',
      status: 'pending',
      dependencies: [],
      context: taskContext as any,
      createdAt: new Date(),
      updatedAt: new Date()
    })
    
    res.json({
      taskId: `hermes-task-${uuid()}`,
      result,
      agent: 'Hermes',
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    res.status(500).json({ 
      error: error instanceof Error ? error.message : 'Task execution failed',
      agent: 'Hermes'
    })
  }
})

app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  console.error('[API Error]', err)
  res.status(500).json({ error: 'Internal server error' })
})// Initialize engine for both local and serverless
engine = createEngine({
  maxConcurrentAgents: 5,
  maxQueueSize: 100,
  defaultTimeout: 300000,
  enableRetry: true,
  maxRetries: 3
})

// Setup all dashboards (works for both local and serverless)
setupReceptionistDashboard(app)
setupPersonalAgentDashboard(app)
setupPersonalReceptionistDashboard(app)
setupReceptionistDemo(app)
setupHermesDashboard(app)
setupHermesCinematic(app)
setupWorkspaceDashboard(app)

// Workspace API routes
app.use('/api/workspace', workspaceRoutes)

// For local development only
if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`\n========================================`)
    console.log(`   AGENT WORKFORCE API`)
    console.log(`   REST API Server`)
    console.log(`========================================`)
    console.log(`\nServer running on http://localhost:${PORT}`)
    console.log(`\nEndpoints:`)
    console.log(`  GET    /health           - Health check`)
    console.log(`  GET    /api/agents        - List all agents`)
    console.log(`  GET    /api/agents/:id    - Get agent details`)
    console.log(`  POST   /api/agents        - Create agent`)
    console.log(`  GET    /api/tasks         - List all tasks`)
    console.log(`  POST   /api/tasks         - Submit new task`)
    console.log(`  GET    /api/tasks/:id     - Get task status`)
    console.log(`  POST   /api/workflows     - Create workflow`)
    console.log(`  GET    /api/workflows/:id - Get workflow status`)
    console.log(`  GET    /api/status        - System status`)
    console.log(`  GET    /api/metrics       - System metrics`)
    console.log(`  GET    /api/workforce/status   - Workforce bridge status`)
    console.log(`  GET    /api/workforce/metrics  - Workforce metrics & agent performance`)
    console.log(`  GET    /api/workforce/tasks    - List workforce tasks (filter by status, type, industry)`)
    console.log(`  GET    /api/workforce/tasks/:id - Get specific task status`)
    console.log(`  POST   /api/workforce/tasks    - Submit workforce task`)
    console.log(`  GET    /api/workforce/agents   - Workforce agent status & metrics\n`)
  })
}

// Vercel serverless export
export default app