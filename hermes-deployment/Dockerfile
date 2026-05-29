# Hermes Agent Dockerfile for SAHJONY Platform Microservice
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl git && rm -rf /var/lib/apt/lists/*

# Install Hermes Agent from NousResearch
RUN pip install git+https://github.com/NousResearch/hermes-agent.git

# Create non-root user
RUN useradd -m -u 10000 hermes && mkdir -p /opt/hermes/data

# Set environment variables
ENV API_SERVER_ENABLED=true
ENV API_SERVER_PORT=8642
ENV API_SERVER_HOST=0.0.0.0
ENV HERMES_GID=10000
ENV HERMES_UID=10000

# Create data directory with permissions
RUN chown -R hermes:hermes /opt/hermes

USER hermes

EXPOSE 8642

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 CMD curl -f http://localhost:8642/health || exit 1

CMD ["hermes", "gateway"]