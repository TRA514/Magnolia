import task_lib
import cron_lib


def test_onboarding_is_a_valid_domain():
    assert "onboarding" in task_lib.DOMAINS
    assert "onboarding" in cron_lib.VALID_DOMAINS
