/**
 * Reviewer Agent Tests
 * Comprehensive tests for code review, security audit, and validation
 */

import { ReviewerAgent, ReviewResult } from '../../src/agents/reviewer-agent'
import { AgentConfig, Task, TaskContext } from '../../src/types'

function makeConfig(overrides: Partial<AgentConfig> = {}): AgentConfig {
  return {
    id: 'reviewer-test-1',
    name: 'Test Reviewer',
    role: 'reviewer',
    capabilities: [{
      name: 'review',
      description: 'Review capabilities',
      tools: ['review_code'],
      maxConcurrentTasks: 2
    }],
    ...overrides
  }
}

function makeContext(overrides: Partial<TaskContext> = {}): TaskContext {
  return {
    userRequest: 'Review the code',
    sessionId: 'test-session',
    variables: {},
    ...overrides
  }
}

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    type: 'review',
    description: 'Review the code',
    priority: 'medium',
    status: 'pending',
    dependencies: [],
    context: makeContext(),
    createdAt: new Date(),
    updatedAt: new Date(),
    ...overrides
  }
}

describe('ReviewerAgent', () => {
  let agent: ReviewerAgent

  beforeEach(() => {
    agent = new ReviewerAgent(makeConfig())
  })

  afterEach(() => {
    agent.destroy()
  })

  describe('Initialization', () => {
    it('should create with correct capabilities', () => {
      const caps = agent.getCapabilities()
      expect(caps).toContain('code_review')
      expect(caps).toContain('security_audit')
      expect(caps).toContain('performance_analysis')
      expect(caps).toContain('compliance_check')
      expect(caps).toContain('style_guide_compliance')
      expect(caps).toContain('best_practices_validation')
    })

    it('should start with idle status', () => {
      expect(agent.getStatus()).toBe('idle')
    })

    it('should start with empty review history', () => {
      expect(agent.getReviewHistory()).toEqual([])
    })

    it('should have stats with zero reviews', () => {
      const stats = agent.getStats()
      expect(stats.totalReviews).toBe(0)
      expect(stats.averageScore).toBe(0)
      expect(stats.approvalRate).toBe(0)
    })
  })

  describe('executeTask - code review', () => {
    it('should execute a code review task successfully', async () => {
      const task = makeTask({ description: 'review this code' })
      const result = await agent.runTask(task)

      expect(result.success).toBe(true)
      expect(result.output).toBeDefined()
      expect(result.artifacts).toBeDefined()
      expect(result.artifacts!.length).toBeGreaterThan(0)
    })

    it('should identify review type based on instruction keywords', async () => {
      // Code review
      const codeTask = makeTask({ description: 'review the codebase' })
      const codeResult = await agent.runTask(codeTask)
      expect(codeResult.success).toBe(true)

      // Security review
      const secTask = makeTask({ description: 'check for security vulnerabilities' })
      const secResult = await agent.runTask(secTask)
      expect(secResult.success).toBe(true)

      // Performance review
      const perfTask = makeTask({ description: 'analyze performance issues' })
      const perfResult = await agent.runTask(perfTask)
      expect(perfResult.success).toBe(true)

      // General review (fallback)
      const genTask = makeTask({ description: 'check this thing' })
      const genResult = await agent.runTask(genTask)
      expect(genResult.success).toBe(true)
    })

    it('should handle tasks with plan context', async () => {
      const task = makeTask({
        description: 'Fallback description',
        context: makeContext({
          userRequest: 'Review the implementation',
          variables: {
            plan: {
              steps: [{ instruction: 'Review for bugs and issues' }]
            }
          }
        })
      })
      const result = await agent.runTask(task)
      expect(result.success).toBe(true)
    })

    it('should produce review output with proper structure', async () => {
      const task = makeTask({ description: 'review code for bugs' })
      const result = await agent.runTask(task)

      expect(result.success).toBe(true)
      const output = result.output as ReviewResult
      expect(output).toHaveProperty('score')
      expect(output).toHaveProperty('issues')
      expect(output).toHaveProperty('suggestions')
      expect(output).toHaveProperty('approved')
      expect(output).toHaveProperty('summary')
    })
  })

  describe('executeTask - security audit', () => {
    it('should execute a security review', async () => {
      const task = makeTask({ description: 'check for security vulnerabilities in the authentication module' })
      const result = await agent.runTask(task)

      expect(result.success).toBe(true)
      const output = result.output as ReviewResult
      expect(output.approved).toBe(true)
    })
  })

  describe('executeTask - performance analysis', () => {
    it('should execute performance analysis', async () => {
      const task = makeTask({ description: 'optimize performance of the data pipeline' })
      const result = await agent.runTask(task)

      expect(result.success).toBe(true)
      const output = result.output as ReviewResult
      expect(output.approved).toBe(true)
    })
  })

  describe('review history', () => {
    it('should accumulate review history', async () => {
      const task1 = makeTask({ id: 'task-1', description: 'review code A' })
      const task2 = makeTask({ id: 'task-2', description: 'review code B' })

      await agent.runTask(task1)
      await agent.runTask(task2)

      const history = agent.getReviewHistory()
      expect(history.length).toBe(2)
    })

    it('should return a copy of history (immutable)', async () => {
      await agent.runTask(makeTask({ description: 'review code' }))
      const history = agent.getReviewHistory()
      history.push({ score: 1, issues: [], suggestions: [], approved: false, summary: 'bad' })
      expect(agent.getReviewHistory().length).toBe(1)
    })
  })

  describe('stats', () => {
    it('should calculate correct stats after reviews', async () => {
      await agent.runTask(makeTask({ id: 't1', description: 'review code' }))
      await agent.runTask(makeTask({ id: 't2', description: 'review code' }))
      await agent.runTask(makeTask({ id: 't3', description: 'review code' }))

      const stats = agent.getStats()
      expect(stats.totalReviews).toBe(3)
      expect(stats.averageScore).toBeGreaterThan(0)
      expect(stats.approvalRate).toBeGreaterThan(0)
    })

    it('should return zero stats with no reviews', () => {
      const stats = agent.getStats()
      expect(stats.totalReviews).toBe(0)
      expect(stats.averageScore).toBe(0)
      expect(stats.approvalRate).toBe(0)
    })
  })

  describe('tool execution', () => {
    it('should have review_code tool registered', async () => {
      const result = await agent.executeTool('review_code', { code: 'const x = 1', language: 'typescript' })
      expect(result.success).toBe(true)
      expect(result.output).toBeDefined()
    })

    it('should have security_scan tool registered', async () => {
      const result = await agent.executeTool('security_scan', { code: 'test' })
      expect(result.success).toBe(true)
    })

    it('should have analyze_performance tool registered', async () => {
      const result = await agent.executeTool('analyze_performance', { code: 'test' })
      expect(result.success).toBe(true)
    })

    it('should have lint tool registered', async () => {
      const result = await agent.executeTool('lint', { code: 'test' })
      expect(result.success).toBe(true)
    })

    it('should return error for unknown tool', async () => {
      const result = await agent.executeTool('nonexistent_tool', {})
      expect(result.success).toBe(false)
      expect(result.error).toContain('not found')
    })
  })

  describe('edge cases', () => {
    it('should handle empty task description gracefully', async () => {
      const task = makeTask({ description: '' })
      const result = await agent.runTask(task)
      // Should not throw, even with empty description
      expect(result).toBeDefined()
    })

    it('should handle errors in executeTask gracefully', async () => {
      // Force an error by passing undefined context
      const task = makeTask()
      ;(task as any).context = undefined
      const result = await agent.runTask(task)
      // Should not crash
      expect(result).toBeDefined()
    })
  })
})
