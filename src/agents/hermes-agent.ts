/**
 * Hermes Agent Integration
 * Wraps the Nous Research Hermes Agent as a workforce agent
 */

import { spawn, ChildProcess } from 'child_process'
import { BaseAgent, AgentTool } from './base-agent'
import { AgentConfig, Task, TaskResult, TaskContext, AgentMessage } from '../types'
import { v4 as uuid } from 'uuid'

// Hermes Agent configuration
export interface HermesAgentConfig extends AgentConfig {
  hermesPath?: string
  model?: string
  personality?: string
}

export class HermesAgent extends BaseAgent {
  private hermesProcess: ChildProcess | null = null
  private messageBuffer: string = ''
  private pendingRequests: Map<string, {
    resolve: (result: TaskResult) => void
    reject: (error: Error) => void
  }> = new Map()
  private hermesPath: string
  private sessionId: string
  private serverlessFallback: boolean = false

  constructor(config: HermesAgentConfig) {
    super(config)
    
    // Detect serverless environment
    this.serverlessFallback = !!(process.env.VERCEL || process.env.AWS_LAMBDA_FUNCTION_NAME || process.env.FUNCTIONS_ROLE)
    
    // Set Hermes path - check common locations
    if (config.hermesPath) {
      this.hermesPath = config.hermesPath
    } else if (process.platform === 'win32') {
      // Windows: check common installation paths
      this.hermesPath = process.env.HERMES_PATH || 'hermes'
    } else {
      // Unix: use PATH or common install locations
      this.hermesPath = process.env.HERMES_PATH || 'hermes'
    }
    
    this.sessionId = `workforce-${uuid()}`
    
    // Skip Hermes initialization in serverless - it won't work there
    if (!this.serverlessFallback) {
      this.initializeHermes()
    } else {
      console.log('[HermesAgent] Running in serverless mode - Hermes CLI not available')
      this.setStatus('idle')
    }
  }

  private isServerless(): boolean {
    return this.serverlessFallback
  }

  private async initializeHermes(): Promise<void> {
    try {
      // Start Hermes in CLI mode with JSON output
      this.hermesProcess = spawn(this.hermesPath, ['--json', '--session', this.sessionId], {
        stdio: ['pipe', 'pipe', 'pipe']
      })

      if (this.hermesProcess.stdout) {
        this.hermesProcess.stdout.on('data', (data: Buffer) => {
          this.handleHermesOutput(data.toString())
        })
      }

      if (this.hermesProcess.stderr) {
        this.hermesProcess.stderr.on('data', (data: Buffer) => {
          console.error(`Hermes stderr: ${data.toString()}`)
        })
      }

      this.hermesProcess.on('error', (error) => {
        console.error(`Hermes process error: ${error.message}`)
        this.setStatus('failed')
      })

      this.hermesProcess.on('exit', (code) => {
        if (code !== 0) {
          console.warn(`Hermes exited with code ${code}`)
          this.setStatus('idle')
        }
      })

      this.setStatus('idle')
      this.emit('hermes:initialized', { sessionId: this.sessionId })
    } catch (error) {
      console.error('Failed to initialize Hermes:', error)
      this.setStatus('failed')
    }
  }

  private handleHermesOutput(data: string): void {
    this.messageBuffer += data
    
    // Try to parse complete JSON messages (newline-delimited)
    const lines = this.messageBuffer.split('\n')
    this.messageBuffer = lines.pop() || ''

    for (const line of lines) {
      if (line.trim()) {
        try {
          const message = JSON.parse(line)
          this.processHermesMessage(message)
        } catch {
          // Not JSON, treat as regular output
          this.emit('hermes:output', { text: line })
        }
      }
    }
  }

  private processHermesMessage(message: {
    type?: string
    requestId?: string
    response?: string
    error?: string
  }): void {
    if (message.requestId && this.pendingRequests.has(message.requestId)) {
      const pending = this.pendingRequests.get(message.requestId)!
      this.pendingRequests.delete(message.requestId)

      if (message.error) {
        pending.resolve({
          success: false,
          error: message.error
        })
      } else {
        pending.resolve({
          success: true,
          output: message.response
        })
      }
    }

    this.emit('hermes:message', message)
  }

  getCapabilities(): string[] {
    return [
      'natural_language_understanding',
      'code_generation',
      'problem_solving',
      'research',
      'reasoning',
      'self_improvement',
      'memory_persistence',
      'tool_use',
      'multi_turn_conversation',
      'skill_creation'
    ]
  }

  async executeTask(task: Task): Promise<TaskResult> {
    this.setStatus('working')

    try {
      const result = await this.sendToHermes(task.description, task.context)

      this.setStatus('completed')
      return {
        success: true,
        output: result.output,
        artifacts: [{
          name: 'hermes-response',
          type: 'data',
          content: JSON.stringify(result.output)
        }]
      }
    } catch (error) {
      this.setStatus('failed')
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error)
      }
    }
  }

  private sendToHermes(message: string, context: TaskContext): Promise<{ output: unknown }> {
    // Serverless fallback - Hermes CLI not available
    if (this.isServerless()) {
      return Promise.reject(new Error('Hermes CLI not available in serverless environment. For full functionality, run the agent-workforce server locally with Hermes installed.'))
    }

    return new Promise((resolve, reject) => {
      if (!this.hermesProcess) {
        reject(new Error('Hermes process not initialized'))
        return
      }

      const requestId = uuid()

      // Format message with context
      const fullMessage = {
        requestId,
        message,
        context: context.variables,
        sessionId: this.sessionId
      }

      // Store pending request
      this.pendingRequests.set(requestId, {
        resolve: (result) => {
          if (result.success) {
            resolve({ output: result.output })
          } else {
            reject(new Error(result.error || 'Hermes request failed'))
          }
        },
        reject
      })

      // Send to Hermes
      if (this.hermesProcess.stdin) {
        this.hermesProcess.stdin.write(JSON.stringify(fullMessage) + '\n')

        // Timeout after 60 seconds
        setTimeout(() => {
          if (this.pendingRequests.has(requestId)) {
            this.pendingRequests.delete(requestId)
            reject(new Error('Hermes request timeout'))
          }
        }, 60000)
      } else {
        reject(new Error('Hermes stdin not available'))
      }
    })
  }

  // Direct chat with Hermes (non-task use)
  async chat(message: string): Promise<string> {
    try {
      const result = await this.sendToHermes(message, {
        userRequest: message,
        sessionId: this.sessionId,
        variables: {}
      })
      return String(result.output || 'No response')
    } catch (error) {
      return `Error: ${error instanceof Error ? error.message : String(error)}`
    }
  }

  // Execute a skill
  async executeSkill(skillName: string, params?: Record<string, unknown>): Promise<TaskResult> {
    return this.executeTask({
      id: `skill-${uuid()}`,
      type: 'skill',
      description: `/skill ${skillName} ${params ? JSON.stringify(params) : ''}`,
      priority: 'medium',
      status: 'pending',
      dependencies: [],
      context: {
        userRequest: `Execute skill: ${skillName}`,
        sessionId: this.sessionId,
        variables: { skillName, params }
      },
      createdAt: new Date(),
      updatedAt: new Date()
    })
  }

  // Get Hermes status
  getHermesStatus(): {
    initialized: boolean
    sessionId: string
    pendingRequests: number
  } {
    return {
      initialized: this.hermesProcess !== null,
      sessionId: this.sessionId,
      pendingRequests: this.pendingRequests.size
    }
  }

  // Register a tool for Hermes to use
  registerHermesTool(tool: AgentTool): void {
    this.registerTool(tool)
    this.emit('hermes:toolRegistered', { toolName: tool.name })
  }

  protected async processMessage(message: AgentMessage): Promise<void> {
    if (message.type === 'task' && message.payload) {
      const payload = message.payload as { instruction: string; context: TaskContext }
      const result = await this.executeTask({
        id: message.taskId || `msg-${uuid()}`,
        type: 'delegated',
        description: payload.instruction,
        priority: 'medium',
        status: 'pending',
        dependencies: [],
        context: payload.context,
        createdAt: new Date(),
        updatedAt: new Date()
      })

      this.sendMessage({
        id: uuid(),
        type: 'result',
        senderId: this.id,
        recipientId: message.senderId,
        taskId: message.taskId,
        correlationId: message.correlationId,
        payload: result,
        timestamp: new Date(),
        priority: 'normal'
      })
    }
  }

  destroy(): void {
    if (this.hermesProcess) {
      this.hermesProcess.kill()
      this.hermesProcess = null
    }
    this.pendingRequests.clear()
    super.destroy()
  }
}