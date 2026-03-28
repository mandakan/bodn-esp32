# bodn/sdcard.py — SD card initialisation and mount
#
# Mounts the SD card from the ILI9341 display breakout's SD slot on SPI3.
# Called once during boot; no-ops gracefully if no card is inserted.

import os
from bodn import config

_mounted = False


def mount():
    """Initialise SPI3 and mount the SD card at /sd.

    Returns True on success, False if no card is present or mount fails.
    The device boots normally without an SD card — only media assets are
    unavailable; firmware and core UX sounds are on flash.
    """
    global _mounted
    if _mounted:
        return True
    try:
        from machine import SDCard, Pin

        sd = SDCard(
            slot=3,
            sck=Pin(config.SD_SCK),
            mosi=Pin(config.SD_MOSI),
            miso=Pin(config.SD_MISO),
            cs=Pin(config.SD_CS),
        )
        os.mount(sd, "/sd")
        _mounted = True
        stat = os.statvfs("/sd")
        # block_size * total_blocks gives total capacity in bytes
        total_mb = stat[0] * stat[2] // (1024 * 1024)
        free_mb = stat[0] * stat[3] // (1024 * 1024)
        print("SD card mounted at /sd: {}MB total, {}MB free".format(total_mb, free_mb))
        return True
    except Exception as e:
        print("SD card not available:", e)
        return False


def is_mounted():
    """Return True if the SD card is currently mounted."""
    return _mounted


def unmount():
    """Unmount the SD card. Safe to call even if not mounted."""
    global _mounted
    if not _mounted:
        return
    try:
        os.umount("/sd")
    except Exception:
        pass
    _mounted = False
