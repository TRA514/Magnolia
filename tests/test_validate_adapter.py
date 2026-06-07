import types
import factory_lib
from adapters.project_management._contract import ProjectManagementAdapter


def test_real_asana_conforms():
    assert factory_lib.validate_adapter("project_management", "asana") == []


def test_missing_publish_is_flagged():
    fake = types.SimpleNamespace(is_configured=lambda root=None: True)
    probs = factory_lib._conformance_problems(fake, ProjectManagementAdapter)
    assert any("publish" in p for p in probs)


def test_wrong_signature_is_flagged():
    fake = types.SimpleNamespace(
        is_configured=lambda root=None: True,
        publish=lambda x: ("K", "U"),          # missing draft/root param names
    )
    probs = factory_lib._conformance_problems(fake, ProjectManagementAdapter)
    assert any("draft" in p or "root" in p for p in probs)


def test_import_error_is_flagged():
    probs = factory_lib.validate_adapter("project_management", "does_not_exist")
    assert any("import failed" in p for p in probs)
