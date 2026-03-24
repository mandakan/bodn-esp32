# bodn/diag.py — gather system diagnostic information
#
# Returns a list of (label, value) tuples suitable for display.
# Used by boot.py (pre-framework) and ui/diag.py (Screen subclass).

import gc
import time

# Hardware status — set once by main.py after create_hardware().
_hw_status = {}


def set_hw_status(status):
    """Store hardware detection results for the diagnostic screen."""
    global _hw_status
    _hw_status = status


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

    # IP — read live from network interface if no ip passed
    if ip == "0.0.0.0":
        try:
            import network

            for mode in (network.AP_IF, network.STA_IF):
                wlan = network.WLAN(mode)
                if wlan.active() and wlan.isconnected():
                    ip = wlan.ifconfig()[0]
                    break
                if mode == network.AP_IF and wlan.active():
                    ip = wlan.ifconfig()[0]
                    break
        except Exception:
            pass
    info.append(("IP", ip))

    # Battery
    try:
        from bodn.battery import (
            read as bat_read,
            voltage_mv as bat_mv,
            status as bat_status,
        )

        pct, chg = bat_read()
        if pct is None:
            info.append(("Battery", "N/A (USB)"))
        else:
            mv = bat_mv()
            st = bat_status()
            flag = ""
            if chg:
                flag = " CHG"
            if st == "warn":
                flag += " LOW"
            elif st == "critical":
                flag += " CRIT"
            elif st == "shutdown":
                flag += " DEAD"
            info.append(
                (
                    "Battery",
                    "{}% {}.{}V{}".format(pct, mv // 1000, (mv % 1000) // 100, flag),
                )
            )
    except Exception:
        pass

    # Temperature
    try:
        from bodn.temperature import read as temp_read, sensor_count as temp_count

        temps = temp_read()
        if temp_count() == 0:
            info.append(("Temp", "no sensors"))
        else:
            parts = []
            for i in sorted(temps):
                t_c = temps[i]
                parts.append("{}C".format(int(t_c)) if t_c is not None else "?")
            info.append(("Temp", " / ".join(parts)))
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

    # Hardware detection (set by main.py after create_hardware)
    if _hw_status:
        parts = []
        for name, ok in sorted(_hw_status.items()):
            parts.append("{}:{}".format(name.upper(), "ok" if ok else "--"))
        info.append(("Hardware", " ".join(parts)))

    return info
