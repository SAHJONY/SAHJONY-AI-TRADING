# Market Feed Simulator Dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY simulator.py .
RUN pip install --no-cache-dir numpy

ENTRYPOINT ["python", "simulator.py"]
