# Robinhood Account Activation Runbook

This project does not bypass brokerage authentication, account ownership,
provider eligibility, or trading permissions. Those controls are enforced by
Robinhood and must be completed through supported Robinhood authorization.

The repository now includes a read-only readiness auditor:

```bash
python tools/account_readiness.py
```

The auditor never submits or cancels orders. It exits with code `2` whenever an
enabled account is not ready.

## Current account design

- SAHJONY `***1100`: equity account; monitor-only until an authenticated and
  supported equity execution adapter exists.
- Agentic `***1131`: equity account; monitor-only until an authenticated and
  supported equity execution adapter exists.
- SAHJONY CRYPTO `***5744`: Robinhood Crypto Trading API candidate; execution
  remains blocked until the runtime API account is explicitly approved and the
  API returns funded buying power or holdings.

## Crypto activation gates

All of the following must be true:

1. The Robinhood API key and Ed25519 private key authenticate.
2. Robinhood confirms which user-facing account the returned API account maps to.
3. `ROBINHOOD_APPROVED_API_ACCOUNT` equals the exact runtime API account identifier.
4. The API returns positive buying power or at least one holding.
5. `accounts.yaml` is intentionally changed from `paper: true` only after the
   operator verifies the funded account mapping.
6. `ROBINHOOD_LIVE=true` and
   `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` are set only for a supervised,
   minimum-size validation order.
7. The kill switch and daily-loss circuit breaker have been tested.

## Equity activation gates

An RHS account number is not an API credential. Do not enable either equity
account until Robinhood provides a supported authenticated interface that can:

- return the account identity,
- return balances, positions, and buying power,
- submit and cancel orders,
- return fills and order status,
- select the intended account deterministically.

The adapter must fail closed when the authenticated account does not match the
approved account identity. Until then, keep `execution_mode: monitor_only`,
`adapter_ready: false`, and `paper: true`.

## Running the audit

```bash
cd ~/SAHJONY-AI-TRADING
source .venv/bin/activate
python tools/account_readiness.py
```

A blocked crypto result will resemble:

```json
{
  "status": "blocked",
  "accounts": [
    {
      "account_id": "robinhood_crypto",
      "authenticated": true,
      "identity_verified": false,
      "funded_or_holding_assets": false,
      "trading_ready": false
    }
  ]
}
```

Do not change configuration merely to make the report green. Resolve each
blocker with the brokerage first, then rerun the auditor.
