/**
 * Agent Workforce - Main Entry Point
 * Multi-Agent Orchestration System with Autonomous Task Execution
 */

// Types
export * from './types'

// Agents
export * from './agents'

// Orchestration
export * from './orchestration'

// Re-export engine for convenience
export { getEngine, createEngine, OrchestrationEngine } from './orchestration/engine'

// Re-export ToolResult specifically
export type { ToolResult } from './agents/base-agent'