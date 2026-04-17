# bodn/tts.py — language-aware TTS playback helper
#
# say(key, audio, channel="ui")
#   Resolves the spoken WAV for the current language (preferring a recorded
#   override at /sounds/recordings/<lang>/<key>.wav over the generated TTS at
#   /sounds/tts/<lang>/<key>.wav) and queues it for playback.  Returns True if
#   a file was found, False otherwise (caller can fall back to procedural
#   tones via bodn.sounds).
#
# Depends on: bodn.assets (resolve_voice), bodn.i18n (get_language)

from bodn.assets import resolve_voice
from bodn.i18n import get_language


def say(key, audio, channel="ui"):
    """Play a spoken audio clip for the given i18n key.

    Args:
        key:     i18n key (e.g. "simon_watch"). Must exist in tts.json allowlist.
        audio:   AudioEngine instance (must have a .play(path, channel) method).
        channel: AudioEngine channel name (default "ui").

    Returns:
        True if a WAV was found and queued, False if neither a recording nor
        generated TTS exists for this key.
    """
    lang = get_language()
    resolved = resolve_voice("/sounds/tts/{}/{}.wav".format(lang, key))
    if resolved is None:
        return False
    audio.play(resolved, channel=channel)
    return True
