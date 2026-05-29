// Chat API Route - Integrated with SAHJONY Agent Brain and Database Persistence
// Powered by Hermes Agent architecture with Freebuff support and Prisma database
import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { agentBrain, conversationService, Message, StreamingChunk } from '@/lib/agent';

export const runtime = 'nodejs';
export const maxDuration = 60;

interface ChatRequest {
  message: string;
  workspaceId?: string;
  conversationId?: string;
  model?: 'anthropic' | 'openai';
  stream?: boolean;
}

export async function POST(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    
    if (!session?.user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body: ChatRequest = await request.json();
    const { message, workspaceId, conversationId, model, stream } = body;

    if (!message?.trim()) {
      return NextResponse.json({ error: 'Message is required' }, { status: 400 });
    }

    console.log('[Chat API] Processing message:', message.substring(0, 50));

    // Determine workspace and conversation
    const effectiveWorkspaceId = workspaceId || 'default';
    let effectiveConversationId = conversationId;

    // Create new conversation if needed
    if (!effectiveConversationId) {
      const newConversation = await conversationService.createConversation({
        workspaceId: effectiveWorkspaceId,
        userId: session.user.id || 'anonymous',
        title: message.substring(0, 50) + (message.length > 50 ? '...' : ''),
      });
      effectiveConversationId = newConversation.id;
      console.log('[Chat API] Created new conversation:', effectiveConversationId);
    }

    // Save user message to database
    await conversationService.addMessage({
      conversationId: effectiveConversationId,
      role: 'user',
      content: message,
      model,
    });

    // Update agent model if specified
    if (model) {
      agentBrain.updateConfig({
        model: {
          provider: model,
          model: model === 'anthropic' 
            ? (process.env.ANTHROPIC_MODEL || 'claude-3-5-sonnet-20241022')
            : (process.env.OPENAI_MODEL || 'gpt-4-turbo'),
          api_key: model === 'anthropic' 
            ? process.env.ANTHROPIC_API_KEY 
            : process.env.OPENAI_API_KEY,
        },
      });
    }

    // Create context for the agent
    const context = {
      conversation_id: effectiveConversationId,
      user_id: session.user.id || 'anonymous',
      workspace_id: effectiveWorkspaceId,
    };

    // Get conversation history for context
    const historyMessages = await conversationService.getMessagesForAgent(effectiveConversationId);

    let response: string;

    // Handle streaming response
    if (stream) {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        async start(controller) {
          try {
            // For streaming, we need to handle it differently
            // The agent's processStream doesn't include history, so we pass it separately
            const fullContext = {
              ...context,
              messages: historyMessages,
            };

            await agentBrain.processStream(message, fullContext, (chunk: StreamingChunk) => {
              const data = JSON.stringify(chunk);
              controller.enqueue(encoder.encode(`data: ${data}\n\n`));
            });
            
            // Send final response
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'done', content: response })}\n\n`));
            controller.close();
          } catch (error) {
            console.error('[Chat API] Stream error:', error);
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'error', content: 'Stream failed' })}\n\n`));
            controller.close();
          }
        },
      });

      return new Response(stream, {
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
      });
    }

    // Non-streaming response - pass history for context
    const fullContext = {
      ...context,
      messages: historyMessages,
    };
    response = await agentBrain.process(message, fullContext);

    // Save assistant response to database
    await conversationService.addMessage({
      conversationId: effectiveConversationId,
      role: 'assistant',
      content: response,
      model: model || 'anthropic',
    });

    // Update conversation title if it's the first message after user message
    const conversation = await conversationService.getConversation(effectiveConversationId);
    if (conversation && conversation.messageCount === 2) {
      // First exchange - update title based on first user message
      const title = message.substring(0, 50) + (message.length > 50 ? '...' : '');
      await conversationService.updateTitle(effectiveConversationId, title);
    }

    return NextResponse.json({
      response,
      conversationId: effectiveConversationId,
      workspaceId: effectiveWorkspaceId,
      model: model || 'anthropic',
      agent: 'SAHJONY-Hermes-Agent',
    });

  } catch (error) {
    console.error('[Chat API] Error:', error);
    return NextResponse.json(
      { error: 'Failed to process message' },
      { status: 500 }
    );
  }
}

export async function GET(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    
    if (!session?.user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const workspaceId = searchParams.get('workspaceId') || 'default';
    const limit = parseInt(searchParams.get('limit') || '50', 10);
    const offset = parseInt(searchParams.get('offset') || '0', 10);

    // Get conversations for workspace
    const conversations = await conversationService.getWorkspaceConversations(
      workspaceId,
      limit,
      offset
    );

    // Get workspace stats
    const stats = await conversationService.getStats(workspaceId);

    return NextResponse.json({
      conversations,
      stats,
      models: ['anthropic', 'openai'],
      currentModel: 'anthropic',
      agent: 'SAHJONY-Hermes-Agent',
      version: '1.0.0',
      capabilities: {
        streaming: true,
        tools: agentBrain.getTools().map(t => t.name),
        skills: agentBrain.getSkills().map(s => s.name),
      },
    });

  } catch (error) {
    console.error('[Chat API] Error:', error);
    return NextResponse.json(
      { error: 'Failed to get conversations' },
      { status: 500 }
    );
  }
}