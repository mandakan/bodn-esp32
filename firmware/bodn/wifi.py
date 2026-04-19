# bodn/wifi.py — WiFi connect helpers for ESP32

import time
import network


def connect_sta(ssid, password, timeout=10):
    """Connect to a WiFi network in station mode. Returns True on success."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    # Allow WiFi radio to fully initialise after activation
    time.sleep(0.1)
    if wlan.isconnected():
        return True
    # Clear any stale connection state from a previous boot
    wlan.disconnect()
    time.sleep(0.1)
    wlan.connect(ssid, password)
    start = time.time()
    while not wlan.isconnected():
        if time.time() - start > timeout:
            return False
        time.sleep(0.5)
    return True


def start_ap(ssid="Bodn", timeout=5):
    """Start a WiFi access point. Returns the AP IP address."""
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=ssid)
    start = time.time()
    while not ap.active():
        if time.time() - start > timeout:
            return "0.0.0.0"
        time.sleep(0.1)
    return ap.ifconfig()[0]


def get_ip():
    """Return the current IP address (STA preferred, then AP)."""
    sta = network.WLAN(network.STA_IF)
    if sta.active() and sta.isconnected():
        return sta.ifconfig()[0]
    ap = network.WLAN(network.AP_IF)
    if ap.active():
        return ap.ifconfig()[0]
    return "0.0.0.0"


def _set_hostname(hostname="bodn"):
    """Set the network hostname so mDNS advertises <hostname>.local.

    Must be called BEFORE the STA interface comes up: MicroPython's esp32
    port initialises the ESP-IDF mDNS responder once, on IP_EVENT_STA_GOT_IP,
    and reads the current hostname at that moment (see
    ports/esp32/network_wlan.c::network_wlan_ip_event_handler). Setting the
    hostname afterwards updates the DHCP-client name but leaves the mDNS
    responder stuck on the default, which is why `<host>.local` silently
    fails to resolve.
    """
    try:
        network.hostname(hostname)
    except Exception as e:
        print("mDNS: could not set hostname:", e)


class WiFiController:
    """Runtime WiFi enable/disable control."""

    def __init__(self, settings):
        self._settings = settings
        self._active = False

    def is_active(self):
        """Check if any WiFi interface is currently active."""
        try:
            sta = network.WLAN(network.STA_IF)
            ap = network.WLAN(network.AP_IF)
            self._active = sta.active() or ap.active()
        except Exception:
            self._active = False
        return self._active

    def disable(self):
        """Disable all WiFi interfaces."""
        try:
            network.WLAN(network.STA_IF).active(False)
            network.WLAN(network.AP_IF).active(False)
            self._active = False
            print("WiFi: disabled")
        except Exception as e:
            print("WiFi disable error:", e)

    def enable(self):
        """Re-enable WiFi using current settings."""
        try:
            ip = connect(self._settings)
            self._active = True
            print("WiFi: enabled, IP:", ip)
        except Exception as e:
            print("WiFi enable error:", e)


def connect(settings):
    """Connect WiFi based on settings. Returns IP string.

    Priority:
    1. STA mode with configured SSID (user set via web UI)
    2. AP mode if explicitly configured
    3. Wokwi-GUEST fallback (for simulator — skipped if wifi_mode is "ap" with SSID set)
    4. AP mode as last resort
    """
    mode = settings.get("wifi_mode", "ap")
    ssid = settings.get("wifi_ssid", "")
    password = settings.get("wifi_pass", "")

    hostname = settings.get("hostname", "bodn")

    # Set hostname BEFORE any STA activity so the mDNS responder picks
    # up the right name at init time (see _set_hostname docstring).
    _set_hostname(hostname)

    # User configured a network — try it
    if mode == "sta" and ssid:
        print("WiFi: connecting to", ssid)
        if connect_sta(ssid, password):
            print("mDNS: {}.local".format(hostname))
            return get_ip()
        print("WiFi: failed to connect to", ssid)

    # User explicitly wants AP mode and has no STA config — skip Wokwi-GUEST
    if mode == "ap" and not ssid:
        # But first try Wokwi-GUEST in case we're in the simulator.
        # On real hardware this times out in 3s — acceptable at first boot.
        # Once the user configures WiFi via the web UI, this path is skipped.
        print("WiFi: trying Wokwi-GUEST...")
        if connect_sta("Wokwi-GUEST", "", timeout=3):
            print("mDNS: {}.local".format(hostname))
            return get_ip()

    # Fall back to AP mode — mDNS responder only runs on the STA interface
    # in MicroPython's esp32 port, so bodn.local won't resolve here.
    print("WiFi: starting AP mode")
    return start_ap()
