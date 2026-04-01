# bodn/assets.py — asset path resolver and preloader (flash/SD overlay)
#
# Checks the SD card first, falls back to flash for any asset path.
# One os.stat() per call (~0.1 ms) — negligible vs file I/O.
#
# Usage:
#   from bodn.assets import resolve, resolve_sounds, preload_sounds
#   path = resolve("/sounds/bank_0/0.wav")
#   # Returns "/sd/sounds/bank_0/0.wav" if present on SD, else the original path.
#
#   paths = resolve_sounds("/sounds/space/", ["thruster", "shields", "horn"])
#   # Returns ["/sd/sounds/space/thruster.wav", None, "/sd/sounds/space/horn.wav"]
#
#   buffers = preload_sounds("/sounds/space/", ["engine_loop", "alarm_loop"])
#   # Returns [bytearray(PCM data), None] — raw PCM loaded into RAM/PSRAM

import os
import struct


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


def preload_wav(path):
    """Read a WAV file and return its raw PCM data as a bytearray.

    Parses the WAV header to find the data chunk, then reads the entire
    PCM payload into memory.  Returns None if the file doesn't exist.

    Intended to be called at mode enter so playback can use MemorySource
    (zero I/O per frame).  Allocates into PSRAM on ESP32-S3.
    """
    resolved = resolve(path)
    try:
        os.stat(resolved)
    except OSError:
        return None

    with open(resolved, "rb") as f:
        # RIFF header
        riff = f.read(12)
        if len(riff) < 12 or riff[0:4] != b"RIFF" or riff[8:12] != b"WAVE":
            return None

        # Walk chunks to find 'data'
        while True:
            chunk_hdr = f.read(8)
            if len(chunk_hdr) < 8:
                return None
            chunk_id = chunk_hdr[0:4]
            chunk_size = struct.unpack("<I", chunk_hdr[4:8])[0]
            if chunk_id == b"data":
                data = bytearray(chunk_size)
                f.readinto(data)
                return data
            # Skip non-data chunks
            f.read(chunk_size)


def preload_sounds(directory, names):
    """Preload a list of named WAV files into RAM bytearrays.

    Like :func:`resolve_sounds` but reads the entire PCM payload into
    memory.  Returns a list parallel to *names* — bytearray or None.
    """
    buffers = []
    for name in names:
        buf = preload_wav(directory + name + ".wav")
        buffers.append(buf)
    return buffers
