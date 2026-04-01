# bodn/tts.py — language-aware TTS playback helper
#
# say(key, audio, channel="ui")
#   Resolves the TTS WAV for the current language and queues it for playback.
#   Returns True if the file was found, False otherwise (caller can fall back
#   to procedural tones via bodn.sounds).
#
# Depends on: bodn.assets (resolve), bodn.i18n (get_language)

import os

from bodn.assets import resolve
from bodn.i18n import get_language


def say(key, audio, channel="ui"):
    """Play a TTS audio clip for the given i18n key.

    Args:
        key:     i18n key (e.g. "simon_watch"). Must exist in tts.json allowlist.
        audio:   AudioEngine instance (must have a .play(path, channel) method).
        channel: AudioEngine channel name (default "ui").

    Returns:
        True if the WAV was found and queued, False if the file is missing.
    """
    lang = get_language()
    path = "/sounds/tts/{}/{}.wav".format(lang, key)
    resolved = resolve(path)
    try:
        os.stat(resolved)
    except OSError:
        return False
    audio.play(resolved, channel=channel)
    return True
