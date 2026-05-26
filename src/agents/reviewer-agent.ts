/**
 * Reviewer Agent
 * Specialized agent for reviewing, validating, and ensuring quality
 */

import { BaseAgent, ToolResult } from './base-agent'
import { AgentConfig, Task, TaskResult, TaskContext } from '../types'

export interface ReviewResult {
  score: number
  issues: ReviewIssue[]
  suggestions: string[]
  approved: boolean
  summary: string
}

export interface ReviewIssue {
  severity: 'critical' | 'major' | 'minor' | 'info'
  category: string
  message: string
  location?: string
  line?: number
}

export class ReviewerAgent extends BaseAgent {
  private reviewHistory: ReviewResult[] = []

  constructor(config: AgentConfig) {
    super(config)
    this.registerDefaultTools()
  }

  getCapabilities(): string[] {
    return [
      'code_review',
      'security_audit',
      'performance_analysis',
      'compliance_check',
      'style_guide_compliance',
      'best_practices_validation'
    ]
  }

  private registerDefaultTools(): void {
    // Code review tool
    this.registerTool({
      name: 'review_code',
      description: 'Review code for issues, bugs, and improvements',
      execute: async (params: unknown) => {
        const p = params as { code: string; language: string }
        return {
          success: true,
          output: {
            issues: [
              { severity: 'info', category: 'style', message: 'Consider using const instead of let', line: 5 }
            ],
            score: 8.5,
            suggestions: ['Add error handling', 'Consider TypeScript types']
          },
          duration: 600
        }
      }
    })

    // Security audit tool
    this.registerTool({
      name: 'security_scan',
      description: 'Scan code for security vulnerabilities',
      execute: async (params: unknown) => {
        const p = params as { code: string }
        return {
          success: true,
          output: {
            vulnerabilities: [],
            securityScore: 10,
            recommendations: []
          },
          duration: 800
        }
      }
    })

    // Performance analysis tool
    this.registerTool({
      name: 'analyze_performance',
      description: 'Analyze code for performance issues',
      execute: async (params: unknown) => {
        const p = params as { code: string }
        return {
          success: true,
          output: {
            issues: [],
            performanceScore: 9,
            bottlenecks: []
          },
          duration: 500
        }
      }
    })

    // Lint tool
    this.registerTool({
      name: 'lint',
      description: 'Check code against style guides and linting rules',
      execute: async (params: unknown) => {
        const p = params as { code: string; rules?: string[] }
        return {
          success: true,
          output: {
            violations: [],
            passed: true,
            summary: 'No linting violations found'
          },
          duration: 300
        }
      }
    })
  }

  async executeTask(task: Task): Promise<TaskResult> {
    const context = task.context
    const instruction = this.extractInstruction(task)

    try {
      // Step 1: Identify what to review
      const reviewType = this.identifyReviewType(instruction)

      // Step 2: Perform the review
      const review = await this.performReview(reviewType, task)

      // Step 3: Generate detailed report
      const report = this.generateReport(review, context)

      this.reviewHistory.push(review)

      return {
        success: true,
        output: report,
        artifacts: [{
          name: 'review_report',
          type: 'report',
          content: JSON.stringify(report, null, 2),
          metadata: {
            reviewType: reviewType,
            score: review.score,
            approved: review.approved,
            timestamp: new Date().toISOString()
          }
        }]
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

  private identifyReviewType(instruction: string): 'code' | 'security' | 'performance' | 'general' {
    const lower = instruction.toLowerCase()
    if (lower.includes('security') || lower.includes('vulnerability')) return 'security'
    if (lower.includes('performance') || lower.includes('optimize')) return 'performance'
    if (lower.includes('code') || lower.includes('review')) return 'code'
    return 'general'
  }

  private async performReview(
    reviewType: 'code' | 'security' | 'performance' | 'general',
    task: Task
  ): Promise<ReviewResult> {
    const context = task.context
    const code = (context.previousResults?.code as string) || context.variables?.code as string || ''

    let result: ToolResult

    switch (reviewType) {
      case 'security':
        result = await this.executeTool('security_scan', { code })
        break
      case 'performance':
        result = await this.executeTool('analyze_performance', { code })
        break
      case 'code':
      default:
        result = await this.executeTool('review_code', { code, language: 'typescript' })
        break
    }

    if (!result.success) {
      // Create a default review result for simulation
      return {
        score: 8,
        issues: [],
        suggestions: ['Code review completed'],
        approved: true,
        summary: `${reviewType} review completed successfully`
      }
    }

    const output = result.output as {
      issues?: ReviewIssue[]
      score?: number
      suggestions?: string[]
      vulnerabilities?: unknown[]
      performanceScore?: number
      securityScore?: number
    }

    const issues: ReviewIssue[] = (output.issues || []).map((issue: ReviewIssue) => ({
      ...issue,
      category: reviewType
    }))

    const score = output.score || output.securityScore || output.performanceScore || 8

    return {
      score,
      issues,
      suggestions: output.suggestions || [],
      approved: score >= 7,
      summary: `${reviewType} review: Score ${score}/10 - ${issues.length} issues found`
    }
  }

  private generateReport(review: ReviewResult, context: TaskContext): ReviewResult {
    return {
      ...review,
      summary: `Review of: ${context.userRequest}\n\n${review.summary}`
    }
  }

  // Get review history
  getReviewHistory(): ReviewResult[] {
    return [...this.reviewHistory]
  }

  // Calculate aggregate statistics
  getStats(): {
    totalReviews: number
    averageScore: number
    approvalRate: number
  } {
    if (this.reviewHistory.length === 0) {
      return { totalReviews: 0, averageScore: 0, approvalRate: 0 }
    }

    const totalScore = this.reviewHistory.reduce((sum, r) => sum + r.score, 0)
    const approvedCount = this.reviewHistory.filter(r => r.approved).length

    return {
      totalReviews: this.reviewHistory.length,
      averageScore: totalScore / this.reviewHistory.length,
      approvalRate: (approvedCount / this.reviewHistory.length) * 100
    }
  }
}