# bodn/assets.py — asset path resolver (flash/SD overlay)
#
# Checks the SD card first, falls back to flash for any asset path.
# One os.stat() per call (~0.1 ms) — negligible vs file I/O.
#
# Usage:
#   from bodn.assets import resolve, resolve_sounds
#   path = resolve("/sounds/bank_0/0.wav")
#   # Returns "/sd/sounds/bank_0/0.wav" if present on SD, else the original path.
#
#   paths = resolve_sounds("/sounds/space/", ["thruster", "shields", "horn"])
#   # Returns ["/sd/sounds/space/thruster.wav", None, "/sd/sounds/space/horn.wav"]

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


def resolve_sounds(directory, names):
    """Resolve a list of named WAV files inside a directory.

    Intended to be called once at mode enter so there is zero per-press
    overhead during play.  Each name is looked up as ``<directory><name>.wav``
    via :func:`resolve` (SD first, flash fallback).  If the file does not
    exist at either location the slot is ``None``.

    Args:
        directory: logical directory path ending with "/" (e.g. "/sounds/space/").
        names:     list of stem names (without extension).

    Returns:
        List parallel to *names* — resolved path string or None per entry.
    """
    paths = []
    for name in names:
        resolved = resolve(directory + name + ".wav")
        try:
            os.stat(resolved)
            paths.append(resolved)
        except OSError:
            paths.append(None)
    return paths
