"""Generate an Ed25519 keypair for the Robinhood Crypto API — run LOCALLY.

    python -m scripts.robinhood_keygen

Prints two base64 strings:
  • PUBLIC key  → paste into Robinhood's API credentials portal
                  (robinhood.com/account/crypto → API trading) to get your API key.
  • PRIVATE key → store ONLY as the ROBINHOOD_PRIVATE_KEY GitHub Actions secret
                  (and/or your local .env). Never commit it, never paste it in
                  chat, never give it to anyone — it signs real-money orders.

Nothing is sent anywhere; the pair is generated in-process and printed once.
If Robinhood's portal offers "generate keypair in browser", that works too —
this script is for doing it yourself so the private key never leaves your machine.
"""
from __future__ import annotations

import base64


def main() -> int:
    try:
        import nacl.signing
    except ImportError:
        print("pynacl is required:  pip install pynacl")
        return 1
    key = nacl.signing.SigningKey.generate()
    priv = base64.b64encode(bytes(key)).decode()
    pub = base64.b64encode(bytes(key.verify_key)).decode()
    bar = "=" * 64
    print(bar)
    print("  ROBINHOOD CRYPTO — Ed25519 KEYPAIR (generated locally, shown once)")
    print(bar)
    print("  PUBLIC key  (paste into the Robinhood API portal):")
    print(f"    {pub}")
    print()
    print("  PRIVATE key (GitHub secret ROBINHOOD_PRIVATE_KEY — keep it secret):")
    print(f"    {priv}")
    print(bar)
    print("  Next: portal gives you an API key → GitHub secret ROBINHOOD_API_KEY,")
    print("  then run the read-only check (Actions → 'Robinhood Crypto — auth check').")
    print(bar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
