#!/bin/bash
# Hermes Agent Deployment Script
# Usage: ./deploy.sh [environment]
# Environments: docker, railway, render, local

set -e

ENVIRONMENT=${1:-docker}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Hermes Agent Deployment Script"
echo "=================================="
echo "Environment: $ENVIRONMENT"
echo ""

# Load environment variables
if [ -f .env ]; then
    echo "📁 Loading environment from .env..."
    set -a
    source .env
    set +a
else
    echo "⚠️  No .env file found. Please create one from .env.example"
    exit 1
fi

deploy_docker() {
    echo "🐳 Deploying with Docker..."
    
    # Build Docker image
    echo "📦 Building Docker image..."
    docker build -t hermes-agent:latest .
    
    # Use docker-compose for zero-downtime deployment
    echo "🚀 Starting Hermes Agent via docker-compose..."
    docker-compose up -d --build
    
    # Wait for health check
    echo "⏳ Waiting for service to be healthy..."
    sleep 10
    
    # Verify health
    if curl -f http://localhost:8642/health 2>/dev/null; then
        echo "✅ Docker deployment complete!"
        echo "   Hermes Agent running at: http://localhost:8642"
        echo "   Health check: http://localhost:8642/health"
    else
        echo "⚠️  Service started but health check failed. Check logs with: docker-compose logs"
    fi
}

deploy_railway() {
    echo "🚂 Deploying to Railway..."
    
    echo "📦 Installing Hermes Agent..."
    pip install hermes-agent
    
    echo "🚀 Starting Hermes Gateway..."
    exec hermes gateway
}

deploy_render() {
    echo "🎨 Deploying to Render..."
    
    echo "📦 Installing Hermes Agent..."
    pip install hermes-agent
    
    echo "🚀 Starting Hermes Gateway..."
    exec hermes gateway
}

deploy_local() {
    echo "💻 Running locally (non-Docker)..."
    
    # Check if hermes-agent is installed
    if ! command -v hermes &> /dev/null; then
        echo "📦 Installing Hermes Agent..."
        pip install hermes-agent
    fi
    
    echo "🚀 Starting Hermes Gateway on port $API_SERVER_PORT..."
    hermes gateway
}

# Main deployment logic
case $ENVIRONMENT in
    docker)
        deploy_docker
        ;;
    railway)
        deploy_railway
        ;;
    render)
        deploy_render
        ;;
    local)
        deploy_local
        ;;
    *)
        echo "❌ Unknown environment: $ENVIRONMENT"
        echo "Usage: $0 [docker|railway|render|local]"
        exit 1
        ;;
esac

echo ""
echo "📋 Next Steps:"
echo "   1. Update your SAHJONY platform's .env.local with:"
echo "      HERMES_AGENT_URL=http://localhost:8642"
echo "      HERMES_AGENT_API_KEY=$API_SERVER_KEY"
echo "   2. Test the connection: curl http://localhost:8642/health"