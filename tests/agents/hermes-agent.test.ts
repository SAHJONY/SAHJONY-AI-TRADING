/**
 * Hermes Agent Tests
 * Tests for non-process-dependent methods of HermesAgent
 */

import { HermesAgent, HermesAgentConfig } from '../../src/agents/hermes-agent'

function makeConfig(overrides: Partial<HermesAgentConfig> = {}): HermesAgentConfig {
  return {
    id: 'hermes-test-1',
    name: 'Test Hermes',
    role: 'hermes',
    hermesPath: 'nonexistent-hermes',
    capabilities: [{
      name: 'ai_assistant',
      description: 'AI assistant capability',
      tools: [],
      maxConcurrentTasks: 3
    }],
    ...overrides,
  }
}

/**
 * Creates a config that spawns a long-running Node.js process
 * (instead of a real hermes binary) for testing destroy/cleanup behavior.
 */
function makeLongRunningConfig(overrides: Partial<HermesAgentConfig> = {}): HermesAgentConfig {
  return makeConfig({
    hermesPath: process.execPath,
    hermesArgs: ['-e', 'setTimeout(()=>{},30000)'],
    ...overrides,
  })
}

describe('HermesAgent', () => {
  let agent: HermesAgent

  beforeEach(() => {
    agent = new HermesAgent(makeConfig())
  })

  afterEach(() => {
    try { agent.destroy() } catch { /* process may not have started */ }
  })

  describe('Initialization', () => {
    it('should create with correct capabilities', () => {
      const caps = agent.getCapabilities()
      expect(caps).toContain('natural_language_understanding')
      expect(caps).toContain('code_generation')
      expect(caps).toContain('problem_solving')
      expect(caps).toContain('research')
      expect(caps).toContain('reasoning')
      expect(caps).toContain('self_improvement')
      expect(caps).toContain('memory_persistence')
      expect(caps).toContain('tool_use')
      expect(caps).toContain('multi_turn_conversation')
      expect(caps).toContain('skill_creation')
    })

    it('should have proper id and name', () => {
      expect(agent.id).toBe('hermes-test-1')
      expect(agent.name).toBe('Test Hermes')
      expect(agent.role).toBe('hermes')
    })

    it('should return hermes status', () => {
      const status = agent.getHermesStatus()
      expect(status).toHaveProperty('initialized')
      expect(status).toHaveProperty('sessionId')
      expect(status).toHaveProperty('pendingRequests')
      expect(status.pendingRequests).toBe(0)
    })

    it('should have a session ID', () => {
      const status = agent.getHermesStatus()
      expect(status.sessionId).toBeDefined()
      expect(status.sessionId.length).toBeGreaterThan(0)
    })
  })

  describe('Tool Registration', () => {
    it('should register a hermes tool', () => {
      agent.registerHermesTool({
        name: 'test_tool',
        description: 'A test tool',
        execute: async () => ({ success: true, output: 'ok', duration: 5 })
      })
      // Should not throw
      const status = agent.getHermesStatus()
      expect(status).toBeDefined()
    })
  })

  describe('Task Execution', () => {
    it('should fail gracefully without hermes process', async () => {
      const task = {
        id: 'task-1',
        type: 'test',
        description: 'Test task',
        priority: 'medium' as const,
        status: 'pending' as const,
        dependencies: [],
        context: {
          userRequest: 'Test request',
          sessionId: 'test-session',
          variables: {},
        },
        createdAt: new Date(),
        updatedAt: new Date(),
      }

      const result = await agent.runTask(task)
      // Should handle the failure gracefully
      expect(result).toBeDefined()
    })
  })

  describe('getHermesStatus', () => {
    it('should report not initialized when process has died', async () => {
      // Wait for the nonexistent hermes process to fail and be cleaned up
      await new Promise(r => setTimeout(r, 200))
      const status = agent.getHermesStatus()
      expect(status.initialized).toBe(false)
    })
  })

  describe('Process Lifecycle / rejectAllPending', () => {
    let liveAgent: HermesAgent

    beforeEach(() => {
      // Use a long-running node process instead of a real hermes binary
      liveAgent = new HermesAgent(makeLongRunningConfig({ id: 'hermes-live' }))
    })

    afterEach(() => {
      try { liveAgent.destroy() } catch { /* already destroyed */ }
    })

    it('should reject pending tasks when agent is destroyed', async () => {
      const task = {
        id: 'task-destroy',
        type: 'test',
        description: 'Task that will be interrupted',
        priority: 'medium' as const,
        status: 'pending' as const,
        dependencies: [],
        context: {
          userRequest: 'Test request',
          sessionId: 'test-session',
          variables: {},
        },
        createdAt: new Date(),
        updatedAt: new Date(),
      }

      // Fire off the task (it will hang waiting for hermes response)
      const taskPromise = liveAgent.runTask(task)

      // Give it a moment to register the pending request
      await new Promise(r => setTimeout(r, 50))

      // Destroy the agent while the task is pending
      liveAgent.destroy()

      // The task should resolve with a failure (not hang)
      const result = await taskPromise
      expect(result).toBeDefined()
      expect(result.success).toBe(false)
      expect(result.error).toContain('destroyed')
    })

    it('should reject multiple concurrent pending tasks on destroy', async () => {
      const makeTask = (id: string) => ({
        id,
        type: 'test' as const,
        description: `Task ${id}`,
        priority: 'medium' as const,
        status: 'pending' as const,
        dependencies: [],
        context: {
          userRequest: 'Test request',
          sessionId: 'test-session',
          variables: {},
        },
        createdAt: new Date(),
        updatedAt: new Date(),
      })

      // Fire off multiple tasks concurrently
      const promises = [
        liveAgent.runTask(makeTask('multi-1')),
        liveAgent.runTask(makeTask('multi-2')),
        liveAgent.runTask(makeTask('multi-3')),
      ]

      // Let them all register their pending requests
      await new Promise(r => setTimeout(r, 50))

      // All three should be pending
      expect(liveAgent.getHermesStatus().pendingRequests).toBe(3)

      // Destroy while tasks are pending
      liveAgent.destroy()

      // All tasks should resolve with failure (not hang)
      const results = await Promise.all(promises)
      for (const result of results) {
        expect(result.success).toBe(false)
        expect(result.error).toContain('destroyed')
      }
    })

    it('should report zero pending requests after destroy', async () => {
      // Fire off a task to create a pending request
      liveAgent.runTask({
        id: 'task-cleanup',
        type: 'test',
        description: 'Cleanup test',
        priority: 'medium' as const,
        status: 'pending' as const,
        dependencies: [],
        context: {
          userRequest: 'Test',
          sessionId: 'test-session',
          variables: {},
        },
        createdAt: new Date(),
        updatedAt: new Date(),
      })

      // Give the task a moment to register its pending request
      // (runTask yields at await onTaskStart before executeTask adds to the map)
      await new Promise(r => setTimeout(r, 50))

      // Destroy should clean up all pending requests
      liveAgent.destroy()

      expect(liveAgent.getHermesStatus().pendingRequests).toBe(0)
    })

    it('should not throw when destroy is called twice', () => {
      liveAgent.destroy()
      expect(() => liveAgent.destroy()).not.toThrow()
    })
  })
})
