# tests/test_tts.py — tests for bodn.tts helper

from unittest.mock import MagicMock, patch

from bodn.i18n import init, set_language
from bodn.tts import say


class TestSay:
    def setup_method(self):
        init("sv")

    def test_returns_true_when_file_exists(self):
        audio = MagicMock()
        with patch("bodn.tts.resolve", return_value="/sounds/tts/sv/simon_watch.wav"):
            with patch("bodn.tts.os.stat"):
                result = say("simon_watch", audio)
        assert result is True
        audio.play.assert_called_once_with(
            "/sounds/tts/sv/simon_watch.wav", channel="ui"
        )

    def test_returns_false_when_file_missing(self):
        audio = MagicMock()
        with patch("bodn.tts.resolve", return_value="/sounds/tts/sv/missing.wav"):
            with patch("bodn.tts.os.stat", side_effect=OSError):
                result = say("missing_key", audio)
        assert result is False
        audio.play.assert_not_called()

    def test_uses_current_language_sv(self):
        init("sv")
        audio = MagicMock()
        with patch("bodn.tts.resolve") as mock_resolve:
            mock_resolve.return_value = "/sounds/tts/sv/bat_low.wav"
            with patch("bodn.tts.os.stat"):
                say("bat_low", audio)
        mock_resolve.assert_called_once_with("/sounds/tts/sv/bat_low.wav")

    def test_uses_current_language_en(self):
        set_language("en")
        audio = MagicMock()
        with patch("bodn.tts.resolve") as mock_resolve:
            mock_resolve.return_value = "/sounds/tts/en/bat_low.wav"
            with patch("bodn.tts.os.stat"):
                say("bat_low", audio)
        mock_resolve.assert_called_once_with("/sounds/tts/en/bat_low.wav")

    def test_language_switch_changes_path(self):
        audio = MagicMock()

        set_language("sv")
        with patch("bodn.tts.resolve") as mock_resolve:
            mock_resolve.return_value = "/sounds/tts/sv/bat_critical.wav"
            with patch("bodn.tts.os.stat"):
                say("bat_critical", audio)
        mock_resolve.assert_called_with("/sounds/tts/sv/bat_critical.wav")

        set_language("en")
        with patch("bodn.tts.resolve") as mock_resolve:
            mock_resolve.return_value = "/sounds/tts/en/bat_critical.wav"
            with patch("bodn.tts.os.stat"):
                say("bat_critical", audio)
        mock_resolve.assert_called_with("/sounds/tts/en/bat_critical.wav")

    def test_custom_channel(self):
        audio = MagicMock()
        with patch("bodn.tts.resolve", return_value="/sounds/tts/sv/bat_low.wav"):
            with patch("bodn.tts.os.stat"):
                say("bat_low", audio, channel="music")
        audio.play.assert_called_once_with(
            "/sounds/tts/sv/bat_low.wav", channel="music"
        )

    def test_resolve_called_for_sd_first_logic(self):
        """resolve() is always called — SD-first logic lives in bodn.assets.resolve."""
        audio = MagicMock()
        with patch("bodn.tts.resolve") as mock_resolve:
            mock_resolve.return_value = "/sd/sounds/tts/sv/simon_watch.wav"
            with patch("bodn.tts.os.stat"):
                say("simon_watch", audio)
        mock_resolve.assert_called_once_with("/sounds/tts/sv/simon_watch.wav")
        audio.play.assert_called_once_with(
            "/sd/sounds/tts/sv/simon_watch.wav", channel="ui"
        )
