// In-memory workspace store (serverless compatible)
// For production, replace with a cloud database like Supabase, Turso, or PlanetScale

interface Workspace {
  id: string;
  shareId: string;
  name: string;
  messages: Array<{
    id: string;
    role: 'user' | 'hermes' | 'system';
    content: string;
    timestamp: string;
  }>;
  createdAt: string;
  updatedAt: string;
  settings: {
    model: string;
    temperature: number;
  };
  metrics: {
    totalMessages: number;
    totalInteractions: number;
    lastActivity: string | null;
  };
}

// Generate a random share ID (6 characters)
function generateShareId(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < 6; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

// Generate a random workspace ID
function generateId(): string {
  return 'ws_' + Math.random().toString(36).substring(2, 15);
}

class WorkspaceStore {
  private workspaces: Map<string, Workspace> = new Map();
  private shareIndex: Map<string, string> = new Map(); // shareId -> workspaceId

  create(data?: Partial<Workspace>): Workspace {
    const id = generateId();
    const shareId = generateShareId();
    const now = new Date().toISOString();

    const workspace: Workspace = {
      id,
      shareId,
      name: data?.name || 'My Workspace',
      messages: [],
      createdAt: now,
      updatedAt: now,
      settings: data?.settings || {
        model: 'auto',
        temperature: 0.7
      },
      metrics: data?.metrics || {
        totalMessages: 0,
        totalInteractions: 0,
        lastActivity: null
      }
    };

    this.workspaces.set(id, workspace);
    this.shareIndex.set(shareId, id);

    return workspace;
  }

  get(id: string): Workspace | undefined {
    return this.workspaces.get(id);
  }

  getByShareId(shareId: string): Workspace | undefined {
    const id = this.shareIndex.get(shareId);
    return id ? this.workspaces.get(id) : undefined;
  }

  update(id: string, data: Partial<Workspace>): Workspace | undefined {
    const workspace = this.workspaces.get(id);
    if (!workspace) return undefined;

    const updated = {
      ...workspace,
      ...data,
      id: workspace.id, // Prevent ID changes
      updatedAt: new Date().toISOString()
    };

    this.workspaces.set(id, updated);
    return updated;
  }

  delete(id: string): boolean {
    const workspace = this.workspaces.get(id);
    if (!workspace) return false;

    this.shareIndex.delete(workspace.shareId);
    this.workspaces.delete(id);
    return true;
  }

  addMessage(workspaceId: string, message: Omit<Workspace['messages'][0], 'id' | 'timestamp'>): Workspace | undefined {
    const workspace = this.workspaces.get(workspaceId);
    if (!workspace) return undefined;

    const newMessage = {
      id: 'msg_' + Math.random().toString(36).substring(2, 10),
      timestamp: new Date().toISOString(),
      ...message
    };

    workspace.messages.push(newMessage);
    workspace.metrics.totalMessages++;
    workspace.metrics.totalInteractions++;
    workspace.metrics.lastActivity = newMessage.timestamp;
    workspace.updatedAt = newMessage.timestamp;

    return workspace;
  }

  list(): Workspace[] {
    return Array.from(this.workspaces.values());
  }

  // Get or create default workspace for a session
  getOrCreate(id: string): Workspace {
    const existing = this.workspaces.get(id);
    if (existing) return existing;
    return this.create({ name: 'Default Workspace' });
  }
}

// Singleton instance
export const workspaceStore = new WorkspaceStore();

// Helper to create default workspace
export function createDefaultWorkspace(): Workspace {
  return workspaceStore.create({
    name: 'Agent Workforce Workspace'
  });
}