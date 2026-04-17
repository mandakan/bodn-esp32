# tests/test_assets.py — host-side tests for the asset path resolver

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware"))

import bodn.assets as assets_mod
from bodn.assets import resolve, resolve_voice


def test_resolve_falls_back_to_flash_when_sd_missing(monkeypatch):
    """resolve() returns the original path when SD file does not exist."""

    def _stat_raise(path):
        raise OSError("no such file")

    monkeypatch.setattr(assets_mod.os, "stat", _stat_raise)
    assert resolve("/sounds/bank_0/0.wav") == "/sounds/bank_0/0.wav"


def test_resolve_returns_sd_path_when_present(monkeypatch, tmp_path):
    """resolve() returns /sd<path> when that file exists on SD."""
    # Create the SD file in a temp location and make os.stat succeed for it.
    sd_path = "/sd/sounds/bank_0/0.wav"
    original_stat = os.stat

    def _fake_stat(path):
        if path == sd_path:
            return original_stat(str(tmp_path))  # stat a real directory (enough)
        raise OSError("no such file")

    monkeypatch.setattr(assets_mod.os, "stat", _fake_stat)
    assert resolve("/sounds/bank_0/0.wav") == sd_path


def test_resolve_flash_path_unchanged(monkeypatch):
    """resolve() returns the exact original path on flash fallback."""

    monkeypatch.setattr(
        assets_mod.os, "stat", lambda p: (_ for _ in ()).throw(OSError())
    )
    path = "/images/cat.bmp"
    assert resolve(path) == path


def test_resolve_sd_path_prefix(monkeypatch, tmp_path):
    """The SD path is always /sd + original path (no double slash)."""
    original_stat = os.stat

    def _fake_stat(path):
        if path.startswith("/sd/"):
            return original_stat(str(tmp_path))
        raise OSError()

    monkeypatch.setattr(assets_mod.os, "stat", _fake_stat)
    result = resolve("/animations/stars.bin")
    assert result == "/sd/animations/stars.bin"


# --- resolve_voice() — hand-recorded overlay on top of generated TTS --------


def _stat_whitelist(monkeypatch, tmp_path, present):
    """Patch os.stat so it succeeds for paths in *present* and raises otherwise."""
    original_stat = os.stat
    present = set(present)

    def _fake_stat(path):
        if path in present:
            return original_stat(str(tmp_path))
        raise OSError("no such file")

    monkeypatch.setattr(assets_mod.os, "stat", _fake_stat)


def test_resolve_voice_prefers_sd_recording(monkeypatch, tmp_path):
    """A recording on the SD card wins over every TTS candidate."""
    _stat_whitelist(
        monkeypatch,
        tmp_path,
        [
            "/sd/sounds/recordings/sv/simon_watch.wav",
            "/sd/sounds/tts/sv/simon_watch.wav",
            "/sounds/tts/sv/simon_watch.wav",
        ],
    )
    assert (
        resolve_voice("/sounds/tts/sv/simon_watch.wav")
        == "/sd/sounds/recordings/sv/simon_watch.wav"
    )


def test_resolve_voice_flash_recording_beats_sd_tts(monkeypatch, tmp_path):
    """A flash recording beats an SD TTS (recording layer wins at every level)."""
    _stat_whitelist(
        monkeypatch,
        tmp_path,
        [
            "/sounds/recordings/sv/simon_watch.wav",
            "/sd/sounds/tts/sv/simon_watch.wav",
            "/sounds/tts/sv/simon_watch.wav",
        ],
    )
    assert (
        resolve_voice("/sounds/tts/sv/simon_watch.wav")
        == "/sounds/recordings/sv/simon_watch.wav"
    )


def test_resolve_voice_falls_back_to_sd_tts(monkeypatch, tmp_path):
    """With no recording anywhere, SD TTS wins over flash TTS."""
    _stat_whitelist(
        monkeypatch,
        tmp_path,
        [
            "/sd/sounds/tts/sv/simon_watch.wav",
            "/sounds/tts/sv/simon_watch.wav",
        ],
    )
    assert (
        resolve_voice("/sounds/tts/sv/simon_watch.wav")
        == "/sd/sounds/tts/sv/simon_watch.wav"
    )


def test_resolve_voice_falls_back_to_flash_tts(monkeypatch, tmp_path):
    """Flash TTS is the final fallback (safety keys live here)."""
    _stat_whitelist(
        monkeypatch,
        tmp_path,
        ["/sounds/tts/sv/bat_critical.wav"],
    )
    assert (
        resolve_voice("/sounds/tts/sv/bat_critical.wav")
        == "/sounds/tts/sv/bat_critical.wav"
    )


def test_resolve_voice_returns_none_when_nothing_exists(monkeypatch):
    """If neither recording nor TTS exists, return None."""

    monkeypatch.setattr(
        assets_mod.os, "stat", lambda p: (_ for _ in ()).throw(OSError())
    )
    assert resolve_voice("/sounds/tts/sv/unknown.wav") is None


def test_resolve_voice_handles_story_paths(monkeypatch, tmp_path):
    """The /tts/ → /recordings/ swap works for story paths too."""
    _stat_whitelist(
        monkeypatch,
        tmp_path,
        ["/sd/stories/peter_rabbit/recordings/sv/home.wav"],
    )
    assert (
        resolve_voice("/stories/peter_rabbit/tts/sv/home.wav")
        == "/sd/stories/peter_rabbit/recordings/sv/home.wav"
    )


def test_resolve_voice_swaps_only_first_tts_segment(monkeypatch, tmp_path):
    """Only the first /tts/ occurrence is swapped — defensive against odd paths."""
    _stat_whitelist(
        monkeypatch,
        tmp_path,
        ["/sd/stories/tts_demo/recordings/sv/tts/sample.wav"],
    )
    # Contrived path with /tts/ appearing twice. Only the first is swapped.
    assert (
        resolve_voice("/stories/tts_demo/tts/sv/tts/sample.wav")
        == "/sd/stories/tts_demo/recordings/sv/tts/sample.wav"
    )
