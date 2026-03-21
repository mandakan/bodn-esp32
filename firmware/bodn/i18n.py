# bodn/i18n.py — lightweight internationalisation for Bodn
#
# Usage:
#   from bodn.i18n import t, set_language
#   t("pause_resume")           → "Fortsätt" (if lang is "sv")
#   t("home_plays_left", 3)     → "3 spel kvar"

_LANGUAGES = ("sv", "en")
_lang = "sv"
_strings = {}


def init(lang="sv"):
    """Load language strings. Call once at boot."""
    global _lang, _strings
    _lang = lang if lang in _LANGUAGES else "sv"
    # Lazy import — only the active language is loaded into RAM.
    if _lang == "sv":
        from bodn.lang.sv import STRINGS
    else:
        from bodn.lang.en import STRINGS
    _strings = STRINGS


def t(key, *args):
    """Translate a string key. Falls back to the key itself if missing."""
    s = _strings.get(key, key)
    return s.format(*args) if args else s


def set_language(lang):
    """Switch language at runtime. Re-imports the string table."""
    init(lang)


def get_language():
    """Return the current language code."""
    return _lang


def available():
    """Return tuple of available language codes."""
    return _LANGUAGES
