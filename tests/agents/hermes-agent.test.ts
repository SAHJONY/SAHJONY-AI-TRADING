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
})
