import pytest
import task_lib


def test_validate_rejects_non_editable_field():
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("id", "X")
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("queue", "agent")
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("created", "2026-01-01")


def test_validate_priority_enum():
    assert task_lib.validate_field_edit("priority", "high") == "high"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("priority", "urgent")


def test_validate_status_excludes_done_and_cancelled():
    assert task_lib.validate_field_edit("status", "in-progress") == "in-progress"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("status", "done")
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("status", "cancelled")


def test_validate_domain_enum():
    assert task_lib.validate_field_edit("domain", "product") == "product"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("domain", "nonsense")


def test_validate_date_format():
    assert task_lib.validate_field_edit("due", "2026-07-01") == "2026-07-01"
    assert task_lib.validate_field_edit("due", "") == ""
    assert task_lib.validate_field_edit("waiting_expected", "2026-07-01") == "2026-07-01"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("due", "07/01/2026")


def test_validate_text_strips_and_bounds():
    assert task_lib.validate_field_edit("waiting_on", "  Acme Corp  ") == "Acme Corp"
    assert task_lib.validate_field_edit("title", "Ship it") == "Ship it"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("title", "x" * 201)


def test_validate_tags_coerces_list():
    assert task_lib.validate_field_edit("tags", ["a", " b ", ""]) == ["a", "b"]
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("tags", "a,b")
