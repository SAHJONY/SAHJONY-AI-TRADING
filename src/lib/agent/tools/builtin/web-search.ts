// Web Search Tool - Real implementation
import { Tool, ToolCall, ToolResult } from '../../types';

export const webSearchTool: Tool = {
  name: 'web_search',
  description: 'Search the web for information. Use this when you need to find current information or facts.',
};

interface SearchArgs {
  query: string;
  num_results?: number;
}

export async function executeWebSearch(args: Record<string, unknown>, toolCallId: string): Promise<ToolResult> {
  const { query, num_results = 5 } = args as SearchArgs;
  
  if (!query || typeof query !== 'string') {
    return {
      tool_call_id: toolCallId,
      result: JSON.stringify({ error: 'Query is required' }),
      success: false,
      error: 'Query is required',
      content: JSON.stringify({ error: 'Query is required' }),
    };
  }

  try {
    // Using DuckDuckGo instant answer API (no API key required)
    // Fallback to a simple fetch-based search
    const encodedQuery = encodeURIComponent(query);
    
    // Try using a search API - using Wikipedia API as a fallback for general knowledge
    const wikiUrl = `https://en.wikipedia.org/api/rest_v1/page/summary/${encodedQuery}`;
    
    try {
      const response = await fetch(wikiUrl, { 
        method: 'GET',
        headers: { 'Accept': 'application/json' },
      });

      if (response.ok) {
        const data = await response.json();
        const result = {
          query,
          results: [{
            title: data.title || query,
            snippet: data.extract || 'No information found',
            url: data.content_urls?.desktop?.page || `https://en.wikipedia.org/wiki/${encodedQuery}`,
          }],
          success: true,
        };

        return {
          tool_call_id: toolCallId,
          result: JSON.stringify(result),
          success: true,
          content: JSON.stringify(result),
        };
      }
    } catch {
      // Wikipedia API failed, try DDG instant answer
    }

    // Fallback: Use DuckDuckGo HTML to get instant answer
    const ddgUrl = `https://api.duckduckgo.com/?q=${encodedQuery}&format=json&no_html=1`;
    const ddgResponse = await fetch(ddgUrl, { method: 'GET' });
    
    if (ddgResponse.ok) {
      const ddgData = await ddgResponse.json();
      
      const results = {
        query,
        results: [] as { title: string; snippet: string; url: string }[],
        success: true,
      };

      // Extract topics (instant answer)
      if (ddgData.AbstractText) {
        results.results.push({
          title: ddgData.Heading || query,
          snippet: ddgData.AbstractText,
          url: ddgData.AbstractURL || '',
        });
      }

      // Extract related topics
      if (ddgData.RelatedTopics && ddgData.RelatedTopics.length > 0) {
        for (const topic of ddgData.RelatedTopics.slice(0, num_results)) {
          if (topic.Text) {
            results.results.push({
              title: topic.Text.substring(0, 100),
              snippet: topic.Text,
              url: topic.URL || '',
            });
          }
        }
      }

      return {
        tool_call_id: toolCallId,
        result: JSON.stringify(results),
        success: true,
        content: JSON.stringify(results),
      };
    }

    throw new Error('Search API not available');
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