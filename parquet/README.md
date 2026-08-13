# Parquet terminal

Parquet is a transparent dashboard over the repository's existing Python trading engine. It does not own broker credentials or submit orders. The Python engine remains the sole execution authority, including its reconciliation, circuit breaker, position cap, data-integrity, and live-arming checks.

Run `npm install`, then `npm run dev`. The Vite UI is served on port 5173 and the read-only Node/WebSocket projection service on port 8788. The service calls `parquet/bridge/snapshot.py` every 30 seconds and records each council signal in `data/parquet_attribution.db` for later realized-alpha attribution.

`npm run typecheck` and `npm run build` validate the terminal. The public contract is defined in `parquet/ui/src/types.ts`.
