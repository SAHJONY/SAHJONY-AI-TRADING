# AI Agent Platform - Specification

## 1. Concept & Vision

**Convo** — A sleek, developer-friendly AI Agent Platform that lets solo builders create, deploy, and manage intelligent agents with powerful skills and real-time chat capabilities. Built for creators who want production-quality AI infrastructure without enterprise complexity. The aesthetic is "professional dark mode meets modern SaaS" — think Linear meets Vercel.

## 2. Design Language

### Color Palette
- **Background**: `#0a0a0b` (near-black)
- **Surface**: `#111113` (card backgrounds)
- **Border**: `#1e1e21` (subtle borders)
- **Primary**: `#6366f1` (indigo-500, main actions)
- **Primary Hover**: `#818cf8` (indigo-400)
- **Accent**: `#22d3ee` (cyan-400, highlights)
- **Text Primary**: `#fafafa` (white-ish)
- **Text Secondary**: `#a1a1aa` (zinc-400)
- **Success**: `#22c55e` (green-500)
- **Warning**: `#f59e0b` (amber-500)
- **Error**: `#ef4444` (red-500)

### Typography
- **Font**: Inter (Google Fonts) — clean, professional
- **Headings**: Inter, weight 600-700, tracking tight
- **Body**: Inter, weight 400, 15px base
- **Code/Mono**: JetBrains Mono

### Spatial System
- Base unit: 4px
- Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64
- Border radius: 6px (small), 8px (medium), 12px (large)
- Cards: 16px padding, 1px border

### Motion Philosophy
- Transitions: 150ms ease-out for interactions, 300ms for page transitions
- Micro-interactions: subtle scale (1.02) on hover for cards
- Loading: skeleton shimmer animation
- Success feedback: brief green pulse

### Visual Assets
- Icons: Lucide React (consistent, clean)
- Decorative: subtle gradient meshes, glow effects on focus
- Agent avatars: gradient backgrounds with initials

## 3. Layout & Structure

### Page Structure
```
┌─────────────────────────────────────────────────┐
│ Top Nav: Logo | Agents | Conversations | User   │
├─────────┬───────────────────────────────────────┤
│         │                                       │
│ Sidebar │         Main Content Area             │
│ (Agent  │                                       │
│  List)  │                                       │
│         │                                       │
├─────────┴───────────────────────────────────────┤
│ Chat Interface (expandable)                     │
└─────────────────────────────────────────────────┘
```

### Pages
1. **Dashboard** (`/`) — Agent overview, recent activity, quick actions
2. **Agent Builder** (`/agents/new`, `/agents/[id]/edit`) — Create/configure agents
3. **Agent Chat** (`/agents/[id]`) — Interactive chat with the agent
4. **Conversations** (`/conversations`) — History of all chats
5. **Settings** (`/settings`) — API keys, profile, preferences

### Responsive Strategy
- Desktop-first (primary target for developers)
- Tablet: collapse sidebar to icons
- Mobile: bottom nav, stacked layouts

## 4. Features & Interactions

### Core Features

#### 4.1 Agent Management
- **Create Agent**: Name, description, system prompt, model selection
- **Edit Agent**: Update all fields, add/remove skills
- **Delete Agent**: Confirmation modal, soft delete with 30-day recovery
- **Clone Agent**: Duplicate with "Copy of" prefix
- **Agent Status**: Active (green), Inactive (gray), Error (red)

#### 4.2 Skills System
- Pre-built skills: Web Search, Image Generation, Calculator, File Reader
- Custom skill creation with JSON schema definition
- Skill enable/disable per agent
- Skill marketplace (future)

#### 4.3 Real-time Chat
- Streaming responses (SSE)
- Message history persistence
- Copy message, regenerate response
- Code block syntax highlighting
- Export conversation as JSON/Markdown

#### 4.4 API Key Management
- Personal API keys for external integrations
- Rate limiting display
- Key rotation with grace period

### Interaction Details

#### Create Agent Flow
1. Click "New Agent" → Modal or dedicated page
2. Fill: Name (required), Description, System Prompt (textarea with markdown)
3. Select Model: dropdown (GPT-4, Claude, Gemini, etc.)
4. Enable Skills: checkbox list
5. Save → Redirect to agent chat

#### Chat Interaction
- User types message → Press Enter or click Send
- Message appears immediately (pending state)
- Streaming response appears token-by-token
- Complete → Show response time, allow feedback
- Error → Show error message with retry button

### Edge Cases
- Empty state: "No agents yet. Create your first agent!"
- Network error: Toast notification, retry button
- Long messages: Scrollable with jump-to-bottom button
- Rate limit: Warning badge, queue requests

## 5. Component Inventory

### Navigation Components
- **TopNav**: Logo, nav links, user dropdown
- **Sidebar**: Agent list, collapse toggle
- **UserMenu**: Avatar, dropdown with settings/logout

### Agent Components
- **AgentCard**: Name, model badge, status indicator, last active
- **AgentForm**: All inputs for create/edit
- **AgentAvatar**: Gradient + initials, optional image
- **SkillBadge**: Icon + name, toggle state

### Chat Components
- **ChatWindow**: Messages container, input area
- **MessageBubble**: User (right, indigo) vs Agent (left, surface)
- **StreamingText**: Animated text with cursor
- **ChatInput**: Textarea, send button, model indicator
- **MessageActions**: Copy, regenerate, feedback buttons

### Common Components
- **Button**: Primary, secondary, ghost, danger variants
- **Input**: Text, textarea with label and error state
- **Select**: Dropdown with search (for model selection)
- **Modal**: Centered overlay with backdrop blur
- **Toast**: Success/error/warning notifications
- **Skeleton**: Loading placeholder with shimmer

## 6. Technical Approach

### Stack
- **Frontend**: Next.js 15 (App Router), TypeScript, Tailwind CSS
- **Backend**: Next.js API Routes + Supabase Edge Functions
- **Database**: Supabase (PostgreSQL + Auth + Realtime)
- **Deployment**: Vercel
- **State**: React Context + Zustand for local state

### Database Schema

```sql
-- Profiles (extends auth.users)
CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id),
  full_name TEXT,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Agents
CREATE TABLE agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  system_prompt TEXT,
  model TEXT DEFAULT 'gpt-4',
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'error')),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Agent Skills (junction)
CREATE TABLE agent_skills (
  agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
  skill_id TEXT NOT NULL,
  config JSONB DEFAULT '{}',
  PRIMARY KEY (agent_id, skill_id)
);

-- Conversations
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) NOT NULL,
  title TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Messages
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- API Keys
CREATE TABLE api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) NOT NULL,
  name TEXT NOT NULL,
  key_hash TEXT NOT NULL,
  last_used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Row Level Security
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

-- Policies: Users can only access their own data
CREATE POLICY "Users can manage own profile" ON profiles
  FOR ALL USING (auth.uid() = id);

CREATE POLICY "Users can manage own agents" ON agents
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own conversations" ON conversations
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own messages" ON messages
  FOR ALL USING (
    EXISTS (SELECT 1 FROM conversations WHERE id = conversation_id AND user_id = auth.uid())
  );

CREATE POLICY "Users can manage own api_keys" ON api_keys
  FOR ALL USING (auth.uid() = user_id);
```

### API Endpoints

```
Auth:
  POST /api/auth/signup        - Register new user
  POST /api/auth/login         - Login
  POST /api/auth/logout        - Logout
  GET  /api/auth/me            - Get current user

Agents:
  GET    /api/agents           - List user's agents
  POST   /api/agents           - Create agent
  GET    /api/agents/[id]      - Get agent details
  PUT    /api/agents/[id]      - Update agent
  DELETE /api/agents/[id]      - Delete agent

Conversations:
  GET    /api/conversations           - List conversations
  POST   /api/conversations           - Create conversation
  GET    /api/conversations/[id]      - Get conversation with messages
  DELETE /api/conversations/[id]      - Delete conversation

Chat:
  POST   /api/chat/[conversation_id]  - Send message (streaming)

Messages:
  POST   /api/messages/[id]/feedback  - Submit feedback
```

### Environment Variables
```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
OPENAI_API_KEY=
```

## 7. File Structure

```
agent-platform/
├── SPEC.md
├── README.md
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── next.config.js
├── .env.local.example
├── supabase/
│   ├── config.toml
│   └── migrations/
│       └── 001_initial_schema.sql
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx (dashboard)
│   │   ├── globals.css
│   │   ├── agents/
│   │   │   ├── page.tsx (list)
│   │   │   ├── new/page.tsx
│   │   │   └── [id]/
│   │   │       ├── page.tsx (chat)
│   │   │       └── edit/page.tsx
│   │   ├── conversations/
│   │   │   └── page.tsx
│   │   ├── settings/
│   │   │   └── page.tsx
│   │   └── api/
│   │       ├── auth/
│   │       ├── agents/
│   │       ├── conversations/
│   │       ├── chat/
│   │       └── messages/
│   ├── components/
│   │   ├── ui/ (Button, Input, Modal, etc.)
│   │   ├── agents/ (AgentCard, AgentForm, etc.)
│   │   ├── chat/ (ChatWindow, MessageBubble, etc.)
│   │   └── layout/ (TopNav, Sidebar, etc.)
│   ├── lib/
│   │   ├── supabase/
│   │   │   ├── client.ts
│   │   │   ├── server.ts
│   │   │   └── middleware.ts
│   │   ├── utils.ts
│   │   └── constants.ts
│   ├── hooks/
│   │   ├── useAgents.ts
│   │   ├── useConversations.ts
│   │   └── useChat.ts
│   └── types/
│       └── database.ts
└── public/
    └── favicon.ico
```