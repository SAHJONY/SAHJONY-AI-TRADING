from __future__ import annotations

import json

from config import load_config
from dashboard.account_aggregator import AccountDashboardAggregator
from utils.broker import get_broker


def main() -> None:
    cfg = load_config()
    broker = get_broker(cfg)
    result = AccountDashboardAggregator().build(broker)
    print(json.dumps(result["totals"], indent=2))
    if result["warnings"]:
        print("WARNINGS:")
        for warning in result["warnings"]:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
