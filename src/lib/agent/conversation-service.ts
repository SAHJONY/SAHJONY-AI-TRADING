// Conversation Service - Database operations for conversations and messages
// Uses the existing Prisma schema (Conversation and Message models)
import { prisma } from '@/lib/prisma';
import { Message } from './types';

export interface CreateConversationParams {
  title?: string;
  workspaceId: string;
  userId: string;
}

export interface CreateMessageParams {
  conversationId: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  model?: string;
  tokens?: number;
  metadata?: Record<string, unknown>;
}

export interface ConversationWithMessages {
  id: string;
  title: string;
  workspaceId: string;
  messageCount: number;
  createdAt: Date;
  updatedAt: Date;
  messages: Array<{
    id: string;
    role: string;
    content: string;
    model: string | null;
    tokens: number | null;
    metadata: string | null;
    createdAt: Date;
  }>;
}

export class ConversationService {
  /**
   * Create a new conversation
   */
  async createConversation(params: CreateConversationParams): Promise<{ id: string; title: string; createdAt: Date }> {
    const { title = 'New Conversation', workspaceId, userId } = params;

    const conversation = await prisma.conversation.create({
      data: {
        title,
        workspaceId,
        messageCount: 0,
      },
      select: {
        id: true,
        title: true,
        createdAt: true,
      },
    });

    console.log(`[ConversationService] Created conversation ${conversation.id} for user ${userId}`);
    return conversation;
  }

  /**
   * Get a conversation by ID with its messages
   */
  async getConversation(conversationId: string): Promise<ConversationWithMessages | null> {
    const conversation = await prisma.conversation.findUnique({
      where: { id: conversationId },
      include: {
        messages: {
          orderBy: { createdAt: 'asc' },
          select: {
            id: true,
            role: true,
            content: true,
            model: true,
            tokens: true,
            metadata: true,
            createdAt: true,
          },
        },
      },
    });

    return conversation as ConversationWithMessages | null;
  }

  /**
   * Get all conversations for a workspace
   */
  async getWorkspaceConversations(
    workspaceId: string,
    limit = 50,
    offset = 0
  ): Promise<Array<{ id: string; title: string; messageCount: number; createdAt: Date; updatedAt: Date }>> {
    const conversations = await prisma.conversation.findMany({
      where: { workspaceId },
      orderBy: { updatedAt: 'desc' },
      skip: offset,
      take: limit,
      select: {
        id: true,
        title: true,
        messageCount: true,
        createdAt: true,
        updatedAt: true,
      },
    });

    return conversations;
  }

  /**
   * Add a message to a conversation
   */
  async addMessage(params: CreateMessageParams): Promise<{ id: string; createdAt: Date }> {
    const { conversationId, role, content, model, tokens, metadata } = params;

    // Create the message
    const message = await prisma.message.create({
      data: {
        conversationId,
        role,
        content,
        model,
        tokens,
        metadata: metadata ? JSON.stringify(metadata) : null,
      },
      select: {
        id: true,
        createdAt: true,
      },
    });

    // Update conversation's message count and updatedAt
    await prisma.conversation.update({
      where: { id: conversationId },
      data: {
        messageCount: { increment: 1 },
        updatedAt: new Date(),
      },
    });

    console.log(`[ConversationService] Added ${role} message to conversation ${conversationId}`);
    return message;
  }

  /**
   * Add multiple messages (for conversation history import)
   */
  async addMessages(
    conversationId: string,
    messages: Array<{ role: string; content: string; model?: string; tokens?: number }>
  ): Promise<void> {
    await prisma.$transaction(async (tx) => {
      for (const msg of messages) {
        await tx.message.create({
          data: {
            conversationId,
            role: msg.role as 'user' | 'assistant' | 'system' | 'tool',
            content: msg.content,
            model: msg.model,
            tokens: msg.tokens,
          },
        });
      }

      // Update message count
      await tx.conversation.update({
        where: { id: conversationId },
        data: {
          messageCount: { increment: messages.length },
          updatedAt: new Date(),
        },
      });
    });

    console.log(`[ConversationService] Added ${messages.length} messages to conversation ${conversationId}`);
  }

  /**
   * Update conversation title
   */
  async updateTitle(conversationId: string, title: string): Promise<void> {
    await prisma.conversation.update({
      where: { id: conversationId },
      data: { title },
    });
    console.log(`[ConversationService] Updated conversation ${conversationId} title to: ${title}`);
  }

  /**
   * Delete a conversation and all its messages
   */
  async deleteConversation(conversationId: string): Promise<void> {
    // Messages will be deleted automatically due to cascade
    await prisma.conversation.delete({
      where: { id: conversationId },
    });
    console.log(`[ConversationService] Deleted conversation ${conversationId}`);
  }

  /**
   * Search conversations by title or content
   */
  async searchConversations(
    workspaceId: string,
    query: string,
    limit = 20
  ): Promise<Array<{ id: string; title: string; snippet?: string }>> {
    // Search in conversation titles and message content
    const conversations = await prisma.conversation.findMany({
      where: {
        workspaceId,
        OR: [
          { title: { contains: query } },
          { messages: { some: { content: { contains: query } } } },
        ],
      },
      include: {
        messages: {
          where: { content: { contains: query } },
          select: { content: true },
          take: 1,
        },
      },
      take: limit,
    });

    return conversations.map((conv) => ({
      id: conv.id,
      title: conv.title,
      snippet: conv.messages[0]?.content.substring(0, 100),
    }));
  }

  /**
   * Get conversation statistics
   */
  async getStats(workspaceId: string): Promise<{
    totalConversations: number;
    totalMessages: number;
    lastConversationAt: Date | null;
  }> {
    const [count, messageSum, lastConv] = await Promise.all([
      prisma.conversation.count({ where: { workspaceId } }),
      prisma.conversation.aggregate({
        where: { workspaceId },
        _sum: { messageCount: true },
      }),
      prisma.conversation.findFirst({
        where: { workspaceId },
        orderBy: { updatedAt: 'desc' },
        select: { updatedAt: true },
      }),
    ]);

    return {
      totalConversations: count,
      totalMessages: count > 0 ? (messageSum._sum.messageCount || 0) : 0,
      lastConversationAt: lastConv?.updatedAt || null,
    };
  }

  /**
   * Convert Prisma message format to agent Message type
   */
  toAgentMessage(prismaMessage: {
    id: string;
    role: string;
    content: string;
    createdAt: Date;
  }): Message {
    return {
      id: prismaMessage.id,
      role: prismaMessage.role as Message['role'],
      content: prismaMessage.content,
      timestamp: prismaMessage.createdAt.getTime(),
    };
  }

  /**
   * Get messages for an agent context
   */
  async getMessagesForAgent(conversationId: string): Promise<Message[]> {
    const conversation = await this.getConversation(conversationId);
    if (!conversation) return [];

    return conversation.messages.map((msg) => this.toAgentMessage(msg));
  }
}

// Singleton instance
export const conversationService = new ConversationService();