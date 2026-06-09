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


def test_gather_evidence_ticket_description_in_evidence():
    # parse_jira_draft's ### Description capture is non-greedy and stops at the
    # next "### " section (lookahead in the regex). A description followed by a
    # second "### " section therefore parses non-empty — verified against
    # jira_publish.parse_jira_draft below — and the text reaches the evidence.
    body = (
        "<!-- JIRA_DRAFT -->\n"
        "<!-- JIRA_TYPE:Bug -->\n"
        "<!-- JIRA_SUMMARY:Login fails on Safari -->\n"
        "### Description\n"
        "Users on Safari 17 cannot log in; the button does nothing.\n"
        "### Acceptance Criteria\n"
        "- Login works on Safari 17\n"
        "<!-- /JIRA_DRAFT -->"
    )
    # Confirm the fixture genuinely parses a non-empty description before asserting.
    import jira_publish
    draft = jira_publish.parse_jira_draft(body)
    assert draft["description"], "fixture must parse a non-empty description"

    ev, note = judge.gather_evidence("ticket", {"task_type": "publish-ticket"}, body, "T-1")
    assert ev and "Safari" in ev


def test_gather_evidence_ticket_no_draft_returns_none():
    # No JIRA_DRAFT block in the body → nothing to grade → skip.
    ev, note = judge.gather_evidence("ticket", {"task_type": "publish-ticket"}, "no draft here", "T-2")
    assert ev is None
