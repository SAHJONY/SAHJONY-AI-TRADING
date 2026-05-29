# SAHJONY - AI Agent Platform

A sleek, developer-friendly AI Agent Platform built with Next.js 15, Supabase, and TypeScript. Powered by **Hermes Agent architecture** with Freebuff coding agent integration.

## 🧠 Brain Architecture

The platform uses a three-tier AI brain system:

```
User → SAHJONY Agent Brain
            ↓
    ┌───────┼───────┐
    ↓       ↓       ↓
Freebuff  Hermes  Local
(Coding)  Agent  Providers
```

- **Hermes Agent** (Primary): Advanced reasoning via Python microservice
- **Freebuff** (Coding): AI coding assistant for code generation/refactoring
- **Local Providers**: Anthropic/OpenAI fallback when microservices unavailable

## Features

- 🤖 **Agent Management** - Create, edit, and manage AI agents with custom prompts and models
- 💬 **Real-time Chat** - Streaming conversations with your agents
- 🔐 **Authentication** - Email/password and OAuth (GitHub) login
- 🎨 **Modern UI** - Dark theme with Tailwind CSS
- 📱 **Responsive** - Works on desktop and mobile
- 🧠 **Hermes Brain** - Advanced reasoning with Hermes Agent microservice
- 💻 **Freebuff Coding** - AI-powered coding assistance

## Tech Stack

- **Frontend**: Next.js 15 (App Router), React 19, TypeScript
- **Backend**: Next.js API Routes, Supabase Edge Functions
- **Database**: Supabase (PostgreSQL)
- **AI Brain**: Hermes Agent (Python) + Freebuff + Anthropic/OpenAI
- **Styling**: Tailwind CSS
- **Deployment**: Vercel

## Getting Started

### 1. Clone and Install

```bash
npm install
```

### 2. Set up Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. Run the migration in `supabase/migrations/001_initial_schema.sql`
3. Enable Email auth and GitHub OAuth in Supabase dashboard
4. Copy your project URL and keys to `.env.local`

### 3. Configure Environment

```bash
cp .env.example .env.local
# Edit .env.local with your credentials
```

**Key Environment Variables:**
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` - AI provider keys
- `HERMES_AGENT_URL` - URL for Hermes Agent microservice (optional)
- `HERMES_AGENT_API_KEY` - API key for Hermes Agent
- `FREEBUFF_API_URL` - URL for Freebuff service (optional)

### 4. Deploy Hermes Agent (Optional)

For advanced reasoning capabilities, deploy the Hermes Agent microservice:

```bash
cd hermes-deployment
cp .env.example .env
# Edit .env with your API keys
docker-compose up -d
```

Then configure your SAHJONY platform to connect:
```env
HERMES_AGENT_URL=http://your-hermes-server:8642
HERMES_AGENT_API_KEY=your_api_key
```

### 5. Run Development Server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to see the app.

## Project Structure

```
src/
├── app/                    # Next.js App Router pages and API routes
│   ├── api/chat/           # Chat API (integrated with Agent Brain)
│   └── ...
├── components/             # React components (UI, agents, chat, layout)
├── lib/
│   ├── agent/              # AI Agent Brain system
│   │   ├── agent-brain.ts  # Main facade with routing
│   │   ├── conversation-loop.ts  # Local fallback processing
│   │   ├── hermes-bridge.ts      # Hermes Agent connection
│   │   ├── freebuff-integration.ts  # Freebuff coding agent
│   │   ├── utils.ts        # Shared utilities
│   │   └── ...
│   ├── supabase/           # Supabase client setup
│   └── ...
└── types/                  # TypeScript type definitions

hermes-deployment/          # Hermes Agent microservice deployment
├── Dockerfile
├── docker-compose.yml
├── deploy.sh
└── README.md
```

## Agent Brain System

The `src/lib/agent/` directory contains the complete AI brain system:

- **agent-brain.ts**: Main entry point, routes requests to appropriate engines
- **conversation-loop.ts**: Local fallback when microservices unavailable
- **hermes-bridge.ts**: Connection to Hermes Agent microservice
- **freebuff-integration.ts**: Freebuff coding agent adapter
- **providers/**: Anthropic and OpenAI provider adapters
- **tools/**: Tool execution system (web search, code execution, etc.)
- **memory/**: Context management and compression

### Routing Logic

1. **Coding tasks** → Freebuff (write code, refactor, debug)
2. **Complex reasoning** → Hermes Agent (analyze, research, plan)
3. **General requests** → Hermes Agent (if available) or local providers
4. **Fallback** → Local Anthropic/OpenAI providers

## Database Schema

The platform uses these main tables:
- `profiles` - User profiles (extends auth.users)
- `agents` - AI agent configurations
- `conversations` - Chat conversations
- `messages` - Individual chat messages
- `api_keys` - User API keys for external integrations

## Deployment to Vercel

1. Push to GitHub
2. Import to Vercel
3. Add environment variables in Vercel dashboard
4. Deploy!

## License

MIT