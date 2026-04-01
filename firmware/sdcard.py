"""
MicroPython driver for SD cards using SPI bus.

Based on micropython-lib sdcard.py, optimised for ESP32-S3 audio streaming:
- @micropython.native on hot-path methods
- Local attribute caching to reduce dict lookups
- Removed sleep_ms(1) in token polling (spin instead)

Requires an SPI bus and a CS pin.  Provides readblocks and writeblocks
methods so the device can be mounted as a filesystem.
"""

from micropython import const
import micropython
import time


_CMD_TIMEOUT = const(100)

_R1_IDLE_STATE = const(1 << 0)
_R1_ILLEGAL_COMMAND = const(1 << 2)
_TOKEN_CMD25 = const(0xFC)
_TOKEN_STOP_TRAN = const(0xFD)
_TOKEN_DATA = const(0xFE)

_FF = b"\xff"


@micropython.viper
def _crc7(buf, n: int) -> int:
    p = ptr8(buf)  # noqa: F821
    crc: int = 0
    for i in range(n):
        crc ^= int(p[i])
        for _ in range(8):
            crc = ((crc << 1) ^ (0x12 * (crc >> 7))) & 0xFF
    return crc


class SDCard:
    def __init__(self, spi, cs, baudrate=1320000):
        self.spi = spi
        self.cs = cs

        self.cmdbuf = bytearray(6)
        self.dummybuf = bytearray(512)
        self.tokenbuf = bytearray(1)
        for i in range(512):
            self.dummybuf[i] = 0xFF
        self.dummybuf_memoryview = memoryview(self.dummybuf)

        # initialise the card
        self.init_card(baudrate)

    def init_spi(self, baudrate):
        try:
            master = self.spi.MASTER
        except AttributeError:
            self.spi.init(baudrate=baudrate, phase=0, polarity=0)
        else:
            self.spi.init(master, baudrate=baudrate, phase=0, polarity=0)

    def init_card(self, baudrate):
        self.cs.init(self.cs.OUT, value=1)
        self.init_spi(100000)

        for i in range(16):
            self.spi.write(_FF)

        for _ in range(5):
            if self.cmd(0, 0) == _R1_IDLE_STATE:
                break
        else:
            raise OSError("no SD card")

        r = self.cmd(8, 0x01AA, 4)
        if r == _R1_IDLE_STATE:
            self.init_card_v2()
        elif r == (_R1_IDLE_STATE | _R1_ILLEGAL_COMMAND):
            self.init_card_v1()
        else:
            raise OSError("couldn't determine SD card version")

        if self.cmd(9, 0, 0, False) != 0:
            raise OSError("no response from SD card")
        csd = bytearray(16)
        self.readinto(csd)
        if csd[0] & 0xC0 == 0x40:
            self.sectors = ((csd[7] << 16 | csd[8] << 8 | csd[9]) + 1) * 1024
        elif csd[0] & 0xC0 == 0x00:
            c_size = (csd[6] & 0b11) << 10 | csd[7] << 2 | csd[8] >> 6
            c_size_mult = (csd[9] & 0b11) << 1 | csd[10] >> 7
            read_bl_len = csd[5] & 0b1111
            capacity = (c_size + 1) * (2 ** (c_size_mult + 2)) * (2**read_bl_len)
            self.sectors = capacity // 512
        else:
            raise OSError("SD card CSD format not supported")

        if self.cmd(16, 512) != 0:
            raise OSError("can't set 512 block size")

        self.init_spi(baudrate)

    def init_card_v1(self):
        for i in range(_CMD_TIMEOUT):
            time.sleep_ms(50)
            self.cmd(55, 0)
            if self.cmd(41, 0) == 0:
                self.cdv = 512
                return
        raise OSError("timeout waiting for v1 card")

    def init_card_v2(self):
        for i in range(_CMD_TIMEOUT):
            time.sleep_ms(50)
            self.cmd(58, 0, 4)
            self.cmd(55, 0)
            if self.cmd(41, 0x40000000) == 0:
                self.cmd(58, 0, -4)
                ocr = self.tokenbuf[0]
                if not ocr & 0x40:
                    self.cdv = 512
                else:
                    self.cdv = 1
                return
        raise OSError("timeout waiting for v2 card")

    @micropython.native
    def cmd(self, cmd, arg, final=0, release=True, skip1=False):
        cs = self.cs
        spi = self.spi
        tokenbuf = self.tokenbuf

        cs(0)

        buf = self.cmdbuf
        buf[0] = 0x40 | cmd
        buf[1] = arg >> 24
        buf[2] = arg >> 16
        buf[3] = arg >> 8
        buf[4] = arg
        buf[5] = _crc7(buf, 5) | 0x01
        spi.write(buf)

        if skip1:
            spi.readinto(tokenbuf, 0xFF)

        for i in range(_CMD_TIMEOUT):
            spi.readinto(tokenbuf, 0xFF)
            response = tokenbuf[0]
            if not (response & 0x80):
                if final < 0:
                    spi.readinto(tokenbuf, 0xFF)
                    final = -1 - final
                for j in range(final):
                    spi.write(_FF)
                if release:
                    cs(1)
                    spi.write(_FF)
                return response

        cs(1)
        spi.write(_FF)
        return -1

    @micropython.native
    def readinto(self, buf):
        cs = self.cs
        spi = self.spi
        tokenbuf = self.tokenbuf

        cs(0)

        # Spin-wait for data token — no sleep, keeps latency minimal
        for i in range(_CMD_TIMEOUT):
            spi.readinto(tokenbuf, 0xFF)
            if tokenbuf[0] == _TOKEN_DATA:
                break
        else:
            cs(1)
            raise OSError("timeout waiting for response")

        mv = self.dummybuf_memoryview
        if len(buf) != len(mv):
            mv = mv[: len(buf)]
        spi.write_readinto(mv, buf)

        spi.write(_FF)
        spi.write(_FF)

        cs(1)
        spi.write(_FF)

    def write(self, token, buf):
        cs = self.cs
        spi = self.spi

        cs(0)

        spi.read(1, token)
        spi.write(buf)
        spi.write(_FF)
        spi.write(_FF)

        if (spi.read(1, 0xFF)[0] & 0x1F) != 0x05:
            cs(1)
            spi.write(_FF)
            return

        while spi.read(1, 0xFF)[0] == 0:
            pass

        cs(1)
        spi.write(_FF)

    def write_token(self, token):
        cs = self.cs
        spi = self.spi

        cs(0)
        spi.read(1, token)
        spi.write(_FF)
        while spi.read(1, 0xFF)[0] == 0x00:
            pass

        cs(1)
        spi.write(_FF)

    @micropython.native
    def readblocks(self, block_num, buf):
        spi = self.spi
        cs = self.cs
        cdv = self.cdv

        spi.write(_FF)

        nblocks = len(buf) // 512
        assert nblocks and not len(buf) % 512, "Buffer length is invalid"
        if nblocks == 1:
            if self.cmd(17, block_num * cdv, release=False) != 0:
                cs(1)
                raise OSError(5)
            self.readinto(buf)
        else:
            if self.cmd(18, block_num * cdv, release=False) != 0:
                cs(1)
                raise OSError(5)
            offset = 0
            mv = memoryview(buf)
            while nblocks:
                self.readinto(mv[offset : offset + 512])
                offset += 512
                nblocks -= 1
            if self.cmd(12, 0, skip1=True):
                raise OSError(5)

    def writeblocks(self, block_num, buf):
        spi = self.spi

        spi.write(_FF)

        nblocks, err = divmod(len(buf), 512)
        assert nblocks and not err, "Buffer length is invalid"
        if nblocks == 1:
            if self.cmd(24, block_num * self.cdv) != 0:
                raise OSError(5)
            self.write(_TOKEN_DATA, buf)
        else:
            if self.cmd(25, block_num * self.cdv) != 0:
                raise OSError(5)
            offset = 0
            mv = memoryview(buf)
            while nblocks:
                self.write(_TOKEN_CMD25, mv[offset : offset + 512])
                offset += 512
                nblocks -= 1
            self.write_token(_TOKEN_STOP_TRAN)

    def ioctl(self, op, arg):
        if op == 4:
            return self.sectors
        if op == 5:
            return 512
