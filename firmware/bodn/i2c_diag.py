# bodn/i2c_diag.py — I2C bus diagnostic tool
#
# Continuously polls the I2C bus and reports device changes, MCP register
# reads, and connection quality. Designed to survive disconnects without
# crashing — useful for finding intermittent wiring issues.
#
# Usage from REPL:
#   from bodn.i2c_diag import run
#   run()
#
# Or auto-launched by holding Ctrl-C during the boot safe-window,
# then typing: exec(open('bodn/i2c_diag.py').read())

import time
from machine import I2C, Pin
from micropython import const
from bodn import config

_EXPECTED = {
    config.MCP23017_ADDR: "MCP1 (buttons/switches)",
    config.MCP2_ADDR: "MCP2 (encoder buttons)",
    config.PCA9685_ADDR: "PCA9685 (PWM)",
}

_POLL_MS = 200
_GPIOA = const(0x12)
_GPIOB = const(0x13)


def _scan(i2c):
    """I2C scan that never raises."""
    try:
        return set(i2c.scan())
    except Exception:
        return set()


def _read_reg(i2c, addr, reg):
    """Read one register, return value or None on error."""
    try:
        buf = bytearray(1)
        i2c.readfrom_mem_into(addr, reg, buf)
        return buf[0]
    except Exception:
        return None


def _fmt_pins(val):
    """Format 8-bit port value as pin states: 1=high(open) 0=low(pressed)."""
    if val is None:
        return "--------"
    return "".join("1" if val & (1 << i) else "0" for i in range(8))


def run():
    """Main diagnostic loop. Ctrl-C to exit."""
    i2c = I2C(0, scl=Pin(config.I2C_SCL), sda=Pin(config.I2C_SDA), freq=400_000)

    print()
    print("=== I2C Bus Diagnostic ===")
    print("Expected devices:")
    for addr, name in sorted(_EXPECTED.items()):
        print("  0x{:02X}  {}".format(addr, name))
    print()
    print("Polling every {}ms — Ctrl-C to stop".format(_POLL_MS))
    print("--------------------------------------------------")

    prev_devs = None
    prev_porta = {}
    prev_portb = {}
    scan_count = 0
    fail_count = 0

    try:
        while True:
            devs = _scan(i2c)
            scan_count += 1

            # Report bus changes
            if devs != prev_devs:
                if prev_devs is None:
                    # First scan
                    if devs:
                        found = ", ".join("0x{:02X}".format(a) for a in sorted(devs))
                        print("[SCAN] Found: {}".format(found))
                    else:
                        print("[SCAN] No devices found!")
                else:
                    added = devs - prev_devs
                    removed = prev_devs - devs
                    for a in sorted(added):
                        name = _EXPECTED.get(a, "unknown")
                        print("[+] 0x{:02X} appeared  ({})".format(a, name))
                    for a in sorted(removed):
                        name = _EXPECTED.get(a, "unknown")
                        print("[-] 0x{:02X} LOST      ({})".format(a, name))

                # Check for missing expected devices
                missing = set(_EXPECTED.keys()) - devs
                if missing:
                    names = ", ".join("0x{:02X}".format(a) for a in sorted(missing))
                    print("[!] Missing: {}".format(names))

                prev_devs = devs

            # Read MCP ports for devices that are present
            for addr in sorted(_EXPECTED.keys()):
                if addr not in devs:
                    continue
                if addr == config.PCA9685_ADDR:
                    continue  # PCA doesn't have GPIO ports

                pa = _read_reg(i2c, addr, _GPIOA)
                pb = _read_reg(i2c, addr, _GPIOB)

                if pa is None or pb is None:
                    if prev_porta.get(addr) is not None:
                        name = _EXPECTED.get(addr, "?")
                        print("[!] 0x{:02X} read FAILED ({})".format(addr, name))
                        fail_count += 1
                    prev_porta[addr] = None
                    prev_portb[addr] = None
                    continue

                # Only print when pin states change
                if pa != prev_porta.get(addr) or pb != prev_portb.get(addr):
                    name = _EXPECTED.get(addr, "?")
                    print(
                        "0x{:02X} A=[{}] B=[{}]  {}".format(
                            addr, _fmt_pins(pa), _fmt_pins(pb), name
                        )
                    )
                    prev_porta[addr] = pa
                    prev_portb[addr] = pb

            time.sleep_ms(_POLL_MS)

    except KeyboardInterrupt:
        print()
        print("--------------------------------------------------")
        print("Scans: {}  Read failures: {}".format(scan_count, fail_count))
        print("Diagnostic stopped.")


# Allow direct execution: exec(open('bodn/i2c_diag.py').read())
if __name__ == "__main__" or __name__ == "__builtins__":
    run()
