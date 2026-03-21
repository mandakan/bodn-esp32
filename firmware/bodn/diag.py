# bodn/diag.py — gather system diagnostic information
#
# Returns a list of (label, value) tuples suitable for display.
# Used by boot.py (pre-framework) and ui/diag.py (Screen subclass).

import gc
import time


def gather(ip="0.0.0.0", boot_results=None, boot_steps=None):
    """Collect system diagnostics. Returns list of (label, value) pairs."""
    info = []

    # Platform and MicroPython version
    import sys

    ver = sys.version
    info.append(("uPy", ver.split(";")[0] if ";" in ver else ver[:20]))
    info.append(("Platform", sys.platform))

    # CPU frequency
    try:
        from machine import freq as _cpu_freq

        info.append(("CPU", "{} MHz".format(_cpu_freq() // 1_000_000)))
    except Exception:
        pass

    # Memory
    gc.collect()
    free = gc.mem_free()
    alloc = gc.mem_alloc()
    info.append(("RAM free", "{} KB".format(free // 1024)))
    info.append(("RAM used", "{} KB".format(alloc // 1024)))

    # Flash filesystem
    try:
        import os

        st = os.statvfs("/")
        fs_total = st[0] * st[2] // 1024
        fs_free = st[0] * st[3] // 1024
        info.append(("Flash", "{}/{} KB".format(fs_free, fs_total)))
    except Exception:
        pass

    # WiFi MAC
    try:
        import network

        mac = network.WLAN(network.STA_IF).config("mac")
        mac_str = ":".join("{:02X}".format(b) for b in mac)
        info.append(("MAC", mac_str))
    except Exception:
        pass

    # IP
    info.append(("IP", ip))

    # Battery
    try:
        from bodn.battery import read as bat_read

        pct, chg = bat_read()
        info.append(("Battery", "{}%{}".format(pct, " CHG" if chg else "")))
    except Exception:
        pass

    # NTP / time
    t = time.localtime()
    if t[0] >= 2024:
        info.append(("Time", "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])))

    # Boot results
    if boot_results and boot_steps:
        summary = " ".join(
            "{}:{}".format(boot_steps[i][0], boot_results[i] or "?")
            for i in range(len(boot_steps))
        )
        info.append(("Boot", summary))

    return info
