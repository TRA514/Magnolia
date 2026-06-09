import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import judge


def test_detect_kind_ticket():
    assert judge.detect_kind({"task_type": "publish-ticket"}) == "ticket"


def test_ticket_rubric_registered():
    assert "ticket" in judge.RUBRICS
    assert "ticket" in judge.DIMENSIONS_BY_KIND


def test_gather_evidence_ticket_parses_draft():
    # parse_jira_draft reads the summary from the JIRA_SUMMARY HTML comment and
    # the description from the ### Description markdown section. A bare
    # "### Summary" header is NOT how the parser sources the summary.
    body = (
        "<!-- JIRA_DRAFT -->\n"
        "<!-- JIRA_TYPE:Bug -->\n"
        "<!-- JIRA_SUMMARY:Fix the thing -->\n"
        "### Description\n"
        "When X then Y.\n"
        "<!-- /JIRA_DRAFT -->"
    )
    ev, note = judge.gather_evidence("ticket", {"task_type": "publish-ticket"}, body, "T-1")
    assert ev and "Fix the thing" in ev
