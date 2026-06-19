# SAHJONY‑AI‑TRADING – Autonomous Alpaca Trading Bot

An end‑to‑end, self‑contained algorithmic trading engine built for **Alpaca Paper Trading**.
The project is structured for seamless CI/CD integration and includes:

- **Modular Python code** (`utils/`, `strategies/`)  
- **Persistent state** (`state.json`)  
- **Docker support** for reproducible deployment  
- **Helm chart** for Kubernetes rollout (optional)  
- **Cron‑ready** entry point (`main.py`) that can be scheduled every 15 min during market hours.

## Quick start (local)

```bash
# 1. Clone the repo (already done)
# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the template env and fill in your Alpaca keys
cp .env.template .env
# edit .env → set ALPACA_API_KEY and ALPACA_API_SECRET

# 5. Run the bot (dry‑run)
python main.py --dry-run
```

## Docker

```bash
docker build -t sahjony/ai-trading .
docker run -it --rm \
-v $(pwd)/state.json:/app/state.json \
-v $(pwd)/.env:/app/.env \
sahjony/ai-trading
```

## Kubernetes (Helm)

```bash
helm upgrade --install ai-trading ./helm/chart \ 
--namespace trading \ 
--set image.repository=sahejony/ai-trading \ 
--set image.tag=latest
```

## Scheduling

A typical CronJob (K8s) runs every 15 minutes during NYSE market hours:

```yaml
schedule: "*/15 13-20 * * 1-5"   # EST 9:30‑16:00 => UTC 13‑20
```

---

For full documentation on each strategy, see the `strategies/` package.
