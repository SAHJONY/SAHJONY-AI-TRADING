/**
 * CLI Interface for Agent Workforce
 * Command-line tool for interacting with the multi-agent system
 */

import { createInterface } from 'readline'
import { v4 as uuid } from 'uuid'
import { OrchestrationEngine, getEngine, createEngine } from '../orchestration/engine'
import { TaskContext, AgentRole, TaskResult } from '../types'

const rl = createInterface({
  input: process.stdin,
  output: process.stdout
})

class AgentWorkforceCLI {
  private engine: OrchestrationEngine
  private sessionId: string

  constructor() {
    this.sessionId = `cli-${uuid()}`
    this.engine = getEngine()
    this.setupEventHandlers()
  }

  private setupEventHandlers(): void {
    this.engine.on('agent:spawned', (data: { agentId: string }) => {
      console.log(`[System] Agent spawned: ${data.agentId}`)
    })

    this.engine.on('agent:task_assigned', (data: { taskId: string; agentId: string }) => {
      console.log(`[System] Task ${data.taskId} assigned to ${data.agentId}`)
    })

    this.engine.on('agent:task_completed', (data: { taskId: string }) => {
      console.log(`[System] Task ${data.taskId} completed`)
    })

    this.engine.on('agent:error', (data: { taskId: string; error: string }) => {
      console.log(`[Error] Task ${data.taskId} failed: ${data.error}`)
    })
  }

  async start(): Promise<void> {
    console.log('\n========================================')
    console.log('   AGENT WORKFORCE CLI')
    console.log('   Multi-Agent Orchestration System')
    console.log('========================================\n')
    console.log('Type your requests and press Enter.')
    console.log('Commands: /help, /status, /agents, /tasks, /exit\n')

    this.showStatus()

    this.prompt()
  }

  private prompt(): void {
    rl.question('\n> ', async (input) => {
      const trimmed = input.trim()

      if (!trimmed) {
        this.prompt()
        return
      }

      if (trimmed.startsWith('/')) {
        await this.handleCommand(trimmed)
      } else {
        await this.handleRequest(trimmed)
      }

      this.prompt()
    })
  }

  private async handleCommand(command: string): Promise<void> {
    const [cmd] = command.split(' ')

    switch (cmd.toLowerCase()) {
      case '/help':
        this.showHelp()
        break
      case '/status':
        this.showStatus()
        break
      case '/agents':
        this.showAgents()
        break
      case '/tasks':
        this.showTasks()
        break
      case '/queue':
        this.showQueue()
        break
      case '/exit':
      case '/quit':
        console.log('\nShutting down agent workforce...\n')
        rl.close()
        process.exit(0)
      default:
        console.log(`Unknown command: ${cmd}`)
        console.log('Type /help for available commands')
    }
  }

  private async handleRequest(request: string): Promise<void> {
    console.log(`\n[Processing] ${request}\n`)

    try {
      const context: TaskContext = {
        userRequest: request,
        sessionId: this.sessionId,
        variables: {}
      }

      const task = await this.engine.submitTask(request, context, { priority: 'medium' })
      console.log(`[Task Created] ${task.id}`)

      const result = await this.waitForTask(task.id)
      
      if (result) {
        console.log('\n[Result]')
        if (result.success && result.output) {
          console.log(JSON.stringify(result.output, null, 2))
        } else if (result.error) {
          console.log(`Error: ${result.error}`)
        }
      }

    } catch (error) {
      console.error(`[Error] ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  private async waitForTask(taskId: string, maxWait = 60000): Promise<TaskResult | null> {
    const startTime = Date.now()
    
    while (Date.now() - startTime < maxWait) {
      const task = this.engine.getTask(taskId)
      if (task) {
        if (task.status === 'completed' || task.status === 'failed') {
          return task.result || null
        }
      }
      
      const allTasks = this.engine.getAllTasks()
      const completed = allTasks.find(t => t.id === taskId && (t.status === 'completed' || t.status === 'failed'))
      if (completed) {
        return completed.result || null
      }

      await new Promise(resolve => setTimeout(resolve, 500))
    }

    return null
  }

  private showHelp(): void {
    console.log(`
Available Commands:
  /help      - Show this help message
  /status    - Show system status
  /agents    - List all agents and their status
  /tasks     - Show completed tasks
  /queue     - Show pending tasks in queue
  /exit      - Exit the CLI
`)
  }

  private showStatus(): void {
    const status = this.engine.getStatus()
    console.log(`
System Status:
  Queue Length:    ${status.queueLength}
  Active Tasks:    ${status.activeTasks}
  Completed Tasks: ${status.completedTasks}
  Total Agents:    ${status.agents.length}
`)
  }

  private showAgents(): void {
    const status = this.engine.getStatus()
    console.log('\nActive Agents:')
    console.log('  ID                  Role          Status')
    console.log('  ─────────────────────────────────────────')
    for (const agent of status.agents) {
      console.log(`  ${agent.id.padEnd(18)} ${agent.role.padEnd(12)} ${agent.status}`)
    }
  }

  private showTasks(): void {
    const tasks = this.engine.getAllTasks()
    const completed = tasks.filter(t => t.status === 'completed' || t.status === 'failed')
    
    console.log(`\nCompleted Tasks (${completed.length}):`)
    console.log('  ID                  Status    Description')
    console.log('  ──────────────────────────────────────────────────────────────────')
    
    for (const task of completed.slice(-10)) {
      const desc = task.description.substring(0, 50) + (task.description.length > 50 ? '...' : '')
      console.log(`  ${task.id.padEnd(18)} ${(task.status as string).padEnd(9)} ${desc}`)
    }
  }

  private showQueue(): void {
    const status = this.engine.getStatus()
    console.log(`\nPending Tasks: ${status.queueLength}`)
    
    const tasks = this.engine.getAllTasks()
    const pending = tasks.filter(t => t.status === 'pending')
    
    console.log('  ID                  Priority')
    console.log('  ─────────────────────────────────────────')
    for (const task of pending.slice(0, 10)) {
      console.log(`  ${task.id.padEnd(18)} ${task.priority}`)
    }
  }
}

async function main() {
  createEngine({
    maxConcurrentAgents: 5,
    maxQueueSize: 100,
    defaultTimeout: 300000,
    enableRetry: true,
    maxRetries: 3
  })

  const cli = new AgentWorkforceCLI()
  await cli.start()
}

main().catch(console.error)

export { AgentWorkforceCLI }