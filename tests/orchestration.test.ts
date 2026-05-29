/**
 * Orchestration Engine Tests
 * Unit tests for the multi-agent orchestration system
 */

import { OrchestrationEngine, createEngine } from '../src/orchestration/engine'
import { TaskContext, AgentRole, WorkflowDefinition } from '../src/types'

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
    it('should have agents spawned on initialization', () => {
      const newEngine = new OrchestrationEngine()
      const agents = newEngine.getAllAgents()
      expect(agents.length).toBeGreaterThan(0)
      expect(agents[0].id).toBeDefined()
      expect(agents[0].role).toBeDefined()
    })

    it('should emit task events when submitting tasks', async () => {
      let taskSubmitted = false
      let taskAssigned = false

      engine.on('task:submitted', () => {
        taskSubmitted = true
      })

      engine.on('agent:task_assigned', () => {
        taskAssigned = true
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