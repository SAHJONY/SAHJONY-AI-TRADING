from execution.robinhood_review_gate import (
    ReviewContext,
    ReviewPolicy,
    ReviewRequest,
    assert_no_execution_authority,
    evaluate_review_request,
)


def ready_context(**overrides):
    values = {
        "identity_verified": True,
        "expected_last4": "1131",
        "data_ready": True,
        "funding_ready": True,
        "positions_reconciled": True,
        "quote_fresh": True,
        "market_open": True,
        "execution_authority": False,
        "trading_armed": False,
    }
    values.update(overrides)
    return ReviewContext(**values)


def test_valid_one_dollar_limit_buy_is_reviewable_but_not_placeable():
    request = ReviewRequest(symbol="VTI", side="buy", quantity=0.0025, limit_price=400.0)
    decision = evaluate_review_request(request, ready_context())
    assert decision.allowed is True
    assert decision.stage == "review-only"
    assert decision.execution_authority is False
    assert decision.can_place_order is False
    assert_no_execution_authority(decision)


def test_unresolved_positions_block_review():
    request = ReviewRequest(symbol="VTI", side="buy", quantity=0.0025, limit_price=400.0)
    decision = evaluate_review_request(request, ready_context(positions_reconciled=False))
    assert decision.allowed is False
    assert "positions are not reconciled" in decision.blockers


def test_wrong_account_is_blocked():
    request = ReviewRequest(
        symbol="VTI", side="buy", quantity=0.0025, limit_price=400.0,
        account_last4="1100",
    )
    decision = evaluate_review_request(request, ready_context())
    assert decision.allowed is False
    assert "request account does not match configured Agentic account" in decision.blockers


def test_notional_above_one_dollar_is_blocked():
    request = ReviewRequest(symbol="VTI", side="buy", quantity=0.01, limit_price=400.0)
    decision = evaluate_review_request(request, ready_context())
    assert decision.allowed is False
    assert "review notional exceeds $1.00 cap" in decision.blockers


def test_market_sell_and_live_context_are_blocked():
    request = ReviewRequest(
        symbol="VTI", side="sell", quantity=0.0025, limit_price=400.0,
        order_type="market",
    )
    decision = evaluate_review_request(
        request,
        ready_context(execution_authority=True, trading_armed=True),
    )
    assert decision.allowed is False
    assert "review-only canary permits long buys only" in decision.blockers
    assert "review-only canary permits limit orders only" in decision.blockers
    assert "review-only gate requires execution authority to remain disabled" in decision.blockers


def test_symbol_allowlist_is_fail_closed():
    request = ReviewRequest(symbol="NVDA", side="buy", quantity=0.004, limit_price=200.0)
    decision = evaluate_review_request(request, ready_context(), ReviewPolicy(allowed_symbols=("VTI",)))
    assert decision.allowed is False
    assert "symbol is not in the review allowlist" in decision.blockers
