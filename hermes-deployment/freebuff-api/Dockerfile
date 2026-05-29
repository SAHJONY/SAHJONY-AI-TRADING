# Freebuff API Service Dockerfile
# Provides Freebuff coding agent capabilities as an API service

FROM node:18-alpine

WORKDIR /app

# Install curl for healthcheck (Alpine doesn't have it by default)
RUN apk add --no-cache curl

# Install dependencies
COPY package*.json ./
RUN npm install --production

# Copy source
COPY . .

# Expose port
EXPOSE 3001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD curl -f http://localhost:3001/health || exit 1

# Start the service
CMD ["node", "server.js"]