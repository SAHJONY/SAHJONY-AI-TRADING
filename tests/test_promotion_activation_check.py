from scripts.promotion_activation_check import REQUIRED_LOCAL


def test_activation_check_requires_all_security_configuration():
    assert set(REQUIRED_LOCAL) == {
        "PROMOTION_ARTIFACT_SIGNING_KEY", "PROMOTION_ARTIFACT_KEY_ID",
        "PROMOTION_STATUS_PUBLISH_TOKEN", "PROMOTION_STATUS_URL",
        "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN",
    }
