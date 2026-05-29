import express, { Request, Response } from 'express';

const router = express.Router();

// In-memory store reference (set from server.ts)
let workspaceStore: any = null;

// Export function to set store (called from server.ts)
export function setWorkspaceStore(store: any) {
  workspaceStore = store;
}

// GET /api/workspace/share/:shareId - Get workspace by share ID (public)
router.get('/share/:shareId', (req: Request, res: Response) => {
  try {
    const workspace = workspaceStore?.getByShareId(req.params.shareId);
    if (!workspace) {
      return res.status(404).json({ error: 'Workspace not found' });
    }
    // Return minimal public info
    res.json({
      id: workspace.id,
      shareId: workspace.shareId,
      name: workspace.name,
      messages: workspace.messages,
      createdAt: workspace.createdAt,
      settings: workspace.settings,
      metrics: workspace.metrics
    });
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch workspace' });
  }
});

// POST /api/workspace - Create new workspace
router.post('/', (req: Request, res: Response) => {
  try {
    const workspace = workspaceStore?.create(req.body);
    res.status(201).json(workspace);
  } catch (error) {
    res.status(500).json({ error: 'Failed to create workspace' });
  }
});

// GET /api/workspace/:id - Get workspace by ID
router.get('/:id', (req: Request, res: Response) => {
  try {
    const workspace = workspaceStore?.get(req.params.id);
    if (!workspace) {
      return res.status(404).json({ error: 'Workspace not found' });
    }
    res.json(workspace);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch workspace' });
  }
});

// PATCH /api/workspace/:id - Update workspace
router.patch('/:id', (req: Request, res: Response) => {
  try {
    const workspace = workspaceStore?.update(req.params.id, req.body);
    if (!workspace) {
      return res.status(404).json({ error: 'Workspace not found' });
    }
    res.json(workspace);
  } catch (error) {
    res.status(500).json({ error: 'Failed to update workspace' });
  }
});

// DELETE /api/workspace/:id - Delete workspace
router.delete('/:id', (req: Request, res: Response) => {
  try {
    const deleted = workspaceStore?.delete(req.params.id);
    if (!deleted) {
      return res.status(404).json({ error: 'Workspace not found' });
    }
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: 'Failed to delete workspace' });
  }
});

// POST /api/workspace/:id/messages - Add message to workspace
router.post('/:id/messages', (req: Request, res: Response) => {
  try {
    const { role, content } = req.body;
    if (!role || !content) {
      return res.status(400).json({ error: 'Role and content required' });
    }

    const workspace = workspaceStore?.addMessage(req.params.id, { role, content });
    if (!workspace) {
      return res.status(404).json({ error: 'Workspace not found' });
    }
    res.json(workspace);
  } catch (error) {
    res.status(500).json({ error: 'Failed to add message' });
  }
});

// GET /api/workspace - List all workspaces
router.get('/', (req: Request, res: Response) => {
  try {
    const workspaces = workspaceStore?.list() || [];
    res.json(workspaces);
  } catch (error) {
    res.status(500).json({ error: 'Failed to list workspaces' });
  }
});

export default router;