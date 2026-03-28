# tests/test_assets.py — host-side tests for the asset path resolver

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware"))

import bodn.assets as assets_mod
from bodn.assets import resolve


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
