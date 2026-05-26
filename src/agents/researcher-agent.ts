/**
 * Researcher Agent
 * Specialized agent for gathering, analyzing, and synthesizing information
 */

import { BaseAgent, ToolResult } from './base-agent'
import { AgentConfig, Task, TaskResult, TaskContext } from '../types'
import { v4 as uuid } from 'uuid'

export interface ResearchResult {
  query: string
  findings: ResearchFinding[]
  summary: string
  sources: string[]
  confidence: number
}

export interface ResearchFinding {
  topic: string
  content: string
  relevance: number
  source?: string
}

export class ResearcherAgent extends BaseAgent {
  private researchHistory: Map<string, ResearchResult> = new Map()

  constructor(config: AgentConfig) {
    super(config)
    this.registerDefaultTools()
  }

  getCapabilities(): string[] {
    return [
      'web_search',
      'document_analysis',
      'code_search',
      'data_gathering',
      'fact_checking',
      'summarization'
    ]
  }

  private registerDefaultTools(): void {
    // Web research tool
    this.registerTool({
      name: 'web_search',
      description: 'Search the web for information on a given topic',
      execute: async (params: unknown) => {
        const p = params as { query: string; limit?: number }
        return {
          success: true,
          output: {
            query: p.query,
            results: [
              { title: `Information about ${p.query}`, url: `https://example.com/${p.query}`, snippet: `Relevant findings on ${p.query}` }
            ],
            totalResults: 1
          },
          duration: 500
        }
      }
    })

    // Code search tool
    this.registerTool({
      name: 'code_search',
      description: 'Search codebases for relevant implementations',
      execute: async (params: unknown) => {
        const p = params as { query: string; scope?: string }
        return {
          success: true,
          output: {
            query: p.query,
            matches: [],
            filesSearched: 0
          },
          duration: 300
        }
      }
    })

    // Document analysis tool
    this.registerTool({
      name: 'analyze_document',
      description: 'Analyze documents or files for relevant information',
      execute: async (params: unknown) => {
        const p = params as { content: string; query: string }
        return {
          success: true,
          output: {
            relevantSections: [],
            entities: [],
            summary: `Analysis of document regarding: ${p.query}`
          },
          duration: 400
        }
      }
    })

    // Summarize tool
    this.registerTool({
      name: 'summarize',
      description: 'Summarize large amounts of text into concise key points',
      execute: async (params: unknown) => {
        const p = params as { text: string; maxLength?: number }
        return {
          success: true,
          output: {
            summary: p.text.substring(0, p.maxLength || 500),
            keyPoints: [],
            wordCount: p.text.split(/\n/).length
          },
          duration: 200
        }
      }
    })
  }

  async executeTask(task: Task): Promise<TaskResult> {
    const context = task.context
    const instruction = this.extractInstruction(task)
    
    try {
      // Step 1: Understand the research query
      const researchQuery = this.parseResearchQuery(instruction)

      // Step 2: Gather information using tools
      const findings = await this.gatherInformation(researchQuery)

      // Step 3: Analyze and synthesize
      const analysis = await this.analyzeFindings(findings, researchQuery)

      // Step 4: Generate comprehensive report
      const report = this.generateReport(analysis, context)

      return {
        success: true,
        output: report,
        artifacts: [
          {
            name: 'research_report',
            type: 'report',
            content: JSON.stringify(report, null, 2),
            metadata: { query: researchQuery, timestamp: new Date().toISOString() }
          }
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
    // Extract the research instruction from the task
    const plan = task.context.variables.plan as { steps?: Array<{ instruction?: string }> } | undefined
    if (plan?.steps?.[0]?.instruction) {
      return plan.steps[0].instruction
    }
    return task.description
  }

  private parseResearchQuery(instruction: string): string {
    // Extract the actual research topic from the instruction
    const patterns = [
      /research(?:and)?\/?(?:\bgather information about\b)?:?\/?\/?\/?(.+)/i,
      /find(?:information about|details on):?\/?(.+)/i,
      /analyze:?\/?(.+)/i,
      /investigat(?:e|ion):?\/?(.+)/i
    ]

    for (const pattern of patterns) {
      const match = instruction.match(pattern)
      if (match && match[1]) {
        return match[1].trim()
      }
    }

    return instruction
  }

  private async gatherInformation(query: string): Promise<ResearchFinding[]> {
    const findings: ResearchFinding[] = []

    // Use web search
    const webResult = await this.executeTool('web_search', { query, limit: 10 })
    if (webResult.success && webResult.output) {
      const searchData = webResult.output as { results?: Array<{ title: string; snippet: string }> }
      if (searchData.results) {
        for (const result of searchData.results) {
          findings.push({
            topic: query,
            content: result.snippet,
            relevance: 0.8,
            source: result.title
          })
        }
      }
    }

    // Use code search if relevant
    if (query.toLowerCase().includes('code') || query.toLowerCase().includes('implement')) {
      const codeResult = await this.executeTool('code_search', { query })
      if (codeResult.success && codeResult.output) {
        const codeData = codeResult.output as { matches?: unknown[] }
        // Process code search results
      }
    }

    return findings
  }

  private async analyzeFindings(findings: ResearchFinding[], query: string): Promise<{
    summary: string
    keyInsights: string[]
    confidence: number
  }> {
    // Synthesize findings into key insights
    const keyInsights = findings.map(f => f.content).filter(Boolean)

    return {
      summary: `Research on ${query} yielded ${findings.length} relevant findings`,
      keyInsights,
      confidence: Math.min(0.5 + (findings.length * 0.05), 1.0)
    }
  }

  private generateReport(analysis: { summary: string; keyInsights: string[]; confidence: number }, context: TaskContext): ResearchResult {
    const reportId = uuid()
    const report: ResearchResult = {
      query: context.userRequest,
      findings: analysis.keyInsights.map(insight => ({
        topic: 'General',
        content: insight,
        relevance: 0.7
      })),
      summary: analysis.summary,
      sources: [],
      confidence: analysis.confidence
    }

    this.researchHistory.set(reportId, report)

    return report
  }

  // Get historical research data
  getResearchHistory(): ResearchResult[] {
    return Array.from(this.researchHistory.values())
  }

  // Clear research history
  clearHistory(): void {
    this.researchHistory.clear()
  }
}