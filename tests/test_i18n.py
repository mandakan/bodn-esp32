# tests/test_i18n.py — i18n module tests

import json
from pathlib import Path

import pytest

from bodn.i18n import init, t, set_language, get_language, available

_TTS_JSON = Path(__file__).parent.parent / "assets" / "audio" / "tts.json"


class TestI18n:
    def setup_method(self):
        init("sv")

    def test_default_language_is_swedish(self):
        assert get_language() == "sv"

    def test_available_languages(self):
        langs = available()
        assert "sv" in langs
        assert "en" in langs

    def test_translate_swedish(self):
        init("sv")
        assert t("pause_title") == "PAUS"
        assert t("pause_resume") == "Fortsätt"

    def test_translate_english(self):
        init("en")
        assert t("pause_title") == "PAUSED"
        assert t("pause_resume") == "Resume"

    def test_translate_with_args(self):
        init("sv")
        assert t("home_plays_left", 3) == "3 spel kvar"
        init("en")
        assert t("home_plays_left", 3) == "3 plays left"

    def test_missing_key_returns_key(self):
        assert t("nonexistent_key_xyz") == "nonexistent_key_xyz"

    def test_set_language_switches(self):
        init("sv")
        assert t("on") == "PÅ"
        set_language("en")
        assert t("on") == "ON"
        assert get_language() == "en"

    def test_set_language_invalid_falls_back_to_swedish(self):
        set_language("xx")
        assert get_language() == "sv"

    def test_all_sv_keys_exist_in_en(self):
        """Every key in Swedish should also exist in English."""
        from bodn.lang.sv import STRINGS as sv
        from bodn.lang.en import STRINGS as en

        missing = [k for k in sv if k not in en]
        assert missing == [], "Keys in sv.py missing from en.py: {}".format(missing)

    def test_all_en_keys_exist_in_sv(self):
        """Every key in English should also exist in Swedish."""
        from bodn.lang.sv import STRINGS as sv
        from bodn.lang.en import STRINGS as en

        missing = [k for k in en if k not in sv]
        assert missing == [], "Keys in en.py missing from sv.py: {}".format(missing)

    def test_no_empty_values(self):
        """No translation should be an empty string."""
        from bodn.lang.sv import STRINGS as sv
        from bodn.lang.en import STRINGS as en

        empty_sv = [k for k, v in sv.items() if not v]
        empty_en = [k for k, v in en.items() if not v]
        assert empty_sv == [], "Empty values in sv.py: {}".format(empty_sv)
        assert empty_en == [], "Empty values in en.py: {}".format(empty_en)

    def test_tts_keys_exist_in_both_languages(self):
        """Every TTS key in tts.json must be present in sv.py and en.py."""
        if not _TTS_JSON.exists():
            pytest.skip("assets/audio/tts.json not found")

        with open(_TTS_JSON) as f:
            manifest = json.load(f)

        from bodn.lang.sv import STRINGS as sv
        from bodn.lang.en import STRINGS as en

        missing_sv = [k for k in manifest["keys"] if k not in sv]
        missing_en = [k for k in manifest["keys"] if k not in en]
        assert missing_sv == [], "TTS keys missing from sv.py: {}".format(missing_sv)
        assert missing_en == [], "TTS keys missing from en.py: {}".format(missing_en)

    def test_tts_keys_have_no_placeholders(self):
        """TTS keys must not contain {} format placeholders in either language."""
        if not _TTS_JSON.exists():
            pytest.skip("assets/audio/tts.json not found")

        with open(_TTS_JSON) as f:
            manifest = json.load(f)

        from bodn.lang.sv import STRINGS as sv
        from bodn.lang.en import STRINGS as en

        for lang_name, strings in (("sv", sv), ("en", en)):
            with_placeholder = [
                k for k in manifest["keys"] if k in strings and "{" in strings[k]
            ]
            assert with_placeholder == [], (
                "TTS keys with {{}} placeholders in {}.py: {}".format(
                    lang_name, with_placeholder
                )
            )
