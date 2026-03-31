# bodn/encoder_scope.py — visual oscilloscope for encoder signals
#
# Displays raw CLK and DT signals on the primary TFT as a rolling
# scope trace, plus decoded direction and step count. Useful for
# diagnosing encoder wiring (noise, missing pull-ups, swapped CLK/DT).
#
# Usage from REPL (after /skip_main boot):
#   from bodn.encoder_scope import run
#   run()          # both encoders
#   run(enc=1)     # ENC1 (NAV) only
#   run(enc=2)     # ENC2 only

import time
from machine import Pin, SPI
from bodn import config
from st7735 import ST7735

# Quadrature state-machine lookup table for direction decoding.
# Index = (prev_state << 2) | curr_state, where state = (CLK << 1) | DT.
# Values: 1 = CW step, 255 = CCW step (-1 as unsigned byte), 0 = invalid/skip.
_QEM = bytes([0, 1, 255, 0, 255, 0, 0, 1, 1, 0, 0, 255, 0, 255, 1, 0])

_BG = 0x0000
_GRID = ST7735.rgb(30, 30, 30)
_CURSOR = ST7735.rgb(50, 50, 50)
_LABEL_COL = ST7735.rgb(160, 160, 160)
_CLK1 = ST7735.rgb(0, 255, 100)
_DT1 = ST7735.rgb(100, 200, 255)
_CLK2 = ST7735.rgb(255, 100, 0)
_DT2 = ST7735.rgb(255, 50, 200)
_CW_COL = ST7735.rgb(0, 200, 0)
_CCW_COL = ST7735.rgb(200, 0, 0)

_W = config.TFT_WIDTH
_H = config.TFT_HEIGHT
_LABEL_W = 40
_SCOPE_X = _LABEL_W
_SCOPE_W = _W - _LABEL_W
_TRACE_H = 30
_GAP = 6
_HIGH_Y = 4
_LOW_Y = _TRACE_H - 5
_STATUS_Y = _H - 12  # bottom row for status text
_STATUS_H = 12
_ERASE_GAP = 8  # blank columns ahead of cursor (ECG-style)


def run(enc=0, sample_ms=2):
    """Run the encoder oscilloscope. Ctrl-C to stop.

    Args:
        enc: 0=both encoders, 1=ENC1 only, 2=ENC2 only
        sample_ms: milliseconds between samples (1=fastest)
    """
    spi = SPI(
        1, baudrate=26_000_000, sck=Pin(config.TFT_SCK), mosi=Pin(config.TFT_MOSI)
    )
    tft = ST7735(
        spi,
        cs=Pin(config.TFT_CS, Pin.OUT),
        dc=Pin(config.TFT_DC, Pin.OUT),
        rst=Pin(config.TFT_RST, Pin.OUT),
        width=_W,
        height=_H,
        col_offset=config.TFT_COL_OFFSET,
        row_offset=config.TFT_ROW_OFFSET,
        madctl=config.TFT_MADCTL,
    )
    Pin(config.TFT_BL, Pin.OUT, value=1)

    enc1_clk = Pin(config.ENC1_CLK, Pin.IN, Pin.PULL_UP)
    enc1_dt = Pin(config.ENC1_DT, Pin.IN, Pin.PULL_UP)
    enc2_clk = Pin(config.ENC2_CLK, Pin.IN, Pin.PULL_UP)
    enc2_dt = Pin(config.ENC2_DT, Pin.IN, Pin.PULL_UP)

    # Build traces: (label, colour, pin)
    traces = []
    # Track which encoder groups we have for decoded status
    enc_groups = []  # list of (clk_idx, dt_idx, label)

    if enc in (0, 1):
        traces.append(("CLK1", _CLK1, enc1_clk))
        traces.append(("DT1", _DT1, enc1_dt))
        enc_groups.append((len(traces) - 2, len(traces) - 1, "E1"))
    if enc in (0, 2):
        traces.append(("CLK2", _CLK2, enc2_clk))
        traces.append(("DT2", _DT2, enc2_dt))
        enc_groups.append((len(traces) - 2, len(traces) - 1, "E2"))

    n = len(traces)
    total_h = n * _TRACE_H + (n - 1) * _GAP
    y_start = max(12, (_H - total_h - _STATUS_H - 8) // 2)
    trace_y = [y_start + i * (_TRACE_H + _GAP) for i in range(n)]

    # Static elements
    tft.fill(_BG)
    tft.text("Scope", _SCOPE_X + 4, 2, _LABEL_COL)
    ms_txt = "{}ms/px".format(sample_ms)
    tft.text(ms_txt, _W - len(ms_txt) * 8 - 4, 2, _LABEL_COL)
    for i, (label, colour, _) in enumerate(traces):
        tft.text(label, 2, trace_y[i] + (_TRACE_H - 8) // 2, colour)
        tft.hline(_SCOPE_X, trace_y[i] + _HIGH_Y, _SCOPE_W, _GRID)
        tft.hline(_SCOPE_X, trace_y[i] + _LOW_Y, _SCOPE_W, _GRID)
    tft.show()

    # Encoder decode state per group (quadrature state machine)
    steps = [0] * len(enc_groups)
    enc_state = []  # (CLK << 1) | DT for each group
    for ci, di, _ in enc_groups:
        enc_state.append((traces[ci][2].value() << 1) | traces[di][2].value())
    prev_status = ""

    prev = [1] * n
    x = 0
    sample_ms = max(1, min(50, sample_ms))
    print(
        "Scope: {} traces, {}ms/px — turn encoders slowly, Ctrl-C to stop".format(
            n, sample_ms
        )
    )

    try:
        while True:
            sx = _SCOPE_X + x

            # Sample all pins
            vals = [traces[i][2].value() for i in range(n)]

            for i in range(n):
                ty = trace_y[i]
                val = vals[i]
                cur_py = ty + (_HIGH_Y if val else _LOW_Y)
                prev_py = ty + (_HIGH_Y if prev[i] else _LOW_Y)

                # Clear column
                tft.vline(sx, ty, _TRACE_H, _BG)
                # Grid dots
                tft.pixel(sx, ty + _HIGH_Y, _GRID)
                tft.pixel(sx, ty + _LOW_Y, _GRID)
                # Signal — edge or level
                if val != prev[i]:
                    y_top = min(cur_py, prev_py)
                    tft.vline(sx, y_top, abs(cur_py - prev_py) + 1, traces[i][1])
                else:
                    tft.pixel(sx, cur_py, traces[i][1])
                prev[i] = val

                # ECG-style erase gap ahead of cursor
                for g_off in range(1, _ERASE_GAP + 1):
                    gx = _SCOPE_X + ((x + g_off) % _SCOPE_W)
                    tft.vline(gx, ty, _TRACE_H, _BG)

            # Decode direction via quadrature state machine
            for g, (ci, di, label) in enumerate(enc_groups):
                new_st = (vals[ci] << 1) | vals[di]
                delta = _QEM[(enc_state[g] << 2) | new_st]
                if delta == 1:
                    steps[g] += 1
                elif delta == 255:  # -1
                    steps[g] -= 1
                enc_state[g] = new_st

            # Update status bar
            parts = []
            for g, (_, _, label) in enumerate(enc_groups):
                s = steps[g]
                if s > 0:
                    arrow = ">"
                elif s < 0:
                    arrow = "<"
                else:
                    arrow = "="
                parts.append("{} {}{:+d}".format(label, arrow, s))
            status = "  ".join(parts)

            if status != prev_status:
                tft.fill_rect(0, _STATUS_Y, _W, _STATUS_H, _BG)
                # Draw each group with colour
                sx_text = 4
                for g, (_, _, label) in enumerate(enc_groups):
                    s = steps[g]
                    col = _CW_COL if s > 0 else _CCW_COL if s < 0 else _LABEL_COL
                    txt = "{} {:+d}".format(label, s)
                    tft.text(txt, sx_text, _STATUS_Y + 2, col)
                    sx_text += len(txt) * 8 + 16
                tft.show_rect(0, _STATUS_Y, _W, _STATUS_H)
                prev_status = status

            # Flush trace columns — current + erase gap ahead
            flush_y = trace_y[0]
            flush_h = trace_y[-1] + _TRACE_H - flush_y
            # Flush from current column through the gap in one rect when contiguous
            gap_end_x = _SCOPE_X + ((x + _ERASE_GAP) % _SCOPE_W)
            if gap_end_x > sx:
                tft.show_rect(sx, flush_y, gap_end_x - sx + 1, flush_h)
            else:
                # Wrapped around — flush two segments
                tft.show_rect(sx, flush_y, _SCOPE_X + _SCOPE_W - sx, flush_h)
                tft.show_rect(_SCOPE_X, flush_y, gap_end_x - _SCOPE_X + 1, flush_h)

            x = (x + 1) % _SCOPE_W
            time.sleep_ms(sample_ms)

    except KeyboardInterrupt:
        print()
        for g, (_, _, label) in enumerate(enc_groups):
            print("  {}: {} steps".format(label, steps[g]))
        print("Scope stopped.")
        tft.fill(_BG)
        tft.text("Scope stopped", 100, 116, _LABEL_COL)
        tft.show()
