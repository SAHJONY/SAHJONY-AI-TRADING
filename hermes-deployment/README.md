# Hermes Agent Microservice Deployment

This directory contains the configuration and scripts needed to deploy the Hermes Agent Python microservice that powers the SAHJONY platform's advanced reasoning capabilities.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      SAHJONY Platform                            │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │  Next.js    │───▶│ Agent Brain  │───▶│  Hermes Bridge   │   │
│  │  Frontend   │    │              │    │                  │   │
│  └─────────────┘    └──────────────┘    └────────┬─────────┘   │
│                                                   │              │
└───────────────────────────────────────────────────┼──────────────┘
                                                    │
                                           ┌────────▼────────┐
                                           │  Hermes Agent   │
                                           │  Microservice   │
                                           │  (Port 8642)    │
                                           └─────────────────┘
```

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Build the Docker image
docker build -t hermes-agent .

# Run the container
docker run -d -p 8642:8642 --env-file .env hermes-agent

# Or use Docker Compose
docker-compose up -d
```

### Option 2: Direct Python Installation

```bash
# Install Hermes Agent
pip install hermes-agent

# Set environment variables
export API_SERVER_ENABLED=true
export API_SERVER_PORT=8642
export ANTHROPIC_API_KEY=your_key_here

# Start the gateway
hermes gateway
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_SERVER_KEY` | Yes | - | API key for authenticating requests to the microservice |
| `ANTHROPIC_API_KEY` | Yes | - | Anthropic API key for AI model access |
| `OPENAI_API_KEY` | No | - | OpenAI API key (alternative to Anthropic) |
| `API_SERVER_PORT` | No | 8642 | Port for the API server to listen on |
| `API_SERVER_HOST` | No | 0.0.0.0 | Host to bind the server to |
| `LOG_LEVEL` | No | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |

## API Endpoints

The Hermes Agent exposes an OpenAI-compatible API:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | Send a chat completion request |
| `/health` | GET | Health check endpoint |
| `/models` | GET | List available models |

### Chat Completions Request

```bash
curl -X POST http://localhost:8642/v1/chat/completions \\
  -H "Authorization: Bearer YOUR_API_SERVER_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "hermes-3",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 1000
  }'
```

## Connecting to SAHJONY Platform

After deploying Hermes Agent, configure your SAHJONY platform's `.env.local`:

```env
HERMES_AGENT_URL=http://your-hermes-server:8642
HERMES_AGENT_API_KEY=your_api_server_key_from_hermes_deployment
```

## Deployment on Railway

1. Create a new Railway project
2. Add a Python service
3. Set the start command: `hermes gateway`
4. Add environment variables from `.env.example`
5. Deploy

## Deployment on Render

1. Create a new Web Service
2. Set build command: `pip install hermes-agent`
3. Set start command: `hermes gateway`
4. Add environment variables
5. Deploy

## Verification

Check if Hermes Agent is running correctly:

```bash
curl http://localhost:8642/health
```

Expected response: `{"status": "ok"}`

## Troubleshooting

### Port already in use
If port 8642 is occupied, change the port:
```bash
export API_SERVER_PORT=8643
hermes gateway
```

### Authentication errors
Verify your `API_SERVER_KEY` matches between deployment and SAHJONY configuration.

### Model not available
Ensure `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is properly set in the environment.