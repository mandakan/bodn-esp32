# bodn/sdcard.py — SD card initialisation and mount
#
# Mounts the SD card from the ILI9341 display breakout's SD slot on SPI3.
# Called once during boot; no-ops gracefully if no card is inserted.
#
# The ESP-IDF SPI bus acquired by SDCard(slot=3) persists across soft
# reboots.  If the normal init fails (SPI already held), we check whether
# the previous VFS mount at /sd is still alive and usable.

import os
from bodn import config

_mounted = False
_sd = None  # SDCard object — must stay alive for deinit on unmount/reboot


def _verify_sd():
    """Return True if /sd is mounted and contains a sounds/ directory."""
    try:
        entries = os.listdir("/sd")
        return "sounds" in entries
    except OSError:
        return False


def mount():
    """Initialise SPI3 and mount the SD card at /sd.

    Returns True on success, False if no card is present or mount fails.
    The device boots normally without an SD card — only media assets are
    unavailable; firmware and core UX sounds are on flash.
    """
    global _mounted, _sd
    if _mounted:
        return True

    from machine import SDCard, Pin

    try:
        _sd = SDCard(
            slot=3,
            sck=Pin(config.SD_SCK),
            mosi=Pin(config.SD_MOSI),
            miso=Pin(config.SD_MISO),
            cs=Pin(config.SD_CS),
        )
        os.mount(_sd, "/sd")
        _mounted = True
        stat = os.statvfs("/sd")
        total_mb = stat[0] * stat[2] // (1024 * 1024)
        free_mb = stat[0] * stat[3] // (1024 * 1024)
        print("SD card mounted at /sd: {}MB total, {}MB free".format(total_mb, free_mb))
        return True
    except OSError:
        # SPI bus may still be held from before a soft reboot.
        # Check if the previous VFS mount is still alive and valid.
        if _verify_sd():
            _mounted = True
            print("SD card at /sd (survived soft reboot)")
            return True
        print("SD card not available")
        return False
    except Exception as e:
        print("SD card not available:", e)
        return False


def is_mounted():
    """Return True if the SD card is currently mounted."""
    return _mounted


def unmount():
    """Unmount the SD card and release the SPI bus. Safe to call even if not mounted."""
    global _mounted, _sd
    if not _mounted:
        return
    try:
        os.umount("/sd")
    except Exception:
        pass
    if _sd is not None:
        try:
            _sd.deinit()
        except Exception:
            pass
        _sd = None
    _mounted = False
