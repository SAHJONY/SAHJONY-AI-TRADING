# Adding & withdrawing funds

> **Key fact:** money does **not** move through this bot. Your cash lives at your
> broker (Alpaca). The platform's job is to **track** every deposit/withdrawal so
> your returns reflect *trading*, not *funding* — a $10k deposit must never look
> like a $10k gain. That tracking is the **Treasury / Capital Ledger**.

## 1. How the real money actually moves

### Paper account (where you start)
There is **no real cash**. To change the paper balance, open the Alpaca
dashboard → **Paper account** → reset / adjust the starting balance. Then record
it in the ledger so the dashboard accounting matches (method `paper_reset`).

### Live account (real money)
Fund and withdraw through **Alpaca itself** — the bot can't and shouldn't:
1. In the Alpaca app/website, **link your bank** (Plaid or manual micro-deposits).
2. **Deposit:** Transfers → ACH (free, ~1–3 business days) or wire (fast, fee).
3. **Withdraw:** Transfers → withdraw to the linked bank. Note Alpaca's
   settlement (T+1) and pattern-day-trader rules before pulling cash.
4. The standard **Trading API** this app uses *cannot* initiate transfers. Only
   Alpaca's separate **Broker API** can (a different product with its own KYC).
   If you ever want programmatic ACH, that's a deliberate, larger migration —
   ask and we'll scope it.

## 2. Record every flow in the ledger (so returns stay honest)

After you deposit or withdraw at Alpaca, log it once:

```bash
# put money in
python -m treasury.treasury deposit  --amount 10000 --method ach --note "initial funding"
# take money out
python -m treasury.treasury withdraw --amount 2500  --method ach
# where you stand
python -m treasury.treasury summary
python -m treasury.treasury history
```

`--method` ∈ `ach | wire | alpaca | paper_reset | manual`. Optionally pass
`--equity-after` (account equity right after the flow) for tighter accounting.

Multi-account: prefix with `SAHJONY_HOME=...` so each desk keeps its own ledger:
```bash
SAHJONY_HOME=~/desks/us-equities python -m treasury.treasury deposit --amount 5000
```

## 3. How the accounting works

The dashboard's **Book → Treasury · Capital Ledger** panel shows it live:

- **Net capital** = total deposits − total withdrawals (the money *you* put in).
- **Trading P&L** = current equity − net capital (what the strategy actually made).
- **Trading return %** = equity / net capital − 1.

So depositing $10k moves *net capital* up by $10k and leaves *trading return* at
0% — exactly right. With no flows recorded, the platform falls back to the
opening-equity baseline. This is the same separation a real fund reports to its
investors (capital contributions vs. investment performance).

> Investor capital (family & friends putting money into *your* fund) is a
> different ledger — the CRM (`python -m crm.crm contribute …`). The Treasury here
> is **your own account's** cash in and out.
