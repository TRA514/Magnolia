import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(ROOT, "scripts", "workers", "message-writer.md")

def test_message_writer_uses_profile_voice_not_jay():
    text = open(F, encoding="utf-8").read()
    assert "jay-voice" not in text.lower()
    assert "datasets/reference/jay-voice.md" not in text
    assert "profile/voice/teams.md" in text and "profile/voice/email.md" in text
    assert not re.search(r"\bJay\b", text), "found a standalone 'Jay' reference"
