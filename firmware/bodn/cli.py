# bodn/cli.py — serial REPL helpers for configuration
#
# Usage from REPL (Ctrl-C to stop main loop first):
#   from bodn.cli import *
#   show()              # print all settings
#   wifi("SSID", "pw")  # configure WiFi STA mode
#   ap()                # switch to AP mode
#   set("key", value)   # set any setting
#   save()              # persist to flash
#   reboot()            # machine.reset()

from bodn.storage import load_settings, save_settings

_s = load_settings()


def show():
    """Print all current settings."""
    for k in sorted(_s):
        if not k.startswith("_"):
            print("  {:20s} = {}".format(k, repr(_s[k])))


def get(key):
    """Get a setting value."""
    return _s.get(key)


def set(key, value):
    """Set a setting value (call save() to persist)."""
    _s[key] = value
    print("  {} = {}".format(key, repr(value)))


def wifi(ssid, password="", mode="sta"):
    """Configure WiFi and save. mode='sta' or 'ap'."""
    _s["wifi_ssid"] = ssid
    _s["wifi_pass"] = password
    _s["wifi_mode"] = mode
    save()
    print("WiFi configured: mode={} ssid={}".format(mode, ssid))
    print("Reboot to apply: reboot()")


def ap():
    """Switch to AP mode and save."""
    _s["wifi_mode"] = "ap"
    save()
    print("AP mode set. Reboot to apply: reboot()")


def save():
    """Persist settings to flash."""
    save_settings(_s)
    print("Settings saved.")


def reboot():
    """Reset the device."""
    import machine

    machine.reset()
