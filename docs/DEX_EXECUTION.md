# Decentralized-exchange execution

The DEX adapter is an execution foundation, not a claim that every on-chain
venue has identical semantics. It routes EVM swaps through an aggregator, which
can source liquidity from many AMMs without writing one adapter per pool.

## Current capability

- `BROKER=dex`
- 0x AllowanceHolder quote and transaction construction
- EVM chain selected with `DEX_CHAIN_ID`
- token allowlist
- hard maximum slippage
- no private key storage
- no signing or broadcasting
- every prepared swap returns `approval_required`

Use `DEXBroker.prepare_swap(sell_token, buy_token, sell_amount)` with token
contract addresses and base-unit amounts. The returned payload must be
simulated again and signed by MetaMask, a hardware wallet, or a policy-controlled
multisig.

## Coverage roadmap

1. EVM routing: 0x today; add 1inch as a second independent quote source.
2. Solana: add Jupiter using the same normalized quote object.
3. Cross-chain: add intent/bridge providers only after bridge-risk policies.
4. Non-EVM chains: implement dedicated drivers because addresses, fee markets,
   finality, signing, and token standards differ.

## Production gates

- explicit chain and token allowlists
- verified token decimals and contracts
- two independent quotes for material orders
- RPC simulation and revert detection
- price-impact, gas, slippage, and stale-quote limits
- MEV-protected/private submission where supported
- daily notional and per-token exposure limits
- owner-approved signer or bounded smart account
- on-chain receipt reconciliation before ledger updates
- emergency wallet-level revocation and pause

Never put a seed phrase or private key in repository files, prompts, logs, MCP
configuration, CI variables exposed to pull requests, or the trading worker.
