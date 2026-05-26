/**
 * Coder Agent
 * Specialized agent for writing, implementing, and refactoring code
 */

import { BaseAgent, ToolResult } from './base-agent'
import { AgentConfig, Task, TaskResult, TaskContext } from '../types'
import { v4 as uuid } from 'uuid'

export interface CodeImplementation {
  language: string
  files: CodeFile[]
  tests?: CodeFile[]
  documentation?: string
}

export interface CodeFile {
  path: string
  content: string
  language: string
  purpose: string
}

export interface CodeAnalysis {
  issues: CodeIssue[]
  suggestions: string[]
  complexity: number
  maintainability: number
}

export interface CodeIssue {
  severity: 'error' | 'warning' | 'info'
  line?: number
  message: string
  rule?: string
}

export class CoderAgent extends BaseAgent {
  private projectContext: Map<string, unknown> = new Map()

  constructor(config: AgentConfig) {
    super(config)
    this.registerDefaultTools()
  }

  getCapabilities(): string[] {
    return [
      'code_generation',
      'code_refactoring',
      'code_review',
      'debugging',
      'testing',
      'documentation'
    ]
  }

  private registerDefaultTools(): void {
    // Code generation tool
    this.registerTool({
      name: 'generate_code',
      description: 'Generate code based on specification',
      execute: async (params: unknown) => {
        const p = params as { spec: string; language?: string }
        return {
          success: true,
          output: {
            files: [{
              path: `generated.${p.language || 'ts'}`,
              content: `// Generated code for: ${p.spec}\nconsole.log('Hello');`,
              language: p.language || 'typescript'
            }]
          },
          duration: 1000
        }
      }
    })

    // Code analysis tool
    this.registerTool({
      name: 'analyze_code',
      description: 'Analyze code for issues and improvements',
      execute: async (params: unknown) => {
        return {
          success: true,
          output: {
            issues: [],
            suggestions: ['Consider adding type annotations', 'Add error handling'],
            complexity: 5,
            maintainability: 8
          },
          duration: 500
        }
      }
    })

    // Code formatting tool
    this.registerTool({
      name: 'format_code',
      description: 'Format code according to language best practices',
      execute: async (params: unknown) => {
        const p = params as { code: string; language: string }
        return {
          success: true,
          output: { formatted: p.code },
          duration: 200
        }
      }
    })

    // Test generation tool
    this.registerTool({
      name: 'generate_tests',
      description: 'Generate unit tests for code',
      execute: async (params: unknown) => {
        return {
          success: true,
          output: {
            testFiles: [{
              path: `test.spec.ts`,
              content: `// Tests for the code\ndescribe('Tests', () => { it('works', () => {}); });`,
              language: 'typescript'
            }]
          },
          duration: 800
        }
      }
    })
  }

  async executeTask(task: Task): Promise<TaskResult> {
    const context = task.context
    const instruction = this.extractInstruction(task)

    try {
      // Step 1: Understand the implementation requirements
      const requirements = this.parseRequirements(instruction)

      // Step 2: Generate implementation
      const implementation = await this.generateImplementation(requirements, context)

      // Step 3: Add tests
      const tests = await this.generateTests(implementation)

      // Step 4: Generate documentation
      const documentation = this.generateDocumentation(implementation)

      return {
        success: true,
        output: {
          implementation,
          tests,
          documentation
        },
        artifacts: [
          ...implementation.files.map(file => ({
            name: file.path,
            type: 'code' as const,
            path: file.path,
            content: file.content,
            metadata: { language: file.language, purpose: file.purpose }
          })),
          ...tests.files.map(file => ({
            name: file.path,
            type: 'code' as const,
            path: file.path,
            content: file.content,
            metadata: { language: file.language, purpose: 'test' }
          }))
        ]
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

  private parseRequirements(instruction: string): {
    language: string
    functionality: string
    constraints: string[]
  } {
    const langMatch = instruction.match(/\b(ts|typescript|js|javascript|py|python|go|rust|java|csharp)\b/i)
    
    return {
      language: langMatch ? langMatch[1].toLowerCase() : 'typescript',
      functionality: instruction,
      constraints: []
    }
  }

  private async generateImplementation(
    requirements: { language: string; functionality: string },
    context: TaskContext
  ): Promise<CodeImplementation> {
    // Use code generation tool
    const result = await this.executeTool('generate_code', {
      spec: requirements.functionality,
      language: requirements.language
    })

    const files: CodeFile[] = result.success && result.output
      ? (result.output as { files?: CodeFile[] }).files || []
      : []

    return {
      language: requirements.language,
      files,
      tests: []
    }
  }

  private async generateTests(implementation: CodeImplementation): Promise<{ files: CodeFile[] }> {
    const testFiles: CodeFile[] = []

    for (const file of implementation.files) {
      const result = await this.executeTool('generate_tests', {
        code: file.content,
        framework: 'vitest'
      })

      if (result.success && result.output) {
        const testData = result.output as { testFiles?: CodeFile[] }
        if (testData.testFiles) {
          testFiles.push(...testData.testFiles)
        }
      }
    }

    return { files: testFiles }
  }

  private generateDocumentation(implementation: CodeImplementation): string {
    const fileList = implementation.files.map(f => `- \`${f.path}\`: ${f.purpose}`).join('\n')
    
    return `# Implementation Documentation\n\n## Files\n${fileList}\n\n## Overview\nThis implementation provides the requested functionality.\n\n## Usage\nSee individual file documentation for usage instructions.`
  }

  // Set project context for better code generation
  setProjectContext(key: string, value: unknown): void {
    this.projectContext.set(key, value)
  }

  getProjectContext(): Record<string, unknown> {
    return Object.fromEntries(this.projectContext)
  }
}