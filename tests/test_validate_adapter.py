import types
import typing
import importlib
import factory_lib
from adapters.project_management._contract import ProjectManagementAdapter


def test_real_asana_conforms():
    assert factory_lib.validate_adapter("project_management", "asana") == []


def test_transcript_otter_conforms():
    # Locks in cross-family generality: the sync-only transcript family validates too.
    assert factory_lib.validate_adapter("transcript", "otter") == []


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


def _two_protocol_contract():
    """A real module object whose two Protocols both name it as their __module__."""
    fake = types.ModuleType("adapters.project_management._contract")

    class AAdapter(typing.Protocol):
        def publish(self, draft, root=None) -> tuple: ...

    class BAdapter(typing.Protocol):
        def publish(self, draft, root=None) -> tuple: ...

    AAdapter.__module__ = fake.__name__
    BAdapter.__module__ = fake.__name__
    fake.AAdapter = AAdapter
    fake.BAdapter = BAdapter
    return fake


def test_protocols_in_detects_multiple():
    # Direct detection: two Protocols in the contract module are both found.
    assert len(factory_lib._protocols_in(_two_protocol_contract())) == 2


def test_multiple_protocols_is_flagged(monkeypatch):
    # The count-guard in validate_adapter: an ambiguous contract is a hard error,
    # never a silent alphabetically-first pick.
    fake = _two_protocol_contract()
    monkeypatch.setattr(
        importlib, "import_module",
        lambda name, *a, **k: fake if name.endswith("._contract")
        else (_ for _ in ()).throw(ModuleNotFoundError(name)))
    probs = factory_lib.validate_adapter("project_management", "whatever")
    assert any("exactly one Protocol" in p for p in probs)
