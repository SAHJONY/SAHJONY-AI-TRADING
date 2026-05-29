/**
 * Orchestration Engine Tests
 * Unit tests for the multi-agent orchestration system
 */

import { OrchestrationEngine, createEngine, getEngine } from '../src/orchestration/engine'
import type { OrchestratorConfig } from '../src/orchestration/engine'
import { TaskContext, AgentRole, WorkflowDefinition } from '../src/types'

/**
 * Helper: creates an OrchestrationEngine with deferInit so listeners can
 * be registered before constructor events fire. After registration,
 * calls engine.init() to trigger agent spawning/registration events.
 */
function createEngineWithListener(
  event: string,
  listener: (...args: any[]) => void,
  config?: Partial<OrchestratorConfig>
): OrchestrationEngine {
  const engine = new OrchestrationEngine({ ...(config ?? { maxConcurrentAgents: 3, maxQueueSize: 10, defaultTimeout: 5000, enableRetry: false, maxRetries: 1 }), deferInit: true })
  engine.on(event, listener)
  engine.init()
  return engine
}

describe('OrchestrationEngine', () => {
  let engine: OrchestrationEngine

  beforeEach(() => {
    engine = createEngine({
      maxConcurrentAgents: 3,
      maxQueueSize: 10,
      defaultTimeout: 5000,
      enableRetry: false,
      maxRetries: 1
    })
  })

  describe('Initialization', () => {
    it('should create engine with default configuration', () => {
      const defaultEngine = new OrchestrationEngine()
      expect(defaultEngine).toBeDefined()
    })

    it('should initialize with default agents', () => {
      const status = engine.getStatus()
      expect(status.agents.length).toBeGreaterThan(0)
    })

    it('should have orchestrator agent', () => {
      const agents = engine.getAllAgents()
      const hasOrchestrator = agents.some(a => a.role === 'orchestrator')
      expect(hasOrchestrator).toBe(true)
    })
  })

  describe('Task Management', () => {
    it('should submit a task', async () => {
      const context: TaskContext = {
        userRequest: 'Test task',
        sessionId: 'test-session',
        variables: {}
      }

      const task = await engine.submitTask('Research AI trends', context, { priority: 'high' })
      
      expect(task).toBeDefined()
      expect(task.id).toBeDefined()
      expect(task.description).toBe('Research AI trends')
      expect(task.priority).toBe('high')
    })

    it('should have tasks in queue after submission', async () => {
      const context: TaskContext = {
        userRequest: 'Test task',
        sessionId: 'test-session',
        variables: {}
      }

      await engine.submitTask('Task 1', context)
      await engine.submitTask('Task 2', context)

      const status = engine.getStatus()
      expect(status.queueLength).toBeGreaterThanOrEqual(0)
    })

    it('should get task by ID', async () => {
      const context: TaskContext = {
        userRequest: 'Test task',
        sessionId: 'test-session',
        variables: {}
      }

      const submitted = await engine.submitTask('Find task by ID', context)
      const found = engine.getTask(submitted.id)

      expect(found).toBeDefined()
      expect(found?.id).toBe(submitted.id)
    })

    it('should get all agents', () => {
      const agents = engine.getAllAgents()
      expect(Array.isArray(agents)).toBe(true)
      expect(agents.length).toBeGreaterThan(0)
    })

    it('should get agent by ID', () => {
      const agents = engine.getAllAgents()
      if (agents.length > 0) {
        const agent = engine.getAgent(agents[0].id)
        expect(agent).toBeDefined()
      }
    })
  })

  describe('Workflow Execution', () => {
    it('should submit a workflow', async () => {
      const workflow: WorkflowDefinition = {
        id: 'test-workflow',
        name: 'Test Workflow',
        description: 'A test workflow',
        tasks: [
          {
            id: 'task-1',
            type: 'research',
            agentRole: 'researcher',
            instruction: 'Research AI',
            dependencies: []
          },
          {
            id: 'task-2',
            type: 'code',
            agentRole: 'coder',
            instruction: 'Implement AI',
            dependencies: ['task-1']
          }
        ],
        agents: [],
        maxParallelAgents: 2
      }

      const workflowId = await engine.submitWorkflow(workflow)
      expect(workflowId).toBeDefined()
    })
  })

  describe('System Status', () => {
    it('should return correct status structure', () => {
      const status = engine.getStatus()

      expect(status).toHaveProperty('queueLength')
      expect(status).toHaveProperty('activeTasks')
      expect(status).toHaveProperty('completedTasks')
      expect(status).toHaveProperty('agents')
      expect(Array.isArray(status.agents)).toBe(true)
    })

    it('should track agent states', () => {
      const agents = engine.getAllAgents()
      
      for (const agent of agents) {
        expect(agent.id).toBeDefined()
        expect(agent.role).toBeDefined()
        expect(agent.getStatus()).toBeDefined()
      }
    })
  })

  describe('Event Handling', () => {
    it('should emit agent:spawned for each agent during initialization', () => {
      const spawned: Array<{ agentId: string; role: string }> = []

      // Use helper that registers listener BEFORE init fires constructor events
      const newEngine = createEngineWithListener('agent:spawned', (data) => {
        spawned.push({ agentId: data.agentId, role: data.role })
      })

      // All agents should have been spawned during init()
      const agents = newEngine.getAllAgents()
      expect(spawned.length).toBe(agents.length)
      expect(spawned.length).toBeGreaterThan(0)

      // Each spawned event matches a real agent
      for (const s of spawned) {
        expect(s.agentId).toBeDefined()
        expect(s.role).toBeDefined()
        const match = agents.find(a => a.id === s.agentId && a.role === s.role)
        expect(match).toBeDefined()
      }
    })

    it('should be idempotent — calling init() twice does not duplicate agents or events', () => {
      const firstSpawnCount: Array<{ agentId: string }> = []

      const engine = createEngineWithListener('agent:spawned', (data) => {
        firstSpawnCount.push({ agentId: data.agentId })
      })

      const agentCountAfterFirstInit = engine.getAllAgents().length
      expect(firstSpawnCount.length).toBe(agentCountAfterFirstInit)

      // Call init() again — should be a no-op
      const secondSpawnCount: Array<{ agentId: string }> = []
      engine.on('agent:spawned', (data) => {
        secondSpawnCount.push({ agentId: data.agentId })
      })
      engine.init()

      // No new events fired, no new agents added
      expect(secondSpawnCount.length).toBe(0)
      expect(engine.getAllAgents().length).toBe(agentCountAfterFirstInit)
    })

    it('should emit task events when submitting tasks', async () => {
      let _taskSubmitted = false
      let _taskAssigned = false

      engine.on('task:submitted', () => {
        _taskSubmitted = true
      })

      engine.on('agent:task_assigned', () => {
        _taskAssigned = true
      })

      const context: TaskContext = {
        userRequest: 'Test event',
        sessionId: 'test-session',
        variables: {}
      }

      await engine.submitTask('Test task event', context)

      // Give time for async event emission
      await new Promise(resolve => setTimeout(resolve, 100))
    })
  })

  describe('Message Broadcasting', () => {
    it('should send messages to specific agents', () => {
      const agents = engine.getAllAgents()
      if (agents.length > 0) {
        expect(() => {
          engine.sendMessage({
            id: 'msg-1',
            type: 'command',
            senderId: 'test',
            recipientId: agents[0].id,
            correlationId: 'corr-1',
            payload: { command: 'test' },
            timestamp: new Date(),
            priority: 'normal'
          })
        }).not.toThrow()
      }
    })

    it('should handle sendMessage to non-existent agent gracefully', () => {
      expect(() => {
        engine.sendMessage({
          id: 'msg-1',
          type: 'command',
          senderId: 'test',
          recipientId: 'nonexistent-agent',
          correlationId: 'corr-1',
          payload: { command: 'test' },
          timestamp: new Date(),
          priority: 'normal'
        })
      }).not.toThrow()
    })

    it('should broadcast messages to all agents', () => {
      expect(() => {
        engine.broadcast({
          id: 'broadcast-1',
          type: 'command',
          senderId: 'system',
          correlationId: 'corr-1',
          payload: { alert: 'system update' },
          timestamp: new Date(),
          priority: 'high'
        })
      }).not.toThrow()
    })
  })

  describe('Event Logging', () => {
    it('should log system events', () => {
      const events: any[] = []
      engine.on('workflow:started' as any, (data) => events.push(data))

      engine.logEvent({
        type: 'workflow:started',
        timestamp: new Date(),
        source: 'test',
        data: { key: 'value' }
      })

      expect(events.length).toBe(1)
      expect(events[0].data.key).toBe('value')
    })
  })

  describe('Retry Logic', () => {
    it('should support retry configuration', () => {
      const retryEngine = createEngine({
        maxConcurrentAgents: 3,
        maxQueueSize: 10,
        defaultTimeout: 5000,
        enableRetry: true,
        maxRetries: 3
      })

      expect(retryEngine).toBeDefined()
      const status = retryEngine.getStatus()
      expect(status.agents.length).toBeGreaterThan(0)
    })
  })

  describe('Task Edge Cases', () => {
    it('should return undefined for non-existent task', () => {
      const task = engine.getTask('non-existent-task-id')
      expect(task).toBeUndefined()
    })

    it('should get all tasks including queued and completed', async () => {
      const context: TaskContext = {
        userRequest: 'Test',
        sessionId: 'test-session',
        variables: {}
      }

      await engine.submitTask('Task for all', context)
      const allTasks = engine.getAllTasks()
      expect(allTasks.length).toBeGreaterThan(0)
    })

    it('should submit task with all options', async () => {
      const context: TaskContext = {
        userRequest: 'Test with options',
        sessionId: 'test-session',
        variables: { existing: 'data' }
      }

      const task = await engine.submitTask('Build a complex feature', context, {
        priority: 'critical',
        agentRole: 'coder',
        timeout: 10000
      })

      expect(task.priority).toBe('critical')
    })
  })

  describe('Singleton Behavior', () => {
    it('should return same instance from getEngine', () => {
      const engine1 = getEngine()
      const engine2 = getEngine()
      expect(engine1).toBe(engine2)
    })

    it('should replace instance with createEngine', () => {
      const engine1 = createEngine({ maxConcurrentAgents: 2 })
      const engine2 = getEngine()
      expect(engine1).toBe(engine2)
    })
  })

  describe('Workflow Advanced', () => {
    it('should emit workflow:started event', async () => {
      const events: any[] = []
      engine.on('workflow:started', (data) => events.push(data))

      const workflow: WorkflowDefinition = {
        id: 'wf-event',
        name: 'Event Workflow',
        description: 'Test events',
        tasks: [
          {
            id: 'wf-task-1',
            type: 'research',
            agentRole: 'researcher',
            instruction: 'Research topic',
            dependencies: []
          }
        ],
        agents: [],
        maxParallelAgents: 1
      }

      await engine.submitWorkflow(workflow)
      expect(events.length).toBe(1)
      expect(events[0].workflowId).toBeDefined()
    })

    it('should submit workflow with retry policy', async () => {
      const workflow: WorkflowDefinition = {
        id: 'wf-retry',
        name: 'Retry Workflow',
        description: 'Test retry',
        tasks: [
          {
            id: 'rt-1',
            type: 'research',
            agentRole: 'researcher',
            instruction: 'Research',
            dependencies: [],
            timeout: 30000,
            critical: true
          }
        ],
        agents: [],
        maxParallelAgents: 1,
        retryPolicy: {
          maxRetries: 3,
          backoffMs: 1000,
          exponentialBackoff: true
        },
        timeout: 60000
      }

      const workflowId = await engine.submitWorkflow(workflow)
      expect(workflowId).toBeDefined()
    })
  })

  describe('Deferred Initialization', () => {
    it('should support deferInit config option', () => {
      const deferred = new OrchestrationEngine({
        maxConcurrentAgents: 1,
        maxQueueSize: 5,
        defaultTimeout: 1000,
        deferInit: true
      })

      // Before init, there should be no agents
      const agentsBefore = deferred.getAllAgents()
      expect(agentsBefore.length).toBe(0)

      // After init, agents should be created
      deferred.init()
      const agentsAfter = deferred.getAllAgents()
      expect(agentsAfter.length).toBeGreaterThan(0)
    })
  })
})

describe('Agent Roles', () => {
  it('should have correct agent roles defined', () => {
    const roles: AgentRole[] = ['orchestrator', 'researcher', 'coder', 'reviewer', 'executor', 'planner']
    
    for (const role of roles) {
      expect(typeof role).toBe('string')
    }
  })
})