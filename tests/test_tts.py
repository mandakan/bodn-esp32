# tests/test_tts.py — tests for bodn.tts helper

from unittest.mock import MagicMock, patch

from bodn.i18n import init, set_language
from bodn.tts import say


class TestSay:
    def setup_method(self):
        init("sv")

    def test_returns_true_when_voice_resolves(self):
        audio = MagicMock()
        with patch(
            "bodn.tts.resolve_voice",
            return_value="/sounds/tts/sv/simon_watch.wav",
        ):
            result = say("simon_watch", audio)
        assert result is True
        audio.play.assert_called_once_with(
            "/sounds/tts/sv/simon_watch.wav", channel="ui"
        )

    def test_returns_false_when_nothing_resolves(self):
        audio = MagicMock()
        with patch("bodn.tts.resolve_voice", return_value=None):
            result = say("missing_key", audio)
        assert result is False
        audio.play.assert_not_called()

    def test_plays_recording_when_resolver_returns_recording_path(self):
        """resolve_voice owns the override logic — tts.say just plays what it returns."""
        audio = MagicMock()
        with patch(
            "bodn.tts.resolve_voice",
            return_value="/sd/sounds/recordings/sv/simon_watch.wav",
        ):
            say("simon_watch", audio)
        audio.play.assert_called_once_with(
            "/sd/sounds/recordings/sv/simon_watch.wav", channel="ui"
        )

    def test_uses_current_language_sv(self):
        init("sv")
        audio = MagicMock()
        with patch("bodn.tts.resolve_voice") as mock_resolve:
            mock_resolve.return_value = "/sounds/tts/sv/bat_low.wav"
            say("bat_low", audio)
        mock_resolve.assert_called_once_with("/sounds/tts/sv/bat_low.wav")

    def test_uses_current_language_en(self):
        set_language("en")
        audio = MagicMock()
        with patch("bodn.tts.resolve_voice") as mock_resolve:
            mock_resolve.return_value = "/sounds/tts/en/bat_low.wav"
            say("bat_low", audio)
        mock_resolve.assert_called_once_with("/sounds/tts/en/bat_low.wav")

    def test_language_switch_changes_path(self):
        audio = MagicMock()

        set_language("sv")
        with patch("bodn.tts.resolve_voice") as mock_resolve:
            mock_resolve.return_value = "/sounds/tts/sv/bat_critical.wav"
            say("bat_critical", audio)
        mock_resolve.assert_called_with("/sounds/tts/sv/bat_critical.wav")

        set_language("en")
        with patch("bodn.tts.resolve_voice") as mock_resolve:
            mock_resolve.return_value = "/sounds/tts/en/bat_critical.wav"
            say("bat_critical", audio)
        mock_resolve.assert_called_with("/sounds/tts/en/bat_critical.wav")

    def test_custom_channel(self):
        audio = MagicMock()
        with patch("bodn.tts.resolve_voice", return_value="/sounds/tts/sv/bat_low.wav"):
            say("bat_low", audio, channel="music")
        audio.play.assert_called_once_with(
            "/sounds/tts/sv/bat_low.wav", channel="music"
        )
