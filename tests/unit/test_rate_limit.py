"""Test rate limiting logic for meal analysis."""


def test_daily_limit_constant():
    """Rate limit is set to 20 analyses/day."""
    from server.routers.nutrition import DAILY_ANALYSIS_LIMIT

    assert DAILY_ANALYSIS_LIMIT == 20


def test_allowed_audio_types():
    """Only audio/webm, audio/mp4, audio/mpeg are accepted."""
    from server.routers.nutrition import ALLOWED_AUDIO_TYPES

    assert "audio/webm" in ALLOWED_AUDIO_TYPES
    assert "audio/mp4" in ALLOWED_AUDIO_TYPES
    assert "audio/mpeg" in ALLOWED_AUDIO_TYPES
    assert "audio/wav" not in ALLOWED_AUDIO_TYPES
    assert "audio/ogg" not in ALLOWED_AUDIO_TYPES
    assert "video/mp4" not in ALLOWED_AUDIO_TYPES


def test_voice_note_mime_validation():
    """ALLOWED_AUDIO_TYPES is exactly the expected set."""
    from server.routers.nutrition import ALLOWED_AUDIO_TYPES

    assert ALLOWED_AUDIO_TYPES == {"audio/webm", "audio/mp4", "audio/mpeg"}
