# Finnhub market data

Finnhub is enabled as a server-side, read-only data provider. It does not expose
an order API and cannot change trading or execution authority.

- Vercel reads `FINNHUB_API_KEY` only inside `/api/finnhub`.
- The browser calls the same-origin proxy and never receives the key.
- GitHub Actions uses the secret only in the read-only canary workflow.
- Quote symbols, prices, and source timestamps are validated fail-closed.
- The canary explicitly blanks all live-trading credentials and flags.

Manual validation: run the **Finnhub — read-only canary** workflow. A valid run
prints only symbol, provider, quote age, and the fixed safety declarations
`read_only=true` and `execution_authority=false`.
