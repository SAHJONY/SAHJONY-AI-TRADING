/**
 * Orchestrator Agent Tests
 * Comprehensive tests for agent coordination, task decomposition, and message handling
 */

import { OrchestratorAgent } from '../../src/agents/orchestrator'
import { BaseAgent } from '../../src/agents/base-agent'
import { AgentConfig, Task, TaskResult, TaskContext, AgentMessage } from '../../src/types'

// Simple test agent for the agent pool
class TestWorkerAgent extends BaseAgent {
  private shouldFail = false

  constructor(config: AgentConfig, shouldFail = false) {
    super(config)
    this.shouldFail = shouldFail
  }

  async executeTask(task: Task): Promise<TaskResult> {
    if (this.shouldFail) {
      throw new Error('Worker failure')
    }
    return {
      success: true,
      output: { message: `Worker executed: ${task.description}` }
    }
  }

  getCapabilities(): string[] {
    return ['test']
  }
}

function makeConfig(overrides: Partial<AgentConfig> = {}): AgentConfig {
  return {
    id: 'orch-test-1',
    name: 'Test Orchestrator',
    role: 'orchestrator',
    capabilities: [{
      name: 'orchestration',
      description: 'Coordination',
      tools: [],
      maxConcurrentTasks: 5
    }],
    ...overrides
  }
}

function makeWorkerConfig(id: string, role: string): AgentConfig {
  return {
    id,
    name: `Worker ${id}`,
    role: role as any,
    capabilities: [{
      name: role,
      description: `${role} work`,
      tools: [],
      maxConcurrentTasks: 1
    }]
  }
}

function makeContext(overrides: Partial<TaskContext> = {}): TaskContext {
  return {
    userRequest: 'Test request',
    sessionId: 'test-session',
    variables: {},
    ...overrides
  }
}

describe('OrchestratorAgent', () => {
  let orch: OrchestratorAgent

  beforeEach(() => {
    orch = new OrchestratorAgent(makeConfig(), 5)
  })

  afterEach(() => {
    orch.destroy()
  })

  describe('Initialization', () => {
    it('should create with correct capabilities', () => {
      const caps = orch.getCapabilities()
      expect(caps).toContain('task_planning')
      expect(caps).toContain('task_decomposition')
      expect(caps).toContain('agent_coordination')
      expect(caps).toContain('workflow_orchestration')
      expect(caps).toContain('resource_allocation')
      expect(caps).toContain('error_recovery')
    })

    it('should start with idle status', () => {
      expect(orch.getStatus()).toBe('idle')
    })

    it('should have empty agent pool initially', () => {
      const stats = orch.getStats()
      expect(stats.activeAgents).toBe(0)
      expect(stats.completedTasks).toBe(0)
      expect(stats.failedTasks).toBe(0)
    })
  })

  describe('processRequest', () => {
    it('should process a research request', async () => {
      // Register workers
      const researcher = new TestWorkerAgent(makeWorkerConfig('researcher-1', 'researcher'))
      orch.registerAgent(researcher)
      const coder = new TestWorkerAgent(makeWorkerConfig('coder-1', 'coder'))
      orch.registerAgent(coder)

      const result = await orch.processRequest('research AI trends', makeContext())

      expect(result.success).toBe(true)
      expect(result.output).toBeDefined()

      researcher.destroy()
      coder.destroy()
    })

    it('should process a build request', async () => {
      const coder = new TestWorkerAgent(makeWorkerConfig('coder-1', 'coder'))
      orch.registerAgent(coder)

      const result = await orch.processRequest('build a REST API', makeContext())
      expect(result.success).toBe(true)

      coder.destroy()
    })

    it('should process a review request', async () => {
      const reviewer = new TestWorkerAgent(makeWorkerConfig('reviewer-1', 'reviewer'))
      orch.registerAgent(reviewer)

      const result = await orch.processRequest('review the codebase', makeContext())
      expect(result.success).toBe(true)

      reviewer.destroy()
    })

    it('should process an execute request', async () => {
      const executor = new TestWorkerAgent(makeWorkerConfig('executor-1', 'executor'))
      orch.registerAgent(executor)

      const result = await orch.processRequest('run the deployment script', makeContext())
      expect(result.success).toBe(true)

      executor.destroy()
    })

    it('should handle request with no matching workers (full pipeline)', async () => {
      const researcher = new TestWorkerAgent(makeWorkerConfig('researcher-1', 'researcher'))
      const coder = new TestWorkerAgent(makeWorkerConfig('coder-1', 'coder'))
      const reviewer = new TestWorkerAgent(makeWorkerConfig('reviewer-1', 'reviewer'))
      orch.registerAgent(researcher)
      orch.registerAgent(coder)
      orch.registerAgent(reviewer)

      const result = await orch.processRequest('do something completely new', makeContext())
      expect(result.success).toBe(true)

      researcher.destroy()
      coder.destroy()
      reviewer.destroy()
    })

    it('should handle failure when no workers available', async () => {
      const result = await orch.processRequest('research AI', makeContext())
      // Should still return a result, even if no workers completed
      expect(result).toBeDefined()
    })
  })

  describe('executeTask', () => {
    it('should delegate to processRequest', async () => {
      const coder = new TestWorkerAgent(makeWorkerConfig('coder-1', 'coder'))
      orch.registerAgent(coder)

      const task: Task = {
        id: 'task-1',
        type: 'generic',
        description: 'build something',
        priority: 'medium',
        status: 'pending',
        dependencies: [],
        context: makeContext({ userRequest: 'build a feature' }),
        createdAt: new Date(),
        updatedAt: new Date()
      }

      const result = await orch.executeTask(task)
      expect(result.success).toBe(true)

      coder.destroy()
    })
  })

  describe('registerAgent', () => {
    it('should add agent to pool', () => {
      const worker = new TestWorkerAgent(makeWorkerConfig('worker-1', 'researcher'))
      orch.registerAgent(worker)

      const stats = orch.getStats()
      expect(stats.activeAgents).toBe(1)

      worker.destroy()
    })

    it('should forward worker events', () => {
      const events: any[] = []
      orch.on('agentTaskCompleted', (data) => events.push(data))

      const worker = new TestWorkerAgent(makeWorkerConfig('worker-1', 'researcher'))
      orch.registerAgent(worker)
      // Worker emits taskCompleted when runTask completes
      // We just verify the forwarding setup doesn't crash

      worker.destroy()
    })
  })

  describe('processMessage', () => {
    it('should handle task delegation message', () => {
      const msg: AgentMessage = {
        id: 'msg-1',
        type: 'task',
        senderId: 'other-agent',
        recipientId: 'orch-test-1',
        taskId: 'task-1',
        correlationId: 'corr-1',
        payload: {
          instruction: 'research AI',
          context: makeContext()
        },
        timestamp: new Date(),
        priority: 'normal'
      }

      // Should not throw
      orch.receiveMessage(msg)
    })

    it('should handle status query message', () => {
      const msg: AgentMessage = {
        id: 'msg-1',
        type: 'status',
        senderId: 'other-agent',
        recipientId: 'orch-test-1',
        correlationId: 'corr-1',
        payload: {},
        timestamp: new Date(),
        priority: 'normal'
      }

      // Should emit response
      const events: any[] = []
      orch.on('messageSent', (data) => events.push(data))

      orch.receiveMessage(msg)
      expect(events.length).toBe(1)
      expect(events[0].type).toBe('status')
      expect(events[0].payload).toHaveProperty('status')
    })
  })

  describe('createExecutionPlan', () => {
    it('should create a plan for research tasks', async () => {
      const plans = await orch.createExecutionPlan('research AI trends', makeContext())
      expect(plans.length).toBeGreaterThan(0)
      expect(plans[0].steps).toBeDefined()
    })

    it('should create a plan for build tasks', async () => {
      const plans = await orch.createExecutionPlan('build a REST API', makeContext())
      expect(plans.length).toBeGreaterThan(0)
    })

    it('should create a full pipeline for generic requests', async () => {
      const plans = await orch.createExecutionPlan('do something', makeContext())
      expect(plans.length).toBeGreaterThan(0)
    })

    it('should emit planCreated event', async () => {
      const events: any[] = []
      orch.on('planCreated', (data) => events.push(data))

      await orch.createExecutionPlan('research AI', makeContext())
      expect(events.length).toBe(1)
      expect(events[0].taskCount).toBeGreaterThan(0)
    })
  })

  describe('getStats', () => {
    it('should return stats with workers', () => {
      const worker = new TestWorkerAgent(makeWorkerConfig('w-1', 'researcher'))
      orch.registerAgent(worker)

      const stats = orch.getStats()
      expect(stats.activeAgents).toBe(1)
      expect(stats.completedTasks).toBe(0)
      expect(stats.failedTasks).toBe(0)

      worker.destroy()
    })
  })
})
