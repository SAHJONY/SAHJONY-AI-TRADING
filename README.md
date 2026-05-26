# Agent Workforce - Multi-Agent Orchestration System

A sophisticated multi-agent orchestration system with autonomous task execution capabilities.

## 🚀 Features

### AI Agents
- **Personal AI Agent**: Your personal assistant with email, calendar, tasks, notes, reminders, contacts, files, finances, travel, health, research, and memory capabilities
- **AI Receptionist**: Handles visitor greeting, appointment scheduling, knowledge FAQ, and escalations
- **Workforce Metrics Dashboard**: Real-time monitoring of agent performance and system health

### Core Capabilities
- Autonomous task execution across multiple domains
- Real-time agent coordination and communication
- REST API for all agent operations
- Web dashboard for monitoring and control
- Multi-language support (English, Spanish, French, Chinese, Hindi, Arabic, Portuguese, Korean, Japanese, Vietnamese)

## 📁 Project Structure

```
agent-workforce/
├── src/
│   ├── agents/           # Base agent classes
│   ├── api/              # Express server and REST API
│   ├── cli/              # Command-line interface
│   ├── orchestration/    # Task orchestration engine
│   ├── personal-agent/   # Personal AI assistant module
│   ├── personal-receptionist/  # Unified personal + receptionist
│   ├── receptionist/     # AI receptionist module
│   ├── types/            # TypeScript type definitions
│   └── web/              # Web dashboard
├── tests/                # Test suites
├── dist/                 # Compiled JavaScript
└── package.json
```

## 🛠️ Installation

```bash
npm install
```

## 🔨 Build

```bash
npm run build
```

## 🚀 Development

```bash
npm run dev
```

## 📡 API Endpoints

### Personal AI Agent (`/api/personal-agent/*`)
- `POST /chat` - Process personal assistant message
- `GET /context/:userId` - Get user context
- `GET /tasks/:userId` - Get user tasks
- `POST /tasks/:userId` - Create task
- `GET /calendar/:userId` - Get calendar events
- `POST /calendar/:userId` - Create event
- `GET /notes/:userId` - Get notes
- `POST /notes/:userId` - Create note
- `GET /contacts/:userId` - Get contacts
- And more...

### AI Receptionist (`/api/receptionist/*`)
- `POST /chat` - Process visitor interaction
- `GET /visitors` - List visitors
- `POST /visitors` - Register visitor
- `GET /appointments` - List appointments
- `POST /appointments` - Book appointment
- `GET /escalations` - List escalation tickets
- And more...

### Unified Personal Receptionist (`/api/personal-receptionist/*`)
- Combines Personal AI Agent + AI Receptionist capabilities
- Mode toggle between personal assistant and receptionist modes

## 🌐 Web Dashboard

Access the web dashboard at:
- Personal AI Agent: `http://localhost:3000/personal-assistant`
- AI Receptionist: `http://localhost:3000/receptionist`
- Personal Receptionist: `http://localhost:3000/personal-receptionist`
- Workforce Metrics: `http://localhost:3000/`

## 🧪 Testing

```bash
npm test
```

## 📦 Dependencies

- **express**: Web server framework
- **uuid**: UUID generation
- **cors**: Cross-origin resource sharing
- **events**: Event emitter for agent communication

## 📄 License

MIT