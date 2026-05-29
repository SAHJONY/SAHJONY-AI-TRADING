// Freebuff API Service - Provides Freebuff coding agent as an API
// This is a placeholder service - real integration requires @codebuff/sdk

const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'freebuff-api', timestamp: new Date().toISOString() });
});

// Coding task endpoint
app.post('/v1/coding/task', async (req, res) => {
  try {
    const { instruction, files, context } = req.body;
    
    if (!instruction) {
      return res.status(400).json({ error: 'Missing required field: instruction' });
    }

    console.log(`[FreebuffAPI] Processing task: ${instruction.substring(0, 50)}...`);
    
    // TODO: Integrate with actual Codebuff SDK for production
    // const CodebuffClient = require('@codebuff/sdk');
    // const client = new CodebuffClient({ apiKey: process.env.CODEBUFF_API_KEY });
    
    res.json({
      success: true,
      task_id: `freebuff-${Date.now()}`,
      changes: [],
      logs: ['[Freebuff] Processing coding task via API...'],
      message: 'Freebuff API service is running. For full functionality, integrate @codebuff/sdk.'
    });

  } catch (error) {
    console.error('[FreebuffAPI] Error:', error);
    res.status(500).json({ 
      success: false, 
      error: error.message || 'Internal server error' 
    });
  }
});

// Chat completions endpoint (OpenAI-compatible)
app.post('/v1/chat/completions', async (req, res) => {
  try {
    const { messages, model, temperature, max_tokens } = req.body;
    
    const lastMessage = messages[messages.length - 1]?.content || '';
    
    res.json({
      id: `freebuff-${Date.now()}`,
      model: model || 'freebuff',
      choices: [{
        message: {
          role: 'assistant',
          content: `[Freebuff Coding Agent] I can help with coding tasks. You've asked about: "${lastMessage.substring(0, 100)}..."\n\nTo enable full functionality, please set up the Codebuff SDK integration.`
        },
        finish_reason: 'stop'
      }],
      usage: {
        prompt_tokens: 10,
        completion_tokens: 50,
        total_tokens: 60
      }
    });

  } catch (error) {
    console.error('[FreebuffAPI] Chat error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Start server
app.listen(PORT, '0.0.0.0', () => {
  console.log(`[FreebuffAPI] Service started on port ${PORT}`);
  console.log(`[FreebuffAPI] Health check: http://localhost:${PORT}/health`);
});