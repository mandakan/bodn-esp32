# bodn/tts.py — language-aware TTS playback helper
#
# say(key, audio, channel="ui")
#   Resolves the spoken WAV for the current language (preferring a recorded
#   override at /sounds/recordings/<lang>/<key>.wav over the generated TTS at
#   /sounds/tts/<lang>/<key>.wav) and queues it for playback.  Returns True if
#   a file was found, False otherwise (caller can fall back to procedural
#   tones via bodn.sounds).
#
# say_seq(keys, audio, channel="ui", gap_ms=80)
#   Fire-and-forget: spawn an asyncio task that plays the clips one after
#   another, waiting for each to finish.  Useful for dynamic challenges built
#   from reusable atoms (number words, operators, connectors) so we don't
#   have to pre-cook every permutation.
#
# Depends on: bodn.assets (resolve_voice), bodn.i18n (get_language)

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

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


async def _say_seq_async(keys, audio, channel, gap_ms):
    for k in keys:
        if k is None:
            continue
        if not say(k, audio, channel=channel):
            continue
        # Let playback kick in, then wait for the voice pool to clear.
        await asyncio.sleep_ms(30)
        # Cap per-clip wait at ~4s so a stuck clip can't wedge the sequence.
        for _ in range(400):
            if not audio.channel_active(channel):
                break
            await asyncio.sleep_ms(10)
        if gap_ms > 0:
            await asyncio.sleep_ms(gap_ms)


def say_seq(keys, audio, channel="ui", gap_ms=80):
    """Spawn a task that plays TTS clips in sequence.

    Fire-and-forget — returns immediately.  Missing clips are skipped so
    partial coverage (e.g. no num_15 recording yet) still speaks what it can.
    """
    try:
        asyncio.create_task(_say_seq_async(list(keys), audio, channel, gap_ms))
    except (AttributeError, RuntimeError):
        # No running loop (e.g. host tests) — fall back to best-effort single calls.
        for k in keys:
            if k is not None:
                say(k, audio, channel=channel)
