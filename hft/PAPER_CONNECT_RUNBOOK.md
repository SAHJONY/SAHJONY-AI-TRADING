# Paper Connect Runbook — HFT Lab v2

Status 2026-09-22: old keys revoked, fresh paper pair minted by Juan (values never
shared). Secure handoff for the pair is still pending — the Secure Vault declines
multi-secret API credentials, and real keys must never appear in chat, files, logs,
source code, documentation, or the repo.

## Prerequisites

- Old Alpaca credentials revoked (the set exposed in the 2026-09-22 WhatsApp dump).
- Fresh PAPER API key pair minted in the Alpaca paper dashboard (paper only —
  not live, not the Broker API sandbox, not OAuth client ID/secret).
- Pair delivered through an approved secure handoff. Until one exists: NO account
  check, NO orders. Do not improvise a handoff.
- Endpoint must be `https://paper-api.alpaca.markets`. The runner hard-refuses
  every other endpoint, including live `https://api.alpaca.markets`.
- Credentials enter only as environment variables, never written to disk:
  `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`.

## Step 1 — read-only account check (first, always)

```
python3 -m hft.paper_run --mode account
```

Default mode. Places zero orders. Verify:
- exit code 0
- account payload shows `paper: true`
- equity / buying power sane
- audit log written with secret-like fields redacted
- no request to any host other than `paper-api.alpaca.markets`

## Step 2 — dry-run trade loop

```
python3 -m hft.paper_run --mode trade
```

Dry-run is the default: submits nothing. Verify:
- every intent passes the v2 RiskGateway
- max 5 orders per run, max $25 notional per order
- audit covers intents, decisions, errors, account snapshots
- market-data failure fails closed with no order

## Step 3 — paper order plan (Juan's explicit approval required)

Present the exact plan before anything is submitted: symbol, side,
quantity/notional, expected price, risk limits, cancellation path.
No submission until he approves the exact plan.

## Step 4 — single paper order (only after Step-3 approval)

```
python3 -m hft.paper_run --mode trade --dry-run=false
```

One tightly capped paper test. Then verify the fill in the audit log.

## Kill switch

- SIGINT at any time: cancels open orders and shuts down.
- Daily-loss threshold breached: same automatic cancel + shutdown.
- Any Alpaca market-data failure: fail-closed, no orders placed.

## Never

- Real-money Alpaca connection without Juan's separate explicit authorization.
- Push, merge, deploy, or publish without his explicit approval.
- Real credential values in chat, memory, logs, files, or the repo.
