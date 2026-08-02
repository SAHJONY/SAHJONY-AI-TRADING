# Robinhood Agentic review-only rollout

This milestone does **not** activate live trading. It adds a pure policy gate that
can decide whether a proposed long-equity order is eligible to be sent to
Robinhood's `review_equity_order` tool at a later integration stage.

## Current safety state

```env
ROBINHOOD_MCP_LIVE=false
ROBINHOOD_LIVE=false
LIVE_TRADING_ACK=
```

The existing local MCP gateway remains read-only and exposes no order routes.
The review gate has no broker, MCP, network, or order-placement imports.
The review-only venue boundary is implemented but is not injected by default.

Its complete allowlist is:

- `check_tradability`
- `review_order`
- `get_order_status`
- `discover_cancel_capability`

It structurally rejects `place_order`, `replace_order`, `modify_order`, and
`cancel_order`. The production adapter also refuses to derive execution
authority from a transport whose `placement_available` marker is false.

Until broker evidence is exactly `RECONCILED`, review eligibility returns:

```json
{
  "eligible": false,
  "stage": "review-only",
  "reason": "broker reconciliation is not RECONCILED",
  "execution_authority": false,
  "placement_available": false
}
```

## Default review policy

- Agentic account ending `1131` only
- Identity, data, funding, positions reconciliation, and quote freshness required
- Market must be open
- `VTI` only
- Long buys only
- Limit orders only
- Good-for-day only
- Maximum reviewed notional: `$1.00`
- Execution authority must remain disabled
- A successful review decision can never place an order

## Promotion sequence

1. Resolve the upstream positions discrepancy.
2. Keep the system in authenticated read-only observation mode across multiple sessions.
3. Integrate only `get_equity_tradability` and `review_equity_order` behind this policy gate.
4. Store the complete reviewed order, warnings, estimated cost, identity, quote timestamp, and policy decision in the immutable audit journal.
5. Require explicit human approval before creating any separate placement-capable canary adapter.
6. Keep placement, cancellation, options, market orders, and autonomous execution out of scope for this milestone.

## Validation

```bash
python -m pytest tests/test_robinhood_review_gate.py -q
python -m pytest -q
```

A review result is advisory evidence only. It does not confer trading readiness,
execution authority, or permission to place an order.
