// Shared utility functions for the SAHJONY Agent Engine

/**
 * Check if a message is a coding task (should route to Freebuff)
 */
export function isCodingTask(message: string): boolean {
  const codingKeywords = [
    'write code', 'create function', 'implement', 'refactor',
    'debug', 'fix bug', 'add feature', 'modify', 'delete code',
    'class ', 'function ', 'const ', 'let ', 'var ',
    'import ', 'export ', 'return ', 'async ', 'await',
    '.ts', '.js', '.tsx', '.jsx', '.py', '.java',
    '```', 'def ', 'fn ', 'pub ', 'struct ', 'enum ',
    'code', 'programming', 'script', 'algorithm'
  ];
  const lowerMessage = message.toLowerCase();
  return codingKeywords.some(keyword => lowerMessage.includes(keyword));
}

/**
 * Check if a message requires complex reasoning (should route to Hermes)
 */
export function isComplexReasoning(message: string): boolean {
  const reasoningKeywords = [
    'analyze', 'research', 'explain', 'compare', 'evaluate',
    'think step', 'reasoning', 'plan', 'design', 'architecture',
    'strategy', 'investigate', 'explore', 'discover', 'understand'
  ];
  const lowerMessage = message.toLowerCase();
  return reasoningKeywords.some(keyword => lowerMessage.includes(keyword));
}

/**
 * Format a timestamp for logging
 */
export function formatTimestamp(date: Date = new Date()): string {
  return date.toISOString().split('T')[1].split('.')[0] + 'Z';
}

/**
 * Truncate a string for logging
 */
export function truncate(str: string, maxLength: number = 50): string {
  return str.length > maxLength ? str.substring(0, maxLength) + '...' : str;
}