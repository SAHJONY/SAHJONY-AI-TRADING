/**
 * Executor Agent Tests
 * Comprehensive tests for command execution, deployment, testing, and verification
 */

import { ExecutorAgent } from '../../src/agents/executor-agent'
import { AgentConfig, Task, TaskContext } from '../../src/types'

function makeConfig(overrides: Partial<AgentConfig> = {}): AgentConfig {
  return {
    id: 'executor-test-1',
    name: 'Test Executor',
    role: 'executor',
    capabilities: [{
      name: 'execution',
      description: 'Execution capabilities',
      tools: ['run_command'],
      maxConcurrentTasks: 2
    }],
    ...overrides
  }
}

function makeContext(overrides: Partial<TaskContext> = {}): TaskContext {
  return {
    userRequest: 'Run the tests',
    sessionId: 'test-session',
    variables: {},
    ...overrides
  }
}

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    type: 'execution',
    description: 'Run the tests',
    priority: 'medium',
    status: 'pending',
    dependencies: [],
    context: makeContext(),
    createdAt: new Date(),
    updatedAt: new Date(),
    ...overrides
  }
}

describe('ExecutorAgent', () => {
  let agent: ExecutorAgent

  beforeEach(() => {
    agent = new ExecutorAgent(makeConfig())
  })

  afterEach(() => {
    agent.destroy()
  })

  describe('Initialization', () => {
    it('should create with correct capabilities', () => {
      const caps = agent.getCapabilities()
      expect(caps).toContain('command_execution')
      expect(caps).toContain('test_execution')
      expect(caps).toContain('deployment')
      expect(caps).toContain('environment_setup')
      expect(caps).toContain('process_management')
      expect(caps).toContain('verification')
    })

    it('should start with idle status', () => {
      expect(agent.getStatus()).toBe('idle')
    })

    it('should start with empty execution history', () => {
      expect(agent.getExecutionHistory()).toEqual([])
    })

    it('should have stats with zero executions', () => {
      const stats = agent.getStats()
      expect(stats.totalExecutions).toBe(0)
      expect(stats.successRate).toBe(0)
      expect(stats.averageDuration).toBe(0)
    })
  })

  describe('executeTask - test execution', () => {
    it('should execute a test command task', async () => {
      const task = makeTask({ description: 'run the tests' })
      const result = await agent.runTask(task)

      expect(result.success).toBe(true)
      expect(result.output).toBeDefined()
      expect(result.artifacts).toBeDefined()
    })

    it('should run build commands', async () => {
      const task = makeTask({ description: 'build the project' })
      const result = await agent.runTask(task)

      expect(result.success).toBe(true)
      expect(result.output).toBeDefined()
    })

    it('should handle deploy commands', async () => {
      const task = makeTask({ description: 'deploy to production' })
      const result = await agent.runTask(task)

      expect(result.success).toBe(true)
    })

    it('should handle verify commands', async () => {
      const task = makeTask({ description: 'verify the deployment' })
      const result = await agent.runTask(task)

      expect(result.success).toBe(true)
    })

    it('should handle tasks with plan context', async () => {
      const task = makeTask({
        description: 'Fallback',
        context: makeContext({
          userRequest: 'Run the test suite',
          variables: {
            plan: {
              steps: [{ instruction: 'Run npm test' }]
            }
          }
        })
      })
      const result = await agent.runTask(task)
      expect(result.success).toBe(true)
    })

    it('should produce output with execution report structure', async () => {
      const task = makeTask({ description: 'run the tests' })
      const result = await agent.runTask(task)

      expect(result.success).toBe(true)
      const output = result.output as any
      expect(output).toHaveProperty('success')
      expect(output).toHaveProperty('output')
      expect(output).toHaveProperty('errors')
    })
  })

  describe('deployment tasks', () => {
    it('should handle deploy to staging', async () => {
      const task = makeTask({ description: 'deploy to staging environment' })
      const result = await agent.runTask(task)

      expect(result.success).toBe(true)
      const output = result.output as any
      expect(output.success).toBe(true)
    })

    it('should handle deploy with plan context', async () => {
      const task = makeTask({
        description: 'Deploy this',
        context: makeContext({
          variables: {
            plan: {
              steps: [{ instruction: 'deploy to production' }]
            }
          }
        })
      })
      const result = await agent.runTask(task)
      expect(result.success).toBe(true)
    })
  })

  describe('execution history', () => {
    it('should accumulate execution history', async () => {
      await agent.runTask(makeTask({ id: 't1', description: 'run the tests' }))
      await agent.runTask(makeTask({ id: 't2', description: 'run lint' }))

      const history = agent.getExecutionHistory()
      expect(history.length).toBe(2)
    })

    it('should return a copy of history (immutable)', async () => {
      await agent.runTask(makeTask({ description: 'run tests' }))
      const history = agent.getExecutionHistory()
      history.push({ success: true, output: '', errors: [], warnings: [], duration: 100, exitCode: 0 })
      expect(agent.getExecutionHistory().length).toBe(1)
    })
  })

  describe('stats', () => {
    it('should calculate correct stats after executions', async () => {
      await agent.runTask(makeTask({ id: 't1', description: 'run tests' }))
      await agent.runTask(makeTask({ id: 't2', description: 'run lint' }))
      await agent.runTask(makeTask({ id: 't3', description: 'run build' }))

      const stats = agent.getStats()
      expect(stats.totalExecutions).toBe(3)
      expect(stats.successRate).toBeGreaterThan(0)
      expect(stats.averageDuration).toBeGreaterThanOrEqual(0)
    })

    it('should return zero stats with no executions', () => {
      const stats = agent.getStats()
      expect(stats.totalExecutions).toBe(0)
      expect(stats.successRate).toBe(0)
      expect(stats.averageDuration).toBe(0)
    })
  })

  describe('tool execution', () => {
    it('should have run_command tool registered', async () => {
      const result = await agent.executeTool('run_command', { command: 'echo test' })
      expect(result.success).toBe(true)
    })

    it('should have run_tests tool registered', async () => {
      const result = await agent.executeTool('run_tests', {})
      expect(result.success).toBe(true)
      const output = result.output as any
      expect(output.passed).toBe(10)
      expect(output.failed).toBe(0)
    })

    it('should have build tool registered', async () => {
      const result = await agent.executeTool('build', {})
      expect(result.success).toBe(true)
      const output = result.output as any
      expect(output.artifacts).toBeDefined()
    })

    it('should have deploy tool registered', async () => {
      const result = await agent.executeTool('deploy', { environment: 'staging' })
      expect(result.success).toBe(true)
      const output = result.output as any
      expect(output.url).toBeDefined()
    })

    it('should have verify tool registered', async () => {
      const result = await agent.executeTool('verify', {
        target: 'deployment',
        checks: ['health_check', 'smoke_test']
      })
      expect(result.success).toBe(true)
      const output = result.output as any
      expect(output.passed).toBe(2)
    })

    it('should return error for unknown tool', async () => {
      const result = await agent.executeTool('nonexistent', {})
      expect(result.success).toBe(false)
      expect(result.error).toContain('not found')
    })
  })

  describe('task composition', () => {
    it('should handle build+test+deploy pipeline', async () => {
      const task = makeTask({ description: 'build and run the tests and deploy to staging' })
      const result = await agent.runTask(task)

      expect(result.success).toBe(true)
      const output = result.output as any
      // The output field should contain execution output text
      expect(output.output).toBeDefined()
    })

    it('should handle task with only test execution', async () => {
      const task = makeTask({ description: 'run npm test' })
      const result = await agent.runTask(task)
      expect(result.success).toBe(true)
    })
  })
})
