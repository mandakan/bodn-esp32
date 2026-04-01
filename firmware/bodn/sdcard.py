# bodn/sdcard.py — SD card initialisation and mount
#
# Mounts the SD card from the ILI9341 display breakout's SD slot.
# Uses machine.SPI(2) with the micropython-lib sdcard.py driver instead
# of machine.SDCard(slot=3) — the ESP-IDF SDSPI driver leaves SPI3 in an
# unrecoverable state on the ESP32-S3 with Octal-SPIRAM.
#
# Called once during boot; no-ops gracefully if no card is inserted.

import os
from bodn import config

_mounted = False
_spi = None  # SPI bus — kept alive for the duration of the mount
_sd = None  # sdcard.SDCard block device


def mount():
    """Initialise SPI2 and mount the SD card at /sd.

    Returns True on success, False if no card is present or mount fails.
    The device boots normally without an SD card — only media assets are
    unavailable; firmware and core UX sounds are on flash.
    """
    global _mounted, _spi, _sd

    if _mounted:
        return True

    from machine import SPI, Pin
    import sdcard

    try:
        _spi = SPI(
            2,
            baudrate=10_000_000,
            sck=Pin(config.SD_SCK),
            mosi=Pin(config.SD_MOSI),
            miso=Pin(config.SD_MISO),
        )
        cs = Pin(config.SD_CS, Pin.OUT, value=1)
        _sd = sdcard.SDCard(_spi, cs, baudrate=10_000_000)
        os.mount(_sd, "/sd")
    except OSError as e:
        _cleanup()
        print("SD card not available:", e)
        return False
    except Exception as e:
        _cleanup()
        print("SD card not available:", e)
        return False

    _mounted = True
    stat = os.statvfs("/sd")
    total_mb = stat[0] * stat[2] // (1024 * 1024)
    free_mb = stat[0] * stat[3] // (1024 * 1024)
    print("SD card mounted at /sd: {}MB total, {}MB free".format(total_mb, free_mb))
    return True


def _cleanup():
    """Release SPI and SD objects after a failed mount."""
    global _spi, _sd
    if _spi is not None:
        try:
            _spi.deinit()
        except Exception:
            pass
        _spi = None
    _sd = None


def is_mounted():
    """Return True if the SD card is currently mounted."""
    return _mounted


def unmount():
    """Unmount the SD card and release the SPI bus. Safe to call even if not mounted."""
    global _mounted
    if not _mounted:
        return
    try:
        os.umount("/sd")
    except Exception:
        pass
    _cleanup()
    _mounted = False
