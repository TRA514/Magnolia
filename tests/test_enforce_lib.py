import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import enforce_lib


def test_action_type_send_message():
    assert enforce_lib.action_type_of({"task_type": "send-message"}) == "send-message"


def test_action_type_publish_ticket():
    assert enforce_lib.action_type_of({"task_type": "publish-ticket"}) == "publish-ticket"


def test_action_type_jira_body_marker_when_unstamped():
    fm = {"task_type": None, "body": "x\n<!-- JIRA_DRAFT -->\n...\n<!-- /JIRA_DRAFT -->"}
    assert enforce_lib.action_type_of(fm) == "publish-ticket"


def test_action_type_artifact_is_none():
    assert enforce_lib.action_type_of({"task_type": "prd"}) is None
    assert enforce_lib.action_type_of({"task_type": None, "domain": "product"}) is None


def test_grouping_key_prefers_action_type_then_domain():
    assert enforce_lib.grouping_key({"task_type": "send-message"}) == "send-message"
    assert enforce_lib.grouping_key({"task_type": None, "domain": "eng"}) == "eng"
    assert enforce_lib.grouping_key({}) == "uncategorized"
