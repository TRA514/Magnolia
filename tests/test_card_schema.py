import json
import pytest
import card_schema

REG = "ui/task-board/cardtypes/registry.json"


def test_real_registry_validates():
    errors = card_schema.validate()  # validates the repo's real registry.json
    assert errors == [], f"registry.json invalid: {errors}"


def test_dangling_signal_reference_is_caught():
    reg = {"slotOrder": ["head", "title", "context", "signals", "body", "actions"],
           "signals": {}, "actions": {},
           "cardTypes": {"task": {"signals": ["ghost"], "actions": [], "body": None}}}
    errors = card_schema.validate_doc(reg, signal_ids={"ghost"}, tokens=set())
    assert any("ghost" in e for e in errors)


def test_hardcoded_color_is_rejected():
    reg = {"slotOrder": ["head", "title", "context", "signals", "body", "actions"],
           "signals": {"x": {"icon": "due", "tokens": ["#ff0000"]}},
           "actions": {}, "cardTypes": {"task": {"signals": ["x"], "actions": [], "body": None}}}
    errors = card_schema.validate_doc(reg, signal_ids={"x"}, tokens={"--accent"})
    assert any("token" in e.lower() or "color" in e.lower() for e in errors)


def test_reordered_slots_are_rejected():
    reg = {"slotOrder": ["title", "head", "context", "signals", "body", "actions"],
           "signals": {}, "actions": {},
           "cardTypes": {"task": {"signals": [], "actions": [], "body": None}}}
    errors = card_schema.validate_doc(reg, signal_ids=set(), tokens=set())
    assert any("slotOrder" in e for e in errors)


def test_unknown_body_renderer_is_caught():
    reg = {"slotOrder": ["head", "title", "context", "signals", "body", "actions"],
           "signals": {}, "actions": {},
           "cardTypes": {"task": {"signals": [], "actions": [], "body": "nope"}}}
    errors = card_schema.validate_doc(reg, signal_ids=set(), tokens=set(),
                                      body_renderers={"diff", "preview", "agreement"})
    assert any("nope" in e for e in errors)
