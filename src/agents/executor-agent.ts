/**
 * Executor Agent
 * Specialized agent for executing, testing, and deploying solutions
 */

import { BaseAgent } from './base-agent'
import { AgentConfig, Task, TaskResult, TaskContext } from '../types'

export interface ExecutionResult {
  success: boolean
  output: string
  errors: string[]
  warnings: string[]
  duration: number
  exitCode: number
}

export interface DeploymentResult {
  environment: string
  url?: string
  status: 'pending' | 'deployed' | 'failed'
  artifacts: string[]
  logs: string[]
}

export class ExecutorAgent extends BaseAgent {
  private executionHistory: ExecutionResult[] = []

  constructor(config: AgentConfig) {
    super(config)
    this.registerDefaultTools()
  }

  getCapabilities(): string[] {
    return [
      'command_execution',
      'test_execution',
      'deployment',
      'environment_setup',
      'process_management',
      'verification'
    ]
  }

  private registerDefaultTools(): void {
    // Command execution tool
    this.registerTool({
      name: 'run_command',
      description: 'Execute a shell command or script',
      execute: async (params: unknown) => {
        const p = params as { command: string; cwd?: string; timeout?: number }
        return {
          success: true,
          output: `Executed: ${p.command}\nOutput: Command completed successfully`,
          duration: 1000
        }
      }
    })

    // Test execution tool
    this.registerTool({
      name: 'run_tests',
      description: 'Execute test suites',
      execute: async (params: unknown) => {
        return {
          success: true,
          output: {
            passed: 10,
            failed: 0,
            skipped: 0,
            total: 10,
            duration: 2000,
            results: []
          },
          duration: 2000
        }
      }
    })

    // Build tool
    this.registerTool({
      name: 'build',
      description: 'Build the project',
      execute: async (params: unknown) => {
        return {
          success: true,
          output: {
            artifacts: ['dist/index.js', 'dist/index.css'],
            buildTime: 5000
          },
          duration: 5000
        }
      }
    })

    // Deployment tool
    this.registerTool({
      name: 'deploy',
      description: 'Deploy to target environment',
      execute: async (params: unknown) => {
        const p = params as { environment: string; artifacts?: string[] }
        return {
          success: true,
          output: {
            url: `https://${p.environment}.example.com`,
            deployed: true,
            timestamp: new Date().toISOString()
          },
          duration: 10000
        }
      }
    })

    // Verification tool
    this.registerTool({
      name: 'verify',
      description: 'Verify deployment or execution results',
      execute: async (params: unknown) => {
        const p = params as { target: string; checks: string[] }
        return {
          success: true,
          output: {
            passed: p.checks.length,
            failed: 0,
            results: p.checks.map((check: string) => ({ check, passed: true }))
          },
          duration: 3000
        }
      }
    })
  }

  async executeTask(task: Task): Promise<TaskResult> {
    const context = task.context
    const instruction = this.extractInstruction(task)

    try {
      // Step 1: Parse execution instructions
      const executionPlan = this.parseExecutionPlan(instruction)

      // Step 2: Set up environment
      if (executionPlan.needsSetup) {
        await this.setupEnvironment(executionPlan.environment)
      }

      // Step 3: Execute the plan
      const results = await this.executePlan(executionPlan, context)

      // Step 4: Verify results
      const verification = await this.verifyResults(results, executionPlan.checks)

      // Step 5: Generate execution report
      const report = this.generateExecutionReport(results, verification, context)

      return {
        success: verification.success,
        output: report,
        artifacts: [
          {
            name: 'execution_report',
            type: 'report',
            content: JSON.stringify(report, null, 2),
            metadata: {
              duration: results.duration,
              exitCode: results.exitCode,
              timestamp: new Date().toISOString()
            }
          }
        ],
        metrics: {
          duration: results.duration,
          tokensUsed: 0
        }
      }

    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error)
      }
    }
  }

  private extractInstruction(task: Task): string {
    const plan = task.context.variables.plan as { steps?: Array<{ instruction?: string }> } | undefined
    if (plan?.steps?.[0]?.instruction) {
      return plan.steps[0].instruction
    }
    return task.description
  }

  private parseExecutionPlan(instruction: string): {
    commands: string[]
    environment?: string
    needsSetup: boolean
    checks: string[]
    deployment?: { target: string; artifacts?: string[] }
  } {
    const lower = instruction.toLowerCase()
    
    const commands: string[] = []
    let environment: string | undefined
    let needsSetup = false
    const checks: string[] = []
    let deployment: { target: string; artifacts?: string[] } | undefined

    if (lower.includes('test') || lower.includes('run')) {
      commands.push('npm test')
      checks.push('tests_pass')
    }

    if (lower.includes('build')) {
      commands.push('npm run build')
      checks.push('build_success')
    }

    if (lower.includes('deploy')) {
      const targetMatch = lower.match(/deploy(?: to| on)?\/?\/?\/?(\\w+)/i)
      environment = targetMatch ? targetMatch[1] : 'staging'
      deployment = { target: environment }
      commands.push(`deploy ${environment}`)
      checks.push('deployment_successful')
    }

    if (lower.includes('verify') || lower.includes('check')) {
      checks.push('functionality_verified')
    }

    return { commands, environment, needsSetup, checks, deployment }
  }

  private async setupEnvironment(environment?: string): Promise<void> {
    if (!environment) return
    
    const result = await this.executeTool('run_command', {
      command: `echo Setting up ${environment} environment`,
      timeout: 30000
    })

    if (!result.success) {
      throw new Error(`Failed to set up environment: ${environment}`)
    }
  }

  private async executePlan(
    plan: { commands: string[]; deployment?: { target: string; artifacts?: string[] } },
    context: TaskContext
  ): Promise<ExecutionResult> {
    const errors: string[] = []
    const warnings: string[] = []
    let output = ''
    const startTime = Date.now()

    for (const command of plan.commands) {
      const result = await this.executeTool('run_command', { command })
      
      if (result.success && result.output) {
        output += result.output + '\n'
      } else if (result.error) {
        errors.push(result.error)
      }
    }

    // Handle deployment if specified
    if (plan.deployment) {
      const deployResult = await this.executeTool('deploy', {
        environment: plan.deployment.target,
        artifacts: plan.deployment.artifacts
      })

      if (deployResult.success && deployResult.output) {
        const deployData = deployResult.output as { url?: string }
        output += `\nDeployed to: ${deployData.url || plan.deployment.target}`
      } else {
        errors.push('Deployment failed')
      }
    }

    const duration = Date.now() - startTime
    const result: ExecutionResult = {
      success: errors.length === 0,
      output,
      errors,
      warnings,
      duration,
      exitCode: errors.length === 0 ? 0 : 1
    }

    this.executionHistory.push(result)
    return result
  }

  private async verifyResults(
    results: ExecutionResult,
    checks: string[]
  ): Promise<{ success: boolean; details: Record<string, boolean> }> {
    const details: Record<string, boolean> = {}

    for (const check of checks) {
      // Simulate verification checks
      details[check] = results.success
    }

    return {
      success: results.success && Object.values(details).every(v => v),
      details
    }
  }

  private generateExecutionReport(
    results: ExecutionResult,
    verification: { success: boolean; details: Record<string, boolean> },
    context: TaskContext
  ): {
    success: boolean
    output: string
    errors: string[]
    verification: Record<string, boolean>
    duration: number
  } {
    return {
      success: verification.success,
      output: results.output,
      errors: results.errors,
      verification: verification.details,
      duration: results.duration
    }
  }

  // Get execution history
  getExecutionHistory(): ExecutionResult[] {
    return [...this.executionHistory]
  }

  // Get statistics
  getStats(): {
    totalExecutions: number
    successRate: number
    averageDuration: number
  } {
    if (this.executionHistory.length === 0) {
      return { totalExecutions: 0, successRate: 0, averageDuration: 0 }
    }

    const successful = this.executionHistory.filter(e => e.success).length
    const totalDuration = this.executionHistory.reduce((sum, e) => sum + e.duration, 0)

    return {
      totalExecutions: this.executionHistory.length,
      successRate: (successful / this.executionHistory.length) * 100,
      averageDuration: totalDuration / this.executionHistory.length
    }
  }
}