/**
 * Layer 4 — Unified LLM Provider Layer
 *
 * Abstracts OpenAI and Anthropic behind a single interface.
 * Each trading agent can be independently configured with its preferred provider/model.
 */

import { ChatOpenAI } from '@langchain/openai'
import { ChatAnthropic } from '@langchain/anthropic'
import { BaseChatModel } from '@langchain/core/language_models/chat_models'
import { HumanMessage, SystemMessage } from '@langchain/core/messages'
import { z } from 'zod'
import { LLMProviderConfig, LLMResponse } from './types'

// ── Provider Factory ──

export function createLLM(config: {
  provider: 'openai' | 'anthropic'
  model: string
  temperature: number
  maxTokens: number
  apiKey?: string
}): BaseChatModel {
  const providerConfig = getProviderConfig()

  if (config.provider === 'openai') {
    return new ChatOpenAI({
      modelName: config.model,
      temperature: config.temperature,
      maxTokens: config.maxTokens,
      openAIApiKey: config.apiKey || providerConfig.apiKey,
      maxRetries: providerConfig.maxRetries,
      timeout: providerConfig.timeoutMs,
    })
  }

  return new ChatAnthropic({
    modelName: config.model,
    temperature: config.temperature,
    maxTokens: config.maxTokens,
    anthropicApiKey: config.apiKey || providerConfig.apiKey,
    maxRetries: providerConfig.maxRetries,
    clientOptions: { timeout: providerConfig.timeoutMs },
  })
}

// ── Global Provider Config ──

let globalProviderConfig: LLMProviderConfig = {
  provider: 'openai',
  apiKey: process.env.OPENAI_API_KEY || process.env.ANTHROPIC_API_KEY || '',
  defaultModel: 'gpt-4o',
  maxRetries: 3,
  timeoutMs: 60_000,
}

export function setProviderConfig(config: Partial<LLMProviderConfig>): void {
  globalProviderConfig = { ...globalProviderConfig, ...config }
}

export function getProviderConfig(): LLMProviderConfig {
  return { ...globalProviderConfig }
}

// ── Structured Output Helper ──

/**
 * Invoke an LLM with structured output (Zod schema).
 * Uses native tool calling / structured output mode for reliability.
 */
export async function invokeStructured<T extends z.ZodTypeAny>(params: {
  llm: BaseChatModel
  systemPrompt: string
  userPrompt: string
  schema: T
  modelName: string
}): Promise<{ parsed: z.infer<T>; response: LLMResponse }> {
  const startTime = Date.now()

  // Use LangChain's withStructuredOutput for reliable JSON mode
  const structuredLlm = params.llm.withStructuredOutput(params.schema, {
    name: 'trading_analysis',
  })

  const messages = [
    new SystemMessage(params.systemPrompt),
    new HumanMessage(params.userPrompt),
  ]

  const result = await structuredLlm.invoke(messages)
  const latencyMs = Date.now() - startTime

  return {
    parsed: result as z.infer<T>,
    response: {
      content: JSON.stringify(result),
      model: params.modelName,
      tokensUsed: 0, // Structured output mode doesn't expose token counts easily
      latencyMs,
      finishReason: 'stop',
    },
  }
}

/**
 * Invoke an LLM with a simple text prompt (no structured output).
 */
export async function invokeText(params: {
  llm: BaseChatModel
  systemPrompt: string
  userPrompt: string
  modelName: string
}): Promise<{ content: string; response: LLMResponse }> {
  const startTime = Date.now()

  const messages = [
    new SystemMessage(params.systemPrompt),
    new HumanMessage(params.userPrompt),
  ]

  const result = await params.llm.invoke(messages)
  const latencyMs = Date.now() - startTime

  const content = typeof result.content === 'string'
    ? result.content
    : Array.isArray(result.content)
      ? result.content.map(c => (typeof c === 'string' ? c : JSON.stringify(c))).join('')
      : JSON.stringify(result.content)

  return {
    content,
    response: {
      content,
      model: params.modelName,
      tokensUsed: 0,
      latencyMs,
      finishReason: 'stop',
    },
  }
}
