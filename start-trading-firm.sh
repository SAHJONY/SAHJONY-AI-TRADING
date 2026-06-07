#!/bin/bash

# Start all services in the background
cd services/director && python main.py &
cd services/risk && python main.py &
cd services/quant && python main.py &
cd services/sentiment && python main.py &
cd services/executor && python main.py &
cd services/compliance && python main.py &

# Start supporting services
redis-server --daemonize yes
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=example postgres

echo "All services started"