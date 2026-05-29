// File Tools - Real implementation
import { Tool, ToolCall, ToolResult } from '../../types';
import * as fs from 'fs';
import * as path from 'path';

export const fileToolsTool: Tool = {
  name: 'file_tools',
  description: 'Read, write, list, and manage files in the workspace.',
};

interface FileOperationArgs {
  operation: 'read' | 'write' | 'list' | 'exists' | 'delete' | 'mkdir';
  path?: string;
  content?: string;
  pattern?: string;
}

const WORKSPACE_ROOT = process.cwd();

function sanitizePath(inputPath: string): string {
  // Prevent path traversal attacks
  const normalized = path.normalize(inputPath);
  const fullPath = path.isAbsolute(normalized) 
    ? normalized 
    : path.resolve(WORKSPACE_ROOT, normalized);
  
  // Ensure the path is within workspace root
  if (!fullPath.startsWith(WORKSPACE_ROOT)) {
    throw new Error('Access denied: Path outside workspace');
  }
  
  return fullPath;
}

export async function executeFileOperation(args: Record<string, unknown>, toolCallId: string): Promise<ToolResult> {
  const { operation, path: filePath, content, pattern } = args as FileOperationArgs;

  if (!filePath && operation !== 'list') {
    return {
      tool_call_id: toolCallId,
      result: JSON.stringify({ error: 'Path is required for file operations' }),
      success: false,
      error: 'Path is required',
      content: JSON.stringify({ error: 'Path is required' }),
    };
  }

  try {
    switch (operation) {
      case 'read': {
        const safePath = sanitizePath(filePath!);
        
        if (!fs.existsSync(safePath)) {
          return {
            tool_call_id: toolCallId,
            result: JSON.stringify({ error: 'File not found' }),
            success: false,
            error: 'File not found',
            content: JSON.stringify({ error: 'File not found' }),
          };
        }

        const stat = fs.statSync(safePath);
        if (stat.isDirectory()) {
          return {
            tool_call_id: toolCallId,
            result: JSON.stringify({ error: 'Path is a directory, not a file' }),
            success: false,
            error: 'Path is a directory',
            content: JSON.stringify({ error: 'Path is a directory' }),
          };
        }

        // Limit file size to 1MB
        if (stat.size > 1024 * 1024) {
          return {
            tool_call_id: toolCallId,
            result: JSON.stringify({ error: 'File too large (max 1MB)' }),
            success: false,
            error: 'File too large',
            content: JSON.stringify({ error: 'File too large' }),
          };
        }

        const fileContent = fs.readFileSync(safePath, 'utf-8');
        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ success: true, content: fileContent, path: filePath }),
          success: true,
          content: JSON.stringify({ success: true, content: fileContent, path: filePath }),
        };
      }

      case 'write': {
        if (content === undefined) {
          return {
            tool_call_id: toolCallId,
            result: JSON.stringify({ error: 'Content is required for write operation' }),
            success: false,
            error: 'Content is required',
            content: JSON.stringify({ error: 'Content is required' }),
          };
        }

        const safePath = sanitizePath(filePath!);
        
        // Ensure directory exists
        const dir = path.dirname(safePath);
        if (!fs.existsSync(dir)) {
          fs.mkdirSync(dir, { recursive: true });
        }

        fs.writeFileSync(safePath, content, 'utf-8');
        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ success: true, path: filePath }),
          success: true,
          content: JSON.stringify({ success: true, path: filePath }),
        };
      }

      case 'list': {
        const listPath = filePath ? sanitizePath(filePath) : WORKSPACE_ROOT;
        
        if (!fs.existsSync(listPath)) {
          return {
            tool_call_id: toolCallId,
            result: JSON.stringify({ error: 'Directory not found' }),
            success: false,
            error: 'Directory not found',
            content: JSON.stringify({ error: 'Directory not found' }),
          };
        }

        const stat = fs.statSync(listPath);
        if (!stat.isDirectory()) {
          return {
            tool_call_id: toolCallId,
            result: JSON.stringify({ error: 'Path is not a directory' }),
            success: false,
            error: 'Path is not a directory',
            content: JSON.stringify({ error: 'Path is not a directory' }),
          };
        }

        const entries = fs.readdirSync(listPath, { withFileTypes: true });
        const files = entries.map(entry => ({
          name: entry.name,
          type: entry.isDirectory() ? 'directory' : 'file',
          path: path.join(listPath, entry.name),
        }));

        // Filter by pattern if provided
        let filtered = files;
        if (pattern) {
          const regex = new RegExp(pattern);
          filtered = files.filter(f => regex.test(f.name));
        }

        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ success: true, files: filtered, path: listPath }),
          success: true,
          content: JSON.stringify({ success: true, files: filtered, path: listPath }),
        };
      }

      case 'exists': {
        const safePath = sanitizePath(filePath!);
        const exists = fs.existsSync(safePath);
        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ success: true, exists, path: filePath }),
          success: true,
          content: JSON.stringify({ success: true, exists, path: filePath }),
        };
      }

      case 'delete': {
        const safePath = sanitizePath(filePath!);
        
        if (!fs.existsSync(safePath)) {
          return {
            tool_call_id: toolCallId,
            result: JSON.stringify({ error: 'File not found' }),
            success: false,
            error: 'File not found',
            content: JSON.stringify({ error: 'File not found' }),
          };
        }

        const stat = fs.statSync(safePath);
        if (stat.isDirectory()) {
          fs.rmdirSync(safePath, { recursive: true });
        } else {
          fs.unlinkSync(safePath);
        }

        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ success: true, deleted: filePath }),
          success: true,
          content: JSON.stringify({ success: true, deleted: filePath }),
        };
      }

      case 'mkdir': {
        const safePath = sanitizePath(filePath!);
        fs.mkdirSync(safePath, { recursive: true });
        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ success: true, created: filePath }),
          success: true,
          content: JSON.stringify({ success: true, created: filePath }),
        };
      }

      default:
        return {
          tool_call_id: toolCallId,
          result: JSON.stringify({ error: `Unknown operation: ${operation}` }),
          success: false,
          error: `Unknown operation: ${operation}`,
          content: JSON.stringify({ error: `Unknown operation: ${operation}` }),
        };
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    return {
      tool_call_id: toolCallId,
      result: JSON.stringify({ error: errorMessage }),
      success: false,
      error: errorMessage,
      content: JSON.stringify({ error: errorMessage }),
    };
  }
}