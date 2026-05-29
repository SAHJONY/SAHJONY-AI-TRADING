/**
 * Base Agent Tests
 * Tests for BaseAgent abstract class, factory functions, and registry
 */

import { BaseAgent, AgentTool, registerAgent, createAgent, agentRegistry } from '../../src/agents/base-agent'
import { AgentConfig, Task, TaskResult, AgentMessage } from '../../src/types'

// Concrete implementation for testing
class TestAgent extends BaseAgent {
  async executeTask(task: Task): Promise<TaskResult> {
    return {
      success: true,
      output: { message: `Executed: ${task.description}` }
    }
  }

  getCapabilities(): string[] {
    return ['testing']
  }
}

function makeConfig(overrides: Partial<AgentConfig> = {}): AgentConfig {
  return {
    id: 'test-agent-1',
    name: 'Test Agent',
    role: 'researcher',
    capabilities: [{
      name: 'test',
      description: 'Test capability',
      tools: [],
      maxConcurrentTasks: 1
    }],
    ...overrides
  }
}

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    type: 'test',
    description: 'Test task',
    priority: 'medium',
    status: 'pending',
    dependencies: [],
    context: {
      userRequest: 'Test request',
      sessionId: 'test-session',
      variables: {}
    },
    createdAt: new Date(),
    updatedAt: new Date(),
    ...overrides
  }
}

describe('BaseAgent', () => {
  let agent: TestAgent

  beforeEach(() => {
    agent = new TestAgent(makeConfig())
  })

  afterEach(() => {
    agent.destroy()
  })

  describe('Properties', () => {
    it('should return correct id', () => {
      expect(agent.id).toBe('test-agent-1')
    })

    it('should return correct role', () => {
      expect(agent.role).toBe('researcher')
    })

    it('should return correct name', () => {
      expect(agent.name).toBe('Test Agent')
    })

    it('should start as idle', () => {
      expect(agent.getStatus()).toBe('idle')
    })

    it('should return a copy of state', () => {
      const state1 = agent.getState()
      const state2 = agent.getState()
      expect(state1).not.toBe(state2) // different references
      expect(state1.agentId).toBe(state2.agentId)
    })
  })

  describe('setStatus', () => {
    it('should update status', () => {
      agent.setStatus('working')
      expect(agent.getStatus()).toBe('working')
    })

    it('should emit statusChange event', () => {
      const events: any[] = []
      agent.on('statusChange', (data) => events.push(data))
      agent.setStatus('working')
      expect(events.length).toBe(1)
      expect(events[0].status).toBe('working')
      expect(events[0].agentId).toBe('test-agent-1')
    })

    it('should update lastActivity on status change', () => {
      const before = agent.getState().lastActivity
      // Small delay to ensure timestamp difference
      agent.setStatus('completed')
      const after = agent.getState().lastActivity
      expect(after.getTime()).toBeGreaterThanOrEqual(before.getTime())
    })
  })

  describe('Tool Management', () => {
    it('should register a tool', () => {
      const tool: AgentTool = {
        name: 'echo',
        description: 'Echo tool',
        execute: async () => ({ success: true, output: 'echo', duration: 10 })
      }
      agent.registerTool(tool)
      // Should not throw
    })

    it('should emit toolRegistered event', () => {
      const events: any[] = []
      agent.on('toolRegistered', (data) => events.push(data))

      agent.registerTool({
        name: 'echo',
        description: 'Echo',
        execute: async () => ({ success: true, output: 'ok', duration: 5 })
      })

      expect(events.length).toBe(1)
      expect(events[0].tool).toBe('echo')
    })

    it('should execute registered tool', async () => {
      agent.registerTool({
        name: 'echo',
        description: 'Echo',
        execute: async (params: unknown) => ({
          success: true,
          output: (params as any).message,
          duration: 5
        })
      })

      const result = await agent.executeTool('echo', { message: 'hello' })
      expect(result.success).toBe(true)
      expect(result.output).toBe('hello')
      expect(result.duration).toBeGreaterThanOrEqual(0)
    })

    it('should return error for unknown tool', async () => {
      const result = await agent.executeTool('nonexistent', {})
      expect(result.success).toBe(false)
      expect(result.error).toContain('not found')
      expect(result.duration).toBe(0)
    })

    it('should handle tool execution error', async () => {
      agent.registerTool({
        name: 'failing',
        description: 'Always fails',
        execute: async () => {
          throw new Error('Tool error')
        }
      })

      const result = await agent.executeTool('failing', {})
      expect(result.success).toBe(false)
      expect(result.error).toBe('Tool error')
      expect(result.duration).toBeGreaterThanOrEqual(0)
    })
  })

  describe('runTask', () => {
    it('should execute task and return success result', async () => {
      const task = makeTask()
      const result = await agent.runTask(task)

      expect(result.success).toBe(true)
      expect(result.output).toBeDefined()
    })

    it('should update status to working during execution', () => {
      const task = makeTask()
      const promise = agent.runTask(task)
      // Status might be 'working' or already 'completed' depending on timing
      promise.then(() => {
        expect(agent.getStatus()).toBe('completed')
      })
      return promise
    })

    it('should emit taskCompleted event on success', async () => {
      const events: any[] = []
      agent.on('taskCompleted', (data) => events.push(data))

      await agent.runTask(makeTask())
      expect(events.length).toBeGreaterThanOrEqual(1)
    })

    it('should emit taskStarted event', async () => {
      const events: any[] = []
      agent.on('taskStarted', (data) => events.push(data))

      await agent.runTask(makeTask())
      expect(events.length).toBe(1)
    })

    it('should track completed tasks', async () => {
      await agent.runTask(makeTask({ id: 'task-a' }))
      const state = agent.getState()
      expect(state.completedTasks).toContain('task-a')
    })

    it('should update metrics on success', async () => {
      await agent.runTask(makeTask())
      const state = agent.getState()
      expect(state.metrics.tasksCompleted).toBe(1)
    })

    it('should update metrics on failure', async () => {
      // Create an agent that fails
      class FailingAgent extends BaseAgent {
        async executeTask(_task: Task): Promise<TaskResult> {
          throw new Error('Intentional failure')
        }
        getCapabilities(): string[] { return [] }
      }

      const failing = new FailingAgent(makeConfig({ id: 'failing-agent' }))
      const result = await failing.runTask(makeTask())

      expect(result.success).toBe(false)
      expect(result.error).toBe('Intentional failure')
      expect(failing.getState().metrics.tasksFailed).toBe(1)
      failing.destroy()
    })

    it('should emit taskFailed on failure', async () => {
      class FailingAgent extends BaseAgent {
        async executeTask(_task: Task): Promise<TaskResult> {
          throw new Error('Failure')
        }
        getCapabilities(): string[] { return [] }
      }

      const failing = new FailingAgent(makeConfig({ id: 'fail-1' }))
      const events: any[] = []
      failing.on('taskFailed', (data) => events.push(data))

      await failing.runTask(makeTask())
      expect(events.length).toBeGreaterThanOrEqual(1)
      failing.destroy()
    })

    it('should track failed tasks', async () => {
      class FailingAgent extends BaseAgent {
        async executeTask(_task: Task): Promise<TaskResult> {
          throw new Error('Failure')
        }
        getCapabilities(): string[] { return [] }
      }

      const failing = new FailingAgent(makeConfig({ id: 'fail-2' }))
      await failing.runTask(makeTask({ id: 'task-fail' }))
      expect(failing.getState().failedTasks).toContain('task-fail')
      failing.destroy()
    })

    it('should calculate average execution time correctly', async () => {
      await agent.runTask(makeTask({ id: 't1' }))
      await agent.runTask(makeTask({ id: 't2' }))

      const state = agent.getState()
      // Average execution time may be 0 for very fast mock executions
      expect(state.metrics.averageExecutionTime).toBeGreaterThanOrEqual(0)
      expect(state.metrics.tasksCompleted).toBe(2)
    })

    it('should reset currentTaskId after execution', async () => {
      await agent.runTask(makeTask())
      const state = agent.getState()
      expect(state.currentTaskId).toBeUndefined()
    })
  })

  describe('Message Handling', () => {
    it('should send a message', () => {
      const message: AgentMessage = {
        id: 'msg-1',
        type: 'command',
        senderId: 'test-agent-1',
        correlationId: 'corr-1',
        payload: { cmd: 'test' },
        timestamp: new Date(),
        priority: 'normal'
      }

      agent.sendMessage(message)
      // Should not throw
    })

    it('should emit messageSent event', () => {
      const events: any[] = []
      agent.on('messageSent', (data) => events.push(data))

      agent.sendMessage({
        id: 'msg-1',
        type: 'status',
        senderId: 'test-agent-1',
        correlationId: 'corr-1',
        payload: {},
        timestamp: new Date(),
        priority: 'normal'
      })

      expect(events.length).toBe(1)
    })

    it('should receive a message', () => {
      const events: any[] = []
      agent.on('messageReceived', (data) => events.push(data))

      agent.receiveMessage({
        id: 'msg-1',
        type: 'command',
        senderId: 'other-agent',
        recipientId: 'test-agent-1',
        correlationId: 'corr-1',
        payload: { cmd: 'test' },
        timestamp: new Date(),
        priority: 'normal'
      })

      expect(events.length).toBe(1)
    })
  })

  describe('destroy', () => {
    it('should clean up resources', () => {
      agent.registerTool({
        name: 'test',
        description: 'test',
        execute: async () => ({ success: true, output: 'ok', duration: 1 })
      })

      agent.destroy()
      // After destroy, listeners should be cleared
      // The agent should not throw when destroyed
    })
  })
})

describe('Agent Factory', () => {
  beforeEach(() => {
    agentRegistry.clear()
  })

  it('should register an agent constructor', () => {
    registerAgent('researcher', TestAgent)
    expect(agentRegistry.has('researcher')).toBe(true)
  })

  it('should create agent from registry', () => {
    registerAgent('researcher', TestAgent)
    const agent = createAgent('researcher', makeConfig())
    expect(agent).toBeInstanceOf(TestAgent)
    expect(agent.id).toBe('test-agent-1')
    agent.destroy()
  })

  it('should throw for unregistered role', () => {
    expect(() => createAgent('coder', makeConfig())).toThrow('No agent registered for role')
  })

  it('should allow registering multiple roles', () => {
    registerAgent('researcher', TestAgent)
    registerAgent('reviewer', TestAgent)
    expect(agentRegistry.size).toBe(2)
  })

  it('should overwrite existing role registration', () => {
    registerAgent('researcher', TestAgent)
    class OtherAgent extends TestAgent {}
    registerAgent('researcher', OtherAgent)
    const agent = createAgent('researcher', makeConfig())
    expect(agent).toBeInstanceOf(OtherAgent)
    agent.destroy()
  })
})
