# bodn/ftp.py — minimal async FTP server for dev-mode OTA staging
#
# Files uploaded via FTP land in the OTA staging directory (/.ota/).
# After uploading, call POST /api/ota/commit — the device verifies MD5
# hashes from MANIFEST.json and atomically moves files into place.
#
# Only starts when WiFi STA is connected. Always requires authentication.
# Not intended for production use — this is a dev-speed tool.

import os

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import network
except ImportError:
    network = None

OTA_STAGE = "/.ota"
_DATA_PORT_BASE = 50100
_DATA_PORT_RANGE = 10  # rotate through 50100–50109 to avoid TIME_WAIT
_server = None
_data_port_idx = 0


def _get_ip():
    if network is None:
        return "127.0.0.1"
    sta = network.WLAN(network.STA_IF)
    if sta.isconnected():
        return sta.ifconfig()[0]
    ap = network.WLAN(network.AP_IF)
    return ap.ifconfig()[0]


def _list_dir(path):
    """Return unix-style LIST lines for a directory."""
    lines = []
    try:
        entries = os.listdir(path)
    except OSError:
        return lines
    for name in entries:
        full = path + "/" + name
        try:
            st = os.stat(full)
            is_dir = st[0] & 0x4000
        except OSError:
            continue
        if is_dir:
            line = "drwxr-xr-x 1 bodn bodn 0 Jan  1 00:00 " + name
        else:
            line = "-rw-r--r-- 1 bodn bodn {} Jan  1 00:00 {}".format(st[6], name)
        lines.append(line)
    return lines


class _FTPSession:
    def __init__(self, reader, writer, user, password, settings=None):
        self._r = reader
        self._w = writer
        self._user = user
        self._pass = password
        self._settings = settings
        self.authed = False
        self._pending_user = None
        self.cwd = "/"
        # PASV state — set up by PASV, consumed by next transfer command
        self._data_ready = None  # asyncio.Event or None
        self._data_r = None
        self._data_w = None
        self._data_srv = None

    def _poke_idle(self):
        """Reset the device's idle timer so a long sync doesn't trip lightsleep."""
        if self._settings is None:
            return
        tracker = self._settings.get("_idle_tracker")
        if tracker is not None:
            tracker.poke()

    def _real(self, path=""):
        """Map an FTP path (relative to FTP root) to a real filesystem path
        under the staging directory.

        FTP root "/" maps to OTA_STAGE ("/.ota").
        """
        if not path:
            path = self.cwd
        elif not path.startswith("/"):
            base = self.cwd if self.cwd.endswith("/") else self.cwd + "/"
            path = base + path
        # Normalise: remove empty segments
        parts = [p for p in path.split("/") if p]
        normalised = "/" + "/".join(parts) if parts else "/"
        return OTA_STAGE if normalised == "/" else OTA_STAGE + normalised

    async def _send(self, msg):
        self._w.write(msg.encode())
        await self._w.drain()

    # ------------------------------------------------------------------ PASV

    async def _cmd_PASV(self, _):
        global _data_port_idx
        # Close any previous data server that was never used
        if self._data_srv is not None:
            try:
                self._data_srv.close()
            except Exception:
                pass
            self._data_srv = None

        self._data_ready = asyncio.Event()
        self._data_r = None
        self._data_w = None

        async def _on_data(r, w):
            self._data_r = r
            self._data_w = w
            self._data_ready.set()

        # Rotate through a small port range to avoid TIME_WAIT collisions
        port = _DATA_PORT_BASE + _data_port_idx
        _data_port_idx = (_data_port_idx + 1) % _DATA_PORT_RANGE
        self._data_srv = await asyncio.start_server(_on_data, "0.0.0.0", port)
        ip = _get_ip()
        h = ip.replace(".", ",")
        ph, pl = port >> 8, port & 0xFF
        await self._send("227 Entering Passive Mode ({},{},{})\r\n".format(h, ph, pl))

    async def _get_data(self):
        """Wait for the PASV data connection and return (reader, writer).
        Raises OSError on timeout or if PASV was not called first.
        """
        if self._data_ready is None:
            raise OSError("no PASV")
        try:
            await asyncio.wait_for(self._data_ready.wait(), 15)
        except Exception:
            raise OSError("data connection timeout")
        finally:
            if self._data_srv is not None:
                try:
                    self._data_srv.close()
                except Exception:
                    pass
                self._data_srv = None
        self._data_ready = None
        return self._data_r, self._data_w

    # ------------------------------------------------------------------ main loop

    async def run(self):
        await self._send("220 Bodn FTP (dev OTA)\r\n")
        try:
            while True:
                try:
                    line = await asyncio.wait_for(self._r.readline(), 120)
                except Exception:
                    break
                if not line:
                    break
                text = line.decode().strip()
                if not text:
                    continue
                self._poke_idle()
                parts = text.split(" ", 1)
                cmd = parts[0].upper()
                arg = parts[1].strip() if len(parts) > 1 else ""
                handler = getattr(self, "_cmd_" + cmd, None)
                if handler:
                    await handler(arg)
                else:
                    await self._send("502 {} not implemented\r\n".format(cmd))
        except Exception:
            pass
        try:
            self._w.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ commands

    async def _cmd_USER(self, arg):
        self._pending_user = arg
        await self._send("331 Password required\r\n")

    async def _cmd_PASS(self, arg):
        if self._pending_user == self._user and arg == self._pass:
            self.authed = True
            await self._send("230 Logged in\r\n")
        else:
            await self._send("530 Login incorrect\r\n")

    async def _cmd_SYST(self, _):
        await self._send("215 UNIX Type: L8\r\n")

    async def _cmd_FEAT(self, _):
        await self._send("211-Features:\r\n SIZE\r\n211 End\r\n")

    async def _cmd_TYPE(self, _):
        # Accept any TYPE (I/A) — always transfer in binary
        await self._send("200 Type OK\r\n")

    async def _cmd_NOOP(self, _):
        await self._send("200 OK\r\n")

    async def _cmd_QUIT(self, _):
        await self._send("221 Bye\r\n")

    async def _cmd_PWD(self, _):
        if not self.authed:
            await self._send("530 Not logged in\r\n")
            return
        await self._send('257 "{}" is current directory\r\n'.format(self.cwd))

    async def _cmd_CWD(self, arg):
        if not self.authed:
            await self._send("530 Not logged in\r\n")
            return
        if arg == "/":
            self.cwd = "/"
        elif arg.startswith("/"):
            self.cwd = arg
        else:
            self.cwd = self.cwd.rstrip("/") + "/" + arg
        await self._send("250 Directory changed\r\n")

    async def _cmd_CDUP(self, _):
        if not self.authed:
            await self._send("530 Not logged in\r\n")
            return
        if self.cwd != "/":
            self.cwd = self.cwd.rsplit("/", 1)[0] or "/"
        await self._send("200 OK\r\n")

    async def _cmd_MKD(self, arg):
        if not self.authed:
            await self._send("530 Not logged in\r\n")
            return
        real = self._real(arg)
        # Create all intermediate directories
        parts = [p for p in real.split("/") if p]
        cur = ""
        for part in parts:
            cur += "/" + part
            try:
                os.mkdir(cur)
            except OSError:
                pass  # already exists
        await self._send('257 "{}" created\r\n'.format(arg))

    async def _cmd_SIZE(self, arg):
        if not self.authed:
            await self._send("530 Not logged in\r\n")
            return
        real = self._real(arg)
        try:
            await self._send("213 {}\r\n".format(os.stat(real)[6]))
        except OSError:
            await self._send("550 File not found\r\n")

    async def _cmd_DELE(self, arg):
        if not self.authed:
            await self._send("530 Not logged in\r\n")
            return
        try:
            os.remove(self._real(arg))
        except OSError:
            pass
        await self._send("250 Deleted\r\n")

    async def _cmd_LIST(self, arg):
        if not self.authed:
            await self._send("530 Not logged in\r\n")
            return
        try:
            dr, dw = await self._get_data()
        except OSError as e:
            await self._send("425 {}\r\n".format(e))
            return
        path = self._real(arg or self.cwd)
        lines = _list_dir(path)
        await self._send("150 Directory listing\r\n")
        for line in lines:
            dw.write((line + "\r\n").encode())
        try:
            await dw.drain()
        except Exception:
            pass
        try:
            dw.close()
        except Exception:
            pass
        await self._send("226 Transfer complete\r\n")

    async def _cmd_NLST(self, arg):
        if not self.authed:
            await self._send("530 Not logged in\r\n")
            return
        try:
            dr, dw = await self._get_data()
        except OSError as e:
            await self._send("425 {}\r\n".format(e))
            return
        path = self._real(arg or self.cwd)
        try:
            entries = os.listdir(path)
        except OSError:
            entries = []
        await self._send("150 Name list\r\n")
        for name in entries:
            dw.write((name + "\r\n").encode())
        try:
            await dw.drain()
        except Exception:
            pass
        try:
            dw.close()
        except Exception:
            pass
        await self._send("226 Transfer complete\r\n")

    async def _cmd_STOR(self, arg):
        if not self.authed:
            await self._send("530 Not logged in\r\n")
            return
        real = self._real(arg)
        # Ensure all parent directories exist before opening data connection
        parent = real.rsplit("/", 1)[0]
        parts = [p for p in parent.split("/") if p]
        cur = ""
        for part in parts:
            cur += "/" + part
            try:
                os.mkdir(cur)
            except OSError:
                pass
        try:
            dr, dw = await self._get_data()
        except OSError as e:
            await self._send("425 {}\r\n".format(e))
            return
        await self._send("125 Transfer starting\r\n")
        # Write to a .tmp file first; rename on success (atomic at file level)
        tmp = real + ".tmp"
        chunks_since_poke = 0
        try:
            with open(tmp, "wb") as f:
                while True:
                    chunk = await dr.read(1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    chunks_since_poke += 1
                    # Keep the idle timer fresh during long single-file uploads.
                    if chunks_since_poke >= 32:
                        self._poke_idle()
                        chunks_since_poke = 0
                    # Yield to the async loop so TCP can breathe during
                    # long flash writes — without this, large files stall.
                    await asyncio.sleep_ms(0)
            try:
                dw.close()  # close writer to release the socket (reader.close won't)
            except Exception:
                pass
            try:
                os.remove(real)
            except OSError:
                pass
            os.rename(tmp, real)
            await self._send("226 Transfer complete\r\n")
        except Exception as e:
            try:
                dw.close()
            except Exception:
                pass
            try:
                os.remove(tmp)
            except OSError:
                pass
            await self._send("550 Transfer failed: {}\r\n".format(e))

    async def _cmd_RETR(self, arg):
        if not self.authed:
            await self._send("530 Not logged in\r\n")
            return
        real = self._real(arg)
        try:
            size = os.stat(real)[6]
        except OSError:
            await self._send("550 File not found\r\n")
            return
        try:
            dr, dw = await self._get_data()
        except OSError as e:
            await self._send("425 {}\r\n".format(e))
            return
        await self._send("150 Opening connection, {} bytes\r\n".format(size))
        try:
            with open(real, "rb") as f:
                while True:
                    chunk = f.read(512)
                    if not chunk:
                        break
                    dw.write(chunk)
            await dw.drain()
            try:
                dw.close()
            except Exception:
                pass
            await self._send("226 Transfer complete\r\n")
        except Exception as e:
            await self._send("550 Read failed: {}\r\n".format(e))


async def start_ftp(settings):
    """Start the FTP server. Returns the server object, or None if not applicable.

    Only starts when WiFi STA is connected. Does nothing in AP-only mode so
    the server is never exposed on the child-facing access point.
    """
    global _server
    if not settings.get("ftp_enabled", True):
        return None
    if network is None:
        return None
    sta = network.WLAN(network.STA_IF)
    if not sta.isconnected():
        return None

    user = settings.get("ftp_user", "bodn")
    password = settings.get("ftp_pass", "bodn")

    from bodn.config import FTP_PORT

    async def _cb(r, w):
        session = _FTPSession(r, w, user, password, settings=settings)
        await session.run()

    try:
        try:
            os.mkdir(OTA_STAGE)
        except OSError:
            pass
        _server = await asyncio.start_server(_cb, "0.0.0.0", FTP_PORT)
        print(
            "FTP server on {}:{} (dev OTA — STA mode only)".format(
                sta.ifconfig()[0], FTP_PORT
            )
        )
        return _server
    except Exception as e:
        print("FTP server failed to start:", e)
        return None
