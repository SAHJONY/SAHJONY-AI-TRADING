# Multi‑stage Dockerfile for SAHJONY Capital trading bot
# ---------- Builder ----------
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# ---------- Runtime ----------
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app .
ENV PYTHONUNBUFFERED=1
# Non‑root user
RUN useradd -u 1001 -m appuser
USER appuser
CMD ["python", "main.py"]
