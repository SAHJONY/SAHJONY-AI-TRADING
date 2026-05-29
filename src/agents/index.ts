/**
 * Agents Index
 * Exports all agent types for the workforce system
 */

export { BaseAgent, AgentTool, ToolResult, registerAgent, createAgent, AgentConstructor } from './base-agent'
export { OrchestratorAgent } from './orchestrator'
export { ResearcherAgent } from './researcher-agent'
export { CoderAgent } from './coder-agent'
export { ReviewerAgent } from './reviewer-agent'
export { ExecutorAgent } from './executor-agent'
export { HermesAgent, HermesAgentConfig } from './hermes-agent'