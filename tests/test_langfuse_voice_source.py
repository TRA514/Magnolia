import inspect
import langfuse_setup

def test_register_voice_uses_profile_not_dead_path():
    src = inspect.getsource(langfuse_setup.register_voice)
    assert "datasets/reference/jay-voice.md" not in src
    assert "voice_text" in src or "profile/voice" in src
    assert "judge-voice" in src
