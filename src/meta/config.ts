/**
 * Layer 5 — Meta-Learning System Configuration
 *
 * Centralized configuration for the self-evolving meta-learning layer.
 * All values can be overridden via environment variables.
 */

import * as path from 'path'
import { MetaLearningConfig } from './types'
import {
  DEFAULT_GA_CONFIG,
  DEFAULT_GENE_POOL,
} from './strategy-ga'
import { DEFAULT_BANDIT_CONFIG } from './model-router'
import { DEFAULT_BACKTEST_CONFIG } from './backtest-engine'
import { DEFAULT_PROMPT_OPTIMIZER_CONFIG } from './prompt-optimizer'

// ── Environment Helpers ──

const env = (key: string, fallback: string): string => process.env[key] || fallback
const envNum = (key: string, fallback: number): number => {
  const val = process.env[key]
  return val ? parseFloat(val) : fallback
}
const envBool = (key: string, fallback: boolean): boolean => {
  const val = process.env[key]
  return val !== undefined ? val === 'true' || val === '1' : fallback
}
const envList = (key: string, fallback: string[]): string[] => {
  const val = process.env[key]
  return val ? val.split(',').map(s => s.trim()).filter(Boolean) : fallback
}

// ── Default Meta-Learning Configuration ──

export const DEFAULT_META_LEARNING_CONFIG: MetaLearningConfig = {
  ga: {
    ...DEFAULT_GA_CONFIG,
    populationSize: envNum('GA_POPULATION_SIZE', 50),
    generations: envNum('GA_GENERATIONS', 20),
    eliteCount: envNum('GA_ELITE_COUNT', 5),
    crossoverRate: envNum('GA_CROSSOVER_RATE', 0.8),
    mutationRate: envNum('GA_MUTATION_RATE', 0.1),
    tournamentSize: envNum('GA_TOURNAMENT_SIZE', 3),
    minSamples: envNum('GA_MIN_SAMPLES', 50),
    persist: envBool('GA_PERSIST', true),
    persistDir: env('GA_PERSIST_DIR', path.resolve(process.cwd(), 'data', 'meta-learning', 'ga')),
  },

  genePool: DEFAULT_GENE_POOL,

  bandit: {
    ...DEFAULT_BANDIT_CONFIG,
    strategy: (env('BANDIT_STRATEGY', 'ucb1') as 'epsilon_greedy' | 'ucb1' | 'thompson_sampling'),
    epsilon: envNum('BANDIT_EPSILON', 0.1),
    epsilonDecay: envNum('BANDIT_EPSILON_DECAY', 0.995),
    ucbC: envNum('BANDIT_UCB_C', 2.0),
    warmupPulls: envNum('BANDIT_WARMUP_PULLS', 5),
  },

  backtest: {
    ...DEFAULT_BACKTEST_CONFIG,
    symbols: envList('BACKTEST_SYMBOLS', []),
    initialEquity: envNum('BACKTEST_EQUITY', 100_000),
    commissionBps: envNum('BACKTEST_COMMISSION_BPS', 1),
    slippageBps: envNum('BACKTEST_SLIPPAGE_BPS', 2),
    walkForward: envBool('BACKTEST_WALK_FORWARD', false),
    walkForwardWindowDays: envNum('BACKTEST_WF_WINDOW', 60),
    outOfSampleDays: envNum('BACKTEST_OOS_DAYS', 20),
  },

  promptOptimization: {
    ...DEFAULT_PROMPT_OPTIMIZER_CONFIG,
    minEvaluations: envNum('PROMPT_MIN_EVALUATIONS', 20),
    maxFewShotExamples: envNum('PROMPT_MAX_FEWSHOT', 4),
    positiveExamplesOnly: envBool('PROMPT_POSITIVE_ONLY', true),
    mutationIterations: envNum('PROMPT_MUTATION_ITERATIONS', 5),
  },

  schedule: {
    evolutionCron: env('EVOLUTION_CRON', '0 0 * * 0'),
    evolutionSampleThreshold: envNum('EVOLUTION_SAMPLE_THRESHOLD', 100),
    sharpeDegradationThreshold: envNum('EVOLUTION_SHARPE_DEGRADE', -0.5),
    drawdownTriggerPct: envNum('EVOLUTION_DRAWDOWN_TRIGGER', 15),
  },

  retention: {
    maxDebateRecords: envNum('RETENTION_MAX_DEBATES', 10_000),
    maxTradeRecords: envNum('RETENTION_MAX_TRADES', 50_000),
    persistRecords: envBool('RETENTION_PERSIST', true),
    persistDir: env('RETENTION_PERSIST_DIR', path.resolve(process.cwd(), 'data', 'meta-learning')),
  },
}

// ── Config Builder ──

/**
 * Build a MetaLearningConfig with overrides.
 */
export function buildMetaLearningConfig(
  overrides: Partial<MetaLearningConfig> = {}
): MetaLearningConfig {
  return {
    ...DEFAULT_META_LEARNING_CONFIG,
    ...overrides,
    ga: { ...DEFAULT_META_LEARNING_CONFIG.ga, ...overrides.ga },
    genePool: { ...DEFAULT_META_LEARNING_CONFIG.genePool, ...overrides.genePool },
    bandit: { ...DEFAULT_META_LEARNING_CONFIG.bandit, ...overrides.bandit },
    backtest: { ...DEFAULT_META_LEARNING_CONFIG.backtest, ...overrides.backtest },
    promptOptimization: { ...DEFAULT_META_LEARNING_CONFIG.promptOptimization, ...overrides.promptOptimization },
    schedule: { ...DEFAULT_META_LEARNING_CONFIG.schedule, ...overrides.schedule },
    retention: { ...DEFAULT_META_LEARNING_CONFIG.retention, ...overrides.retention },
  }
}
