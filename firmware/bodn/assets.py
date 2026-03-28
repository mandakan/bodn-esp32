# bodn/assets.py — asset path resolver (flash/SD overlay)
#
# Checks the SD card first, falls back to flash for any asset path.
# One os.stat() per call (~0.1 ms) — negligible vs file I/O.
#
# Usage:
#   from bodn.assets import resolve
#   path = resolve("/sounds/bank_0/0.wav")
#   # Returns "/sd/sounds/bank_0/0.wav" if present on SD, else the original path.

import os


def resolve(path):
    """Return the best filesystem path for an asset.

    Checks /sd<path> first; returns it if the file exists there.
    Falls back to <path> on flash (no existence check — let the caller fail).

    Args:
        path: logical asset path, must start with "/" (e.g. "/sounds/bank_0/0.wav").

    Returns:
        Absolute filesystem path string.
    """
    sd_path = "/sd" + path
    try:
        os.stat(sd_path)
        return sd_path
    except OSError:
        return path
