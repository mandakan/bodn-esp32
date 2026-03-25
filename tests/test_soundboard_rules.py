# tests/test_soundboard_rules.py — host-side tests for the soundboard rule engine

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware"))

from bodn.soundboard_rules import (
    SoundboardState,
    bank_from_toggles,
    wav_path,
    arcade_wav_path,
    scan_bank,
    scan_arcade,
    load_manifest,
    NUM_MINI_BUTTONS,
    NUM_ARCADE_BUTTONS,
    NUM_BANKS,
    SOUNDS_ROOT,
    MANIFEST_PATH,
    VOLUME_STEP,
    _DEFAULT_COLORS,
    _DEFAULT_BANK_NAMES,
)
import bodn.soundboard_rules as sbr


# ---------------------------------------------------------------------------
# bank_from_toggles
# ---------------------------------------------------------------------------


def test_bank_from_toggles_all_off():
    assert bank_from_toggles(0, 0) == 0


def test_bank_from_toggles_sw0_only():
    assert bank_from_toggles(1, 0) == 1


def test_bank_from_toggles_sw1_only():
    assert bank_from_toggles(0, 1) == 2


def test_bank_from_toggles_both_on():
    assert bank_from_toggles(1, 1) == 3


# ---------------------------------------------------------------------------
# wav_path / arcade_wav_path
# ---------------------------------------------------------------------------


def test_wav_path_format():
    assert wav_path(0, 0) == "/sounds/bank_0/0.wav"
    assert wav_path(3, 7) == "/sounds/bank_3/7.wav"
    assert wav_path(1, 4) == "/sounds/bank_1/4.wav"


def test_arcade_wav_path_format():
    assert arcade_wav_path(0) == "/sounds/arcade/0.wav"
    assert arcade_wav_path(4) == "/sounds/arcade/4.wav"


# ---------------------------------------------------------------------------
# scan_bank / scan_arcade — use monkeypatching to mock filesystem
# ---------------------------------------------------------------------------


def test_scan_bank_all_missing(monkeypatch):
    monkeypatch.setattr(sbr, "_file_exists", lambda p: False)
    result = scan_bank(0)
    assert result == [False] * NUM_MINI_BUTTONS


def test_scan_bank_all_present(monkeypatch):
    monkeypatch.setattr(sbr, "_file_exists", lambda p: True)
    result = scan_bank(0)
    assert result == [True] * NUM_MINI_BUTTONS


def test_scan_bank_mixed(monkeypatch):
    present = {wav_path(0, 0), wav_path(0, 3), wav_path(0, 7)}
    monkeypatch.setattr(sbr, "_file_exists", lambda p: p in present)
    result = scan_bank(0)
    assert result[0] is True
    assert result[1] is False
    assert result[3] is True
    assert result[7] is True
    assert result[4] is False


def test_scan_arcade_all_present(monkeypatch):
    monkeypatch.setattr(sbr, "_file_exists", lambda p: True)
    result = scan_arcade()
    assert result == [True] * NUM_ARCADE_BUTTONS


def test_scan_arcade_none_present(monkeypatch):
    monkeypatch.setattr(sbr, "_file_exists", lambda p: False)
    result = scan_arcade()
    assert result == [False] * NUM_ARCADE_BUTTONS


# ---------------------------------------------------------------------------
# load_manifest — uses real filesystem via tempfile
# ---------------------------------------------------------------------------


def _write_manifest(data):
    """Write manifest JSON to a temp file and patch MANIFEST_PATH."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


def test_load_manifest_missing_file(monkeypatch):
    monkeypatch.setattr(sbr, "MANIFEST_PATH", "/nonexistent/manifest.json")
    result = load_manifest()
    # Should return defaults
    assert len(result["banks"]) == NUM_BANKS
    assert result["labels"] == {}
    for i in range(NUM_BANKS):
        assert result["banks"][i]["color"] == _DEFAULT_COLORS[i]


def test_load_manifest_empty_file(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write("{}")
    tmp.close()
    monkeypatch.setattr(sbr, "MANIFEST_PATH", tmp.name)
    result = load_manifest()
    assert len(result["banks"]) == NUM_BANKS
    assert result["labels"] == {}


def test_load_manifest_bank_names_and_colors(monkeypatch):
    data = {
        "banks": {
            "0": {"name": "Djur", "color": "#FF6B35"},
            "1": {"name": "Instrument", "color": "#3B82F6"},
        }
    }
    path = _write_manifest(data)
    monkeypatch.setattr(sbr, "MANIFEST_PATH", path)
    result = load_manifest()
    assert result["banks"][0]["name"] == "Djur"
    assert result["banks"][0]["color"] == (0xFF, 0x6B, 0x35)
    assert result["banks"][1]["name"] == "Instrument"
    assert result["banks"][1]["color"] == (0x3B, 0x82, 0xF6)
    # Banks 2 and 3 stay as defaults
    assert result["banks"][2]["color"] == _DEFAULT_COLORS[2]


def test_load_manifest_labels(monkeypatch):
    data = {
        "labels": {
            "0_0": "Hund",
            "0_1": "Katt",
            "3_7": "Häst",
        }
    }
    path = _write_manifest(data)
    monkeypatch.setattr(sbr, "MANIFEST_PATH", path)
    result = load_manifest()
    assert result["labels"][(0, 0)] == "Hund"
    assert result["labels"][(0, 1)] == "Katt"
    assert result["labels"][(3, 7)] == "Häst"


def test_load_manifest_malformed_json(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write("not valid json {{")
    tmp.close()
    monkeypatch.setattr(sbr, "MANIFEST_PATH", tmp.name)
    result = load_manifest()
    # Should return defaults without raising
    assert len(result["banks"]) == NUM_BANKS


def test_load_manifest_invalid_bank_index(monkeypatch):
    data = {
        "banks": {
            "99": {"name": "Invalid"},
            "-1": {"name": "Negative"},
        }
    }
    path = _write_manifest(data)
    monkeypatch.setattr(sbr, "MANIFEST_PATH", path)
    result = load_manifest()
    # Out-of-range indices should be silently ignored
    assert len(result["banks"]) == NUM_BANKS


def test_load_manifest_invalid_color_ignored(monkeypatch):
    data = {"banks": {"0": {"name": "Test", "color": "#GGGGGG"}}}
    path = _write_manifest(data)
    monkeypatch.setattr(sbr, "MANIFEST_PATH", path)
    result = load_manifest()
    # Name was applied, bad color falls back to default
    assert result["banks"][0]["name"] == "Test"
    assert result["banks"][0]["color"] == _DEFAULT_COLORS[0]


# ---------------------------------------------------------------------------
# SoundboardState
# ---------------------------------------------------------------------------


def test_initial_state():
    state = SoundboardState()
    assert state.bank == 0
    assert state.playing_slot == -1
    assert state.playing_arcade == -1
    assert state.volume == 50
    assert state.muted is False


def test_set_bank_clears_playing(monkeypatch):
    monkeypatch.setattr(sbr, "_file_exists", lambda p: True)
    state = SoundboardState()
    state.slots_present = [True] * NUM_MINI_BUTTONS
    state.playing_slot = 3
    state.playing_arcade = 1
    state.set_bank(2)
    assert state.bank == 2
    assert state.playing_slot == -1
    assert state.playing_arcade == -1


def test_set_bank_wraps(monkeypatch):
    monkeypatch.setattr(sbr, "_file_exists", lambda p: False)
    state = SoundboardState()
    state.set_bank(5)  # 5 & 3 = 1
    assert state.bank == 1


def test_adjust_volume_clamps():
    state = SoundboardState()
    state.volume = 50
    state.adjust_volume(100)
    assert state.volume == 100
    state.adjust_volume(-200)
    assert state.volume == 0


def test_adjust_volume_step():
    state = SoundboardState()
    state.volume = 50
    state.adjust_volume(1)
    assert state.volume == 50 + VOLUME_STEP
    state.adjust_volume(-1)
    assert state.volume == 50


def test_toggle_mute():
    state = SoundboardState()
    assert state.muted is False
    state.toggle_mute()
    assert state.muted is True
    state.toggle_mute()
    assert state.muted is False


def test_effective_volume_muted():
    state = SoundboardState()
    state.volume = 80
    state.muted = True
    assert state.effective_volume() == 0


def test_effective_volume_unmuted():
    state = SoundboardState()
    state.volume = 80
    assert state.effective_volume() == 80


def test_press_slot_present(monkeypatch):
    monkeypatch.setattr(sbr, "_file_exists", lambda p: True)
    state = SoundboardState()
    state.slots_present = [True] * NUM_MINI_BUTTONS
    path = state.press_slot(3)
    assert path == wav_path(0, 3)
    assert state.playing_slot == 3


def test_press_slot_missing_returns_none(monkeypatch):
    state = SoundboardState()
    state.slots_present = [False] * NUM_MINI_BUTTONS
    path = state.press_slot(3)
    assert path is None
    assert state.playing_slot == -1


def test_press_slot_clears_arcade():
    state = SoundboardState()
    state.playing_arcade = 2
    state.slots_present = [False] * NUM_MINI_BUTTONS
    state.press_slot(0)
    assert state.playing_arcade == -1


def test_press_arcade_present(monkeypatch):
    monkeypatch.setattr(sbr, "_file_exists", lambda p: True)
    state = SoundboardState()
    state.arcade_present = [True] * NUM_ARCADE_BUTTONS
    path = state.press_arcade(2)
    assert path == arcade_wav_path(2)
    assert state.playing_arcade == 2


def test_press_arcade_missing_returns_none():
    state = SoundboardState()
    state.arcade_present = [False] * NUM_ARCADE_BUTTONS
    path = state.press_arcade(0)
    assert path is None
    assert state.playing_arcade == -1


def test_press_arcade_clears_slot():
    state = SoundboardState()
    state.playing_slot = 5
    state.arcade_present = [False] * NUM_ARCADE_BUTTONS
    state.press_arcade(0)
    assert state.playing_slot == -1


def test_on_playback_done():
    state = SoundboardState()
    state.playing_slot = 3
    state.playing_arcade = 1
    state.on_playback_done()
    assert state.playing_slot == -1
    assert state.playing_arcade == -1


def test_bank_color_default():
    state = SoundboardState()
    state.bank = 0
    state.manifest = None
    assert state.bank_color() == _DEFAULT_COLORS[0]


def test_bank_name_from_manifest(monkeypatch):
    monkeypatch.setattr(sbr, "_file_exists", lambda p: False)
    data = {"banks": {"0": {"name": "Djur", "color": "#FF6B35"}}}
    path = _write_manifest(data)
    monkeypatch.setattr(sbr, "MANIFEST_PATH", path)
    state = SoundboardState()
    state.load()
    assert state.bank_name() == "Djur"


def test_slot_label_from_manifest(monkeypatch):
    monkeypatch.setattr(sbr, "_file_exists", lambda p: False)
    data = {"labels": {"0_2": "Katt"}}
    path = _write_manifest(data)
    monkeypatch.setattr(sbr, "MANIFEST_PATH", path)
    state = SoundboardState()
    state.load()
    assert state.slot_label(2) == "Katt"
    assert state.slot_label(3) is None
